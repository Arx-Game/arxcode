"""
Different classes for running Arx-specific tests, mostly configuring evennia's built-in test framework to work for
us. Some minor changes, like having their command tests print out raw strings so we don't need to guess what
whitespace characters don't match.
"""
import re

from mock import Mock, patch

from evennia.commands.default.tests import CommandTest
from evennia.server.sessionhandler import SESSIONS
from evennia.utils import ansi, utils
from evennia.utils.test_resources import EvenniaTest
from typeclasses.characters import Character
from typeclasses.accounts import Account
from typeclasses.objects import Object
from typeclasses.rooms import ArxRoom
from typeclasses.exits import Exit
from world.crafting.constants import INNER, OUTER


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
    char = None
    char1 = None
    account = None
    account1 = None
    room = None
    room1 = None
    obj = None
    obj1 = None

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

    def setup_character_and_account(self, character, account, num=1):
        """Sets up a character/account combo with RosterEntry, dompc, etc."""
        from world.dominion.setup_utils import setup_dom_for_player, setup_assets
        # the attributes that are for 1 don't have a number
        if num == 1:
            num = ""
        num = str(num)
        dompc = setup_dom_for_player(account)
        owner = setup_assets(dompc, 0)
        entry = self.active_roster.entries.create(player=account, character=character)
        setattr(self, 'dompc%s' % num, dompc)
        setattr(self, "assetowner%s" % num, owner)
        setattr(self, "roster_entry%s" % num, entry)

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
        return self.call(self.instance, args, msg, caller=self.caller, **kwargs)

    # noinspection PyBroadException
    def call(self, cmdobj, args, msg=None, cmdset=None, noansi=True, caller=None, receiver=None, cmdstring=None,
             obj=None, inputs=None, raw_string=None):
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
            stored_msg = [args[0] if args and args[0] else kwargs.get("text", utils.to_str(kwargs))
                          for name, args, kwargs in receiver.msg.mock_calls]
            # Get the first element of a tuple if msg received a tuple instead of a string
            stored_msg = [smsg[0] if not isinstance(smsg, str) and hasattr(smsg, '__iter__')
                          else str(smsg) for smsg in stored_msg]
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


# noinspection PyUnresolvedReferences
# noinspection PyAttributeOutsideInit
class TestEquipmentMixins(object):
    """
    Creation of Wearable and Wieldable items used for testing commands.
    """
    def setUp(self):
        super(TestEquipmentMixins, self).setUp()
        from world.dominion.models import Organization, AssetOwner
        from world.crafting.models import CraftingMaterialType
        from world.crafting.models import CraftingRecipe, WearableStats, RecipeRequirement
        wearable_typeclass = "typeclasses.wearable.wearable.Wearable"
        purse_typeclass = "typeclasses.wearable.wearable.WearableContainer"
        weapon_typeclass = "typeclasses.wearable.wieldable.Wieldable"
        small_weapon_typeclass = "typeclasses.wearable.wieldable.SmallWeapon"
        hairpin_typeclass = "typeclasses.wearable.decorative_weapon.DecorativeWieldable"
        mask_typeclass = "typeclasses.disguises.disguises.Mask"
        self.org = Organization.objects.create(name="Orgtest")
        AssetOwner.objects.create(organization_owner=self.org)
        self.org.members.create(player=self.dompc)
        self.mat1 = CraftingMaterialType.objects.create(name="Mat1", value=100)
        self.top1_recipe = CraftingRecipe.objects.create(name="Top 1 Slot", ability="tailor", level=5, baseval=1,
                                                         type=wearable_typeclass)
        WearableStats.objects.create(recipe=self.top1_recipe, slot="chest", slot_volume=100, penalty=2, layer=OUTER)
        self.top2_recipe = CraftingRecipe.objects.create(name="Top 2 Slot", ability="leatherworker", level=6,
                                                         type=wearable_typeclass)
        WearableStats.objects.create(recipe=self.top2_recipe, slot="chest", slot_volume=50, layer=INNER)
        self.purse_recipe = CraftingRecipe.objects.create(name="Bag", ability="leatherworker", level=5,
                                                          baseval=40, type=purse_typeclass)
        WearableStats.objects.create(recipe=self.purse_recipe, slot="bag", slot_volume=50)
        self.small_weapon_recipe = CraftingRecipe.objects.create(name="Small Weapon", ability="weaponsmith",
                                                                 level=4, baseval=1, type=small_weapon_typeclass)
        self.hairpin_recipe = CraftingRecipe.objects.create(name="Hairpins", ability="weaponsmith",
                                                            level=4, baseval=4, type=hairpin_typeclass)
        WearableStats.objects.create(recipe=self.hairpin_recipe, slot="hair", slot_volume=50)
        self.mask_recipe = CraftingRecipe.objects.create(name="Mask", ability="apothecary",
                                                         level=4, type=mask_typeclass)
        WearableStats.objects.create(recipe=self.mask_recipe, slot="face", slot_volume=100, fashion_mult=6)
        self.medium_weapon_recipe = CraftingRecipe.objects.create(name="Medium Weapon", ability="weaponsmith",
                                                                  level=4, baseval=5, type=weapon_typeclass)
        self.test_recipes = [self.top1_recipe, self.top2_recipe, self.purse_recipe, self.small_weapon_recipe,
                             self.hairpin_recipe, self.mask_recipe, self.medium_weapon_recipe]
        for recipe in self.test_recipes:
            RecipeRequirement.objects.create(recipe=recipe, type=self.mat1, amount=recipe.level)
        # Top1 is a wearable object with no crafter designated
        self.top_no_crafter = self.top1_recipe.create_object(quality=6, location=self.room1, home=self.room1)
        # Top2 is a 1-slot_limit chest Wearable made by non-staff char2
        self.top_with_crafter = self.top1_recipe.create_object(quality=6, crafter=self.char2, location=self.char2,
                                                               key="Top2", home=self.room1)
        # Slinkity1 is chest 2-slot_limit, so can stack once with chest-wearables. Also has adorns
        self.catsuit1 = self.top2_recipe.create_object(quality=11, crafter=self.char2, location=self.char2,
                                                       home=self.room1, adornment_map={self.mat1: 200}, key="Slinkity")
        # Purse1 is a wearable container; baseval is their capacity
        self.purse1 = self.purse_recipe.create_object(quality=4, crafter=self.char2, key="Purse1", location=self.char2,
                                                      home=self.room1)
        # Imps leer when they lick a knife
        self.knife1 = self.small_weapon_recipe.create_object(quality=11, crafter=self.char2, key="Lickyknife1",
                                                             location=self.char2, home=self.room1)
        # A larger weapon
        self.sword1 = self.medium_weapon_recipe.create_object(quality=6, crafter=self.char2, key="Sword1",
                                                              location=self.char2, home=self.room1)
        # Hairpins1 is a decorative weapon and should always show as 'worn' rather than 'sheathed'
        self.hairpins1 = self.hairpin_recipe.create_object(quality=4, crafter=self.char2, key="Hairpins1",
                                                           location=self.char2, home=self.room1)
        # Masks change wearer identity and are restricted from being worn by 0 quality
        self.mask1 = self.mask_recipe.create_object(crafter=self.char2, key="A Fox Mask", location=self.char2,
                                                    home=self.room1, disguise="A very Slyyyy Fox...", quality=0,
                                                    adornment_map={self.mat1: 20})

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


# noinspection PyUnresolvedReferences
# noinspection PyAttributeOutsideInit
class TestTicketMixins(object):
    def setUp(self):
        from web.helpdesk.models import Ticket, Queue
        super(TestTicketMixins, self).setUp()
        self.q_req = Queue.objects.create(slug="Request", title="Request for GM action")
        self.q_bug = Queue.objects.create(slug="Bugs", title="Bug reports/Technical issues")
        self.q_typ = Queue.objects.create(slug="Typo", title="Typos")
        self.q_cod = Queue.objects.create(slug="Code", title="Coding Requests/Wishlist")
        self.q_prp = Queue.objects.create(slug="PRP", title="PRP Questions")
        self.q_sto = Queue.objects.create(slug="Story", title="Story Actions")
        pout = Ticket.objects.create
        with patch('django.utils.timezone.now', Mock(return_value=self.fake_datetime)):
            self.tix1 = pout(title="Bishi too easy", queue=self.q_bug, submitter_email="sly@vix.com",
                             submitting_player=self.account2, submitting_room=self.room,
                             description="Galvanion didn't last longer than three minutes. Wtf.")
            self.tix2 = pout(title="Let me kill a bishi?", queue=self.q_req, submitter_email="sly@vix.com",
                             submitting_player=self.account2, submitting_room=self.room,
                             description="Somehow Darain is still alive, as a paladin. Can't let it slide.")
            self.tix3 = pout(title="Sly Spareaven?", queue=self.q_typ, submitter_email="sly@vix.com",
                             submitting_player=self.account2, submitting_room=self.room, priority=5,
                             description="What's a Spareaven anyway? I am -the- sexiest Deraven.")
            self.tix4 = pout(title="Command for licking paladins", queue=self.q_cod, submitter_email="sly@vix.com",
                             submitting_player=self.account2, submitting_room=self.room, priority=4,
                             description="Need a command to let me steal souls like Poison. /lick maybe?")
            self.tix5 = pout(title="Bring Sexy Back", queue=self.q_prp, submitter_email="sly@vix.com",
                             submitting_player=self.account2, submitting_room=self.room,
                             description="Propose an event with so many shy bishis, and 0 Dark Princesses.")
            self.tix6 = pout(title="Poison too hot", queue=self.q_bug, submitter_email="sly@vix.com",
                             submitting_player=self.account2, submitting_room=self.room, priority=1,
                             description="Let's make Poison an Iksar. Scaled for his pleasure?")
            # this ticket's player is char1 instead:
            self.tix7 = pout(title="3 Raccoons in a Trenchcoat", queue=self.q_sto, submitter_email="p@ison.com",
                             submitting_player=self.account, submitting_room=self.room,
                             description="Just when you thought you'd met the perfect girl.")
