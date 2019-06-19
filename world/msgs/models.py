"""
A basic inform, as well as other in-game messages.
"""
from django.conf import settings
from django.db import models
from evennia.comms.models import Msg
from .managers import (JournalManager, WhiteJournalManager, BlackJournalManager, MessengerManager, WHITE_TAG, BLACK_TAG,
                       RELATIONSHIP_TAG, MESSENGER_TAG, GOSSIP_TAG, RUMOR_TAG, POST_TAG,
                       PostManager, RumorManager, PRESERVE_TAG, TAG_CATEGORY, REVEALED_BLACK_TAG)


# ------------------------------------------------------------
#
# Inform
#
# ------------------------------------------------------------

class Inform(models.Model):
    """
    Informs represent persistent messages sent from the server
    to a player. For communication between entities, like mail,
    Msg should be used. This will primarily be used in Dominion
    or other game events where players will be informed upon
    logging-in of what transpired. In Dominion, these messages
    are created during weekly maintenance, and the week # is
    stored as well.

    The Inform class defines the following properties:
        player - recipient of the inform
        message - Text that is sent to the player
        date_sent - Time the inform was sent
        is_unread - Whether the player has read the inform
        week - The # of the week during which this inform was created.
    """
    player = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="informs", blank=True, null=True, on_delete=models.CASCADE)
    organization = models.ForeignKey("dominion.Organization", related_name="informs", blank=True, null=True, on_delete=models.CASCADE)
    message = models.TextField("Information sent to player or org")
    # send date
    date_sent = models.DateTimeField(editable=False, auto_now_add=True, db_index=True)
    # the week # of the maintenance cycle during which this inform was created
    week = models.PositiveSmallIntegerField(default=0, blank=0, db_index=True)
    read_by = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="read_informs")
    # allow for different types of informs/reports
    category = models.CharField(blank=True, null=True, max_length=80)
    # let them mark important messages for saving
    important = models.BooleanField(default=False)

    class Meta:
        app_label = "msgs"
        db_table = "comms_inform"


def get_model_from_tags(tag_list):
    """
    Given a list of tags, we return the appropriate proxy model
    Args:
        tag_list: list of strings that mark the Msg object's type

    Returns:
        The appropriate proxy class.
    """
    if WHITE_TAG in tag_list or BLACK_TAG in tag_list or RELATIONSHIP_TAG in tag_list:
        return Journal
    if MESSENGER_TAG in tag_list:
        return Messenger
    if POST_TAG in tag_list:
        return Post
    if RUMOR_TAG in tag_list or GOSSIP_TAG in tag_list:
        return Rumor


# noinspection PyUnresolvedReferences
class MarkReadMixin(object):
    """
    Proxy method for Msg that adds a few methods that most uses in Arx will share in common.
    """
    def mark_read(self, player):
        """
        Mark this Msg object as read by the player
        Args:
            player: Player who has read this Journal/Messenger/Board post/etc
        """
        self.db_receivers_accounts.add(player)

    def mark_unread(self, player):
        """
        Mark this Msg object as unread by the player
        Args:
            player: Player who has read this Journal/Messenger/Board post/etc
        """
        self.db_receivers_accounts.remove(player)

    def check_read(self, player):
        return self.db_receivers_accounts.filter(id=player.id)
        
    def parse_header(self):
        """
        Given a message object, return a dictionary of the different
        key:value pairs separated by semicolons in the header
        """
        header = self.db_header
        if not header:
            return {}
        hlist = header.split(";")
        keyvalpairs = [pair.split(":") for pair in hlist]
        keydict = {pair[0].strip(): pair[1].strip() for pair in keyvalpairs if len(pair) == 2}
        return keydict

    @property
    def event(self):
        from world.dominion.models import RPEvent
        from evennia.typeclasses.tags import Tag
        try:
            tag = self.db_tags.get(db_key__isnull=False, db_data__isnull=False, db_category="event")
            return RPEvent.objects.get(id=tag.db_data)
        except (Tag.DoesNotExist, Tag.MultipleObjectsReturned, AttributeError,
                TypeError, ValueError, RPEvent.DoesNotExist):
            return None

    @property
    def sender(self):
        senders = self.senders
        if senders:
            return senders[0]

    def get_sender_name(self, viewer):
        sender = self.sender
        if sender:
            if sender.db.longname:
                real_name = sender.db.longname
            else:
                real_name = sender.key
        else:
            real_name = "Unknown Sender"
        header = self.parse_header()
        fake_name = header.get('spoofed_name', None) or ""
        if not fake_name:
            return real_name
        if viewer.check_permstring("builders"):
            fake_name = "%s {w(%s){n" % (fake_name, real_name)
        return fake_name

    @property
    def ic_date(self):
        header = self.parse_header()
        return header.get('date', None) or ""


# different proxy classes for Msg objects
class Journal(MarkReadMixin, Msg):
    """
    Proxy model for Msg that represents an in-game journal written by a Character.
    """
    class Meta:
        proxy = True
    objects = JournalManager()
    white_journals = WhiteJournalManager()
    black_journals = BlackJournalManager()

    @property
    def writer(self):
        """The person who wrote this journal."""
        try:
            return self.senders[0]
        except IndexError:
            pass

    @property
    def relationship(self):
        """Character who a journal is written about."""
        try:
            return self.db_receivers_objects.all()[0]
        except IndexError:
            pass

    def __str__(self):
        relationship = self.relationship
        rel_txt = " on %s" % relationship.key if relationship else ""
        return "<Journal written by %s%s>" % (self.writer, rel_txt)

    def tag_favorite(self, player):
        """
        Tags this journal as a favorite by the player. We create a custom tag on the Journal to represent that.
        Args:
            player: Player tagging this journal as a favorite.
        """
        self.tags.add("pid_%s_favorite" % player.id)

    def untag_favorite(self, player):
        """
        Removes tag marking this journal as a favorite of the player if it's present.
        Args:
            player: Player removing this journal as a favorite.
        """
        self.tags.remove("pid_%s_favorite" % player.id)

    def add_black_locks(self):
        """Sets the locks for this message being black"""
        try:
            p_id = self.senders[0].player_ob.id
            blacklock = "read: perm(Builders) or pid(%s)." % p_id
        except (AttributeError, IndexError):
            blacklock = "read: perm(Builders)"
        self.locks.add(blacklock)

    def remove_black_locks(self):
        """Removes the lock for black journals"""
        self.locks.add("read: all()")
        
    def convert_to_black(self):
        """Converts this journal to a black journal"""
        self.db_header = self.db_header.replace("white", "black")
        self.tags.add(BLACK_TAG, category="msg")
        self.tags.remove(WHITE_TAG, category="msg")
        self.add_black_locks()
        self.save()

    def convert_to_white(self):
        """Converts this journal to a white journal"""
        self.db_header = self.db_header.replace("black", "white")
        self.tags.remove(BLACK_TAG, category="msg")
        self.tags.add(WHITE_TAG, category="msg")
        self.remove_black_locks()
        self.save()

    def reveal_black_journal(self):
        """Makes a black journal viewable to all - intended for posthumous releases"""
        self.remove_black_locks()
        self.tags.add(REVEALED_BLACK_TAG, category="msg")

    def hide_black_journal(self):
        """Hides a black journal again, for fixing errors"""
        self.add_black_locks()
        self.tags.remove(REVEALED_BLACK_TAG, category="msg")

    @property
    def is_public(self):
        """Whether this journal is visible to the public without an access check"""
        tags = self.tags.all()
        return WHITE_TAG in tags or REVEALED_BLACK_TAG in tags


class Messenger(MarkReadMixin, Msg):
    """
    Proxy model for Msg that represents an in-game messenger sent by a Character.
    """
    class Meta:
        proxy = True
    objects = MessengerManager()

    @property
    def preserved(self):
        return self.tags.get(PRESERVE_TAG, category=TAG_CATEGORY)

    def preserve(self):
        self.tags.add(PRESERVE_TAG, category=TAG_CATEGORY)

    def add_receiver(self, character):
        """
        Adds a character to our list of object receivers. This indicates that they're intended to receive the
        messenger, though it may still be pending.
        Args:
            character: Character object to add to our list of receivers.
        """
        self.db_receivers_objects.add(character)


class Rumor(MarkReadMixin, Msg):
    """
    Proxy model for Msg that represents an in-game rumor written by a Character.
    """
    class Meta:
        proxy = True
    objects = RumorManager()


class Post(MarkReadMixin, Msg):
    """
    Proxy model for Msg that represents an ooc bulletin board post.
    """
    class Meta:
        proxy = True
    objects = PostManager()

    @property
    def bulletin_board(self):
        """Returns the bulletin board this post is attached to"""
        from typeclasses.bulletin_board.bboard import BBoard
        result = self.db_receivers_objects.filter(db_typeclass_path=BBoard.path).first()

        if result is None:
            result = self.db_receivers_objects.first()

        return result

    @property
    def poster_name(self):
        """Returns the name of the entity that posted this"""
        if self.db_sender_external:
            return self.db_sender_external
        sender = ""
        if self.db_sender_accounts.exists():
            sender += ", ".join(str(ob).capitalize() for ob in self.db_sender_accounts.all())
        if self.db_sender_objects.exists():
            if sender:
                sender += ", "
            sender += ", ".join(str(ob).capitalize() for ob in self.db_sender_objects.all())
        if not sender:
            sender = "No One"
        return sender
