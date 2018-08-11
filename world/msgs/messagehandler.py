"""
Messagehandler

This handler takes either a AccountDB or ObjectDB object and
processes the Msg objects they have in their related sets.
Msg() objects will be distinguished in how they function based
on their header field, which we'll parse and process here. The
header field will be a list of key:value pairs, separated by
semicolons.
"""

from server.utils.arx_utils import get_date, create_arx_message
from .handler_mixins import messengerhandler, journalhandler, msg_utils
from .managers import (VISION_TAG)


class MessageHandler(messengerhandler.MessengerHandler, journalhandler.JournalHandler):
    """Handler for most messages"""
    def __init__(self, obj=None):
        """
        We'll be doing a series of delayed calls to set up the various
        attributes in the MessageHandler, since we can't have ObjectDB
        refer to Msg during the loading-up process.
        """
        # the ObjectDB instance
        super(MessageHandler, self).__init__(obj)
        # comments that obj has received about it
        self._rumors = None
        self._gossip = None
        self._visions = None

    @property
    def rumors(self):
        if self._rumors is None:
            self.build_rumorslist()
        return self._rumors

    @property
    def gossip(self):
        if self._gossip is None:
            self.build_gossiplist()
        return self._gossip

    @property
    def visions(self):
        """Visions received by the character"""
        if self._visions is None:
            self.build_visionslist()
        return self._visions

    # ---------------------------------------------------------
    # Setup/building methods
    # ---------------------------------------------------------
    
    def build_rumorslist(self):
        """
        Returns a list of all rumor entries which we've heard (marked as a receiver for)
        """
        self._rumors = list(msg_utils.get_initial_queryset("Rumor").about_character(self.obj))
        return self._rumors
    
    def build_gossiplist(self):
        """
        Returns a list of all gossip entries we've heard (marked as a receiver for)
        """
        if self.obj.player_ob:
            self._gossip = list(msg_utils.get_initial_queryset("Rumor").all_read_by(self.obj.player_ob))
        else:
            self._gossip = self.build_rumorslist()

    def build_visionslist(self):
        """
        Returns a list of all messengers this character has received. Does not include pending.
        """
        self._visions = list(msg_utils.get_initial_queryset("Vision").about_character(self.obj))
        return self._visions

    # --------------------------------------------------------------
    # API/access methods
    # --------------------------------------------------------------

    def add_vision(self, msg, sender, vision_obj=None):
        """adds a vision sent by a god or whatever"""
        cls = msg_utils.lazy_import_from_str("Vision")
        date = get_date()
        header = "date:%s" % date
        if not vision_obj:
            vision_obj = create_arx_message(sender, msg, receivers=self.obj, header=header, cls=cls, tags=VISION_TAG)
        else:
            self.obj.receiver_object_set.add(vision_obj)
        if vision_obj not in self.visions:
            self.visions.append(vision_obj)
        return vision_obj

    # ---------------------------------------------------------------------
    # Display methods
    # ---------------------------------------------------------------------
        
    @property
    def num_flashbacks(self):
        """Flashbacks written by the player"""
        return self.obj.db.num_flashbacks or 0
        
    @num_flashbacks.setter
    def num_flashbacks(self, val):
        self.obj.db.num_flashbacks = val

    @property
    def num_weekly_journals(self):
        """Number of journal-type things that count for xp"""
        return self.num_journals + self.num_rel_updates + self.num_flashbacks

    def reset_journal_count(self):
        """Resetting our count of things which count for xp"""
        self.num_journals = 0
        self.num_rel_updates = 0
        self.num_flashbacks = 0
