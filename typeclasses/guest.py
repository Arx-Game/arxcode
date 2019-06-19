"""

Guest is a child of default Player class.

"""
from .accounts import Account

CMDSET_GUEST = "commands.cmdsets.cmdset_guest.GuestCmdSet"


class Guest(Account):
    """
    See Player object for API. Will be overloading most methods to customize.
    """
    
    def at_account_creation(self):
        """
        This is called once, the very first time
        the player is created (i.e. first time they
        register with the game). It's a good place
        to store attributes all players should have,
        like configuration values etc.
        """
        # set an (empty) attribute holding the characters this player has
        lockstring = "attrread:perm(Wizards);attredit:perm(Wizards);attrcreate:perm(Wizards)"
        self.attributes.add("_playable_characters", [], lockstring=lockstring)
        self.db.mails = []
        self.db.newmail = False
        self.db.readmails = set()
        self.db.tutorial_stage = 0
        self.db.char = None

    def at_post_login(self, session=None):
        """
        Called at the end of the login process, just before letting
        them loose. This is called before an eventual Character's
        at_post_login hook.
        """
        self.db.tutorial_stage = 0
        self._send_to_connect_channel("{G%s connected{n" % self.key)
        self.email = "dummy@dummy.com"
        self.db.player_email = None
        self.db.char = None
        self.db._saved_protocol_flags = {}
        # In theory ndb values should not need to be initalized, but was
        # seeing them persistent on reconnect cases
        self.ndb.email = None
        self.ndb.seen_stage1_intro = False
        self.ndb.seen_stage2_intro = False
        self.ndb.seen_stage3_intro = False
        self.ndb.seen_stage4_intro = False
        
        # The tutorial for a guest will be a series of overloaded look
        # commands, returning different results based on the current
        # tutorial stage value. 0 will be the entry window.
        self.execute_cmd("addcom guest")
        self.execute_cmd("@bbsub/quiet wanted concepts")
        self.execute_cmd("@bbsub/quiet story updates")
        self.cmdset.remove("more_commands")
        self.execute_cmd("l")
        
    def is_guest(self):
        """
        Overload in guest object to return True
        """
        return True

    def basetype_setup(self):
        """
        This sets up the basic properties for a player.
        Overload this with at_player_creation rather than
        changing this method.

        """
        # the text encoding to use.
        self.db.encoding = "utf-8"

        # A basic security setup
        lockstring = "examine:perm(Wizards);edit:perm(Wizards);delete:perm(Wizards);boot:perm(Wizards);msg:all()"
        self.locks.add(lockstring)

        # The ooc player cmdset
        self.cmdset.add_default(CMDSET_GUEST, permanent=True)

    def at_disconnect(self, reason=None):
        """
        Called just before user is disconnected.
        """
        self.execute_cmd("allcom off")
        self.db.player_email = None
        self.db.char = None
        self.db.tutorial_stage = 0
        self.email = "dummy@dummy.com"
        reason = reason and "(%s)" % reason or ""
        self._send_to_connect_channel("{R%s disconnected %s{n" % (self.key, reason))

    def _send_to_connect_channel(self, message):
        try:
            from evennia.comms.models import ChannelDB
            from django.utils import timezone
            chan = ChannelDB.objects.get(db_key__iexact="guest")
            now = timezone.now()
            now = "%02i:%02i" % (now.hour, now.minute)
            chan.tempmsg("[%s]: %s" % (now, message))
            gm_chan = ChannelDB.objects.get(db_key__iexact="staffinfo")
            addr = self.sessions.all()[0].address
            message += " from %s" % addr
            gm_chan.msg(message)
        except Exception as err:
            import traceback
            traceback.print_exc()
            print("Error in logging messages to guest channel: %s" % err)
