from evennia.utils.idmapper.models import SharedMemoryModel
from django.db import models
from django.db.models import Q
from world.dominion.managers import CrisisManager
from server.utils.arx_utils import inform_staff, passthrough_properties, get_week
from web.character.models import AbstractPlayerAllocations
from server.utils.exceptions import ActionSubmissionError
from django.conf import settings
from world.dominion.domain.models import Army, Orders

from datetime import datetime


class Plot(SharedMemoryModel):
    """
    A plot being run in the game. This can either be a crisis affecting organizations or the entire gameworld,
    a gm plot for some subset of players, a player-run plot for players, or a subplot of any of the above. In
    general, a crisis is a type of plot that allows offscreen actions to be submitted and is resolved at regular
    intervals: This is more or less intended for large-scale events. GM Plots and Player Run Plots will tend to
    be focused on smaller groups of players.
    """
    CRISIS, GM_PLOT, PLAYER_RUN_PLOT, PITCH = range(4)
    USAGE_CHOICES = ((CRISIS, "Crisis"), (GM_PLOT, "GM Plot"), (PLAYER_RUN_PLOT, "Player-Run Plot"),
                     (PITCH, "Pitch"))
    name = models.CharField(blank=True, null=True, max_length=255, db_index=True)
    usage = models.SmallIntegerField(choices=USAGE_CHOICES, default=CRISIS)
    headline = models.CharField("News-style bulletin", max_length=255, blank=True, null=True)
    desc = models.TextField(blank=True, null=True)
    orgs = models.ManyToManyField('Organization', related_name='plots', blank=True, through="OrgPlotInvolvement")
    dompcs = models.ManyToManyField('PlayerOrNpc', blank=True, related_name='plots', through="PCPlotInvolvement",
                                    through_fields=("plot", "dompc"))
    parent_plot = models.ForeignKey('self', related_name="subplots", blank=True, null=True, on_delete=models.SET_NULL)
    escalation_points = models.SmallIntegerField(default=0, blank=0)
    results = models.TextField(blank=True, null=True)
    modifiers = models.TextField(blank=True, null=True)
    public = models.BooleanField(default=True, blank=True)
    required_clue = models.ForeignKey('character.Clue', related_name="crises", blank=True, null=True,
                                      on_delete=models.SET_NULL)
    resolved = models.BooleanField(default=False)
    start_date = models.DateTimeField(blank=True, null=True)
    end_date = models.DateTimeField(blank=True, null=True)
    chapter = models.ForeignKey('character.Chapter', related_name="crises", blank=True, null=True,
                                on_delete=models.SET_NULL)
    search_tags = models.ManyToManyField("character.SearchTag", blank=True, related_name="plots")
    objects = CrisisManager()

    class Meta:
        """Define Django meta options"""
        verbose_name_plural = "Plots"

    def __str__(self):
        return self.name

    @property
    def time_remaining(self):
        """Returns timedelta of how much time is left before the crisis updates"""
        now = datetime.now()
        if self.end_date and self.end_date > now:
            return self.end_date - now

    @property
    def rating(self):
        """Returns how much rating is left in our crisis"""
        if self.escalation_points:
            return self.escalation_points - sum(ob.outcome_value for ob in self.actions.filter(
                status=PlotAction.PUBLISHED))

    @property
    def beats(self):
        """Returns updates that have descs written, meaning they aren't pending/future events."""
        return self.updates.exclude(desc="")

    def display_base(self):
        """Common plot display information"""
        msg = "|w[%s|w]{n" % self
        if self.rating:
            msg += " |w(%s Rating)|n" % self.rating
        if self.time_remaining:
            msg += " {yTime Remaining:{n %s" % str(self.time_remaining).split(".")[0]
        tags = self.search_tags.all()
        if tags:
            msg += " |wTags:|n %s" % ", ".join(("|235%s|n" % tag) for tag in tags)
        msg += "\n%s" % self.desc
        return msg

    def display(self, display_connected=True, staff_display=False):
        """Returns string display for the plot and its latest update/beat"""
        msg = [self.display_base()]
        beats = list(self.beats)
        if display_connected:
            orgs, clue, cast = self.orgs.all(), self.required_clue, self.cast_list
            if clue:
                msg.append("|wRequired Clue:|n {}".format(self.required_clue))
            if staff_display:
                subplots, clues, revs = self.subplots.all(), self.clues.all(), self.revelations.all()
                if self.parent_plot:
                    msg.append("|wMain Plot:|n {} (#{})".format(self.parent_plot, self.parent_plot.id))
                if subplots:
                    msg.append("|wSubplots:|n {}".format(", ".join(("%s (#%s)" % (ob, ob.id)) for ob in subplots)))
                if clues:
                    msg.append("|wClues:|n {}".format("; ".join(("%s (#%s)" % (ob, ob.id)) for ob in clues)))
                if revs:
                    msg.append("|wRevelations:|n {}".format("; ".join(("%s (#%s)" % (ob, ob.id)) for ob in revs)))
            if cast:
                msg.append(cast)
            if orgs:
                msg.append("|wInvolved Organizations:|n {}".format(", ".join(str(ob) for ob in orgs)))
        if beats:
            last = beats[-1]
            if self.usage in (self.PLAYER_RUN_PLOT, self.GM_PLOT):
                msg.append("|wBeat IDs:|n {}".format(", ".join(str(ob.id) for ob in beats)))
            msg.append(last.display_beat(display_connected=display_connected, staff_display=staff_display))
        return "\n".join(msg)

    def display_timeline(self, staff_display=False):
        """Base plot description plus all beats/updates displays"""
        beats = list(self.beats)
        msg = "{}\n{}".format(self.display_base(),
                              "\n".join([ob.display_beat(staff_display=staff_display) for ob in beats]))
        return msg

    def check_taken_action(self, dompc):
        """Whether player has submitted action for the current crisis update."""
        return self.actions.filter(Q(dompc=dompc) & Q(beat__isnull=True)
                                   & ~Q(status__in=(PlotAction.DRAFT, PlotAction.CANCELLED))).exists()

    def raise_submission_errors(self):
        """Raises errors if it's not valid to submit an action for this crisis"""
        if self.resolved:
            raise ActionSubmissionError("%s has been marked as resolved." % self)
        if self.end_date and datetime.now() > self.end_date:
            raise ActionSubmissionError("It is past the deadline for %s." % self)

    def raise_creation_errors(self, dompc):
        """Raise errors if dompc shouldn't be allowed to submit an action for this crisis"""
        self.raise_submission_errors()
        if self.check_taken_action(dompc=dompc):
            raise ActionSubmissionError("You have already submitted an action for this stage of the crisis.")

    def create_update(self, gemit_text, caller=None, gm_notes=None, do_gemit=True,
                      episode_name=None, episode_synopsis=None):
        """
        Creates an update for the crisis. An update functions as saying the current round/turn of actions is
        over, and announces to the game a synopsis of what occurred. After the update, if the crisis is not
        resolved, players would be free to put in another action.
        Args:
            gemit_text: Summary of what happened in this update
            caller: The GM who published this
            gm_notes: Notes to other GMs about what happened
            do_gemit: Whether to announce this to the whole game
            episode_name: The name of the episode this happened during
            episode_synopsis: Summary of an episode if we're creating one
        """
        from server.utils.arx_utils import broadcast_msg_and_post
        gm_notes = gm_notes or ""
        from web.character.models import Episode, Chapter
        if not episode_name:
            latest_episode = Episode.objects.last()
        else:
            latest_episode = Chapter.objects.last().episodes.create(name=episode_name, synopsis=episode_synopsis)
        update = self.updates.create(date=datetime.now(), desc=gemit_text, gm_notes=gm_notes, episode=latest_episode)
        qs = self.actions.filter(status__in=(PlotAction.PUBLISHED, PlotAction.PENDING_PUBLISH,
                                             PlotAction.CANCELLED), beat__isnull=True)
        pending = []
        already_published = []
        for action in qs:
            if action.status == PlotAction.PENDING_PUBLISH:
                action.send(update=update, caller=caller)
                pending.append(str(action.id))
            else:
                action.update = update
                action.save()
                already_published.append(str(action.id))
        if do_gemit:
            broadcast_msg_and_post(gemit_text, caller, episode_name=latest_episode.name)
        pending = "Pending actions published: %s" % ", ".join(pending)
        already_published = "Already published actions for this update: %s" % ", ".join(already_published)
        post = "Gemit:\n%s\nGM Notes: %s\n%s\n%s" % (gemit_text, gm_notes, pending, already_published)
        subject = "Update for %s" % self
        inform_staff("Crisis update posted by %s for %s:\n%s" % (caller, self, post), post=True, subject=subject)

    def check_can_view(self, user):
        """Checks if user can view this plot"""
        if self.public:
            return True
        if not user or not user.is_authenticated():
            return False
        if user.is_staff or user.check_permstring("builders"):
            return True
        return self.required_clue in user.roster.clues.all()

    @property
    def finished_actions(self):
        """Returns queryset of all published actions"""
        return self.actions.filter(status=PlotAction.PUBLISHED)

    def get_viewable_actions(self, user):
        """Returns actions that the user can view - published actions they participated in, or all if they're staff."""
        if not user or not user.is_authenticated():
            return self.finished_actions.filter(public=True)
        if user.is_staff or user.check_permstring("builders"):
            return self.finished_actions
        dompc = user.Dominion
        return self.finished_actions.filter(Q(dompc=dompc) | Q(assistants=dompc)).order_by('-date_submitted')

    def add_dompc(self, dompc, status=None, recruiter=None):
        """Invites a dompc to join the plot."""
        from server.utils.exceptions import CommandError
        status_types = [ob[1].split()[0].lower() for ob in PCPlotInvolvement.CAST_STATUS_CHOICES]
        del status_types[-1]
        status = status if status else "main"
        if status not in status_types:
            raise CommandError("Status must be one of these: %s" % ", ".join(status_types))
        try:
            involvement = self.dompc_involvement.get(dompc_id=dompc.id)
            if involvement.activity_status <= PCPlotInvolvement.INVITED:
                raise CommandError("They are already invited.")
        except PCPlotInvolvement.DoesNotExist:
            involvement = PCPlotInvolvement(dompc=dompc, plot=self)
        involvement.activity_status = PCPlotInvolvement.INVITED
        involvement.cast_status = status_types.index(status)
        involvement.save()
        inf_msg = "You have been invited to join plot '%s'" % self
        inf_msg += (" by %s" % recruiter) if recruiter else ""
        inf_msg += ". Use 'plots %s' for details, including other participants. " % self.id
        inf_msg += "To accept this invitation, use the following command: "
        inf_msg += "plots/accept %s[=<IC description of character's involvement>]." % self.id
        if recruiter:
            inf_msg += "\nIf you accept, a small XP reward can be given to %s (and yourself) with: " % recruiter
            inf_msg += "'plots/rewardrecruiter %s=%s'. For more help see 'help plots'." % (self.id, recruiter)
        dompc.inform(inf_msg, category="Plot Invite")

    @property
    def first_owner(self):
        """Returns the first owner-level PlayerOrNpc, or None"""
        owner_inv = self.dompc_involvement.filter(admin_status=PCPlotInvolvement.OWNER).first()
        if owner_inv:
            return owner_inv.dompc

    @property
    def cast_list(self):
        """Returns string of the cast's status and admin levels."""
        cast = self.dompc_involvement.filter(activity_status__lte=PCPlotInvolvement.INVITED).order_by('cast_status')
        msg = "Involved Characters:\n" if cast else ""
        sep = ""
        for role in cast:
            invited = "*Invited* " if role.activity_status == role.INVITED else ""
            msg += "%s%s|c%s|n" % (sep, invited, role.dompc)
            status = []
            if role.cast_status <= 2:
                status.append(role.get_cast_status_display())
            if role.admin_status >= 2:
                status.append(role.get_admin_status_display())
            if any(status):
                msg += " (%s)" % ", ".join([ob for ob in status])
            sep = "\n"
        return msg

    def inform(self, text, category="Plot", append=True):
        """Sends an inform to all active participants"""
        active = self.dompcs.filter(plot_involvement__activity_status=PCPlotInvolvement.ACTIVE)
        for dompc in active:
            dompc.inform(text, category=category, append=append)


class OrgPlotInvolvement(SharedMemoryModel):
    """An org's participation in a plot"""
    plot = models.ForeignKey("Plot", related_name="org_involvement", on_delete=models.CASCADE)
    org = models.ForeignKey("Organization", related_name="plot_involvement", on_delete=models.CASCADE)
    auto_invite_members = models.BooleanField(default=False)
    gm_notes = models.TextField(blank=True)


class PCPlotInvolvement(SharedMemoryModel):
    """A character's participation in a plot"""
    REQUIRED_CAST, MAIN_CAST, SUPPORTING_CAST, EXTRA, TANGENTIAL = range(5)
    ACTIVE, INACTIVE, INVITED, HAS_RP_HOOK, LEFT, NOT_ADDED = range(6)
    SUBMITTER, PLAYER, RECRUITER, GM, OWNER = range(5)
    CAST_STATUS_CHOICES = ((REQUIRED_CAST, "Required Cast"), (MAIN_CAST, "Main Cast"),
                           (SUPPORTING_CAST, "Supporting Cast"),
                           (EXTRA, "Extra"), (TANGENTIAL, "Tangential"))
    ACTIVITY_STATUS_CHOICES = ((ACTIVE, "Active"), (INACTIVE, "Inactive"), (INVITED, "Invited"),
                               (HAS_RP_HOOK, "Has RP Hook"), (LEFT, "Left"), (NOT_ADDED, "Not Added"))
    ADMIN_STATUS_CHOICES = ((OWNER, "Owner"), (GM, "GM"), (RECRUITER, "Recruiter"), (PLAYER, "Player"),
                            (SUBMITTER, "Submitting Player"))
    plot = models.ForeignKey("Plot", related_name="dompc_involvement", on_delete=models.CASCADE)
    dompc = models.ForeignKey("PlayerOrNpc", related_name="plot_involvement", on_delete=models.CASCADE)
    cast_status = models.PositiveSmallIntegerField(choices=CAST_STATUS_CHOICES, default=MAIN_CAST)
    activity_status = models.PositiveSmallIntegerField(choices=ACTIVITY_STATUS_CHOICES, default=ACTIVE)
    admin_status = models.PositiveSmallIntegerField(choices=ADMIN_STATUS_CHOICES, default=PLAYER)
    recruiter_story = models.TextField(blank=True)
    recruited_by = models.ForeignKey("PlayerOrNpc", blank=True, null=True, related_name="plot_recruits", on_delete=models.SET_NULL)
    gm_notes = models.TextField(blank=True)

    def __str__(self):
        return str(self.dompc)

    def get_modified_status_display(self):
        """Modifies status display with whether we're a GM"""
        msg = self.get_cast_status_display()
        if self.admin_status > self.PLAYER:
            msg += " (%s)" % self.get_admin_status_display()
        return msg

    def display_plot_involvement(self):
        """
        Plot info along with attached lore objects that are marked
        if the character does not know them.
        """
        msg = self.plot.display()
        clues = self.plot.clues.all()
        revs = self.plot.revelations.all()
        theories = self.plot.theories.all()
        our_plots = self.dompc.active_plots.all()
        subplots = set(self.plot.subplots.all()) & set(our_plots)

        def format_name(obj, unknown):
            name = "%s(#%s)" % (obj, obj.id)
            if obj in unknown:
                name += "({rX{n)"
            return name

        if self.plot.parent_plot and self.plot.parent_plot in our_plots:
            # noinspection PyTypeChecker
            msg += "\n{wParent Plot:{n %s" % format_name(self.plot.parent_plot, [])
        if subplots:
            msg += "\n{wSubplots:{n %s" % ", ".join(format_name(ob, []) for ob in subplots)
        if clues:
            msg += "\n{wRelated Clues:{n "
            pc_clues = list(self.dompc.player.roster.clues.all())
            unknown_clues = [ob for ob in clues if ob not in pc_clues]
            msg += "; ".join(format_name(ob, unknown_clues) for ob in clues)
        if revs:
            msg += "\n{wRelated Revelations:{n "
            pc_revs = list(self.dompc.player.roster.revelations.all())
            unknown_revs = [ob for ob in revs if ob not in pc_revs]
            msg += "; ".join(format_name(ob, unknown_revs) for ob in revs)
        if theories:
            msg += "\n{wRelated Theories:{n "
            pc_theories = list(self.dompc.player.known_theories.all())
            unknown_theories = [ob for ob in theories if ob not in pc_theories]
            msg += "; ".join(format_name(ob, unknown_theories) for ob in theories)
        return msg

    def accept_invitation(self, description=""):
        self.activity_status = self.ACTIVE
        if description:
            if self.gm_notes:
                self.gm_notes += "\n"
            self.gm_notes += description
        self.save()

    def leave_plot(self):
        self.activity_status = self.LEFT
        self.save()


class PlotUpdate(SharedMemoryModel):
    """
    Container for showing all the Plot Actions during a period and their corresponding
    result on the crisis
    """
    plot = models.ForeignKey("Plot", related_name="updates", db_index=True, on_delete=models.CASCADE)
    desc = models.TextField("Story of what happened this update", blank=True)
    ooc_notes = models.TextField("Player-visible ooc notes", blank=True)
    gm_notes = models.TextField("Staff-visible notes", blank=True)
    date = models.DateTimeField(blank=True, null=True)
    episode = models.ForeignKey("character.Episode", related_name="plot_updates", blank=True, null=True,
                                on_delete=models.SET_NULL)
    search_tags = models.ManyToManyField("character.SearchTag", blank=True, related_name="plot_updates")

    @property
    def noun(self):
        return "Beat" if self.plot.usage == Plot.PLAYER_RUN_PLOT else "Update"

    def __str__(self):
        return "%s #%s for %s" % (self.noun, self.id, self.plot)

    def display_beat(self, display_connected=True, staff_display=False):
        """Return string display of this update/beat"""
        msg_bits = ["|w[{}|w]|n".format(self)]
        if self.date:
            msg_bits.append(" |wDate|n {}".format(self.date.strftime("%x %X")))
        tags = self.search_tags.all()
        if tags:
            msg_bits.append(" |wTags:|n %s" % ", ".join(("|235%s|n" % tag) for tag in tags))
        msg_bits.append("\n{}".format(self.desc or "Pending {} placeholder.".format(self.noun)))
        if display_connected:
            for attr in ("actions", "events", "emits", "flashbacks"):
                qs = getattr(self, attr).all()
                if qs:
                    msg_bits.append("\n|w%s:|n %s" % (attr.capitalize(), ", ".join("%s (#%s)" % (ob, ob.id) for ob in qs)))
        if self.ooc_notes:
            msg_bits.append("\n{}".format(self.ooc_notes))
        if staff_display and self.gm_notes:
            msg_bits.append("\n|wOOC for Staff:|n {}".format(self.gm_notes))
        return "".join(msg_bits)





class AbstractAction(AbstractPlayerAllocations):
    """Abstract parent class representing a player's participation in an action"""
    NOUN = "Action"
    BASE_AP_COST = 50
    secret_actions = models.TextField("Secret actions the player is taking", blank=True)
    attending = models.BooleanField(default=True)
    traitor = models.BooleanField(default=False)
    date_submitted = models.DateTimeField(blank=True, null=True)
    editable = models.BooleanField(default=True)
    resource_types = ('silver', 'military', 'economic', 'social', 'ap', 'action points', 'army')
    free_action = models.BooleanField(default=False)
    difficulty = None

    class Meta:
        abstract = True

    @property
    def submitted(self):
        """Whether they've submitted this or not"""
        return bool(self.date_submitted)

    @property
    def ap_refund_amount(self):
        """How much AP to refund"""
        return self.action_points + self.BASE_AP_COST

    def pay_action_points(self, amount):
        """Passthrough method to make the player pay action points"""
        return self.dompc.player.pay_action_points(amount)

    def refund(self):
        """Method for refunding a player's resources, AP, etc."""
        self.pay_action_points(-self.ap_refund_amount)
        for resource in ('military', 'economic', 'social'):
            value = getattr(self, resource)
            if value:
                self.dompc.player.gain_resources(resource, value)
        if self.silver:
            self.dompc.assets.vault += self.silver
            self.dompc.assets.save()

    def check_view_secret(self, caller):
        """Whether caller can view the secret part of this action"""
        if not caller:
            return
        if caller.check_permstring("builders") or caller == self.dompc.player:
            return True

    def get_action_text(self, secret=False, disp_summary=False):
        """Gets the text of their action"""
        noun = self.NOUN
        author = " by {c%s{w" % self.author
        if secret:
            prefix_txt = "Secret "
            action = self.secret_actions
            if self.traitor:
                prefix_txt += "{rTraitorous{w "
            suffix_txt = ":{n %s" % action
        else:
            prefix_txt = ""
            action = self.actions
            if noun == "Action":
                noun = "%s" % self.pretty_str
                author = ""
            summary = ""
            if disp_summary:
                summary = "\n%s" % self.get_summary_text()
            suffix_txt = "%s\n{wAction:{n %s" % (summary, action)
        return "\n{w%s%s%s%s{n" % (prefix_txt, noun, author, suffix_txt)

    def get_summary_text(self):
        """Returns brief formatted summary of this action"""
        return "{wSummary:{n %s" % self.topic

    @property
    def ooc_intent(self):
        """Returns the question that acts as this action's OOC intent - what the player wants"""
        try:
            return self.questions.get(is_intent=True)
        except ActionOOCQuestion.DoesNotExist:
            return None

    def set_ooc_intent(self, text):
        """Sets the action's OOC intent"""
        ooc_intent = self.ooc_intent
        if not ooc_intent:
            self.questions.create(text=text, is_intent=True)
        else:
            ooc_intent.text = text
            ooc_intent.save()

    def ask_question(self, text):
        """Adds an OOC question to GMs by the player"""
        msg = "{c%s{n added a comment/question about Action #%s:\n%s" % (self.author, self.main_id, text)
        inform_staff(msg)
        if self.gm:
            self.gm.inform(msg, category="Action questions")
        return self.questions.create(text=text)

    @property
    def is_main_action(self):
        """Whether this is the main action. False means we're an assist"""
        return self.NOUN == "Action"

    @property
    def author(self):
        """The author of this action - the main originating character who others are assisting"""
        return self.dompc

    def inform(self, text, category="Actions", append=False):
        """Passthrough method to send an inform to the player"""
        self.dompc.inform(text, category=category, append=append)

    def submit(self):
        """Attempts to submit this action. Can raise ActionSubmissionErrors."""
        self.raise_submission_errors()
        self.on_submit_success()

    def on_submit_success(self):
        """If no errors were raised, we mark ourselves as submitted and no longer allow edits."""
        if not self.date_submitted:
            self.date_submitted = datetime.now()
        self.editable = False
        self.save()
        self.post_edit()

    def raise_submission_errors(self):
        """Raises errors if this action is not ready for submission."""
        fields = self.check_incomplete_required_fields()
        if fields:
            raise ActionSubmissionError("Incomplete fields: %s" % ", ".join(fields))
        from server.utils.arx_utils import check_break
        if check_break():
            raise ActionSubmissionError("Cannot submit an action while staff are on break.")

    def check_incomplete_required_fields(self):
        """Returns any required fields that are not yet defined."""
        fields = []
        if not self.actions:
            fields.append("action text")
        if not self.ooc_intent:
            fields.append("ooc intent")
        if not self.topic:
            fields.append("tldr")
        if not self.skill_used or not self.stat_used:
            fields.append("roll")
        return fields

    def post_edit(self):
        """In both child classes this check occurs after a resubmit."""
        pass

    @property
    def plot_attendance(self):
        """Returns list of actions we are attending - physically present for"""
        attended_actions = list(self.dompc.actions.filter(Q(beat__isnull=True)
                                                          & Q(attending=True)
                                                          & Q(plot__isnull=False)
                                                          & ~Q(status=PlotAction.CANCELLED)
                                                          & Q(date_submitted__isnull=False)))
        attended_actions += list(self.dompc.assisting_actions.filter(Q(plot_action__beat__isnull=True)
                                                                     & Q(attending=True)
                                                                     & Q(plot_action__plot__isnull=False)
                                                                     & ~Q(plot_action__status=PlotAction.CANCELLED)
                                                                     & Q(date_submitted__isnull=False)))
        return attended_actions

    def check_plot_omnipresence(self):
        """Raises an ActionSubmissionError if we are already attending for this crisis"""
        if self.attending:
            already_attending = [ob for ob in self.plot_attendance if ob.plot == self.plot]
            if already_attending:
                already_attending = already_attending[-1]
                raise ActionSubmissionError("You are marked as physically present at %s. Use @action/toggleattend"
                                            " and also ensure this story reads as a passive role." % already_attending)

    def check_plot_overcrowd(self):
        """Raises an ActionSubmissionError if too many people are attending"""
        attendees = self.attendees
        if len(attendees) > self.attending_limit and not self.prefer_offscreen:
            excess = len(attendees) - self.attending_limit
            raise ActionSubmissionError("An onscreen action can have %s people attending in person. %s of you should "
                                        "check your story, then change to a passive role with @action/toggleattend. "
                                        "Alternately, the action can be marked as preferring offscreen resolution. "
                                        "Current attendees: %s" % (self.attending_limit, excess,
                                                                   ",".join(str(ob) for ob in attendees)))

    def check_plot_errors(self):
        """Raises ActionSubmissionErrors if anything should stop our submission"""
        if self.plot:
            self.plot.raise_submission_errors()
            self.check_plot_omnipresence()
        self.check_plot_overcrowd()

    def mark_attending(self):
        """Marks us as physically attending, raises ActionSubmissionErrors if it shouldn't be allowed."""
        self.check_plot_errors()
        self.attending = True
        self.save()

    def add_resource(self, r_type, value):
        """
        Adds a resource to this action of the specified type and value
        Args:
            r_type (str or unicode): The resource type
            value (str or unicode): The value passed.

        Raises:
            ActionSubmissionError if we run into bad values passed or cannot otherwise submit an action, and ValueError
            if they submit a value that isn't a positive integer when an amount is specified.
        """
        if not self.actions:
            raise ActionSubmissionError("Join first with the /setaction switch.")
        if self.plot:
            try:
                self.plot.raise_creation_errors(self.dompc)
            except ActionSubmissionError as err:
                raise ActionSubmissionError(err)
        r_type = r_type.lower()
        if r_type not in self.resource_types:
            raise ActionSubmissionError("Invalid type of resource.")
        if r_type == "army":
            try:
                return self.add_army(value)
            except ActionSubmissionError as err:
                raise ActionSubmissionError(err)
        try:
            value = int(value)
            if value <= 0:
                raise ValueError
        except ValueError:
            raise ActionSubmissionError("Amount must be a positive number.")
        if r_type == "silver":
            try:
                self.dompc.player.char_ob.pay_money(value)
            except PayError:
                raise ActionSubmissionError("You cannot afford that.")
        elif r_type == 'ap' or r_type == 'action points':
            if not self.dompc.player.pay_action_points(value):
                raise ActionSubmissionError("You do not have enough action points to exert that kind of effort.")
            r_type = "action_points"
        else:
            if not self.dompc.player.pay_resources(r_type, value):
                raise ActionSubmissionError("You cannot afford that.")
        value += getattr(self, r_type)
        setattr(self, r_type, value)
        self.save()

    def add_army(self, name_or_id):
        """Adds army orders to this action. Army can be specified by name or ID."""
        try:
            if name_or_id.isdigit():
                army = Army.objects.get(id=int(name_or_id))
            else:
                army = Army.objects.get(name__iexact=name_or_id)
        except (AttributeError, Army.DoesNotExist):
            raise ActionSubmissionError("No army by that ID# was found.")
        if self.is_main_action:
            action = self
            action_assist = None
        else:
            action = self.plot_action
            action_assist = self
        orders = army.send_orders(player=self.dompc.player, order_type=Orders.CRISIS, action=action,
                                  action_assist=action_assist)
        if not orders:
            raise ActionSubmissionError("Failed to send orders to the army.")

    def do_roll(self, stat=None, skill=None, difficulty=None, reset_total=True):
        """
        Does a roll for this action
        Args:
            stat: stat to override stat currently set in the action
            skill: skill to override skill currently set in the action
            difficulty: difficulty to override difficulty currently set in the action
            reset_total: Whether to recalculate the outcome value

        Returns:
            An integer result of the roll.
        """
        from world.stats_and_skills import do_dice_check
        self.stat_used = stat or self.stat_used
        self.skill_used = skill or self.skill_used
        if difficulty is not None:
            self.difficulty = difficulty
        self.roll = do_dice_check(self.dompc.player.char_ob, stat=self.stat_used, skill=self.skill_used,
                                  difficulty=self.difficulty)
        self.save()
        if reset_total:
            self.calculate_outcome_value()
        return self.roll

    def display_followups(self):
        """Returns string of the display of all of our questions."""
        return "\n".join(question.display() for question in self.questions.all())

    def add_answer(self, gm, text):
        """Adds a GM's answer to an OOC question"""
        unanswered = self.unanswered_questions
        if unanswered:
            unanswered.last().add_answer(gm, text)
        else:
            self.questions.last().add_answer(gm, text)

    def mark_answered(self, gm):
        """Marks a question as resolved"""
        for question in self.unanswered_questions:
            question.mark_answered = True
            question.save()
        inform_staff("%s has marked action %s's questions as answered." % (gm, self.main_id))

    @property
    def main_id(self):
        """ID of the main action"""
        return self.main_action.id

    @property
    def unanswered_questions(self):
        """Returns queryset of an OOC questions without an answer"""
        return self.questions.filter(answers__isnull=True).exclude(Q(is_intent=True) | Q(mark_answered=True))


class PlotAction(AbstractAction):
    """
    An action that a player is taking. May be in response to a Crisis.
    """
    NOUN = "Action"
    EASY_DIFFICULTY = 15
    NORMAL_DIFFICULTY = 30
    HARD_DIFFICULTY = 60
    week = models.PositiveSmallIntegerField(default=0, blank=0, db_index=True)
    dompc = models.ForeignKey("PlayerOrNpc", db_index=True, blank=True, null=True, related_name="actions", on_delete=models.CASCADE)
    plot = models.ForeignKey("Plot", db_index=True, blank=True, null=True, related_name="actions", on_delete=models.SET_NULL)
    beat = models.ForeignKey("PlotUpdate", db_index=True, blank=True, null=True, related_name="actions", on_delete=models.SET_NULL)
    public = models.BooleanField(default=False, blank=True)
    gm_notes = models.TextField("Any ooc notes for other GMs", blank=True)
    story = models.TextField("Story written by the GM for the player", blank=True)
    secret_story = models.TextField("Any secret story written for the player", blank=True)
    difficulty = models.SmallIntegerField(default=0, blank=0)
    outcome_value = models.SmallIntegerField(default=0, blank=0)
    assistants = models.ManyToManyField("PlayerOrNpc", blank=True, through="PlotActionAssistant",
                                        related_name="assisted_actions")
    prefer_offscreen = models.BooleanField(default=False, blank=True)
    gemit = models.ForeignKey("character.StoryEmit", blank=True, null=True, related_name="actions", on_delete=models.CASCADE)
    gm = models.ForeignKey(settings.AUTH_USER_MODEL, blank=True, null=True, related_name="gmd_actions", on_delete=models.SET_NULL)
    search_tags = models.ManyToManyField("character.SearchTag", blank=True, related_name="actions")
    working = models.OneToOneField("magic.Working", blank=True, null=True, related_name="action", on_delete=models.CASCADE)

    UNKNOWN, COMBAT, SUPPORT, SABOTAGE, DIPLOMACY, SCOUTING, RESEARCH = range(7)

    CATEGORY_CHOICES = ((UNKNOWN, 'Unknown'), (COMBAT, 'Combat'), (SUPPORT, 'Support'), (SABOTAGE, 'Sabotage'),
                        (DIPLOMACY, 'Diplomacy'), (SCOUTING, 'Scouting'), (RESEARCH, 'Research'))
    category = models.PositiveSmallIntegerField(choices=CATEGORY_CHOICES, default=UNKNOWN)

    DRAFT, NEEDS_PLAYER, NEEDS_GM, CANCELLED, PENDING_PUBLISH, PUBLISHED = range(6)

    STATUS_CHOICES = ((DRAFT, 'Draft'), (NEEDS_PLAYER, 'Needs Player Input'), (NEEDS_GM, 'Needs GM Input'),
                      (CANCELLED, 'Cancelled'), (PENDING_PUBLISH, 'Pending Resolution'), (PUBLISHED, 'Resolved'))
    status = models.PositiveSmallIntegerField(choices=STATUS_CHOICES, default=DRAFT)
    max_requests = 2
    num_days = 60
    attending_limit = 5

    def __str__(self):
        if self.plot:
            plot = " for %s" % self.plot
        else:
            plot = ""
        return "%s by %s%s" % (self.NOUN, self.author, plot)

    @property
    def commafied_participants(self):
        dompc_list = [str(self.dompc)]
        for assist in self.assistants.all():
            dompc_list.append(str(assist))
        if len(dompc_list) == 1:
            return str(self.dompc)
        elif len(dompc_list) == 2:
            return dompc_list[0] + " and " + dompc_list[1]
        else:
            return ", ".join(dompc_list[:-2] + [" and ".join(dompc_list[-2:])])

    @property
    def pretty_str(self):
        """Returns formatted display of this action"""
        if self.plot:
            plot = " for {m%s{n" % self.plot
        else:
            plot = ""
        return "%s by {c%s{n%s" % (self.NOUN, self.author, plot)

    @property
    def sent(self):
        """Whether this action is published"""
        return bool(self.status == self.PUBLISHED)

    @property
    def total_social(self):
        """Total social resources spent"""
        return self.social + sum(ob.social for ob in self.assisting_actions.all())

    @property
    def total_economic(self):
        """Total economic resources spent"""
        return self.economic + sum(ob.economic for ob in self.assisting_actions.all())

    @property
    def total_military(self):
        """Total military resources spent"""
        return self.military + sum(ob.military for ob in self.assisting_actions.all())

    @property
    def total_silver(self):
        """Total silver spent"""
        return self.silver + sum(ob.silver for ob in self.assisting_actions.all())

    @property
    def total_action_points(self):
        """Total action points spent"""
        return self.action_points + sum(ob.action_points for ob in self.assisting_actions.all())

    @property
    def action_and_assists_and_invites(self):
        """List of this action and all our assists, whether they've accepted invite or not"""
        return [self] + list(self.assisting_actions.all())

    @property
    def action_and_assists(self):
        """Listof actions and assists if they've written anything"""
        return [ob for ob in self.action_and_assists_and_invites if ob.actions]

    @property
    def all_editable(self):
        """List of all actions and assists if they're currently editable"""
        return [ob for ob in self.action_and_assists_and_invites if ob.editable]

    def send(self, update=None, caller=None):
        """Publishes this action"""
        if self.plot:
            msg = "{wGM Response to action for crisis:{n %s" % self.plot
        else:
            msg = "{wGM Response to story action of %s" % self.author
        msg += "\n{wRolls:{n %s" % self.outcome_value
        msg += "\n\n{wStory Result:{n %s\n\n" % self.story
        self.week = get_week()
        if update:
            self.beat = update
        if self.status != PlotAction.PUBLISHED:
            self.inform(msg)
            for assistant in self.assistants.all():
                assistant.inform(msg, category="Actions")
            for orders in self.orders.all():
                orders.complete = True
                orders.save()
            self.status = PlotAction.PUBLISHED
        if not self.gm:
            self.gm = caller
        self.save()
        if not update:
            subject = "Action %s Published by %s" % (self.id, caller)
            post = self.view_tldr()
            post += "\n{wStory Result:{n %s" % self.story
            if self.secret_story:
                post += "\n{wSecret Story{n %s" % self.secret_story
            inform_staff("Action %s has been published by %s:\n%s" % (self.id, caller, msg),
                         post=post, subject=subject)

    def view_action(self, caller=None, disp_pending=True, disp_old=False, disp_ooc=True):
        """
        Returns a text string of the display of an action.

            Args:
                caller: Player who is viewing this
                disp_pending (bool): Whether to display pending questions
                disp_old (bool): Whether to display answered questions
                disp_ooc (bool): Whether to only display IC information

            Returns:
                Text string to display.
        """
        msg = "\n"
        if caller:
            staff_viewer = caller.check_permstring("builders")
            participant_viewer = caller == self.dompc.player or caller.Dominion in self.assistants.all()
        else:
            staff_viewer = False
            participant_viewer = False
        if not self.public and not (staff_viewer or participant_viewer):
            return msg
        # print out actions of everyone
        all_actions = self.action_and_assists
        view_main_secrets = staff_viewer or self.check_view_secret(caller)
        if disp_ooc:
            msg += "{wAction ID:{n #%s" % self.id
            msg += " {wCategory:{n %s" % self.get_category_display()
            if self.date_submitted:
                msg += "  {wDate:{n %s" % self.date_submitted.strftime("%x %X")
            if staff_viewer:
                if self.gm is not None:
                    msg += "  {wGM:{n %s" % self.gm
        for ob in all_actions:
            view_secrets = staff_viewer or ob.check_view_secret(caller)
            msg += ob.get_action_text(disp_summary=view_secrets)
            if ob.secret_actions and view_secrets:
                msg += ob.get_action_text(secret=True)
            if view_secrets and disp_ooc:
                attending = "[%s]" % ("physically present" if ob.attending else "offscreen")
                msg += "\n{w%s{n {w%s{n (stat) + {w%s{n (skill) at difficulty {w%s{n" % (
                    attending,
                    ob.stat_used.capitalize() or "No stat set",
                    ob.skill_used.capitalize() or "No skill set",
                    self.difficulty)
                if self.sent or (ob.roll_is_set and staff_viewer):
                    msg += "{w [Dice Roll: %s%s{w]{n " % (self.roll_color(ob.roll), ob.roll_string)
                if ob.ooc_intent:
                    msg += "\n%s" % ob.ooc_intent.display()
            msg += "\n"
        if self.working:
            msg += "\n{wWorking:{n %d [%s]: %s" % (self.working.id, self.working.participant_string,
                                                   self.working.intent)
        if (disp_pending or disp_old) and disp_ooc:
            q_and_a_str = self.get_questions_and_answers_display(answered=disp_old, staff=staff_viewer, caller=caller)
            if q_and_a_str:
                msg += "\n{wOOC Notes and GM responses\n%s" % q_and_a_str
        if staff_viewer and self.gm_notes or self.prefer_offscreen:
            offscreen = "[Offscreen resolution preferred.] " if self.prefer_offscreen else ""
            msg += "\n{wGM Notes:{n %s%s" % (offscreen, self.gm_notes)
        if self.sent or staff_viewer:
            if disp_ooc:
                msg += "\n{wOutcome Value:{n %s%s{n" % (self.roll_color(self.outcome_value), self.outcome_value)
            msg += "\n{wStory Result:{n %s" % self.story
            if self.secret_story and view_main_secrets:
                msg += "\n{wSecret Story{n %s" % self.secret_story
        if disp_ooc:
            msg += "\n" + self.view_total_resources_msg()
            orders = []
            for ob in all_actions:
                orders += list(ob.orders.all())
            orders = set(orders)
            if len(orders) > 0:
                msg += "\n{wArmed Forces Appointed:{n %s" % ", ".join(str(ob.army) for ob in orders)
            needs_edits = ""
            if self.status == PlotAction.NEEDS_PLAYER:
                needs_edits = " Awaiting edits to be submitted by: %s" % \
                              ", ".join(ob.author for ob in self.all_editable)
            msg += "\n{w[STATUS: %s]{n%s" % (self.get_status_display(), needs_edits)
        return msg

    @staticmethod
    def roll_color(val):
        """Returns a color string based on positive or negative value."""
        return "{r" if (val < 0) else "{g"

    def view_tldr(self):
        """Returns summary message of the action and assists"""
        msg = "{wSummary of action %s{n" % self.id
        for action in self.action_and_assists:
            msg += "\n%s: %s\n" % (action.pretty_str, action.get_summary_text())
        return msg

    def view_total_resources_msg(self):
        """Returns string of all resources spent"""
        msg = ""
        fields = {'extra action points': self.total_action_points,
                  'silver': self.total_silver,
                  'economic': self.total_economic,
                  'military': self.total_military,
                  'social': self.total_social}
        totals = ", ".join("{c%s{n %s" % (key, value) for key, value in fields.items() if value > 0)
        if totals:
            msg = "{wTotal resources:{n %s" % totals
        return msg

    def cancel(self):
        """Cancels and refunds this action"""
        for action in self.assisting_actions.all():
            action.cancel()
        self.refund()
        if not self.date_submitted:
            self.delete()
        else:
            self.status = PlotAction.CANCELLED
            self.save()

    def check_incomplete_required_fields(self):
        """Checks which fields are incomplete"""
        fields = super(PlotAction, self).check_incomplete_required_fields()
        if not self.category:
            fields.append("category")
        return fields

    def raise_submission_errors(self):
        """Raises errors that prevent submission"""
        super(PlotAction, self).raise_submission_errors()
        self.check_plot_errors()
        self.check_draft_errors()

    def check_draft_errors(self):
        """Checks any errors that occur only during initial creation"""
        if self.status != PlotAction.DRAFT:
            return
        self.check_action_against_maximum_allowed()
        self.check_warning_prompt_sent()

    def check_action_against_maximum_allowed(self):
        """Checks if we're over our limit on number of actions"""
        if self.free_action:
            return
        recent_actions = self.dompc.recent_actions
        num_actions = len(recent_actions)
        # we allow them to use unspent actions for assists, but not vice-versa
        num_assists = self.dompc.recent_assists.count()
        num_assists -= PlotActionAssistant.MAX_ASSISTS
        if num_assists >= 0:
            num_actions += num_assists
        if num_actions >= self.max_requests:
            raise ActionSubmissionError("You are permitted %s action requests every %s days. Recent actions: %s"
                                        % (self.max_requests, self.num_days,
                                           ", ".join(str(ob.id) for ob in recent_actions)))

    def check_warning_prompt_sent(self):
        """Sends a warning message to the player if they don't have one yet"""
        if self.dompc.player.ndb.action_submission_prompt != self:
            self.dompc.player.ndb.action_submission_prompt = self
            warning = ("{yBefore submitting this action, make certain that you have invited all players you wish to "
                       "help with the action, and add any resources necessary. Any invited players who have incomplete "
                       "actions will have their assists deleted.")
            unready = ", ".join(str(ob.author) for ob in self.get_unready_assisting_actions())
            if unready:
                warning += "\n{rThe following assistants are not ready and will be deleted: %s" % unready
            warning += "\n{yWhen ready, /submit the action again.{n"
            raise ActionSubmissionError(warning)

    def get_unready_assisting_actions(self):
        """Gets list of assists that are not yet ready"""
        unready = []
        for ob in self.assisting_actions.all():
            try:
                ob.raise_submission_errors()
            except ActionSubmissionError:
                unready.append(ob)
        return unready

    def check_unready_assistant(self, dompc):
        """Checks a given dompc being unready"""
        try:
            assist = self.assisting_actions.get(dompc=dompc)
            assist.raise_submission_errors()
        except PlotActionAssistant.DoesNotExist:
            return False
        except ActionSubmissionError:
            return True
        else:
            return False

    @property
    def attendees(self):
        """Returns list of authors of all actions and assists if physically present"""
        return [ob.author for ob in self.action_and_assists if ob.attending]

    def on_submit_success(self):
        """Announces us after successful submission. refunds any assistants who weren't ready"""
        if self.status == PlotAction.DRAFT:
            self.status = PlotAction.NEEDS_GM
            for assist in self.assisting_actions.filter(date_submitted__isnull=True):
                assist.submit_or_refund()
            inform_staff("%s submitted action #%s. %s" % (self.author, self.id, self.get_summary_text()))
        super(PlotAction, self).on_submit_success()

    def post_edit(self):
        """Announces that we've finished editing our action and are ready for a GM"""
        if self.status == PlotAction.NEEDS_PLAYER and not self.all_editable:
            self.status = PlotAction.NEEDS_GM
            self.save()
            inform_staff("%s has been resubmitted for GM review." % self)
            if self.gm:
                self.gm.inform("Action %s has been updated." % self.id, category="Actions")

    def invite(self, dompc):
        """Invites an assistant, sending them an inform"""
        if self.assistants.filter(player=dompc.player).exists():
            raise ActionSubmissionError("They have already been invited.")
        if dompc == self.dompc:
            raise ActionSubmissionError("The owner of an action cannot be an assistant.")
        self.assisting_actions.create(dompc=dompc, stat_used="", skill_used="")
        msg = "You have been invited by %s to assist with action #%s." % (self.author, self.id)
        msg += " It will now display under the {w@action{n command. To assist, simply fill out"
        msg += " the required fields, starting with {w@action/setaction{n, and then {w@action/submit %s{n." % self.id
        msg += " If the owner submits the action to the GMs before your assist is valid, it will be"
        msg += " deleted and you will be refunded any AP and resources."
        msg += " When creating your assist, please only write a story about attempting to modify"
        msg += " the main action you're assisting. Assists which are unrelated to the action"
        msg += " should be their own independent @action. Secret actions attempting to undermine"
        msg += " the action/crisis should use the '/traitor' switch."
        msg += " To decline this invitation, use {w@action/cancel %s{n." % self.id
        dompc.inform(msg, category="Action Invitation")

    def roll_all(self):
        """Rolls for every action and assist, changing outcome value"""
        for ob in self.action_and_assists:
            ob.do_roll(reset_total=False)
        return self.calculate_outcome_value()

    def calculate_outcome_value(self):
        """Calculates total value of the action"""
        value = sum(ob.roll for ob in self.action_and_assists)
        self.outcome_value = value
        self.save()
        return self.outcome_value

    def get_questions_and_answers_display(self, answered=False, staff=False, caller=None):
        """Displays all OOC questions and answers"""
        qs = self.questions.filter(is_intent=False)
        if not answered:
            qs = qs.filter(answers__isnull=True, mark_answered=False)
        if not staff:
            dompc = caller.Dominion
            # players can only see questions they wrote themselves and their answers
            qs = qs.filter(Q(action_assist__dompc=dompc) | Q(Q(action__dompc=dompc) & Q(action_assist__isnull=True)))
        qs = list(qs)
        if staff:
            for ob in self.assisting_actions.all():
                if answered:
                    qs.extend(list(ob.questions.filter(is_intent=False)))
                else:
                    qs.extend(list(ob.questions.filter(answers__isnull=True, is_intent=False, mark_answered=False)))
        return "\n".join(question.display() for question in set(qs))

    @property
    def main_action(self):
        """Returns ourself as the main action"""
        return self

    def make_public(self):
        """Makes an action public for all players to see"""
        if self.public:
            raise ActionSubmissionError("That action has already been made public.")
        if self.status != PlotAction.PUBLISHED:
            raise ActionSubmissionError("The action must be finished before you can make details of it public.")
        self.public = True
        self.save()
        xp_value = 2
        if self.plot and not self.plot.public:
            xp_value = 1
        self.dompc.player.char_ob.adjust_xp(xp_value)
        self.dompc.msg("You have gained %s xp for making your action public." % xp_value)
        inform_staff("Action %s has been made public." % self.id)


NAMES_OF_PROPERTIES_TO_PASS_THROUGH = ['plot', 'action_and_assists', 'status', 'prefer_offscreen', 'attendees',
                                       'all_editable', 'outcome_value', 'difficulty', 'gm', 'attending_limit']


@passthrough_properties('plot_action', *NAMES_OF_PROPERTIES_TO_PASS_THROUGH)
class PlotActionAssistant(AbstractAction):
    """An assist for a plot action - a player helping them out and writing how."""
    NOUN = "Assist"
    BASE_AP_COST = 10
    MAX_ASSISTS = 4
    plot_action = models.ForeignKey("PlotAction", db_index=True, related_name="assisting_actions", on_delete=models.CASCADE)
    dompc = models.ForeignKey("PlayerOrNpc", db_index=True, related_name="assisting_actions", on_delete=models.CASCADE)

    class Meta:
        unique_together = ('plot_action', 'dompc')

    def __str__(self):
        return "%s assisting %s" % (self.author, self.plot_action)

    @property
    def pretty_str(self):
        """Formatted string of the assist"""
        return "{c%s{n assisting %s" % (self.author, self.plot_action)

    def cancel(self):
        """Cancels and refunds this assist, then deletes it"""
        if self.actions:
            self.refund()
        self.delete()

    def view_total_resources_msg(self):
        """Passthrough method to return total resources msg"""
        return self.plot_action.view_total_resources_msg()

    def calculate_outcome_value(self):
        """Passthrough method to calculate outcome value"""
        return self.plot_action.calculate_outcome_value()

    def submit_or_refund(self):
        """Submits our assist if we're ready, or refunds us"""
        try:
            self.submit()
        except ActionSubmissionError:
            main_action_msg = "Cancelling incomplete assist: %s\n" % self.author
            assist_action_msg = "Your assist for %s was incomplete and has been refunded." % self.plot_action
            self.plot_action.inform(main_action_msg)
            self.inform(assist_action_msg)
            self.cancel()

    def post_edit(self):
        """Passthrough hook for after editing"""
        self.plot_action.post_edit()

    @property
    def has_paid_initial_ap_cost(self):
        """Returns if we've paid our AP cost"""
        return bool(self.actions)

    @property
    def main_action(self):
        """Returns the action we're assisting"""
        return self.plot_action

    def set_action(self, story):
        """
        Sets our assist's actions. If the action has not been set yet, we'll attempt to pay the initial ap cost,
        raising an error if that fails.

            Args:
                story (str or unicode): The story of the character's actions, written by the player.

            Raises:
                ActionSubmissionError if we have not yet paid our AP cost and the player fails to do so here.
        """
        self.check_max_assists()
        if not self.has_paid_initial_ap_cost:
            self.pay_initial_ap_cost()
        self.actions = story
        self.save()

    def ask_question(self, text):
        """Asks GMs an OOC question"""
        question = super(PlotActionAssistant, self).ask_question(text)
        question.action = self.plot_action
        question.save()

    def pay_initial_ap_cost(self):
        """Pays our initial AP cost or raises an ActionSubmissionError"""
        if not self.pay_action_points(self.BASE_AP_COST):
            raise ActionSubmissionError("You do not have enough action points.")

    def view_action(self, caller=None, disp_pending=True, disp_old=False, disp_ooc=True):
        """Returns display of the action"""
        return self.plot_action.view_action(caller=caller, disp_pending=disp_pending, disp_old=disp_old,
                                            disp_ooc=disp_ooc)

    def check_max_assists(self):
        """Raises an error if we've assisted too many actions"""
        # if we haven't spent all our actions, we'll let them use it on assists
        if self.free_action or self.plot_action.free_action:
            return
        num_actions = self.dompc.recent_actions.count() - 2
        num_assists = self.dompc.recent_assists.count()
        if num_actions < 0:
            num_assists += num_actions
        if num_assists >= self.MAX_ASSISTS:
            raise ActionSubmissionError("You are assisting too many actions.")

    def raise_submission_errors(self):
        """Raises errors that prevent submission"""
        super(PlotActionAssistant, self).raise_submission_errors()
        self.check_max_assists()


class ActionOOCQuestion(SharedMemoryModel):
    """
    OOC Question about a plot. Can be associated with a given action
    or asked about independently.
    """
    action = models.ForeignKey("PlotAction", db_index=True, related_name="questions", null=True, blank=True, on_delete=models.CASCADE)
    action_assist = models.ForeignKey("PlotActionAssistant", db_index=True, related_name="questions", null=True, blank=True, on_delete=models.CASCADE)
    text = models.TextField(blank=True)
    is_intent = models.BooleanField(default=False)
    mark_answered = models.BooleanField(default=False)

    def __str__(self):
        return "%s %s: %s" % (self.author, self.noun, self.text)

    @property
    def target(self):
        """The action or assist this question is from"""
        if self.action_assist:
            return self.action_assist
        return self.action

    @property
    def author(self):
        """Who wrote this question"""
        return self.target.author

    @property
    def noun(self):
        """String display of whether we're ooc intentions or a question"""
        return "OOC %s" % ("intentions" if self.is_intent else "Question")

    def display(self):
        """Returns string display of this object"""
        msg = "{c%s{w %s:{n %s" % (self.author, self.noun, self.text)
        answers = self.answers.all()
        if answers:
            msg += "\n%s" % "\n".join(ob.display() for ob in answers)
        return msg

    @property
    def text_of_answers(self):
        """Returns this question and all the answers to it"""
        return "\n".join("%s wrote: %s" % (ob.gm, ob.text) for ob in self.answers.all())

    @property
    def main_id(self):
        """ID of the target of this question"""
        return self.target.main_id

    def add_answer(self, gm, text):
        """Adds an answer to this question"""
        self.answers.create(gm=gm, text=text)
        self.target.inform("GM %s has posted a followup to action %s: %s" % (gm, self.main_id, text))
        answer = "{c%s{n wrote: %s\n{c%s{n answered: %s" % (self.author, self.text, gm, text)
        inform_staff("%s has posted a followup to action %s: %s" % (gm, self.main_id, text), post=answer,
                     subject="Action %s followup" % self.action.id)


class ActionOOCAnswer(SharedMemoryModel):
    """
    OOC answer from a GM about a plot.
    """
    gm = models.ForeignKey(settings.AUTH_USER_MODEL, blank=True, null=True, related_name="answers_given", on_delete=models.CASCADE)
    question = models.ForeignKey("ActionOOCQuestion", db_index=True, related_name="answers", on_delete=models.CASCADE)
    text = models.TextField(blank=True)

    def display(self):
        """Returns string display of this answer"""
        return "{wReply by {c%s{w:{n %s" % (self.gm, self.text)
