"""
Tests for the Character app. Mostly this will be investigations/clue stuff.
"""
from mock import Mock, patch

from django.test import Client
from django.urls import reverse

from server.utils.test_utils import ArxCommandTest, ArxTest
from web.character import investigation, scene_commands
from web.character.models import Clue, Revelation, SearchTag


class InvestigationTests(ArxCommandTest):
    def setUp(self):
        super(InvestigationTests, self).setUp()
        self.clue = Clue.objects.create(name="test clue", rating=10, desc="test clue desc")
        self.clue2 = Clue.objects.create(name="test clue2", rating=50, desc="test clue2 desc")
        self.revelation = Revelation.objects.create(name="test revelation", desc="test rev desc",
                                                    required_clue_value=60)
        self.clue_disco = self.roster_entry.clue_discoveries.create(clue=self.clue, message="additional text test")

        self.revelation.clues_used.create(clue=self.clue)
        self.revelation.clues_used.create(clue=self.clue2)

    # noinspection PyUnresolvedReferences
    @patch("web.character.models.datetime")
    @patch.object(investigation, "datetime")
    def test_cmd_clues(self, mock_datetime, mock_roster_datetime):
        from datetime import datetime
        mock_datetime.now = Mock(return_value=datetime(2009, 1, 6, 15, 8, 24, 78915))
        mock_roster_datetime.now = Mock(return_value=datetime(2009, 1, 6, 15, 8, 24, 78915))
        now = mock_datetime.now()
        self.setup_cmd(investigation.CmdListClues, self.account)
        self.call_cmd("1", "test clue\nRating: 10\ntest clue desc\nadditional text test")
        self.call_cmd("/addnote 1=test note", "test clue\nRating: 10\ntest clue desc\nadditional text test"
                                              "\n[%s] TestAccount wrote: test note" % now.strftime("%x %X"))
        self.call_cmd("/share 1=", "Who are you sharing with?")
        self.call_cmd("/share 1=Testaccount2", "Sharing the clue(s) with them would cost 101 action points.")
        self.roster_entry.action_points = 202
        self.call_cmd("/share 1=Testaccount2", "You use 101 action points and have 101 remaining this week.|"
                                               "You have shared the clue(s) 'test clue' with Char2.")
        self.assertEqual(self.roster_entry.action_points, 101)
        self.call_cmd("/share 2=Testaccount2", "No clue found by this ID: 2. ")
        self.clue_disco2 = self.roster_entry.clue_discoveries.create(clue=self.clue2, message="additional text test2")
        self.assertFalse(bool(self.roster_entry2.revelations.all()))
        self.call_cmd("/share 2=Testaccount2/Love Tehom", "You use 101 action points and have 0 remaining this week.|"
                      "You have shared the clue(s) 'test clue2' with Char2.\nYour note: Love Tehom")
        self.assertTrue(bool(self.roster_entry2.revelations.all()))
        self.caller = self.account2
        self.call_cmd("2", "test clue2\nRating: 50\ntest clue2 desc\n%s This clue was shared with you by Char,"
                      " who noted: Love Tehom\n" % now.strftime("%x %X"))

    def test_cmd_helpinvestigate(self):
        self.roster_entry2.investigations.create()
        self.setup_cmd(investigation.CmdAssistInvestigation, self.char1)
        self.char1.db.investigation_invitations = [1]
        self.call_cmd("/new", 'Helping an investigation:|Investigation: |Story: |Stat: |Skill: '
                              '|Assisting Character: Char')
        self.call_cmd("/target 2", 'No investigation by that ID.')
        self.call_cmd("/target 1", 'Helping an investigation:|Investigation: 1|Story: |Stat: |Skill: '
                                   '|Assisting Character: Char')
        self.call_cmd("/finish", 'You must have a story defined.')
        self.call_cmd("/story test", 'Helping an investigation:|Investigation: 1|Story: test|Stat: |Skill: '
                                     '|Assisting Character: Char')
        with patch.object(self.cmd_class, 'check_enough_time_left') as fake_method:
            fake_method.return_value = True
            self.call_cmd("/finish", "Char is now helping Char2's investigation on .")


class SceneCommandTests(ArxCommandTest):
    def test_cmd_flashback(self):
        from web.character.models import Flashback
        self.setup_cmd(scene_commands.CmdFlashback, self.account)
        self.call_cmd("/create testing", "You have created a new flashback with the ID of #1.")
        self.call_cmd("/create testing", "There is already a flashback with that title. Please choose another.")
        self.call_cmd("1", "(#1) testing\nOwner: Char\nSummary: \nPosts: ")
        self.call_cmd("/catchup 1", "No new posts for #1.")
        self.account2.inform = Mock()
        self.call_cmd("/invite 1=Testaccount2", "You have invited Testaccount2 to participate in this flashback.")
        self.account2.inform.assert_called_with("You have been invited by Testaccount to participate in flashback #1:"
                                                " 'testing'.", category="Flashbacks")
        self.call_cmd("/post 1", "You must include a message.")                                            
        self.assertEqual(self.char1.messages.num_flashbacks, 0)
        self.call_cmd("/post 1=A new testpost", "You have posted a new message to testing: A new testpost")
        self.assertEqual(self.char1.messages.num_flashbacks, 1)
        self.account2.inform.assert_called_with("There is a new post on flashback #1 by Char.",
                                                category="Flashbacks")
        self.caller = self.account2
        self.call_cmd("/catchup 1", "New posts for #1\nChar wrote: A new testpost\n")
        self.call_cmd("/summary 1=test", "Only the flashback's owner may use that switch.")
        self.caller = self.account
        self.call_cmd("/uninvite 1=Testaccount2", "You have uninvited Testaccount2 from this flashback.")
        self.account2.inform.assert_called_with("You have been removed from flashback #1.", category="Flashbacks")
        self.call_cmd("/summary 1=test summary", "summary set to: test summary.")
        Flashback.objects.get(id=1).posts.create(poster=self.roster_entry, actions="Foo")
        self.call_cmd("1=foo", '(#1) testing\nOwner: Char\nSummary: test summary\nPosts:\n'
                               'Char wrote: A new testpost\nChar wrote: Foo')
        self.call_cmd("1=1", '(#1) testing\nOwner: Char\nSummary: test summary\nPosts:\nChar wrote: Foo')


class ViewTests(ArxTest):
    def setUp(self):
        super(ViewTests, self).setUp()
        self.client = Client()

    def test_sheet(self):
        response = self.client.get(self.char2.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['character'], self.char2)
        self.assertEqual(response.context['show_hidden'], False)
        self.assertEqual(self.client.login(username='TestAccount2', password='testpassword'), True)
        response = self.client.get(self.char2.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['show_hidden'], True)
        self.client.logout()

    def test_view_flashbacks(self):
        response = self.client.get(reverse('character:list_flashbacks', kwargs={'object_id': self.char2.id}))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.login(username='TestAccount2', password='testpassword'), True)
        response = self.client.get(reverse('character:list_flashbacks', kwargs={'object_id': self.char2.id}))
        self.assertEqual(response.status_code, 200)


class PRPClueTests(ArxCommandTest):
    def setUp(self):
        from world.dominion.models import Plot, PCPlotInvolvement
        super(PRPClueTests, self).setUp()
        self.plot = Plot.objects.create(name="TestPlot")
        self.plot.dompc_involvement.create(dompc=self.dompc, admin_status=PCPlotInvolvement.GM)

    def test_cmd_prpclue(self):
        self.setup_cmd(investigation.CmdPRPClue, self.account1)
        self.call_cmd("", 'Plots GMd: TestPlot (#1)\nClues Written: \nRevelations Written: \n|'
                          'You are not presently creating a Clue.')
        self.call_cmd("/finish", "Use /create to start a new form.")
        self.call_cmd("/create", 'Name: None\nDesc: None\nRevelation: None\nRating: None\nTags: None\nReal: True\n'
                                 'Can Investigate: True\nCan Share: True')
        self.call_cmd("/finish", 'Please correct the following errors:\nRating: This field is required.\n'
                                 'Name: This field is required.\nRevelation: This field is required.\n'
                                 'Desc: This field is required.')
        self.call_cmd("/name testclue", 'Name: testclue\nDesc: None\nRevelation: None\nRating: None\nTags: None\n'
                                        'Real: True\nCan Investigate: True\nCan Share: True')
        self.call_cmd("/desc testdesc", 'Name: testclue\nDesc: testdesc\nRevelation: None\nRating: None\nTags: None\n'
                                        'Real: True\nCan Investigate: True\nCan Share: True')
        self.call_cmd("/rating -5", 'Name: testclue\nDesc: testdesc\nRevelation: None\nRating: -5\nTags: None\n'
                                    'Real: True\nCan Investigate: True\nCan Share: True')
        self.call_cmd("/finish", 'Please correct the following errors:\n'
                                 'Rating: Ensure this value is greater than or equal to 1.\n'
                                 'Revelation: This field is required.')
        self.call_cmd("/rating 60", 'Name: testclue\nDesc: testdesc\nRevelation: None\nRating: 60\nTags: None\n'
                                    'Real: True\nCan Investigate: True\nCan Share: True')
        self.call_cmd("/finish", 'Please correct the following errors:\n'
                                 'Rating: Ensure this value is less than or equal to 50.\n'
                                 'Revelation: This field is required.')
        self.call_cmd("/rating foo", 'Name: testclue\nDesc: testdesc\nRevelation: None\nRating: foo\nTags: None\n'
                                     'Real: True\nCan Investigate: True\nCan Share: True')
        self.call_cmd("/finish", 'Please correct the following errors:\nRating: Enter a whole number.\n'
                                 'Revelation: This field is required.')
        self.call_cmd("/rating 25", 'Name: testclue\nDesc: testdesc\nRevelation: None\nRating: 25\nTags: None\n'
                                    'Real: True\nCan Investigate: True\nCan Share: True')
        Revelation.objects.create(name="test revelation", author=self.roster_entry)
        self.call_cmd("/revelation asdf", 'No Revelation by that name or number.\nPlots GMd: TestPlot (#1)\n'
                                          'Clues Written: \nRevelations Written: test revelation (#1)')
        self.call_cmd("/revelation test revelation", 'Name: testclue\nDesc: testdesc\nRevelation: test revelation\n'
                                                     'Plot: \nRating: 25\nTags: None\nReal: True\n'
                                                     'Can Investigate: True\nCan Share: True')
        self.call_cmd("/tags tag1,tag2,tag3,tag1", 'Name: testclue\nDesc: testdesc\nRevelation: test revelation\n'
                                                   'Plot: \nRating: 25\nTags: tag1,tag2,tag3,tag1\nReal: True\n'
                                                   'Can Investigate: True\nCan Share: True')
        self.call_cmd("/finish", 'testclue(#1) created.')
        self.assertEquals(SearchTag.objects.count(), 3)

    def test_cmd_prprevelation(self):
        self.setup_cmd(investigation.CmdPRPRevelation, self.account1)
        self.call_cmd("", 'Plots GMd: TestPlot (#1)\nClues Written: \nRevelations Written: \n|'
                          'You are not presently creating a Revelation.')
        self.call_cmd("/finish", "Use /create to start a new form.")
        self.call_cmd("/create", 'Name: None\nDesc: None\nPlot: None\nRequired Clue Value: None\n'
                                 'Tags: None\nReal: True')
        self.call_cmd("/finish", 'Please correct the following errors:\nRequired_clue_value: This field is required.\n'
                                 'Plot: This field is required.\nName: This field is required.\n'
                                 'Desc: This field is required.')
        self.call_cmd("/name testrev", 'Name: testrev\nDesc: None\nPlot: None\nRequired Clue Value: None\n'
                                       'Tags: None\nReal: True')
        self.call_cmd("/desc testdesc", 'Name: testrev\nDesc: testdesc\nPlot: None\nRequired Clue Value: None\n'
                                        'Tags: None\nReal: True')
        self.call_cmd("/rating -5", 'Name: testrev\nDesc: testdesc\nPlot: None\nRequired Clue Value: -5\n'
                                    'Tags: None\nReal: True')
        self.call_cmd("/finish", 'Please correct the following errors:\n'
                                 'Required_clue_value: Ensure this value is greater than or equal to 1.\n'
                                 'Plot: This field is required.')
        self.call_cmd("/rating 16000", 'Name: testrev\nDesc: testdesc\nPlot: None\n'
                                       'Required Clue Value: 16000\nTags: None\nReal: True')
        self.call_cmd("/finish", 'Please correct the following errors:\n'
                                 'Required_clue_value: Ensure this value is less than or equal to 10000.\n'
                                 'Plot: This field is required.')
        self.call_cmd("/rating foo", 'Name: testrev\nDesc: testdesc\nPlot: None\nRequired Clue Value: foo\n'
                                     'Tags: None\nReal: True')
        self.call_cmd("/finish", 'Please correct the following errors:\nRequired_clue_value: Enter a whole number.\n'
                                 'Plot: This field is required.')
        self.call_cmd("/rating 25", 'Name: testrev\nDesc: testdesc\nPlot: None\nRequired Clue Value: 25\n'
                                    'Tags: None\nReal: True')
        self.call_cmd("/plot asdf", 'No plot by that name or number.')
        self.call_cmd("/plot testplot", 'Name: testrev\nDesc: testdesc\nPlot: TestPlot\n'
                                        'Required Clue Value: 25\nTags: None\nReal: True')
        self.call_cmd("/finish", 'testrev(#1) created.')
