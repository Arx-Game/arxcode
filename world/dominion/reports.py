"""
Types of reports that we'll use in Dominion to inform the player
of bad events that have occurred. The Reports here will be wrappers
around an Inform object that is either created or retrieved based
on whether the player has an existing report for this week.
"""
import traceback


class Report(object):
    def __init__(self, owner, week, category=None, inform_creator=None):
        self.owner = owner
        self.week = week
        self.category = category
        self.inform_creator = inform_creator
    
    def get_or_create_report(self, category):
        if self.inform_creator:
            # kind of hacky way to determine if this is a AccountDB or Organization instance, but whatever
            if hasattr(self.owner, 'char_ob'):
                report = self.inform_creator.add_player_inform(self.owner, "", category)
            else:
                report = self.inform_creator.add_org_inform(self.owner, "", category)
        else:
            owner = self.owner
            week = self.week
            report = owner.informs.create(week=week, category=self.category)
        return report
            

class ProjectReport(Report):
    def __init__(self, owner, week, project, new_total):
        self.project = project
        self.new_total = new_total
        super(ProjectReport, self).__init__(owner, week, "project")
        self.generate_project_report()

    def generate_project_report(self):
        report = self.get_or_create_report("project")
        txt = "Project report: %s\n" % self.project.domain
        txt += "Project type: %s\n" % self.project.get_type_display()
        txt += "Amount increased: %s\n" % self.project.amount
        txt += "New total: %s\n" % self.new_total
        report.message += txt
        report.save()
        

class StarvationReport(Report):
    pass


class BattleReport(Report):
    def __init__(self, owner, battle):
        self.battle = battle
        super(BattleReport, self).__init__(owner, battle.week, "battle")
        self.generate_battle_report()

    # noinspection PyBroadException
    def generate_battle_report(self):
        try:
            txt = self.text_from_battle()
            self.owner.informs.create(week=self.week, message=txt, category="battle")
        except Exception:
            print "ERROR: Could not generate battle report."
            traceback.print_exc()
                   
    def text_from_battle(self):
        sides = "{w(Attacker){n%s vs {w(Defender){n%s\n" % (self.battle.atk_name, self.battle.def_name)
        victor = self.battle.victor
        if not victor:
            victor = "Neither side could claim decisive victory"
        victor = "\n{wVictor:{n %s\n" % str(victor)
        atkarmy = "\n{wAttacking Units:{n %s\n" % (self.display_units_with_attr(self.battle.atk_units,
                                                                                "starting_quantity"))
        defarmy = "\n{wDefending Units:{n %s\n" % (self.display_units_with_attr(self.battle.def_units,
                                                                                "starting_quantity"))
        atklosses = "\n{wAttacker losses:{n %s\n" % (self.display_units_with_attr(self.battle.atk_units, "losses"))
        deflosses = "\n{wDefender losses:{n %s\n" % (self.display_units_with_attr(self.battle.def_units, "losses"))
        txt = "Battle Report\n" + victor + sides + atkarmy + defarmy + atklosses + deflosses
        return txt

    @staticmethod
    def display_units_with_attr(units, attr):
        display = ["%s: %s" % (unit.name, getattr(unit, attr)) for unit in units]
        return ", ".join(display)


class ExplorationReport(Report):
    def __init__(self, owner, exploration):
        self.explore = exploration
        super(ExplorationReport, self).__init__(owner, self.explore.week, "explore")
        self.generate_explore_report()

    # noinspection PyBroadException
    def generate_explore_report(self):
        try:
            txt = self.text_from_explore()
            self.owner.informs.create(week=self.week, message=txt, category="explore")
        except Exception:
            print "ERROR: Could not generate battle report."
            traceback.print_exc()

    def text_from_explore(self):
        txt = "Exploration Report\n"
        army = "Exploring army: %s\n" % str(self.explore.army)
        outcome = "Outcome: %s\n" % self.explore.outcome
        return txt + army + outcome


class WeeklyReport(Report):
    """
    This report will act as a synopsis of all other reports we've accumulated
    during this weekly cycle.
    """
    def __init__(self, owner, week, inform_creator=None):
        super(WeeklyReport, self).__init__(owner, week, "synopsis", inform_creator)
        self.projects = 0
        self.vault = 0
        self.income_change = 0
        self.owner = owner
        self.failed_payments = []
        self.successful_payments = []
        self.lifestyle_msg = None
        self.owner = owner
        self.week = week
        self.army_reports = []

    def record_income(self, vault, adjust):
        self.vault = vault
        self.income_change = adjust

    def add_project_report(self, project, new_total):
        self.projects += 1
        ProjectReport(self.owner, self.week, project, new_total)

    def add_army_consumption_report(self, army, food, silver):
        s_str = ""
        if silver:
            s_str = " and cost %s silver" % silver
        self.army_reports.append("Army %s ate %s food%s." % (army, food, s_str))

    # noinspection PyBroadException
    def send_report(self):
        """
        Sends our collected reports to the player as an Inform.
        """
        if not any((self.army_reports, self.income_change, self.failed_payments, self.successful_payments)):
            return
        report = self.get_or_create_report(self.category)
        txt = ""
        try:
            txt += "Week %s Reports for %s\n" % (self.week, self.owner)
            txt += "This week's income: %s\n" % self.income_change
            if self.successful_payments:
                txt += "Payments received: %s\n" % ", ".join(self.successful_payments)
            if self.failed_payments:
                txt += "Failed payments to you: %s\n" % ", ".join(self.failed_payments)
            txt += "Bank balance after income: %s\n" % self.vault
            if self.army_reports:
                txt += "Army reports: %s\n" % ", ".join(self.army_reports)
            if self.lifestyle_msg:
                txt += self.lifestyle_msg
            if report.message:
                report.message += "\n" + txt
            else:
                report.message = txt
        except Exception:
            import traceback
            report.message = txt + "\n" + traceback.print_exc()
        if not self.inform_creator:
            report.save()

    def payment_fail(self, payment):
        self.failed_payments.append(str(payment))

    def add_payment(self, payment):
        self.successful_payments.append(str(payment))
