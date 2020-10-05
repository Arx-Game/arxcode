from world.magic.models import Practitioner, SkillNodeResonance
from evennia.utils import logger
from evennia.utils.evtable import EvTable
from server.utils.arx_utils import inform_staff, commafy
from typeclasses.scripts.scripts import Script
from evennia.scripts.models import ScriptDB
from datetime import timedelta
from django.utils import timezone
from typeclasses.scripts.script_mixins import RunDateMixin
from evennia.utils import create


_MAGIC_LOG_ENABLED = False


def round_up(floatvalue):
    try:
        intvalue = int(floatvalue)
    except ValueError:
        return None

    if floatvalue != intvalue:
        return intvalue + 1

    return intvalue


class MagicAdvancementScript(Script, RunDateMixin):

    # noinspection PyMethodMayBeStatic
    def advance_weekly_resonance(self, practitioner):

        mana_base = round_up(practitioner.character.db.mana / 2.0)
        resonance_base = int((practitioner.potential ** (1 / 10.0))) ** 6
        resonance_weekly = (resonance_base * mana_base) / 4.0

        new_resonance = min(
            practitioner.potential, practitioner.unspent_resonance + resonance_weekly
        )
        practitioner.unspent_resonance = new_resonance
        practitioner.save()
        if _MAGIC_LOG_ENABLED:
            logger.log_info(
                "Magic: {} gained {} unspent resonance, now {} of {} max".format(
                    str(practitioner),
                    new_resonance,
                    resonance_weekly,
                    practitioner.potential,
                )
            )

        return {
            "name": str(practitioner),
            "gain": resonance_weekly,
            "resonance": new_resonance,
            "potential": practitioner.potential,
        }

    # noinspection PyMethodMayBeStatic
    def advance_weekly_practice(self, practitioner):

        potential_factor = int(practitioner.potential ** (1 / 10.0))

        max_spend = min(
            practitioner.potential / ((potential_factor ** 2) * 10),
            practitioner.unspent_resonance,
        )
        nodes = practitioner.node_resonances.filter(practicing=True)
        if nodes.count() == 0:
            return None

        noderesults = []
        nodenames = []

        # Get a floating point value of how much resonance to add to each node
        spend_each = max_spend / (nodes.count() * 1.0)
        for node in nodes.all():
            nodenames.append(node.node.name)
            add_node = spend_each
            extra = ""
            teacher = ""
            if node.teaching_multiplier:
                add_node *= node.teaching_multiplier
                teacher = node.taught_by
                extra = "(taught by {} for bonus of {}x)".format(
                    str(node.taught_by), node.teaching_multiplier
                )

            if _MAGIC_LOG_ENABLED:
                logger.log_info(
                    "Magic: {} spent {} resonance on node {} for gain of {} {}".format(
                        str(practitioner), spend_each, node.node.name, add_node, extra
                    )
                )

            node.raw_resonance = node.raw_resonance + add_node

            noderesults.append(
                {
                    "node": node.node.name,
                    "gain": add_node,
                    "resonance": node.raw_resonance,
                    "teacher": teacher,
                }
            )

            node.teaching_multiplier = None
            node.taught_by = None
            node.taught_on = None
            node.save()

        self.inform_creator.add_player_inform(
            player=practitioner.character.dompc.player,
            msg="You practiced {} this week.".format(commafy(nodenames)),
            category="Magic",
        )

        return {"name": str(practitioner), "practices": noderesults}

    # noinspection PyMethodMayBeStatic
    def get_active_practitioners(self):
        return Practitioner.objects.filter(
            character__roster__roster__name__in=["Active", "Available", "Unavailable"]
        )

    def weekly_resonance_update(self):

        results = []

        for practitioner in self.get_active_practitioners().all():
            result = self.advance_weekly_resonance(practitioner)
            if result:
                results.append(result)

        from typeclasses.bulletin_board.bboard import BBoard

        board = BBoard.objects.get(db_key__iexact="staff")
        table = EvTable(
            "{wName{n", "{wGain{n", "{wUnspent{n", "{wMax{n", border="cells", width=78
        )
        for result in results:
            table.add_row(
                result["name"],
                result["gain"],
                "%.2f" % result["resonance"],
                result["potential"],
            )
        board.bb_post(
            poster_obj=self,
            msg=str(table),
            subject="Magic Resonance Gains",
            poster_name="Magic System",
        )
        inform_staff("List of magic resonance gains posted.")

    def weekly_practice_update(self):

        results = []
        for practitioner in self.get_active_practitioners().all():
            result = self.advance_weekly_practice(practitioner)
            if result:
                results.append(result)

        from typeclasses.bulletin_board.bboard import BBoard

        board = BBoard.objects.get(db_key__iexact="staff")
        table = EvTable(border="cells", width=78)
        table.add_column("|wName|n", width=20, valign="t")
        table.add_column("|wPractices|n", valign="t")
        for result in results:
            subtable = EvTable(border=None)
            for node in result["practices"]:
                subtable.add_row(
                    node["node"],
                    "%.2f gain" % node["gain"],
                    "%.2f total" % node["resonance"],
                    node["teacher"],
                )
            table.add_row(result["name"], str(subtable))

        SkillNodeResonance.objects.filter(teaching_multiplier__isnull=False).update(
            teaching_multiplier=None, taught_by=None, taught_on=None
        )

        board.bb_post(
            poster_obj=self,
            msg=str(table),
            subject="Magic Practice Results",
            poster_name="Magic System",
        )
        inform_staff("List of magic practice results posted.")

    def perform_weekly_magic(self):

        self.weekly_resonance_update()
        self.weekly_practice_update()
        self.inform_creator.create_and_send_informs(sender="the magic system")

        # Set our target time for 11:30pm next Sunday
        target_time = timezone.now() + timedelta(days=1)
        target_time += timedelta(days=(13 - target_time.weekday()) % 7)
        target_time.replace(hour=23, minute=30)

        self.attributes.add("run_date", target_time)

    @property
    def inform_creator(self):
        from typeclasses.scripts.weekly_events import BulkInformCreator

        """Returns a bulk inform creator we'll use for gathering informs from the weekly update"""
        if self.ndb.inform_creator is None:
            self.ndb.inform_creator = BulkInformCreator(week=self.db.week)
        return self.ndb.inform_creator

    def at_script_creation(self):
        self.key = "Magic Weekly"
        self.desc = "Triggers weekly magic events"
        self.interval = 3600
        self.persistent = True
        self.start_delay = True

        # Set our target time to be 11:30pm on Sunday.
        target_time = timezone.now()
        target_time += timedelta(days=(13 - target_time.weekday()) % 7)
        target_time.replace(hour=23, minute=30)

        self.attributes.add("run_date", target_time)

    def at_repeat(self):
        if self.check_event():
            self.perform_weekly_magic()


def magic_advancement_script():
    try:
        return ScriptDB.objects.get(db_key="Magic Weekly")
    except ScriptDB.DoesNotExist:
        return None


def init_magic_advancement():
    """
    This is called on startup, when you want to enable the magic system.
    """
    try:
        ScriptDB.objects.get(db_key="Magic Weekly")
    except ScriptDB.DoesNotExist:
        magic_system = create.create_script(MagicAdvancementScript)
        magic_system.start()
