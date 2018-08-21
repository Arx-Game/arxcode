"""
Tests for dominion stuff. Crisis commands, etc.
"""
from mock import patch

from server.utils.test_utils import ArxCommandTest
from . import crisis_commands, commands


class TestCrisisCommands(ArxCommandTest):
    def setUp(self):
        super(TestCrisisCommands, self).setUp()
        from world.dominion.models import Crisis, CrisisAction
        self.crisis = Crisis.objects.create(name="test crisis", escalation_points=100)
        self.action = self.crisis.actions.create(dompc=self.dompc2, actions="test action", outcome_value=50, 
                                                 status=CrisisAction.PENDING_PUBLISH)
        
    @patch("world.dominion.models.inform_staff")
    @patch("world.dominion.models.get_week")
    def test_cmd_gm_crisis(self, mock_get_week, mock_inform_staff):
        self.cmd_class = crisis_commands.CmdGMCrisis
        self.caller = self.account
        mock_get_week.return_value = 1
        self.call_cmd("/create test crisis2/ermagerd headline=test desc", 
                      "Crisis created. Make gemits or whatever for it.")
        with patch('server.utils.arx_utils.broadcast_msg_and_post') as mock_msg_and_post:
            from web.character.models import Story, Chapter, Episode
            chapter = Chapter.objects.create(name="test chapter")
            Episode.objects.create(name="test episode", chapter=chapter)
            Story.objects.create(name="test story", current_chapter=chapter)
            self.call_cmd("/update 1=test gemit/test note", "You have updated the crisis.")
            mock_msg_and_post.assert_called_with("test gemit", self.caller, episode_name="test episode")
            mock_inform_staff.assert_called_with('Crisis update posted by Testaccount for test crisis:\nGemit:\ntest '
                                                 'gemit\nGM Notes: test note\nPending actions published: 1\nAlready '
                                                 'published actions for this update: ', post=True,
                                                 subject='Update for test crisis')
            self.call_cmd("1", "Name: test crisis\nDescription: None\nCurrent Rating: 50\nLatest Update:\ntest gemit")
            self.call_cmd("/update 1/another test episode/test synopsis=test gemit 2",
                          "You have updated the crisis, creating a new episode called 'another test episode'.")
            mock_msg_and_post.assert_called_with("test gemit 2", self.caller, episode_name="another test episode")
        
    def test_cmd_view_crisis(self):
        self.cmd_class = crisis_commands.CmdViewCrisis
        self.caller = self.account
        self.call_cmd("1", "Name: test crisis\nDescription: None\nCurrent Rating: 100")


class TestGeneralDominionCommands(ArxCommandTest):
    @patch("world.dominion.models.randint")
    @patch("world.dominion.models.get_week")
    @patch('world.dominion.models.do_dice_check')
    def test_cmd_work(self, mock_dice_check, mock_get_week, mock_randint):
        from world.dominion.models import Organization, AssetOwner
        org = Organization.objects.create(name="Orgtest")
        org_owner = AssetOwner.objects.create(organization_owner=org)
        member = org.members.create(player=self.dompc)
        self.cmd_class = commands.CmdWork
        self.caller = self.account
        self.call(self.cmd_class(), args="", msg="Command does not exist. Please see 'help work'.", 
                  caller=self.caller, cmdstring="task")
        self.call_cmd("", "Must give a name and type of resource.")
        self.call_cmd("asdf, 5", "No match for an org by the name: asdf.")
        self.call_cmd("Orgtest, 5", "Type must be one of these: Economic, Military, Social.")
        self.roster_entry.action_points = 0
        self.call_cmd("Orgtest, economic", "You cannot afford the AP cost to work.")
        self.roster_entry.action_points = 100
        mock_dice_check.return_value = -5
        mock_get_week.return_value = 0
        self.char1.db.intellect = 5
        self.char1.db.composure = 5
        mock_randint.return_value = 5
        self.call_cmd("Orgtest, economic", 'You use 15 action points and have 85 remaining this week.|'
                                           'Your social clout reduces difficulty by 1.\n'
                                           'Char rolling intellect and economics. You have gained 5 economic resources.'
                                           '|Orgtest has new @informs. Use @informs/org Orgtest/1 to read them.')
        mock_dice_check.return_value = 20
        self.call_cmd("Orgtest, economic", 'You use 15 action points and have 70 remaining this week.|'
                                           'Your social clout reduces difficulty by 1.\n'
                                           'Char rolling intellect and economics. You have gained 6 economic resources.'
                                           '|Orgtest has new @informs. Use @informs/org Orgtest/1 to read them.')
        self.call_cmd("Orgtest, economic=Char2", "No protege by that name.")
        self.dompc2.patron = self.dompc
        self.dompc2.save()
        self.char2.db.charm = 10
        self.char2.db.intellect = 5
        self.char2.db.composure = 5
        self.call_cmd("Orgtest, economic=TestAccount2",
                      'You use 15 action points and have 55 remaining this week.|'
                      'Your social clout combined with that of your protege reduces difficulty by 22.\n'
                      'Char rolling intellect and economics. You have gained 7 economic resources.'
                      '|Orgtest has new @informs. Use @informs/org Orgtest/1 to read them.')
        self.assertEqual(self.assetowner2.economic, 2)
        self.assertEqual(self.assetowner.economic, 18)
        self.assertEqual(org_owner.economic, 3)
        self.assertEqual(member.work_this_week, 3)
        self.call_cmd("/invest orgtest,economic=testaccount2", "You must specify at least 10 resources to invest.")
        self.call_cmd("/invest orgtest,economic,20=testaccount2", "You cannot afford to pay 20 resources.")
        self.call_cmd("/invest orgtest,economic,18=testaccount2",
                      'You use 5 action points and have 50 remaining this week.|'
                      'Your social clout combined with that of your protege reduces difficulty by 22.\n'
                      'Char rolling intellect and economics. \n'
                      'You and Orgtest both gain 4000 prestige.\n'
                      'You have increased the economic influence of Orgtest by 25.\n'
                      'Current modifier is 0, progress to next is 1/100.')
        self.call_cmd("/score orgtest2", "No match for an org by the name: orgtest2.")
        self.call_cmd("/score orgtest", 'Member      Total Work Total Invested Combined \n'
                                        'Testaccount 3          25             28')
