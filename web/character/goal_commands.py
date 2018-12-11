"""
Commands for goals
"""
from evennia.utils.evtable import EvTable

from commands.base import ArxCommand
from commands.mixins import CommandError
from .models import Goal, GoalUpdate
from server.utils.helpdesk_api import create_ticket, resolve_ticket
from web.helpdesk.models import Ticket
from world.dominion.models import Plot, PlotUpdate


class CmdGoals(ArxCommand):
    """
    View or set goals for your character

    Usage:
        goals[/old]
        goals [<goal id>
        goals/create <summary>/<description>
        goals/summary <goal id>=<new summary>
             /description <goal id>=<new description>
             /scope <goal id>=<scope>
             /plot  <goal id>=<plot ID, if any>
             /status <goal id>=<status>
             /ooc_notes <goal id>=<notes>
        goals/rfr <goal id>[,<beat id>]=<IC summary>/<request to staff>

        Valid scopes: 'Heartbreakingly Modest', 'Modest', 'Reasonable',
            'Ambitious', 'Venomously Ambitious', 'Megalomanic'.
        Valid statuses: 'Succeeded', 'Failed', 'Abandoned', 'Dormant',
            'Active'.

    The goals command is for creating and tracking the goals of your
    character, and then for asking for staff updates where appropriate
    based on scenes that have occurred. Creating a goal for your character
    does not require staff approval - just decide what your character wants,
    how grand (or mild) their ambitions are, then hook it up to whatever
    current plot is appropriate for advancing it. For example, if your
    character desperately wants to learn magic, you would set that as a goal,
    and if a plot seems likely to lead to that you would set that plot as how
    you're pursuing your goal. Then if during a plot beat (an action, event,
    or flashback) or a scene something happened that would advance your
    character's goal, you would submit a goals/rfr to ask for staff ruling on
    any game results. You may submit an rfr once every 30 days.
    """
    key = "goals"
    aliases = ["goal"]
    field_switches = ("summary", "description", "scope", "status", "ooc_notes", "plot")

    @property
    def goals(self):
        """Goals queryset for our caller"""
        return self.caller.roster.goals

    def func(self):
        """Executes goals cmd"""
        try:
            if not self.args:
                return self.list_goals()
            if "create" in self.switches:
                return self.create_goal()
            try:
                goal = self.goals.get(id=self.lhslist[0])
            except (Goal.DoesNotExist, ValueError, IndexError):
                raise CommandError("You do not have a goal by that number.")
            if not self.switches:
                return self.msg(goal.display())
            if self.check_switches(self.field_switches):
                return self.update_goal_field(goal)
            if "rfr" in self.switches:
                return self.request_review(goal)
            raise CommandError("Invalid switch.")
        except CommandError as err:
            self.msg(err)

    def list_goals(self):
        """Displays our goals for our caller"""
        if "old" in self.switches:
            qs = self.goals.exclude(status=Goal.ACTIVE)
        else:
            qs = self.goals.filter(status=Goal.ACTIVE)
        table = EvTable("{wID{n", "{wSummary{n", "{wPlot{n")
        for ob in qs:
            table.add_row(ob.id, ob.summary, ob.plot)
        self.msg(str(table))

    def create_goal(self):
        try:
            summary, desc = self.args.split("/", 1)
            if not desc:
                raise ValueError
        except ValueError:
            raise CommandError('You must provide a summary and a description of your goal.')
        goal = self.goals.create(summary=summary, description=desc)
        self.msg('You have created a new goal: ID #%s.' % goal.id)

    def update_goal_field(self, goal):
        """Updates a field for a goal"""
        args = self.rhs or ""
        target_name = self.rhs
        field = list(set(self.switches) & set(self.field_switches))[0]
        old = getattr(goal, field)
        if field == "status":
            args = self.get_value_for_choice_field_string(Goal.STATUS_CHOICES, args)
            old = goal.get_status_display()
        elif field == "scope":
            args = self.get_value_for_choice_field_string(Goal.SCOPE_CHOICES, args)
            old = goal.get_scope_display()
        elif field == "plot":
            try:
                args = self.caller.dompc.plots.get(id=args)
                target_name = args
            except (Plot.DoesNotExist, ValueError):
                raise CommandError("No plot by that ID.")
        setattr(goal, field, args)
        goal.save()
        msg = "Old value was: %s\n" % old
        msg += "%s set to: %s" % (field.capitalize(), target_name)
        self.msg(msg)

    def request_review(self, goal):
        """Submits a ticket asking for a review of progress toward their goal"""
        from datetime import datetime, timedelta
        past_thirty_days = datetime.now() - timedelta(days=30)
        recent = GoalUpdate.objects.filter(goal__in=self.goals.all(), db_date_created__gt=past_thirty_days).first()
        beat = None
        if recent:
            raise CommandError("You submitted a request for review for goal %s too recently." % recent.goal.id)
        try:
            summary, ooc_message = self.rhs.split("/")
        except (AttributeError, ValueError):
            raise CommandError("You must provide both a short story summary of what your character did or attempted to "
                               "do in order to make progress toward their goal, and an OOC message to staff, telling "
                               "them of your intent for results you would like and anything else that seems "
                               "relevant.")
        if len(self.lhslist) > 1:
            try:
                beat = PlotUpdate.objects.filter(plot__in=self.caller.dompc.plots.all()).get(id=self.lhslist[1])
            except (PlotUpdate.DoesNotExist, ValueError):
                raise CommandError("No beat by that ID.")
        update = goal.updates.create(beat=beat, player_summary=summary)
        ticket = create_ticket(self.caller.player_ob, self.rhs, plot=goal.plot, beat=beat, goal_update=update,
                               queue_slug="Goals")
        self.msg("You have sent in a request for review for goal %s. Ticket ID is %s." % (goal.id, ticket.id))


class CmdGMGoals(ArxCommand):
    """
    Administrates goals for characters

    Usage:
        gmgoals
        gmgoals <#>
        gmgoals/close <#>=<result>

    Lists open tickets for people wanting results written for progress toward
    their goals. gmgoals/close allows you to close a ticket and write the
    result they get for the GoalUpdate.
    """
    key = "gmgoals"
    aliases = ["gmgoal"]
    locks = "cmd:perm(builders)"

    @property
    def tickets(self):
        return Ticket.objects.filter(queue__slug="Goals", status=Ticket.OPEN_STATUS)

    def func(self):
        """Executes GMgoals command"""
        try:
            if not self.args:
                return self.list_tickets()
            try:
                ticket = self.tickets.get(id=self.lhs)
            except Ticket.DoesNotExist:
                raise CommandError("No ticket found by that ID.")
            if not self.switches:
                return self.msg(ticket.display())
            if "close" in self.switches:
                return self.close_ticket(ticket)
        except CommandError as err:
            self.msg(err)

    def list_tickets(self):
        """List tickets for goalupdates"""
        table = EvTable("{wID{n", "{wPlayer{n", "{wGoal{n")
        for ticket in self.tickets:
            table.add_row(ticket.id, str(ticket.submitting_player), ticket.goal_update.goal.summary)
        self.msg(str(table))

    def close_ticket(self, ticket):
        """Closes a ticket"""
        if not self.rhs:
            raise CommandError("You must provide a result.")
        update = ticket.goal_update
        if update.result:
            raise CommandError("Update already has a result written. Close the ticket with @job.")
        update.result = self.rhs
        update.save()
        resolve_ticket(self.caller.player_ob, ticket, "Result: %s" % self.rhs)
        self.msg("You have closed the ticket and set the result to: %s" % self.rhs)
