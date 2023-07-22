"""
Tests for commands associated with typeclasses, or typeclass functionality.
We'll use the Arx CommandTest class, which is a subclass of Evennia's testcases
that leverage django's testrunner.
"""
from unittest.mock import patch

from typeclasses.rooms import CmdExtendedLook
from server.utils.test_utils import ArxCommandTest


class ArxRoomTests(ArxCommandTest):
    """Tests commands associated with ArxRoom, such as CmdExtendedLook."""

    @patch("typeclasses.scripts.gametime.get_time_and_season")
    def test_extended_look(self, mock_get_time_and_season):
        """
        Tests the CmdExtendedLook class. We'll set different seasonal descriptions,
        permanent descriptions, and temporary descriptions with and without time of
        day tags in order to determine that the correct strings are being returned.
        We'll set these values in self.room1, as that's the default room being used
        for commands as the caller's location.
        """
        # call setup_cmd to set up the command for CmdExtendedLook
        self.setup_cmd(CmdExtendedLook, self.char1)
        # give room a permanent description with no time of day tags
        desc = "This is a test room."
        self.room1.desc = desc
        # player made rooms have special caching, we'll make sure that is stripped
        self.room1.tags.add("player_made_room")
        mock_get_time_and_season.return_value = ("spring", "morning")

        def get_full_desc(base_desc):
            """helper function that adds footer and header to desc"""
            return f"Room\n{base_desc}\nExits: out\nCharacters: Char, Char2\nObjects: Obj, Obj2"

        # basic case - desc with no seasonal descriptions or time of day tags
        self.call_cmd("", get_full_desc(desc))

        # add time of day tags to desc
        morning = "It is morning in the test room."
        desc = f"<morning>{morning}</morning>"
        afternoon = "It is afternoon in the test room."
        desc += f"<afternoon>{afternoon}</afternoon>"
        evening = "It is evening in the test room."
        desc += f"<evening>{evening}</evening>"
        night = "It is night in the test room."
        desc += f"<night>{night}</night>"
        self.room1.desc = desc
        for time_desc in ("morning", "afternoon", "evening", "night"):
            with self.subTest(f"Testing time of day: {time_desc}"):
                mock_get_time_and_season.return_value = ("spring", time_desc)
                self.call_cmd("", get_full_desc(locals()[time_desc]))

        for season in ("spring", "summer", "autumn", "winter"):
            with self.subTest(f"Testing seasonal description: {season}"):
                mock_get_time_and_season.return_value = (season, "morning")
                desc = f"It is {season} in the test room."
                setattr(self.room1.item_data, f"{season}_description", desc)
                self.call_cmd("", get_full_desc(desc))
