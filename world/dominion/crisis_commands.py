from django.db.models import Q

from evennia.utils.evtable import EvTable

from commands.base import ArxPlayerCommand
from world.dominion.models import Plot, PlotAction, PlotActionAssistant


# noinspection PyUnresolvedReferences
class CrisisCmdMixin(object):
    @property
    def viewable_crises(self):
        qs = Plot.objects.viewable_by_player(self.caller).order_by('end_date')
        return qs

    def list_crises(self):
        qs = self.viewable_crises
        resolved = "old" in self.switches
        qs = qs.filter(usage=Plot.CRISIS, resolved=resolved)
        table = EvTable("{w#{n", "{wName{n", "{wDesc{n", "{wUpdates On{n", width=78, border="cells")
        for ob in qs:
            date = "--" if not ob.end_date else ob.end_date.strftime("%m/%d")
            table.add_row(ob.id, ob.name, ob.headline, date)
        table.reformat_column(0, width=7)
        table.reformat_column(1, width=20)
        table.reformat_column(2, width=40)
        table.reformat_column(3, width=11)
        self.msg(table)

    def get_crisis(self, args):
        try:
            if args.isdigit():
                return self.viewable_crises.get(id=args)
            else:
                return self.viewable_crises.get(name__iexact=args)
        except (Plot.DoesNotExist, ValueError):
            self.msg("Crisis not found by that # or name.")

    def view_crisis(self):
        crisis = self.get_crisis(self.lhs)
        if not crisis:
            return self.list_crises()
        self.msg(crisis.display(display_connected=self.called_by_staff, staff_display=self.called_by_staff))


class CmdGMCrisis(CrisisCmdMixin, ArxPlayerCommand):
    """
    GMs a crisis

    Usage:
        @gmcrisis
        @gmcrisis/old
        @gmcrisis <crisis #>
        @gmcrisis/create <name>/<headline>=<desc>

        @gmcrisis/update <crisis name or #>[/episode name/episode synopsis]
                            =<gemit text>[/<ooc notes>]
        @gmcrisis/update/nogemit <as above>

    Use the @actions command to answer individual actions, or mark then as
    published or pending publish. When making an update, all current actions
    for a crisis that aren't attached to a past update will then be attached to
    the current update, marking them as finished. That then allows players to
    submit new actions for the next round of the crisis, if the crisis is not
    resolved. If a new episode name is specified, a new episode for the current
    chapter will be created with the given name, and any synopsis specified.

    Remember that if a crisis is not public (has a clue to see it), gemits
    probably shouldn't be sent or should be the vague details that people have
    no idea the crisis exists might notice.
    """
    key = "@gmcrisis"
    locks = "cmd:perm(wizards)"
    help_category = "GMing"

    def func(self):
        if not self.args:
            return self.list_crises()
        if "create" in self.switches:
            return self.create_crisis()
        if "update" in self.switches:
            return self.create_update()
        if not self.switches:
            return self.view_crisis()
        self.msg("Invalid switch")

    def create_crisis(self):
        lhs = self.lhs.split("/")
        if len(lhs) < 2:
            self.msg("Bad args.")
            return
        name, headline = lhs[0], lhs[1]
        desc = self.rhs
        Plot.objects.create(name=name, headline=headline, desc=desc)
        self.msg("Crisis created. Make gemits or whatever for it.")

    def create_update(self):
        lhslist = self.lhs.split("/")
        crisis = self.get_crisis(lhslist[0])
        if not crisis:
            return
        episode_name = ""
        episode_synopsis = ""
        try:
            episode_name = lhslist[1]
            episode_synopsis = lhslist[2]
        except IndexError:
            pass
        rhs = self.rhs.split("/")
        gemit = rhs[0]
        gm_notes = None
        if len(rhs) > 1:
            gm_notes = rhs[1]
        crisis.create_update(gemit, self.caller, gm_notes, do_gemit="nogemit" not in self.switches,
                             episode_name=episode_name, episode_synopsis=episode_synopsis)
        episode_text = ""
        if episode_name:
            episode_text = ", creating a new episode called '%s'" % episode_name
        self.msg("You have updated the crisis%s." % episode_text)


class CmdViewCrisis(CrisisCmdMixin, ArxPlayerCommand):
    """
    View the current or past crises

    Usage:
        +crisis [# or name]
        +crisis/old [<# or name>]
        +crisis/viewaction <action #>

    Crisis actions are queued and simultaneously resolved by GMs periodically.
    To view crises that have since been resolved, use /old switch. Each crisis
    that isn't resolved can have a rating assigned that determines the current
    strength of the crisis, and any action taken can adjust that rating by the
    action's outcome value. If you choose to secretly support the crisis, you
    can use the /traitor option for a crisis action, in which case your action's
    outcome value will strengthen the crisis. Togglepublic can keep the action
    from being publically listed. The addition of resources, armies, and extra
    action points is taken into account when deciding outcomes. New actions cost
    50 action points, while assisting costs 10.

    To create a new action, use the @action command.
    """
    key = "crisis"
    locks = "cmd:all()"
    help_category = "Story"

    @property
    def current_actions(self):
        return self.caller.Dominion.actions.exclude(status__in=(PlotAction.PUBLISHED, PlotAction.CANCELLED))

    @property
    def assisted_actions(self):
        return self.caller.Dominion.assisting_actions.all()

    def list_crises(self):
        super(CmdViewCrisis, self).list_crises()
        self.msg("{wYour pending actions:{n")
        table = EvTable("{w#{n", "{wCrisis{n")
        current_actions = [ob for ob in self.current_actions if ob.plot] + [
            ass.plot_action for ass in self.assisted_actions.exclude(
                plot_action__status__in=(PlotAction.PUBLISHED, PlotAction.CANCELLED)) if ass.plot_action.plot]
        for ob in current_actions:
            table.add_row(ob.id, ob.plot)
        self.msg(table)
        past_actions = [ob for ob in self.caller.past_participated_actions if ob.plot]
        if past_actions:
            table = EvTable("{w#{n", "{wCrisis{n")
            self.msg("{wYour past actions:{n")
            for ob in past_actions:
                table.add_row(ob.id, ob.plot)
            self.msg(table)

    def get_action(self, get_all=False, get_assisted=False, return_assistant=False):
        dompc = self.caller.Dominion
        if not get_all and not get_assisted:
            qs = self.current_actions
        else:
            qs = PlotAction.objects.filter(Q(dompc=dompc) | Q(assistants=dompc)).distinct()
        try:
            action = qs.get(id=self.lhs)
            if not action.pk:
                self.msg("That action has been deleted.")
                return
            if return_assistant:
                try:
                    return action.assisting_actions.get(dompc=dompc)
                except PlotActionAssistant.DoesNotExist:
                    self.msg("You are not assisting that crisis action.")
                    return
            return action
        except (PlotAction.DoesNotExist, ValueError):
            self.msg("No action found by that id. Remember to specify the number of the action, not the crisis. " +
                     "Use /assist if trying to change your assistance of an action.")
        return

    def view_action(self):
        action = self.get_action(get_all=True, get_assisted=True)
        if not action:
            return
        msg = action.view_action(self.caller, disp_pending=True, disp_old=True)
        if not msg:
            msg = "You are not able to view that action."
        self.msg(msg)

    def func(self):
        if not self.args and (not self.switches or "old" in self.switches):
            self.list_crises()
            return
        if not self.switches or "old" in self.switches:
            self.view_crisis()
            return
        if "viewaction" in self.switches:
            self.view_action()
            return
        self.msg("Invalid switch")
