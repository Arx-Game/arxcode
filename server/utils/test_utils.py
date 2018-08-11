"""
Different classes for running Arx-specific tests, mostly configuring evennia's built-in test framework to work for
us. Some minor changes, like having their command tests print out raw strings so we don't need to guess what
whitespace characters don't match.
"""
import re

from mock import Mock

from evennia.commands.default.tests import CommandTest
from evennia.server.sessionhandler import SESSIONS
from evennia.utils import ansi, utils
from evennia.utils.test_resources import EvenniaTest
from typeclasses.characters import Character
from typeclasses.accounts import Account
from typeclasses.objects import Object
from typeclasses.rooms import ArxRoom
from typeclasses.exits import Exit


# set up signal here since we are not starting the server

_RE = re.compile(r"^\+|-+\+|\+-+|--+|\|(?:\s|$)", re.MULTILINE)


class ArxTestConfigMixin(object):
    """
    Mixin for configuration of Evennia's test class. It adds a number of attributes we'll use during setUp.
    """
    account_typeclass = Account
    object_typeclass = Object
    character_typeclass = Character
    exit_typeclass = Exit
    room_typeclass = ArxRoom
    num_additional_characters = 0  # additional characters for this test
    BASE_NUM_CHARACTERS = 2  # constant set by Evennia
    dompc = None
    dompc2 = None
    assetowner = None
    assetowner2 = None
    roster_entry = None
    roster_entry2 = None
    
    @property
    def total_num_characters(self):
        """The total number of characters we'll have for this test"""
        return self.BASE_NUM_CHARACTERS + self.num_additional_characters
        
    def setup_aliases(self):
        """Setup aliases because the inconsistency drove me crazy"""
        self.char = self.char1
        self.account1 = self.account
        self.room = self.room1
        self.obj = self.obj1

    # noinspection PyAttributeOutsideInit
    def setUp(self):
        """Run for each testcase"""
        super(ArxTestConfigMixin, self).setUp()
        from web.character.models import Roster
        self.active_roster = Roster.objects.create(name="Active")
        self.setup_aliases()
        self.setup_arx_characters()
        
    def setup_arx_characters(self):
        """
        Creates any additional characters/accounts and initializes them all. Sets up
        their roster entries, dominion objects, asset owners, etc.
        """
        if self.num_additional_characters:
            first_additional = self.BASE_NUM_CHARACTERS + 1
            for num in range(first_additional, self.total_num_characters + 1):
                self.add_character(num)
        for num in range(1, self.total_num_characters + 1):
            character = getattr(self, "char%s" % num)
            account = getattr(self, "account%s" % num)
            self.setup_character_and_account(character, account, num)
        
    def add_character(self, number):
        """Creates another character/account of the given number"""
        from evennia.utils import create
        setattr(self, "account%s" % number, 
                create.create_account("TestAccount%s" % number, email="test@test.com", password="testpassword", 
                                      typeclass=self.account_typeclass))
        setattr(self, "char%s" % number,
                create.create_object(self.character_typeclass, key="Char%s" % number, 
                                     location=self.room1, home=self.room1))
        
    def setup_character_and_account(self, character, account, num=""):
        """Sets up a character/account combo with RosterEntry, dompc, etc."""
        from world.dominion.setup_utils import setup_dom_for_player, setup_assets
        # the attributes that are for 1 don't have a number
        if num == 1:
            num = ""
        num = str(num)
        setattr(self, 'dompc%s' % num, setup_dom_for_player(account))
        setattr(self, "assetowner%s" % num, setup_assets(getattr(self, "dompc%s" % num), 0))
        setattr(self, "roster_entry%s" % num, 
                self.active_roster.entries.create(player=getattr(self, "account%s" % num),
                                                  character=getattr(self, "char%s" % num)))
            
    
class ArxTest(ArxTestConfigMixin, EvenniaTest):
    pass


class ArxCommandTest(ArxTestConfigMixin, CommandTest):
    """
    child of Evennia's CommandTest class specifically for Arx. We'll add some
    objects that our characters/players would be expected to have for any 
    particular test.
    """
    cmd_class = None
    caller = None

    def setup_cmd(self, cmd_cls, caller):
        self.cmd_class = cmd_cls
        self.caller = caller

    def call_cmd(self, args, msg, **kwargs):
        self.call(self.cmd_class(), args, msg, caller=self.caller, **kwargs)

    # noinspection PyBroadException
    def call(self, cmdobj, args, msg=None, cmdset=None, noansi=True, caller=None, receiver=None, cmdstring=None,
             obj=None):
        """
        Test a command by assigning all the needed
        properties to cmdobj and  running
            cmdobj.at_pre_cmd()
            cmdobj.parse()
            cmdobj.func()
            cmdobj.at_post_cmd()
        The msgreturn value is compared to eventual
        output sent to caller.msg in the game

        Returns:
            msg (str): The received message that was sent to the caller.

        """
        caller = caller if caller else self.char1
        receiver = receiver if receiver else caller
        cmdobj.caller = caller
        cmdobj.cmdstring = cmdstring if cmdstring else cmdobj.key
        cmdobj.args = args
        cmdobj.cmdset = cmdset
        cmdobj.session = SESSIONS.session_from_sessid(1)
        cmdobj.account = self.account
        cmdobj.raw_string = cmdobj.key + " " + args
        cmdobj.obj = obj or (caller if caller else self.char1)
        # test
        old_msg = receiver.msg
        try:
            receiver.msg = Mock()
            if cmdobj.at_pre_cmd():
                return
            cmdobj.parse()
            cmdobj.func()
            cmdobj.at_post_cmd()
        except Exception:
            import traceback
            receiver.msg(traceback.format_exc())
        finally:
            # clean out prettytable sugar. We only operate on text-type
            stored_msg = [args[0] if args and args[0] else kwargs.get("text", utils.to_str(kwargs, force_string=True))
                          for name, args, kwargs in receiver.msg.mock_calls]
            # Get the first element of a tuple if msg received a tuple instead of a string
            stored_msg = [smsg[0] if hasattr(smsg, '__iter__') else smsg for smsg in stored_msg]
            if msg is not None:
                returned_msg = self.format_returned_msg(stored_msg, noansi)
                if msg == "" and returned_msg or returned_msg != msg.strip():
                    sep1 = "\n" + "="*30 + "Wanted message" + "="*34 + "\n"
                    sep2 = "\n" + "="*30 + "Returned message" + "="*32 + "\n"
                    sep3 = "\n" + "="*78
                    # important - use raw strings for wanted/returned messages so we can see whitespace
                    retval = "%s%r%s%r%s" % (sep1, msg.strip(), sep2, returned_msg, sep3)
                    raise AssertionError(retval)
            else:
                returned_msg = "\n".join(str(msg) for msg in stored_msg)
                returned_msg = ansi.parse_ansi(returned_msg, strip_ansi=noansi).strip()
            receiver.msg = old_msg
        return returned_msg

    @staticmethod
    def format_returned_msg(stored_msg, no_ansi):
        """
        Formats the stored_msg list into a single string joined by separators
        Args:
            stored_msg: list of strings that have been sent to our receiver
            no_ansi: whether to strip ansi or not

        Returns:
            A string joined by | for each substring in stored_msg. Ansi will
            be stripped if no_ansi is specified.
        """
        returned_msg = "||".join(_RE.sub("", str(mess)) for mess in stored_msg)
        returned_msg = ansi.parse_ansi(returned_msg, strip_ansi=no_ansi).strip()
        return returned_msg
