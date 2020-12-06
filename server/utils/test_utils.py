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
from typeclasses.accounts import Account
from typeclasses.characters import Character
from typeclasses.exits import Exit
from typeclasses.objects import Object
from typeclasses.rooms import ArxRoom
from world.stat_checks.models import (
    DifficultyRating,
    RollResult,
    StatWeight,
    StatCheckOutcome,
    DamageRating,
    StatCombination,
    StatCheck,
    TraitsInCombination,
    CheckCondition,
    CheckDifficultyRule,
    NaturalRollType,
)
from world.traits.models import Trait

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
    # series of flags for generating other data
    HAS_COMBAT_DATA = False

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
        from world.traits.models import Trait

        self.active_roster = Roster.objects.create(name="Active")
        self.setup_aliases()
        self.setup_arx_characters()
        Trait._cache_set = False
        StatWeight._cache_set = False
        StatCheck._cache_set = False
        RollResult._cache_set = False
        DamageRating._cache_set = False
        DifficultyRating._cache_set = False

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

        setattr(
            self,
            "account%s" % number,
            create.create_account(
                "TestAccount%s" % number,
                email="test@test.com",
                password="testpassword",
                typeclass=self.account_typeclass,
            ),
        )
        setattr(
            self,
            "char%s" % number,
            create.create_object(
                self.character_typeclass,
                key="Char%s" % number,
                location=self.room1,
                home=self.room1,
            ),
        )

    def setup_character_and_account(self, character, account, num=""):
        """Sets up a character/account combo with RosterEntry, dompc, etc."""
        from world.dominion.setup_utils import setup_dom_for_player, setup_assets

        # the attributes that are for 1 don't have a number
        if num == 1:
            num = ""
        num = str(num)
        setattr(self, "dompc%s" % num, setup_dom_for_player(account))
        setattr(
            self, "assetowner%s" % num, setup_assets(getattr(self, "dompc%s" % num), 0)
        )
        setattr(
            self,
            "roster_entry%s" % num,
            self.active_roster.entries.create(
                player=getattr(self, "account%s" % num),
                character=getattr(self, "char%s" % num),
            ),
        )

    @property
    def fake_datetime(self):
        import datetime

        return datetime.datetime(1978, 8, 27, 12, 8, 0)

    @classmethod
    def get_or_create(cls, targcls, **kwargs):
        obj, _ = targcls.objects.get_or_create(**kwargs)
        targcls._cache_set = False
        return obj

    @classmethod
    def setUpTestData(cls):
        if cls.HAS_COMBAT_DATA:
            cls.generate_combat_data()

    @classmethod
    def generate_combat_data(cls):
        cls.get_or_create(
            DamageRating, name="severe", value=70, max_value=110, armor_percentage=25
        )
        # all the stuff needed for harm
        StatCheck.objects.all().delete()
        StatCombination.objects.filter(combined_into__isnull=False).delete()
        StatCombination.objects.all().delete()
        death_save_system = StatCombination.objects.create()
        death_save = cls.get_or_create(
            StatCheck,
            name="death save",
            dice_system=death_save_system,
            description="A check to stay alive. Success indicates the character lives.",
        )
        # set traits used for death save
        armor_class = cls.get_or_create(
            Trait,
            name="armor_class",
            defaults=dict(category="combat", trait_type=Trait.OTHER),
        )
        cls.get_or_create(
            Trait,
            name="boss_rating",
            defaults=dict(category="combat", trait_type=Trait.OTHER),
        )
        cls.get_or_create(
            Trait,
            name="bonus_max_hp",
            defaults=dict(category="combat", trait_type=Trait.OTHER),
        )
        stamina = cls.get_or_create(Trait, name="stamina")
        willpower = cls.get_or_create(Trait, name="willpower")
        luck = cls.get_or_create(Trait, name="luck")
        cls.get_or_create(Trait, name="strength")
        cls.get_or_create(Trait, name="dexterity")
        cls.get_or_create(Trait, name="charm")
        cls.get_or_create(Trait, name="command")
        cls.get_or_create(Trait, name="composure")
        cls.get_or_create(Trait, name="intellect")
        cls.get_or_create(Trait, name="mana")
        cls.get_or_create(Trait, name="wits")
        cls.get_or_create(Trait, name="perception")
        cls.get_or_create(Trait, name="archery", defaults=dict(trait_type=Trait.SKILL))
        cls.get_or_create(
            Trait, name="athletics", defaults=dict(trait_type=Trait.SKILL)
        )
        cls.get_or_create(Trait, name="brawl", defaults=dict(trait_type=Trait.SKILL))
        cls.get_or_create(Trait, name="dodge", defaults=dict(trait_type=Trait.SKILL))
        cls.get_or_create(Trait, name="huge wpn", defaults=dict(trait_type=Trait.SKILL))
        cls.get_or_create(
            Trait, name="medium wpn", defaults=dict(trait_type=Trait.SKILL)
        )
        cls.get_or_create(
            Trait, name="small wpn", defaults=dict(trait_type=Trait.SKILL)
        )
        cls.get_or_create(Trait, name="stealth", defaults=dict(trait_type=Trait.SKILL))
        cls.get_or_create(Trait, name="survival", defaults=dict(trait_type=Trait.SKILL))
        cls.get_or_create(Trait, name="ride", defaults=dict(trait_type=Trait.SKILL))
        cls.get_or_create(
            Trait, name="leadership", defaults=dict(trait_type=Trait.SKILL)
        )
        cls.get_or_create(Trait, name="war", defaults=dict(trait_type=Trait.SKILL))
        higher_of_willpower_or_luck = cls.get_or_create(
            StatCombination,
            combination_type=StatCombination.USE_HIGHEST,
            combined_into=death_save_system,
        )
        cls.get_or_create(
            TraitsInCombination,
            trait=willpower,
            stat_combination=higher_of_willpower_or_luck,
        )
        cls.get_or_create(
            TraitsInCombination,
            trait=luck,
            stat_combination=higher_of_willpower_or_luck,
        )
        cls.get_or_create(
            TraitsInCombination, trait=stamina, stat_combination=death_save_system
        )
        cls.get_or_create(
            TraitsInCombination, trait=armor_class, stat_combination=death_save_system
        )
        # we map different difficulties to check conditions that are the percent of missing health
        # easy is when they have 100% of their health missing - they just hit 0
        easy_condition = cls.get_or_create(CheckCondition, value=100)
        easy = cls.get_or_create(DifficultyRating, name="easy", defaults={"value": 25})
        normal_condition = cls.get_or_create(CheckCondition, value=125)
        normal = cls.get_or_create(
            DifficultyRating, name="normal", defaults={"value": 50}
        )
        hard_condition = cls.get_or_create(CheckCondition, value=150)
        hard = cls.get_or_create(DifficultyRating, name="hard", defaults={"value": 75})
        daunting_condition = cls.get_or_create(CheckCondition, value=195)
        daunting = cls.get_or_create(
            DifficultyRating, name="daunting", defaults={"value": 95}
        )
        cls.get_or_create(
            CheckDifficultyRule,
            stat_check=death_save,
            situation=easy_condition,
            difficulty=easy,
            description="The character is expected to survive, but can still die.",
        )
        cls.get_or_create(
            CheckDifficultyRule,
            stat_check=death_save,
            situation=normal_condition,
            difficulty=normal,
            description="Seriously wounded - the character has a good chance of death.",
        )
        cls.get_or_create(
            CheckDifficultyRule,
            stat_check=death_save,
            situation=hard_condition,
            difficulty=hard,
            description="Very serious wounds - more fragile characters are likely to die.",
        )
        cls.get_or_create(
            CheckDifficultyRule,
            stat_check=death_save,
            situation=daunting_condition,
            difficulty=daunting,
            description="Extremely dire wounds - the character is very likely to die.",
        )
        fail = cls.get_or_create(
            RollResult,
            name="marginally fails",
            defaults=dict(value=-15, template="{{character}} |512{{result}}|n."),
        )
        success = cls.get_or_create(
            RollResult,
            name="marginally successful",
            defaults=dict(value=0, template="{{character}} is |240{{result}}|n."),
        )
        cls.get_or_create(
            RollResult,
            name="inhumanly successful",
            defaults=dict(
                value=151,
                template="|542{% if crit %}{{ crit|title }}! {% endif %}{{character}} is "
                "{{result}} in a way that defies expectations.|n",
            ),
        )
        cls.get_or_create(
            StatCheckOutcome,
            stat_check=death_save,
            result=fail,
            description="The character dies on any failure result.",
        )
        cls.get_or_create(
            StatCheckOutcome,
            stat_check=death_save,
            result=success,
            description="The character lives on any success result.",
        )
        # unconsciousness save
        uncon_save_system = StatCombination.objects.create()
        uncon_save = cls.get_or_create(
            StatCheck,
            name="unconsciousness save",
            dice_system=uncon_save_system,
            description="A check to stay conscious. Failure is being knocked out.",
        )
        cls.get_or_create(
            TraitsInCombination, trait=stamina, stat_combination=uncon_save_system
        )
        easy_condition = cls.get_or_create(
            CheckCondition, value=1, condition_type=CheckCondition.HEALTH_BELOW_100
        )
        normal_condition = cls.get_or_create(
            CheckCondition, value=26, condition_type=CheckCondition.HEALTH_BELOW_100
        )
        hard_condition = cls.get_or_create(
            CheckCondition, value=51, condition_type=CheckCondition.HEALTH_BELOW_100
        )
        daunting_condition = cls.get_or_create(
            CheckCondition, value=76, condition_type=CheckCondition.HEALTH_BELOW_100
        )
        cls.get_or_create(
            CheckDifficultyRule,
            stat_check=uncon_save,
            situation=easy_condition,
            difficulty=easy,
            description="The character is expected to stay conscious, "
            "but can still be knocked out.",
        )
        cls.get_or_create(
            CheckDifficultyRule,
            stat_check=uncon_save,
            situation=normal_condition,
            difficulty=normal,
            description="The character has a good chance of being knocked out.",
        )
        cls.get_or_create(
            CheckDifficultyRule,
            stat_check=uncon_save,
            situation=hard_condition,
            difficulty=hard,
            description="The character is likely to be knocked out.",
        )
        cls.get_or_create(
            CheckDifficultyRule,
            stat_check=uncon_save,
            situation=daunting_condition,
            difficulty=daunting,
            description="The character is very likely to lose consciousness.",
        )
        cls.get_or_create(
            StatCheckOutcome,
            stat_check=uncon_save,
            result=fail,
            description="The character falls unconscious on any failure result.",
        )
        cls.get_or_create(
            StatCheckOutcome,
            stat_check=uncon_save,
            result=success,
            description="The character remains conscious on any success result.",
        )

        # permanent wound save
        perm_wound_system = StatCombination.objects.create()
        perm_wound_save = cls.get_or_create(
            StatCheck,
            name="permanent wound save",
            dice_system=perm_wound_system,
            description="A check to avoid suffering permanent effects from wounds.",
        )
        cls.get_or_create(
            TraitsInCombination, trait=stamina, stat_combination=perm_wound_system
        )
        normal_condition = cls.get_or_create(
            CheckCondition,
            value=30,
            condition_type=CheckCondition.PERCENT_HEALTH_INFLICTED,
        )
        hard_condition = cls.get_or_create(
            CheckCondition,
            value=45,
            condition_type=CheckCondition.PERCENT_HEALTH_INFLICTED,
        )
        daunting_condition = cls.get_or_create(
            CheckCondition,
            value=60,
            condition_type=CheckCondition.PERCENT_HEALTH_INFLICTED,
        )
        cls.get_or_create(
            CheckDifficultyRule,
            stat_check=perm_wound_save,
            situation=normal_condition,
            difficulty=normal,
            description="The character has a good chance of taking a lingering wound.",
        )
        cls.get_or_create(
            CheckDifficultyRule,
            stat_check=perm_wound_save,
            situation=hard_condition,
            difficulty=hard,
            description="The character is likely to have a lingering wound.",
        )
        cls.get_or_create(
            CheckDifficultyRule,
            stat_check=perm_wound_save,
            situation=daunting_condition,
            difficulty=daunting,
            description="The character is very likely to have a permanent, lasting wound.",
        )
        botch = cls.get_or_create(
            RollResult,
            name="catastrophically fails",
            defaults=dict(
                value=-160,
                template="{% if botch %}{{ botch|title }}! {% endif %}{{character}} |505{{result}}|n.",
            ),
        )
        normal_fail = cls.get_or_create(
            RollResult,
            name="fails",
            defaults=dict(value=-60, template="{{character}} |r{{result}}|n."),
        )
        cls.get_or_create(
            NaturalRollType,
            name="critical success",
            defaults=dict(value=96, result_shift=1),
        )
        cls.get_or_create(
            NaturalRollType,
            name="botch",
            defaults=dict(value=5, value_type=1, result_shift=-1),
        )
        cls.get_or_create(
            StatCheckOutcome,
            stat_check=perm_wound_save,
            result=botch,
            description="The character takes a permanent wound on botches/catastrophic failures.",
        )
        cls.get_or_create(
            StatCheckOutcome,
            stat_check=perm_wound_save,
            result=normal_fail,
            description="The character takes a serious wound on failure/marginal failure.",
        )
        cls.get_or_create(
            StatCheckOutcome,
            stat_check=perm_wound_save,
            result=success,
            description="The character does not suffer a permanent wound on success.",
        )
        cls.get_or_create(
            StatWeight, stat_type=StatWeight.HEALTH_STA, level=0, weight=75
        )
        cls.get_or_create(
            StatWeight, stat_type=StatWeight.HEALTH_STA, level=1, weight=25
        )
        cls.get_or_create(
            StatWeight, stat_type=StatWeight.HEALTH_BOSS, level=1, weight=100
        )
        cls.get_or_create(StatWeight, stat_type=StatWeight.MISC)


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
    def call(
        self,
        cmdobj,
        args,
        msg=None,
        cmdset=None,
        noansi=True,
        caller=None,
        receiver=None,
        cmdstring=None,
        obj=None,
        inputs=None,
        raw_string=None,
    ):
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
            stored_msg = [
                args[0]
                if args and args[0]
                else kwargs.get("text", utils.to_str(kwargs))
                for name, args, kwargs in receiver.msg.mock_calls
            ]
            # Get the first element of a tuple if msg received a tuple instead of a string
            stored_msg = [
                smsg[0]
                if not isinstance(smsg, str) and hasattr(smsg, "__iter__")
                else str(smsg)
                for smsg in stored_msg
            ]
            if msg is not None:
                returned_msg = self.format_returned_msg(stored_msg, noansi)
                if msg == "" and returned_msg or returned_msg != msg.strip():
                    sep1 = "\n" + "=" * 30 + "Wanted message" + "=" * 34 + "\n"
                    sep2 = "\n" + "=" * 30 + "Returned message" + "=" * 32 + "\n"
                    sep3 = "\n" + "=" * 78
                    # important - use raw strings for wanted/returned messages so we can see whitespace
                    retval = "%s%r%s%r%s" % (
                        sep1,
                        msg.strip(),
                        sep2,
                        returned_msg,
                        sep3,
                    )
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
        from world.dominion.models import (
            Organization,
            AssetOwner,
            CraftingRecipe,
            CraftingMaterialType,
        )

        wearable_typeclass = Wearable
        purse_typeclass = WearableContainer
        weapon_typeclass = Wieldable
        hairpin_typeclass = DecorativeWieldable
        mask_typeclass = Mask
        self.org = Organization.objects.create(name="Orgtest")
        AssetOwner.objects.create(organization_owner=self.org)
        self.org.members.create(player=self.dompc)
        self.mat1 = CraftingMaterialType.objects.create(name="Mat1", value=100)
        self.recipe1 = CraftingRecipe.objects.create(
            name="Top 1 Slot",
            ability="tailor",
            primary_amount=5,
            level=5,
            result="slot:chest;slot_limit:1;baseval:1;penalty:2",
        )
        self.recipe2 = CraftingRecipe.objects.create(
            name="Top 2 Slot",
            ability="leatherworker",
            primary_amount=6,
            level=6,
            result="slot:chest;slot_limit:2",
        )
        self.recipe3 = CraftingRecipe.objects.create(
            name="Bag",
            ability="leatherworker",
            primary_amount=5,
            level=5,
            result="slot:bag;slot_limit:2;baseval:40",
        )
        self.recipe4 = CraftingRecipe.objects.create(
            name="Small Weapon",
            ability="weaponsmith",
            primary_amount=4,
            level=4,
            result="baseval:1;weapon_skill:small wpn",
        )
        self.recipe5 = CraftingRecipe.objects.create(
            name="Hairpins",
            ability="weaponsmith",
            primary_amount=4,
            level=4,
            result="slot:hair;slot_limit:2;baseval:4;",
        )
        self.recipe6 = CraftingRecipe.objects.create(
            name="Mask",
            ability="apothecary",
            primary_amount=4,
            level=4,
            result="slot:face;slot_limit:1;fashion_mult:6",
        )
        self.recipe7 = CraftingRecipe.objects.create(
            name="Medium Weapon",
            ability="weaponsmith",
            primary_amount=4,
            level=4,
            result="baseval:5",
        )
        self.test_recipes = [
            self.recipe1,
            self.recipe2,
            self.recipe3,
            self.recipe4,
            self.recipe5,
            self.recipe6,
            self.recipe7,
        ]
        for recipe in self.test_recipes:
            recipe.primary_materials.add(self.mat1)
            recipe.locks.add("learn:all();teach:all()")
            recipe.save()
        # Top1 is a wearable object with no recipe or crafter designated
        self.top1 = create.create_object(
            wearable_typeclass, key="Top1", location=self.room1, home=self.room1
        )
        self.top1.db.quality_level = 6
        # Top2 is a 1-slot_limit chest Wearable made by non-staff char2
        self.top2 = create.create_object(
            wearable_typeclass, key="Top2", location=self.char2, home=self.room1
        )
        self.top2.db.quality_level = 6
        self.top2.db.recipe = 1
        self.top2.db.crafted_by = self.char2
        # Slinkity1 is chest 2-slot_limit, so can stack once with chest-wearables. Also has adorns
        self.catsuit1 = create.create_object(
            wearable_typeclass, key="Slinkity1", location=self.char2, home=self.room1
        )
        self.catsuit1.db.quality_level = 11
        self.catsuit1.db.recipe = 2
        self.catsuit1.db.crafted_by = self.char2
        self.catsuit1.db.adorns = {1: 200}
        # Purse1 is a wearable container; baseval is their capacity
        self.purse1 = create.create_object(
            purse_typeclass, key="Purse1", location=self.char2, home=self.room1
        )
        self.purse1.db.quality_level = 4
        self.purse1.db.recipe = 3
        self.purse1.db.crafted_by = self.char2
        # Imps leer when they lick a knife
        self.knife1 = create.create_object(
            weapon_typeclass, key="Lickyknife1", location=self.char2, home=self.room1
        )
        self.knife1.db.quality_level = 11
        self.knife1.db.recipe = 4
        self.knife1.db.crafted_by = self.char2
        self.knife1.db.attack_skill = self.knife1.recipe.resultsdict.get(
            "weapon_skill", "medium wpn"
        )
        # A larger weapon
        self.sword1 = create.create_object(
            weapon_typeclass, key="Sword1", location=self.char2, home=self.room1
        )
        self.sword1.db.quality_level = 6
        self.sword1.db.recipe = 7
        self.sword1.db.crafted_by = self.char2
        self.sword1.db.attack_skill = self.sword1.recipe.resultsdict.get(
            "weapon_skill", "medium wpn"
        )
        # Hairpins1 is a decorative weapon and should always show as 'worn' rather than 'sheathed'
        self.hairpins1 = create.create_object(
            hairpin_typeclass, key="Hairpins1", location=self.char2, home=self.room1
        )
        self.hairpins1.db.quality_level = 4
        self.hairpins1.db.recipe = 5
        self.hairpins1.db.crafted_by = self.char2
        self.hairpins1.db.attack_skill = self.hairpins1.recipe.resultsdict.get(
            "weapon_skill", "small wpn"
        )
        # Masks change wearer identity and are restricted from being worn by 0 quality
        self.mask1 = create.create_object(
            mask_typeclass, key="A Fox Mask", location=self.char2, home=self.room1
        )
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


class TestTicketMixins(object):
    def setUp(self):
        from web.helpdesk.models import Ticket, Queue

        super(TestTicketMixins, self).setUp()
        self.q_req = Queue.objects.create(slug="Request", title="Request for GM action")
        self.q_bug = Queue.objects.create(
            slug="Bugs", title="Bug reports/Technical issues"
        )
        self.q_typ = Queue.objects.create(slug="Typo", title="Typos")
        self.q_cod = Queue.objects.create(slug="Code", title="Coding Requests/Wishlist")
        self.q_prp = Queue.objects.create(slug="PRP", title="PRP Questions")
        self.q_sto = Queue.objects.create(slug="Story", title="Story Actions")
        pout = Ticket.objects.create
        with patch("django.utils.timezone.now", Mock(return_value=self.fake_datetime)):
            self.tix1 = pout(
                title="Bishi too easy",
                queue=self.q_bug,
                submitter_email="sly@vix.com",
                submitting_player=self.account2,
                submitting_room=self.room,
                description="Galvanion didn't last longer than three minutes. Wtf.",
            )
            self.tix2 = pout(
                title="Let me kill a bishi?",
                queue=self.q_req,
                submitter_email="sly@vix.com",
                submitting_player=self.account2,
                submitting_room=self.room,
                description="Somehow Darain is still alive, as a paladin. Can't let it slide.",
            )
            self.tix3 = pout(
                title="Sly Spareaven?",
                queue=self.q_typ,
                submitter_email="sly@vix.com",
                submitting_player=self.account2,
                submitting_room=self.room,
                priority=5,
                description="What's a Spareaven anyway? I am -the- sexiest Deraven.",
            )
            self.tix4 = pout(
                title="Command for licking paladins",
                queue=self.q_cod,
                submitter_email="sly@vix.com",
                submitting_player=self.account2,
                submitting_room=self.room,
                priority=4,
                description="Need a command to let me steal souls like Poison. /lick maybe?",
            )
            self.tix5 = pout(
                title="Bring Sexy Back",
                queue=self.q_prp,
                submitter_email="sly@vix.com",
                submitting_player=self.account2,
                submitting_room=self.room,
                description="Propose an event with so many shy bishis, and 0 Dark Princesses.",
            )
            self.tix6 = pout(
                title="Poison too hot",
                queue=self.q_bug,
                submitter_email="sly@vix.com",
                submitting_player=self.account2,
                submitting_room=self.room,
                priority=1,
                description="Let's make Poison an Iksar. Scaled for his pleasure?",
            )
            # this ticket's player is char1 instead:
            self.tix7 = pout(
                title="3 Raccoons in a Trenchcoat",
                queue=self.q_sto,
                submitter_email="p@ison.com",
                submitting_player=self.account,
                submitting_room=self.room,
                description="Just when you thought you'd met the perfect girl.",
            )
