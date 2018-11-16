"""
Commands specific to plots. There'll be some overlap with crisis commands due to
them both using the same underlying database model, though for now going to handle
them differently due to a Crisis being public, while plots are private and can
be player-run.
"""
from datetime import datetime

from commands.base import ArxCommand
from server.utils.helpdesk_api import create_ticket, add_followup, resolve_ticket
from server.utils.prettytable import PrettyTable
from server.utils.exceptions import CommandError
from server.utils.arx_utils import dict_from_choices_field
from web.character.models import StoryEmit, Flashback, Clue, Revelation
from web.helpdesk.models import Ticket
from world.dominion.models import PCPlotInvolvement, PlotUpdate, RPEvent, PlotAction, Plot, Organization


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
                               usage=Plot.PITCH)

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


class CmdPlots(ArxCommand):
    """
    Run/Participate in plots

    Usage:
        plots
        plots <ID>[=<beat ID>]
        plots/old
        plots/createbeat <plot ID>=<IC summary>/<ooc notes of consequences>
        plots/add/rpevent <rp event ID>=<beat ID>
        plots/add/action <action ID>=<beat ID>
        plots/add/gemit <gemit ID>=<beat ID>
        plots/add/flashback <flashback ID>=<beat ID>
        plots/storyhook <plot ID>=<recruiter>/<Example plot hook for meeting>
        plots/perm <plot ID>=<participant>/<gm, recruiter, or player>
        plots/rfr <ID>[,<beat ID>]=<message to staff of what to review>
        plots/invite <ID>=<character>,<main, secondary, extra>
        plots/accept <ID>[=<IC description of character's involvement>]
        plots/leave <ID>
        plots/pitch <name>/<summary>/<desc>/<GM Notes>[=<plot ID if subplot>]
        plots/findcontact <secret ID>
        plots/rewardrecruiter <plot ID>=<recruiter>

    Allows for managing and participating in plots in the game. Plots are
    updated with 'beats', which are an event or action that further the
    plot. For example, if you run an event as part of the plot, after the
    event has concluded you would plots/createbeat to provide a summary
    of what occurred, both as an IC story, and an ooc notes of what
    occurred. You then associate that beat with the rpevent by using the
    plots/add/rpevent command. You would then request that staff review
    the beat and make the appropriate game adjustments to record what
    happened in the event with the plots/rfr command, which stands for
    'request for review'.

    Plots are hidden until someone is a participant, but secrets can act
    as hooks for plots and make the /findcontact command available. With
    /findcontact, every plot that a secret acts as a hook for will make
    visible characters who have flagged themselves as points of contact
    for those plots, with IC story hooks for how your character might have
    heard of them. You would then arrange for an IC scene with the character
    if it's a plot you want to pursue, and if you're invited to join and
    accept, you can use the /rewardrecruiter command to give a small xp
    bonus to whoever recruited you as well as yourself.

    The plots command can also be used to pitch ideas for new plots. The
    plots/pitch command will open a ticket for GM approval of your plot.
    If approved, the plot will be created automatically, and you'll be
    set as the plot's owner. You can select an existing plot to pitch a
    subplot off of it, such as if you wanted to make a small subplot for
    a few players off of a large GM plot. A pitch should have the name,
    a one-sentence summary of the plot as a headline/title, a longer IC
    description, and then OOC notes describing what the plot is about,
    or what you'd like to see happen.

    Players may have different levels of participation and access for a
    plot. A plot's owner is the administrator of a plot, while a GM has
    the ability to run events/create beats for it. A recruiter can be set
    as a point of contact for a plot.

    Participants can be flagged based on how essential they are for the plot
    to proceed. 'Required' cast must be present for an event to occur - the
    plot is essentially about them. 'Main' cast would generally be involved
    in most events. 'Supporting' cast or lower may only be present sometimes,
    while lower might indicate someone only appearing once or twice in a few
    events. GMs must be supporting cast or lower - they cannot be central
    characters in the story.
    """
    key = "+plots"
    aliases = ["+plot"]
    help_category = "Story"
    admin_switches = ("storyhook", "rfr", "invite", "perm")
    recruited_xp = 1

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
            if not self.switches or "old" in self.switches:
                return self.do_plot_displays()
            if "createbeat" in self.switches:
                return self.create_beat()
            if "add" in self.switches:
                return self.add_object_to_beat()
            if self.check_switches(self.admin_switches):
                return self.do_admin_switches()
            if "accept" in self.switches:
                return self.accept_invitation()
            if "leave" in self.switches:
                return self.leave_plot()
            if "pitch" in self.switches:
                return self.make_plot_pitch()
            if "findcontact" in self.switches:
                return self.find_contact()
            if "rewardrecruiter" in self.switches:
                return self.reward_recruiter()
            raise CommandError("Unrecognized switch.")
        except CommandError as err:
            self.msg(err)

    def do_plot_displays(self):
        """Different display methods"""
        if not self.args:
            return self.display_available_plots()
        if not self.rhs:
            return self.view_plot()
        return self.view_beat()

    def display_available_plots(self):
        """Lists all plots available to caller"""
        qs = self.involvement_queryset.filter(plot__resolved="old" in self.switches).distinct()
        msg = "Plot Involvement:\n"
        table = PrettyTable(["Name/ID", "Involvement"])
        for involvement in qs:
            name = "%s (#%s)" % (involvement.plot, involvement.plot.id)
            status = involvement.get_modified_status_display()
            table.add_row([name, status])
        msg += str(table)
        self.msg(msg)

    def view_plot(self):
        """Views a given plot"""
        involvement = self.get_involvement_by_plot_id(required_permission=PCPlotInvolvement.PLAYER, allow_old=True)
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

    def create_beat(self):
        """Creates a beat for a plot."""
        involvement = self.get_involvement_by_plot_id(required_permission=PCPlotInvolvement.GM)
        ooc_notes = ""
        try:
            rhs = self.rhs.split("/")
            if len(rhs) == 2:
                ooc_notes = rhs[1]
            desc = rhs[0]
        except (AttributeError, IndexError):
            raise CommandError("You must specify an IC summary of what occurred.")
        if len(desc) < 10:
            raise CommandError("Please have a slightly longer IC summary.")
        plot = involvement.plot
        beat = plot.updates.create(desc=desc, gm_notes=ooc_notes, date=datetime.now())
        self.msg("You have created a new beat for %s, ID: %s." % (plot, beat.id))

    def add_object_to_beat(self):
        """Adds an object that was the origin of a beat for a plot"""
        beat = self.get_beat(self.rhs)
        if "rpevent" in self.switches:
            if self.called_by_staff:
                qs = RPEvent.objects.all()
            else:
                qs = self.caller.dompc.events.filter(pc_event_participation__gm=True)
            try:
                added_obj = qs.get(id=self.lhs)
            except RPEvent.DoesNotExist:
                raise CommandError("You are not a GM for an RPEvent with that ID.")
        elif "action" in self.switches:
            if self.called_by_staff:
                qs = PlotAction.objects.all()
            else:
                qs = self.caller.dompc.actions.all()
            try:
                added_obj = qs.get(id=self.lhs)
            except PlotAction.DoesNotExist:
                raise CommandError("No action by that ID found for you.")
        elif "gemit" in self.switches:
            if not self.called_by_staff:
                raise CommandError("Only staff can add gemits to plot beats.")
            try:
                added_obj = StoryEmit.objects.get(id=self.lhs)
            except StoryEmit.DoesNotExist:
                raise CommandError("No gemit found by that ID.")
        elif "flashback" in self.switches:
            if not self.called_by_staff:
                qs = Flashback.objects.all()
            else:
                qs = self.caller.roster.created_flashbacks.all()
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

    def get_beat(self, beat_id):
        """Gets a beat for a plot by its ID"""
        if self.called_by_staff:
            qs = PlotUpdate.objects.all()
        else:
            qs = PlotUpdate.objects.filter(plot_id__in=self.caller.dompc.plots_we_can_gm)
        try:
            beat = qs.get(id=beat_id)
        except (PlotUpdate.DoesNotExist, ValueError):
            raise CommandError("You are not a GM for the plot that has a beat of that ID.")
        return beat

    def do_admin_switches(self):
        """Switches for changing a plot"""
        if "perm" in self.switches or "storyhook" in self.switches:
            attr = ""
            access_level = PCPlotInvolvement.OWNER
            try:
                name, attr = self.rhs.split("/")
            except (TypeError, ValueError):
                if "perm" in self.switches:
                    raise CommandError("You must specify both a name and a permission level.")
                else:  # attr being a blank string means it's being wiped
                    name = self.rhs
            if "storyhook" in self.switches:
                story = attr
                perm_status = None
                if name.lower() == self.caller.key.lower():
                    access_level = PCPlotInvolvement.RECRUITER
            else:
                story = None
                perm = attr.lower()
                if perm == "recruiter":
                    perm_status = PCPlotInvolvement.RECRUITER
                elif perm == "gm":
                    perm_status = PCPlotInvolvement.GM
                elif perm == "player":
                    perm_status = PCPlotInvolvement.PLAYER
                else:
                    raise CommandError("Permission must be 'gm', 'player', or 'recruiter'.")
            plot = self.get_involvement_by_plot_id(required_permission=access_level).plot
            self.change_permission_or_set_story(plot, name, perm_status, story)
        elif "invite" in self.switches:
            plot = self.get_involvement_by_plot_id(required_permission=PCPlotInvolvement.RECRUITER).plot
            self.invite_to_plot(plot)
        elif "rfr" in self.switches:
            plot = self.get_involvement_by_plot_id(required_permission=PCPlotInvolvement.GM).plot
            self.request_for_review(plot)

    def change_permission_or_set_story(self, plot, pc_name, perm_level=None, story=None):
        """Changes permissions for a plot for a participant or set their recruiter story"""
        involvement = self.get_involvement_by_plot_object(plot, pc_name)
        if perm_level is not None:
            if involvement.admin_status == PCPlotInvolvement.OWNER:
                raise CommandError("Owners cannot have their status changed.")
            if involvement.cast_status < PCPlotInvolvement.SUPPORTING_CAST and perm_level >= PCPlotInvolvement.GM:
                raise CommandError("GMs are limited to supporting cast or less.")
            involvement.admin_status = perm_level
            msg = "You have marked %s as a %s." % (involvement.dompc, involvement.get_admin_status_display())
        else:
            if story:
                if involvement.admin_status == PCPlotInvolvement.PLAYER:
                    raise CommandError("They must be set as a recruiter to have a story hook set for how "
                                       "someone wanting to become involved in the plot might have heard of them.")
                msg = "You have set %s's story hook that contacts can see to: %s" % (involvement, story)
            else:
                if involvement.admin_status == PCPlotInvolvement.RECRUITER:
                    raise CommandError("You cannot remove their hook while they are flagged as a recruiter.")
                msg = "You have removed %s's story hook." % involvement
            involvement.recruiter_story = story
        involvement.save()
        self.msg(msg)

    def get_involvement_by_plot_object(self, plot, pc_name):
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

    def invite_to_plot(self, plot):
        """Invites a player to join a plot"""
        try:
            name, status = self.rhslist
        except (TypeError, ValueError):
            raise CommandError("Must provide both a name and a status for invitation.")
        dompc = self.dompc_search(name)
        plot.add_dompc(dompc, status)
        self.msg("You have invited %s to join %s." % (dompc, plot))

    def request_for_review(self, plot):
        """Makes a request for joining a plot"""
        if not self.rhs:
            return self.display_open_tickets_for_plot(plot)
        beat = None
        if len(self.lhslist) > 1:
            beat = self.get_beat(self.lhslist[1])
        title = "RFR: %s" % plot
        create_ticket(self.caller.player_ob, self.rhs, queue_slug="PRP", optional_title=title, plot=plot, beat=beat)
        self.msg("You have submitted a new ticket for %s." % plot)

    def display_open_tickets_for_plot(self, plot):
        """Displays unresolved requests for review for a plot"""
        tickets = plot.tickets.filter(status=Ticket.OPEN_STATUS)
        table = PrettyTable(["ID", "Title"])
        for ticket in tickets:
            table.add_row([ticket.id, ticket.title])
        self.msg("Open tickets for %s:\n%s" % (plot, table))

    def accept_invitation(self):
        """Accepts an invitation to a plot"""
        if not self.lhs:
            return self.msg(self.list_invitations())
        try:
            invite = self.invitations.get(plot_id=self.lhs)
        except PCPlotInvolvement.DoesNotExist:
            raise CommandError("No invitation by that ID.\n%s" % self.list_invitations())
        invite.accept_invitation(self.rhs)
        self.msg("You have joined %s (Plot ID: %s)" % (invite.plot, invite.plot.id))

    def list_invitations(self):
        """Returns text of all their invitations to plots"""
        invites = self.invitations
        return "Outstanding invitations: %s" % ", ".join(str(ob.plot_id) for ob in invites)

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
        targ.player.inform("You have been marked as the recruiter of %s for plot %s, and gained %s xp." % (
            involvement, involvement.plot, xp))
        self.caller.adjust_xp(self.recruited_xp)
        self.msg("You have marked %s as your recruiter. You have both gained xp." % targ.key)


class CmdGMPlots(ArxCommand):
    """
    @gmplots [<plot ID>]
    @gmplots/old
    Admin:
    @gmplots/create <name>/<headline>/<description>[=<parent plot if subplot>]
    @gmplots/end <ID>[=<gm notes of resolution>]
    @gmplots/addbeat/rpevent <plot ID>=<rp event ID>/<story>/<GM Notes>
            /action <plot ID>=<action ID>/<story>/<GM Notes>
            /flashback <plot ID>=<flashback ID>/<story>/<GM Notes>
            /other <plot ID>=<story>/<GM Notes>
    @gmplots/rfr [<ID>]
    @gmplots/rfr/close <ID>[=<ooc notes to players>]
    @gmplots/pitches [<pitch ID>]
    @gmplots/pitches/followup <pitch ID>=<message to player>
    @gmplots/pitches/approve <pitch ID>[=<ooc notes to player>]
    @gmplots/pitches/decline <pitch ID>[=<ooc notes to player>]
    @gmplots/participation <plot ID>=<player>,<participation level>
    @gmplots/perm <plot ID>=<player>/<owner, gm, recruiter, player>

    Tagging:
    @gmplots/connect/char <plot ID>=<character>/<desc of relationship>
                    /clue <plot ID>=<clue ID>/<desc of relationship>
    /connect also supports /revelation, /org

    """
    key = "@gmplots"
    help_category = "GMing"
    locks = "cmd: perm(builders)"
    plot_switches = ("end", "addbeat", "participation", "perm", "connect")
    ticket_switches = ("rfr", "pitches")
    beat_objects = ("rpevent", "flashback", "action")

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
            if "old" in self.switches or not self.switches:
                return self.view_plots()
            if "create" in self.switches:
                return self.create_plot()
            if self.check_switches(self.plot_switches):
                return self.do_plot_switches()
            if self.check_switches(self.ticket_switches):
                return self.do_ticket_switches()
        except CommandError as err:
            self.msg(err)

    def view_plots(self):
        """Displays existing plots"""
        if not self.args:
            old = "old" in self.switches
            self.msg(str(Plot.objects.view_plots_table(old=old)))
        else:
            try:
                plot = Plot.objects.get(id=self.lhs)
            except Plot.DoesNotExist:
                raise CommandError("No plot found by that ID.")
            self.msg(plot.display())

    def create_plot(self):
        """Creates a new plot"""
        parent = None
        try:
            name, summary, desc = self.lhs.split("/")
        except (TypeError, ValueError):
            raise CommandError("Must include a name, summary, and a description for the plot.")
        if self.rhs:
            parent = self.get_plot(self.rhs)
        plot = Plot.objects.create(name=name, desc=desc, parent_plot=parent, usage=Plot.GM_PLOT,
                                   start_date=datetime.now(), headline=summary)
        if parent:
            self.msg("You have created a new subplot of %s: %s." % (parent, plot))
        else:
            self.msg("You have created a new gm plot: %s." % plot)

    def get_plot(self, args=None):
        if args is None:
            args = self.lhs
        try:
            if args.isdigit():
                parent = Plot.objects.get(id=args)
            else:
                parent = Plot.objects.get(name__iexact=args)
        except (TypeError, ValueError, Plot.DoesNotExist):
            raise CommandError("Invalid plot ID or name: %s" % args)
        return parent

    def do_plot_switches(self):
        """Commands for handling a given plot"""
        plot = self.get_plot()
        if "end" in self.switches:
            return self.end_plot(plot)
        if "addbeat" in self.switches:
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
            name, choice = self.rhs.split("/")
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
        except (TypeError, ValueError):
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
