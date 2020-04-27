"""
Tests for different command sets.
"""
from mock import patch, Mock

from server.utils.test_utils import ArxCommandTest
from . import combat, market, home


# noinspection PyUnresolvedReferences
# noinspection PyUnusedLocal
@patch.object(combat, "inform_staff")
class CombatCommandsTests(ArxCommandTest):
    def start_fight(self, *args):
        """Helper function for starting a fight in our test"""
        fight = combat.start_fight_at_room(self.room1)
        for ob in args:
            fight.add_combatant(ob)
        return fight

    @patch.object(combat, 'do_dice_check')
    def test_cmd_heal(self, mock_dice_check, mock_inform_staff):
        from world.dominion.models import RPEvent
        event = RPEvent.objects.create(name="test")
        mock_dice_check.return_value = 10
        self.setup_cmd(combat.CmdHeal, self.char1)
        self.call_cmd("char2", "Char2 does not require any medical attention.")
        self.char2.dmg = 20
        self.call_cmd("char2", "Char2 has not granted you permission to heal them. Have them use +heal/permit.")
        self.call(self.cmd_class(), "/permit char", "You permit Char to heal you.", caller=self.char2)
        self.room1.start_event_logging(event)
        self.caller = self.char2
        self.call_cmd("/gmallow char=10", "This may only be used by the GM of an event.")
        event.add_gm(self.dompc2, send_inform=False)
        self.call_cmd("char2", "There is an event here and you have not been granted GM permission to use +heal.")
        self.call_cmd("/gmallow char=10", "You have allowed Char to use +heal, with a bonus to their roll of 10.")
        self.assertEqual(self.char1.ndb.healing_gm_allow, 10)
        self.caller = self.char1
        self.call_cmd("char2", "You rolled a 10 on your heal roll.")

    def test_cmd_start_combat(self, mock_inform_staff):
        self.setup_cmd(combat.CmdStartCombat, self.char1)
        self.call_cmd("", "No one else is fighting here. To start a new fight, +fight <character>")
        self.call_cmd("=test", "Usage: +fight <character to attack>")
        self.call_cmd("foo", "Could not find 'foo'.|No one found by the names you provided.")
        self.call_cmd("char2", "Entering combat mode.\n\n\n "
                               "Combat makes commands available to you, which you can see by looking at\n"
                               "'help combat'. While in combat, you can not use room exits: attempting\n"
                               "to use an exit will return 'What?' as an unrecognized command. The only way to\n"
                               "move from the room is with the successful use of a flee command. Combat is\n"
                               "turn-based in order to allow ample time for RP - please use poses and emits to\n"
                               "describe the results of your actions to the room, and show respect to other\n"
                               "players by being patient. Combat continues until all active parties agree to\n"
                               "end by a vote or have otherwise disengaged from the fight. Please note that\n"
                               "deliberately terminating your connection to avoid fights is against the rules.|"
                               "You have started a fight.|You have added Char2 to a fight.|\n"
                               "Entering Setup Phase:\n\n"
                               "The setup phase allows you to finish adding characters to combat or to\n"
                               "perform preliminary RP that may stop the combat before things proceed\n"
                               "further. During this phase, other characters may enter combat via the\n"
                               "+fight command and be able to act during the same turn. No characters\n"
                               "may escape via exits at this stage - they may only attempt to flee once\n"
                               "the fighting begins, during their turn. Combat may be exited without any\n"
                               "fighting if all parties vote to +end_combat. Otherwise, combat begins\n"
                               "when all characters involved have selected to continue.\n\n\n"
                               "Combatant Damage Fatigue Action Ready? \n"
                               "Char      no     0       None   no     "
                               "Char2     no     0       None   no     \nCurrent Round: 0")
        mock_inform_staff.assert_called_with("{wCombat:{n {cChar{n started a fight in room {w1{n.")
        self.assertTrue(self.char1.combat.state in self.room1.ndb.combat_manager.ndb.combatants)
        self.assertTrue(self.char2.combat.state in self.room1.ndb.combat_manager.ndb.combatants)
        self.assertEqual(self.room1.ndb.combat_manager, self.char1.combat.combat)
        self.assertEqual(self.char1.combat.combat, self.char2.combat.combat)

    def test_cmd_autoattack(self, mock_inform_staff):
        self.setup_cmd(combat.CmdAutoattack, self.char1)
        self.call_cmd("", "Autoattack is now set to be on.")
        self.assertTrue(self.char1.combat.autoattack)
        self.call_cmd("", "Autoattack is now set to be off.")
        self.assertFalse(self.char1.combat.autoattack)
        self.call_cmd("/stop", "Autoattack is now set to be off.")
        self.assertFalse(self.char1.combat.autoattack)

    def test_cmd_protect(self, mock_inform_staff):
        self.setup_cmd(combat.CmdProtect, self.char1)
        self.call_cmd("/stop", "You weren't guarding anyone.")
        self.call_cmd("foo", "Could not find 'foo'.|Couldn't find anyone to guard.")
        self.char2.tags.add("unattackable")
        self.call_cmd("char2", "Your target is currently not attackable and does not need a guard.")
        self.char2.tags.remove("unattackable")
        self.call_cmd("char2", "You start guarding Char2.")
        self.assertTrue(self.char1 in self.char2.db.defenders)
        self.assertEqual(self.char1.db.guarding, self.char2)
        self.call_cmd("foo", "You are currently guarding Char2. To guard someone else, first use +protect/stop.")
        self.call_cmd("/stop", "You stop guarding Char2.")
        self.assertEqual(self.char1.db.guarding, None)
        self.assertEqual(self.char2.db.defenders, None)

    def test_cmd_combatstats(self, mock_inform_staff):
        from evennia.utils.ansi import parse_ansi
        self.assertEqual(self.call(combat.CmdCombatStats(), ""),
                         "%s's Combat Stats\n%s" % (self.char1, parse_ansi(self.char1.combat.display_stats(),
                                                                           strip_ansi=True)))
        self.assertEqual(self.call(combat.CmdCombatStats(), "/view testaccount2"),
                         "%s's Combat Stats\n%s" % (self.char2, parse_ansi(self.char2.combat.display_stats(),
                                                                           strip_ansi=True)))
        self.setup_cmd(combat.CmdCombatStats, self.char2)
        self.call_cmd("/view testaccount", "Only GMs can view +combatstats of other players.")

    def test_cmd_observe_combat(self, mock_inform_staff):
        self.setup_cmd(combat.CmdObserveCombat, self.char1)
        self.call_cmd("", "No combat found at your location.")
        fight = self.start_fight()
        mock_inform_staff.assert_called_with("{wCombat:{n {cA non-player{n started a fight in room {w1{n.")
        self.call_cmd("", "You are now in observer mode for a fight. Most combat commands will not\nfunction. "
                          "To join the fight, use the +fight command.|\nCombatant Damage Fatigue Action Ready? \n\n"
                          "Current Round: 0")
        self.call_cmd("", "You are already spectating a combat.")
        self.call_cmd("/stop", 'You stop spectating the fight.')
        fight.add_combatant(self.char1)
        # check to make sure equality functions for non-StateHandler
        self.assertFalse(None in fight.ndb.combatants)
        self.call_cmd("", "You are already involved in this combat.")

    def test_cmd_combat_status(self, mock_inform_staff):
        self.setup_cmd(combat.CmdFightStatus, self.char1)
        self.call_cmd("", "No combat found at your location.")
        self.start_fight(self.char2)
        self.call_cmd("", "Combatant Damage Fatigue Action Ready? \n"
                          "Char2     no     0       None   no     \nCurrent Round: 0")

    def test_cmd_admin_combat(self, mock_inform_staff):
        self.setup_cmd(combat.CmdAdminCombat, self.char1)
        self.call_cmd("", "No combat found at your location.")
        self.call_cmd("/startfight", "You are now in observer mode for a fight. Most combat commands will not\n"
                                     "function. To join the fight, use the +fight command.|\n"
                                     "Combatant Damage Fatigue Action Ready? \n\nCurrent Round: 0")
        self.call_cmd("/startfight", "There is already a fight at your location.")
        self.call_cmd("/add char2", "Added Char2.")
        self.call_cmd("/add char2", "Char2 is already in combat.")
        self.call_cmd("/addspecial", "Current Actions:\n\n# Name Stat Skill Difficulty")
        self.call_cmd("/addspecial foo", "Must provide a stat and difficulty.")
        self.call_cmd("/addspecial foo=strength/brawl,15", "Current Actions:\n\n# Name Stat     Skill Difficulty \n"
                                                           "1 foo  strength brawl 15")
        self.call_cmd("/rmspecial 2", "No action by that number.\nCurrent Actions:\n\n"
                                      "# Name Stat     Skill Difficulty \n1 foo  strength brawl 15")
        self.call_cmd("/rmspecial 1", "Action removed.\nCurrent Actions:\n\n# Name Stat Skill Difficulty")
        self.call_cmd("/managed", "Combat is now in managed mode, and will pause "
                      "before each character to allow for rolls.")
        self.call_cmd("/managed", "Combat is no longer in managed mode, and will automatically "
                      "execute actions without pausing.")
        combat_script = self.room1.ndb.combat_manager
        self.call_cmd("/next", "Currently in setup phase. Use /readyall to advance to next phase.")
        combat_script.managed_mode = True
        self.call_cmd("/readyall", "Resolution Phase|It is now Char2's turn.|Char2's current action: None\n"
                                   "Use @admin_combat/roll to make a check, /execute to perform their action, "
                                   "and /next to mark resolved.")
        self.assertTrue(not combat_script.ndb.combatants[0].automated)
        self.assertTrue(combat_script.ndb.combatants[0].can_fight)
        self.assertEqual(combat_script.ndb.phase, 2)
        self.call_cmd("/next", "Advancing to next character.|Setup Phase|\n"
                               "Combatant Damage Fatigue Action Ready? \n"
                               "Char2     no     0       None   no     \nCurrent Round: 1")
        self.assertEqual(combat_script.ndb.phase, 1)
        combat_script.start_phase_2()
        self.assertFalse(combat_script.ndb.shutting_down)
        self.call_cmd("/requeue char2", "Giving Char2 an action at the end of initiative list.")
        self.assertEqual(combat_script.ndb.initiative_list, [self.char2.combat.state])
        self.call_cmd("/force char2=pass", "Forcing Char2 to: pass|Char2 passes their turn.|Setup Phase|\n"
                                           "Combatant Damage Fatigue Action Ready? \n"
                                           "Char2     no     0       None   no     \nCurrent Round: 2")
        self.assertEqual(combat_script.ndb.initiative_list, [])

    def test_cmd_create_antagonist(self, mock_inform_staff):
        self.setup_cmd(combat.CmdCreateAntagonist, self.char1)
        self.call_cmd("/boss testboss=2,5", "Created new boss with rating of 2 and threat of 5.")
        self.call_cmd("testboss=testmsg", "You spawn testboss.|testmsg")

    @patch("server.utils.arx_utils.inform_staff")
    @patch('typeclasses.scripts.combat.attacks.randint')
    @patch('typeclasses.scripts.combat.attacks.do_dice_check')
    def test_cmd_harm(self, mock_dice_check, mock_randint, mock_char_inform_staff, mock_inform_staff):
        mock_dice_check.return_value = 10
        mock_randint.return_value = 5
        self.setup_cmd(combat.CmdHarm, self.char1)
        self.call_cmd("", "Must provide at least one character = number for damage amount.")
        self.call_cmd("=50", "Must provide at least one character = number for damage amount.")
        self.call_cmd("Char2=apple", "Must provide at least one character = number for damage amount.")
        self.call(self.cmd_class(), "Char=5", "Non-GM usage. Pruning others from your list.", caller=self.char2)
        self.char2.location = self.room2
        self.call_cmd("Char2=5", "Could not find 'Char2'.")
        self.call_cmd("/global Char2=0/Thoughts.", "Thoughts. You inflict 0. Char2 is unharmed.")
        self.char2.armor = 10
        self.char2.location = self.room1
        self.char2.msg = Mock()
        self.call_cmd("Char2=1/Prayers.", "Prayers. 1 inflicted and Char2 is unharmed.|Prayers. You inflict 1. "
                                          "Char2 is unharmed.")
        self.char2.msg.assert_called_with("Your armor mitigated 1 of the damage.")
        mock_inform_staff.assert_called_with("{cChar{n used @harm for 1 damage on Char2.")
        self.call_cmd("Char2=500/Nuclear apple.", "Nuclear apple. 500 inflicted and Char2 is harmed for grave damage."
                                                  "|Nuclear apple. You inflict 500. Char2 is harmed for grave damage."
                                                  "|Char2 remains capable of fighting.")
        mock_inform_staff.assert_called_with("{cChar{n used @harm for 500 damage on Char2.")
        self.assertEqual(self.char2.damage, 488)
        self.call_cmd("/private/noarmor Char2=400/Apple turret.", "Apple turret. You inflict 400. Char2 is harmed "
                                                                  "for grave damage.")
        self.assertEqual(self.char2.damage, 888)
        mock_dice_check.return_value = -1
        self.call_cmd("/mercy Char2=500", "500 inflicted and Char2 is harmed for grave damage."
                                          "|You inflict 500. Char2 is harmed for grave damage."
                                          "|Char2 is incapacitated and falls unconscious.")
        self.call_cmd("Char2=500/Emerald's Kiss.", "Emerald's Kiss. 500 inflicted and Char2 is harmed for grave damage."
                                                   "|Emerald's Kiss. You inflict 500. Char2 is harmed for grave damage."
                                                   "|Char2 has died.")
        mock_char_inform_staff.assert_called_with("{rDeath{n: Character {cChar2{n has died.")

    def test_cmd_standyoassup(self, mock_inform_staff):
        self.setup_cmd(combat.CmdStandYoAssUp, self.char1)
        self.char2.damage = 500
        self.char2.fall_asleep(uncon=True)
        self.call_cmd("/noheal Char2", "Char2 wakes up.")
        self.assertEqual(self.char2.damage, 500)
        self.assertTrue(self.char2.conscious)
        self.char2.fall_asleep(uncon=True)
        self.char2.location = self.room2
        self.call_cmd("Char2", "Could not find 'Char2'.")
        self.call_cmd("/global Char2",
                      "You heal Char2 because they're a sissy mortal who needs everything done for them.")
        self.assertEqual(self.char2.damage, 0)
        self.assertTrue(self.char2.conscious)

    def test_cmd_end_combat(self, mock_inform_staff):
        self.setup_cmd(combat.CmdEndCombat, self.char1)
        self.start_fight(self.char2, self.char1)
        self.call_cmd("", "Char has voted to end the fight.\nCurrently voting to end combat: Char\n"
                          "For the fight to end, the following characters must also use +end_combat: Char2")
        self.call_cmd("", "You have already voted to end the fight.|Currently voting to end combat: Char\n"
                          "For the fight to end, the following characters must also use +end_combat: Char2")
        self.char2.fall_asleep(uncon=True)
        self.call_cmd("", "You have already voted to end the fight.|All participants have voted to end combat.|"
                          "Ending combat.|Char2 has left the fight.")

    @patch("server.utils.arx_utils.inform_staff")
    @patch('typeclasses.scripts.combat.attacks.randint')
    @patch('typeclasses.scripts.combat.attacks.do_dice_check')
    def test_cmd_attack(self, mock_dice_check, mock_randint, mock_char_inform_staff, mock_inform_staff):
        self.setup_cmd(combat.CmdAttack, self.char1)
        from evennia.utils import create
        self.account3 = create.create_account("TestAccount3", email="test@test.com", password="testpassword",
                                              typeclass=self.account_typeclass)
        self.char3 = create.create_object(self.character_typeclass, key="Char3", location=self.room1, home=self.room1)
        self.char3.account = self.account3
        self.account3.db._last_puppet = self.char3
        self.char1.db.defenders = [self.char3]
        self.char3.db.guarding = self.char1
        self.char3.combat.autoattack = True
        fight = self.start_fight(self.char1)
        self.call_cmd("", "Could not find ''.|Attack who?")
        self.call_cmd("Emerald", "Could not find 'Emerald'.|Attack who?")
        self.char2.tags.add("unattackable")
        self.call_cmd("Char2", "Char2 is not attackable and cannot enter combat.")
        self.char2.tags.remove("unattackable")
        self.call_cmd("Char2", "They are not in combat.")
        fight.add_combatant(self.char2, adder=self.char1)
        self.char1.db.sleep_status = "unconscious"
        self.call_cmd("Char2", "You are not conscious.")
        self.caller = self.char2
        self.call_cmd("Char", "Char is incapacitated. To kill an incapacitated character, you must use the "
                              "+coupdegrace command.")
        self.char1.db.sleep_status = "awake"
        self.call_cmd("/critical/accuracy Char", "These switches cannot be used together.")
        self.call_cmd("/critical Char=lipstick", "Modifier must be a number between 1 and 50.")
        self.call_cmd("/accuracy Char", "You have marked yourself as ready to proceed.|\n"
                                        "Combatant Damage Fatigue Action       Ready? \n"
                                        "Char2     no     0       attack Char3 yes    "
                                        "Char      no     0       None         no     "
                                        "Char3     no     0       None         no     \n"
                                        "Current Round: 0|"
                                        "Queuing action for your turn: You attack Char. It was interfered with, "
                                        "forcing you to target Char3 instead. Attempting to make your attack more "
                                        "accurate.")
        self.assertTrue(self.char2.combat.state.queued_action)
        char2_q = self.char2.combat.state.queued_action
        self.assertEqual(char2_q.qtype, "attack")
        self.assertEqual(char2_q.targ, self.char3)
        self.assertEqual(char2_q.msg, "{rYou attack Char.{n It was interfered with, forcing you to target "
                                      "{cChar3{n instead. Attempting to make your attack more accurate.")
        self.assertEqual(char2_q.attack_penalty, -15)
        self.assertEqual(char2_q.dmg_penalty, 15)
        self.call_cmd("/critical/only Char", "Queuing action for your turn: You attack Char. "
                                             "Attempting a critical hit.")
        char2_q = self.char2.combat.state.queued_action
        self.assertEqual(char2_q.targ, self.char1)
        self.assertEqual(char2_q.msg, "{rYou attack Char.{n Attempting a critical hit.")
        self.assertEqual(char2_q.attack_penalty, 30)
        self.assertEqual(char2_q.dmg_penalty, -15)
        # phase 2 attack
        self.caller = self.char1
        self.char3.combat.state.setup_attacks()  # bodyguard's autoattack
        self.char1.combat.state.ready, self.char3.combat.state.ready = True, True
        fight.build_initiative_list = Mock()
        fight.ndb.initiative_list = [self.char2.combat.state, self.char3.combat.state]
        fight.ndb.phase = 2
        fight.ndb.active_character = self.char1
        mock_dice_check.return_value = 10
        mock_randint.return_value = 5
        self.char1.armor = 1  # 8 mitigation
        self.char2.armor = 5  # 10 mitigation
        self.char1.combat.state.damage_modifier = 100  # 32--> -mit = 22--> *dmgmult 0.5
        self.char2.combat.state.damage_modifier = 30  # 15--> -mit = 7--> *dmgmult 0.5
        self.call_cmd("Char2", "You attack Char2. |YOU attack Char2 10 vs 10: graze for severe damage (11).|"
                               "Char attacks Char2 (graze for severe damage).|It is now Char2's turn.|"
                               "Char2 attacks YOU and rolled 10 vs 10: graze for moderate damage (3). "
                               "Your armor mitigated 8 of the damage.|"
                               "Char2 attacks Char (graze for moderate damage).|It is now Char3's turn.|"
                               "Char3 attacks Char2 (graze for no damage).|Setup Phase|\n"
                               "Combatant Damage   Fatigue Action       Ready? \n"
                               "Char      moderate 0       None         no     "
                               "Char2     severe   0       None         no     "
                               "Char3     no       0       attack Char2 no     \n"
                               "Current Round: 1")
        self.assertEqual(self.char1.damage, 3)
        self.assertEqual(self.char2.damage, 11)
        self.call_cmd("/flub Char2", "You must specify both a to-hit and damage penalty, though they can be 0.")
        self.call_cmd("/flub Char2=5,6,7", "You must specify both a to-hit and damage penalty, though they can be 0.")
        self.call_cmd("/flub Char2=200,-2000", "Maximum flub value is 500.")
        self.call_cmd("/flub Char2=200,-200", 'You have marked yourself as ready to proceed.|\n'
                                              'Combatant Damage   Fatigue Action       Ready? \n'
                                              'Char      moderate 0       attack Char2 yes    '
                                              'Char2     severe   0       None         no     '
                                              'Char3     no       0       attack Char2 no     \n'
                                              'Current Round: 1|'
                                              'Queuing action for your turn: You attack Char2. '
                                              'Adjusting your attack with a to-hit penalty of 200 and'
                                              ' damage penalty of 200.')
        last_action = self.char1.combat.state.queued_action
        self.assertEqual(last_action.attack_penalty, 200)
        self.assertEqual(last_action.dmg_penalty, 200)
        fight.ndb.phase = 2
        self.char1.combat.state.do_turn_actions()
        self.assertEqual(last_action, self.char1.combat.state.last_action)
        attack = last_action.finished_attack
        self.assertEqual(attack.dmg_penalty, 200)
        self.assertEqual(attack.attack_penalty, 200)
        # TODO: Maybe try a riposte. Also test death.
    
    @patch('typeclasses.scripts.combat.attacks.randint')
    @patch('typeclasses.scripts.combat.attacks.do_dice_check')
    def test_cmd_slay(self, mock_dice_check, mock_randint, mock_inform_staff):
        self.setup_cmd(combat.CmdSlay, self.char1)
        self.start_fight(self.char1, self.char2)
        self.char2.db.sleep_status = "unconscious"
        mock_dice_check.return_value = 10
        mock_randint.return_value = 5
        # dmg 10--> *dmgmult 2.0 //4 + 5 = 10--> -mit (wiped out by uncon)
        self.call_cmd("Char2", "You have marked yourself as ready to proceed.|Resolution Phase|You attack Char2. |"
                               "YOU attack Char2 10 vs -9999: no-contest hit for serious damage (10).|"
                               "Char attacks Char2 (no-contest hit for serious damage).|Setup Phase|\n"
                               "Combatant Damage  Fatigue Action Ready? \n"
                               "Char      no      0       None   no     "
                               "Char2     serious 0       None   no     \n"
                               "Current Round: 1")
        self.assertEqual(self.char2.damage, 10)

    def test_cmd_ready_turn(self, mock_inform_staff):
        self.setup_cmd(combat.CmdReadyTurn, self.char2)
        fight = self.start_fight(self.char2, self.char1)
        self.assertFalse(self.char2.combat.state.ready)
        self.call_cmd("", "You have marked yourself as ready to proceed.|\n"
                          "Combatant Damage Fatigue Action Ready? \n"
                          "Char2     no     0       None   yes    "
                          "Char      no     0       None   no     \nCurrent Round: 0")
        self.assertTrue(self.char2.combat.state.ready)
        self.call_cmd("", "Combatant Damage Fatigue Action Ready? \n"
                          "Char2     no     0       None   yes    "
                          "Char      no     0       None   no     \nCurrent Round: 0")
        self.char2.combat.state.ready = False
        self.char2.fall_asleep(uncon=True)
        self.caller = self.char1
        fight.ndb.afk_check.append(self.char1)
        fight.build_initiative_list = Mock()
        fight.ndb.initiative_list = [self.char1.combat.state]
        self.call_cmd("", "You are no longer being checked for AFK.|You have marked yourself as ready to proceed.|"
                          "Resolution Phase|\nIt is now your turn to act in combat. Please give a little time to make\n"
                          "sure other players have finished their poses or emits before you select\n"
                          "an action. For your character's action, you may either pass your turn\n"
                          "with the pass command, or execute a command like attack. Once you\n"
                          "have executed your command, control will pass to the next character, but\n"
                          "please describe the results of your action with appropriate poses.")
        self.assertEqual(fight.ndb.afk_check, [])
        fight.ndb.afk_check.append(self.char1)
        self.call_cmd("", "You are no longer being checked for AFK.")

    def test_cmd_pass_turn(self, mock_inform_staff):
        self.setup_cmd(combat.CmdPassTurn, self.char1)
        fight = self.start_fight(self.char2, self.char1)
        self.call_cmd("", "Wrong combat phase for this command.")
        fight.build_initiative_list = Mock()
        fight.ndb.initiative_list = [self.char1.combat.state, self.char2.combat.state]
        fight.start_phase_2()
        self.call_cmd("", "Char delays their turn.|It is now Char2's turn.", cmdstring="delay")
        self.assertEqual(fight.ndb.initiative_list, [self.char1.combat.state])
        self.call_cmd("", "Queuing this action for later.", cmdstring="delay")
        self.caller = self.char2
        self.call_cmd("", "Char2 passes their turn.|It is now Char's turn.|"
                          "Char delays their turn.|It is now Char's turn.", cmdstring="pass")
        self.assertEqual(fight.ndb.initiative_list, [])

    # def test_cmd_flee(self, mock_inform_staff):  # Feature to be renovated
    #     self.setup_cmd(combat.CmdFlee, self.char1)
    #     self.start_fight(self.char2)
    #     pass

    # def test_cmd_flank(self, mock_inform_staff):  # Feature to be renovated
    #     self.setup_cmd(combat.CmdFlank, self.char1)
    #     self.start_fight(self.char2)
    #     pass

    def test_cmd_combat_stance(self, mock_inform_staff):
        self.setup_cmd(combat.CmdCombatStance, self.char1)
        self.call_cmd("", "Current combat stance: balanced")
        self.call_cmd("blushing", "Your stance must be one of the following: aggressive, balanced, defensive, "
                      "guarded, or reckless")
        fight = self.start_fight(self.char1, self.char2)
        fight.ndb.phase = 2
        self.call_cmd("defensive", "Can only change stance between rounds.")
        fight.ndb.phase = 1
        self.call_cmd("defensive", "Stance changed to defensive.")
        self.assertEqual(self.char1.combat.stance, "defensive")

    # def test_cmd_catch(self, mock_inform_staff):  # Feature to be renovated
    #     self.setup_cmd(combat.CmdCombatStance, self.char1)
    #     self.start_fight(self.char2)
    #     pass

    # def test_cmd_cover_retreat(self, mock_inform_staff):  # Feature to be renovated
    #     self.setup_cmd(combat.CmdCoverRetreat, self.char1)
    #     self.start_fight(self.char2)
    #     pass
    
    def test_cmd_vote_afk(self, mock_inform_staff):
        self.setup_cmd(combat.CmdVoteAFK, self.char1)
        fight = self.start_fight(self.char1)
        self.call_cmd("Char2", "They are not in combat.")
        fight.add_combatant(self.char2, adder=self.char1)
        self.call_cmd("Char", "You cannot vote yourself AFK to leave combat.")
        self.char2.combat.state.ready = True
        self.call_cmd("Char2", "That character is ready to proceed with combat. They are not holding up the fight.")
        fight.ndb.phase = 2
        fight.ndb.active_character = self.char1
        self.call_cmd("Char2", "It is not their turn to act. You may only vote them AFK if they are holding up "
                               "the fight.")
        fight.ndb.active_character = self.char2
        self.char2.msg = Mock()
        self.call_cmd("Char2", "You have nudged Char2 to take an action.")
        self.char2.msg.assert_called_with("{wChar is checking if you are AFK. Please take"
                                          " an action within a few minutes.{n")
        self.assertEqual(fight.ndb.afk_check, [self.char2])
        self.assertTrue(self.char2.combat.state.afk_timer)
        # TODO: Can test here for the 'AFK period not yet elapsed' message if you want.
        self.char2.combat.state.afk_timer = 1234892919.655932  # fyi it's Tue Feb 17 10:48:39 2009
        self.call_cmd("Char2", "Removing Char2 from combat due to inactivity.|Char2 has left the fight."
                               "|Ending combat.")
        
    def test_cmd_cancel_action(self, mock_inform_staff):
        self.setup_cmd(combat.CmdCancelAction, self.char1)
        self.char1.combat.autoattack = True
        fight = self.start_fight(self.char2)
        fight.add_combatant(self.char1, adder=self.char2)
        self.assertTrue(self.char1.combat.state.queued_action)
        self.call_cmd("", "You clear any queued combat action.|\n"
                          "Combatant Damage Fatigue Action Ready? \n"
                          "Char      no     0       None   no     "
                          "Char2     no     0       None   no     \nCurrent Round: 0")
        self.assertFalse(self.char1.combat.state.queued_action)

    def test_cmd_surrender(self, mock_inform_staff):
        self.setup_cmd(combat.CmdSurrender, self.char1)
        fight = self.start_fight(self.char1)
        self.call_cmd("Char2", "Char2 is not in combat with you.")
        fight.add_combatant(self.char2, adder=self.char1)
        self.call_cmd("Char2", "Use the command by itself to surrender.")
        self.call_cmd("/deny Char2", "You are preventing the surrender of Char2.")
        self.assertEqual(self.char1.combat.state.prevent_surrender_list, [self.char2])
        self.call_cmd("/deny Char2", "You no longer prevent the surrender of Char2.")
        self.assertEqual(self.char1.combat.state.prevent_surrender_list, [])
        self.char2.combat.state.prevent_surrender_list = [self.char1]
        self.call_cmd("", "You are stopped from attempting to surrender.")
        self.char2.combat.state.prevent_surrender_list = []
        self.call_cmd("", "Char is attempting to surrender. "
                          "They will leave combat if not prevented with surrender/deny.")
        self.call_cmd("", "Char removes their bid to surrender.")

    # def test_cmd_special_action(self, mock_inform_staff):
    #     self.setup_cmd(combat.CmdSpecialAction, self.char1)
    #     self.start_fight(self.char1)
    #     pass
    
    # def test_cmd_combat_stats(self, mock_inform_staff):
    #     pass


# noinspection PyUnresolvedReferences
class TestMarketCommands(ArxCommandTest):
    @patch.object(market, "do_dice_check")
    def test_cmd_haggle(self, mock_dice_check):
        from world.dominion.models import CraftingMaterialType
        self.setup_cmd(market.CmdHaggle, self.char1)
        self.call_cmd("", "You currently haven't found a deal to negotiate. Use haggle/findbuyer"
                          " or haggle/findseller first.")
        self.call_cmd("/findseller economic=-1", "You must provide a material type and a positive amount "
                                                 "for the transaction.")
        self.call_cmd("/findseller x=50", "No material found for the name 'x'.")
        mock_dice_check.return_value = -1
        self.assertEqual(self.roster_entry.action_points, 100)
        self.call_cmd("/findseller economic=1", "You failed to find anyone willing to deal with you at all.")
        self.assertEqual(self.roster_entry.action_points, 95)
        mock_dice_check.return_value = 10
        self.call_cmd("/findseller economic=50000", "You found someone willing to sell 100 economic. "
                                                    "You can use /roll to try to negotiate the price.")
        self.assertEqual(self.roster_entry.action_points, 90)
        self.call_cmd("/findbuyer economic=200", 'You already have a deal in progress: please decline it first.\n'
                                                 'Attempting to buy: 100 economic resources.\nCurrent Discount: 20\n'
                                                 'Silver Cost: 40000.0 (Base Cost Per Unit: 500.0)\n'
                                                 'Roll Modifier: 0')
        self.call_cmd("/accept", "You haven't struck a deal yet. You must negotiate the deal before you can accept it.")
        self.call_cmd("/roll", 'You have found a better deal:\nAttempting to buy: 100 economic resources.\n'
                               'Current Discount: 30\nSilver Cost: 35000.0 (Base Cost Per Unit: 500.0)\n'
                               'Roll Modifier: 0')
        self.call_cmd("/roll", 'You failed to find a better deal.\nAttempting to buy: 100 economic resources.\n'
                               'Current Discount: 30\nSilver Cost: 35000.0 (Base Cost Per Unit: 500.0)\n'
                               'Roll Modifier: 0')
        self.assertEqual(self.roster_entry.action_points, 80)
        deal = self.char1.db.haggling_deal
        self.call_cmd("/decline", "You have cancelled the deal.")
        self.assertEqual(self.char1.db.haggling_deal, None)
        self.char1.db.haggling_deal = deal
        self.call_cmd("/accept", 'You cannot afford the silver cost of 35000.0.')
        self.char1.db.currency = 40000.0
        self.call_cmd("/accept", 'You have bought 100 economic resources for 35000.0 silver.')
        self.assertEqual(self.assetowner.economic, 100)
        self.assertEqual(self.char1.currency, 5000.0)
        mock_dice_check.return_value = 200
        self.call_cmd("/findbuyer economic=100", 'Due to your success in searching for a deal, haggling rolls will have'
                                                 ' a bonus of 25.|You found someone willing to buy 100 economic. '
                                                 'You can use /roll to try to negotiate the price.')
        self.call_cmd("/roll", 'You have found a better deal:\nAttempting to sell: 100 economic resources.\n'
                               'Current Markup Bonus: 55\nSilver Value: 27500.0 (Base Cost Per Unit: 500.0)\n'
                               'Roll Modifier: 25')
        self.call_cmd("/accept", 'You have sold 100 economic resources and gained 27500.0 silver.')
        self.assertEqual(self.assetowner.economic, 0)
        self.assertEqual(self.char1.currency, 32500.0)
        material = CraftingMaterialType.objects.create(name="testium", value=50000000)
        self.call_cmd("/findseller testium=10", 'You had trouble finding a deal for such a valuable item. Haggling '
                                                'rolls will have a penalty of -99.|You found someone willing to sell 1 '
                                                'testium. You can use /roll to try to negotiate the price.')
        self.char1.ndb.haggling_deal.post_deal_cleanup()
        material.value = 5000
        material.save()
        self.call_cmd("/findseller testium=10", 'Due to your success in searching for a deal, haggling rolls will have'
                                                ' a bonus of 25.|You found someone willing to sell 10 testium. You can '
                                                'use /roll to try to negotiate the price.')
        self.call_cmd("/roll", 'You have found a better deal:\nAttempting to buy: 10 testium.\nCurrent Discount: 65\n'
                               'Silver Cost: 17500.0 (Base Cost Per Unit: 5000.0)\nRoll Modifier: 25')
        deal = list(self.char1.db.haggling_deal)
        self.call_cmd("/accept", "You have bought 10 testium for 17500.0 silver.")
        mats = self.assetowner.materials.get(type__name=material.name)
        self.assertEqual(mats.amount, 10)
        deal[0] = "sell"
        deal[2] = 30
        self.char1.db.haggling_deal = deal
        self.call_cmd("/accept", 'You do not have enough testium to sell.')
        mats.amount = 30
        mats.save()
        self.char1.db.social_rank = 1
        self.assetowner.fame = 500
        self.assetowner.save()
        self.call_cmd("/roll",
                      'Engaging in crass mercantile haggling is considered beneath those of high social rank. '
                      'Fortunately, no one noticed this time.|You failed to find a better deal.\n'
                      'Attempting to sell: 30 testium.\nCurrent Markup Bonus: 55\n'
                      'Silver Value: 35194.5 (Base Cost Per Unit: 2133)\nRoll Modifier: 25')
        mock_dice_check.return_value = -5
        self.call_cmd("/roll", 'Engaging in crass mercantile haggling is considered beneath those of high social rank. '
                               'Unfortunately, you were noticed and lose 5 fame.|You failed to find a better deal.\n'
                               'Attempting to sell: 30 testium.\nCurrent Markup Bonus: 55\n'
                               'Silver Value: 35194.5 (Base Cost Per Unit: 2133)'
                               '\nRoll Modifier: 25')
        self.call_cmd("/accept", 'You have sold 30 testium and gained 35194.5 silver.')
        self.assertEqual(self.assetowner.fame, 495)
        self.assertEqual(mats.amount, 0)
        self.assertEqual(self.char1.currency, 50194.5)
        mock_dice_check.return_value = 10
        self.call_cmd("/findseller testium,testaccount2=50,bar", "The optional minimum bonus must be a number.")
        self.call_cmd("/findseller testium,testaccount2=50,500", 'The roll bonus of 0 was below the minimum of 25, '
                                                                 'so the deal is cancelled.')
        mock_dice_check.return_value = 500
        self.account2.inform = Mock()
        self.call_cmd("/findseller testium,testaccount2=50,25",
                      'Due to your success in searching for a deal, haggling rolls will have a bonus of 25.|'
                      'You found someone willing to sell 50 testium. You let Char2 know that a deal is on the way.')
        self.assertEqual(self.char2.db.haggling_deal, ('buy', 1, 50, 0, 25))
        self.account2.inform.assert_called_with('You have been sent a deal that you can choose to haggle by Char.\n'
                                                '{wAttempting to buy:{n 50 testium.\n{wCurrent Discount:{n 20\n'
                                                '{wSilver Cost:{n 200000.0 (Base Cost Per Unit: 5000.0)\n'
                                                '{wRoll Modifier:{n 25',
                                                category='Deal Offer')
        self.call_cmd("/findseller testium,testaccount2=50,25",
                      "They already have a deal in progress. Ask them to decline it first.")


class TestHomeCommands(ArxCommandTest):
    def test_cmd_shop(self):
        from world.dominion.models import CraftingRecipe
        recipes = {CraftingRecipe.objects.create(id=1, name="Item1", additional_cost=10),  
                   CraftingRecipe.objects.create(id=2, name="Item2")}
        self.char2.player_ob.Dominion.assets.recipes.set(recipes)
        prices = self.room.db.crafting_prices or {}
        prices[1] = 10
        prices["removed"] = {2}
        self.room.db.crafting_prices = prices
        self.room.db.shopowner = self.char2
        self.char1.location = self.room
        self.setup_cmd(home.CmdBuyFromShop, self.char1)
        self.call_cmd("/test", "Invalid switch.")
        self.call_cmd("/craft", "Please provide a valid recipe name.")
        self.call_cmd("/craft Item2", "Recipe by the name Item2 is not available.")
        self.call_cmd("/craft Item3", "No recipe found by the name Item3.")
        self.call_cmd("", 'Crafting Prices\n\nName  Craft Price Refine Price \n'
                          'Item1 11.0        0            \nItem Prices')
        self.call_cmd("/craft Item1", 'Char2 has started to craft: Item1.|'
                                      'To finish it, use /finish after you gather the following:|Silver: 10')              
