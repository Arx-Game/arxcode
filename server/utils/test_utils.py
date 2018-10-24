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

    @property
    def fake_datetime(self):
        import datetime
        return datetime.datetime(1978, 8, 27, 12, 8, 0)


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
    instance = None

    def setup_cmd(self, cmd_cls, caller):
        self.cmd_class = cmd_cls
        self.caller = caller
        self.instance = self.cmd_class()

    def call_cmd(self, args, msg, **kwargs):
        if not self.instance:
            self.instance = self.cmd_class()
        self.call(self.instance, args, msg, caller=self.caller, **kwargs)

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


class TestEquipmentMixins(object):
    """
    Creation of Wearable and Wieldable items used for testing commands.
    """
    def setUp(self):
        super(TestEquipmentMixins, self).setUp()
        from evennia.utils import create
        from typeclasses.wearable.wearable import Wearable, WearableContainer
        from typeclasses.disguises.disguises import Mask
        from typeclasses.wearable.wieldable import Wieldable
        from typeclasses.wearable.decorative_weapon import DecorativeWieldable
        from world.dominion.models import Organization, AssetOwner, CraftingRecipe, CraftingMaterialType
        wearable_typeclass = Wearable
        purse_typeclass = WearableContainer
        weapon_typeclass = Wieldable
        hairpin_typeclass = DecorativeWieldable
        mask_typeclass = Mask
        self.org = Organization.objects.create(name="Orgtest")
        AssetOwner.objects.create(organization_owner=self.org)
        self.org.members.create(player=self.dompc)
        self.mat1 = CraftingMaterialType.objects.create(name="Mat1", value=100)
        self.recipe1 = CraftingRecipe.objects.create(name="Top 1 Slot", ability="tailor",
                                                     primary_amount=5, level=5,
                                                     result="slot:chest;slot_limit:1;baseval:1;penalty:2")
        self.recipe2 = CraftingRecipe.objects.create(name="Top 2 Slot", ability="leatherworker",
                                                     primary_amount=6, level=6,
                                                     result="slot:chest;slot_limit:2")
        self.recipe3 = CraftingRecipe.objects.create(name="Bag", ability="leatherworker",
                                                     primary_amount=5, level=5,
                                                     result="slot:bag;slot_limit:2;baseval:40")
        self.recipe4 = CraftingRecipe.objects.create(name="Small Weapon", ability="weaponsmith",
                                                     primary_amount=4, level=4,
                                                     result="baseval:1;weapon_skill:small wpn")
        self.recipe5 = CraftingRecipe.objects.create(name="Hairpins", ability="weaponsmith",
                                                     primary_amount=4, level=4,
                                                     result="slot:hair;slot_limit:2;baseval:4;")
        self.recipe6 = CraftingRecipe.objects.create(name="Mask", ability="apothecary",
                                                     primary_amount=4, level=4,
                                                     result="slot:face;slot_limit:1;fashion_mult:6")
        self.recipe7 = CraftingRecipe.objects.create(name="Medium Weapon", ability="weaponsmith",
                                                     primary_amount=4, level=4,
                                                     result="baseval:5")
        self.test_recipes = [self.recipe1, self.recipe2, self.recipe3, self.recipe4, self.recipe5,
                             self.recipe6, self.recipe7]
        for recipe in self.test_recipes:
            recipe.primary_materials.add(self.mat1)
            recipe.locks.add("learn:all();teach:all()")
            recipe.save()
        # Top1 is a wearable object with no recipe or crafter designated
        self.top1 = create.create_object(wearable_typeclass, key="Top1", location=self.room1, home=self.room1)
        self.top1.db.quality_level = 6
        # Top2 is a 1-slot_limit chest Wearable made by non-staff char2
        self.top2 = create.create_object(wearable_typeclass, key="Top2", location=self.char2,
                                         home=self.room1)
        self.top2.db.quality_level = 6
        self.top2.db.recipe = 1
        self.top2.db.crafted_by = self.char2
        # Slinkity1 is chest 2-slot_limit, so can stack once with chest-wearables. Also has adorns
        self.catsuit1 = create.create_object(wearable_typeclass, key="Slinkity1", location=self.char2,
                                         home=self.room1)
        self.catsuit1.db.quality_level = 11
        self.catsuit1.db.recipe = 2
        self.catsuit1.db.crafted_by = self.char2
        self.catsuit1.db.adorns = {1: 200}
        # Purse1 is a wearable container; baseval is their capacity
        self.purse1 = create.create_object(purse_typeclass, key="Purse1", location=self.char2,
                                           home=self.room1)
        self.purse1.db.quality_level = 4
        self.purse1.db.recipe = 3
        self.purse1.db.crafted_by = self.char2
        # Imps leer when they lick a knife
        self.knife1 = create.create_object(weapon_typeclass, key="Lickyknife1", location=self.char2,
                                           home=self.room1)
        self.knife1.db.quality_level = 11
        self.knife1.db.recipe = 4
        self.knife1.db.crafted_by = self.char2
        self.knife1.db.attack_skill = self.knife1.recipe.resultsdict.get("weapon_skill", "medium wpn")
        # A larger weapon
        self.sword1 = create.create_object(weapon_typeclass, key="Sword1", location=self.char2,
                                           home=self.room1)
        self.sword1.db.quality_level = 6
        self.sword1.db.recipe = 7
        self.sword1.db.crafted_by = self.char2
        self.sword1.db.attack_skill = self.sword1.recipe.resultsdict.get("weapon_skill", "medium wpn")
        # Hairpins1 is a decorative weapon and should always show as 'worn' rather than 'sheathed'
        self.hairpins1 = create.create_object(hairpin_typeclass, key="Hairpins1", location=self.char2,
                                              home=self.room1)
        self.hairpins1.db.quality_level = 4
        self.hairpins1.db.recipe = 5
        self.hairpins1.db.crafted_by = self.char2
        self.hairpins1.db.attack_skill = self.hairpins1.recipe.resultsdict.get("weapon_skill", "small wpn")
        # Masks change wearer identity and are restricted from being worn by 0 quality
        self.mask1 = create.create_object(mask_typeclass, key="A Fox Mask", location=self.char2,
                                          home=self.room1)
        self.mask1.db.quality_level = 0
        self.mask1.db.recipe = 6  # mask also has fashion_mult:6
        self.mask1.db.crafted_by = self.char2
        self.mask1.db.maskdesc = "A very Slyyyy Fox..."
        self.mask1.db.adorns = {1: 20}

    def start_ze_fight(self):
        """Helper to start a fight and add the current caller."""
        from commands.cmdsets import combat
        fight = combat.start_fight_at_room(self.room1)
        fight.add_combatant(self.caller)
        return fight

    def create_ze_outfit(self, name):
        """Helper to create an outfit from current caller's equipped stuff."""
        from world.fashion.models import FashionOutfit as Outfit
        outfit = Outfit.objects.create(name=name, owner=self.caller.dompc)
        worn = list(self.caller.worn)
        weapons = list(self.caller.wielded) + list(self.caller.sheathed)
        for weapon in weapons:
            slot = "primary weapon" if weapon.is_wielded else "sheathed weapon"
            outfit.add_fashion_item(item=weapon, slot=slot)
        for item in worn:
            outfit.add_fashion_item(item=item)
        return outfit

    def add_recipe_additional_costs(self, val):
        """Adds additional_cost to recipes and saves them."""
        for recipe in self.test_recipes:
            recipe.additional_cost = val
            recipe.save()

    def match_recipe_locks_to_level(self):
        """Replaces with locks appropriate to recipe difficulty."""
        for recipe in self.test_recipes:
            lvl = recipe.level
            lockstr = "learn: ability(%s)" % lvl
            if lvl < 6:
                lockstr += ";teach: ability(%s)" % (lvl + 1)
            recipe.locks.replace(lockstr)
            recipe.save()
