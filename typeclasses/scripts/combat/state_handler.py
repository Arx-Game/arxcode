"""
Stores information about a combatant's current state in a given fight. All temporary
fight data should go here - who they're engaged with, who's covering them, their
status, any temporary modifiers, initiative rolls, fatigue, etc.

roll_initiative() - sets initiative and a tiebreaker value for the character
"""
from functools import total_ordering
from random import randint, choice

from commands.cmdsets.combat import CombatCmdSet
from world.stats_and_skills import do_dice_check


class CombatAction(object):
    """
    An action that a player queues in when it is not their turn,
    or automatically queued in for them if they are autoattacking.
    """

    ATTACK_QTYPES = ["attack", "kill", "flank"]

    def __init__(
        self,
        character,
        qtype="pass",
        targ=None,
        msg="",
        attack_penalty=0,
        dmg_penalty=0,
        status="queued",
        desc="",
        action=None,
        working=None,
        unsafe=False,
        delete_on_fail=False,
    ):
        self.character = character
        self.state = character.combat.state
        self.status = status
        self.qtype = qtype
        self.targ = targ
        self.msg = msg
        self.attack_penalty = attack_penalty
        self.dmg_penalty = dmg_penalty
        self.round_started = None
        self.round_completed = None
        self.roll = None
        self.description = desc
        self.special_action = action
        self.finished_attack = None
        self.working = working
        self.unsafe = unsafe
        self.delete_working_on_failure = delete_on_fail

    def __str__(self):
        text = "attack" if self.qtype in self.ATTACK_QTYPES else self.qtype
        if self.description:
            text += ": %s" % self.description
        if self.targ:
            text += " Target: %s" % self.targ
        return "Action: %s" % text

    @property
    def table_str(self):
        """Gets text for our table"""
        text = "attack" if self.qtype in self.ATTACK_QTYPES else self.qtype
        if self.targ:
            text += " %s" % self.targ
        return text

    def display_roll(self):
        """Returns a string representation of the current roll for the action"""
        if not self.roll:
            return "None"
        return self.roll.result

    def roll_result(self):
        """Returns the result of our roll or 0 if hasn't been rolled yet. Used for summations of all rolls"""
        if not self.roll:
            return 0
        return self.roll.result

    def do_roll(self, stat=None, skill=None, difficulty=15):
        """Performs and records a roll for this action."""
        from world.roll import Roll

        roll = Roll(
            self.character,
            stat=stat,
            skill=skill,
            difficulty=difficulty,
            quiet=False,
            flat_modifier=self.state.special_roll_modifier,
        )
        roll.roll()
        self.roll = roll

    def do_roll_for_special_action(self):
        """Performs a roll based on the stat/skill/difficult of our special action"""
        self.do_roll(
            stat=self.special_action.stat,
            skill=self.special_action.skill,
            difficulty=self.special_action.difficulty,
        )


@total_ordering
class CombatantStateHandler(object):
    """
    Stores information about a character's participation in a fight.
    """

    def __init__(self, character, combat, reset=True):
        self.combat = combat
        combat.register_state(self)
        self.combat_handler = character.combat
        # also give combat_handler a reference to us stored in 'state'
        self.combat_handler.state = self
        self.character = character
        self.character.cmdset.add(CombatCmdSet, permanent=False)
        self.attack_modifier = 0
        self.defense_modifier = 0
        self.mitigation_modifier = 0
        self.damage_modifier = 0
        self.special_roll_modifier = 0
        self.armor_pierce_modifier = 0

        # add defenders/guards
        self.defenders = []  # can be guarded by many
        if self.character.db.defenders:
            for ob in self.character.db.defenders:
                self.add_defender(ob)
        if self.character.db.assigned_guards:
            for ob in self.character.db.assigned_guards:
                self.add_defender(ob)
        self.guarding = character.db.guarding  # can only guard 1 character
        self.initiative = 0
        self.tiebreaker = 0
        self.queued_action = None
        # one attack per character
        self.num_attacks = self.combat_handler.num
        # remaining attacks this round
        self.remaining_attacks = 1
        # whether or not we intentionally kill PCs
        self.do_lethal = (
            True if self.combat.ndb.random_deaths and self.character.is_npc else False
        )
        # list of targets for each of our attacks this round
        self.targets = []
        # last person we attacked
        self.prev_targ = None
        # list of valid foes for us to make into targets
        self.foelist = []
        self.friendlist = []
        self._ready = False  # ready to move on from phase 1
        self.last_defense_method = None  # how we avoided the last attack we stopped
        self.status = "active"
        self.afk_timer = None
        self.votes_to_kick = []  # if we're AFK
        self.lost_turn_counter = 0  # lose a turn whenever it's > 0
        self.block_flee = None  # Anyone we stop from fleeing
        self.blocker_list = []  # Anyone stopping us from fleeing
        self.covering_targs = []  # Covering their retreat
        self.covered_by = []  # Having your retreat covered
        self.formation = None
        self.flee_exit = None
        self.wants_to_end = False
        self.times_attacked = 0
        self._fatigue_penalty = 0
        self.fatigue_gained_this_turn = 0
        self.num_actions = 0  # used for fatigue calculation
        self.changed_stance = False
        self.prevent_surrender_list = []
        self.automated_override = False
        self.recent_actions = []
        if reset:
            self.reset()
        self.trigger_combat_entry_hooks()

    def __str__(self):
        return self.combat_handler.name

    def __lt__(self, other):
        try:
            if self.ready == other.ready:
                return str(self) < str(other)
            return other.ready < self.ready
        except AttributeError:
            return id(self) < id(other)

    def __eq__(self, other):
        try:
            if self.ready == other.ready:
                return str(self) == str(other)
            return False
        except AttributeError:
            return False

    def __hash__(self):
        return id(self)

    @property
    def affect_real_dmg(self):
        """Whether the combat we're in is real or fake damage"""
        return self.combat.ndb.affect_real_dmg

    @property
    def random_deaths(self):
        """Whether the combat we're in allows for random one-shots"""
        return self.combat.ndb.random_deaths

    @property
    def automated(self):
        """Whether this character is automated"""
        return self.automated_override or not bool(self.character.player)

    def get_current_and_queued_actions(self):
        """Returns list of actions taken this turn, or queued"""
        actions = [
            ob
            for ob in self.recent_actions
            if ob.round_completed == self.combat.ndb.rounds
        ]
        if self.queued_action:
            actions += [self.queued_action]
        return actions

    @property
    def valid_target(self):
        """
        Whether we're in the combat at all. Should not be valid in any way to interact
        with.
        """
        if not self.character:
            return False
        if not self.combat:
            return False
        if self.character.location != self.combat.obj:
            return False
        return True

    @property
    def can_fight(self):
        """
        Whether we're totally out of the fight. Can be killed, but no longer
        a combatant.
        """
        if not self.valid_target:
            return False
        if not self.character.conscious:
            return False
        return True

    @property
    def can_act(self):
        """
        Whether we can act this round. May be temporarily stunned.
        """
        if not self.can_fight:
            return False
        return self.status == "active"

    @property
    def ready(self):
        """Whether we're ready to progress from phase 1"""
        # if we're an automated npc, we are ALWAYS READY TO ROCK. BAM.
        return self.automated or self._ready

    @ready.setter
    def ready(self, value):
        # set whether or not a sissy-man non-npc is ready. Unlike npcs, which are ALWAYS READY. BOOYAH.
        self._ready = value

    def leave_combat(self):
        """Leaves combat"""
        character = self.character
        # nonlethal combat leaves no lasting harm
        self.character.temp_dmg = 0
        if not self.affect_real_dmg:
            character.wake_up(quiet=True)
        self.stop_covering()
        self.clear_blocked_by_list()
        self.clear_covered_by_list()
        guarding = self.guarding
        if guarding and guarding.combat.state:
            guarding.combat.state.remove_defender(character)
        self.combat.msg("%s has left the fight." % character.name)
        character.cmdset.delete(CombatCmdSet)
        self.combat_handler.state = None
        try:
            # remove temporary losses from MultiNpcs
            self.character.temp_losses = 0
        except AttributeError:
            pass

    def reset(self):
        """Resets values on a per-round basis"""
        self.times_attacked = 0
        self.ready = False
        self.queued_action = None
        self.changed_stance = False
        self.fatigue_gained_this_turn = 0
        # check for attrition between rounds
        if self.combat_handler.multiple:
            self.num_attacks = self.combat_handler.num
        self.remaining_attacks = self.num_attacks

    def setup_phase_prep(self):
        """Sets us up for each turn, check for automated npcs wanting for combat to end"""
        # if we order them to stand down, they do nothing
        if self.automated:
            if self.wants_to_end:
                self.combat.vote_to_end(self.character)
                self.set_queued_action("pass")
                return
        self.setup_attacks()

    def set_queued_action(
        self,
        qtype=None,
        targ=None,
        msg="",
        attack_penalty=0,
        dmg_penalty=0,
        do_ready=True,
        desc=None,
        action=None,
    ):
        """
        Setup our type of queued action, remember targets, that sorta deal.
        """
        # remember that this is someone we wanted to attack
        if targ and targ not in self.foelist:
            self.add_foe(targ)
        self.queued_action = CombatAction(
            self.character,
            qtype=qtype,
            targ=targ,
            msg=msg,
            attack_penalty=attack_penalty,
            dmg_penalty=dmg_penalty,
            desc=desc,
            action=action,
        )
        if do_ready:
            self.character_ready()

    def character_ready(self):
        """
        Character is ready to proceed from phase 1. Once all
        characters hit ready, we move to phase 2.
        """
        character = self.character
        combat = self.combat
        if combat.ndb.phase == 2:
            combat.remove_afk(character)
            return
        if self.ready:
            combat.ready_check(character)
            return
        combat.remove_afk(character)
        self.ready = True
        character.msg("You have marked yourself as ready to proceed.")
        combat_round = combat.ndb.rounds
        combat.ready_check()
        # if we didn't go to the next turn
        if combat.ndb.phase == 1 and combat.ndb.rounds == combat_round:
            combat.build_status_table()
            combat.display_phase_status(character, disp_intro=False)

    def setup_attacks(self):
        """Sets up our attacks for npcs/auto-attackers"""
        if not self.combat_handler.autoattack:
            self.validate_targets()
        else:
            self.validate_targets(self.do_lethal)
            if self.targets and self.can_fight:
                targ = self.prev_targ
                if not targ:
                    targ = choice(self.targets)
                targ, mssg = self.check_defender_replacement(targ)
                qtype = "kill" if self.do_lethal else "attack"
                self.set_queued_action(qtype, targ, mssg, do_ready=False)
            else:
                ready = False
                if self.automated:
                    self.wants_to_end = True
                    ready = True
                self.set_queued_action("pass", do_ready=ready)

    @staticmethod
    def check_defender_replacement(targ):
        """
        Check if we replace target with a defender
        Args:
            targ (ObjectDB): Character we're attacking

        Returns:
            (targ, msg): New target, replacement

        So we just try to determine who we're attacking if a target has some defenders. We'll
        build a dict of defenders with the number of guys per defender (multinpc guards), then
        do a roll that's weighted by those values. This should make large guard groups much
        more likely to be attacked, but it's not guaranteed.
        """
        mssg = "{rYou attack %s.{n " % targ
        defenders = targ.combat.get_defenders()
        if not defenders:
            return targ, mssg
        # build dict of our defenders to how many dudes they have
        chance_dict = {obj: obj.db.num_living or 1 for obj in defenders if obj}
        # # add original target
        # chance_dict[targ] = targ.db.num_living or 1
        # do a roll from 0 to the total of all dudes in the dict
        roll = randint(0, sum(chance_dict.values()))
        # now go through and see if we get a new target
        for obj, val in chance_dict.items():
            if roll <= val:
                # found our result
                if obj == targ:
                    return targ, mssg
                targ = obj
                mssg += (
                    "It was interfered with, forcing you to target {c%s{n instead. "
                    % targ
                )
                return targ, mssg
            # reduce our roll, so we have increasing probability. 100% by end
            roll -= val

    def validate_targets(self, can_kill=False):
        """
        builds a list of targets from our foelist, making sure each
        target is in combat and meets our requirements. If can_kill
        is false, we can only attack opponents that are conscious.
        """
        beneficiary = self.character.db.guarding
        if (
            beneficiary
            and beneficiary.combat.combat
            and beneficiary.combat.combat == self.combat
        ):
            b_state = beneficiary.combat.state
            for foe in b_state.foelist:
                self.add_foe(foe)
        foelist = [
            ob
            for ob in self.foelist
            if ob.combat.state and ob.combat.state.valid_target
        ]
        if not can_kill:
            foelist = [ob for ob in foelist if ob.combat.can_fight]
        self.targets = foelist

    def add_foe(self, targ):
        """
        Adds a target to our foelist, and also checks for whoever is defending
        them, to add them as potential targets as well.
        """
        if targ in self.foelist or targ == self.character:
            return
        self.foelist.append(targ)
        if targ in self.friendlist:
            # YOU WERE LIKE A BROTHER TO ME
            # NOT A VERY GOOD BROTHER BUT STILL
            self.friendlist.remove(targ)
        defenders = targ.db.defenders or []
        for defender in defenders:
            # YOU'RE HIS PAL? WELL, FUCK YOU TOO THEN
            if defender not in self.friendlist and defender != self.character:
                self.add_foe(defender)

    def add_friend(self, friend):
        """
        FRIIIIIENDS, yes? FRIIIIIIIIENDS.
        """
        if friend in self.friendlist or friend == self.character:
            return
        self.friendlist.append(friend)
        if friend in self.foelist:
            # ALL IS FORGIVEN. YOU WERE LOST, AND NOW ARE FOUND
            self.foelist.remove(friend)
        defenders = friend.db.defenders or []
        for defender in defenders:
            # YOU'RE WITH HIM? OKAY, YOU'RE COOL
            if defender not in self.foelist and self.character != defender:
                self.add_friend(defender)

    def cancel_queued_action(self):
        """Eliminates our queued action"""
        self.queued_action = None

    def npc_target_choice(self, targ):
        """Checks who the npc will target"""
        from .utils import npc_target_choice

        return npc_target_choice(
            targ, self.targets, self.prev_targ, self.combat_handler.switch_chance
        )

    def do_turn_actions(self, took_actions=False):
        """
        Takes any queued action we have and returns a result. If we have no
        queued action, return None. If our queued action can no longer be
        completed, return None. Otherwise, return a result.
        """
        if not self.combat:
            return
        if self.combat.ndb.shutting_down:
            return
        if self.combat.ndb.phase != 2:
            return False
        if not self.character.conscious:
            self.character.msg("You are no longer conscious and can take no action.")
            self.do_pass()
            return took_actions
        if self.character in self.combat.ndb.flee_success:
            # cya nerds
            self.do_flee(self.flee_exit)
            return True
        q = self.queued_action
        self.queued_action = None
        if not q:
            # we have no queued action, so player must act
            if self.automated:
                # if we're automated and have no action, pass turn
                self.do_pass()
            return took_actions
        if q.qtype == "pass" or q.qtype == "delay":
            delay = q.qtype == "delay"
            self.character.msg(q.msg)
            self.do_pass(delay=delay)
            return True
        can_kill = q.qtype in ("kill", "casting")
        # if we have multiple npcs in us, we want to spread out
        # our attacks. validate_targets will only show conscious targets
        self.validate_targets(can_kill)
        if q.qtype == "attack" or q.qtype == "kill":
            targ = q.targ
            if not self.targets:
                self.character.msg("No valid target to attack, or autoattack.")
                if self.automated:
                    self.do_pass()
                return took_actions
            if targ not in self.targets:
                wrong_targ = targ
                targ = choice(self.targets)
                self.character.msg(
                    "%s is no longer a valid target to attack. Attacking %s instead."
                    % (wrong_targ, targ)
                )
            else:
                self.character.msg(q.msg)
            if self.automated:
                targ = self.npc_target_choice(targ)
            # set who we attacked
            self.prev_targ = targ
            attack = self.combat_handler.do_attack(
                targ,
                attacker=self.character,
                attack_penalty=q.attack_penalty,
                dmg_penalty=q.dmg_penalty,
            )
            q.finished_attack = attack
            self.recent_actions.append(q)
            return True
        if q.qtype == "casting":
            if q.working.perform(unsafe=q.unsafe):
                q.working.finalize()
                return True
            elif q.delete_working_on_failure:
                q.working.delete()

    def roll_initiative(self):
        """Rolls and stores initiative for the character."""
        self.initiative = do_dice_check(
            self.character,
            stat_list=["dexterity", "composure"],
            stat_keep=True,
            difficulty=0,
        )
        self.tiebreaker = randint(1, 1000000000)

    @property
    def total_attack_modifier(self):
        """Gets our per-fight attack penalties"""
        base = self.attack_modifier
        base -= self.fatigue_atk_penalty()
        return base

    @property
    def total_defense_modifier(self):
        """Gets our per-fight defense penalties"""
        base = self.defense_modifier
        base -= self.fatigue_def_penalty()
        # it gets increasingly hard to defend the more times you're attacked per round
        overwhelm_penalty = self.times_attacked * 10
        if overwhelm_penalty > 40:
            overwhelm_penalty = 40
        base -= overwhelm_penalty
        return base

    def roll_fatigue(self):
        """
        Chance of incrementing our fatigue penalty. The difficulty is the
        number of combat actions we've taken plus our armor penalty.
        """
        if self.combat_handler.multiple:
            # figure out way later to track fatigue for units
            return
        if self.character.db.never_tire:
            return
        armor_penalty = 0
        if hasattr(self.character, "armor_penalties"):
            armor_penalty = self.character.armor_penalties
        penalty = armor_penalty
        self.num_actions += 1 + (0.12 * armor_penalty)
        penalty += self.num_actions + 25
        keep = self.fatigue_soak
        penalty = int(penalty)
        penalty = penalty // 2 + randint(0, penalty // 2)
        myroll = do_dice_check(
            self.character,
            stat_list=["strength", "stamina", "dexterity", "willpower"],
            skill="athletics",
            keep_override=keep,
            difficulty=int(penalty),
            divisor=2,
        )
        myroll += randint(0, 25)
        if myroll < 0 and self.fatigue_gained_this_turn < 1:
            self._fatigue_penalty += 0.5
            self.fatigue_gained_this_turn += 0.5

    @property
    def fatigue_soak(self):
        """Returns a buffer value before fatigue kicks in"""
        soak = max(self.character.traits.willpower, self.character.traits.stamina)
        try:
            soak += self.character.traits.get_skill_value("athletics", 0)
        except (AttributeError, TypeError, ValueError):
            pass
        if soak < 2:
            soak = 2
        return soak

    @property
    def fatigue_penalty(self):
        """Returns the penalty we currently suffer from fatigue"""
        fat = int(self._fatigue_penalty)
        soak = self.fatigue_soak
        fat -= soak
        if fat < 0:
            return 0
        return fat

    def fatigue_atk_penalty(self):
        """Penalty we currently get to attack from fatigue"""
        fat = self.fatigue_penalty / 2
        if fat > 30:
            return 30
        return fat

    def fatigue_def_penalty(self):
        """Penalty we currently get to defense from fatigue"""
        return int(self.fatigue_penalty * 2.0)

    def add_defender(self, guard):
        """
        add_defender can be called as a way to enter combat, so we'll
        be handling a lot of checks and messaging here. If checks are
        successful, we add the guard to combat, and set them to protect the
        protected character.
        """
        protected = self.character
        combat = self.combat
        if not protected or not guard:
            return
        if not combat:
            return
        if (
            protected.location != combat.ndb.combat_location
            or guard.location != combat.ndb.combat_location
        ):
            return
        if guard.db.passive_guard:
            return
        if not guard.conscious:
            return
        if guard not in combat.characters_in_combat:
            combat.add_combatant(guard)
            guard.msg("{rYou enter combat to protect %s.{n" % protected.name)
        if guard not in self.defenders:
            self.defenders.append(guard)
            combat.msg("%s begins protecting %s." % (guard.name, protected.name))
        fdata = guard.combat
        if fdata:
            fdata.guarding = protected

    def remove_defender(self, guard):
        """
        If guard is currently guarding protected, make him stop doing so.
        Currently not having this remove someone from a .db.defenders
        attribute - these changes are on a per combat basis, which include
        removal for temporary reasons like incapacitation.
        """
        protected = self.character
        combat = self.combat
        if not protected or not guard:
            return
        if guard in self.defenders:
            self.defenders.remove(guard)
            if combat:
                combat.msg(
                    "%s is no longer protecting %s." % (guard.name, protected.name)
                )

    def get_defenders(self):
        """
        Returns list of defenders of a target.
        """
        return [
            ob for ob in self.defenders if ob.combat.state and ob.combat.state.can_act
        ]

    def clear_blocked_by_list(self):
        """
        Removes us from defending list for everyone defending us.
        """
        if self.blocker_list:
            for ob in self.blocker_list:
                ob = ob.combat.state
                if ob:
                    ob.block_flee = None

    def begin_covering(self, targlist):
        """
        Character covers the retreat of characters in targlist, represented by
        CharacterCombatData.covering_targs list and CharacterCombatData.covered_by
        list. Covered characters will succeed in fleeing automatically, but there
        are a number of restrictions. A covering character cannot be covered by
        anyone else.
        """
        character = self.character
        for targ in targlist:
            if targ in self.covered_by:
                character.msg(
                    "%s is already covering you. You cannot cover their retreat."
                    % targ.name
                )
            elif targ in self.covering_targs:
                character.msg("You are already covering %s's retreat." % targ.name)
            elif targ == self.block_flee:
                character.msg(
                    "Why would you cover the retreat of someone you are trying to catch?"
                )
            else:
                self.covering_targs.append(targ)
                targ.combat.covered_by.append(character)
                character.msg("You begin covering %s's retreat." % targ.name)

    def stop_covering(self, targ=None, quiet=True):
        """
        If target is not specified, remove everyone we're covering. Otherwise
        remove targ.
        """
        character = self.character
        if not targ:
            if self.covering_targs:
                character.msg("You will no longer cover anyone's retreat.")
                self.covering_targs = []
                return
            if not quiet:
                character.msg("You aren't covering anyone's retreat currently.")
            return
        self.covering_targs.remove(targ)
        character.msg("You no longer cover %s's retreat." % targ.name)

    def clear_covered_by_list(self):
        """
        Removes us from list of anyone covering us.
        """
        our_character = self.character
        if self.covered_by:
            for character_covering_us in self.covered_by:
                their_handler = character_covering_us.combat.state
                if not their_handler:
                    continue
                if our_character in their_handler.covering_targs:
                    their_handler.stop_covering(targ=our_character)

    def take_action(self, action_cost=1):
        """
        Record that we've used an attack and go to the next character's turn if we're out
        """
        self.remaining_attacks -= action_cost
        if not self.combat:
            return
        self.combat.remove_afk(self.character)
        if (
            self.combat.ndb.phase == 2
            and self.combat.ndb.active_character == self.character
        ):
            if self.character in self.combat.ndb.initiative_list:
                self.combat.ndb.initiative_list.remove(self)
            # if we have remaining attacks, add us to the end
            if self.remaining_attacks > 0:
                self.combat.ndb.initiative_list.append(self)
            self.combat.next_character_turn()

    def do_pass(self, delay=False):
        """
        Passes a combat turn for character. If it's their turn, next character goes.
        If it's not their turn, remove them from initiative list if they're in there
        so they don't get a turn when it comes up.
        """
        character = self.character
        combat = self.combat
        if not combat:
            return
        if delay:
            action_cost = 0
            verb = "delays"
        else:
            action_cost = 1
            verb = "passes"
        combat.msg("%s %s their turn." % (character.name, verb))
        self.take_action(action_cost)

    def do_flee(self, exit_obj):
        """
        Character attempts to flee from combat. If successful, they are
        removed from combat and leave the room. Because of the relatively
        unlimited travel system we have out of combat in Arx, we want to
        restrict movement immediately at the start of combat, as otherwise
        simply leaving is trivial. Currently we don't support combat with
        characters in other spaces, and require a new combat to start every
        time you chase someone down in some extended chase scene. This may
        not be the best implementation, but it's what we're going with for
        now.
        Flee works by flagging the character as attempting to flee. They're
        added to an attempting to flee list. If someone stops them, they're
        removed from the list. Executing the command when already in the
        list will complete it successfully.
        """
        character = self.character
        combat = self.combat
        combat.remove_afk(character)
        if self.covering_targs:
            character.msg("You cannot attempt to run while covering others' retreat.")
            character.msg("Stop covering them first if you wish to try to run.")
            return
        if character not in combat.ndb.flee_success:
            if character in combat.ndb.fleeing:
                character.msg(
                    "You are already attempting to flee. If no one stops you, executing "
                    "flee next turn will let you get away."
                )
                return
            combat.ndb.fleeing.append(character)
            character.msg(
                "If no one is able to stop you, executing flee next turn will let you run away."
            )
            character.msg(
                "Attempting to flee does not take your action this turn. You may still take an action."
            )
            combat.msg(
                "%s begins to try to withdraw from combat." % character.name,
                exclude=[character],
            )
            self.flee_exit = exit_obj
            return
        # we can flee for the hills
        if not exit_obj.access(character, "traverse"):
            character.msg("You are not permitted to flee that way.")
            return
        # this is the command that exit_obj commands use
        exit_obj.at_traverse(character, exit_obj.destination, allow_follow=False)
        combat.msg("%s has fled from combat." % character.name)
        combat.remove_combatant(character)

    def do_stop_flee(self, target):
        """
        Try to stop a character from fleeing. Lists of who is stopping who from running
        are all stored in lists inside the CombataData objects for every character
        in the fighter_data dict. Whether attempts to stop players from running works
        is determined at the start of each round when initiative is rolled. The person
        attempting to flee must evade every person attempting to stop them.
        """
        character = self.character
        combat = self.combat
        combat.remove_afk(character)
        t_fite = target.combat
        if self.block_flee == target:
            character.msg("You are already attempting to stop them from fleeing.")
            return
        if target in self.covering_targs:
            character.msg(
                "It makes no sense to try to stop the retreat of someone you are covering."
            )
            return
        # check who we're currently blocking. we're switching from them
        prev_blocked = self.block_flee
        if prev_blocked:
            # if they're still in combat (in fighter data), we remove character from blocking them
            prev_blocked = prev_blocked.combat
            if prev_blocked:
                if character in prev_blocked.blocker_list:
                    prev_blocked.blocker_list.remove(character)
        # new person we're blocking
        self.block_flee = target
        if character not in t_fite.blocker_list:
            # add character to list of people blocking them
            t_fite.blocker_list.append(character)
        combat.msg(
            "%s moves to stop %s from being able to flee."
            % (character.name, target.name)
        )

    def roll_flee_success(self):
        """
        Determines if we can flee. Called during initiative. If successful,
        we're added to the list of people who can now gtfo. If someone is
        covering our retreat, we succeed automatically. We must outroll every
        player attempting to block us to flee otherwise.
        """
        if self.covered_by:
            return True
        myroll = do_dice_check(
            self.character, stat="dexterity", skill="dodge", difficulty=0
        )
        for guy in self.blocker_list:
            if myroll < do_dice_check(
                guy, stat="dexterity", skill="brawl", difficulty=0
            ):
                return False
        return True

    def toggle_prevent_surrender(self, target):
        """
        Adds or removes a character from our list of people we would stop from surrendering.
        Args:
            target: Character to add/remove from surrender denial list.
        """
        if target in self.prevent_surrender_list:
            self.prevent_surrender_list.remove(target)
            self.character.msg("You no longer prevent the surrender of %s." % target)
        else:
            self.prevent_surrender_list.append(target)
            self.character.msg("You are preventing the surrender of %s." % target)

    def attempt_surrender(self):
        """Register us as trying to surrender."""
        combat = self.combat
        if self.character in combat.ndb.surrender_list:
            combat.ndb.surrender_list.remove(self.character)
            combat.msg("%s removes their bid to surrender." % self.character)
            return
        if combat.register_surrendering_character(self.character):
            combat.msg(
                "%s is attempting to surrender. They will leave combat if not prevented "
                "with surrender/deny." % self.character
            )
        else:
            self.character.msg("You are stopped from attempting to surrender.")

    @property
    def conscious(self):
        """Returns whether our character is conscious"""
        return self.character.conscious

    def get_action_description(self):
        """Returns description of our queued action"""
        return str(self.queued_action)

    def do_check(self, stat=None, skill=None, difficulty=15):
        """Executes a check for a queued action"""
        self.queued_action.do_roll(stat, skill, difficulty)

    def do_check_for_special_action(self):
        """Get stat, skill, and difficulty based on our special action."""
        self.queued_action.do_roll_for_special_action()

    def take_preset_action(self, preset_action):
        """Queues us to take a GM preset action"""
        self.set_queued_action(qtype="Preset", action=preset_action)

    def take_unique_action(self, description):
        """Takes a unique action that the GM can react to."""
        self.set_queued_action(qtype="Unique", desc=description)

    @property
    def last_action(self):
        """Gets our most recent action"""
        try:
            return self.recent_actions[-1]
        except IndexError:
            return None

    def trigger_combat_entry_hooks(self):
        self.character.health_status.at_enter_combat()
