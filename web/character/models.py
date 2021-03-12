"""
App that handles the relation of the Account and Character typeclasses, web display/extensions for them, and
various in-game activities. It was meant to be the On-screen companion for Dominion acting as the off-screen
version, but the scope of that quickly became far too broad. So it's mostly limited to things like investigations,
clue discoveries, etc.

Originally, the evennia Account typeclass was called Player, which was deemed confusing for what it did, and the
name was changed. There's some confusing overlap between that and our own PlayerAccount model, but just try to hum
loudly and remember that we'll usually refer to evennia's account typeclass as 'player' or 'user' or whatever for
the django USER_AUTH_MODEL.
"""
from datetime import datetime, date
from functools import reduce
import random
import traceback

from django.db import models
from django.db.models import Q, Count, Avg
from django.conf import settings
from cloudinary.models import CloudinaryField
from evennia.locks.lockhandler import LockHandler
from evennia.utils.idmapper.models import SharedMemoryModel

from .managers import ArxRosterManager, AccountHistoryManager
from server.utils.arx_utils import CachedProperty
from server.utils.picker import WeightedPicker
from world.stats_and_skills import do_dice_check


class Photo(SharedMemoryModel):
    """
    Used for uploading photos to cloudinary. It holds a reference to cloudinary-stored
    image and contains some metadata about the image.
    """

    #  Misc Django Fields
    create_time = models.DateTimeField(auto_now_add=True)
    title = models.CharField(
        "Name or description of the picture (optional)", max_length=200, blank=True
    )
    owner = models.ForeignKey(
        "objects.ObjectDB",
        blank=True,
        null=True,
        verbose_name="owner",
        help_text="a Character owner of this image, if any.",
        on_delete=models.SET_NULL,
    )
    alt_text = models.CharField(
        "Optional 'alt' text when mousing over your image", max_length=200, blank=True
    )

    # Points to a Cloudinary image
    image = CloudinaryField("image")

    """ Informative name for mode """

    def __str__(self):
        try:
            public_id = self.image.public_id
        except AttributeError:
            public_id = ""
        return "Photo <%s:%s>" % (self.title, public_id)


class Roster(SharedMemoryModel):
    """
    A model for storing lists of entries of characters. Each RosterEntry has
    information on the Player and Character objects of that entry, information
    on player emails of previous players, GM notes, etc. The Roster itself just
    has locks for determining who can view the contents of a roster.
    """

    name = models.CharField(blank=True, null=True, max_length=255, db_index=True)
    lock_storage = models.TextField(
        "locks", blank=True, help_text="defined in setup_utils"
    )
    objects = ArxRosterManager()

    def __init__(self, *args, **kwargs):
        super(Roster, self).__init__(*args, **kwargs)
        self.locks = LockHandler(self)

    def access(self, accessing_obj, access_type="view", default=True):
        """
        Determines if another object has permission to access.
        accessing_obj - object trying to access this one
        access_type - type of access sought
        default - what to return if no lock of access_type was found
        """
        return self.locks.check(accessing_obj, access_type=access_type, default=default)

    def __str__(self):
        return self.name or "Unnamed Roster"


class RosterEntry(SharedMemoryModel):
    """
    Main model for the character app. This is used both as an extension of an evennia AccountDB model (which serves as
    USER_AUTH_MODEL and a Character typeclass, and links the two together. It also is where some data used for the
    character lives, such as action points, the profile picture for their webpage, the PlayerAccount which currently
    is playing the character, and who played it previously. RosterEntry is used for most other models in the app,
    such as investigations, discoveries of clues/revelations/mysteries, etc.
    """

    roster = models.ForeignKey(
        "Roster",
        related_name="entries",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        db_index=True,
    )
    player = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        related_name="roster",
        blank=True,
        null=True,
        unique=True,
        on_delete=models.CASCADE,
    )
    character = models.OneToOneField(
        "objects.ObjectDB",
        related_name="roster",
        blank=True,
        null=True,
        unique=True,
        on_delete=models.CASCADE,
    )
    current_account = models.ForeignKey(
        "PlayerAccount",
        related_name="characters",
        db_index=True,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )
    previous_accounts = models.ManyToManyField(
        "PlayerAccount", through="AccountHistory", blank=True
    )
    gm_notes = models.TextField(blank=True)
    # different variations of reasons not to display us
    inactive = models.BooleanField(default=False, null=False)
    frozen = models.BooleanField(default=False, null=False)
    # profile picture for sheet and also thumbnail for list
    profile_picture = models.ForeignKey(
        "Photo", blank=True, null=True, on_delete=models.SET_NULL
    )
    # going to use for determining how our character page appears
    sheet_style = models.TextField(blank=True)
    lock_storage = models.TextField(
        "locks", blank=True, help_text="defined in setup_utils"
    )
    action_points = models.SmallIntegerField(default=100, blank=100)
    show_positions = models.BooleanField(default=False)

    def __init__(self, *args, **kwargs):
        super(RosterEntry, self).__init__(*args, **kwargs)
        self.locks = LockHandler(self)

    class Meta:
        """Define Django meta options"""

        verbose_name_plural = "Roster Entries"
        unique_together = ("player", "character")

    def __str__(self):
        if self.character:
            return self.character.key
        if self.player:
            return self.player.key
        return "Blank Entry"

    def access(self, accessing_obj, access_type="show_hidden", default=False):
        """
        Determines if another object has permission to access.
        accessing_obj - object trying to access this one
        access_type - type of access sought
        default - what to return if no lock of access_type was found
        """
        return self.locks.check(accessing_obj, access_type=access_type, default=default)

    def fake_delete(self):
        """We don't really want to delete RosterEntries for reals. So we fake it."""
        self.roster = Roster.objects.deleted
        self.inactive = True
        self.frozen = True
        self.save()

    def undelete(self):
        """Restores a fake-deleted entry."""
        self.roster = Roster.objects.active
        self.inactive = False
        self.frozen = False
        self.save()

    def adjust_xp(self, val):
        """Stores xp the player's earned in their history of playing the character."""
        try:
            if val < 0:
                return
            history = self.accounthistory_set.filter(
                account=self.current_account
            ).last()
            history.xp_earned += val
            history.save()
        except AttributeError:
            pass

    @property
    def undiscovered_clues(self):
        """Clues that we -haven't- discovered. We might have partial progress or not"""
        return Clue.objects.exclude(id__in=self.clues.all())

    @property
    def alts(self):
        """Other roster entries played by our current PlayerAccount"""
        if self.current_account:
            return self.current_account.characters.exclude(id=self.id)
        return []

    def discover_clue(self, clue, method="Prior Knowledge", message=""):
        """Discovers and returns the clue, if not already."""
        disco, created = self.clue_discoveries.get_or_create(clue=clue)
        if created:
            disco.mark_discovered(method=method, message=message or "")
        return disco

    @property
    def current_history(self):
        """Displays the current tenure of the PlayerAccount running this entry."""
        return self.accounthistory_set.last()

    @property
    def previous_history(self):
        """Gets all previous accounthistories after current"""
        return self.accounthistory_set.order_by("-id")[1:]

    @property
    def postable_flashbacks(self):
        """Queryset of flashbacks we can post to."""
        retired = FlashbackInvolvement.RETIRED
        return self.flashbacks.exclude(
            Q(concluded=True) | Q(flashback_involvements__status__lte=retired)
        )

    @property
    def impressions_of_me(self):
        """Gets queryset of all our current first impressions"""
        try:
            return self.current_history.received_contacts.all()
        except AttributeError:
            return []

    @property
    def previous_impressions_of_me(self):
        """Gets queryset of first impressions written on previous"""
        return FirstContact.objects.filter(to_account__in=self.previous_history)

    @property
    def public_impressions_of_me(self):
        """Gets queryset of non-private impressions_of_me"""
        try:
            return self.impressions_of_me.filter(private=False).order_by(
                "from_account__entry__character__db_key"
            )
        except AttributeError:
            return []

    @property
    def impressions_for_all(self):
        """Public impressions that both the writer and receiver have signed off on sharing"""
        try:
            return self.public_impressions_of_me.filter(
                writer_share=True, receiver_share=True
            )
        except AttributeError:
            return []

    def get_impressions_str(self, player=None, previous=False):
        """Returns string display of first impressions"""
        if previous:
            qs = self.previous_impressions_of_me.filter(private=False)
        else:
            qs = self.impressions_of_me.filter(private=False)
        if player:
            qs = qs.filter(from_account__entry__player=player)

        def public_str(obj):
            """Returns markup of the first impression based on its visibility"""
            if obj.viewable_by_all:
                return "{w(Shared by Both){n"
            if obj.writer_share:
                return "{w(Marked Public by Writer){n"
            if obj.receiver_share:
                return "{w(Marked Public by You){n"
            return "{w(Private){n"

        return "\n\n".join(
            "{c%s{n wrote %s: %s" % (ob.writer, public_str(ob), ob.summary) for ob in qs
        )

    @property
    def known_tags(self):
        """Returns a queryset of our collection of tags."""
        dompc = self.player.Dominion
        clu_q = Q(clues__in=self.clues.all())
        rev_q = Q(revelations__in=self.revelations.all())
        plot_q = Q(plots__in=dompc.active_plots)
        beat_q = Q(plot_updates__plot__in=dompc.active_plots)
        act_q = Q(actions__in=self.player.participated_actions)
        evnt_q = Q(events__dompcs=dompc) | Q(events__orgs__in=dompc.current_orgs)
        flas_q = Q(plot_updates__flashbacks__in=self.flashbacks.all())
        obj_q = Q(game_objects__db_location=self.character)
        qs = SearchTag.objects.filter(
            clu_q | rev_q | plot_q | beat_q | act_q | evnt_q | flas_q | obj_q
        )
        return qs.distinct().order_by("name")

    def display_tagged_objects(self, tag):
        """
        Returns a string listing tagged objects sorted by class, or empty string.
            Args:
                tag: SearchTag object
        """
        from server.utils.arx_utils import qslist_to_string
        from world.dominion.models import RPEvent
        from world.dominion.plots.models import PlotUpdate
        from web.helpdesk.models import KBItem, KBCategory

        dompc = self.player.Dominion
        querysets = []
        # knowledge base categories & items:
        querysets.append(KBCategory.objects.filter(search_tags=tag))
        querysets.append(KBItem.objects.filter(search_tags=tag))
        # append clues/revelations we know:
        for related_name in ("clues", "revelations"):
            querysets.append(getattr(self, related_name).filter(search_tags=tag))
        # append our plots:
        querysets.append(dompc.active_plots.filter(search_tags=tag))
        all_beats = PlotUpdate.objects.filter(search_tags=tag)  # ALL tagged beats
        # append our beats~
        querysets.append(all_beats.filter(plot__in=dompc.active_plots))
        # append beat-attached experiences we were part of, but don't have plot access to~
        # actions:
        querysets.append(self.player.participated_actions.filter(search_tags=tag))
        # events:
        querysets.append(
            RPEvent.objects.filter(
                Q(search_tags=tag) & (Q(dompcs=dompc) | Q(orgs__in=dompc.current_orgs))
            )
        )
        # flashbacks:
        querysets.append(self.flashbacks.filter(beat__in=all_beats))
        # append our tagged inventory items:
        querysets.append(
            self.character.locations_set.filter(search_tags=tag).order_by(
                "db_typeclass_path"
            )
        )
        msg = qslist_to_string(querysets)
        if msg:
            msg = ("|wTagged as '|235%s|w':|n" % tag) + msg
        return msg

    def save(self, *args, **kwargs):
        """check if a database lock during profile_picture setting has put us in invalid state"""
        if self.profile_picture and not self.profile_picture.pk:
            print("Error: RosterEntry %s had invalid profile_picture." % self)
            # noinspection PyBroadException
            try:
                self.profile_picture.save()
            except Exception:
                print("Error when attempting to save it:")
                traceback.print_exc()
            else:
                print("Saved profile_picture successfully.")
            # if profile_picture's pk is still invalid we'll just clear it out to super().save won't ValueError
            if not self.profile_picture.pk:
                print("profile_picture has no pk, clearing it.")
                self.profile_picture = None
        return super(RosterEntry, self).save(*args, **kwargs)

    @property
    def max_action_points(self):
        """Maximum action points we're allowed"""
        return 300

    @property
    def action_point_regen(self):
        """How many action points we get back in a week."""
        return 150 + self.action_point_regen_modifier

    @CachedProperty
    def action_point_regen_modifier(self):
        """AP penalty from our number of fealties"""
        from world.dominion.plots.models import PlotAction, PlotActionAssistant

        ap_mod = 0
        # they lose 10 AP per fealty they're in
        try:
            ap_mod -= 10 * self.player.Dominion.num_fealties
        except AttributeError:
            pass
        # gain 20 AP for not having an investigation
        if not self.investigations.filter(active=True).exists():
            ap_mod += 20
        # gain 20 AP per unused action, 40 max
        try:
            unused_actions = (
                PlotAction.max_requests - self.player.Dominion.recent_actions.count()
            )
            ap_mod += 20 * unused_actions
        except AttributeError:
            pass
        # gain 5 AP per unused assist, 20 max
        try:
            unused_assists = (
                PlotActionAssistant.MAX_ASSISTS
                - self.player.Dominion.recent_assists.count()
            )
            ap_mod += 5 * unused_assists
        except AttributeError:
            pass
        return ap_mod

    @classmethod
    def clear_ap_cache_in_cached_instances(cls):
        """Invalidate cached_ap_penalty in all cached RosterEntries when Fealty chain changes. Won't happen often."""
        for instance in cls.get_all_cached_instances():
            delattr(instance, "action_point_regen_modifier")


class Story(SharedMemoryModel):
    """An overall storyline for the game. It can be divided into chapters, which have their own episodes."""

    current_chapter = models.OneToOneField(
        "Chapter",
        related_name="current_chapter_story",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        db_index=True,
    )
    name = models.CharField(blank=True, null=True, max_length=255, db_index=True)
    synopsis = models.TextField(blank=True, null=True)
    season = models.PositiveSmallIntegerField(default=0, blank=0)
    start_date = models.DateTimeField(blank=True, null=True)
    end_date = models.DateTimeField(blank=True, null=True)

    class Meta:
        """Define Django meta options"""

        verbose_name_plural = "Stories"

    def __str__(self):
        return self.name or "Story object"


class Chapter(SharedMemoryModel):
    """
    A chapter in a given story. This will typically be the most used demarcation for a narrative, as episodes
    tend to be brief, while stories are very long.
    """

    name = models.CharField(blank=True, null=True, max_length=255, db_index=True)
    synopsis = models.TextField(blank=True, null=True)
    story = models.ForeignKey(
        "Story",
        blank=True,
        null=True,
        db_index=True,
        on_delete=models.SET_NULL,
        related_name="previous_chapters",
    )
    start_date = models.DateTimeField(blank=True, null=True)
    end_date = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return self.name or "Chapter object"

    @property
    def public_crises(self):
        """Crises that everyone knows about, so will show up on the webpage"""
        return self.crises.filter(public=True)

    def crises_viewable_by_user(self, user):
        """Returns crises that aren't public that user can see."""
        if not user or not user.is_authenticated:
            return self.public_crises
        if user.is_staff or user.check_permstring("builders"):
            return self.crises.all()
        return self.crises.filter(
            Q(public=True) | Q(required_clue__in=user.roster.clues.all())
        )


class Episode(SharedMemoryModel):
    """
    A brief episode. The teeniest bit of story. Originally I intended these to be holders for one-off events,
    but they more or less became used as dividers for chapters, which is fine.
    """

    name = models.CharField(blank=True, null=True, max_length=255, db_index=True)
    chapter = models.ForeignKey(
        "Chapter",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="episodes",
        db_index=True,
    )
    synopsis = models.TextField(blank=True, null=True)
    gm_notes = models.TextField(blank=True, null=True)
    date = models.DateTimeField(blank=True, null=True, db_index=True)

    def __str__(self):
        return self.name or "Episode object"

    @property
    def public_crisis_updates(self):
        """
        Updates for a crisis that happened during this episode. Display them along with emits to create a
        history of what happened during the episode.
        """
        from world.dominion.models import Plot

        return self.plot_updates.filter(plot__usage=Plot.CRISIS).filter(
            plot__public=True
        )

    def get_viewable_crisis_updates_for_player(self, player):
        """Returns non-public crisis updates that the player can see."""
        from world.dominion.models import Plot

        if not player or not player.is_authenticated:
            return self.public_crisis_updates
        if player.is_staff or player.check_permstring("builders"):
            return self.plot_updates.all()
        return (
            self.plot_updates.filter(plot__usage=Plot.CRISIS)
            .filter(
                Q(plot__public=True)
                | Q(plot__required_clue__in=player.roster.clues.all())
            )
            .distinct()
        )

    def get_viewable_emits_for_player(self, player):
        """Returns emits viewable for a given player"""
        if not player or not player.is_authenticated:
            return self.emits.filter(orgs__isnull=True).distinct()
        elif player.is_staff or player.check_permstring("builders"):
            return self.emits.all()
        orgs = player.Dominion.current_orgs
        return self.emits.filter(Q(orgs__isnull=True) | Q(orgs__in=orgs)).distinct()


class StoryEmit(SharedMemoryModel):
    """
    A story emit is a short blurb written by GMs to show something that happened. Along with crisis updates, this
    more or less creates the history for the game world.
    """

    # chapter only used if we're not specifically attached to some episode
    chapter = models.ForeignKey(
        "Chapter",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="emits",
    )
    episode = models.ForeignKey(
        "Episode",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="emits",
    )
    text = models.TextField(blank=True, null=True)
    date = models.DateTimeField(auto_now_add=True)
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="emits",
    )
    orgs = models.ManyToManyField(
        "dominion.Organization", blank=True, related_name="emits"
    )
    search_tags = models.ManyToManyField("SearchTag", blank=True, related_name="emits")
    beat = models.ForeignKey(
        "dominion.PlotUpdate",
        blank=True,
        null=True,
        related_name="emits",
        on_delete=models.SET_NULL,
    )

    def __str__(self):
        return "StoryEmit #%d" % self.id

    def broadcast(self):
        """Broadcast a storyemit either to orgs or to the game as a whole"""
        orgs = self.orgs.all()
        if not orgs:
            from server.utils.arx_utils import broadcast_msg_and_post

            broadcast_msg_and_post(
                self.text, self.sender, episode_name=str(self.episode or "")
            )
        else:
            for org in orgs:
                org.gemit_to_org(self)


class Milestone(SharedMemoryModel):
    """
    Major events in a character's life. Not used that much yet, GMs have set a few by hand. We'll expand this
    later in order to create a more robust/detailed timeline for a character's story arc.
    """

    protagonist = models.ForeignKey(
        "RosterEntry", related_name="milestones", on_delete=models.CASCADE
    )
    name = models.CharField(blank=True, null=True, max_length=255)
    synopsis = models.TextField(blank=True, null=True)
    chapter = models.ForeignKey(
        "Chapter",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="milestones",
    )
    episode = models.ForeignKey(
        "Episode",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="milestones",
    )
    secret = models.BooleanField(default=False, null=False)
    image = models.ForeignKey(
        "Photo",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="milestones",
    )
    gm_notes = models.TextField(blank=True, null=True)
    participants = models.ManyToManyField(
        "RosterEntry", through="Participant", blank=True
    )
    importance = models.PositiveSmallIntegerField(default=0, blank=0)

    def __str__(self):
        return "%s - %s" % (self.protagonist, self.name)


class Participant(SharedMemoryModel):
    """Participant in a milestone."""

    milestone = models.ForeignKey("Milestone", on_delete=models.CASCADE)
    character = models.ForeignKey("RosterEntry", on_delete=models.CASCADE)
    xp_earned = models.PositiveSmallIntegerField(default=0, blank=0)
    karma_earned = models.PositiveSmallIntegerField(default=0, blank=0)
    gm_notes = models.TextField(blank=True, null=True)


class Comment(SharedMemoryModel):
    """Comment upon a milestone, written by someone involved."""

    poster = models.ForeignKey(
        "RosterEntry", related_name="comments", on_delete=models.CASCADE
    )
    target = models.ForeignKey(
        "RosterEntry",
        related_name="comments_upon",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )
    text = models.TextField(blank=True, null=True)
    date = models.DateTimeField(auto_now_add=True)
    gamedate = models.CharField(blank=True, null=True, max_length=80)
    reply_to = models.ForeignKey(
        "self", blank=True, null=True, on_delete=models.CASCADE
    )
    milestone = models.ForeignKey(
        "Milestone",
        blank=True,
        null=True,
        related_name="comments",
        on_delete=models.CASCADE,
    )


class PlayerAccount(SharedMemoryModel):
    """
    This is used to represent a player, who might be playing one or more RosterEntries. They're uniquely identified
    by their email address. Karma is for any OOC goodwill they've built up over time. Not currently used. YET.
    """

    email = models.EmailField(unique=True)
    karma = models.PositiveSmallIntegerField(default=0, blank=0)
    gm_notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return str(self.email)

    @property
    def total_xp(self):
        """Total xp they've earned over all time"""
        qs = self.accounthistory_set.all()
        return sum(ob.xp_earned for ob in qs)


class PlayerSiteEntry(SharedMemoryModel):

    account = models.ForeignKey(
        PlayerAccount, related_name="addresses", on_delete=models.CASCADE
    )
    address = models.CharField(blank=True, null=True, max_length=255)
    last_seen = models.DateTimeField(blank=True, null=True)

    class Meta:
        verbose_name_plural = "Site Entries"

    @classmethod
    def add_site_for_player(cls, player, site):
        entries = AccountHistory.objects.filter(
            entry__character=player, end_date__isnull=True
        )
        if entries.count() == 0 or entries.count() > 1:
            return

        account = entries[0].account

        try:
            entry = PlayerSiteEntry.objects.get(account=account, address=site)
        except PlayerSiteEntry.DoesNotExist:
            entry = PlayerSiteEntry(account=account, address=site)

        entry.last_seen = date.today()
        entry.save()


class PlayerInfoEntry(SharedMemoryModel):
    """
    This is used to reference any event that we'd like to have a record of, tied to a given
    PlayerAccount.
    """

    INFO = 0
    RULING = 1
    PRAISE = 2
    CRITICISM = 3

    entry_types = (
        (INFO, "Info"),
        (RULING, "Ruling"),
        (PRAISE, "Praise"),
        (CRITICISM, "Criticism"),
    )

    account = models.ForeignKey(
        PlayerAccount, related_name="entries", on_delete=models.CASCADE
    )
    entry_type = models.PositiveSmallIntegerField(choices=entry_types, default=INFO)
    entry_date = models.DateTimeField(blank=True, null=True)
    text = models.TextField(blank=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="+",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )

    class Meta:
        verbose_name_plural = "Info Entries"

    @property
    def type_name(self):
        for type_entry in self.__class__.entry_types:
            if type_entry[0] == self.entry_type:
                return type_entry[1]

        return "Unknown"

    @classmethod
    def type_for_name(cls, entry_type):
        entry_type = entry_type.lower()
        for type_entry in cls.entry_types:
            if type_entry[1].lower() == entry_type:
                return type_entry[0]

        return None

    @classmethod
    def valid_types(cls):
        return [et[1] for et in cls.entry_types]


class AccountHistory(SharedMemoryModel):
    """Record of a PlayerAccount playing an individual character."""

    account = models.ForeignKey(
        "PlayerAccount", db_index=True, on_delete=models.CASCADE
    )
    entry = models.ForeignKey("RosterEntry", db_index=True, on_delete=models.CASCADE)
    xp_earned = models.SmallIntegerField(default=0, blank=0)
    gm_notes = models.TextField(blank=True, null=True)
    start_date = models.DateTimeField(blank=True, null=True, db_index=True)
    end_date = models.DateTimeField(blank=True, null=True, db_index=True)
    contacts = models.ManyToManyField(
        "self",
        blank=True,
        through="FirstContact",
        related_name="contacted_by",
        symmetrical=False,
    )
    objects = AccountHistoryManager()

    class Meta:
        verbose_name_plural = "Played Characters"
        verbose_name = "Played Character"

    def __str__(self):
        start = ""
        end = ""
        if self.start_date:
            start = self.start_date.strftime("%x")
        if self.end_date:
            end = self.end_date.strftime("%x")
        return "%s playing %s from %s to %s" % (self.account, self.entry, start, end)


class FirstContact(SharedMemoryModel):
    """
    Shows someone's first impression of an iteration of a RosterEntry played by someone. So we point to
    AccountHistory objects rather than RosterEntries, to let people set their impression of a player's take on
    the character.
    """

    from_account = models.ForeignKey(
        "AccountHistory",
        related_name="initiated_contacts",
        db_index=True,
        on_delete=models.CASCADE,
    )
    to_account = models.ForeignKey(
        "AccountHistory",
        related_name="received_contacts",
        db_index=True,
        on_delete=models.CASCADE,
    )
    summary = models.TextField(blank=True)
    private = models.BooleanField(default=False)
    writer_share = models.BooleanField(default=False)
    receiver_share = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "First Impressions"

    def __str__(self):
        try:
            return "%s to %s" % (self.writer, self.receiver)
        except AttributeError:
            return "%s to %s" % (self.from_account, self.to_account)

    @property
    def writer(self):
        """The RosterEntry of the writer"""
        return self.from_account.entry

    @property
    def receiver(self):
        """RosterEntry of the receiver"""
        return self.to_account.entry

    @property
    def viewable_by_all(self):
        """Whether everyone can see this"""
        return self.writer_share and self.receiver_share


class RPScene(SharedMemoryModel):
    """
    Player-uploaded, non-GM'd scenes, for them posting logs and the like.
    Log is saved in just a textfield rather than going through the trouble
    of sanitizing an uploaded and stored text file.
    """

    character = models.ForeignKey(
        "RosterEntry", related_name="logs", on_delete=models.CASCADE
    )
    title = models.CharField("title of the scene", max_length=80)
    synopsis = models.TextField("Description of the scene written by player")
    date = models.DateTimeField(blank=True, null=True)
    log = models.TextField("Text log of the scene")
    lock_storage = models.TextField(
        "locks", blank=True, help_text="defined in setup_utils"
    )
    milestone = models.OneToOneField(
        "Milestone",
        related_name="log",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
    )

    def __init__(self, *args, **kwargs):
        super(RPScene, self).__init__(*args, **kwargs)
        self.locks = LockHandler(self)

    class Meta:
        """Define Django meta options"""

        verbose_name_plural = "RP Scenes"

    def __str__(self):
        return self.title

    def access(self, accessing_obj, access_type="show_hidden", default=False):
        """
        Determines if another object has permission to access.
        accessing_obj - object trying to access this one
        access_type - type of access sought
        default - what to return if no lock of access_type was found
        """
        return self.locks.check(accessing_obj, access_type=access_type, default=default)


class AbstractPlayerAllocations(SharedMemoryModel):
    """Mixin for resources/stats used for an in-game activity."""

    UNSET_ROLL = -9999
    topic = models.CharField(
        blank=True, max_length=255, help_text="Keywords or tldr or title"
    )
    actions = models.TextField(
        blank=True,
        help_text="The writeup the player submits of their actions, used for GMing.",
    )
    stat_used = models.CharField(
        blank=True,
        max_length=80,
        default="perception",
        help_text="The stat the player chose to use",
    )
    skill_used = models.CharField(
        blank=True,
        max_length=80,
        default="investigation",
        help_text="The skill the player chose to use",
    )
    silver = models.PositiveSmallIntegerField(
        default=0, blank=0, help_text="Additional silver added by the player"
    )
    economic = models.PositiveSmallIntegerField(
        default=0,
        blank=0,
        help_text="Additional economic resources added by the player",
    )
    military = models.PositiveSmallIntegerField(
        default=0,
        blank=0,
        help_text="Additional military resources added by the player",
    )
    social = models.PositiveSmallIntegerField(
        default=0, blank=0, help_text="Additional social resources added by the player"
    )
    action_points = models.PositiveSmallIntegerField(
        default=0,
        blank=0,
        help_text="How many action points spent by player/assistants.",
    )
    roll = models.SmallIntegerField(
        default=UNSET_ROLL, blank=True, help_text="Current dice roll"
    )

    class Meta:
        abstract = True

    @property
    def roll_is_set(self):
        """
        Whether our roll is currently a valid value. Could have used null/None, but I prefer being more explicit
        rather than risking errors of 'if not roll' when it's 0 rather than None. And if you're going to check
        'if roll is None' then why not just check a constant anyway?
        """
        return self.roll != self.UNSET_ROLL

    @property
    def roll_string(self):
        """Returns a string representation of our roll"""
        if self.roll_is_set:
            return str(self.roll)
        return "No roll"


class Mystery(SharedMemoryModel):
    """One of the big mysteries of the game. Kind of used as a category for revelations."""

    name = models.CharField(max_length=255, db_index=True)
    desc = models.TextField(
        "Description",
        help_text="A summary of the lore of revelations for this category",
        blank=True,
    )
    category = models.CharField(
        help_text="Type of mystery this is - ability-related, metaplot, etc",
        max_length=80,
        blank=True,
    )

    class Meta:
        verbose_name_plural = "Mysteries"

    def __str__(self):
        return self.name


class Revelation(SharedMemoryModel):
    """A major piece of lore that can be discovered by players. Clues make up pieces of it."""

    name = models.CharField(max_length=255, blank=True, db_index=True)
    desc = models.TextField(
        "Description",
        help_text="Description of the revelation given to the player",
        blank=True,
    )
    gm_notes = models.TextField(help_text="OOC Notes about this topic", blank=True)
    mysteries = models.ManyToManyField(
        "Mystery",
        blank=True,
        related_name="revelations",
        help_text="Categories of revelations with summaries",
    )

    required_clue_value = models.PositiveSmallIntegerField(
        default=0, blank=0, help_text="The total value of clues to trigger this"
    )

    red_herring = models.BooleanField(
        default=False, help_text="Whether this revelation is totally fake"
    )
    characters = models.ManyToManyField(
        "RosterEntry",
        blank=True,
        through="RevelationDiscovery",
        through_fields=("revelation", "character"),
        db_index=True,
        related_name="revelations",
    )
    author = models.ForeignKey(
        "RosterEntry",
        blank=True,
        null=True,
        related_name="revelations_written",
        on_delete=models.CASCADE,
    )
    plots = models.ManyToManyField(
        "dominion.Plot",
        blank=True,
        through="RevelationPlotInvolvement",
        related_name="revelations",
    )
    search_tags = models.ManyToManyField(
        "SearchTag", blank=True, related_name="revelations"
    )

    def __str__(self):
        return self.name

    @property
    def total_clue_value(self):
        """Total value of the clues used for this revelation"""
        return sum(ob.rating for ob in self.clues.all())

    @property
    def requires(self):
        """String representation of amount required compared to available clue points"""
        return "%d of %d" % (self.required_clue_value, self.total_clue_value)

    def player_can_discover(self, char):
        """Check whether they can discover the revelation"""
        # check if they're missing any required clues
        if (
            self.clues.filter(usage__required_for_revelation=True)
            .exclude(id__in=char.clues.all())
            .exists()
        ):
            return False
        # check if we have enough numerical value of clues to pass
        if self.check_progress(char) >= self.required_clue_value:
            return True
        return False

    def check_progress(self, char):
        """
        Returns the total value of the clues used for this revelation by
        char.
        """
        return sum(ob.rating for ob in char.clues.filter(revelations=self))

    def display(self):
        """Text display for Revelation"""
        msg = self.name + "\n"
        msg += self.desc + "\n"
        return msg


class RevelationPlotInvolvement(SharedMemoryModel):
    """How a revelation is related to a plot"""

    revelation = models.ForeignKey(
        "Revelation", related_name="plot_involvement", on_delete=models.CASCADE
    )
    plot = models.ForeignKey(
        "dominion.Plot", related_name="revelation_involvement", on_delete=models.CASCADE
    )
    gm_notes = models.TextField(blank=True)

    class Meta:
        unique_together = ("revelation", "plot")


class Clue(SharedMemoryModel):
    """A significant discovery by a player that points their character toward a Revelation, if it's not fake."""

    GAME_LORE, VISION, CHARACTER_SECRET = 0, 1, 2
    CLUE_TYPE_CHOICES = (
        (GAME_LORE, "Game Lore"),
        (VISION, "Vision"),
        (CHARACTER_SECRET, "Character Secret"),
    )
    name = models.CharField(max_length=255, blank=True, db_index=True)
    clue_type = models.PositiveSmallIntegerField(
        choices=CLUE_TYPE_CHOICES, default=GAME_LORE
    )
    rating = models.PositiveSmallIntegerField(
        default=0, blank=0, help_text="Value required to get this clue", db_index=True
    )
    desc = models.TextField(
        "Description",
        help_text="Description of the clue given to the player",
        blank=True,
    )
    gm_notes = models.TextField(
        "GM Notes",
        help_text="Notes visible only to staff/GMs about this clue",
        blank=True,
    )
    revelations = models.ManyToManyField(
        "Revelation", through="ClueForRevelation", blank=True, related_name="clues"
    )
    plots = models.ManyToManyField(
        "dominion.Plot", through="CluePlotInvolvement", blank=True, related_name="clues"
    )
    tangible_object = models.ForeignKey(
        "objects.ObjectDB",
        blank=True,
        null=True,
        related_name="clues",
        help_text="An in-game object that this Clue is a secret or backstory for",
        on_delete=models.SET_NULL,
    )
    characters = models.ManyToManyField(
        "RosterEntry",
        blank=True,
        through="ClueDiscovery",
        db_index=True,
        through_fields=("clue", "character"),
        related_name="clues",
    )
    red_herring = models.BooleanField(
        default=False, help_text="Whether this revelation is totally fake"
    )
    allow_investigation = models.BooleanField(
        default=False, help_text="Can be gained through investigation rolls"
    )
    allow_exploration = models.BooleanField(
        default=False, help_text="Can be gained through exploration rolls"
    )
    allow_trauma = models.BooleanField(
        default=False, help_text="Can be gained through combat rolls"
    )
    allow_sharing = models.BooleanField(default=True, help_text="Can be shared")
    search_tags = models.ManyToManyField(
        "SearchTag", blank=True, db_index=True, related_name="clues"
    )
    author = models.ForeignKey(
        "RosterEntry",
        blank=True,
        null=True,
        related_name="clues_written",
        on_delete=models.CASCADE,
    )

    def __str__(self):
        return self.name

    @CachedProperty
    def keywords(self):
        """List of keywords from our search tags. We use them for auto-matching clues with investigations."""
        return [ob.name for ob in self.search_tags.all().distinct()]

    def display(self, show_gm_notes=False, disco_msg=""):
        """String display for clue"""
        msg = "|w[|c%s|w]|n (%s Rating)" % (self.name, self.rating)
        tags = self.search_tags.all()
        if tags:
            msg += " |wTags:|n %s" % ", ".join(("|235%s|n" % ob) for ob in tags)
        msg += "\n%s\n" % self.desc
        if disco_msg:
            msg += disco_msg
        if show_gm_notes and self.gm_notes:
            msg += "\n{wGM Notes:{n %s\n" % self.gm_notes
        return msg

    @property
    def recruiters(self):
        """Recruiters for a plot that this clue acts as a hook/grants access to"""
        from world.dominion.models import PCPlotInvolvement

        access = (CluePlotInvolvement.HOOKED, CluePlotInvolvement.GRANTED)
        plots = self.plots.filter(clue_involvement__access__in=access)
        qs = PCPlotInvolvement.objects.filter(
            plot__in=plots, admin_status__gte=PCPlotInvolvement.RECRUITER
        )
        return qs.exclude(recruiter_story="")

    def determine_discovery_multiplier(self):
        """Calculates a multiplier for investigations' completion_value based on number of discoveries"""
        avg = (
            Clue.objects.filter(allow_investigation=True)
            .annotate(cnt=Count("discoveries"))
            .aggregate(avg=Avg("cnt"))
        )
        discos = self.discoveries.count() + 0.5
        return avg["avg"] / discos

    def get_completion_value(self):
        """Gets the default/suggested completion value for an investigation into this clue."""
        value = int(self.rating * self.determine_discovery_multiplier())
        if value < 1:
            value = 1
        return value

    def save(self, *args, **kwargs):
        """Save and then update all investigations that point to us"""
        super(Clue, self).save(*args, **kwargs)
        ongoing = self.investigation_set.filter(ongoing=True)
        if ongoing:
            value = self.get_completion_value()
            # make sure investigations have the correct completion value for this clue
            for investigation in ongoing:
                if investigation.completion_value != value:
                    investigation.completion_value = value
                    investigation.save()


class CluePlotInvolvement(SharedMemoryModel):
    """How a clue is related to a plot"""

    clue = models.ForeignKey(
        "Clue", related_name="plot_involvement", on_delete=models.CASCADE
    )
    plot = models.ForeignKey(
        "dominion.Plot", related_name="clue_involvement", on_delete=models.CASCADE
    )
    gm_notes = models.TextField(blank=True)
    NEUTRAL, HOOKED, GRANTED = range(3)
    ACCESS_CHOICES = ((NEUTRAL, "Neutral"), (HOOKED, "Hooked"), (GRANTED, "Granted"))
    access = models.PositiveSmallIntegerField(choices=ACCESS_CHOICES, default=NEUTRAL)

    class Meta:
        unique_together = ("clue", "plot")


class SearchTag(SharedMemoryModel):
    """Tags for Clues that are used for automatching investigations to them."""

    name = models.CharField(max_length=255, unique=True)
    game_objects = models.ManyToManyField(
        "objects.ObjectDB", blank=True, related_name="search_tags"
    )

    def __str__(self):
        return self.name

    def display_tagged_objects(self):
        """Returns a string listing all tagged objects sorted by their class, or empty string."""
        msg = ""
        querysets = [self.game_objects.all().order_by("db_typeclass_path")]
        for related_name in ("emits", "clues", "revelations", "plots", "plot_updates"):
            querysets.append(getattr(self, related_name).all())
        querysets = [ob for ob in querysets if len(ob) > 0]

        def get_obj_str(obj):
            return "%s (#%s)" % (str(obj), obj.id)

        def get_queryset_str(qset):
            """
            Gets a string representation of the queryset. We check the class name for each object in the
            queryset because typeclasses will have different class names, and we want to simulate that being
            a different type of match.
            """
            class_name = None
            message = ""
            sep = ""
            for obj in qset:
                # noinspection PyProtectedMember
                plural_name = obj._meta.verbose_name_plural
                if plural_name != class_name:
                    class_name = plural_name
                    message += "\n|w[%s]|n " % class_name.title()
                    sep = ""
                message += sep + get_obj_str(obj)
                sep = "; "
            return message

        if querysets:
            msg = "|wTagged as '|235%s|w':|n" % self
            for qs in querysets:
                msg += get_queryset_str(qs)
        return msg


class RevelationDiscovery(SharedMemoryModel):
    """Through model used to record when a character discovers a revelation."""

    character = models.ForeignKey(
        "RosterEntry",
        related_name="revelation_discoveries",
        db_index=True,
        on_delete=models.CASCADE,
    )
    revelation = models.ForeignKey(
        "Revelation",
        related_name="discoveries",
        db_index=True,
        on_delete=models.CASCADE,
    )
    investigation = models.ForeignKey(
        "Investigation",
        blank=True,
        null=True,
        related_name="revelations",
        on_delete=models.CASCADE,
    )
    message = models.TextField(
        blank=True,
        help_text="Message for the player's records about how they discovered this.",
    )
    date = models.DateTimeField(blank=True, null=True)
    milestone = models.OneToOneField(
        "Milestone",
        related_name="revelation",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )
    discovery_method = models.CharField(
        help_text="How this was discovered - exploration, trauma, etc", max_length=255
    )
    revealed_by = models.ForeignKey(
        "RosterEntry",
        related_name="revelations_spoiled",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )

    class Meta:
        unique_together = ("character", "revelation")
        verbose_name_plural = "Revelation Discoveries"

    def __str__(self):
        return "%s's discovery of %s" % (self.character, self.revelation)

    def display(self):
        """Returns string display for the revelation."""
        msg = self.revelation.display()
        if self.message:
            msg += "\n" + self.message
        return msg

    def check_node_discovery(self):
        from world.magic.models import Practitioner, SkillNodeResonance

        msg = ""
        nodes = self.revelation.nodes.all()
        if nodes:
            practitioner, _ = Practitioner.objects.get_or_create(
                character=self.character.character
            )
            known_nodes = practitioner.nodes.all()
            nodes = [ob for ob in nodes if ob not in known_nodes]
            for node in nodes:
                practitioner.open_node(node, reason=SkillNodeResonance.LEARN_DISCOVERED)
                msg += (
                    "\nYou have unlocked a node from learning this revelation: %s"
                    % node
                )
        return msg


class ClueDiscovery(SharedMemoryModel):
    """Through model that represents knowing/progress towards discovering a clue."""

    clue = models.ForeignKey(
        "Clue", related_name="discoveries", db_index=True, on_delete=models.CASCADE
    )
    character = models.ForeignKey(
        "RosterEntry",
        related_name="clue_discoveries",
        db_index=True,
        on_delete=models.CASCADE,
    )
    investigation = models.ForeignKey(
        "Investigation",
        blank=True,
        null=True,
        related_name="clue_discoveries",
        db_index=True,
        on_delete=models.CASCADE,
    )
    message = models.TextField(
        blank=True,
        help_text="Message for the player's records about how they discovered this.",
    )
    date = models.DateTimeField(blank=True, null=True)
    milestone = models.OneToOneField(
        "Milestone",
        related_name="clue",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )
    discovery_method = models.CharField(
        help_text="How this was discovered - exploration, trauma, etc",
        blank=True,
        max_length=255,
    )
    revealed_by = models.ForeignKey(
        "RosterEntry",
        related_name="clues_spoiled",
        blank=True,
        null=True,
        db_index=True,
        on_delete=models.CASCADE,
    )

    class Meta:
        verbose_name_plural = "Clue Discoveries"
        unique_together = ("clue", "character")

    @property
    def name(self):
        """Returns the name of the clue we're discovering"""
        return self.clue.name

    def display(self, show_sharing=False, show_gm_notes=False):
        """Returns a string showing that we're not yet done, or the completed clue discovery."""
        msg = ""
        if self.message:
            if self.date:
                msg += self.date.strftime("%x %X") + " "
            msg += self.message + "\n"
        if show_sharing:
            shared = self.shared_with
            if shared:
                msg += "\n{wShared with{n: %s" % ", ".join(str(ob) for ob in shared)
        return self.clue.display(show_gm_notes=show_gm_notes, disco_msg=msg)

    def check_revelation_discovery(self):
        """
        If this Clue discovery means that the character now has every clue
        for the revelation, we award it to them.
        """
        # find all ClueForRevelations used for this discovery
        clue_usage = self.clue.usage.all()
        # get the associated revelations the player doesn't yet have
        revelations = Revelation.objects.filter(
            Q(clues_used__in=clue_usage) & ~Q(characters=self.character)
        ).distinct()
        discovered = []
        for rev in revelations:
            if rev.player_can_discover(self.character):
                discovered.append(rev)
        return discovered

    def __str__(self):
        return "%s's discovery of %s" % (self.character, self.clue)

    def mark_discovered(
        self,
        method="Prior Knowledge",
        message="",
        revealed_by=None,
        investigation=None,
        inform_creator=None,
    ):
        """
        Discovers the clue for our character.

        Args:
            method: String describing how the clue was discovered.
            message: Additional message saying how it was discovered, stored in self.message
            revealed_by: If the clue was shared by someone else, we store their RosterEntry
            investigation: If it was from an investigation, we mark that also.
            inform_creator: Object used for bulk creation of informs
        """
        from world.magic.models import Practitioner, PractitionerSpell

        date_now = datetime.now()
        self.date = date_now
        self.discovery_method = method
        self.message = message
        self.revealed_by = revealed_by
        self.investigation = investigation
        self.save()
        revelations = self.check_revelation_discovery()
        msg = ""
        for revelation in revelations:
            msg += "\nYou have discovered a revelation: %s\n%s" % (
                str(revelation),
                revelation.desc,
            )
            message = "You had a revelation after learning a clue!"
            disco = RevelationDiscovery.objects.create(
                character=self.character,
                discovery_method=method,
                message=message,
                investigation=investigation,
                revelation=revelation,
                date=date_now,
            )
            msg += disco.check_node_discovery()
        spells = self.clue.spells.all()
        if spells:
            practitioner, _ = Practitioner.objects.get_or_create(
                character=self.character.character
            )
            known_spells = practitioner.spells.all()
            spells = [ob for ob in spells if not known_spells]
            for spell in spells:
                practitioner.learn_spell(
                    spell, reason=PractitionerSpell.LEARN_DISCOVERED
                )
                msg += (
                    "\nYou have learned a spell from discovering the clue: %s" % spell
                )
        if msg:
            if inform_creator:
                inform_creator.add_player_inform(
                    self.character.player, msg, "Discovery"
                )
            else:
                self.character.player.inform(msg, category="Discovery", append=False)
        # make sure any investigations targeting the now discovered clue get reset. queryset.update doesn't work with
        # SharedMemoryModel (cached objects will overwrite it), so we iterate through them instead
        qs = self.character.investigations.filter(clue_target=self.clue)
        if investigation:
            qs = qs.exclude(id=investigation.id)
        for snoopery in qs:
            snoopery.clue_target = None
            if snoopery.active:
                inactive_msg = (
                    "After a recent clue discovery, %s is no longer active." % snoopery
                )
                snoopery.active = False
                snoopery.refund_ap()
                self.character.player.inform(
                    inactive_msg, category="Inactive Investigation", append=False
                )
            snoopery.save()

    def share(self, entry, investigation=None, note=None, inform_creator=None):
        """
        Copy this clue to target entry. If they already have the
        discovery, we'll add our roll to theirs (which presumably should
        finish it). If not, they'll get a copy with their roll value
        equal to ours. We'll check for them getting a revelation discovery.
        """
        try:
            entry.clue_discoveries.get(clue=self.clue)
            entry.player.send_or_queue_msg(
                "%s tried to share the clue %s with you, but you already know that."
                % (self.character, self.name)
            )
            return False
        except ClueDiscovery.DoesNotExist:
            targ_clue = entry.clue_discoveries.create(clue=self.clue)
        note_msg = "."
        if note:
            note_msg = ", who noted: %s" % note
        message = "This clue was shared with you by %s%s" % (self.character, note_msg)
        targ_clue.mark_discovered(
            method="Sharing",
            message=message,
            revealed_by=self.character,
            investigation=investigation,
            inform_creator=inform_creator,
        )
        pc = targ_clue.character.player
        msg = "A new clue (%d) has been shared with you by %s!\n\n%s\n" % (
            self.clue.id,
            self.character,
            targ_clue.display(),
        )
        if inform_creator:
            inform_creator.add_player_inform(pc, msg, "Investigations")
        else:
            pc.inform(msg, category="Investigations", append=False)
        return True

    @property
    def shared_with(self):
        """Shortcut to show everyone our character shared this clue with."""
        spoiled = self.character.clues_spoiled.filter(clue=self.clue)
        return RosterEntry.objects.filter(clues__in=spoiled)

    def save(self, *args, **kwargs):
        super(ClueDiscovery, self).save(*args, **kwargs)
        if (
            self.clue
            and self.clue.tangible_object
            and hasattr(self.clue.tangible_object, "messages")
            and self.clue.clue_type == Clue.CHARACTER_SECRET
        ):
            self.clue.tangible_object.messages.build_secretslist()


class ClueForRevelation(SharedMemoryModel):
    """Through model that shows which clues are required for a revelation"""

    clue = models.ForeignKey(
        "Clue", related_name="usage", db_index=True, on_delete=models.CASCADE
    )
    revelation = models.ForeignKey(
        "Revelation", related_name="clues_used", db_index=True, on_delete=models.CASCADE
    )
    required_for_revelation = models.BooleanField(
        default=True,
        help_text="Whether this must be discovered for " + "the revelation to finish",
    )
    tier = models.PositiveSmallIntegerField(
        default=0,
        blank=0,
        help_text="How high in the hierarchy of discoveries this clue is, "
        + "lower number discovered first",
    )

    def __str__(self):
        return "Clue %s used for %s" % (self.clue, self.revelation)


class InvestigationAssistant(SharedMemoryModel):
    """Someone who is helping an investigation out. Note that char is an ObjectDB, not RosterEntry."""

    currently_helping = models.BooleanField(
        default=False, help_text="Whether they're currently helping out"
    )
    investigation = models.ForeignKey(
        "Investigation",
        related_name="assistants",
        db_index=True,
        on_delete=models.CASCADE,
    )
    char = models.ForeignKey(
        "objects.ObjectDB",
        related_name="assisted_investigations",
        db_index=True,
        on_delete=models.CASCADE,
    )
    stat_used = models.CharField(
        blank=True,
        max_length=80,
        default="perception",
        help_text="The stat the player chose to use",
    )
    skill_used = models.CharField(
        blank=True,
        max_length=80,
        default="investigation",
        help_text="The skill the player chose to use",
    )
    actions = models.TextField(
        blank=True,
        help_text="The writeup the player submits of their actions, used for GMing.",
    )

    class Meta:
        unique_together = ("char", "investigation")

    def __str__(self):
        return "%s helping: %s" % (self.char, self.investigation)

    @property
    def helper_name(self):
        """Name of the character, with their owner if they're a retainer"""
        name = self.char.key
        if hasattr(self.char, "owner"):
            name += " (%s)" % self.char.owner
        return name

    def shared_discovery(self, clue, inform_creator=None):
        """
        Shares a clue discovery with this assistant.
        Args:
            clue: The ClueDiscovery we're sharing
            inform_creator: Object used for bulk-creation of informs
        """
        self.currently_helping = False
        self.save()
        entry = self.roster_entry
        if entry:
            clue.share(
                entry, investigation=self.investigation, inform_creator=inform_creator
            )

    @property
    def roster_entry(self):
        """Gets roster entry object for either character or a retainer's owner"""
        try:
            return self.char.roster
        except AttributeError:
            # No roster entry, so we're a retainer. Try to return our owner's roster entry
            try:
                return self.char.owner.player.player.roster
            except AttributeError:
                pass


class Investigation(AbstractPlayerAllocations):
    """
    An investigation by a character or group of characters into a given topic. Typically used for discovering clues,
    but can be set to return just a message by turning automate_result to False and writing self.results manually.
    """

    character = models.ForeignKey(
        "RosterEntry",
        related_name="investigations",
        db_index=True,
        on_delete=models.CASCADE,
    )
    ongoing = models.BooleanField(
        default=True,
        help_text="Whether this investigation is finished or not",
        db_index=True,
    )
    active = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Whether this is the investigation for the"
        + " week. Only one allowed",
    )
    automate_result = models.BooleanField(
        default=True,
        help_text="Whether to generate a result during weekly "
        + "maintenance. Set false if GM'd",
    )
    results = models.TextField(
        default="You didn't find anything.",
        blank=True,
        help_text="The text to send the player, either set by GM or generated automatically "
        + "by script if automate_result is set.",
    )
    clue_target = models.ForeignKey(
        "Clue", blank=True, null=True, on_delete=models.CASCADE
    )
    progress = models.IntegerField(
        default=0, help_text="Progress made towards a discovery."
    )
    completion_value = models.IntegerField(
        default=300, help_text="Total progress needed to make a discovery."
    )

    def __str__(self):
        return "%s's investigation on %s" % (self.character, self.topic)

    def display(self):
        """Returns string display of investigation for players"""
        msg = "{wID{n: %s" % self.id
        if not self.active:
            msg += " {r(Investigation Not Currently Active){n"
        msg += "\n{wCharacter{n: %s\n" % self.character
        msg += "{wTopic{n: %s\n" % self.topic
        msg += "{wActions{n: %s\n" % self.actions
        msg += "{wModified Difficulty{n: %s\n" % self.difficulty
        msg += "{wCurrent Progress{n: %s\n" % self.progress_str
        msg += "{wStat used{n: %s\n" % self.stat_used
        msg += "{wSkill used{n: %s\n" % self.skill_used
        for assistant in self.active_assistants:
            msg += "{wAssistant:{n %s {wStat:{n %s {wSkill:{n %s {wActions:{n %s\n" % (
                assistant.helper_name,
                assistant.stat_used,
                assistant.skill_used,
                assistant.actions,
            )
        return msg

    def gm_display(self):
        """Returns string of investigation stats for GM"""
        msg = self.display()
        msg += "{wCurrent Roll{n: %s\n" % self.roll
        msg += "{wTargeted Clue{n: %s\n" % self.targeted_clue
        msg += "{wProgress Value{n: %s\n" % self.progress
        msg += "{wCompletion Value{n: %s\n" % self.completion_value
        msg += "{wComplete this week?{n: %s\n" % self.check_success()
        msg += "{wSilver Used{n: %s\n" % self.silver
        msg += "{wEconomic Used{n %s\n" % self.economic
        msg += "{wMilitary Used{n %s\n" % self.military
        msg += "{wSocial Used{n %s\n" % self.social
        msg += "{wAction Points Used{n: %s\n" % self.action_points
        return msg

    @classmethod
    def ap_cost(cls, character):
        try:
            cost = 50 - (character.traits.get_skill_value("investigation") * 5)
            if cost < 0:
                cost = 0
            return cost
        except AttributeError:
            return 50

    @property
    def char(self):
        """Character object of the RosterEntry running the investigation"""
        return self.character.character

    @property
    def active_assistants(self):
        """Assistants that are flagged as actively participating"""
        return self.assistants.filter(currently_helping=True)

    @staticmethod
    def do_obj_roll(obj, diff):
        """
        Method that takes either an investigation or one of its
        assistants and returns a dice roll based on its character,
        and the stats/skills used by that investigation or assistant.
        """
        stat = obj.stat_used or "wits"
        stat = stat.lower()
        skill = obj.skill_used or "investigation"
        skill = skill.lower()
        roll = do_dice_check(
            obj.char,
            stat_list=[stat, "perception", "intellect"],
            skill_list=[skill, "investigation"],
            difficulty=diff,
            average_skill_list=True,
        )
        return roll

    def refund_ap(self):
        ap_cost = self.ap_cost(self.char)
        self.char.player_ob.pay_action_points(-ap_cost)

    def do_roll(self, mod=0, diff=None):
        """
        Do a dice roll to return a result
        """
        diff = (diff if diff is not None else self.difficulty) + mod
        roll = self.do_obj_roll(self, diff)
        assistant_roll_total = 0
        assistants = self.active_assistants
        for ass in assistants:
            player_character_mod = 20 if ass.char.player_ob else 0
            a_roll = self.do_obj_roll(ass, diff - player_character_mod)
            if a_roll < 0:
                a_roll = 0
            if not player_character_mod:
                try:
                    ability_level = ass.char.traits.get_ability_value(
                        "investigation_assistant"
                    )
                except (AttributeError, ValueError, KeyError, TypeError):
                    ability_level = 0
                cap = ability_level * 10
                a_roll += random.randint(0, 5) * ability_level
                if a_roll > cap:
                    a_roll = cap
            assistant_roll_total += a_roll
        roll += max(assistant_roll_total, random.randint(0, 100) + len(assistants))
        roll = max(roll, random.randint(-50, 200))
        if roll > 0:
            # a successful roll adds 12% of our completion value, so around 2 months as a limit
            roll += int(self.completion_value * 0.12)
        try:
            roll = int(roll * settings.INVESTIGATION_PROGRESS_RATE)
        except (AttributeError, TypeError, ValueError):
            pass
        # newbie bonus adds an overall 0-50% increase in roll
        roll = int(roll * (1 + (self.newbie_bonus / 100.0)))
        # save the character's roll
        self.roll = roll
        self.save()
        return roll

    @property
    def resource_mod(self) -> int:
        """Difficulty modifier as an integer from silver/resources"""
        mod = 0
        silver_mod = self.silver / 2500
        if silver_mod > 20:
            silver_mod = 20
        mod += silver_mod
        res_mod = int((self.economic + self.military + self.social) / 2.5)
        if random.randint(0, 5) < (self.economic + self.military + self.social) % 5:
            res_mod += 1
        if res_mod > 60:
            res_mod = 60
        mod += res_mod
        mod += self.action_points / 5
        return int(mod)

    def get_roll(self):
        """Does a roll if we're currently not set, then returns our current roll."""
        if self.roll == self.UNSET_ROLL:
            return self.do_roll()
        return self.roll

    @property
    def difficulty(self):
        """
        Determine our difficulty based on our expenditures and the clue
        we're trying to uncover.
        """
        if not self.automate_result or not self.targeted_clue:
            base = 30  # base difficulty for things without clues
        else:
            base = self.targeted_clue.rating
        try:
            base = int(base + settings.INVESTIGATION_DIFFICULTY_MOD)
            base -= self.newbie_bonus
        except (AttributeError, ValueError, TypeError):
            pass
        return base - self.resource_mod

    @CachedProperty
    def newbie_bonus(self):
        """Bonus to reduce difficulty of the investigation for the character's first 5 investigations"""
        bonus = 60 - (10 * self.character.investigations.count())
        if bonus < 0:
            bonus = 0
        return bonus

    def check_success(self, modifier=0, diff=None):
        """
        Checks success. Modifier can be passed by a GM based on their
        discretion, but otherwise is 0. diff is passed if we don't
        want to find a targeted clue and generate our difficulty based
        on that.
        """
        roll = self.get_roll()
        if diff is not None:
            return (roll + self.progress) >= (diff + modifier)
        return (roll + self.progress) >= self.completion_value

    def process_events(self, inform_creator=None):
        """
        Called by the weekly event script to make the investigation run and reset our values,
        then notify the player.
        """
        self.generate_result(inform_creator=inform_creator)
        # reset values
        self.reset_values()
        self.char.attributes.remove("investigation_roll")
        # send along msg
        msg = (
            "Your investigation into '%s' has had the following result:\n" % self.topic
        )
        msg += self.results
        if inform_creator:
            inform_creator.add_player_inform(
                self.character.player, msg, "Investigations"
            )
        else:
            self.character.player.inform(msg, category="Investigations", append=False)

    def generate_result(self, inform_creator=None):
        """
        If we aren't GMing this, check success then set the results string
        accordingly.
        """
        if not self.automate_result:
            self.ongoing = False
            return
        if self.check_success():
            # if we don't have a valid clue, then let's
            # tell them about what a valid clue -could- be.
            if not self.targeted_clue and self.automate_result:
                self.results = "There is nothing else for you to find."
            else:
                # add a valid clue and update results string
                try:
                    disco = self.clue_discoveries.get(
                        clue=self.targeted_clue, character=self.character
                    )
                except ClueDiscovery.DoesNotExist:
                    disco = ClueDiscovery.objects.create(
                        clue=self.targeted_clue,
                        investigation=self,
                        character=self.character,
                    )
                if self.automate_result:
                    self.results = "Your investigation has discovered a clue!\n"
                self.results += disco.display()
                if self.topic and self.topic.lower().startswith("clue:"):
                    try:
                        name = self.topic.lower().lstrip("clue:").strip()
                        if name.isdigit():
                            source_clue = Clue.objects.get(id=name)
                        else:
                            source_clue = Clue.objects.get(name__iexact=name)
                        tags = [ob.id for ob in source_clue.search_tags.all()]
                        shared_tags = self.clue_target.search_tags.filter(id__in=tags)
                        if not shared_tags:
                            msg = (
                                "\nIt's not immediately clear how this relates to %s "
                                % source_clue
                            )
                            msg += ", but you found this while trying to learn more about it."
                        else:
                            from server.utils.arx_utils import list_to_string

                            msg = (
                                "\nWhile looking into %s, you found some references "
                                % source_clue
                            )
                            msg += (
                                "to '%s' that resulted in your discovery."
                                % list_to_string(list(shared_tags))
                            )
                        self.results += msg
                    except (Clue.DoesNotExist, Clue.MultipleObjectsReturned):
                        pass
                message = disco.message or "Your investigation has discovered this!"
                disco.mark_discovered(
                    method="investigation", message=message, investigation=self
                )
                # we found a clue, so this investigation is done.
                self.clue_target = None
                self.ongoing = False
                for ass in self.active_assistants:
                    # noinspection PyBroadException
                    try:
                        ass.shared_discovery(disco, inform_creator)
                    except Exception:
                        traceback.print_exc()
        else:
            # update results to indicate our failure
            self.results = "Your investigation failed to find anything."
            if self.add_progress():
                self.results += (
                    " But you feel you've made some progress in following some leads."
                )
            else:
                self.results += " None of your leads seemed to go anywhere this week."
            self.results += " To continue the investigation, set it active again."

    def reset_values(self):
        """
        Reduce the silver/resources added to this investigation.
        """
        self.active = False
        self.silver = 0
        self.economic = 0
        self.military = 0
        self.social = 0
        self.action_points = 0
        self.roll = Investigation.UNSET_ROLL
        self.save()

    def mark_active(self):
        self.active = True
        self.do_roll()
        del self.character.action_point_regen_modifier

    @property
    def targeted_clue(self):
        """Tries to fetch a clue automatically if we don't have one. Then returns what we have, or None."""
        if self.clue_target:
            return self.clue_target
        clue = self.find_target_clue()
        self.setup_investigation_for_clue(clue)
        return clue

    def setup_investigation_for_clue(self, clue):
        """Sets our completion value for the investigation based on the clue's rating"""
        if clue:
            self.clue_target = clue
            self.completion_value = clue.get_completion_value()
            self.save()

    def find_target_clue(self):
        """
        Finds a target clue based on our topic and our investigation history.
        We'll choose the lowest rating out of 3 random choices.
        """
        from .investigation import CmdInvestigate

        cmd = CmdInvestigate()
        cmd.args = self.topic
        cmd.caller = self.character.character
        try:
            search, omit, source_clue = cmd.get_tags_or_clue_from_args()
        except cmd.error_class:
            names = self.topic.split()
            search = SearchTag.objects.filter(
                reduce(lambda x, y: x | Q(name__icontains=y), names, Q())
            )
            clues = (
                Clue.objects.exclude(characters=self.character)
                .filter(search_tags__in=search)
                .annotate(cnt=Count("discoveries"))
            )
            if clues:
                picker = WeightedPicker()
                for clue in clues:
                    picker.add_option(clue, clue.cnt)
                return picker.pick()
        else:
            return get_random_clue(
                self.character,
                search_tags=search,
                omit_tags=omit,
                source_clue=source_clue,
            )

    def add_progress(self):
        """Adds progress to the investigation, saved in clue.roll"""
        if not self.targeted_clue:
            return
        roll = self.roll
        try:
            roll = int(roll)
        except (ValueError, TypeError):
            return
        if roll <= 0:
            return
        self.progress += roll
        self.save()
        return roll

    @property
    def progress_percentage(self):
        """Returns our percent towards completion as an integer."""
        try:
            return int((float(self.progress) / float(self.completion_value)) * 100)
        except (AttributeError, TypeError, ValueError, ZeroDivisionError):
            return 0

    @property
    def progress_str(self):
        """Returns a string saying how close they are to discovery."""
        progress = self.progress_percentage
        if progress <= 0:
            return "No real progress has been made to finding something new."
        if progress <= 5:
            return "You have made a very tiny amount of progress."
        if progress <= 10:
            return "You have made a tiny amount of progress."
        if progress <= 15:
            return "You have made a little bit of progress."
        if progress <= 25:
            return "You've made some progress."
        if progress <= 50:
            return "You've made a good amount of progress."
        if progress <= 75:
            return "You feel like you're getting close to finding something."
        return "You feel like you're on the verge of a breakthrough. You just need more time."


class Theory(SharedMemoryModel):
    """
    Represents a theory that a player has come up with, and is now
    stored and can be shared with others.
    """

    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="created_theories",
        blank=True,
        null=True,
        db_index=True,
        on_delete=models.CASCADE,
    )
    known_by = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="known_theories",
        blank=True,
        through="TheoryPermissions",
    )
    topic = models.CharField(max_length=255, blank=True, null=True)
    desc = models.TextField(blank=True, null=True)
    related_clues = models.ManyToManyField(
        "Clue", related_name="theories", blank=True, db_index=True
    )
    related_theories = models.ManyToManyField("self", blank=True)
    plots = models.ManyToManyField("dominion.Plot", related_name="theories", blank=True)

    class Meta:
        """Define Django meta options"""

        verbose_name_plural = "Theories"

    def __str__(self):
        return "%s's theory on %s" % (self.creator, self.topic)

    def display(self):
        """Returns string display of the theory with ansi markup"""
        msg = "\n{wCreator{n: %s\n" % self.creator
        msg += "{wCan edit:{n %s\n" % ", ".join(str(ob) for ob in self.can_edit.all())
        msg += "{wTopic{n: %s\n" % self.topic
        msg += "{wDesc{n: %s\n" % self.desc
        return msg

    def share_with(self, player):
        """Share the theory with a player."""
        permission, _ = self.theory_permissions.get_or_create(player=player)

    def forget_by(self, player):
        """Causes the player to forget the theory."""
        permission = self.theory_permissions.filter(player=player)
        permission.delete()

    def add_editor(self, player):
        """Adds the player as an editor for the theory."""
        permission, _ = self.theory_permissions.get_or_create(player=player)
        permission.can_edit = True
        permission.save()

    def remove_editor(self, player):
        """
        Removes a player as an editor if they already were one.
        Args:
            player: Player to stop being an editor
        """
        # No, you don't get to remove the creator
        if player == self.creator:
            pass

        # if they're not an editor, we don't create a theory_permission for them, since that would share theory
        try:
            permission = self.theory_permissions.get(player=player)
            permission.can_edit = False
            permission.save()
        except TheoryPermissions.DoesNotExist:
            pass

    @property
    def can_edit(self):
        """Returns queryset of who has edit permissions for the theory."""
        return self.known_by.filter(theory_permissions__can_edit=True)


class TheoryPermissions(SharedMemoryModel):
    """Through model that shows who knows the theory and whether they can edit it."""

    player = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="theory_permissions",
        on_delete=models.CASCADE,
    )
    theory = models.ForeignKey(
        "Theory", related_name="theory_permissions", on_delete=models.CASCADE
    )
    can_edit = models.BooleanField(default=False)


def get_random_clue(roster, search_tags, omit_tags=None, source_clue=None):
    """
    Finds a target clue based on our topic and our investigation history.
    We'll choose the lowest rating out of 3 random choices.
    """
    exact = Clue.objects.filter(
        Q(allow_investigation=True) & ~Q(characters=roster)
    ).exclude(name__icontains="placeholder")
    if source_clue:
        by_revelation = exact.filter(
            revelations__in=source_clue.revelations.all()
        ).annotate(cnt=Count("discoveries"))
        tags = source_clue.search_tags.all()
        if by_revelation:
            tag_ids = [ob.id for ob in tags]
            picker = WeightedPicker()
            for clue in by_revelation:
                tag_matches = clue.search_tags.filter(id__in=tag_ids).count()
                picker.add_option(clue, clue.cnt + tag_matches)
            return picker.pick()
        exact = exact.filter(search_tags__in=source_clue.search_tags.all())
    else:
        exact = reduce(lambda x, y: x.filter(search_tags=y), search_tags, exact)
        if omit_tags:
            exclude_query = reduce(lambda x, y: x | Q(search_tags=y), omit_tags, Q())
            exact = exact.exclude(exclude_query)
    if exact:
        picker = WeightedPicker()
        exact = exact.annotate(cnt=Count("discoveries"))
        for clue in exact:
            picker.add_option(clue, clue.cnt)
        return picker.pick()


class Flashback(SharedMemoryModel):
    """
    Represents a record of a scene in the past, played out via play-by-post for
    involved characters.
    """

    title = models.CharField(max_length=250, unique=True)
    summary = models.TextField(blank=True)
    participants = models.ManyToManyField(
        "RosterEntry", related_name="flashbacks", through="FlashbackInvolvement"
    )
    concluded = models.BooleanField(default=False)
    db_date_created = models.DateTimeField(blank=True, null=True)
    beat = models.ForeignKey(
        "dominion.PlotUpdate",
        blank=True,
        null=True,
        related_name="flashbacks",
        on_delete=models.SET_NULL,
    )
    MAX_XP = 3
    STRING_DIV = "\n|w%s|n" % ("-" * 70)
    STRING_MISSING_MEMORY = "Part of this tale resides in the memory of someone else."

    def __str__(self):
        return self.title

    def get_new_posts(self, entry):
        """Returns queryset of posts that roster entry hasn't read yet."""
        read = entry.flashback_post_permissions.exclude(is_read=True)
        return self.posts.filter(readable_by=entry).exclude(
            flashback_post_permissions__in=read
        )

    def display(self, display_summary_only=False, post_limit=None, reader=None):
        """
        Returns string display of a flashback.
        Args:
            display_summary_only (boolean): Whether to display posts.
            post_limit (int): How many posts to limit our display to.
            reader (Account/Player): The viewer.
        """
        wip = "" if self.concluded else " work in progress!"
        msg = "|w[%s]|n - (#%s)%s" % (self.title, self.id, wip)
        msg += "\nOwners and authors: %s" % self.owners_and_contributors
        msg += "\nSummary: %s" % self.summary
        if display_summary_only or not reader:
            return msg
        timeline = self.get_post_timeline(reader)
        if post_limit:
            timeline = timeline[-post_limit:]
        div = self.STRING_DIV
        for record in timeline:
            if record["readable"]:
                msg += "%s\n%s" % (div, record["post"].display())
            else:
                msg += "%s\n%s" % (div, self.STRING_MISSING_MEMORY)
        return msg

    def display_involvement(self):
        """A string about who is able to add new posts."""
        msg = "(#%s) |w%s|n - Owners and post authors: %s" % (
            self.id,
            self.title,
            self.owners_and_contributors,
        )
        msg += "\nCharacters invited to post: %s" % ", ".join(
            [str(ob) for ob in self.current_players]
        )
        if self.concluded:
            msg += (
                "\nNote: No one may post since this flashback is concluded, but adding viewers is still "
                "possible with |w/invite/retro|n or |w/allow|n switches. See 'help flashback' for usage."
            )
        return msg

    @property
    def owner(self):
        """Owner's roster entry."""
        return self.owners.first()

    @property
    def owners(self):
        """Queryset of all owners' roster entries."""
        owner = FlashbackInvolvement.OWNER
        return self.participants.filter(flashback_involvements__status=owner)

    @property
    def post_authors(self):
        """Queryset of author roster entries."""
        all_posts = self.posts.all()
        return RosterEntry.objects.filter(flashback_posts__in=all_posts).distinct()

    @property
    def owners_and_contributors(self):
        """String of comma-separated owners (in color!) and post authors."""
        owners = self.owners
        owners_ids = [ob.id for ob in owners]
        owners_names = owners.values_list("player__username", flat=True)
        authors_names = self.post_authors.exclude(id__in=owners_ids).values_list(
            "player__username", flat=True
        )
        return ", ".join(
            ["|c%s|n" % ob.capitalize() for ob in owners_names]
            + [str(ob.capitalize()) for ob in authors_names]
        )

    @property
    def all_players(self):
        """List of players invited to this flashback AND retired contributors."""
        return [ob.player for ob in self.participants.all()]

    @property
    def current_rosters(self):
        """Queryset of roster entries who may add posts."""
        contributor = FlashbackInvolvement.CONTRIBUTOR
        return self.participants.filter(flashback_involvements__status__gte=contributor)

    @property
    def current_players(self):
        """List of players who may add posts."""
        return [ob.player for ob in self.current_rosters]

    def get_involvement(self, roster_entry):
        """Returns a FlashbackInvolvement belonging to the roster entry."""
        try:
            return self.flashback_involvements.get(participant=roster_entry)
        except FlashbackInvolvement.DoesNotExist:
            return None

    def get_post_timeline(self, player, is_staff=None):
        """
        Returns a list of dicts that contain either a single readable post, or
        a list of unreadable posts. Each dict also has a 'readable' boolean.
        This will obfuscate how much material a reader may be missing in gaps.

            Args:
                player (Account object): the reader
                is_staff (Bool): optional, prevents redundant check

            Returns:
                timeline (list of dictionaries): Dicts contain 'readable' bool
                    and a post (if readable) or list-of-posts (if unreadable).

        timeline example:
        [{'readable': False, 'posts': [p1, p2]}, {'readable': True, 'post': p3}]
        """
        if is_staff == None:
            is_staff = bool(player.is_staff or player.check_permstring("builders"))
        try:
            roster = player.roster
            if not is_staff and roster not in self.participants.all():
                raise AttributeError
        except AttributeError:
            raise AttributeError
        timeline = []
        all_posts = list(self.posts.all())
        perms = roster.flashback_post_permissions.filter(post__in=all_posts)
        for post in all_posts:
            perm = [ob for ob in perms if ob.post_id == post.id]  # evaluates 'perms' qs
            if is_staff or perm or post.poster == roster:
                readable_dict = {"readable": True, "post": post}
                timeline.append(readable_dict)
                if perm:
                    perm[0].is_read = True  # cache-safe is cache money, baby
            elif not timeline or timeline[-1]["readable"]:
                unreadable_dict = {"readable": False, "posts": [post]}
                timeline.append(unreadable_dict)
            else:
                timeline[-1]["posts"].append(post)
        perms.exclude(is_read=True).update(is_read=True)  # update skips cached objects
        return timeline

    def posts_allowed_by(self, player):
        """Boolean for whether player may post to this flashback."""
        if player.is_staff or player.check_permstring("builders"):
            return True
        elif not self.concluded and player in self.current_players:
            return True

    def uninvite_involvement(self, inv):
        """Retires contributor or deletes non-contributor's FlashbackInvolvement (inv)."""
        if inv.contributions.exists():
            inv.status = inv.RETIRED
            inv.save()
        else:
            posts = self.posts.all()
            inv.participant.flashback_post_permissions.filter(post__in=posts).delete()
            inv.delete()

    def invite_roster(self, roster_entry, retro=False, owner=False):
        """Creates or unretires a FlashbackInvolvement."""
        inv, created = self.flashback_involvements.get_or_create(
            participant=roster_entry
        )
        if not created:
            inv.status = inv.CONTRIBUTOR
            inv.roll = ""
        if owner:
            inv.status = inv.OWNER
        else:
            roster_entry.player.inform(
                "You have been invited to participate in flashback #%s: '%s'."
                % (self.id, self),
                category="Flashbacks",
            )
        inv.save()
        if retro:
            self.allow_back_read(roster_entry)

    def allow_back_read(self, roster_entry, amount=None):
        """
        Bulk-adds through-models for back-reading posts.
        Args:
            roster_entry (RosterEntry): the reader
            amount (int): number of backposts. None defaults to 'all'.
        """
        posts = self.posts.all()
        readable = posts.filter(Q(readable_by=roster_entry) | Q(poster=roster_entry))
        if amount != None:
            start = len(posts) - amount
            if start > 0:
                posts = posts[start : amount + start]
        bulk_list = []
        for post in posts:
            if post in readable:
                continue
            bulk_list.append(FlashbackPostPermission(post=post, reader=roster_entry))
        FlashbackPostPermission.objects.bulk_create(bulk_list)

    def add_post(self, actions, poster=None):
        """
        Adds a new post to the flashback.
        Args:
            actions (string): The story post that the poster is writing.
            poster (RosterEntry): The player who added the story post.
        """
        now = datetime.now()
        inv = self.get_involvement(poster)
        roll = inv.roll if inv else None
        post = self.posts.create(
            poster=poster, actions=actions, db_date_created=now, roll=roll
        )
        post.set_new_post_readers()
        if inv and roll:
            inv.roll = ""
            inv.save()
        poster_msg = ""
        if poster:
            poster.character.messages.num_flashbacks += 1
            poster_msg = " by %s" % poster
        self.inform_all_but(
            poster, "New post%s on '%s' (flashback #%s)!" % (poster_msg, self, self.id)
        )

    def end_scene(self, ender):
        """Concludes the flashback. Longer flashbacks may award an event XP."""
        num_posts = self.posts.count()
        authors = self.post_authors
        msg = "Flashback #%s '%s' has reached its conclusion." % (self.id, self)
        if num_posts < 1:
            ender.player.inform(
                "With no posts, '%s' (flashback #%s) was deleted." % (self, self.id),
                category="Flashbacks",
            )
            self.delete()
            return
        elif num_posts >= 10 and len(authors) > 1:
            for roster in authors:
                player = roster.player
                val = player.db.event_xp or 0
                if val < self.MAX_XP:
                    val += 1
                    player.char_ob.adjust_xp(1)
                player.db.event_xp = val
            msg += " Its authors gained event XP (up to %s weekly)." % self.MAX_XP
        self.concluded = True
        self.save()
        self.inform_all_but(None, msg)

    def inform_all_but(self, roster_entry, msg):
        """Sends informs to current players except the catalyst."""
        for player in self.current_players:
            if roster_entry and roster_entry.player == player:
                continue
            player.inform(msg, category="Flashbacks")

    def get_absolute_url(self):
        """Returns URL of the view of this flashback"""
        from django.shortcuts import reverse

        object_id = self.owner.character.id
        return reverse(
            "character:flashback_post",
            kwargs={"object_id": object_id, "flashback_id": self.id},
        )


class FlashbackInvolvement(SharedMemoryModel):
    """Through model of a player's involvement with a Flashback."""

    RETIRED, CONTRIBUTOR, OWNER = range(3)
    STATUS_CHOICES = (
        (RETIRED, "Retired"),
        (CONTRIBUTOR, "Contributor"),
        (OWNER, "Owner"),
    )
    flashback = models.ForeignKey(
        "Flashback", related_name="flashback_involvements", on_delete=models.CASCADE
    )
    participant = models.ForeignKey(
        "RosterEntry", related_name="flashback_involvements", on_delete=models.CASCADE
    )
    status = models.PositiveSmallIntegerField(
        choices=STATUS_CHOICES, default=CONTRIBUTOR, blank=True
    )
    roll = models.CharField(max_length=250, blank=True)

    class Meta:
        unique_together = ("flashback", "participant")

    def __str__(self):
        return str(self.participant)

    @property
    def contributions(self):
        """Queryset for our posts"""
        return self.flashback.posts.filter(poster=self.participant)

    def make_dice_roll(self, check_str, flub=False):
        """Clears character's ndb last_roll, forces @check, keeps result string."""
        char = self.participant.character
        check_str = check_str.split("=", 1)[0]  # strips any receivers
        check_str += "=me"  # makes this a private roll
        flub_str = "/flub" if flub else ""
        char.ndb.last_roll = None
        char.execute_cmd("@oldcheck%s %s" % (flub_str, check_str))
        roll = char.ndb.last_roll
        if roll:
            roll.use_real_name = True  # Thanks, Maskbama.
            self.roll = roll.build_msg()
            self.save()
            return True


class FlashbackPost(SharedMemoryModel):
    """A post for a flashback."""

    flashback = models.ForeignKey(
        "Flashback", related_name="posts", on_delete=models.CASCADE
    )
    poster = models.ForeignKey(
        "RosterEntry",
        blank=True,
        null=True,
        related_name="flashback_posts",
        on_delete=models.SET_NULL,
    )
    readable_by = models.ManyToManyField(
        "RosterEntry",
        blank=True,
        related_name="readable_flashback_posts",
        through="FlashbackPostPermission",
    )
    actions = models.TextField(
        "The body of the post for your character's actions", blank=True
    )
    db_date_created = models.DateTimeField(blank=True, null=True)
    roll = models.CharField(max_length=250, blank=True)

    def display(self):
        """Returns string display of our story post."""
        roll = ("%s\n" % self.roll) if self.roll else ""
        return "|w[By %s]|n %s%s" % (self.poster, roll, self.actions)

    def __str__(self):
        return "Post by %s" % self.poster

    def set_new_post_readers(self):
        """Adds current flashback participants as readers. New post only; does not check existing!"""
        bulk_list = []
        current_rosters = self.flashback.current_rosters.exclude(id=self.poster.id)
        for roster_entry in current_rosters:
            bulk_list.append(FlashbackPostPermission(post=self, reader=roster_entry))
        FlashbackPostPermission.objects.bulk_create(bulk_list)

    def get_permission(self, roster_entry):
        """Returns a FlashbackPostPermission for the roster entry."""
        try:
            return self.flashback_post_permissions.get(reader=roster_entry)
        except FlashbackPostPermission.DoesNotExist:
            return None


class FlashbackPostPermission(SharedMemoryModel):
    """The readability status of a flashback post."""

    post = models.ForeignKey(
        "FlashbackPost",
        related_name="flashback_post_permissions",
        on_delete=models.CASCADE,
    )
    reader = models.ForeignKey(
        "RosterEntry",
        related_name="flashback_post_permissions",
        on_delete=models.CASCADE,
    )
    is_read = models.BooleanField(default=False)

    class Meta:
        unique_together = ("post", "reader")


class Goal(SharedMemoryModel):
    """A goal for a character."""

    (
        HEARTBREAKINGLY_MODEST,
        MODEST,
        REASONABLE,
        AMBITIOUS,
        VENOMOUSLY_AMBITIOUS,
        MEGALOMANIC,
    ) = range(0, 6)
    SCOPE_CHOICES = (
        (HEARTBREAKINGLY_MODEST, "Heartbreakingly Modest"),
        (MODEST, "Modest"),
        (REASONABLE, "Reasonable"),
        (AMBITIOUS, "Ambitious"),
        (VENOMOUSLY_AMBITIOUS, "Venomously Ambitious"),
        (MEGALOMANIC, "Megalomanic"),
    )
    SUCCEEDED, FAILED, ABANDONED, DORMANT, ACTIVE = range(0, 5)
    STATUS_CHOICES = (
        (SUCCEEDED, "Succeeded"),
        (FAILED, "Failed"),
        (ABANDONED, "Abandoned"),
        (DORMANT, "Dormant"),
        (ACTIVE, "Active"),
    )
    entry = models.ForeignKey(
        "RosterEntry", related_name="goals", on_delete=models.CASCADE
    )
    scope = models.PositiveSmallIntegerField(choices=SCOPE_CHOICES, default=REASONABLE)
    status = models.PositiveSmallIntegerField(choices=STATUS_CHOICES, default=ACTIVE)
    summary = models.CharField("Summary of the goal", max_length=80)
    description = models.TextField("Detailed description of the goal")
    ooc_notes = models.TextField(
        "Any OOC notes by the player about the goal", blank=True
    )
    gm_notes = models.TextField("Notes by staff, not visible to the player", blank=True)
    plot = models.ForeignKey(
        "dominion.Plot",
        null=True,
        blank=True,
        related_name="goals",
        on_delete=models.SET_NULL,
    )

    def display(self):
        """Returns string display of the goal"""
        msg = "{c%s{n (#%s)\n" % (self.summary, self.id)
        msg += "{wScope{n: %s, {wStatus{n: %s\n" % (
            self.get_scope_display(),
            self.get_status_display(),
        )
        if self.plot:
            msg += "{wPlot{n: %s\n" % self.plot
        msg += "{wDescription:{n %s\n" % self.description
        if self.ooc_notes:
            msg += "{wOOC Notes:{n %s\n" % self.ooc_notes
        updates = self.updates.all()
        if updates:
            msg += "{wUpdates:{n\n"
            msg += "\n".join(ob.display() for ob in updates)
        return msg

    def __str__(self):
        return "%s's Goal (#%s): %s" % (self.entry, self.id, self.summary)


class GoalUpdate(SharedMemoryModel):
    """Updates for goals"""

    goal = models.ForeignKey("Goal", related_name="updates", on_delete=models.CASCADE)
    beat = models.ForeignKey(
        "dominion.PlotUpdate",
        related_name="goal_updates",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
    )
    player_summary = models.TextField(blank=True)
    result = models.TextField(
        "IC description of the outcome for the player", blank=True
    )
    gm_notes = models.TextField("OOC notes for staff about consequences", blank=True)
    db_date_created = models.DateTimeField(auto_now_add=True)

    def display(self):
        msg = ""
        if self.beat:
            msg += "{wBeat #%s of Plot:{n %s\n" % (self.beat.id, self.beat.plot)
        msg = "{wStory Summary:{n %s\n" % self.player_summary
        msg += "{wResult{n: %s" % self.result
        return msg


class PlayerPosition(SharedMemoryModel):
    name = models.CharField(unique=True, max_length=255)
    players = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name="player_positions"
    )

    def __str__(self):
        return self.name
