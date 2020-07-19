"""
Commands specific to plots. There'll be some overlap with crisis commands due to
them both using the same underlying database model, though for now going to handle
them differently due to a Crisis being public, while plots are private and can
be player-run.
"""
from commands.base import ArxCommand, ArxPlayerCommand
from commands.mixins import RewardRPToolUseMixin
from server.utils.helpdesk_api import create_ticket, add_followup, resolve_ticket
from server.utils.prettytable import PrettyTable
from server.utils.exceptions import CommandError
from server.utils.arx_utils import dict_from_choices_field
from web.character.models import StoryEmit, Flashback, Clue, Revelation, Theory
from web.helpdesk.models import Ticket
from world.dominion.plots.models import PCPlotInvolvement, PlotUpdate, Plot
from world.dominion.models import RPEvent, PlotAction, Organization

from datetime import datetime


def create_plot_pitch(desc, gm_notes, name, parent_plot, summary, player_ob):
    """
    Creates a plot pitch with the given arguments
    Args:
        desc: Text description of the plot
        gm_notes: gm notes for the pitch
        name: name of the plot
        parent_plot: parent plot, if any
        summary: headline of the plot
        player_ob: owner/submitting player for the plot

    Returns:
        The pitch, which is a Ticket object
    """
    plot = Plot.objects.create(name=name, headline=summary, desc=desc, parent_plot=parent_plot,
                               usage=Plot.PITCH, public=False)

    plot.dompc_involvement.create(dompc=player_ob.Dominion, admin_status=PCPlotInvolvement.SUBMITTER)
    title = "Pitch: %s" % plot
    if parent_plot:
        title += " (%s)" % parent_plot
    ticket = create_ticket(player_ob, gm_notes, queue_slug="PRP", optional_title=title, plot=plot)
    return ticket


def get_recruiter_xp(character):
    """XP that a character receives for recruiting someone to a plot. They get less each time, min of 1."""
    dompc = character.dompc
    count = dompc.plot_recruits.count()
    xp = 5 - count
    if xp <= 0:
        xp = 1
    return xp


class CmdPlots(RewardRPToolUseMixin, ArxCommand):
    """
    Running and participating in plots! View Usage:
        plots[/old] [<plot ID>][=<beat ID>]
        plots/timeline <plot ID>
    Plot Usage:
        plots/pitch <name>/<summary>/<desc>/<GM Notes>[=<plot ID if subplot>]
        plots/rfr <ID>[,<beat ID>]=<message to staff of what to review>
        plots/add/clue <plot ID>=<clue ID>/<how it's related to the plot>
        plots/add/revelation <plot ID>=<revelation ID>/<how it's related>
        plots/add/theory <plot ID>=<theory ID>
        plots/tag <plot ID>[,<beat ID>]=<tag topic>
        plots/search <tag topic>
        plots/close <plot ID>
    Beat Usage:
        plots/createbeat <plot ID>=<IC summary>/<ooc notes of consequences>
        plots/add/rpevent <rp event ID>=<beat ID>
        plots/add/action <action ID>=<beat ID>
        plots/add/gemit <gemit ID>=<beat ID>
        plots/add/flashback <flashback ID>=<beat ID>
        plots/editbeat <beat ID>=<IC summary>/<ooc appended note>
    Cast Usage:
        plots/invite [<plot ID>=<character>,<casting option*>]
          *casting options: required, main, supporting, extra
        plots/invitations (alias: plots/outstanding)
        plots/accept [<ID>][=<IC description of character's involvement>]
        plots/leave <ID>
        plots/perm <ID>=<participant>/<gm, recruiter, or player>
        plots/cast <ID>=<participant>/<new casting option>
        plots/storyhook <ID>=<recruiter>/<Example plot hook for meeting>
        plots/findcontact <Secret ID>
        plots/rewardrecruiter <plot ID>=<recruiter>

    The plots command can be used to pitch storyline ideas. Open a ticket
    for GM approval of your plot with /pitch. If approved, you become its
    owner. Pitch requires a name, a one-sentence summary, a longer IC
    description, and OOC notes on what it aims to accomplish. Your pitch can
    reference another plot if you want to run a subplot of something larger.
    Plots can be tagged for easy search by topic. Clues, revelations, and
    theories may be added, with notes to show staff why they're connected.

    Advance a plot with beats: events or actions that progress it. Example,
    after a relevant event, GM uses /createbeat to summarize the plot update.
    Tie the event to this beat with /add/rpevent, then show it to staff with
    /rfr (request for review). Staff will change the world appropriately.

    Set plot permissions with /perm. Owners are administrators. GMs create
    beats; anyone may edit. Recruiters are contacts for newcomers. Casting
    options define how essential someone is: 'Required' cast must be present;
    plot is about them. 'Main' cast is involved in most events. 'Supporting'
    may be present sometimes, and 'Extra' indicates guest appearances.
    GMs should be Supporting cast at most.

    Plots are typically hidden until you are invited, but if your secret is
    a plot hook, the /findcontact switch lists recruiter characters who are
    points of contact for a plot. Their storyhook should give ideas of how
    characters might discover they are involved. Arrange a RP scene with one
    to pursue the plot. If they invite and you accept, /rewardrecruiter
    grants xp to you both. See your invitations with plots/invitations.
    """
    key = "+plots"
    aliases = ["+plot"]
    help_category = "Story"
    admin_switches = ("storyhook", "rfr", "invite", "invitation", "perm", "cast", "tag", "close")
    recruited_xp = 1
    help_entry_tags = ["plots", "goals"]

    @property
    def invitations(self):
        """Invitations for the caller"""
        return self.caller.dompc.plot_involvement.filter(activity_status=PCPlotInvolvement.INVITED)

    @property
    def involvement_queryset(self):
        return (self.caller.dompc.plot_involvement.exclude(activity_status__gte=PCPlotInvolvement.LEFT)
                                                  .exclude(plot__usage=Plot.CRISIS).distinct())

    def func(self):
        """Executes plot command"""
        try:
            if not self.switches or "old" in self.switches or "timeline" in self.switches:
                self.do_plot_displays()
            elif "createbeat" in self.switches:
                self.create_beat()
            elif "editbeat" in self.switches:
                self.edit_beat()
            elif self.check_switches(("add", "addclue", "addrevelation", "addtheory")):
                self.add_object_to_beat()
            elif "search" in self.switches:
                self.view_our_tagged_stuff()
            elif self.check_switches(self.admin_switches):
                self.do_admin_switches()
            elif self.check_switches(("accept", "outstanding", "invitations", "invites")):
                self.accept_invitation()
            elif "leave" in self.switches:
                self.leave_plot()
            elif "pitch" in self.switches:
                self.make_plot_pitch()
            elif "findcontact" in self.switches:
                self.find_contact()
            elif "rewardrecruiter" in self.switches:
                self.reward_recruiter()
            else:
                raise CommandError("Unrecognized switch.")
        except CommandError as err:
            self.msg(err)
        else:
            self.mark_command_used()

    def do_plot_displays(self):
        """Different display methods"""
        if not self.args:
            return self.display_available_plots()
        if not self.rhs:
            return self.view_plot()
        return self.view_beat()

    def display_available_plots(self):
        """Lists all plots available to caller"""
        old = "old" in self.switches
        qs = self.involvement_queryset.filter(plot__resolved=old).distinct()
        table = PrettyTable(["|w{}Plot (ID)|n".format("Resolved " if old else ""), "|wInvolvement|n"])
        for involvement in qs:
            if involvement.activity_status in (involvement.INVITED, involvement.HAS_RP_HOOK):
                color = "|y"
            else:
                color = ""
            name = "{}{} (#{})|n".format(color, involvement.plot, involvement.plot.id)
            status = "{}{}|n".format(color, involvement.get_modified_status_display())
            table.add_row([name, status])
        self.msg(str(table))

    def view_plot(self):
        """Views a given plot"""
        involvement = self.get_involvement_by_plot_id(required_permission=PCPlotInvolvement.PLAYER, allow_old=True)
        if "timeline" in self.switches:
            self.msg(involvement.plot.display_timeline())
        else:
            self.msg(involvement.display_plot_involvement())

    def get_involvement_by_plot_id(self, required_permission=PCPlotInvolvement.OWNER, plot_id=None, allow_old=False):
        """Gets one of caller's plot-involvement object based on plot ID"""
        try:
            if not plot_id:
                plot_id = self.lhslist[0]
            involvement = self.involvement_queryset.get(plot_id=plot_id)
            if involvement.admin_status < required_permission:
                raise CommandError("You lack the required permission for that plot.")
        except (PCPlotInvolvement.DoesNotExist, TypeError, ValueError, IndexError):
            raise CommandError("No plot found by that ID.")
        if involvement.plot.resolved and not allow_old:
            raise CommandError("That plot has been resolved.")
        return involvement

    def view_beat(self):
        """Views a beat for a plot"""
        plot = self.get_involvement_by_plot_id(required_permission=PCPlotInvolvement.PLAYER).plot
        try:
            beat = plot.beats.get(id=self.rhs)
        except (PlotUpdate.DoesNotExist, ValueError):
            raise CommandError("No beat found by that ID.")
        self.msg(beat.display_beat())

    def view_our_tagged_stuff(self):
        """Looks up stuff by tag. Without a tag, gives a list of tags we could try."""
        if not self.args:
            tags = ", ".join(("|235%s|n" % ob) for ob in self.caller.roster.known_tags)
            raise CommandError("Search with a tag like: %s" % tags)
        tag = self.get_tag(self.args)
        msg = self.caller.roster.display_tagged_objects(tag)
        if not msg:
            raise CommandError("Nothing found using the '%s' tag." % self.args)
        self.msg(msg)

    def create_beat(self):
        """Creates a beat for a plot."""
        involvement = self.get_involvement_by_plot_id(required_permission=PCPlotInvolvement.GM)
        desc, ooc_notes = self.split_ic_from_ooc()
        plot = involvement.plot
        beat = plot.updates.create(desc=desc, ooc_notes=ooc_notes, date=datetime.now())
        self.msg("You have created a new beat for %s, ID: %s." % (plot, beat.id))

    def edit_beat(self):
        """Allow cast to edit beat after confirmation."""
        beat = self.get_beat(self.lhs, cast_access=True)
        desc, ooc_notes = self.split_ic_from_ooc(allow_blank_desc=True)
        if not (desc or ooc_notes):
            raise CommandError("Edit the beat with what?")
        if ooc_notes and beat.ooc_notes:  # appends a new ooc note
            ooc_notes = "{0}\n{1}".format(beat.ooc_notes, ooc_notes)
        prompt_msg = ("|w[Proposed Edit to Beat #{}]|n {}\n{}\n|yIf this appears correct, repeat command to "
                      "confirm and continue.|n".format(beat.id, desc or beat.desc, ooc_notes or beat.ooc_notes))
        if self.confirm_command("edit_beat", desc, prompt_msg):
            beat.desc = desc or beat.desc
            beat.ooc_notes = ooc_notes or beat.ooc_notes
            beat.save()
            self.msg("Beat #{} has been updated.".format(beat.id))

    def split_ic_from_ooc(self, allow_blank_desc=False):
        """Splits rhs and returns an IC description and ooc notes."""
        try:
            desc, ooc_notes = self.rhs.split("/")
        except (ValueError, AttributeError):
            raise CommandError("Please use / only to divide IC summary from OOC notes. Usage: <#>=<IC>/<OOC>")
        if not allow_blank_desc and (not desc or len(desc) < 10):
            raise CommandError("Please have a slightly longer IC summary.")
        if ooc_notes:
            ooc_notes = "|wOOC |c{}|w:|n {}".format(self.caller.key, ooc_notes)
        return desc, ooc_notes

    def add_object_to_beat(self):
        """Adds an object that was the origin of a beat for a plot"""
        # clues and revelations aren't part of beats but using /add is a convenience for players
        if self.check_switches(("clue", "addclue")):
            return self.add_clue()
        if self.check_switches(("revelation", "addrevelation")):
            return self.add_revelation()
        if self.check_switches(("theory", "addtheory")):
            return self.add_theory()
        beat = self.get_beat(self.rhs, cast_access=True)
        if "rpevent" in self.switches:
            if self.called_by_staff:
                qs = RPEvent.objects.all()
            else:
                qs = self.caller.dompc.events.all()
            try:
                added_obj = qs.get(id=self.lhs)
            except RPEvent.DoesNotExist:
                raise CommandError("You did not attend an RPEvent with that ID.")
        elif "action" in self.switches:
            if self.called_by_staff:
                qs = PlotAction.objects.all()
            else:
                qs = self.caller.past_participated_actions
            try:
                added_obj = qs.get(id=self.lhs)
            except PlotAction.DoesNotExist:
                raise CommandError("No action by that ID found for you.")
            if added_obj.plot and added_obj.plot != beat.plot:
                raise CommandError("That action is already part of another plot.")
            added_obj.plot = beat.plot
        elif "gemit" in self.switches:
            if not self.called_by_staff:
                raise CommandError("Only staff can add gemits to plot beats.")
            try:
                added_obj = StoryEmit.objects.get(id=self.lhs)
            except StoryEmit.DoesNotExist:
                raise CommandError("No gemit found by that ID.")
        elif "flashback" in self.switches:
            if self.called_by_staff:
                qs = Flashback.objects.all()
            else:
                qs = self.caller.roster.flashbacks.all()
            try:
                added_obj = qs.get(id=self.lhs)
            except Flashback.DoesNotExist:
                raise CommandError("No flashback by that ID.")
        else:
            raise CommandError("You must specify a type of object to add to a beat.")
        if added_obj.beat:
            oldbeat = added_obj.beat
            if oldbeat.desc or oldbeat.gm_notes:
                raise CommandError("It already has been assigned to a plot beat.")
            else:  # It was a temporary placeholder to associate an RPEvent with a plot
                oldbeat.delete()
        added_obj.beat = beat
        added_obj.save()
        self.msg("You have added %s to beat(ID: %d) of %s." % (added_obj, beat.id, beat.plot))

    def get_beat(self, beat_id, cast_access=False):
        """Gets a beat for a plot by its ID"""
        if self.called_by_staff:
            qs = PlotUpdate.objects.all()
        elif cast_access:
            qs = PlotUpdate.objects.filter(plot_id__in=self.caller.dompc.active_plots)
        else:
            qs = PlotUpdate.objects.filter(plot_id__in=self.caller.dompc.plots_we_can_gm)
        try:
            beat = qs.get(id=beat_id)
        except (PlotUpdate.DoesNotExist, ValueError):
            raise CommandError("You are not able to alter a beat of that ID.")
        return beat

    def do_admin_switches(self):
        """Switches for changing a plot"""
        if self.check_switches(("perm", "storyhook", "cast")):
            attr = ""
            story, new_perm, new_cast = None, None, None
            access_level = PCPlotInvolvement.OWNER
            try:
                name, attr = self.rhs.split("/")
            except (AttributeError, ValueError):
                if self.check_switches(("perm", "cast")):
                    raise CommandError("You must specify both a name and %s-level." % self.switches[0])
                else:  # attr being a blank string means story being wiped
                    name = self.rhs or ""
            if "storyhook" in self.switches:
                story = attr
                if name.lower() == self.caller.key.lower():
                    access_level = PCPlotInvolvement.RECRUITER
            else:
                perm = attr.lower()
                if perm == "recruiter":
                    new_perm = PCPlotInvolvement.RECRUITER
                elif perm == "gm":
                    new_perm = PCPlotInvolvement.GM
                elif perm == "player":
                    new_perm = PCPlotInvolvement.PLAYER
                elif perm == "required":
                    new_cast = PCPlotInvolvement.REQUIRED_CAST
                elif perm == "main":
                    new_cast = PCPlotInvolvement.MAIN_CAST
                elif perm == "supporting":
                    new_cast = PCPlotInvolvement.SUPPORTING_CAST
                elif perm == "extra":
                    new_cast = PCPlotInvolvement.EXTRA
                else:
                    err = ("You entered '%s'. Valid permission levels: gm, player, or recruiter. "
                           "Valid cast options: required, main, supporting, or extra." % attr)
                    raise CommandError(err)
            plot = self.get_involvement_by_plot_id(required_permission=access_level).plot
            self.change_permission_or_set_story(plot, name, new_perm, new_cast, story)
        elif self.check_switches(("invite", "invitation")):
            if not self.args:
                return self.msg(self.list_invitations())
            plot = self.get_involvement_by_plot_id(required_permission=PCPlotInvolvement.RECRUITER).plot
            self.invite_to_plot(plot)
        elif self.check_switches(("rfr", "tag", "close")):
            plot = self.get_involvement_by_plot_id(required_permission=PCPlotInvolvement.GM, allow_old=True).plot
            if "rfr" in self.switches:
                self.request_for_review(plot)
            elif "close" in self.switches:
                self.close_plot(plot)
            else:
                self.tag_plot_or_beat(plot)

    def change_permission_or_set_story(self, plot, pc_name, new_perm=None, new_cast=None, story=None):
        """Changes permissions for a plot for a participant or set their recruiter story"""
        involvement = self.get_involvement_by_plot_object(plot, pc_name)
        success = ["You have "]
        gm_err = "GMs are limited to supporting cast; they should not star in stories they're telling."
        if new_perm is not None:
            if involvement.admin_status == PCPlotInvolvement.OWNER:
                raise CommandError("Owners cannot have their admin permission changed.")
            if involvement.cast_status < PCPlotInvolvement.SUPPORTING_CAST and new_perm == PCPlotInvolvement.GM:
                raise CommandError(gm_err)
            involvement.admin_status = new_perm
            success.append("marked %s as a %s." % (involvement.dompc, involvement.get_admin_status_display()))
        elif new_cast is not None:
            if new_cast < PCPlotInvolvement.SUPPORTING_CAST and involvement.admin_status == PCPlotInvolvement.GM:
                raise CommandError(gm_err)
            involvement.cast_status = new_cast
            success.append("added %s to the plot's %s members." % (involvement.dompc,
                                                                   involvement.get_cast_status_display()))
        else:
            if story:
                if involvement.admin_status == PCPlotInvolvement.PLAYER:
                    raise CommandError("They must be set as a recruiter to have a story hook set for how "
                                       "someone wanting to become involved in the plot might have heard of them.")
                success.append("set %s's story hook that contacts can see to: %s" % (involvement, story))
            else:
                if involvement.admin_status == PCPlotInvolvement.RECRUITER:
                    raise CommandError("You cannot remove their hook while they are flagged as a recruiter.")
                success.append("removed %s's story hook." % involvement)
            involvement.recruiter_story = story
        involvement.save()
        self.msg("".join(success))

    def get_involvement_by_plot_object(self, plot: Plot, pc_name: str):
        """
        Gets the involvement object for a given plot
        Args:
            plot: The plot to get the involvement from
            pc_name: The name of the character to get involvement from
        Returns:
            A PCPlotInvolvement object corresponding to the username in self.rhs
        Raises:
            CommandError if no involvement is found
        """
        try:
            involvement = plot.dompc_involvement.get(dompc__player__username__iexact=pc_name)
        except PCPlotInvolvement.DoesNotExist:
            raise self.error_class("No one is involved in your plot by the name '%s'." % pc_name)
        return involvement

    def invite_to_plot(self, plot: Plot):
        """Invites a player to join a plot"""
        try:
            name, status = self.rhslist
        except (TypeError, ValueError):
            raise CommandError("Must provide both a name and a status for invitation.")
        dompc = self.dompc_search(name)
        plot.add_dompc(dompc, status=status.lower(), recruiter=self.caller.key)
        self.msg("You have invited %s to join %s." % (dompc, plot))

    def request_for_review(self, plot: Plot):
        """Makes a request for joining a plot"""
        if not self.rhs:
            return self.display_open_tickets_for_plot(plot)
        beat = None
        if len(self.lhslist) > 1:
            beat = self.get_beat(self.lhslist[1])
        title = "RFR: %s" % plot
        create_ticket(self.caller.player_ob, self.rhs, queue_slug="PRP", optional_title=title, plot=plot, beat=beat)
        self.msg("You have submitted a new ticket for %s." % plot)

    def close_plot(self, plot: Plot):
        """Marks a plot as done"""
        plot.resolved = True
        if not plot.end_date:
            plot.end_date = datetime.now()
        plot.save()
        self.msg(f"{plot} has been marked as finished.")

    def tag_plot_or_beat(self, plot):
        """Tags a plot or beat with specified topic."""
        tag_txt = self.rhs if self.rhs else ""
        tag = self.get_tag(tag_txt)
        beat = None
        if len(self.lhslist) > 1:
            beat = self.get_beat(self.lhslist[1])
        thingy = beat if beat else plot
        thingy.search_tags.add(tag)
        self.msg("Added the '|235%s|n' tag on %s." % (tag, thingy))

    def get_tag(self, tag_text=None):
        """Searches for a tag."""
        from web.character.models import SearchTag
        if not tag_text:
            raise CommandError("What tag are we using?")
        return self.get_by_name_or_id(SearchTag, tag_text)

    def display_open_tickets_for_plot(self, plot):
        """Displays unresolved requests for review for a plot"""
        tickets = plot.tickets.filter(status=Ticket.OPEN_STATUS)
        table = PrettyTable(["ID", "Title"])
        for ticket in tickets:
            table.add_row([ticket.id, ticket.title])
        self.msg("Open tickets for %s:\n%s" % (plot, table))

    def accept_invitation(self):
        """Accepts an invitation to a plot"""
        if not self.lhs or self.check_switches(("outstanding", "invites", "invitations")):
            return self.msg(self.list_invitations())
        try:
            invite = self.invitations.get(plot_id=self.lhs)
        except (PCPlotInvolvement.DoesNotExist, ValueError):
            raise CommandError("No invitation by that ID.\n%s" % self.list_invitations())
        invite.accept_invitation(self.rhs)
        self.msg("You have joined %s (Plot ID: %s)" % (invite.plot, invite.plot.id))

    def list_invitations(self):
        """Returns text of all their invitations to plots"""
        invites = self.invitations
        return "|wOutstanding invitations:|n %s" % ", ".join(str(ob.plot_id) for ob in invites)

    def leave_plot(self):
        """Marks us inactive on a plot or deletes an invitation"""
        involvement = self.get_involvement_by_plot_id(PCPlotInvolvement.PLAYER)
        if involvement.activity_status == PCPlotInvolvement.LEFT:
            raise CommandError("You have already left that plot.")
        involvement.leave_plot()
        self.msg("You have left %s." % involvement.plot)

    def make_plot_pitch(self):
        """Creates a ticket about a plot idea"""
        try:
            name, summary, desc, gm_notes = self.lhs.split("/", 3)
        except ValueError:
            raise CommandError("You must provide a name, a one-line summary, desc, and notes for GMs separated by '/'.")
        parent_plot = None
        if self.rhs:
            parent_plot = self.get_involvement_by_plot_id(PCPlotInvolvement.PLAYER, plot_id=self.rhs).plot
        ticket = create_plot_pitch(desc, gm_notes, name, parent_plot, summary, self.caller.player_ob)
        self.msg("You made a pitch to staff for a new plot. Ticket ID: %s." % ticket.id)

    def find_contact(self):
        """Displays a list of recruiter whom the holder of a plot hook can contact to become involved"""
        try:
            secret = self.caller.messages.get_clue_by_id(self.lhs)
        except (ValueError, KeyError, TypeError):
            raise CommandError("You do not have a secret by that number.")
        msg = "People you can talk to for more plot involvement with your secret:\n"
        for recruiter in secret.clue.recruiters.exclude(plot__in=self.caller.dompc.active_plots).distinct():
            msg += "\n{c%s{n: %s\n" % (str(recruiter), recruiter.recruiter_story)
        self.msg(msg)

    def reward_recruiter(self):
        """Gives credit to the person who recruited us to a plot, giving xp to both"""
        involvement = self.get_involvement_by_plot_id(PCPlotInvolvement.PLAYER)
        if involvement.activity_status != PCPlotInvolvement.ACTIVE:
            raise CommandError("You must have joined the plot to reward your recruiter.")
        if involvement.recruited_by:
            raise CommandError("You have already rewarded a recruiter.")
        targ = self.get_involvement_by_plot_object(involvement.plot, self.rhs)
        if targ == involvement:
            raise CommandError("You cannot reward yourself.")
        xp = get_recruiter_xp(targ)
        involvement.recruited_by = targ.dompc
        involvement.save()
        targ = targ.dompc.player.roster.character
        targ.adjust_xp(xp)
        targ.player_ob.inform("You have been marked as the recruiter of %s for plot %s, and gained %s xp." % (
            involvement, involvement.plot, xp))
        self.caller.adjust_xp(self.recruited_xp)
        self.msg("You have marked %s as your recruiter. You have both gained xp." % targ.key)

    def add_clue(self):
        """Adds a clue to an existing plot"""
        plot = self.get_involvement_by_plot_id(PCPlotInvolvement.PLAYER).plot
        try:
            clue_id, notes = self.rhs.split("/", 1)
        except (AttributeError, ValueError):
            raise CommandError("You must include a clue ID and notes of how the clue is related to the plot.")
        try:
            clue = self.caller.roster.clues.get(id=clue_id)
        except (Clue.DoesNotExist, TypeError, ValueError):
            raise CommandError("No clue by that ID.")
        clue_plot_inv, created = clue.plot_involvement.get_or_create(plot=plot)
        if not created:
            raise CommandError("That clue is already related to that plot.")
        clue_plot_inv.gm_notes = notes
        clue_plot_inv.save()
        self.msg("You have associated clue '%s' with plot '%s'." % (clue, plot))

    def add_revelation(self):
        """Adds a revelation to an existing plot"""
        plot = self.get_involvement_by_plot_id(PCPlotInvolvement.PLAYER).plot
        try:
            rev_id, notes = self.rhs.split("/", 1)
        except (AttributeError, ValueError):
            raise CommandError("You must include a revelation ID and notes of how the clue is related to the plot.")
        try:
            revelation = self.caller.roster.revelations.get(id=rev_id)
        except (Clue.DoesNotExist, TypeError, ValueError):
            raise CommandError("No revelation by that ID.")
        rev_plot_inv, created = revelation.plot_involvement.get_or_create(plot=plot)
        if not created:
            raise CommandError("That revelation is already related to that plot.")
        rev_plot_inv.gm_notes = notes
        rev_plot_inv.save()
        self.msg("You have associated revelation '%s' with plot '%s'." % (revelation, plot))

    def add_theory(self):
        """Adds a theory to an existing plot"""
        plot = self.get_involvement_by_plot_id(PCPlotInvolvement.PLAYER).plot
        try:
            theory = self.caller.player_ob.known_theories.get(id=self.rhs)
        except (Theory.DoesNotExist, TypeError, ValueError):
            raise CommandError("No theory by that ID.")
        plot.theories.add(theory)
        self.msg("You have associated theory '%s' with plot '%s'." % (theory, plot))


class CmdGMPlots(ArxCommand):
    """
    @gmplots [<plot ID>]
    @gmplots/old
    @gmplots/all
    @gmplots/recruiting
    @gmplots/timeline [<plot ID>]
    Admin:
    @gmplots/create <name>/<headline>/<desc>[=<parent plot if subplot>]
    @gmplots/end <ID>[=<gm notes of resolution>]
    @gmplots/addbeat/rpevent <plot ID>=<rp event ID>/<story>/<GM Notes>
            /adb/action <plot ID>=<action ID>/<story>/<GM Notes>
            /adb/flashback <plot ID>=<flashback ID>/<story>/<GM Notes>
            /adb/other <plot ID>=<story>/<GM Notes>
    @gmplots/rfr [<ID>]
    @gmplots/rfr/close <ID>[=<ooc notes to players>]
    @gmplots/pitches [<pitch ID>]
            /pitches/followup <pitch ID>=<message to player>
            /pitches/approve <pitch ID>[=<ooc notes to player>]
            /pitches/decline <pitch ID>[=<ooc notes to player>]
    @gmplots/perm <plot ID>=<player>,<owner, gm, recruiter, player>
    @gmplots/participation <plot ID>=<player>,<casting choice*>
      (*required cast, main cast, supporting cast, extra, tangential)
    Tagging:
    @gmplots/connect/char <plot ID>=<character>/<desc of relationship>
                    /clue <plot ID>=<clue ID>/<desc of relationship>
            /connect supports /revelation, /org same as /clue
    """
    key = "@gmplots"
    help_category = "GMing"
    locks = "cmd: perm(builders)"
    plot_switches = ("end", "addbeat", "adb", "participation", "perm", "connect")
    ticket_switches = ("rfr", "pitches")
    beat_objects = ("rpevent", "flashback", "action")
    view_switches = ("old", "all", "timeline", "recruiting")

    @property
    def pitches(self):
        """Tickets for PRP pitches"""
        return Ticket.objects.filter(queue__slug="PRP", plot__usage=Plot.PITCH, status=Ticket.OPEN_STATUS)

    @property
    def requests_for_review(self):
        """Tickets for RFR"""
        return Ticket.objects.filter(queue__slug="PRP", status=Ticket.OPEN_STATUS, plot__usage=Plot.PLAYER_RUN_PLOT)

    def func(self):
        """Executes gmplots command"""
        try:
            if not self.switches or self.check_switches(self.view_switches):
                return self.view_plots()
            elif "create" in self.switches:
                return self.create_plot()
            elif self.check_switches(self.plot_switches) or self.check_switches(self.beat_objects):
                return self.do_plot_switches()
            elif self.check_switches(self.ticket_switches):
                return self.do_ticket_switches()
            else:
                raise CommandError("Incorrect Switch.")
        except CommandError as err:
            self.msg(err)

    def view_plots(self):
        """Displays existing plots"""
        if not self.args:
            old = "old" in self.switches
            recruiting = "recruiting" in self.switches
            only_open = "all" not in self.switches and not old and not recruiting
            self.msg(str(Plot.objects.view_plots_table(old=old, only_open_tickets=only_open,
                                                       only_recruiting=recruiting)))
        else:
            plot = self.get_by_name_or_id(Plot, self.lhs)
            if "timeline" in self.switches:
                self.msg(plot.display_timeline(staff_display=True))
            else:
                self.msg(plot.display(True, True))

    def create_plot(self):
        """Creates a new plot"""
        parent = None
        try:
            name, summary, desc = self.lhs.split("/")
        except (AttributeError, ValueError):
            raise CommandError("Must include a name, summary, and a description for the plot.")
        if self.rhs:
            parent = self.get_by_name_or_id(Plot, self.rhs)
        plot = Plot.objects.create(name=name, desc=desc, parent_plot=parent, usage=Plot.GM_PLOT,
                                   start_date=datetime.now(), headline=summary)
        if parent:
            self.msg("You have created a new subplot of %s: %s (#%s)." % (parent, plot, plot.id))
        else:
            self.msg("You have created a new gm plot: %s (#%s)." % (plot, plot.id))

    def do_plot_switches(self):
        """Commands for handling a given plot"""
        plot = self.get_by_name_or_id(Plot, self.lhs)
        if "end" in self.switches:
            return self.end_plot(plot)
        if "addbeat" in self.switches or "adb" in self.switches or self.check_switches(self.beat_objects):
            return self.add_beat(plot)
        if "participation" in self.switches:
            return self.set_property_for_dompc(plot, "cast_status", "CAST_STATUS_CHOICES")
        if "perm" in self.switches:
            return self.set_property_for_dompc(plot, "admin_status", "ADMIN_STATUS_CHOICES")
        if "connect" in self.switches:
            return self.connect_to_plot(plot)

    def end_plot(self, plot):
        """Ends a plot"""
        if not self.rhs:
            raise CommandError("You must include a resolution.")
        if plot.resolved:
            raise CommandError("That plot has already been resolved.")
        plot.resolved = True
        plot.end_date = datetime.now()
        plot.save()
        self.msg("You have ended %s." % plot)

    def add_beat(self, plot):
        """Adds a beat to a plot"""
        from web.character.models import Episode
        from django.core.exceptions import ObjectDoesNotExist
        obj = None
        try:
            if self.check_switches(self.beat_objects):
                object_id, story, notes = self.get_beat_objects()
                if "rpevent" in self.switches:
                    obj = RPEvent.objects.get(id=object_id)
                elif "flashback" in self.switches:
                    obj = Flashback.objects.get(id=object_id)
                else:  # action
                    obj = PlotAction.objects.get(id=object_id)
                    if obj.plot and obj.plot != plot:
                        raise CommandError("That action is already assigned to a different plot.")
                    obj.plot = plot
                if obj.beat:
                    raise CommandError("That object was already associated with beat #%s." % obj.beat.id)
            elif "other" in self.switches:
                story, notes = self.get_beat_objects(get_related_id=False)
            else:
                raise CommandError("You must include the switch of the cause:"
                                   " /rpevent, /action, /flashback, or /other.")
        except ObjectDoesNotExist:
            raise CommandError("Did not find an object by that ID.")
        update = plot.updates.create(episode=Episode.objects.last(), desc=story, gm_notes=notes)
        msg = "You have created a new beat for plot %s." % plot
        if obj:
            obj.beat = update
            obj.save()
            msg += " The beat concerns %s(#%s)." % (obj, obj.id)
        self.msg(msg)

    def get_beat_objects(self, get_related_id=True):
        """Gets the items for our beat or raises an error"""
        try:
            if get_related_id:
                obj_id, story, notes = self.rhs.split("/")
                return obj_id, story, notes
            else:
                story, notes = self.rhs.split("/")
                return story, notes
        except (TypeError, ValueError):
            raise CommandError("You must include a story and GM Notes.")

    def set_property_for_dompc(self, plot, field, choices_attr):
        """Sets a property for someone involved in a plot"""
        choices = dict_from_choices_field(PCPlotInvolvement, choices_attr)
        try:
            name, choice = self.rhslist
        except (TypeError, ValueError):
            raise CommandError("You must give both a name and a value.")
        choice = choice.lower()
        try:
            choice_value = choices[choice]
        except KeyError:
            keys = [ob[1].lower() for ob in getattr(PCPlotInvolvement, choices_attr)]
            raise CommandError("Choice must be one of: %s." % ", ".join(keys))
        dompc = self.dompc_search(name)
        involvement, _ = plot.dompc_involvement.get_or_create(dompc=dompc)
        setattr(involvement, field, choice_value)
        involvement.save()
        self.msg("You have set %s as a %s in %s." % (dompc, getattr(involvement, "get_%s_display" % field)(), plot))

    def do_ticket_switches(self):
        """Ticket switches, which often wind up in ditches"""
        queryset = self.pitches if "pitches" in self.switches else self.requests_for_review
        if not self.args:
            return self.display_tickets(queryset)
        try:
            ticket = queryset.get(id=self.lhs)
        except Ticket.DoesNotExist:
            raise CommandError("Ticket not found by that ID.")
        if "rfr" in self.switches:
            return self.handle_requests_for_review(ticket)
        if "pitches" in self.switches:
            return self.handle_pitches(ticket)

    def handle_requests_for_review(self, ticket):
        """Handles review requests"""
        if "close" in self.switches:
            resolve_ticket(self.caller.player_ob, ticket, self.rhs)
            self.msg("You have marked the rfr as closed.")
        else:
            self.view_pitch(ticket)

    def handle_pitches(self, ticket):
        """Handles pitches switches, which might possibly be about witches."""
        if "followup" in self.switches:
            return self.add_followup(ticket)
        elif "approve" in self.switches:
            return self.approve_pitch(ticket)
        elif "decline" in self.switches:
            return self.decline_pitch(ticket)
        else:
            return self.view_pitch(ticket)

    def display_tickets(self, queryset):
        """Displays table of plot pitches"""
        table = PrettyTable(["ID", "Submitter", "Name", "Parent"])
        for pitch in queryset:
            table.add_row([pitch.id, str(pitch.submitting_player), pitch.plot.name, str(pitch.plot.parent_plot)])
        self.msg(str(table))

    def add_followup(self, pitch):
        """Adds followup to a plot pitch"""
        add_followup(self.caller.player_ob, pitch, self.rhs)
        self.msg("You have added a followup to Ticket %s." % pitch.id)

    def approve_pitch(self, pitch):
        """Approves a pitch. Closes the ticket and changes its status and that of the owner"""
        resolve_ticket(self.caller.player_ob, pitch, self.rhs)
        plot = pitch.plot
        plot.usage = Plot.PLAYER_RUN_PLOT
        plot.save()
        for pc in plot.dompc_involvement.filter(admin_status=PCPlotInvolvement.SUBMITTER):
            pc.admin_status = PCPlotInvolvement.OWNER
            pc.save()
        self.msg("You have approved the pitch. %s is now active with %s as the owner." % (pitch.plot,
                                                                                          pitch.submitting_player))

    def decline_pitch(self, pitch):
        """Declines a pitch. Deletes it and closes the ticket"""
        resolve_ticket(self.caller.player_ob, pitch, self.rhs)
        pitch.plot.delete()
        self.msg("You have declined the pitch.")

    def view_pitch(self, pitch):
        """Displays information about a pitch."""
        self.msg(pitch.display())

    def connect_to_plot(self, plot):
        """Connects something to a plot with GM notes about it"""
        try:
            name, gm_notes = self.rhs.split("/")
        except (AttributeError, ValueError):
            raise CommandError("You must include a target and notes on how they're connected to the plot.")
        if "char" in self.switches:
            target = self.dompc_search(name)
            involvement, created = plot.dompc_involvement.get_or_create(dompc=target)
            if created:  # if they're only connected by GM note, they shouldn't know they're connected
                involvement.activity_status = PCPlotInvolvement.NOT_ADDED
                involvement.cast_status = PCPlotInvolvement.TANGENTIAL
        elif "clue" in self.switches:
            target = self.get_by_name_or_id(Clue, name)
            involvement, _ = plot.clue_involvement.get_or_create(clue=target)
        elif "revelation" in self.switches:
            target = self.get_by_name_or_id(Revelation, name)
            involvement, _ = plot.revelation_involvement.get_or_create(revelation=target)
        elif "org" in self.switches:
            target = self.get_by_name_or_id(Organization, name)
            involvement, _ = plot.org_involvement.get_or_create(org=target)
        else:
            raise CommandError("You must include the type of object to connect: char, clue, revelation, org.")
        if involvement.gm_notes:
            involvement.gm_notes += "\n"
        involvement.gm_notes += gm_notes
        involvement.save()
        self.msg("You have connected %s with %s." % (target, plot))


class CmdStoryCoordinators(ArxPlayerCommand):
    """
    Lists story coordinator stuff

    story <story coordinator name>
    story/old <org name>
    story/org <org name>
    """
    key = "story"
    locks = "cmd:perm(builders)"
    help_category = "GMing"

    def func(self):
        try:
            if not self.switches:
                return self.display_coordinator()
            if "old" in self.switches:
                return self.display_resolved_plots_for_org()
            return self.display_current_plots_for_org()
        except self.error_class as err:
            self.msg(err)

    def display_coordinator(self):
        targ = self.search(self.args)
        if not targ:
            return
        orgs = Organization.objects.filter(members__in=targ.active_memberships.filter(story_coordinator=True))
        plots = Plot.objects.filter(resolved=False, orgs__in=orgs).distinct()
        plot_display = "\n".join([plot.display_involvement() for plot in plots])
        self.msg(f"Plots for {targ}:\n{plot_display}")

    def display_resolved_plots_for_org(self):
        plots = self.get_plots_for_org().order_by('start_date')
        plot_display = ", ".join([f"{plot.name_and_id}" for plot in plots])
        self.msg(f"Resolved plots for {self.args}: {plot_display}")

    def display_current_plots_for_org(self):
        plots = self.get_plots_for_org()
        plot_display = "\n".join([plot.display_activity() for plot in plots])
        self.msg(f"Active plots for {self.args}: {plot_display}")

    def get_plots_for_org(self):
        resolved = "old" in self.switches
        org = self.get_by_name_or_id(Organization, self.args)
        return Plot.objects.filter(resolved=resolved, orgs=org)
