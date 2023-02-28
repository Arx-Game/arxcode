"""
Combat Manager. This is where the magic happens. And by magic,
we mean characters dying, most likely due to vile sorcery.

The Combat Manager is invoked by a character starting combat
with the +fight command. Anyone set up as a defender of either
of those two characters is pulled into combat automatically.
Otherwise, players can enter into combat that is in progress
with the appropriate defend command, or by a +fight command
to attack one of the belligerent parties.

Turn based combat has the obvious drawback that someone who
is AFK or deliberately not taking their turn completely halts
the action. There isn't an easy solution to this. GMs will
have tools to skip someone's turn or remove them from combat,
and a majority vote by all parties can cause a turn to proceed
even when someone has not taken their turn.

Phase 1 is the setup phase. This phase is designed to have a
pause before deciding actions so that other people can join
combat. Characters who join in later phases will not receive
a combat turn, and will be added to the fight in the following
turn. Phase 1 is also when players can vote to end the combat.
Every player MUST enter a command to continue for combat to
proceed. There will never be a case where a character can be
AFK and in combat. It is possible to vote a character out of
combat due to AFK in order for things to proceed. Immediately
after every current combatant selects to continue, the participants
are locked in and we go to phase 2.

Phase 2 is the action phase. Initiative is rolled, and then
each player must take an action when it is their turn. 'pass'
is a valid action. Each combat action is resolved during the
character's turn. Characters who are incapacitated lose their
action. Characters who join combat during Phase 2 must wait
for the following turn to be allowed a legal action.
"""

import time
from operator import attrgetter

from evennia.utils.utils import fill, dedent

from server.utils.prettytable import PrettyTable
from server.utils.arx_utils import list_to_string
from typeclasses.scripts.combat import combat_settings
from typeclasses.scripts.combat.state_handler import CombatantStateHandler
from typeclasses.scripts.scripts import Script as BaseScript


COMBAT_INTRO = combat_settings.COMBAT_INTRO
PHASE1_INTRO = combat_settings.PHASE1_INTRO
PHASE2_INTRO = combat_settings.PHASE2_INTRO
MAX_AFK = combat_settings.MAX_AFK
ROUND_DELAY = combat_settings.ROUND_DELAY


class CombatManager(BaseScript):
    """
    Players are added via add_combatant or add_observer. These are invoked
    by commands in normal commandsets. Characters added receive the combat
    commandset, which give commands that invoke the other methods.

    Turns proceed based on every combatant submitting an action, which is a
    dictionary of combatant IDs to their actions. Dead characters are moved
    to observer status, incapacitated characters are moved to a special
    list to denote that they're still in combat but can take no action.
    Attribute references to the combat manager script are stored in the room
    location under room.ndb.combat_manager, and inside each character in the
    combat under character.ndb.combat_manager.
    Note that all the data for the combat manager is stored inside non-database
    attributes, since it is designed to be non-persistent. If there's a server
    reset, combat will end.
    Non-database attributes:
    self.ndb.combatants - list of everyone active in the fight. If it's empty, combat ends
    self.ndb.observers - People passively watching the fight
    self.ndb.incapacitated - People who are too injured to act, but still can be attacked
    self.ndb.fighter_data - CharacterCombatData for each combatant. dict with character.id as keys
    self.ndb.combat_location - room where script happens
    self.ndb.initiative_list - CharacterCombatData for each fighter. incapacitated chars aren't in it
    self.ndb.active_character - Current turn of player in phase 2. Not used in phase 1
    self.ndb.phase - Phase 1 or 2. 1 is setup, 2 is resolution
    self.ndb.afk_check - anyone we're checking to see if they're afk
    self.ndb.votes_to_end - anyone voting to end combat
    self.ndb.flee_success - Those who can run this turn
    self.ndb.fleeing - Those intending to try to run

    Admin Methods:
    self.msg() - Message to all combatants/observers.
    self.end_combat() - shut down the fight
    self.next_character_turn() - move to next character in initiative list in phase 2
    self.add_observer(character)
    self.add_combatant(character)
    self.remove_combatant(character)
    self.move_to_observer(character)
    """

    # noinspection PyAttributeOutsideInit
    def at_script_creation(self):
        """
        Setup the script
        """
        self.key = "CombatManager"
        self.desc = "Manages the combat state for a group of combatants"
        # Not persistent because if someone goes LD, we don't want them reconnecting
        # in combat a week later with no way to leave it. Intentionally quitting out
        # to avoid combat will just need to be corrected with rules enforcement.
        self.persistent = False
        self.interval = ROUND_DELAY
        self.start_delay = True
        self.ndb.combatants = []  # those actively involved in fight
        self.ndb.observers = []  # sent combat data, but cannot act
        self.ndb.combat_location = self.obj  # room of the fight
        self.ndb.initiative_list = (
            []
        )  # CharacterCombatData of characters in order of initiative
        self.ndb.active_character = None  # who is currently acting during phase 2
        self.ndb.phase = 1
        self.ndb.afk_check = (
            []
        )  # characters who are flagged afk until they take an action
        self.ndb.votes_to_end = []  # if all characters vote yes, combat ends
        self.ndb.flee_success = (
            []
        )  # if we're here, the character is allowed to flee on their turn
        self.ndb.fleeing = (
            []
        )  # if we're here, they're attempting to flee but haven't rolled yet
        self.ndb.ready = []  # those ready for phase 2
        self.ndb.not_ready = []  # not ready for phase 2
        self.ndb.surrender_list = []  # peoeple trying to surrender
        self.ndb.affect_real_dmg = not self.obj.tags.get("nonlethal_combat")
        self.ndb.random_deaths = not self.obj.tags.get("no_random_deaths")
        self.ndb.max_rounds = 250
        self.ndb.rounds = 0
        # to ensure proper shutdown, prevent some timing errors
        self.ndb.shutting_down = False
        self.ndb.status_table = None
        self.ndb.initializing = True
        if self.obj.event:
            self.ndb.risk = self.obj.event.risk
        else:
            self.ndb.risk = 4
        self.ndb.special_actions = []
        self.ndb.gm_afk_counter = 0

    @property
    def status_table(self):
        """text table of the combat"""
        if not self.ndb.status_table:
            self.build_status_table()
        return self.ndb.status_table

    def at_repeat(self):
        """Called at the script timer interval"""
        if self.check_if_combat_should_end():
            return
        # reset the script timers
        if self.ndb.shutting_down:
            return
        # proceed to combat
        if self.ndb.phase == 1:
            self.ready_check()
        self.msg("Use {w+cs{n to see the current combat status.")
        self.remove_surrendering_characters()

    def is_valid(self):
        """
        Check if still has combatants. Incapacitated characters are still
        combatants, just with very limited options - they can either pass
        turn or vote to end the fight. The fight ends when all combatants
        either pass they turn or choose to end. Players can be forced out
        of active combat if they are AFK, moved to observer status.
        """
        if self.ndb.shutting_down:
            return False
        if self.ndb.combatants:
            return True
        if self.ndb.initializing:
            return True
        return False

    # ----Methods for passing messages to characters-------------
    @staticmethod
    def send_intro_message(character, combatant=True):
        """
        Displays intro message of combat to character
        """
        if not combatant:
            msg = fill(
                "{mYou are now in observer mode for a fight. {n"
                + "Most combat commands will not function. To "
                + "join the fight, use the {w+fight{n command."
            )
        else:
            msg = "{rEntering combat mode.{n\n"
            msg += "\n\n" + fill(COMBAT_INTRO)
        character.msg(msg)
        return

    def display_phase_status(self, character, disp_intro=True):
        """
        Gives message based on the current combat phase to character.cmdset
        In phase 1, just list combatants and observers, anyone marked AFK,
        dead, whatever, and any votes to end.
        In phase 2, list initiative order and who has the current action.
        """
        if self.ndb.shutting_down:
            return
        msg = ""
        if self.ndb.phase == 1:
            if disp_intro:
                msg += PHASE1_INTRO + "\n"
            msg += str(self.status_table) + "\n"
            vote_str = self.vote_string
            if vote_str:
                msg += vote_str + "\n"
        elif self.ndb.phase == 2:
            if disp_intro:
                msg += PHASE2_INTRO + "\n"
            msg += str(self.status_table) + "\n"
            msg += self.get_initiative_list() + "\n"
        msg += "{wCurrent Round:{n %d" % self.ndb.rounds
        character.msg(msg)

    def build_status_table(self):
        """Builds a table of the status of combatants"""
        combatants = sorted(self.ndb.combatants)
        table = PrettyTable(
            ["{wCombatant{n", "{wDamage{n", "{wFatigue{n", "{wAction{n", "{wReady?{n"]
        )
        for state in combatants:
            name = state.combat_handler.name
            dmg = state.character.get_wound_descriptor(state.character.dmg)
            fatigue = str(state.fatigue_penalty)
            action = (
                "None" if not state.queued_action else state.queued_action.table_str
            )
            rdy = "yes" if state.ready else "{rno{n"
            table.add_row([name, dmg, fatigue, action, rdy])
        self.ndb.status_table = table

    def display_phase_status_to_all(self, intro=False):
        """Sends status to all characters in or watching the fight"""
        msglist = set([ob.character for ob in self.ndb.combatants] + self.ndb.observers)
        self.build_status_table()
        self.ready_check()
        for ob in msglist:
            self.display_phase_status(ob, disp_intro=intro)

    def msg(self, message, exclude=None, options=None):
        """
        Sends a message to all objects in combat/observers except for
        individuals in the exclude list.
        """
        # those in incapacitated list should still be in combatants also
        msglist = [ob.character for ob in self.ndb.combatants] + self.ndb.observers
        if not exclude:
            exclude = []
        msglist = [ob for ob in msglist if ob not in exclude]
        for ob in msglist:
            mymsg = message
            ob.msg(mymsg, options)

    # ---------------------------------------------------------------------
    # -----Admin Methods for OOC character status: adding, removing, etc----
    def check_character_is_combatant(self, character):
        """Returns True if the character is one of our combatants."""
        try:
            state = character.combat.state
            return state and state in self.ndb.combatants
        except AttributeError:
            return False

    def add_combatant(self, character, adder=None, reset=False):
        """
        Adds a character to combat. The adder is the character that started
        the process, and the return message is sent to them. We return None
        if they're already fighting, since then it's likely a state change
        in defending or so on, and messages will be sent from elsewhere.
        """
        # if we're already fighting, nothing happens
        cdata = character.combat
        if adder:
            adder_state = adder.combat.state
        else:
            adder_state = None
        if self.check_character_is_combatant(character):
            if character == adder:
                return "You are already in the fight."
            if cdata.state and adder:
                cdata.state.add_foe(adder)
                if adder_state:
                    adder_state.add_foe(character)
            return "%s is already fighting." % character.key
        # check if attackable
        if not character.attackable:
            return "%s is not attackable." % character.key
        if character.location != self.obj:
            return "%s is not in the same room as the fight." % character.key
        # if we were in observer list, we stop since we're participant now
        self.remove_observer(character)
        self.send_intro_message(character)
        # add combat state to list of combatants
        if character not in self.characters_in_combat:
            CombatantStateHandler(character, self, reset=reset)
        if character == adder:
            return "{rYou have entered combat.{n"
        # if we have an adder, they're fighting one another. set targets
        elif self.check_character_is_combatant(adder):
            # make sure adder is a combatant, not a GM
            cdata.state.add_foe(adder)
            cdata.state.prev_targ = adder
            adder_state.add_foe(character)
            adder_state.prev_targ = character
            adder_state.setup_attacks()
            cdata.state.setup_attacks()
        return "You have added %s to a fight." % character.name

    @property
    def characters_in_combat(self):
        """Returns characters from our combat states"""
        return [ob.character for ob in self.ndb.combatants]

    def register_state(self, state):
        """
        Stores reference to a CombatantStateHandler in self.ndb.combatants. Called by CombatantStateHandler's init,
        done this way to avoid possible infinite recursion
        """
        if state not in self.ndb.combatants:
            self.ndb.combatants.append(state)

    def finish_initialization(self):
        """
        Finish the initial setup of combatants we add
        """
        self.ndb.initializing = False
        self.reset_combatants()
        self.display_phase_status_to_all(intro=True)

    def reset_combatants(self):
        """Resets all our combatants for the next round, displaying prep message to them"""
        for state in self.ndb.combatants:
            state.reset()
        for state in self.ndb.combatants:
            state.setup_phase_prep()

    def check_if_combat_should_end(self):
        """Checks if combat should be over"""
        if not self or not self.pk or self.ndb.shutting_down:
            self.end_combat()
            return True
        if (
            not self.ndb.combatants
            and not self.ndb.initializing
            and self.managed_mode_permits_ending()
        ):
            self.msg("No combatants found. Exiting.")
            self.end_combat()
            return True
        active_combatants = [ob for ob in self.ndb.combatants if ob.conscious]
        active_fighters = [
            ob
            for ob in active_combatants
            if not (
                ob.automated and ob.queued_action and ob.queued_action.qtype == "Pass"
            )
        ]
        if not active_fighters and not self.ndb.initializing:
            if self.managed_mode_permits_ending():
                self.msg(
                    "All combatants are incapacitated or automated npcs who are passing their turn. Exiting."
                )
                self.end_combat()
                return True

    def managed_mode_permits_ending(self):
        """If we're in managed mode, increment a counter of how many checks before we decide it's idle and end"""
        if not self.managed_mode:
            return True
        if self.ndb.gm_afk_counter > 3:
            return True
        self.ndb.gm_afk_counter += 1
        return False

    def ready_check(self, checker=None):
        """
        Check all combatants. If all ready, move to phase 2. If checker is
        set, it's a character who is already ready but is using the command
        to see a list of who might not be, so the message is only sent to them.
        """
        self.ndb.ready = []
        self.ndb.not_ready = []
        if self.ndb.phase == 2:
            # already in phase 2, do nothing
            return
        for state in self.ndb.combatants:
            if state.ready:
                self.ndb.ready.append(state.character)
            elif not state.conscious:
                self.ndb.ready.append(state.character)
            else:
                self.ndb.not_ready.append(state.character)
        if self.ndb.not_ready:  # not ready for phase 2, tell them why
            if checker:
                self.display_phase_status(checker, disp_intro=False)
        else:
            try:
                self.start_phase_2()
            except ValueError:
                import traceback

                traceback.print_exc()
                self.end_combat()

    def afk_check(self, checking_char, char_to_check):
        """
        Prods a character to make a response. If the character is not in the
        afk_check list, we add them and send them a warning message, then update
        their combat data with the AFK timer. Subsequent checks are votes to
        kick the player if they have been AFK longer than a given idle timer.
        Any action removes them from AFK timer and resets the AFK timer in their
        combat data as well as removes all votes there.
        """
        # No, they can't vote themselves AFK as a way to escape combat
        if checking_char == char_to_check:
            checking_char.msg("You cannot vote yourself AFK to leave combat.")
            return
        if self.ndb.phase == 1 and char_to_check.combat.state.ready:
            checking_char.msg(
                "That character is ready to proceed "
                + "with combat. They are not holding up the fight."
            )
            return
        if self.ndb.phase == 2 and not self.ndb.active_character == char_to_check:
            checking_char.msg(
                "It is not their turn to act. You may only "
                + "vote them AFK if they are holding up the fight."
            )
            return
        if char_to_check not in self.ndb.afk_check:
            msg = "{w%s is checking if you are AFK. Please take" % checking_char.name
            msg += " an action within a few minutes.{n"
            char_to_check.msg(msg)
            checking_char.msg(
                "You have nudged %s to take an action." % char_to_check.name
            )
            self.ndb.afk_check.append(char_to_check)
            char_to_check.combat.state.afk_timer = time.time()  # current time
            return
        # character is in the AFK list. Check if they've been gone long enough to vote against
        elapsed_time = time.time() - char_to_check.combat.state.afk_timer
        if elapsed_time < MAX_AFK:
            msg = "It has been %s since %s was first checked for " % (
                elapsed_time,
                char_to_check.name,
            )
            msg += "AFK. They have %s seconds to respond before " % (
                MAX_AFK - elapsed_time
            )
            msg += "votes can be lodged against them to remove them from combat."
            checking_char.msg(msg)
            return
        # record votes. if we have enough votes, boot 'em.
        votes = char_to_check.combat.state.votes_to_kick
        if checking_char in votes:
            checking_char.msg(
                "You have already voted for their removal. Every other player "
                + "except for %s must vote for their removal." % char_to_check.name
            )
            return
        votes.append(checking_char)
        if len(votes) >= len(self.ndb.combatants) - 1:
            self.msg("Removing %s from combat due to inactivity." % char_to_check.name)
            self.move_to_observer(char_to_check)
            return
        char_to_check.msg(
            "A vote has been lodged for your removal from combat due to inactivity."
        )

    def remove_afk(self, character):
        """
        Removes a character from the afk_check list after taking a combat
        action. Resets relevant fields in combat data
        """
        if character in self.ndb.afk_check:
            self.ndb.afk_check.remove(character)
            character.combat.state.afk_timer = None
            character.combat.state.votes_to_kick = []
            character.msg("You are no longer being checked for AFK.")
            return

    def move_to_observer(self, character):
        """
        If a character is marked AFK or dies, they are moved from the
        combatant list to the observer list.
        """
        self.remove_combatant(character)
        self.add_observer(character)

    def remove_combatant(self, character, in_shutdown=False):
        """
        Remove a character from combat altogether. Do a ready check if
        we're in phase one.
        """
        state = character.combat.state
        self.clear_lists_of_character(character)
        if state in self.ndb.combatants:
            self.ndb.combatants.remove(state)
        if state:
            state.leave_combat()
        # if we're already shutting down, avoid redundant messages
        if len(self.ndb.combatants) < 2 and not in_shutdown:
            # We weren't shutting down and don't have enough fighters to continue. end the fight.
            self.end_combat()
            return
        if self.ndb.phase == 1 and not in_shutdown:
            self.ready_check()
            return
        if self.ndb.phase == 2 and not in_shutdown:
            if state in self.ndb.initiative_list:
                self.ndb.initiative_list.remove(state)
                return
            if self.ndb.active_character == character:
                self.next_character_turn()

    def clear_lists_of_character(self, character):
        """Removes a character from any of the lists they might be in"""
        if character in self.ndb.fleeing:
            self.ndb.fleeing.remove(character)
        if character in self.ndb.afk_check:
            self.ndb.afk_check.remove(character)
        if character in self.ndb.surrender_list:
            self.ndb.surrender_list.remove(character)

    def add_observer(self, character):
        """
        Character becomes a non-participating observer. This is usually
        for GMs who are watching combat, but other players may be moved
        to this - dead characters are no longer combatants, nor are
        characters who have been marked as AFK.
        """
        # first make sure that any other combat they're watching removes them as a spectator
        currently_spectating = character.combat.spectated_combat
        if currently_spectating and currently_spectating != self:
            currently_spectating.remove_observer(character)
        # now we start them spectating
        character.combat.spectated_combat = self
        self.send_intro_message(character, combatant=False)
        self.display_phase_status(character, disp_intro=False)
        if character not in self.ndb.observers:
            self.ndb.observers.append(character)
            return

    def remove_observer(self, character, quiet=True):
        """
        Leave observer list, either due to stop observing or due to
        joining the fight
        """
        character.combat.spectated_combat = None
        if character in self.ndb.observers:
            character.msg("You stop spectating the fight.")
            self.ndb.observers.remove(character)
            return
        if not quiet:
            character.msg("You were not an observer, but stop anyway.")

    def build_initiative_list(self):
        """
        Rolls initiative for each combatant, resolves ties, adds them
        to list in order from first to last. Sets current character
        to first character in list.
        """
        fighter_states = self.ndb.combatants
        for fighter in fighter_states:
            fighter.roll_initiative()
        self.ndb.initiative_list = sorted(
            [data for data in fighter_states if data.can_act],
            key=attrgetter("initiative", "tiebreaker"),
            reverse=True,
        )

    def get_initiative_list(self):
        """Displays who the acting character is and the remaining order"""
        acting_char = self.ndb.active_character
        msg = ""
        if acting_char:
            msg += "{wIt is {c%s's {wturn.{n " % acting_char.name
        if self.ndb.initiative_list:
            msg += "{wTurn order for remaining characters:{n %s" % list_to_string(
                self.ndb.initiative_list
            )
        return msg

    def next_character_turn(self):
        """
        It is now a character's turn in the iniative list. They will
        be prompted to take an action. If there is no more characters,
        end the turn when this is called and start over at Phase 1.
        """
        if self.ndb.shutting_down:
            return
        if self.ndb.phase != 2:
            return
        self.ndb.initiative_list = [
            ob
            for ob in self.ndb.initiative_list
            if ob.can_act and ob.remaining_attacks > 0
        ]
        if not self.ndb.initiative_list:
            self.start_phase_1()
            self.display_phase_status_to_all()
            return
        character_state = self.ndb.initiative_list.pop(0)
        acting_char = character_state.character
        self.ndb.active_character = acting_char
        # check if they went LD, teleported, or something
        if acting_char.location != self.ndb.combat_location:
            self.msg(
                "%s is no longer here. Removing them from combat." % acting_char.name
            )
            self.remove_combatant(acting_char)
            return self.next_character_turn()
        # For when we put in subdue/hostage code
        elif not character_state.can_act:
            acting_char.msg(
                "It would be your turn, but you cannot act. Passing your turn."
            )
            self.msg("%s cannot act." % acting_char.name, exclude=[acting_char])
            return self.next_character_turn()
        # turns lost from botches or other effects
        elif character_state.lost_turn_counter > 0:
            character_state.remaining_attacks -= 1
            character_state.lost_turn_counter -= 1
            if character_state.remaining_attacks == 0:
                acting_char.msg(
                    "It would be your turn, but you are recovering from a botch. Passing."
                )
                self.msg(
                    "%s is recovering from a botch and loses their turn."
                    % acting_char.name,
                    exclude=[acting_char],
                )
                return self.next_character_turn()
        self.msg(
            "{wIt is now{n {c%s's{n {wturn.{n" % acting_char.name, exclude=[acting_char]
        )
        if self.managed_mode:
            return self.send_managed_mode_prompt()
        result = character_state.do_turn_actions()
        if not result and self.ndb.phase == 2:
            mssg = dedent(
                """
            It is now {wyour turn{n to act in combat. Please give a little time to make
            sure other players have finished their poses or emits before you select
            an action. For your character's action, you may either pass your turn
            with the {wpass{n command, or execute a command like {wattack{n. Once you
            have executed your command, control will pass to the next character, but
            please describe the results of your action with appropriate poses.
            """
            )
            acting_char.msg(mssg)

    def start_phase_1(self):
        """
        Setup for phase 1, the 'setup' phase. We'll mark all current
        combatants as being non-ready. Characters will need to hit the
        'continue' command to be marked as ready. Once all combatants
        have done so, we move to phase 2. Alternately, everyone can
        vote to end the fight, and then we're done.
        """
        if self.ndb.shutting_down:
            return
        self.remove_surrendering_characters()
        self.ndb.phase = 1
        self.ndb.active_character = None
        self.ndb.votes_to_end = []
        allchars = self.ndb.combatants + self.ndb.observers
        if not allchars:
            return
        self.reset_combatants()
        self.ndb.rounds += 1
        if self.ndb.rounds >= self.ndb.max_rounds:
            self.end_combat()
        self.msg("{ySetup Phase{n")

    def start_phase_2(self):
        """
        Setup for phase 2, the 'resolution' phase. We build the list
        for initiative, which will be a list of CombatCharacterData
        objects from self.ndb.fighter_data.values(). Whenever it comes
        to a character's turn, they're popped from the front of the
        list, and it remains their turn until they take an action.
        Any action they take will call the next_character_turn() to
        proceed, and when there are no more characters, we go back
        to phase 1.
        """
        if self.ndb.shutting_down:
            return
        self.ndb.phase = 2
        # determine who can flee this turn
        self.ndb.flee_success = []
        # if they were attempting to flee last turn, roll for them
        for char in self.ndb.fleeing:
            c_fite = char.combat
            if c_fite.state.roll_flee_success():  # they can now flee
                self.ndb.flee_success.append(char)
        self.remove_fled_characters()
        if self.ndb.shutting_down:
            return
        self.msg("{yResolution Phase{n")
        self.build_initiative_list()
        self.next_character_turn()

    def remove_fled_characters(self):
        """Checks characters who fled and removes them"""
        for char in self.all_combatant_characters:
            if char.location != self.ndb.combat_location:
                self.remove_combatant(char)
                continue

    def vote_to_end(self, character):
        """
        Allows characters to vote to bring the fight to a conclusion.
        """
        mess = ""
        try:
            self.register_vote_to_end(character)
            mess = "%s has voted to end the fight.\n" % character.name
        except combat_settings.CombatError as err:
            character.msg(err)
        if self.check_sufficient_votes_to_end():
            return
        mess += self.vote_string
        if mess:
            self.msg(mess)

    def register_vote_to_end(self, character):
        """
        If eligible to vote for an end to combat, appends our state to a tally.
        """
        state = character.combat.state
        if state not in self.ndb.combatants:
            raise combat_settings.CombatError(
                "Only participants in the fight may vote to end it."
            )
        elif state in self.ndb.votes_to_end:
            raise combat_settings.CombatError(
                "You have already voted to end the fight."
            )
        else:
            self.ndb.votes_to_end.append(state)

    def check_sufficient_votes_to_end(self):
        """
        Messages and ends combat if everyone has voted to do so.
        """
        if not self.not_voted:
            self.msg("All participants have voted to end combat.")
            self.end_combat()
            return True

    @property
    def not_voted(self):
        """List of combat states who voted to end"""
        not_voted = [
            ob for ob in self.ndb.combatants if ob and ob not in self.ndb.votes_to_end
        ]
        # only let conscious people vote
        not_voted = [ob for ob in not_voted if ob.can_fight and not ob.wants_to_end]
        return not_voted

    @property
    def vote_string(self):
        """Get string of any who have voted to end, and who still has to vote for combat to end"""
        mess = ""
        if self.ndb.votes_to_end:
            mess += "{wCurrently voting to end combat:{n %s\n" % list_to_string(
                self.ndb.votes_to_end
            )
            mess += "{wFor the fight to end, the following characters must also use +end_combat:{n "
            mess += "%s" % list_to_string(self.not_voted)
        return mess

    # noinspection PyBroadException
    def end_combat(self):
        """
        Shut down combat.
        """
        self.msg("Ending combat.")
        self.ndb.shutting_down = True
        for char in self.all_combatant_characters:
            self.remove_combatant(char, in_shutdown=True)
        for char in self.ndb.observers[:]:
            self.remove_observer(char)
        self.obj.ndb.combat_manager = None
        try:
            self.stop()  # delete script
        except Exception:
            import traceback

            traceback.print_exc()

    @property
    def all_combatant_characters(self):
        """All characters from the states saved in combatants"""
        return [ob.character for ob in self.ndb.combatants]

    def register_surrendering_character(self, character):
        """
        Adds a character to the surrender list.
        Args:
            character: Character who wants to surrender

        Returns:
            True if successfully added, False otherwise
        """
        if self.check_surrender_prevent(character):
            return
        self.ndb.surrender_list.append(character)
        return True

    def check_surrender_prevent(self, character):
        """
        Checks if character is prevented from surrendering
        Args:
            character: Character who is trying to surrender

        Returns:
            True if character is prevented, False otherwise
        """
        for state in self.ndb.combatants:
            if character in state.prevent_surrender_list:
                return True
        return False

    def remove_surrendering_characters(self):
        """
        Check our surrendering characters, remove them from combat if not prevented
        """
        for character in self.ndb.surrender_list[:]:
            if self.check_surrender_prevent(character):
                self.ndb.surrender_list.remove(character)
                return
            self.remove_combatant(character)

    @property
    def special_actions(self):
        """GM defined actions that players can take"""
        return self.ndb.special_actions

    def add_special_action(self, name, stat="", skill="", difficulty=15):
        """Adds a new special action recognized by the combat that players can choose to do"""
        from typeclasses.scripts.combat.special_actions import ActionByGM

        self.special_actions.append(
            ActionByGM(
                combat=self, name=name, stat=stat, skill=skill, difficulty=difficulty
            )
        )

    def list_special_actions(self):
        """Gets string display of GM-defined special actions"""
        msg = "Current Actions:\n"
        table = PrettyTable(["#", "Name", "Stat", "Skill", "Difficulty"])
        for num, action in enumerate(self.special_actions, 1):
            table.add_row(
                [num, action.name, action.stat, action.skill, action.difficulty]
            )
        return msg + str(table)

    def list_rolls_for_special_actions(self):
        """Gets string display of all rolls players have made for GM-defined special actions"""
        actions = self.get_current_and_queued_actions()
        actions = [ob for ob in actions if ob.special_action in self.special_actions]
        table = PrettyTable(["Name", "Action", "Roll"])
        for action in actions:
            table.add_row(
                [
                    str(action.character),
                    str(action.special_action),
                    action.display_roll(),
                ]
            )
        return str(table)

    def get_current_and_queued_actions(self):
        """Returns list of current actions for each combatant"""
        actions = []
        for state in self.ndb.combatants:
            actions.extend(state.get_current_and_queued_actions())
        return actions

    def make_all_checks_for_special_action(self, special_action):
        """Given a special action, make checks for all corresponding queued actions"""
        pc_actions = [
            ob
            for ob in self.get_current_and_queued_actions()
            if ob.special_action == special_action
        ]
        special_action.make_checks(pc_actions)

    @property
    def managed_mode(self):
        """Whether or not a GM controls combat pacing"""
        return self.ndb.managed_mode

    @managed_mode.setter
    def managed_mode(self, value):
        self.ndb.managed_mode = value

    def send_managed_mode_prompt(self):
        """Notifies GMs that we're waiting on them to evaluate the character's turn."""
        character = self.ndb.active_character
        msg = "%s's current action: %s\n" % (
            character,
            character.combat.state.get_action_description(),
        )
        msg += "Use @admin_combat/roll to make a check, /execute to perform their action, and /next to mark resolved."
        self.msg_gms(msg)

    def msg_gms(self, message):
        """Sends a message to current GMs for this combat."""
        for gm in self.gms:
            gm.msg(message)

    def add_gm(self, character):
        """Adds a character to our list of gms."""
        if character not in self.gms:
            self.gms.append(character)

    @property
    def gms(self):
        """Characters who have admin powers for this combat."""
        if self.ndb.gms is None:
            self.ndb.gms = []
        return self.ndb.gms
