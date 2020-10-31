from world.prayer.prayer_commands import CmdPray
from world.prayer.models import InvocableEntity

from server.utils.test_utils import ArxCommandTest
from unittest.mock import patch


class TestPrayerCommands(ArxCommandTest):
    def setUp(self):
        super().setUp()
        InvocableEntity.objects.create(name="Gloria")

    @patch("world.prayer.prayer_commands.inform_staff")
    def test_cmdpray(self, mock_inform):
        self.setup_cmd(CmdPray, self.char1)
        self.call_cmd("gloria=hi", "You pray to Gloria.")
        self.assertEqual(1, self.char1.prayers.count())
        mock_inform.assert_called()
