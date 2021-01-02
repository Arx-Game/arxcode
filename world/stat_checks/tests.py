from unittest.mock import Mock, patch, PropertyMock

from server.utils.test_utils import ArxCommandTest
from world.stat_checks import check_commands
from world.stat_checks.check_maker import SimpleRoll
from world.stat_checks.constants import DEATH_SAVE
from world.stat_checks.models import (
    DifficultyRating,
    RollResult,
    NaturalRollType,
    StatWeight,
    StatCheckOutcome,
)
from world.stat_checks.utils import get_check_by_name
from world.traits.models import Trait


@patch("world.stat_checks.check_maker.randint")
class TestCheckCommands(ArxCommandTest):
    def setUp(self):
        super().setUp()
        DifficultyRating.objects.all().delete()
        StatWeight.objects.all().delete()
        NaturalRollType.objects.all().delete()
        StatCheckOutcome.objects.all().delete()
        RollResult.objects.all().delete()
        self.easy = DifficultyRating.objects.create(name="easy", value=0)
        self.normal = DifficultyRating.objects.create(name="Normal", value=25)
        template = "{% if natural_roll_type %}{{natural_roll_type|title}}! {% endif %}{{character}} rolls {{result}}."
        self.marginal = RollResult.objects.create(
            name="marginal", value=-20, template=template
        )
        self.okay = RollResult.objects.create(name="okay", value=45, template=template)
        self.omg = RollResult.objects.create(
            name="a crit yay!!!!", value=300, template=template
        )
        self.botch = RollResult.objects.create(
            name="a botch - boo!!!", value=-100, template=template
        )
        StatWeight.objects.create(stat_type=StatWeight.ONLY_STAT, weight=5, level=1)
        StatWeight.objects.create(stat_type=StatWeight.STAT, weight=1, level=1)
        StatWeight.objects.create(stat_type=StatWeight.SKILL, weight=5, level=1)
        StatWeight.objects.create(stat_type=StatWeight.KNACK, weight=50, level=1)
        NaturalRollType.objects.create(name="crit", value=99, result_shift=2)
        NaturalRollType.objects.create(
            name="botch",
            value=2,
            value_type=NaturalRollType.UPPER_BOUND,
            result_shift=-2,
        )
        self.setup_cmd(check_commands.CmdStatCheck, self.char1)
        self.mock_announce = Mock()
        self.char1.msg_location_or_contents = self.mock_announce
        self.options = {"roll": True}
        Trait.objects.get_or_create(
            name="melee", trait_type=Trait.SKILL, category=Trait.COMBAT
        )
        Trait.objects.get_or_create(
            name="dex", trait_type=Trait.STAT, category=Trait.PHYSICAL
        )
        Trait.objects.get_or_create(
            name="intelligence", trait_type=Trait.STAT, category=Trait.MENTAL
        )

    def test_stat_check_cmd_normal(self, mock_randint):
        # test help message fetches Difficulty Ratings from lookup table
        help_msg = self.instance.get_help(None, None)
        self.assertIn("easy", help_msg)
        self.assertIn("Normal", help_msg)
        # check to see if the memory model cache has added case-insensitive key
        self.assertEqual(self.normal, DifficultyRating.get_instance_by_name("normal"))
        self.call_cmd("foo", "Usage: stat [+ skill] at <difficulty rating>")
        self.call_cmd("dex at foo", "'foo' is not a valid difficulty rating.")
        # check that a normal roll works
        mock_randint.return_value = 25
        self.call_cmd("dex at normal", "")
        self.char1.msg_location_or_contents.assert_called_with(
            f"{self.char1} checks dex at {self.normal}. {self.char1} rolls marginal.",
            options=self.options,
        )
        # check that we can trigger a higher value result
        self.char1.traits.set_stat_value("dex", 5)
        self.call_cmd("dex at easy", "")
        self.char1.msg_location_or_contents.assert_called_with(
            f"{self.char1} checks dex at {self.easy}. {self.char1} rolls okay.",
            options=self.options,
        )
        # check a crit
        mock_randint.return_value = 99
        self.call_cmd("dex at normal", "")
        self.char1.msg_location_or_contents.assert_called_with(
            f"{self.char1} checks dex at {self.normal}. Crit! {self.char1} rolls a crit yay!!!!.",
            options=self.options,
        )
        # check a botch
        mock_randint.return_value = 1
        self.call_cmd("dex at normal", "")
        self.char1.msg_location_or_contents.assert_called_with(
            f"{self.char1} checks dex at {self.normal}. Botch! {self.char1} rolls a botch - boo!!!.",
            options=self.options,
        )

    @patch("server.utils.notifier.Notifier._filter_gms")
    def test_stat_check_cmd_private(self, mock_gms, mock_randint):
        """Test private roll messaging."""
        # Setup extra characters.
        self.add_character(3)
        self.add_character(4)
        self.setup_character_and_account(self.char3, self.account3, 3)
        self.setup_character_and_account(self.char4, self.account4, 4)

        mock_randint.return_value = 25

        mock_gms.return_value = set()
        # (Staff) Char shares with self -> Char only gets it.
        self.call_cmd(
            "dex at normal=Char",
            f"[Private Roll] {self.char1} checks dex at {self.normal}. {self.char1} rolls marginal. (Shared with: Char)",
        )

        # Char3 shares with self -> Char3, Char get it
        # (Char gets it for being staff)
        # Note Char's name is last because of being a staff-flagged character.
        self.call(
            self.instance,
            "dex at normal=char3",
            f"[Private Roll] {self.char3} checks dex at {self.normal}. {self.char3} rolls marginal. (Shared with: Char3, Char)",
            caller=self.char3,
        )

        mock_gms.return_value = {self.char2}
        # (Staff) Char shares with (GM) Char2, Char4 -> Char2, Char4, Char get it
        # Char3 should NOT get it.
        self.call_cmd(
            "dex at normal=char2,char4",
            f"[Private Roll] {self.char1} checks dex at {self.normal}. {self.char1} rolls marginal. (Shared with: Char2, Char4, Char)",
        )

        mock_gms.return_value = set()
        # Char4 shares with Char3 -> Char3, Char4, Char get it.
        # Char2 should NOT get it.
        self.call(
            self.instance,
            "dex at normal=char3",
            f"[Private Roll] {self.char4} checks dex at {self.normal}. {self.char4} rolls marginal. (Shared with: Char3, Char4, Char)",
            caller=self.char4,
        )

        mock_gms.return_value = {self.char2}
        # Char3 shares with (GM) Char2 -> Char2, Char3, Char get it.
        # Char4 should NOT get it.
        self.call(
            self.instance,
            "dex at normal=char2",
            f"[Private Roll] {self.char3} checks dex at {self.normal}. {self.char3} rolls marginal. (Shared with: Char2, Char3, Char)",
            caller=self.char3,
        )

        mock_gms.return_value = set()
        # Char4 shares with Char3 -> Char3, Char4, Char get it.
        # Char2 should NOT get it.
        self.call(
            self.instance,
            "dex at normal=char3",
            f"[Private Roll] {self.char4} checks dex at {self.normal}. {self.char4} rolls marginal. (Shared with: Char3, Char4, Char)",
            caller=self.char4,
        )

    def test_stat_check_cmd_contest(self, mock_randint):
        self.add_character(3)
        self.add_character(4)
        self.call(
            self.instance,
            "/contest",
            "You are not GMing an event in this room.",
            caller=self.char2,
        )
        self.call_cmd(
            "/contest", "You must specify the names of characters for the contest."
        )
        self.call_cmd(
            f"/contest {self.char1},foo=dex + running at normal",
            "Could not find 'foo'.|Nothing found.",
        )
        mock_randint.return_value = 25
        self.call_cmd("/contest/here", "Usage: stat [+ skill] at <difficulty rating>")
        self.char2.traits.set_skill_value("melee", 1)
        self.char2.mods.create_knack("test", "dex", "melee")
        valid_cmdstrings = [
            "/contest/here dex + melee at easy",
            f"/contest {self.char2},{self.char3},{self.char4}=dex + melee at easy",
        ]
        for cmdstring in valid_cmdstrings:
            with self.subTest(f"cmdstring == '{cmdstring}'"):
                self.call_cmd(cmdstring, "")
                self.mock_announce.assert_called_with(
                    "Char has called for a check of dex and melee at easy.\n"
                    "Char2 rolls okay.\n"
                    "TIE: Char3 rolls marginal. Char4 rolls marginal.",
                    options=self.options,
                )

    def test_stat_check_cmd_versus(self, mock_randint):
        mock_randint.return_value = 25
        self.call_cmd("/vs", "You must provide a target.")
        self.call_cmd("/vs blah blah=foo", "Could not find 'foo'.|Nothing found.")
        self.call_cmd(f"/vs blah blah={self.char2}", "Must provide two checks.")
        self.call_cmd(f"/vs dex + melee vs intelligence={self.char2}", "")
        self.mock_announce.assert_called_with(
            "\n|w*** Char has called for an opposing check with Char2. ***|n\n"
            "Char checks dex and melee at easy. Char rolls marginal.\n"
            "Char2 checks intelligence at easy. Char2 rolls marginal.\n"
            "*** The rolls are |ctied|n. ***",
            options=self.options,
        )
        self.char2.traits.set_stat_value("intelligence", 50)
        self.call_cmd(f"/vs dex + melee vs intelligence={self.char2}", "")
        self.mock_announce.assert_called_with(
            "\n|w*** Char has called for an opposing check with Char2. ***|n\n"
            "Char checks dex and melee at easy. Char rolls marginal.\n"
            "Char2 checks intelligence at easy. Char2 rolls okay.\n"
            "*** |cChar2|n is the winner. ***",
            options=self.options,
        )
        # test rolls ordering
        roll1 = SimpleRoll()
        # normal - diff results, diff values
        roll1.result_value = 20
        roll1.roll_result_object = self.okay
        roll2 = SimpleRoll()
        roll2.result_value = 0
        roll2.roll_result_object = self.omg
        self.assertLess(roll1, roll2)
        # same result, diff values
        roll1.roll_result_object = self.omg
        self.assertGreater(roll1, roll2)
        # tie
        roll2.result_value = 15
        self.assertEqual(roll1, roll2)


@patch("typeclasses.characters.Character.armor", new_callable=PropertyMock)
@patch("world.stat_checks.models.randint")
@patch("world.stat_checks.check_maker.randint")
class TestHarmCommands(ArxCommandTest):
    HAS_COMBAT_DATA = True

    def test_harm(self, mock_check_randint, mock_damage_randint, mock_armor):
        self.setup_cmd(check_commands.CmdHarm, self.char2)
        mock_damage_randint.return_value = 110
        mock_armor.return_value = 125
        self.char1.traits.set_other_value("armor_class", 25)
        mock_check_randint.return_value = 500
        self.call_cmd("foo", "Could not find 'foo'.")
        self.call_cmd(f"{self.char1}", "No damage rating found by that name.")
        self.call_cmd(
            f"{self.char1}=severe", "You may only harm others if GMing an event."
        )
        self.char2.permissions.add("builders")
        self.assertTrue(self.char.conscious)
        self.assertEqual(self.char.damage, 0)
        self.call_cmd(
            f"{self.char1}=severe",
            "Inflicting severe on Char.|"
            "Char checks 'permanent wound save' at hard. Critical Success! "
            "Char is inhumanly successful in a way that defies expectations.|"
            "Despite the terrible damage, Char does not take a permanent wound.|"
            "Char checks 'unconsciousness save' at daunting. Critical Success! "
            "Char is inhumanly successful in a way that defies expectations.|"
            "Char remains capable of fighting.",
        )
        self.assertEqual(self.char.damage, 60)
        mock_check_randint.return_value = 50
        self.call_cmd(
            f"{self.char1}=severe",
            "Inflicting severe on Char.|"
            "Char checks 'death save' at hard. Char is marginally successful.|"
            "Char remains alive, but close to death.|"
            "Char is incapacitated and falls unconscious.|"
            "Char checks 'permanent wound save' at hard. Char fails.",
        )
        self.assertFalse(self.char.conscious)
        self.assertEqual(self.char.damage, 120)
        self.assertEqual(
            str(get_check_by_name(DEATH_SAVE).dice_system),
            "Add Values Together: [Use the Highest Value: [luck, willpower], armor_class, stamina]",
        )


@patch("world.stat_checks.check_maker.randint")
class TestSpoofCommands(ArxCommandTest):
    """
    Tests the @gmcheck comand under the new @check system.
    """

    def setUp(self):
        super().setUp()
        DifficultyRating.objects.all().delete()
        StatWeight.objects.all().delete()
        NaturalRollType.objects.all().delete()
        StatCheckOutcome.objects.all().delete()
        RollResult.objects.all().delete()

        self.setup_cmd(check_commands.CmdSpoofCheck, self.char1)
        self.mock_announce = Mock()
        self.char1.msg_location_or_contents = self.mock_announce
        self.options = {"roll": True}

        self.easy = DifficultyRating.objects.create(name="easy", value=0)
        self.normal = DifficultyRating.objects.create(name="Normal", value=25)
        template = "{% if natural_roll_type %}{{natural_roll_type|title}}! {% endif %}{{character}} rolls {{result}}."
        self.marginal = RollResult.objects.create(
            name="marginal", value=-20, template=template
        )
        self.okay = RollResult.objects.create(name="okay", value=45, template=template)
        self.omg = RollResult.objects.create(
            name="a crit yay!!!!", value=300, template=template
        )
        self.botch = RollResult.objects.create(
            name="a botch - boo!!!", value=-100, template=template
        )

        StatWeight.objects.create(stat_type=StatWeight.ONLY_STAT, weight=5, level=1)
        StatWeight.objects.create(stat_type=StatWeight.STAT, weight=1, level=1)
        StatWeight.objects.create(stat_type=StatWeight.SKILL, weight=5, level=1)
        StatWeight.objects.create(stat_type=StatWeight.KNACK, weight=50, level=1)

        NaturalRollType.objects.create(name="crit", value=99, result_shift=2)
        NaturalRollType.objects.create(
            name="botch",
            value=2,
            value_type=NaturalRollType.UPPER_BOUND,
            result_shift=-2,
        )

        Trait.objects.get_or_create(
            name="strength", trait_type=Trait.STAT, category=Trait.PHYSICAL
        )
        Trait.objects.get_or_create(
            name="athletics", trait_type=Trait.SKILL, category=Trait.PHYSICAL
        )

    def test_stat_check_cmd_spoof(self, mock_randint):
        mock_randint.return_value = 25

        syntax_error = (
            "Usage: <stat>/<value> [+ <skill>/<value>] at difficulty=<npc name>"
        )

        # Incorrect syntax - not a normal @check
        self.call_cmd("strength at normal", syntax_error)

        # Incorrect syntax on including a skill
        self.call_cmd("strength/5 and athletics/5 at normal=NPC", syntax_error)
        self.call_cmd("strength/5 + athletics=5 at normal=NPC", syntax_error)

        # Invalid stat/skill
        self.call_cmd(
            "str/5 + athletics/5 at normal=NPC", "str is not a valid stat name."
        )
        self.call_cmd(
            "strength/5 + ath/5 at normal=NPC", "ath is not a valid skill name."
        )

        # Stat/skill being too high
        self.call_cmd(
            "strength/6 + athletics/5 at normal=NPC", "Stats cannot be higher than 5."
        )
        self.call_cmd(
            "strength/5 + athletics/7 at normal=NPC", "Skills cannot be higher than 6."
        )

        # Incorrect syntax on values
        syntax_error = 'Specify "name/value" for stats and skills.'
        self.call_cmd("strength+5 at normal=NPC", syntax_error)
        self.call_cmd("strength//5 + athletics/5 at normal=NPC", syntax_error)

        # Actual, normal rolling from here on out.
        result = f"NPC ({self.char1}) checks strength (5) and athletics (5) at {self.normal}. {self.char1} rolls marginal."
        self.call_cmd("strength/5 + athletics/5 at normal=NPC", result)
