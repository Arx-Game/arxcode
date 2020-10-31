from world.prayer.prayer_commands import CmdGMPray, CmdPray

from server.utils.test_utils import ArxCommandTest


class TestPrayerCommands(ArxCommandTest):
    def test_cmdpray(self):
        self.setup_cmd(CmdPray, self.char1)

    def test_gmpray(self):
        self.setup_cmd(CmdGMPray, self.char1)
