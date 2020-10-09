from server.utils.test_utils import ArxCommandTest
from world.stat_checks import check_commands
from world.stat_checks.models import (
    DifficultyRating,
    RollResult,
    NaturalRollType,
    StatWeight,
)
from unittest.mock import Mock, patch


@patch("world.stat_checks.check_maker.randint")
class TestCheckCommands(ArxCommandTest):
    def setUp(self):
        super().setUp()
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

    def test_stat_check_cmd_private(self, mock_randint):
        # Test private roll messaging
        # Self-only private roll.
        mock_randint.return_value = 25
        self.call_cmd(
            "dex at normal=me",
            f"[Private Roll] {self.char1} checks dex at {self.normal}. {self.char1} rolls marginal. (Shared with: self-only)",
        )

        # Sharing with another character.
        # Note that the 'me' gets removed because it's redundant.
        self.call_cmd(
            "dex at normal=me,char2",
            f"[Private Roll] {self.char1} checks dex at {self.normal}. {self.char1} rolls marginal. (Shared with: char2)",
        )

        # Test that copy-pasting names aren't going to spam.
        self.call_cmd(
            "dex at normal=char2,char2",
            f"[Private Roll] {self.char1} checks dex at {self.normal}. {self.char1} rolls marginal. (Shared with: char2)",
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
            "Char has called for an opposing check. Char checks dex and melee at easy. Char rolls marginal. "
            "Char2 checks intelligence at easy. Char2 rolls marginal.\nThe rolls are tied.",
            options=self.options,
        )
        self.char2.traits.set_stat_value("intelligence", 50)
        self.call_cmd(f"/vs dex + melee vs intelligence={self.char2}", "")
        self.mock_announce.assert_called_with(
            "Char has called for an opposing check. Char checks dex and melee at easy. Char rolls marginal. "
            "Char2 checks intelligence at easy. Char2 rolls okay.\nChar2 is the winner.",
            options=self.options,
        )
