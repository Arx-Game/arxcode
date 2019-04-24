"""
Tests for the Character app. Mostly this will be investigations/clue stuff.
"""
from mock import Mock, patch

from django.test import Client
from django.urls import reverse

from server.utils.test_utils import ArxCommandTest, ArxTest
from web.character import investigation, scene_commands, goal_commands
from web.character.models import Clue, Revelation, SearchTag, Goal


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
        from world.magic.models import Spell, SkillNode, Practitioner
        from datetime import datetime
        mock_datetime.now = Mock(return_value=self.fake_datetime)
        mock_roster_datetime.now = Mock(return_value=self.fake_datetime)
        now = mock_datetime.now()
        self.setup_cmd(investigation.CmdListClues, self.account)
        self.call_cmd("1", "[test clue] (10 Rating)\ntest clue desc\nadditional text test")
        self.call_cmd("/addnote 1=test note", "[test clue] (10 Rating)\ntest clue desc\nadditional text test"
                                              "\n[%s] TestAccount wrote: test note" % now.strftime("%x %X"))
        self.call_cmd("/share 1=", "Who are you sharing with?")
        self.call_cmd("/share 1=Testaccount2",
                      "You must provide a note that gives context to the clues you're sharing.")
        self.call_cmd("/share 1=Testaccount2/x",
                      "Please write a longer note that gives context to the clues you're sharing.")
        template = "/share {}=Testaccount2/{}"
        self.call_cmd(template.format("1", "x"*80), "Sharing the clue(s) with them would cost 101 action points.")
        self.roster_entry.action_points = 202
        self.call_cmd(template.format("1", "x"*80), "You use 101 action points and have 101 remaining this week.|"
                                                    "You have shared the clue(s) 'test clue' with Char2.\n"
                                                    "Your note: {}".format("x"*80))
        self.assertEqual(self.roster_entry.action_points, 101)
        self.call_cmd("/share 2=Testaccount2", "No clue found by this ID: 2. ")
        self.clue_disco2 = self.roster_entry.clue_discoveries.create(clue=self.clue2, message="additional text test2")
        self.assertFalse(bool(self.roster_entry2.revelations.all()))
        self.node = SkillNode.objects.create(name="test node")
        self.spell = Spell.objects.create(name="test spell", node=self.node)
        self.spell.discovered_by_clues.add(self.clue2)
        self.node.discovered_by_revelations.add(self.revelation)
        self.call_cmd(template.format("2", "Love Tehom"*8), "You use 101 action points and have 0 remaining this week.|"
                      "You have shared the clue(s) 'test clue2' with Char2.\nYour note: {}".format("Love Tehom"*8))
        pract = self.char2.practitioner
        self.assertEqual(pract.spells.first(), self.spell)
        self.assertEqual(pract.nodes.first(), self.node)
        self.assertTrue(bool(self.roster_entry2.revelations.all()))
        self.caller = self.account2
        self.call_cmd("2", ("[test clue2] (50 Rating)\ntest clue2 desc\n{} This clue was shared with you by Char,"
                            " who noted: {}\n").format(now.strftime("%x %X"), "Love Tehom"*8))

    def test_cmd_helpinvestigate(self):
        self.roster_entry2.investigations.create()
        self.setup_cmd(investigation.CmdAssistInvestigation, self.char1)
        self.char1.db.investigation_invitations = [1]
        self.call_cmd("/new", 'Helping an investigation: \nInvestigation: \nStory unfinished.\n'
                              'Stat: ??? - Skill: ???|Assisting Character: Char')
        self.call_cmd("/target 2", 'No investigation by that ID.')
        self.call_cmd("/target 1", 'Helping an investigation: \nInvestigation: 1\nStory unfinished.\n'
                                   'Stat: ??? - Skill: ???|Assisting Character: Char')
        self.call_cmd("/finish", 'You must have a story defined.')
        self.call_cmd("/story test", 'Helping an investigation: \nInvestigation: 1\ntest\n'
                                     'Stat: ??? - Skill: ???|Assisting Character: Char')
        with patch.object(self.cmd_class, 'check_enough_time_left') as fake_method:
            fake_method.return_value = True
            self.call_cmd("/finish", "Char is now helping Char2's investigation on .")

    def test_cmd_investigate(self):
        tag1 = SearchTag.objects.create(name="foo")
        tag2 = SearchTag.objects.create(name="bar")
        tag3 = SearchTag.objects.create(name="zep")
        self.setup_cmd(investigation.CmdInvestigate, self.char1)
        with patch.object(self.cmd_class, 'check_enough_time_left') as fake_method:
            fake_method.return_value = True
            self.call_cmd("/new", 'Creating an investigation: \nStory unfinished.\nStat: ??? - Skill: ???')
            self.call_cmd("/finish", 'You must have topic defined.')
            self.call_cmd("/topic not matching tags", "No SearchTag found using 'not matching tags'.")
            self.call_cmd("/topic foo/-bar/zep/-squeeb/merpl", "No SearchTag found using 'squeeb'.")
            self.call_cmd("/topic foo/-bar/zep", 'The tag(s) or clue specified does not match an existing clue, and '
                                                 'will be much more difficult and more expensive to look into than '
                                                 'normal. Try other tags for an easier investigation, or proceed to '
                                                 '/finish for a much more difficult one.|Creating an investigation: '
                                                 'foo; zep; -bar\nStory unfinished.\nStat: ??? - Skill: ???')
            self.call_cmd("/finish", 'You must have a story defined.')
            self.call_cmd("/story asdf", 'Creating an investigation: foo; zep; -bar\nasdf\nStat: ??? - Skill: ???')
            self.call_cmd("/finish", 'It costs 25 social resources to start a new investigation.')
            self.assetowner.social = 25
            self.call_cmd("/finish", 'An opportunity has arisen to pursue knowledge previously unseen by mortal eyes. '
                                     'It will require a great deal of energy (100 action points) to investigate. Your '
                                     'tag requirements: foo; zep; -bar\nRepeat the command to confirm and continue.')
            self.roster_entry.action_points = 0
            prompt = self.char1.ndb.confirm_new_clue_write
            self.call_cmd("/finish", "You're too busy for such an investigation. (low AP) Try different tags or abort.")
            self.roster_entry.action_points = 300
            self.char1.ndb.confirm_new_clue_write = prompt
            self.call_cmd("/finish", 'You spend 25 social resources to start a new investigation.|'
                                     'New investigation created. This has been set as your active investigation for the'
                                     ' week, and you may add resources/silver to increase its chance of success.|'
                                     'You may only have one active investigation per week, and cannot change it once '
                                     'it has received GM attention. Only the active investigation can progress.')
            invest = self.roster_entry.investigations.first()
            clue = invest.clue_target
            self.assertEqual(clue.name, "PLACEHOLDER for Investigation #1")
            self.assertEqual(list(clue.search_tags.all()), [tag1, tag3])
            self.assertTrue(clue.allow_investigation)
            self.caller = self.char2
            self.char2.ndb.investigation_form = ['', 'story', '', '', '', [], None]
            self.clue.search_tags.add(tag1, tag2, tag3)
            self.clue.allow_investigation = True
            self.clue.save()
            self.clue2.search_tags.add(tag1, tag2)
            self.clue2.allow_investigation = True
            self.clue2.save()
            self.assetowner2.social = 75
            self.call_cmd("/topic foo/bar/-zep", 'Creating an investigation: foo; bar; -zep\nstory\n'
                                                 'Stat: ??? - Skill: ???')
            self.call_cmd("/finish", 'You spend 25 social resources to start a new investigation.|'
                                     'New investigation created. This has been set as your active investigation for the'
                                     ' week, and you may add resources/silver to increase its chance of success.|'
                                     'You may only have one active investigation per week, and cannot change it once it'
                                     ' has received GM attention. Only the active investigation can progress.')
            invest = self.roster_entry2.investigations.first()
            self.assertEqual(invest.clue_target, self.clue2)
            self.assertEqual(self.clue.get_completion_value(), 2)
            self.assertEqual(self.clue2.get_completion_value(), 33)
            self.assertEqual(invest.completion_value, 33)
            self.char2.ndb.investigation_form = ['', 'story', '', '', '', [], None]
            self.call_cmd("/topic clue: 3", "No Clue found using '3'.")
            clue3 = Clue.objects.create(name="another test clue")
            clue3.search_tags.add(tag3)
            clue3.discoveries.create(character=self.roster_entry2)
            self.call_cmd("/topic clue: another test clue", 'Creating an investigation: another test clue\nstory\nS'
                                                            'tat: ??? - Skill: ???')
            self.call_cmd("/finish", 'You spend 25 social resources to start a new investigation.|'
                                     'New investigation created. You already are participating in an active '
                                     'investigation for this week, but may still add resources/silver to increase its '
                                     'chance of success for when you next mark this as active.|You may only have one '
                                     'active investigation per week, and cannot change it once it has received GM '
                                     'attention. Only the active investigation can progress.')
            invest2 = self.roster_entry2.investigations.last()
            self.assertEqual(invest2.clue_target, self.clue)
            self.char2.ndb.investigation_form = ['clue: 3', 'story', '', '', '', [None, None], clue3]
            self.call_cmd("/finish", 'An opportunity has arisen to pursue knowledge previously unseen by mortal eyes. '
                                     'It will require a great deal of energy (100 action points) to investigate. Your '
                                     'tag requirements: another test clue\nRepeat the command to confirm and continue.')
            self.roster_entry2.action_points = 200
            self.call_cmd("/finish", 'You spend 25 social resources to start a new investigation.|New investigation '
                                     'created. You already are participating in an active investigation for this week, '
                                     'but may still add resources/silver to increase its chance of success for when '
                                     'you next mark this as active.|You may only have one active investigation per '
                                     'week, and cannot change it once it has received GM attention. Only the active '
                                     'investigation can progress.')
            invest3 = self.roster_entry2.investigations.last()
            self.assertEqual(invest3.clue_target.name, 'PLACEHOLDER for Investigation #4')
            self.call_cmd("/requesthelp bob, charlie","Must give ID of investigation.")
            self.call_cmd("/requesthelp 1=bob, charlie","Investigation not found.")
            self.call_cmd("/requesthelp 4=bob, charlie","You may only invite others to active investigations.")
            self.call_cmd("/active 4","Char2's investigation on clue: 3 set to active.")
            self.assertEqual(self.roster_entry2.action_points, 50)
            self.call_cmd("/requesthelp 4=bob, charlie","No active player found named bob|No active player found named charlie")
            self.call_cmd("/requesthelp 4=Char2","You cannot invite yourself.")


class SceneCommandTests(ArxCommandTest):

    @patch('world.roll.build_msg')
    def test_cmd_flashback(self, mock_build_msg):
        from web.character.models import Flashback
        self.setup_cmd(scene_commands.CmdFlashback, self.account)
        self.call_cmd("/create testing", "You have created a new flashback with the ID of #1.")
        self.call_cmd("/create testing", "There is already a flashback with that title. Please choose another.")
        self.call_cmd("1", "[testing] - (#1) work in progress!\nOwners and authors: Char\nSummary: ")
        self.call_cmd("/catchup 1", "No new posts for #1.")
        self.call_cmd("/post 1", "You must include a message.")
        self.assertEqual(self.char1.messages.num_flashbacks, 0)
        self.call_cmd("/post 1=A new testpost", "You have posted to testing: A new testpost")
        self.assertEqual(self.char1.messages.num_flashbacks, 1)
        self.account.inform = Mock()
        self.account2.inform = Mock()
        self.call_cmd("/invite/retro 1=Testaccount2", "You have invited Testaccount2 to participate in this "
                                                      "flashback with all previous posts visible.")
        self.account2.inform.assert_called_with("You have been invited by Testaccount to participate in flashback #1:"
                                                " 'testing'.", category="Flashbacks")
        mock_build_msg.return_value = "Galvanion checked willpower at difficulty 9001, rolling 9000 lower."
        self.char.db.willpower = 1
        self.call_cmd("/check 1=willpower", "[Private Roll] %s (Shared with: self-only)|Your next post "
                                            "in flashback #1 will use this roll." % mock_build_msg.return_value)
        self.call_cmd("/check 1=pleading", "Your next post in flashback #1 will use this roll: "
                                        "%s" %  mock_build_msg.return_value)
        self.call_cmd("/post 1=boop.", "This roll will accompany the new post: %s\nPlease repeat command to "
                                       "confirm and continue." % mock_build_msg.return_value)
        self.call_cmd("/post 1=boop.", "You have posted to testing: boop.")
        self.account2.inform.assert_called_with("New post by Char on flashback #1!",
                                                category="Flashbacks")
        self.caller = self.account2
        self.call_cmd("/catchup 1", "testing (#1) New Posts!\n[By Char] A new testpost\n[By Char] "
                                    "%s\nboop." % mock_build_msg.return_value)
        self.call_cmd("/summary 1=test", "Only the flashback's owner may use that switch.")
        self.call_cmd("/invite 1=Testaccount", "Only the flashback's owner may use that switch.")
        self.call_cmd("/conclude 1", "Only the flashback's owner may use that switch.")
        self.caller = self.account
        self.call_cmd("/uninvite 1=Testaccount2", "You have uninvited Testaccount2 from this flashback.")
        self.account2.inform.assert_called_with("You have been retired from flashback #1.", category="Flashbacks")
        self.call_cmd("/summary 1=test summary", "Summary set to: test summary.")
        Flashback.objects.get(id=1).posts.create(poster=self.roster_entry, actions="Foo.")
        self.call_cmd("1=foo", "[testing] - (#1)\nOwners and authors: Char\nSummary: test summary\n[By Char] "
                               "A new testpost\n[By Char] %s\nboop.\n[By Char] Foo." % mock_build_msg.return_value)
        self.call_cmd("1=1", "[testing] - (#1)\nOwners and authors: Char\nSummary: test summary\n[By Char] Foo.")
        self.call_cmd("/conclude 1", "Flashback #1 has been concluded.")
        self.account.inform.assert_called_with("Flashback #1 'testing' has reached its conclusion.", category="Flashbacks")
        self.call_cmd("/conclude 1", "No ongoing flashback by that ID number.")
        self.call_cmd("/create test2", "You have created a new flashback with the ID of #2.")
        self.call_cmd("/conclude 2", "Flashback #2 has been concluded.")
        self.account.inform.assert_called_with("With no posts, 'test2' (flashback #2) was deleted.", category="Flashbacks")


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
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.login(username='TestAccount2', password='testpassword'), True)
        response = self.client.get(reverse('character:list_flashbacks', kwargs={'object_id': self.char2.id}))
        self.assertEqual(response.status_code, 200)


class PRPClueTests(ArxCommandTest):
    def setUp(self):
        from world.dominion.models import Plot, PCPlotInvolvement
        super(PRPClueTests, self).setUp()
        self.plot = Plot.objects.create(name="TestPlot", usage=Plot.PLAYER_RUN_PLOT)
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
        self.call_cmd("/plot testplot=some notes on stuff", 'Name: testrev\nDesc: testdesc\nPlot: TestPlot\n'
                                                            'Required Clue Value: 25\nTags: None\nReal: True')
        self.call_cmd("/finish", 'testrev(#1) created.')
        rev = Revelation.objects.first()
        involvement = rev.plot_involvement.get(plot=self.plot)
        self.assertEqual(involvement.gm_notes, "some notes on stuff")


class GoalTests(ArxCommandTest):
    def setUp(self):
        super(GoalTests, self).setUp()
        from web.helpdesk.models import Queue
        Queue.objects.create(slug="Goals")

    def test_cmd_goals(self):
        from world.dominion.models import Plot, PCPlotInvolvement
        self.setup_cmd(goal_commands.CmdGoals, self.char)
        self.call_cmd("", '| ID | Summary | Plot '
                          '~~~~+~~~~~~~~~+~~~~~~+')
        self.call_cmd("/create asdf", "You must provide a summary and a description of your goal.")
        self.call_cmd("/create testing/this is a /desc/.", "You have created a new goal: ID #1.")
        self.call_cmd("1", 'testing (#1)\nScope: Reasonable, Status: Active\nDescription: this is a /desc/.')
        self.call_cmd("/summary 2=test", "You do not have a goal by that number.")
        self.call_cmd("/summary 1=test", 'Old value was: testing\nSummary set to: test')
        self.call_cmd("/status 1=asdf", 'Invalid Choice. Try one of the following: Succeeded, Failed, Abandoned, '
                                        'Dormant, Active')
        self.call_cmd("/status 1=dormant", 'Old value was: Active\nStatus set to: dormant')
        self.call_cmd("/scope 1=asdf", 'Invalid Choice. Try one of the following: Heartbreakingly Modest, Modest, '
                                       'Reasonable, Ambitious, Venomously Ambitious, Megalomanic')
        self.call_cmd("/scope 1=venomously Ambitious", 'Old value was: Reasonable\nScope set to: venomously Ambitious')
        self.call_cmd("/ooc_notes 1=notes", 'Old value was: \nOoc_notes set to: notes')
        self.call_cmd("/plot 1=1", "No plot by that ID.")
        plot = Plot.objects.create(name="test plot")
        PCPlotInvolvement.objects.create(plot=plot, dompc=self.dompc)
        self.call_cmd("/plot 1=1", 'Old value was: None\nPlot set to: test plot')
        self.call_cmd("1", 'test (#1)\nScope: Venomously Ambitious, Status: Dormant\nPlot: test plot\n'
                           'Description: this is a /desc/.\nOOC Notes: notes')
        self.call_cmd("/old", '| ID | Summary | Plot      '
                              '~~~~+~~~~~~~~~+~~~~~~~~~~~+\n'
                              '| 1  | test    | test plot')
        self.call_cmd("/rfr 1", 'You must provide both a short story summary of what your character did or attempted to'
                                ' do in order to make progress toward their goal, and an OOC message to staff, telling '
                                'them of your intent for results you would like and anything else that seems relevant.')
        self.call_cmd("/rfr 1,1=stuff/things", 'No beat by that ID.')
        plot.updates.create(desc="test")
        self.call_cmd("/rfr 1,1=stuff/things", 'You have sent in a request for review for goal 1. Ticket ID is 1.')
        self.call_cmd("/rfr 1,1=more stuff/things", 'You submitted a request for review for goal 1 too recently.')

    @patch('django.utils.timezone.now')
    def test_cmd_gm_goals(self, mock_now):
        from server.utils.helpdesk_api import create_ticket
        self.setup_cmd(goal_commands.CmdGMGoals, self.caller)
        mock_now.return_value = self.fake_datetime
        goal = Goal.objects.create(entry=self.roster_entry2, summary="test goal")
        update = goal.updates.create(player_summary="test summary")
        ticket = create_ticket(self.account2, message="hepl i do thing", queue_slug="Goals", goal_update=update)
        self.call_cmd("", '| ID | Player       | Goal      '
                          '~~~~+~~~~~~~~~~~~~~+~~~~~~~~~~~+\n'
                          '| 1  | Testaccount2 | test goal')
        self.call_cmd("2", 'No ticket found by that ID.')
        self.call_cmd("1", "[Ticket #1] hepl i do thing\nQueue:  - Priority 3\nPlayer: TestAccount2\n"
                           "Location: Room (#1)\nSubmitted: 08/27/78 12:08:00 - Last Update: 08/27/78 12:08:00\n"
                           "Request: hepl i do thing\nUpdate for goal: Char2's Goal (#1): test goal (#1)\n"
                           "Player Summary: test summary\nGM Resolution: None")
        self.call_cmd("/close 1=ok stuff happen", "You have closed the ticket and set the result to: ok stuff happen")
        self.assertEqual(ticket.resolution, "Result: ok stuff happen")
        self.assertEqual(update.result, "ok stuff happen")
