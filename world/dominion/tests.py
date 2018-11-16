"""
Tests for dominion stuff. Crisis commands, etc.
"""
from mock import patch, Mock

from server.utils.test_utils import ArxCommandTest, TestTicketMixins
from . import crisis_commands, general_dominion_commands, plot_commands
from web.character.models import StoryEmit, Clue, CluePlotInvolvement, Revelation, Investigation
from world.dominion.models import Plot, PlotAction, PCPlotInvolvement, RPEvent, PlotUpdate, Organization


class TestCrisisCommands(ArxCommandTest):
    def setUp(self):
        super(TestCrisisCommands, self).setUp()
        self.crisis = Plot.objects.create(name="test crisis", escalation_points=100)
        self.action = self.crisis.actions.create(dompc=self.dompc2, actions="test action", outcome_value=50,
                                                 status=PlotAction.PENDING_PUBLISH)
        
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
        self.cmd_class = general_dominion_commands.CmdWork
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


class TestPlotCommands(TestTicketMixins, ArxCommandTest):
    def setUp(self):
        super(TestPlotCommands, self).setUp()
        self.plot1 = Plot.objects.create(name="testplot1", usage=Plot.PLAYER_RUN_PLOT)
        self.plot2 = Plot.objects.create(name="testplot2", resolved=True, usage=Plot.GM_PLOT)

    def test_cmd_plots(self):
        self.setup_cmd(plot_commands.CmdPlots, self.char2)
        self.call_cmd("", 'Plot Involvement:\n\nName/ID Involvement')
        self.plot1.dompc_involvement.create(dompc=self.dompc2, cast_status=PCPlotInvolvement.SUPPORTING_CAST,
                                            admin_status=PCPlotInvolvement.OWNER)
        plot2_part = self.plot2.dompc_involvement.create(dompc=self.dompc2)
        self.call_cmd("", 'Plot Involvement:\n\n'
                          'Name/ID        Involvement             \n'
                          'testplot1 (#1) Supporting Cast (Owner)')
        self.call_cmd("/old", 'Plot Involvement:\n\n'
                              'Name/ID        Involvement \n'
                              'testplot2 (#2) Main Cast')
        self.call_cmd("4", 'No plot found by that ID.')
        self.call_cmd("1", 'Name: testplot1\nDescription: None\nYour Involvement: Supporting Cast (Owner)')
        self.call_cmd("2", 'Name: testplot2\nDescription: None\nYour Involvement: Main Cast')
        self.call_cmd("1=1", "No beat found by that ID.")
        beat1 = self.plot1.updates.create(desc="test update")
        self.call_cmd("/createbeat 2=foo", "You lack the required permission for that plot.")
        self.call_cmd("/createbeat 1", "You must specify an IC summary of what occurred.")
        self.call_cmd("/createbeat 1=asdf", "Please have a slightly longer IC summary.")
        self.call_cmd("/createbeat 1=Bob died it was super sad", "You have created a new beat for testplot1, ID: 2.")
        beat2 = PlotUpdate.objects.get(id=2)
        beat3 = self.plot2.updates.create()
        beat3.delete = Mock()
        self.call_cmd("/add/rpevent 1=3", "You are not a GM for the plot that has a beat of that ID.")
        event = RPEvent.objects.create(name="test event", beat=beat3)
        self.call_cmd("/add/rpevent 1=2", "You are not a GM for an RPEvent with that ID.")
        event.pc_event_participation.create(dompc=self.dompc2, gm=True)
        self.call_cmd("/add/rpevent 1=2", "You have added test event to beat(ID: 2) of testplot1.")
        beat3.delete.assert_called()
        self.assertEqual(event.beat, beat2)
        self.call_cmd("/add/rpevent 1=2", 'It already has been assigned to a plot beat.')
        flashback = self.roster_entry2.created_flashbacks.create(title="test flashback")
        self.call_cmd("/add/flashback 1=1", "You have added test flashback to beat(ID: 1) of testplot1.")
        self.assertEqual(flashback.beat, beat1)
        gemit = StoryEmit.objects.create(text="test emit")
        self.call_cmd("/add/gemit 1=1", "Only staff can add gemits to plot beats.")
        self.caller = self.char
        self.call_cmd("/add/gemit 1=1", "You have added StoryEmit #1 to beat(ID: 1) of testplot1.")
        self.assertEqual(gemit.beat, beat1)
        self.caller = self.char2
        action = self.dompc2.actions.create(plot=self.plot1)
        self.call_cmd("/add/action 1=2",
                      'You have added Action by Testaccount2 for testplot1 to beat(ID: 2) of testplot1.')
        self.assertEqual(action.beat, beat2)
        self.call_cmd("/perm 2=foo/recruiter", 'You lack the required permission for that plot.')
        self.call_cmd("/perm 1=foo", 'You must specify both a name and a permission level.')
        self.call_cmd("/perm 1=foo/recruiter", "No one is involved in your plot by the name 'foo'.")
        self.call_cmd("/perm 1=testaccount2/recruiter", 'Owners cannot have their status changed.')
        self.call_cmd("/perm 2=foo/gm", 'You lack the required permission for that plot.')
        self.call_cmd("/perm 1=foo/gm", "No one is involved in your plot by the name 'foo'.")
        part = self.plot1.dompc_involvement.create(dompc=self.dompc)
        self.call_cmd("/perm 1=testaccount/gm", "GMs are limited to supporting cast or less.")
        part.cast_status = PCPlotInvolvement.SUPPORTING_CAST
        self.call_cmd("/perm 1=testaccount/gm", "You have marked Testaccount as a GM.")
        self.call_cmd("/perm 1=testaccount/player", 'You have marked Testaccount as a Player.')
        self.call_cmd("/perm 1=testaccount/recruiter", 'You have marked Testaccount as a Recruiter.')
        self.call_cmd("/perm 1=testaccount/owner", "Permission must be 'gm', 'player', or 'recruiter'.")
        self.call_cmd("/invite 2=testaccount", 'You lack the required permission for that plot.')
        plot2_part.admin_status = PCPlotInvolvement.RECRUITER
        self.call_cmd("/invite 2=testaccount", "That plot has been resolved.")
        self.plot2.resolved = False
        self.call_cmd("/invite 2=testaccount", 'Must provide both a name and a status for invitation.')
        self.call_cmd("/invite 2=testaccount,foo", 'Status must be in: main, secondary, extra')
        self.call_cmd("/invite 2=testaccount,extra", "You have invited Testaccount to join testplot2.")
        self.call_cmd("/invite 2=testaccount,extra", "They are already invited.")
        self.call_cmd("/rfr 2=argleblargle", "You lack the required permission for that plot.")
        self.call_cmd("/rfr 1", "Open tickets for testplot1:\n\nID Title")
        self.call_cmd("/rfr 1=test ticket", "You have submitted a new ticket for testplot1.")
        self.call_cmd("/rfr 1,10=test beat ticket", "You are not a GM for the plot that has a beat of that ID.")
        self.call_cmd("/rfr 1,2=test beat ticket", "You have submitted a new ticket for testplot1.")
        self.call_cmd("/storyhook 2=testaccount2", "You lack the required permission for that plot.")
        self.call_cmd("/storyhook 1=testaccount2", "You have removed Testaccount2's story hook.")
        self.call_cmd("/storyhook 1=testaccount2/test hook", "You have set Testaccount2's story hook that contacts "
                                                             "can see to: test hook")
        self.caller = self.char1
        self.call_cmd("/accept", "Outstanding invitations: 2")
        self.call_cmd("/accept 1", 'No invitation by that ID.\nOutstanding invitations: 2')
        self.call_cmd("/accept 2", 'You have joined testplot2 (Plot ID: 2)')
        self.call_cmd("/accept 2", "No invitation by that ID.\nOutstanding invitations:")
        self.call_cmd("/leave", "No plot found by that ID.\n")
        self.call_cmd("/pitch", "You must provide a name, a one-line summary, desc, "
                                "and notes for GMs separated by '/'.")
        self.call_cmd("/pitch foo/bar/desc/zeb=5", "No plot found by that ID.")
        self.call_cmd("/pitch foo/bar/desc/zeb=2", "You made a pitch to staff for a new plot. Ticket ID: 10.")
        self.call_cmd("/leave 1", "You have left testplot1.")
        self.call_cmd("/findcontact", 'You do not have a secret by that number.')
        secret = Clue.objects.create(tangible_object=self.char1, clue_type=Clue.CHARACTER_SECRET, desc="sekrit")
        secret.plot_involvement.create(plot=self.plot1, access=CluePlotInvolvement.HOOKED)
        disco = secret.discoveries.create(character=self.roster_entry)
        self.assertEqual(self.char1.messages.secrets, [disco])
        self.call_cmd("/findcontact 1", 'People you can talk to for more plot involvement with your secret:\n\n'
                                        'Testaccount2: test hook')
        self.call_cmd("/rewardrecruiter 2=testaccount", "You cannot reward yourself.")
        self.call_cmd("/rewardrecruiter 1=testaccount2", "No plot found by that ID.")
        recruiter_xp = plot_commands.get_recruiter_xp(self.char2)
        self.call_cmd("/rewardrecruiter 2=testaccount2", 'You have marked Char2 as your recruiter. '
                                                         'You have both gained xp.')
        self.assertEqual(self.char2.db.xp, recruiter_xp)
        self.assertEqual(self.char1.db.xp, plot_commands.CmdPlots.recruited_xp)

    @patch('django.utils.timezone.now')
    def test_cmd_gm_plots(self, mock_now):
        from plot_commands import create_plot_pitch
        mock_now.return_value = self.fake_datetime
        self.setup_cmd(plot_commands.CmdGMPlots, self.char1)
        self.call_cmd("", '| #   | Plot (owner)           | {Summary                                    '
                          '~~~~~+~~~~~~~~~~~~~~~~~~~~~~~~+~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~+\n'
                          '| 1   | testplot1              | None')
        self.call_cmd("/old", '| #   | Resolved Plot (owner)  | {Summary                                    '
                              '~~~~~+~~~~~~~~~~~~~~~~~~~~~~~~+~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~+\n'
                              '| 2   | testplot2              | None')
        self.call_cmd("1", 'Name: testplot1\nDescription: None')
        self.call_cmd("/create foo", 'Must include a name, summary, and a description for the plot.')
        self.call_cmd("/create testplot3/test/test", "You have created a new gm plot: testplot3.")
        self.call_cmd("/create testplot4/test/test=testplot3",
                      "You have created a new subplot of testplot3: testplot4.")
        self.call_cmd("/end 2", "You must include a resolution.")
        self.call_cmd("/end 2=asdf", "That plot has already been resolved.")
        self.call_cmd("/end testplot3=asdf", "You have ended testplot3.")
        self.call_cmd("/addbeat 4",
                      "You must include the switch of the cause: /rpevent, /action, /flashback, or /other.")
        self.call_cmd("/addbeat/other 4=asdf", "You must include a story and GM Notes.")
        self.call_cmd("/addbeat/other 2=story/gm notes", "You have created a new beat for plot testplot2.")
        update = self.plot2.updates.last()
        self.assertEqual(update.desc, "story")
        self.assertEqual(update.gm_notes, "gm notes")
        self.call_cmd("/addbeat/rpevent 2=5/story 2/gm notes 2", 'Did not find an object by that ID.')
        event = RPEvent.objects.create(name="test event")
        self.call_cmd("/addbeat/rpevent 2=1/story 2/gm notes 2",
                      'You have created a new beat for plot testplot2. The beat concerns test event(#1).')
        self.assertEqual(event.beat, self.plot2.updates.last())
        self.call_cmd("/perm 4=testaccount2/gm", "You have set Testaccount2 as a GM in testplot4.")
        self.call_cmd("/participation 4=testaccount/blargh",
                      'Choice must be one of: required cast, main cast, supporting cast, extra, tangential.')
        self.call_cmd("/participation 4=testaccount2/required cast",
                      "You have set Testaccount2 as a Required Cast in testplot4.")
        pitch = create_plot_pitch("desc", "notes", "testpitch", self.plot2, "headline", self.account2)
        self.assertEqual(pitch.plot.usage, Plot.PITCH)
        self.call_cmd("/pitches", 'ID Submitter    Name      Parent    \n'
                                  '8  Testaccount2 testpitch testplot2')
        self.call_cmd("/pitches 8", '[Ticket #8] Pitch: testpitch (testplot2)\nQueue: PRP Questions - Priority 3\n'
                                    'Player: TestAccount2\nLocation: Room (#1)\nSubmitted: 08/27/78 12:08:00 - '
                                    'Last Update: 08/27/78 12:08:00\nRequest: notes\n\n'
                                    'Plot Pitch:\n\nName: testpitch\nDescription: desc\n\nGM Resolution: None')
        self.call_cmd("/pitches/followup 8=meh", "You have added a followup to Ticket 8.")
        self.call_cmd("/pitches/approve 8=k",
                      "You have approved the pitch. testpitch is now active with Testaccount2 as the owner.")
        self.assertEqual(pitch.plot.usage, Plot.PLAYER_RUN_PLOT)
        pitch2 = create_plot_pitch("desc", "notes", "testpitch2", self.plot2, "headline", self.account2)
        self.assertEqual(pitch2.plot.pk, 6)
        self.call_cmd("/pitches/decline 9=naw", "You have declined the pitch.")
        self.assertEqual(pitch2.plot.pk, None)
        self.call_cmd("/connect/asdf 5=foo/bar",
                      "You must include the type of object to connect: char, clue, revelation, org.")
        self.call_cmd("/connect/char 5=testaccount/stuff", "You have connected Testaccount with testpitch.")
        org = Organization.objects.create(name="testorg")
        self.call_cmd("/connect/org 5=testorg/staff", "You have connected testorg with testpitch.")
        self.assertEqual(org.plots.first().id, 5)
        clue = Clue.objects.create(name="testclue")
        self.call_cmd("/connect/clue 5=testclue/stuff", "You have connected testclue with testpitch.")
        rev = Revelation.objects.create(name="testrev")
        self.call_cmd("/connect/revelation 5=testrev/stuff", "You have connected testrev with testpitch.")
        pitch3 = create_plot_pitch("desc", "notes", "testrfr", self.plot2, "headline", self.account2)
        pitch3.plot.usage = Plot.PLAYER_RUN_PLOT
        pitch3.plot.save()
        self.call_cmd("/rfr", 'ID Submitter    Name    Parent    \n'
                              '10 Testaccount2 testrfr testplot2')
        self.call_cmd("/rfr 10", '[Ticket #10] Pitch: testrfr (testplot2)\nQueue: PRP Questions - Priority 3\n'
                                 'Player: TestAccount2\nLocation: Room (#1)\n'
                                 'Submitted: 08/27/78 12:08:00 - Last Update: 08/27/78 12:08:00\nRequest: notes\n'
                                 'Plot: testrfr\nGM Resolution: None')
        self.call_cmd("/rfr/close 10=ok whatever", 'You have marked the rfr as closed.')
