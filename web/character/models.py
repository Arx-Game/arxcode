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

from django.db import models
from django.conf import settings
from cloudinary.models import CloudinaryField
from evennia.objects.models import ObjectDB
from evennia.locks.lockhandler import LockHandler
from django.db.models import Q, F
from .managers import ArxRosterManager, AccountHistoryManager
from datetime import datetime, date
import random
import traceback
from world.stats_and_skills import do_dice_check
from evennia.typeclasses.models import SharedMemoryModel

# multiplier for how much higher ClueDiscovery.roll must be over Clue.rating to be discovered
DISCO_MULT = 10


class Photo(SharedMemoryModel):
    """
    Used for uploading photos to cloudinary. It holds a reference to cloudinary-stored
    image and contains some metadata about the image.
    """
    #  Misc Django Fields
    create_time = models.DateTimeField(auto_now_add=True)
    title = models.CharField("Name or description of the picture (optional)", max_length=200, blank=True)
    owner = models.ForeignKey("objects.ObjectDB", blank=True, null=True, verbose_name='owner',
                              help_text='a Character owner of this image, if any.')
    alt_text = models.CharField("Optional 'alt' text when mousing over your image", max_length=200, blank=True)

    # Points to a Cloudinary image
    image = CloudinaryField('image')

    """ Informative name for mode """
    def __unicode__(self):
        try:
            public_id = self.image.public_id
        except AttributeError:
            public_id = ''
        return "Photo <%s:%s>" % (self.title, public_id)


class Roster(SharedMemoryModel):
    """
    A model for storing lists of entries of characters. Each RosterEntry has
    information on the Player and Character objects of that entry, information
    on player emails of previous players, GM notes, etc. The Roster itself just
    has locks for determining who can view the contents of a roster.
    """
    name = models.CharField(blank=True, null=True, max_length=255, db_index=True)
    lock_storage = models.TextField('locks', blank=True, help_text='defined in setup_utils')
    objects = ArxRosterManager()

    def __init__(self, *args, **kwargs):
        super(Roster, self).__init__(*args, **kwargs)
        self.locks = LockHandler(self)

    def access(self, accessing_obj, access_type='view', default=True):
        """
        Determines if another object has permission to access.
        accessing_obj - object trying to access this one
        access_type - type of access sought
        default - what to return if no lock of access_type was found
        """
        return self.locks.check(accessing_obj, access_type=access_type, default=default)

    def __unicode__(self):
        return self.name or 'Unnamed Roster'


class RosterEntry(SharedMemoryModel):
    """
    Main model for the character app. This is used both as an extension of an evennia AccountDB model (which serves as
    USER_AUTH_MODEL and a Character typeclass, and links the two together. It also is where some data used for the
    character lives, such as action points, the profile picture for their webpage, the PlayerAccount which currently
    is playing the character, and who played it previously. RosterEntry is used for most other models in the app,
    such as investigations, discoveries of clues/revelations/mysteries, etc.
    """
    roster = models.ForeignKey('Roster', related_name='entries',
                               on_delete=models.SET_NULL, blank=True, null=True, db_index=True)
    player = models.OneToOneField(settings.AUTH_USER_MODEL, related_name='roster', blank=True, null=True, unique=True)
    character = models.OneToOneField('objects.ObjectDB', related_name='roster', blank=True, null=True, unique=True)
    current_account = models.ForeignKey('PlayerAccount', related_name='characters', db_index=True,
                                        on_delete=models.SET_NULL, blank=True, null=True)
    previous_accounts = models.ManyToManyField('PlayerAccount', through='AccountHistory', blank=True)
    gm_notes = models.TextField(blank=True)
    # different variations of reasons not to display us
    inactive = models.BooleanField(default=False, null=False)
    frozen = models.BooleanField(default=False, null=False)
    # profile picture for sheet and also thumbnail for list
    profile_picture = models.ForeignKey('Photo', blank=True, null=True, on_delete=models.SET_NULL)
    # going to use for determining how our character page appears
    sheet_style = models.TextField(blank=True)
    lock_storage = models.TextField('locks', blank=True, help_text='defined in setup_utils')
    action_points = models.SmallIntegerField(default=100, blank=100)

    def __init__(self, *args, **kwargs):
        super(RosterEntry, self).__init__(*args, **kwargs)
        self.locks = LockHandler(self)

    class Meta:
        """Define Django meta options"""
        verbose_name_plural = "Roster Entries"
        unique_together = ('player', 'character')

    def __unicode__(self):
        if self.character:
            return self.character.key
        if self.player:
            return self.player.key
        return "Blank Entry"

    def access(self, accessing_obj, access_type='show_hidden', default=False):
        """
        Determines if another object has permission to access.
        accessing_obj - object trying to access this one
        access_type - type of access sought
        default - what to return if no lock of access_type was found
        """
        return self.locks.check(accessing_obj, access_type=access_type, default=default)

    def fake_delete(self):
        """We don't really want to delete RosterEntries for reals. So we fake it."""
        try:
            del_roster = Roster.objects.get(name__iexact="Deleted")
        except Roster.DoesNotExist:
            print("Could not find Deleted Roster!")
            return
        self.roster = del_roster
        self.inactive = True
        self.frozen = True
        self.save()

    def undelete(self, r_name="Active"):
        """Restores a fake-deleted entry."""
        try:
            roster = Roster.objects.get(name__iexact=r_name)
        except Roster.DoesNotExist:
            print("Could not find %s roster!" % r_name)
            return
        self.roster = roster
        self.inactive = False
        self.frozen = False
        self.save()

    def adjust_xp(self, val):
        """Stores xp the player's earned in their history of playing the character."""
        try:
            if val < 0:
                return
            history = self.accounthistory_set.filter(account=self.current_account).last()
            history.xp_earned += val
            history.save()
        except AttributeError:
            pass

    @property
    def finished_clues(self):
        """Clue discoveries that are all done and ready. Otherwise, they're just progress and shouldn't be shown"""
        return self.clues.filter(roll__gte=F('clue__rating') * DISCO_MULT)

    @property
    def discovered_clues(self):
        """The actual clues themselves that are all done, not just their discoveries"""
        return Clue.objects.filter(id__in=[ob.clue.id for ob in self.finished_clues])

    @property
    def undiscovered_clues(self):
        """Clues that we -haven't- discovered. We might have partial progress or not"""
        return Clue.objects.exclude(id__in=[ob.clue.id for ob in self.finished_clues])

    @property
    def alts(self):
        """Other roster entries played by our current PlayerAccount"""
        if self.current_account:
            return self.current_account.characters.exclude(id=self.id)
        return []

    def discover_clue(self, clue, method="Prior Knowledge"):
        """Discovers and returns the clue, if not already."""
        try:
            disco = self.clues.get(clue=clue)
        except ClueDiscovery.DoesNotExist:
            disco = self.clues.create(clue=clue)
        except ClueDiscovery.MultipleObjectsReturned:
            disco = self.clues.filter(clue=clue)[0]
        if not disco.finished:
            disco.mark_discovered(method=method)
        return disco

    @property
    def current_history(self):
        """Displays the current tenure of the PlayerAccount running this entry."""
        return self.accounthistory_set.last()

    @property
    def previous_history(self):
        """Gets all previous accounthistories after current"""
        return self.accounthistory_set.order_by('-id')[1:]

    @property
    def impressions_of_me(self):
        """
        Gets queryset of all our current first impressions
        """
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
            return self.impressions_of_me.filter(private=False).order_by('from_account__entry__character__db_key')
        except AttributeError:
            return []

    @property
    def impressions_for_all(self):
        """Public impressions that both the writer and receiver have signed off on sharing"""
        try:
            return self.public_impressions_of_me.filter(writer_share=True, receiver_share=True)
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
        return "\n\n".join("{c%s{n wrote %s: %s" % (ob.writer, public_str(ob),
                                                    ob.summary) for ob in qs)

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
        return 150 - self.action_point_penalty

    @property
    def action_point_penalty(self):
        """AP penalty from our number of fealties"""
        if hasattr(self, 'cached_ap_penalty'):
            return self.cached_ap_penalty
        try:
            self.cached_ap_penalty = 10 * self.player.Dominion.num_fealties
        except AttributeError:
            self.cached_ap_penalty = 0
        return self.cached_ap_penalty

    @classmethod
    def clear_ap_cache_in_cached_instances(cls):
        """Invalidate cached_ap_penalty in all cached RosterEntries when Fealty chain changes. Won't happen often."""
        for instance in cls.get_all_cached_instances():
            if hasattr(instance, 'cached_ap_penalty'):
                del instance.cached_ap_penalty


class Story(SharedMemoryModel):
    """An overall storyline for the game. It can be divided into chapters, which have their own episodes."""
    current_chapter = models.OneToOneField('Chapter', related_name='current_chapter_story',
                                           on_delete=models.SET_NULL, blank=True, null=True, db_index=True)
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
    story = models.ForeignKey('Story', blank=True, null=True, db_index=True,
                              on_delete=models.SET_NULL, related_name='previous_chapters')
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
        if not user or not user.is_authenticated():
            return self.public_crises
        if user.is_staff or user.check_permstring("builders"):
            return self.crises.all()
        return self.crises.filter(Q(public=True) | Q(required_clue__discoveries__in=user.roster.discovered_clues))


class Episode(SharedMemoryModel):
    """
    A brief episode. The teeniest bit of story. Originally I intended these to be holders for one-off events,
    but they more or less became used as dividers for chapters, which is fine.
    """
    name = models.CharField(blank=True, null=True, max_length=255, db_index=True)
    chapter = models.ForeignKey('Chapter', blank=True, null=True,
                                on_delete=models.SET_NULL, related_name='episodes', db_index=True)
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
        return self.crisis_updates.filter(crisis__public=True)

    def get_viewable_crisis_updates_for_player(self, player):
        """Returns non-public crisis updates that the player can see."""
        if not player or not player.is_authenticated():
            return self.public_crisis_updates
        if player.is_staff or player.check_permstring("builders"):
            return self.crisis_updates.all()
        return self.crisis_updates.filter(Q(crisis__public=True) | Q(
            crisis__required_clue__discoveries__in=player.roster.finished_clues)).distinct()

    def get_viewable_emits_for_player(self, player):
        if not player or not player.is_authenticated():
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
    chapter = models.ForeignKey('Chapter', blank=True, null=True,
                                on_delete=models.SET_NULL, related_name='emits')
    episode = models.ForeignKey('Episode', blank=True, null=True,
                                on_delete=models.SET_NULL, related_name='emits')
    text = models.TextField(blank=True, null=True)
    date = models.DateTimeField(auto_now_add=True)
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, blank=True, null=True,
                               on_delete=models.SET_NULL, related_name='emits')
    orgs = models.ManyToManyField('dominion.Organization', blank=True, related_name='emits')

    def broadcast(self):
        orgs = self.orgs.all()
        if not orgs:
            from server.utils.arx_utils import broadcast_msg_and_post
            broadcast_msg_and_post(self.text, self.sender, episode_name=str(self.episode or ""))
        else:
            for org in orgs:
                org.gemit_to_org(self)


class Milestone(SharedMemoryModel):
    """
    Major events in a character's life. Not used that much yet, GMs have set a few by hand. We'll expand this
    later in order to create a more robust/detailed timeline for a character's story arc.
    """
    protagonist = models.ForeignKey('RosterEntry', related_name='milestones')
    name = models.CharField(blank=True, null=True, max_length=255)
    synopsis = models.TextField(blank=True, null=True)
    chapter = models.ForeignKey('Chapter', blank=True, null=True,
                                on_delete=models.SET_NULL, related_name='milestones')
    episode = models.ForeignKey('Episode', blank=True, null=True,
                                on_delete=models.SET_NULL, related_name='milestones')
    secret = models.BooleanField(default=False, null=False)
    image = models.ForeignKey('Photo', blank=True, null=True,
                              on_delete=models.SET_NULL, related_name='milestones')
    gm_notes = models.TextField(blank=True, null=True)
    participants = models.ManyToManyField('RosterEntry', through='Participant', blank=True)
    importance = models.PositiveSmallIntegerField(default=0, blank=0)

    def __str__(self):
        return "%s - %s" % (self.protagonist, self.name)


class Participant(SharedMemoryModel):
    """Participant in a milestone."""
    milestone = models.ForeignKey('Milestone', on_delete=models.CASCADE)
    character = models.ForeignKey('RosterEntry', on_delete=models.CASCADE)
    xp_earned = models.PositiveSmallIntegerField(default=0, blank=0)
    karma_earned = models.PositiveSmallIntegerField(default=0, blank=0)
    gm_notes = models.TextField(blank=True, null=True)


class Comment(SharedMemoryModel):
    """Comment upon a milestone, written by someone involved."""
    poster = models.ForeignKey('RosterEntry', related_name='comments')
    target = models.ForeignKey('RosterEntry', related_name='comments_upon', blank=True, null=True)
    text = models.TextField(blank=True, null=True)
    date = models.DateTimeField(auto_now_add=True)
    gamedate = models.CharField(blank=True, null=True, max_length=80)
    reply_to = models.ForeignKey('self', blank=True, null=True)
    milestone = models.ForeignKey('Milestone', blank=True, null=True, related_name='comments')


class PlayerAccount(SharedMemoryModel):
    """
    This is used to represent a player, who might be playing one or more RosterEntries. They're uniquely identified
    by their email address. Karma is for any OOC goodwill they've built up over time. Not currently used. YET.
    """
    email = models.EmailField(unique=True)
    karma = models.PositiveSmallIntegerField(default=0, blank=0)
    gm_notes = models.TextField(blank=True, null=True)

    def __unicode__(self):
        return str(self.email)

    @property
    def total_xp(self):
        """Total xp they've earned over all time"""
        qs = self.accounthistory_set.all()
        return sum(ob.xp_earned for ob in qs)


class PlayerSiteEntry(SharedMemoryModel):

    account = models.ForeignKey(PlayerAccount, related_name='addresses')
    address = models.CharField(blank=True, null=True, max_length=255)
    last_seen = models.DateTimeField(blank=True, null=True)

    class Meta:
        verbose_name_plural = "Site Entries"

    @classmethod
    def add_site_for_player(cls, player, site):
        entries = AccountHistory.objects.filter(entry__character=player, end_date__isnull=True)
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
        (INFO, 'Info'),
        (RULING, 'Ruling'),
        (PRAISE, 'Praise'),
        (CRITICISM, 'Criticism'),
    )

    account = models.ForeignKey(PlayerAccount, related_name='entries')
    entry_type = models.PositiveSmallIntegerField(choices=entry_types, default=INFO)
    entry_date = models.DateTimeField(blank=True, null=True)
    text = models.TextField(blank=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='+', blank=True, null=True)

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
    account = models.ForeignKey('PlayerAccount', db_index=True)
    entry = models.ForeignKey('RosterEntry', db_index=True)
    xp_earned = models.SmallIntegerField(default=0, blank=0)
    gm_notes = models.TextField(blank=True, null=True)
    start_date = models.DateTimeField(blank=True, null=True, db_index=True)
    end_date = models.DateTimeField(blank=True, null=True, db_index=True)
    contacts = models.ManyToManyField('self', blank=True, through='FirstContact',
                                      related_name='contacted_by', symmetrical=False)
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
    from_account = models.ForeignKey('AccountHistory', related_name='initiated_contacts', db_index=True)
    to_account = models.ForeignKey('AccountHistory', related_name='received_contacts', db_index=True)
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
    character = models.ForeignKey('RosterEntry', related_name='logs')
    title = models.CharField("title of the scene", max_length=80)
    synopsis = models.TextField("Description of the scene written by player")
    date = models.DateTimeField(blank=True, null=True)
    log = models.TextField("Text log of the scene")
    lock_storage = models.TextField('locks', blank=True, help_text='defined in setup_utils')
    milestone = models.OneToOneField('Milestone', related_name='log', blank=True, null=True,
                                     on_delete=models.SET_NULL)

    def __init__(self, *args, **kwargs):
        super(RPScene, self).__init__(*args, **kwargs)
        self.locks = LockHandler(self)

    class Meta:
        """Define Django meta options"""
        verbose_name_plural = "RP Scenes"

    def __unicode__(self):
        return self.title

    def access(self, accessing_obj, access_type='show_hidden', default=False):
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
    topic = models.CharField(blank=True, max_length=255, help_text="Keywords or tldr or title")
    actions = models.TextField(blank=True, help_text="The writeup the player submits of their actions, used for GMing.")
    stat_used = models.CharField(blank=True, max_length=80, default="perception",
                                 help_text="The stat the player chose to use")
    skill_used = models.CharField(blank=True, max_length=80, default="investigation",
                                  help_text="The skill the player chose to use")
    silver = models.PositiveSmallIntegerField(default=0, blank=0, help_text="Additional silver added by the player")
    economic = models.PositiveSmallIntegerField(default=0, blank=0,
                                                help_text="Additional economic resources added by the player")
    military = models.PositiveSmallIntegerField(default=0, blank=0,
                                                help_text="Additional military resources added by the player")
    social = models.PositiveSmallIntegerField(default=0, blank=0,
                                              help_text="Additional social resources added by the player")
    action_points = models.PositiveSmallIntegerField(default=0, blank=0,
                                                     help_text="How many action points spent by player/assistants.")
    roll = models.SmallIntegerField(default=UNSET_ROLL, blank=True, help_text="Current dice roll")

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
    desc = models.TextField("Description", help_text="Description of the mystery given to the player " +
                                                     "when fully revealed",
                            blank=True)
    category = models.CharField(help_text="Type of mystery this is - ability-related, metaplot, etc", max_length=80,
                                blank=True)
    characters = models.ManyToManyField('RosterEntry', blank=True, through='MysteryDiscovery',
                                        through_fields=('mystery', 'character'), db_index=True)

    class Meta:
        verbose_name_plural = "Mysteries"

    def __str__(self):
        return self.name


class Revelation(SharedMemoryModel):
    """A major piece of lore that can be discovered by players. Clues make up pieces of it."""
    name = models.CharField(max_length=255, blank=True, db_index=True)
    desc = models.TextField("Description", help_text="Description of the revelation given to the player",
                            blank=True)
    mysteries = models.ManyToManyField("Mystery", through='RevelationForMystery')

    required_clue_value = models.PositiveSmallIntegerField(default=0, blank=0,
                                                           help_text="The total value of clues to trigger this")

    red_herring = models.BooleanField(default=False, help_text="Whether this revelation is totally fake")
    characters = models.ManyToManyField('RosterEntry', blank=True, through='RevelationDiscovery',
                                        through_fields=('revelation', 'character'), db_index=True)

    def __str__(self):
        return self.name

    @property
    def total_clue_value(self):
        """Total value of the clues used for this revelation"""
        return sum(ob.rating for ob in Clue.objects.filter(revelations=self))

    @property
    def requires(self):
        """String representation of amount required compared to available clue points"""
        return "%d of %d" % (self.required_clue_value, self.total_clue_value)

    def player_can_discover(self, char):
        """Check whether they can discover the revelation"""
        char_clues = set([ob.clue for ob in char.finished_clues])
        used_clues = set([ob.clue for ob in self.clues_used.filter(required_for_revelation=True)])
        # check if we have all the required clues for this revelation discovered
        if not used_clues.issubset(char_clues):
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
        return sum(ob.clue.rating for ob in char.finished_clues.filter(clue__revelations=self))


class Clue(SharedMemoryModel):
    """A significant discovery by a player that points their character toward a Revelation, if it's not fake."""
    name = models.CharField(max_length=255, blank=True, db_index=True)
    rating = models.PositiveSmallIntegerField(default=0, blank=0, help_text="Value required to get this clue",
                                              db_index=True)
    desc = models.TextField("Description", help_text="Description of the clue given to the player",
                            blank=True)
    gm_notes = models.TextField("GM Notes", help_text="Notes visible only to staff/GMs about this clue",
                                blank=True)
    revelations = models.ManyToManyField("Revelation", through='ClueForRevelation', db_index=True)
    characters = models.ManyToManyField('RosterEntry', blank=True, through='ClueDiscovery', db_index=True,
                                        through_fields=('clue', 'character'))
    red_herring = models.BooleanField(default=False, help_text="Whether this revelation is totally fake")
    allow_investigation = models.BooleanField(default=False, help_text="Can be gained through investigation rolls")
    allow_exploration = models.BooleanField(default=False, help_text="Can be gained through exploration rolls")
    allow_trauma = models.BooleanField(default=False, help_text="Can be gained through combat rolls")
    allow_sharing = models.BooleanField(default=True, help_text="Can be shared")
    search_tags = models.ManyToManyField('SearchTag', blank=True, db_index=True)
    # if we were created for an RP event, such as a PRP
    event = models.ForeignKey("dominion.RPEvent", blank=True, null=True, related_name="clues")

    def __str__(self):
        return self.name

    @property
    def keywords(self):
        """List of keywords from our search tags. We use them for auto-matching clues with investigations."""
        return [ob.name for ob in self.search_tags.all()]

    @property
    def creators(self):
        """
        Returns GMs of the event this clue was made for
        """
        if not self.event:
            return []
        try:
            return self.event.gms.all()
        except (AttributeError, IndexError):
            return []

    @property
    def value_for_discovery(self):
        """Value required for this clue to be discovered"""
        return self.rating * DISCO_MULT


class SearchTag(SharedMemoryModel):
    """Tags for Clues that are used for automatching investigations to them."""
    name = models.CharField(max_length=255, unique=True)
    topic = models.ForeignKey('LoreTopic', blank=True, null=True, db_index=True)

    def __str__(self):
        return self.name


class LoreTopic(SharedMemoryModel):
    """GM notes about different in-game topics. Basically a knowledge-base for lore."""
    name = models.CharField(max_length=255, unique=True)
    desc = models.TextField("GM Notes about this Lore Topic", blank=True)

    def __str__(self):
        return self.name


class MysteryDiscovery(SharedMemoryModel):
    """Through model used to record when a character discovers a mystery."""
    character = models.ForeignKey('RosterEntry', related_name="mysteries", db_index=True)
    mystery = models.ForeignKey('Mystery', related_name="discoveries", db_index=True)
    investigation = models.ForeignKey('Investigation', blank=True, null=True, related_name="mysteries")
    message = models.TextField(blank=True, help_text="Message for the player's records about how they discovered this.")
    date = models.DateTimeField(blank=True, null=True)
    milestone = models.OneToOneField('Milestone', related_name="mystery", blank=True, null=True)

    class Meta:
        unique_together = ('character', 'mystery')
        verbose_name_plural = "Mystery Discoveries"

    def __str__(self):
        return "%s's discovery of %s" % (self.character, self.mystery)


class RevelationDiscovery(SharedMemoryModel):
    """Through model used to record when a character discovers a revelation."""
    character = models.ForeignKey('RosterEntry', related_name="revelations", db_index=True)
    revelation = models.ForeignKey('Revelation', related_name="discoveries", db_index=True)
    investigation = models.ForeignKey('Investigation', blank=True, null=True, related_name="revelations")
    message = models.TextField(blank=True, help_text="Message for the player's records about how they discovered this.")
    date = models.DateTimeField(blank=True, null=True)
    milestone = models.OneToOneField('Milestone', related_name="revelation", blank=True, null=True)
    discovery_method = models.CharField(help_text="How this was discovered - exploration, trauma, etc", max_length=255)
    revealed_by = models.ForeignKey('RosterEntry', related_name="revelations_spoiled", blank=True, null=True)

    class Meta:
        unique_together = ('character', 'revelation')
        verbose_name_plural = "Revelation Discoveries"

    def check_mystery_discovery(self):
        """
        For the mystery, make sure that we have all the revelations required
        inside the character before we award it to the character
        """
        # get our RevForMystery where the player does not yet have the mystery, and the rev is required
        rev_usage = self.revelation.usage.filter(required_for_mystery=True).distinct()
        # get the associated mysteries the player doesn't yet have
        mysteries = Mystery.objects.filter(Q(revelations_used__in=rev_usage) &
                                           ~Q(characters=self.character)).distinct()
        discoveries = []
        char_revs = set([ob.revelation for ob in self.character.revelations.all()])
        for myst in mysteries:
            required_revs = set([ob.revelation for ob in myst.revelations_used.filter(required_for_mystery=True)])
            # character now has all revelations, we add the mystery
            if required_revs.issubset(char_revs):
                discoveries.append(myst)
        return discoveries

    def __str__(self):
        return "%s's discovery of %s" % (self.character, self.revelation)

    def display(self):
        """Returns string display for the revelation."""
        msg = self.revelation.name + "\n"
        msg += self.revelation.desc + "\n"
        if self.message:
            msg += "\n" + self.message
        return msg


class RevelationForMystery(SharedMemoryModel):
    """Through model for showing which revelations are required for mystery discovery."""
    mystery = models.ForeignKey('Mystery', related_name="revelations_used", db_index=True)
    revelation = models.ForeignKey('Revelation', related_name="usage", db_index=True)
    required_for_mystery = models.BooleanField(default=True, help_text="Whether this must be discovered for the" +
                                                                       " mystery to finish")
    tier = models.PositiveSmallIntegerField(default=0, blank=0,
                                            help_text="How high in the hierarchy of discoveries this revelation is," +
                                                      " lower number discovered first")

    def __str__(self):
        return "Revelation %s used for %s" % (self.revelation, self.mystery)


class ClueDiscovery(SharedMemoryModel):
    """Through model that represents knowing/progress towards discovering a clue."""
    clue = models.ForeignKey('Clue', related_name="discoveries", db_index=True)
    character = models.ForeignKey('RosterEntry', related_name="clues", db_index=True)
    investigation = models.ForeignKey('Investigation', blank=True, null=True, related_name="clues", db_index=True)
    message = models.TextField(blank=True, help_text="Message for the player's records about how they discovered this.")
    date = models.DateTimeField(blank=True, null=True)
    milestone = models.OneToOneField('Milestone', related_name="clue", blank=True, null=True)
    discovery_method = models.CharField(help_text="How this was discovered - exploration, trauma, etc",
                                        blank=True, max_length=255)
    roll = models.PositiveSmallIntegerField(default=0, blank=0, db_index=True)
    revealed_by = models.ForeignKey('RosterEntry', related_name="clues_spoiled", blank=True, null=True, db_index=True)

    class Meta:
        verbose_name_plural = "Clue Discoveries"

    @property
    def name(self):
        """Returns the name of the clue we're discovering"""
        return self.clue.name

    @property
    def required_roll_for_discovery(self):
        """Value we need self.roll to be for this clue to be discovered."""
        return self.clue.value_for_discovery

    @property
    def finished(self):
        """Whether our clue has been discovered."""
        return self.roll >= self.required_roll_for_discovery

    def display(self, show_sharing=False):
        """Returns a string showing that we're not yet done, or the completed clue discovery."""
        if not self.finished:
            return self.message or "An investigation that hasn't yet yielded anything definite."
        msg = "\n{c%s{n\n" % self.clue.name
        msg += "{wRating:{n %s\n" % self.clue.rating
        msg += self.clue.desc + "\n"
        if self.message:
            if self.date:
                msg += self.date.strftime("%x %X") + " "
            msg += self.message + "\n"
        if show_sharing:
            shared = self.shared_with
            if shared:
                msg += "{wShared with{n: %s" % ", ".join(str(ob) for ob in shared)
        return msg

    def check_revelation_discovery(self):
        """
        If this Clue discovery means that the character now has every clue
        for the revelation, we award it to them.
        """
        # find all ClueForRevelations used for this discovery
        clue_usage = self.clue.usage.all()
        # get the associated revelations the player doesn't yet have
        revelations = Revelation.objects.filter(Q(clues_used__in=clue_usage) &
                                                ~Q(characters=self.character)).distinct()
        discovered = []
        for rev in revelations:
            if rev.player_can_discover(self.character):
                discovered.append(rev)
        return discovered

    def __str__(self):
        return "%s's discovery of %s" % (self.character, self.clue)

    @property
    def progress_percentage(self):
        """Returns our percent towards completion as an integer."""
        try:
            return int((float(self.roll) / float(self.required_roll_for_discovery)) * 100)
        except (AttributeError, TypeError, ValueError, ZeroDivisionError):
            return 0

    def mark_discovered(self, method="Prior Knowledge", message="", roll=None, revealed_by=None, investigation=None,
                        inform_creator=None):
        """
        Discovers the clue for our character.

        Args:
            method: String describing how the clue was discovered.
            message: Additional message saying how it was discovered, stored in self.message
            roll: Stored in self.roll if we want to note high success. Otherwise self.roll becomes minimum required
            revealed_by: If the clue was shared by someone else, we store their RosterEntry
            investigation: If it was from an investigation, we mark that also.
            inform_creator: Object used for bulk creation of informs
        """
        if roll and roll > self.required_roll_for_discovery:
            self.roll = roll
        else:
            self.roll = self.required_roll_for_discovery
        date = datetime.now()
        self.date = date
        self.discovery_method = method
        self.message = message
        self.revealed_by = revealed_by
        self.investigation = investigation
        self.save()
        revelations = self.check_revelation_discovery()
        msg = ""
        for revelation in revelations:
            msg = "\nYou have discovered a revelation: %s\n%s" % (str(revelation), revelation.desc)
            message = "You had a revelation after learning a clue!"
            rev = RevelationDiscovery.objects.create(character=self.character, discovery_method=method,
                                                     message=message, investigation=investigation,
                                                     revelation=revelation, date=date)
            mysteries = rev.check_mystery_discovery()
            for mystery in mysteries:
                msg += "\nYou have also discovered a mystery: %s\n%s" % (str(mystery), mystery.desc)
                message = "You uncovered a mystery after learning a clue!"
                MysteryDiscovery.objects.create(character=self.character, message=message, investigation=investigation,
                                                mystery=mystery, date=date)
        if revelations:
            if inform_creator:
                inform_creator.add_player_inform(self.character.player, msg, "Discovery")
            else:
                self.character.player.inform(msg, category="Discovery", append=False)
        # make sure any investigations targeting the now discovered clue get reset. queryset.update doesn't work with
        # SharedMemoryModel (cached objects will overwrite it), so we iterate through them instead
        for investigation in self.character.investigations.filter(clue_target=self.clue):
            investigation.clue_target = None
            investigation.save()

    def share(self, entry, investigation=None, note=None, inform_creator=None):
        """
        Copy this clue to target entry. If they already have the
        discovery, we'll add our roll to theirs (which presumably should
        finish it). If not, they'll get a copy with their roll value
        equal to ours. We'll check for them getting a revelation discovery.
        """
        try:
            targ_clue = entry.clues.get(clue=self.clue)
        except ClueDiscovery.DoesNotExist:
            targ_clue = entry.clues.create(clue=self.clue)
        except ClueDiscovery.MultipleObjectsReturned:
            # error in that we shouldn't have more than one. Clear out duplicates
            clues = entry.clues.filter(clue=self.clue).order_by('-roll')
            targ_clue = clues[0]
            for clue in clues:
                if clue != targ_clue:
                    clue.delete()
        if targ_clue.finished:
            entry.player.send_or_queue_msg("%s tried to share the clue %s with you, but you already know that." % (
                self.character, self.name))
            return False
        note_msg = "."
        if note:
            note_msg = ", who noted: %s" % note
        message = "This clue was shared with you by %s%s" % (self.character, note_msg)
        targ_clue.mark_discovered(method="Sharing", message=message, revealed_by=self.character,
                                  investigation=investigation, inform_creator=inform_creator)
        pc = targ_clue.character.player
        msg = "A new clue (%d) has been shared with you by %s!\n\n%s\n" % (targ_clue.id, self.character,
                                                                           targ_clue.display())
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


class ClueForRevelation(SharedMemoryModel):
    """Through model that shows which clues are required for a revelation"""
    clue = models.ForeignKey('Clue', related_name="usage", db_index=True)
    revelation = models.ForeignKey('Revelation', related_name="clues_used", db_index=True)
    required_for_revelation = models.BooleanField(default=True, help_text="Whether this must be discovered for " +
                                                                          "the revelation to finish")
    tier = models.PositiveSmallIntegerField(default=0, blank=0,
                                            help_text="How high in the hierarchy of discoveries this clue is, " +
                                                      "lower number discovered first")

    def __str__(self):
        return "Clue %s used for %s" % (self.clue, self.revelation)


class InvestigationAssistant(SharedMemoryModel):
    """Someone who is helping an investigation out. Note that char is an ObjectDB, not RosterEntry."""
    currently_helping = models.BooleanField(default=False, help_text="Whether they're currently helping out")
    investigation = models.ForeignKey('Investigation', related_name="assistants", db_index=True)
    char = models.ForeignKey('objects.ObjectDB', related_name="assisted_investigations", db_index=True)
    stat_used = models.CharField(blank=True, max_length=80, default="perception",
                                 help_text="The stat the player chose to use")
    skill_used = models.CharField(blank=True, max_length=80, default="investigation",
                                  help_text="The skill the player chose to use")
    actions = models.TextField(blank=True, help_text="The writeup the player submits of their actions, used for GMing.")

    class Meta:
        unique_together = ('char', 'investigation')

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
            clue.share(entry, investigation=self.investigation, inform_creator=inform_creator)

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
    character = models.ForeignKey('RosterEntry', related_name="investigations", db_index=True)
    ongoing = models.BooleanField(default=True, help_text="Whether this investigation is finished or not",
                                  db_index=True)
    active = models.BooleanField(default=False, db_index=True, help_text="Whether this is the investigation for the" +
                                                                         " week. Only one allowed")
    automate_result = models.BooleanField(default=True, help_text="Whether to generate a result during weekly " +
                                                                  "maintenance. Set false if GM'd")
    results = models.TextField(default="You didn't find anything.", blank=True,
                               help_text="The text to send the player, either set by GM or generated automatically " +
                               "by script if automate_result is set.")
    clue_target = models.ForeignKey('Clue', blank=True, null=True)

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
                assistant.helper_name, assistant.stat_used, assistant.skill_used, assistant.actions)
        return msg

    def gm_display(self):
        """Returns string of investigation stats for GM"""
        msg = self.display()
        msg += "{wCurrent Roll{n: %s\n" % self.roll
        msg += "{wTargeted Clue{n: %s\n" % self.targeted_clue
        msg += "{wProgress Value{n: %s\n" % self.progress
        msg += "{wComplete this week?{n: %s\n" % self.check_success()
        msg += "{wSilver Used{n: %s\n" % self.silver
        msg += "{wEconomic Used{n %s\n" % self.economic
        msg += "{wMilitary Used{n %s\n" % self.military
        msg += "{wSocial Used{n %s\n" % self.social
        msg += "{wAction Points Used{n: %s\n" % self.action_points
        return msg

    @property
    def char(self):
        """Character object of the RosterEntry running the investigation"""
        return self.character.character

    @property
    def active_assistants(self):
        """Assistants that are flagged as actively participating"""
        return self.assistants.filter(currently_helping=True)

    @property
    def finished_clues(self):
        """Queryset of clues that this investigation has uncovered"""
        return self.clues.filter(roll__gte=F('clue__rating') * DISCO_MULT)

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
        roll = do_dice_check(obj.char, stat_list=[stat, "perception", "intellect"], skill_list=[skill, "investigation"],
                             difficulty=diff, average_skill_list=True)
        return roll

    def do_roll(self, mod=0, diff=None):
        """
        Do a dice roll to return a result
        """
        diff = (diff if diff is not None else self.difficulty) + mod
        roll = self.do_obj_roll(self, diff)
        for ass in self.active_assistants:
            a_roll = self.do_obj_roll(ass, diff - 20)
            if a_roll < 0:
                a_roll = 0
            try:
                ability_level = ass.char.db.abilities['investigation_assistant']
            except (AttributeError, ValueError, KeyError, TypeError):
                ability_level = 0
            a_roll += random.randint(0, 5) * ability_level
            roll += a_roll
        try:
            roll = int(roll * settings.INVESTIGATION_PROGRESS_RATE)
        except (AttributeError, TypeError, ValueError):
            pass
        # save the character's roll
        self.roll = roll
        self.save()
        return roll

    @property
    def resource_mod(self):
        """Difficulty modifier as an integer from silver/resources"""
        mod = 0
        silver_mod = self.silver/2500
        if silver_mod > 20:
            silver_mod = 20
        mod += silver_mod
        res_mod = int((self.economic + self.military + self.social)/2.5)
        if random.randint(0, 5) < (self.economic + self.military + self.social) % 5:
            res_mod += 1
        if res_mod > 60:
            res_mod = 60
        mod += res_mod
        mod += self.action_points/5
        return mod

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
        except (AttributeError, ValueError, TypeError):
            pass
        return base - self.resource_mod

    @property
    def completion_value(self):
        """The value required for us to be done, progress-wise."""
        if not self.targeted_clue:
            return 30
        return self.targeted_clue.value_for_discovery

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
        msg = "Your investigation into '%s' has had the following result:\n" % self.topic
        msg += self.results
        if inform_creator:
            inform_creator.add_player_inform(self.character.player, msg, "Investigations")
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
                kw = self.find_random_keywords()
                if not kw:
                    self.results = "There is nothing else for you to find."
                else:
                    self.results = "You couldn't find anything about '%s', " % self.topic
                    self.results += "but you keep on finding mention of '%s' in your search." % kw
            else:
                # add a valid clue and update results string
                roll = self.get_roll()
                try:
                    clue = self.clues.get(clue=self.targeted_clue, character=self.character)
                except ClueDiscovery.DoesNotExist:
                    clue = ClueDiscovery.objects.create(clue=self.targeted_clue, investigation=self,
                                                        character=self.character)
                final_roll = clue.roll + roll
                clue.roll += roll
                if self.automate_result:
                    self.results = "Your investigation has discovered a clue!\n"
                self.results += clue.display()
                message = clue.message or "Your investigation has discovered this!"
                clue.mark_discovered(method="investigation", message=message, roll=final_roll, investigation=self)
                # we found a clue, so this investigation is done.
                self.clue_target = None
                self.ongoing = False
                for ass in self.active_assistants:
                    # noinspection PyBroadException
                    try:
                        ass.shared_discovery(clue, inform_creator)
                    except Exception:
                        traceback.print_exc()
        else:
            # update results to indicate our failure
            self.results = "Your investigation failed to find anything."
            if self.add_progress():
                self.results += " But you feel you've made some progress in following some leads."
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

    @property
    def targeted_clue(self):
        """Tries to fetch a clue automatically if we don't have one. Then returns what we have, or None."""
        if self.clue_target:
            return self.clue_target
        self.clue_target = self.find_target_clue()
        self.save()
        return self.clue_target

    @property
    def keywords(self):
        """Get list of keywords from parsing the player-set topic"""
        return get_keywords_from_topic(self.topic)

    def find_target_clue(self):
        """
        Finds a target clue based on our topic and our investigation history.
        We'll choose the lowest rating out of 3 random choices.
        """
        return get_random_clue(self.topic, self.character)

    def find_random_keywords(self):
        """
        Finds a random keyword in a clue we don't have yet.
        """
        candidates = Clue.objects.filter(~Q(characters=self.character)).order_by('rating')
        # noinspection PyBroadException
        try:
            ob = random.choice(candidates)
            kw = random.choice(ob.keywords)
            return kw
        except Exception:
            return None

    @property
    def progress(self):
        """Get our progress from our current clue."""
        try:
            clue = self.clues.get(clue=self.targeted_clue)
            return clue.roll
        except ClueDiscovery.DoesNotExist:
            return 0

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
        try:
            clue = self.clues.get(clue=self.targeted_clue)
            clue.roll += roll
            clue.save()
        except ClueDiscovery.DoesNotExist:
            ClueDiscovery.objects.create(clue=self.targeted_clue, investigation=self,
                                         roll=roll,
                                         character=self.character)
        return roll

    @property
    def progress_str(self):
        """Returns a string saying how close they are to discovery."""
        try:
            clue = self.clues.get(clue=self.targeted_clue)
            progress = clue.progress_percentage
        except (ClueDiscovery.DoesNotExist, AttributeError):
            progress = 0
        if progress <= 0:
            return "No real progress has been made to finding something new."
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
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="created_theories", blank=True, null=True,
                                db_index=True)
    known_by = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="known_theories", blank=True,
                                      through="TheoryPermissions")
    topic = models.CharField(max_length=255, blank=True, null=True)
    desc = models.TextField(blank=True, null=True)
    related_clues = models.ManyToManyField("Clue", related_name="theories", blank=True, db_index=True)
    related_theories = models.ManyToManyField("self", blank=True)

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
    player = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="theory_permissions")
    theory = models.ForeignKey("Theory", related_name="theory_permissions")
    can_edit = models.BooleanField(default=False)


def get_keywords_from_topic(topic):
    """
    Helper function for breaking up a phrase into keywords
    Args:
        topic: The phrase we'll break up

    Returns:
        List of words/phrases that are substrings of the topic.
    """
    old_topic = topic
    topic = topic.strip("?").strip(".").strip("!").strip(":").strip(",").strip(";")
    # convert to str from unicode
    k_words = [str(ob) for ob in topic.split()]
    # add singular version
    k_words.extend([ob[:-1] for ob in k_words if ob.endswith("s") and len(ob) > 1])
    # add back in the phrases for phrase matching
    if len(k_words) > 1:
        for pos in range(0, len(k_words)):
            phrase = []
            for s_pos in range(0, pos):
                phrase.append(k_words[s_pos])
            k_words.append(" ".join(phrase))
    for word in ("a", "or", "an", "the", "and", "but", "not",
                 "yet", "with", "in", "how", "if", "of"):
        if word in k_words:
            k_words.remove(str(word))
    if old_topic not in k_words:
        k_words.append(str(old_topic))
    return set(k_words)


def get_random_clue(topic, character):
    """
    Finds a target clue based on our topic and our investigation history.
    We'll choose the lowest rating out of 3 random choices.
    """
    exact = Clue.objects.filter(Q(allow_investigation=True) &
                                Q(search_tags__name__iexact=topic) &
                                ~Q(characters=character)).order_by('rating')
    if exact:
        return random.choice(exact)
    k_words = get_keywords_from_topic(topic)
    # build a case-insensitive query for each keyword of the investigation
    query = Q()
    for k_word in k_words:
        if not k_word:
            continue
        query |= Q(search_tags__name__iexact=k_word)
    # only certain clues - ones that can be investigated, exclude ones we've already started
    candidates = Clue.objects.filter(allow_investigation=True, search_tags__isnull=False).exclude(characters=character)
    # now match them by keyword
    candidates = candidates.filter(query).distinct()
    try:
        return random.choice(candidates)
    except (IndexError, TypeError):
        return None


class Flashback(SharedMemoryModel):
    """
    Represents a record of a scene in the past, played out via play-by-post for
    involved characters.
    """
    title = models.CharField(max_length=250, unique=True)
    summary = models.TextField(blank=True)
    owner = models.ForeignKey('RosterEntry', related_name="created_flashbacks")
    allowed = models.ManyToManyField('RosterEntry', related_name="allowed_flashbacks", blank=True)
    db_date_created = models.DateTimeField(blank=True, null=True)

    def get_new_posts(self, entry):
        """Returns posts that entry hasn't read yet."""
        return self.posts.exclude(Q(read_by=entry) | Q(poster=entry))

    def display(self, display_summary_only=False, post_limit=None):
        """Returns string display of a flashback."""
        msg = "(#%s) %s\n" % (self.id, self.title)
        msg += "Owner: %s\n" % self.owner
        msg += "Summary: %s\n" % self.summary
        if display_summary_only:
            return msg
        posts = list(self.posts.all())
        if post_limit:
            posts = posts[-post_limit:]
        msg += "Posts:\n%s" % "\n".join(post.display() for post in posts)
        return msg

    def __str__(self):
        return self.title

    @property
    def all_players(self):
        """List of players who are involved in the flashback."""
        all_entries = [self.owner] + list(self.allowed.all())
        return [ob.player for ob in all_entries]

    def add_post(self, actions, poster=None):
        """
        Adds a new post to the flashback.
        Args:
            actions: The story post that the poster is writing.
            poster (RosterEntry): The player who added the story post.
        """
        now = datetime.now()
        self.posts.create(poster=poster, actions=actions, db_date_created=now)
        if poster:
            poster.character.messages.num_flashbacks += 1
        for player in self.all_players:
            if poster and poster.player == player:
                continue
            player.inform("There is a new post on flashback #%s by %s." % (self.id, poster),
                          category="Flashbacks")

    def get_absolute_url(self):
        """Returns URL of the view of this flashback"""
        from django.shortcuts import reverse
        object_id = self.owner.character.id
        return reverse('character:flashback_post', kwargs={'object_id': object_id, 'flashback_id': self.id})


class FlashbackPost(SharedMemoryModel):
    """A post for a flashback."""
    flashback = models.ForeignKey('Flashback', related_name="posts")
    poster = models.ForeignKey('RosterEntry', blank=True, null=True, related_name="flashback_posts")
    read_by = models.ManyToManyField('RosterEntry', blank=True, related_name="read_flashback_posts")
    actions = models.TextField("The body of the post for your character's actions", blank=True)
    db_date_created = models.DateTimeField(blank=True, null=True)

    def display(self):
        """Returns string display of our story post."""
        return "%s wrote: %s" % (self.poster, self.actions)

    def __str__(self):
        return "Post by %s" % self.poster
