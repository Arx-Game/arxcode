"""
This commandset attempts to define the combat state.
Combat in Arx isn't designed to mimic the real-time
nature of MMOs, or even a lot of MUDs. Our model is
closer to tabletop RPGs - a turn based system that
can only proceed when everyone is ready. The reason
for this is that having 'forced' events based on a
time limit, while perfectly appropriate for a video
game, is unacceptable when attempting to have a game
that is largely an exercise in collaborative story-
telling. It's simply too disruptive, and often creates
situations that are damaging to immersion and the
creative process.
"""
from django.db.models import Q
from evennia import CmdSet
from server.utils.arx_utils import list_to_string
from commands.base import ArxCommand
from evennia.utils import create, evtable
from server.utils.arx_utils import inform_staff
from typeclasses.scripts.combat import combat_settings
from evennia.objects.models import ObjectDB
import random
from typeclasses.npcs import npc_types
from world.stats_and_skills import do_dice_check

CSCRIPT = "typeclasses.scripts.combat.combat_script.CombatManager"


def start_fight_at_room(room, caller=None, exclude_list=None):
    """
    Starts a new fight in a given room.
    Args:
        room: Where the fight will happen
        caller: Who is starting the fight
        exclude_list: list of people not to announce fight is starting to

    Returns:
        The newly created combat script
    """
    exclude_list = exclude_list or []
    cscript = create.create_script(CSCRIPT, obj=room)
    room.ndb.combat_manager = cscript
    cscript.ndb.combat_location = room
    if caller:
        caller_string = caller.key
        announce_exclude = exclude_list + [caller]
    else:
        caller_string = "A non-player"
        announce_exclude = exclude_list
    inform_staff("{wCombat:{n {c%s{n started a fight in room {w%s{n." % (caller_string, room.id))
    room.msg_contents("{rA fight has broken out here. Use @spectate_combat to watch, or +fight to join.",
                      exclude=announce_exclude)
    return cscript


class CombatCommand(ArxCommand):
    """Command that requires that we're in combat to execute it. Ensures any other requirements are met."""
    exclusive_phase = None
    combat = None

    def at_pre_cmd(self):
        """
        Precursor to parsing switches, this will ensure combat exists, is not shutting down, and 
        makes sure we are part of it. Returning True aborts the command sequence.
        """
        try:
            stupid_prize = False  # play stupid games, win stupid prizes: like aiming for a single return
            location = self.caller.location
            self.combat = location.ndb.combat_manager
            caller_combat = self.caller.combat.state.combat
            if self.combat != caller_combat or self.caller.combat.state not in self.combat.ndb.combatants:
                raise AttributeError
            if self.combat.ndb.shutting_down:
                raise combat_settings.CombatError("Combat is shutting down so this command will not work.")
            if self.exclusive_phase and self.exclusive_phase != self.combat.ndb.phase:
                raise combat_settings.CombatError("Wrong combat phase for this command.")
        except AttributeError:
            self.msg("Not participating in a fight at your location.")
            stupid_prize = True
        except combat_settings.CombatError as err:
            self.msg(err)
            stupid_prize = True
        return stupid_prize
    

class CombatCmdSet(CmdSet):
    """CmdSet for players who are currently engaging in combat."""
    key = "CombatCmdSet"
    priority = 20
    duplicates = False
    no_exits = True
    no_objs = False

    def at_cmdset_creation(self):
        """
        This is the only method defined in a cmdset, called during
        its creation. It should populate the set with command instances.

        Note that it can also take other cmdsets as arguments, which will
        be used by the character default cmdset to add all of these onto
        the internal cmdset stack. They will then be able to removed or
        replaced as needed.
        """
        self.add(CmdEndCombat())
        self.add(CmdAttack())
        self.add(CmdSlay())
        self.add(CmdReadyTurn())
        self.add(CmdPassTurn())
        self.add(CmdFlee())
        self.add(CmdFlank())
        self.add(CmdCombatStance())
        self.add(CmdCatch())
        self.add(CmdCoverRetreat())
        self.add(CmdVoteAFK())
        self.add(CmdCancelAction())
        self.add(CmdSurrender())
        self.add(CmdSpecialAction())
        

"""
-------------------------------------------------------------------
+fight will start combat, and will probably be a part of
the mobile commandset. It won't be a part of the combat command set,
because those are only commands that are added once you're placed
in combat mode.
+defend/+protect will also be a part of mobile, marking a character
as automatically entering combat whenever the character they are
protecting does.
-------------------------------------------------------------------
"""


class CmdStartCombat(ArxCommand):
    """
    Starts combat.
    Usage:
        +fight <character to attack>[,<another character to attack>, etc]
        +fight

    +fight will cause you to enter combat with the list of characters
    you supply, or with no arguments will enter a fight that is already
    present in the room if one exists. While in combat, a number of combat-
    specific commands will be made available to you. Combat continues
    while two or more characters are active combatants.

    To end combat, use +end_combat.
    """
    key = "+fight"
    aliases = ["fight"]
    locks = "cmd:all()"
    help_category = "Combat"

    def func(self):
        """Execute command."""
        caller = self.caller
        room = caller.location
        lhslist = self.lhslist
        # find out if we have a combat script already active for this room
        cscript = room.ndb.combat_manager
        if not self.args:
            if not cscript or not cscript.ndb.combatants:
                caller.msg("No one else is fighting here. To start a new " +
                           "fight, {w+fight <character>{n")
                return
            caller.msg(cscript.add_combatant(caller, caller))
            return
        if not self.lhs:
            caller.msg("Usage: +fight <character to attack>")
            return
        # search for each name listed in arguments, match them to objects
        oblist = [caller.search(name) for name in lhslist if caller.search(name)]
        if not oblist:
            caller.msg("No one found by the names you provided.")
            return
        oblist = [ob for ob in oblist if hasattr(ob, 'attackable') and ob.attackable]
        if not oblist:
            self.msg("No one attackable by the names you provided.")
            return
        if not cscript:
            cscript = start_fight_at_room(room, caller, oblist)
        cscript.add_combatant(caller, caller)
        caller.msg("You have started a fight.")
        for ob in oblist:
            # Try to add them, cscript returns a string of success or error
            retmsg = cscript.add_combatant(ob, caller)
            if retmsg:
                caller.msg(retmsg)
        # mark the script as no longer initializing
        cscript.finish_initialization()


class CmdAutoattack(ArxCommand):
    """
    Turns autoattack on or off
    Usage:
        +autoattack
        +autoattack/stop

    +autoattack toggles whether or not you will automatically issue
    attack commands on people fighting you in combat. It has a number
    of intended limitations: first, you won't attempt to finish off
    an incapcitated enemy. This doesn't mean you can't kill someone,
    but you won't keep hitting someone after they're down. Second,
    you will still need to hit 'ready' at the start of each round
    for it to proceed, as a check against AFK, and so that combat
    doesn't instantly resolve when all characters are autoattacking.
    """
    key = "+autoattack"
    aliases = ["autoattack", "auto"]
    locks = "cmd:all()"
    help_category = "Combat"

    def func(self):
        """Execute command."""
        caller = self.caller
        if "stop" in self.switches or caller.combat.autoattack:
            caller.combat.autoattack = False
            caller.msg("Autoattack is now set to be off.")
        else:
            caller.combat.autoattack = True
            caller.msg("Autoattack is now set to be on.")


class CmdProtect(ArxCommand):
    """
    Defends a character
    Usage:
        +protect <character>
        +defend <character>
        +defend/stop
        +protect/stop

    Marks yourself as defending a character. While with them, this will
    mean you will always enter combat whenever they do, on their side. If
    the character is already in combat, you'll join in. While in combat,
    you will attempt to protect the character by intercepting attackers for
    them and guarding them against attempts to flank them. This captures
    the situation of loyal guards who would place themselves in harm's way
    for the person they're protecting.
    If two characters are attempting to protect each other, it simulates
    the situation of two characters fighting back-to-back or otherwise in
    some formation where they try to guard one another against threats, or
    an individual who stubbornly resists being kept out of harm's way.
    You may only focus on defending one character at a time. To stop
    guarding a character, use the /stop switch.
    """
    key = "+protect"
    aliases = ["+defend"]
    locks = "cmd:all()"
    help_category = "Combat"

    def func(self):
        """
        +protect adds people to character.db.defenders list if they're not
        already there, and sets caller.db.guarding to be that character.db
        Only one guarded target allowed at a time. Additionally, we'll
        add them to combat if their guarded character is involved in a
        fight.
        """
        caller = self.caller
        current = caller.db.guarding
        if "stop" in self.switches:
            caller.db.guarding = None
            if current:
                caller.msg("You stop guarding %s." % current.name)
                deflist = current.db.defenders
                if caller in deflist:
                    deflist.remove(caller)
                    if deflist:
                        current.db.defenders = deflist
                    else:
                        current.attributes.remove("defenders")
                    if current.combat.state:
                        current.combat.state.remove_defender(caller)
                return
            caller.msg("You weren't guarding anyone.")
            return
        if current:
            caller.msg("You are currently guarding %s. To guard someone else, first use {w+protect/stop{n." %
                       current.name)
            return
        if not self.args:
            caller.msg("Protect who?")
            return
        to_guard = caller.search(self.args)
        if not to_guard:
            caller.msg("Couldn't find anyone to guard.")
            return
        if not to_guard.attackable:
            caller.msg("Your target is currently not attackable and " +
                       "does not need a guard.")
            return
        # all checks succeeded. Start guarding
        caller.db.guarding = to_guard
        # doing it this way since list/dict methods tend to fail when called directly on attribute object.
        #  assignment works tho
        dlist = to_guard.db.defenders or []
        dlist.append(caller)
        to_guard.db.defenders = dlist
        caller.msg("You start guarding %s." % to_guard.name)
        # now check if they're in combat. if so, we join in heroically.
        if to_guard.combat.state:
            to_guard.combat.state.add_defender(caller)


"""
----------------------------------------------------
These commands will all be a part of the combat
commandset.

CmdEndCombat - character votes for fight to end
CmdAttack - attack a character
CmdSlay - attempt to kill a player character
CmdReadyTurn - mark ready in phase 1
CmdPassTurn - mark pass or delay in phase 2
CmdFlee - attempt to flee combat
CmdFlank - attempt an ambush attack
CmdCombatStance - ex: from defensive style to aggressive
CmdCatch - attempt to prevent a character from fleeing
CmdCoverRetreat - Try to remain behind to cover others to flee
CmdVoteAFK - vote a character as AFK
CmdSpecialAction - takes a special action in combat
----------------------------------------------------
"""


# ----Helper Functions--------------------------------------
def check_combat(caller, quiet=False):
    """Checks for and returns the combat object for a room."""
    if not caller.location:
        return
    combat = caller.location.ndb.combat_manager
    if not combat and not quiet:
        caller.msg("No combat found at your location.")
    return combat


def check_targ(caller, target, verb="Attack"):
    """
    Checks validity of target, sends error messages to caller, returns
    True or False.
    """
    if not target:
        caller.msg("%s who?" % verb)
        return False
    if not hasattr(target, 'attackable') or not target.attackable:
        caller.msg("%s is not attackable and cannot enter combat." % target.name)
        return False
    combat = target.combat.combat
    if not combat or not combat.check_character_is_combatant(target):
        caller.msg("They are not in combat.")
        return False
    if not combat.check_character_is_combatant(caller) and verb != "Admin":
        raise combat_settings.CombatError("Target check for combat(s) that should not exist.")
    return True
# --------------------------------------------------------


class CmdEndCombat(CombatCommand):
    """
    Votes to end combat.

    Usage:
         +end_combat

    Votes to have the combat come to an end. If every other combatant
    agrees, combat will end. If other players don't vote to end combat,
    the only other choice is to {wcontinue{n to begin the combat round,
    or mark non-participating characters as afk.
    """
    key = "+end_combat"
    locks = "cmd:all()"
    help_category = "Combat"
    aliases = ["+end_fight"]

    def func(self):
        """Execute command."""
        self.combat.vote_to_end(self.caller)


class CmdSurrender(CombatCommand):
    """
    Asks to be dropped from the fight.

    Usage:
        surrender
        surrender/deny <character>

    Asks to leave the fight. The /deny switch rejects a character's ability to
    surrender. Both are toggles.
    """
    key = "surrender"
    locks = "cmd:all()"
    help_category = "Combat"

    def func(self):
        """Executes surrender command"""
        if self.args:
            targ = self.caller.search(self.args)
        else:
            targ = self.caller
        if not targ:
            return
        combat = targ.combat.combat
        if not combat or not self.combat.check_character_is_combatant(targ):
            self.msg("%s is not in combat with you." % targ)
            return
        if "deny" in self.switches:
            if not combat.check_character_is_combatant(self.caller):
                self.msg("You must be in combat to prevent surrender.")
                return
            return self.caller.combat.state.toggle_prevent_surrender(targ)
        elif self.args:
            self.msg("Use the command by itself to surrender.")
            return
        targ.combat.state.attempt_surrender()


class CmdAttack(CombatCommand):
    """
    Attack a character
    Usage:
          attack <character>
          attack/only <character>
          attack/critical <character>[=difficulty]
          attack/accuracy <character>[=advantage]
          attack/flub <character>[=to-hit penalty,damage penalty]
          
    An attempt to attack a given character that is in combat with you. If
    the character has defenders, you will be forced to attack one of them
    instead. The /only switch has you attempt to bypass defenders and only
    attack their protected target, but at a difficulty penalty based on
    the number of defenders. Attempting to bypass a large number of guards
    with brute force is extremely difficult and is likely to result in a
    botch. Attempting to launch a sneak attack around them is represented
    by the {wflank{n command.
    The /critical switch allows you to raise the difficulty of your attack
    in order to attempt to do more damage. The default value is 15.
    The /accuracy switch allows you to lower your damage roll for a greater
    chance to hit. The default value is 15.
    The /flub switch allows you to attach penalties to hit and/or damage
    to intentionally make a poor attack.
    """
    key = "attack"
    locks = "cmd:all()"
    help_category = "Combat"
    can_kill = False
    can_bypass = True

    def func(self):
        """Execute command."""
        caller = self.caller
        combat = self.combat
        targ = caller.search(self.lhs)
        if not check_targ(caller, targ):
            return
        if not caller.conscious:
            self.msg("You are not conscious.")
            return
        # we only allow +coupdegrace to kill unless they're an npc
        can_kill = self.can_kill
        if targ.db.npc:
            can_kill = True
        if not targ.conscious and not can_kill:
            message = "%s is incapacitated. " % targ.name
            message += "To kill an incapacitated character, "
            message += "you must use the {w+coupdegrace{n command."
            caller.msg(message)
            return
        defenders = targ.combat.get_defenders()
        attack_penalty = 0
        dmg_penalty = 0
        msg = "{rYou attack %s.{n " % targ
        if defenders:
            if "only" in self.switches:  # we're doing a called shot at a protected target
                if not self.can_bypass:
                    caller.msg("You cannot bypass defenders with the 'only' switch when trying to kill.")
                    return
                attack_penalty += 15 * len(defenders)
            else:  # bodyguard to the rescue!
                targ, msg = targ.combat.state.check_defender_replacement(targ)
        if "critical" in self.switches or "accuracy" in self.switches:
            if "critical" in self.switches and "accuracy" in self.switches:
                caller.msg("These switches cannot be used together.")
                return
            elif self.rhs:
                try:
                    mod = int(self.rhs)
                    if mod < 1 or mod > 50:
                        raise ValueError
                except ValueError:
                    caller.msg("Modifier must be a number between 1 and 50.")
                    return
            else:
                mod = 15
            if "accuracy" in self.switches:
                attack_penalty += -mod
                dmg_penalty += mod
                msg += "Attempting to make your attack more accurate."
            else:
                attack_penalty += mod
                dmg_penalty += -mod
                msg += "Attempting a critical hit."
        elif "flub" in self.switches:
            try:
                attack_penalty, dmg_penalty = [abs(int(num)) for num in self.rhslist]
            except (TypeError, ValueError):
                self.msg("You must specify both a to-hit and damage penalty, though they can be 0.")
                return
            MAX = 500
            if attack_penalty > MAX or dmg_penalty > MAX:
                self.msg("Maximum flub value is %d." % MAX)
                return
            msg += "Adjusting your attack with a to-hit penalty of %d and damage penalty of %d." % (attack_penalty,
                                                                                                    dmg_penalty)
        this_round = combat.ndb.rounds
        do_ready = not caller.combat.state.ready
        qtype = "kill" if can_kill else "attack"
        caller.combat.state.set_queued_action(qtype, targ, msg, attack_penalty, dmg_penalty, do_ready)
        # check if their participation in combat ended after it set them to be ready
        if not combat or combat.ndb.shutting_down or not caller.combat.state:
            return
        # check if this is queue-for-turn-later, ELSE we're going to immediately use our turn.
        if combat.ndb.phase != 2 or combat.ndb.active_character != caller:
            if this_round == combat.ndb.rounds and caller.combat.state.remaining_attacks > 0:
                caller.msg("{wQueuing action for your turn:{n %s" % msg)
        else:
            result = caller.combat.state.do_turn_actions()
            if not result:
                raise combat_settings.CombatError("Beep boop, attac fail.")
            

class CmdSlay(CmdAttack):
    """
    Kill a player character
    Usage:
        +coupdegrace <character>

    Attacks an incapacitated character with the intent on finishing them
    off. We require a separate command for this to ensure that all deaths
    of player characters are intentional, rather than accidental. While
    accidental deaths are realistic, we feel they aren't very compelling
    from a narrative standpoint. You cannot finish off a character until
    any characters defending them are similarly incapacitated.
    
    Characters that are flagged as NPCs do not have this protection, and
    may be killed via +attack in hilarious training accidents and the
    like. This command uses the same switches as 'attack'.
    """
    key = "+coupdegrace"
    aliases = ["kill"]
    locks = "cmd:all()"
    help_category = "Combat"
    can_kill = True
    can_bypass = False


class CmdReadyTurn(CombatCommand):
    """
    Mark yourself ready for combat to proceed
    Usage:
        continue
        ready

    When in the setup phase of combat, 'continue' or 'ready' will mark you
    as being ready to move on to the combat round. 
    
    Combat is turn-based without any timers to ensure that players have
    adequate time in order to roleplay during fights. This is not a license
    to attempt to stall to avoid consequences in RP, however, and trying
    to freeze combat by not taking your turn or marking yourself ready is
    very strictly prohibited.
    """
    key = "continue"
    aliases = ["ready"]
    locks = "cmd:all()"
    help_category = "Combat"

    def func(self):
        """Execute command."""
        self.caller.combat.state.character_ready()


class CmdPassTurn(CombatCommand):
    """
    Pass your turn in combat
    Usage
        pass
        delay

    Passes your turn in combat. If 'delay' is used instead, will
    defer your turn until everyone else has been offered a chance to
    go.
    """
    key = "pass"
    aliases = ["delay"]
    help_category = "Combat"
    exclusive_phase = 2

    def func(self):
        """Executes the command"""
        caller = self.caller
        cmdstr = self.cmdstring.lower()
        delay = cmdstr == "delay"
        if self.combat.ndb.active_character != caller:
            caller.msg("Queuing this action for later.")
            mssg = "You %s your turn." % cmdstr
            caller.combat.state.set_queued_action(cmdstr, None, mssg)
            return
        caller.combat.state.do_pass(delay=delay)


class CmdCancelAction(CombatCommand):
    """
    cancels your current action
    Usage:
        cancel

    Cancels any current action that you have queued up.
    """
    key = "cancel"
    help_category = "Combat"

    def func(self):
        """Executes the CancelAction command"""
        state = self.caller.combat.state
        state.cancel_queued_action()
        self.msg("You clear any queued combat action.")
        self.combat.build_status_table()
        self.combat.display_phase_status(self.caller, disp_intro=False)


class CmdFlee(CombatCommand):
    """
    Attempt to run out of combat
    Usage:
        flee <exit>

    Attempts to exit combat by running for the specified exit.name
    Fleeing always takes a full turn - you execute the command,
    and if no one successfully stops you before your next turn,
    you execute 'flee <exit>' again to leave.
    """
    key = "flee"
    locks = "cmd:all()"
    help_category = "Combat"

    def func(self):
        """Execute command."""
        caller = self.caller
        exit_obj = caller.search(self.args)
        if not exit_obj:
            return
        if not exit_obj.is_exit:
            caller.msg("That is not an exit.")
            return
        if hasattr(exit_obj, "passable") and not exit_obj.passable(self.caller):
            caller.msg("That exit is blocked by an obstacle you have not passed!")
            return
        caller.combat.state.do_flee(exit_obj)


class CmdFlank(CombatCommand):
    """
    Attempt to ambush an opponent
    Usage:
        flank <character>
        flank/only <character>

    Represents trying to maneuver around to the unprotected side of a
    character for a more successful attack. While the normal {wattack{n
    command attempts to simply barrel past someone's guards, flank
    attempts to evade them and strike the person being guarded before
    they can respond. If the 'only' switch is used, you will back off
    and refrain from attacking guards if you're spotted. Otherwise,
    you will attack the guard who stops you by default.
    """
    key = "flank"
    locks = "cmd:all()"
    help_category = "Combat"
    exclusive_phase = 2

    def func(self):
        """Execute command."""
        caller = self.caller
        if self.combat.ndb.active_character != caller:
            caller.msg("You may only perform this action on your turn.")
            return
        targ = caller.search(self.args)
        if not targ or not check_targ(caller, targ):
            return
        if not targ.conscious and not targ.db.npc:
            caller.msg("You must use '{w+coupdegrace{n' to kill characters.")
            return
        # Check whether we attack guards
        attack_guards = "only" not in self.switches
        # to do later - adding in sneaking/invisibility into game
        caller.combat.do_flank(targ, sneaking=False, invis=False, attack_guard=attack_guards)
        return


class CmdCombatStance(ArxCommand):
    """
    Defines how character fights
    Usage:
        stance <type>

    Roughly defines how your character behaves in a fight, applying
    both defensive and offensive modifiers. <type> must be one of the
    following words, which are styles from the most defensive to the most
    aggressive: 'defensive', 'guarded', 'balanced', 'aggressive', 'reckless'.
    Combat stance of the attacker has no effect on flanking attacks.
    Changing your combat stance does not use up your combat action for your
    turn. Unlike most combat settings, stance is actually persistent between
    fights if not changed.
    """
    key = "stance"
    locks = "cmd:all()"
    help_category = "Combat"

    def func(self):
        """Execute command."""
        caller = self.caller
        if not self.args:
            caller.msg("Current combat stance: %s" % caller.combat.stance)
            return
        elif self.args not in combat_settings.COMBAT_STANCES:
            message = "Your stance must be one of the following: "
            message += "{w%s{n" % list_to_string(sorted(combat_settings.COMBAT_STANCES), endsep="or")
            caller.msg(message)
            return
        combat = check_combat(caller)
        if combat and combat.ndb.phase != 1:
            self.msg("Can only change stance between rounds.")
            return
        caller.combat.change_stance(self.args)
        return


class CmdCatch(CombatCommand):
    """
    Attempt to stop someone from running
    Usage:
        catch <character>
        
    Attempts to maneuver your character to block another character from
    fleeing. You can only attempt to catch one character at a time, though
    you may declare your intent at any time, before a character decides
    whether they would wish to attempt to run or not.
    """
    key = "catch"
    locks = "cmd:all()"
    help_category = "Combat"

    def func(self):
        """Execute command."""
        caller = self.caller
        targ = caller.search(self.args)
        if not targ or not check_targ(caller, targ, "Catch"):
            return
        caller.combat.state.do_stop_flee(targ)


class CmdCoverRetreat(CombatCommand):
    """
    Attempt to cover the retreat of other characters
    Usage:
        cover <character>[,<character2>,<character3>...]
        cover/stop [<character>, <character2>...]
        
    Cover has your character declare your intent to remain behind and fight
    others while you cover the retreat of one or more characters. Covering
    a retreat does not take your action for the round, but prevents you
    from fleeing yourself and imposes a difficulty penalty on attacks due
    to the distraction.
    """
    key = "cover"
    locks = "cmd:all()"
    help_category = "Combat"
    exclusive_phase = 2

    def func(self):
        """Execute command."""
        caller = self.caller
        combat = self.combat
        if combat.ndb.active_character != caller:
            caller.msg("You may only perform this action on your turn.")
            return
        if "stop" in self.switches and not self.args:
            caller.combat.stop_covering(quiet=False)
            return
        targlist = [caller.search(arg) for arg in self.lhslist]
        targlist = [targ for targ in targlist if check_targ(caller, targ, "Cover")]
        if not targlist:
            return
        if "stop" in self.switches:
            for targ in targlist:
                caller.combat.stop_covering(targ)
        else:
            caller.combat.begin_covering(targlist)


class CmdVoteAFK(CombatCommand):
    """
    Voting a character 'away from keyboard' to remove them from combat.
    Usage:
        +vote_afk <character>
        
    People have to go AFK sometimes. It's a game, and RL has to take priority.
    Unfortunately, with turn-based combat, that can mean you can wait a long
    time for someone to take their turn. If it's someone's turn and they're
    AFK, you can +vote_afk to give them 2 minutes to take an action. At the
    end of that period, +vote_afk begins to accumulate votes against them
    to kick them. Voting must be unanimous by all except the player in who
    is being voted upon.
    """
    key = "+vote_afk"
    locks = "cmd:all()"
    help_category = "Combat"

    def func(self):
        """Execute command."""
        caller = self.caller
        targ = caller.search(self.args, global_search=True)
        if not targ:
            return
        if not targ.location or targ.location != self.combat.ndb.combat_location:
            # if they're no longer there, just remove them automatically
            self.combat.remove_combatant(targ)
            return
        if not check_targ(caller, targ, "+vote_afk"):
            return
        self.combat.afk_check(caller, targ)


class CmdCombatStats(ArxCommand):
    """
    View your combat stats
    Usage:
        +combatstats
        +combatstats/view <character> - GM-only usage
        
    Displays your combat stats.
    """
    key = "+combatstats"
    locks = "cmd:all()"
    help_category = "Combat"

    def func(self):
        """Execute command."""
        if "view" in self.switches:
            if not self.caller.player.check_permstring("builders"):
                self.msg("Only GMs can view +combatstats of other players.")
                return
            pc = self.caller.player.search(self.args)
            if not pc:
                return
            char = pc.char_ob
        else:
            char = self.caller
        fighter = char.combat
        msg = "\n{c%s{w's Combat Stats\n" % char
        self.msg(msg + fighter.display_stats())
    
    
class CmdSpecialAction(CombatCommand):
    """
    Take special action in combat 
    Usage:
        @specialaction
        @specialaction/preset <number of GM declared action>
        @specialaction <description of what you're doing>
        
    Declares intent to take an action in a GM'd combat. This allows players to
    either select a type of action that a GM has declared available, or to
    specify their own action.
    """
    key = "@specialaction"
    locks = "cmd:all()"
    help_category = "Combat"
    
    def func(self):
        """Executes SpecialAction command"""
        combat = self.combat
        if not combat.managed_mode:
            self.msg("Special actions can only be taken when combat has a presiding GM.")
            return
        if not self.args:
            return self.list_actions(combat)
        if "preset" in self.switches:
            return self.do_preset_action(combat)
        return self.do_special_action(combat)
        
    def list_actions(self, combat):
        """Lists available GM actions, any action caller is taking"""
        self.msg(combat.list_special_actions())
    
    def do_preset_action(self, combat):
        """Selects an action defined by a GM"""
        try:
            action = combat.ndb.special_actions[int(self.lhs) - 1]
        except (IndexError, ValueError, TypeError):
            msg = "%s does not match a current action.\n" % self.lhs
            self.msg(msg + combat.list_special_actions())
        else:
            self.caller.combat.state.take_preset_action(action)
            self.msg("Queued %s." % action)
    
    def do_special_action(self, combat):
        """Defines an action that the player wishes to do"""
        self.caller.combat.state.take_unique_action(self.args)
        self.msg("Set yourself to take the following action: %s" % self.args)
    
    
"""
----------------------------------------------------
These commands will all be a part of the staff
commands for manipulating combat: observing combat,
as well as changing events.
----------------------------------------------------
"""


class CmdObserveCombat(ArxCommand):
    """
    Enters combat as an observer
    Usage:
            @spectate_combat
            @spectate_combat/stop
    Enters combat if it is present in your current location.
    """
    key = "@spectate_combat"
    locks = "cmd:all()"
    help_category = "Combat"

    def func(self):
        """Execute command."""
        caller = self.caller
        if "stop" in self.switches:
            combat = self.caller.combat.spectated_combat
            if not combat:
                self.msg("You are not watching a combat.")
                return
            combat.remove_observer(caller, quiet=False)
            return
        combat = check_combat(caller)
        if not combat:
            return
        if caller.combat.spectated_combat:
            caller.msg("You are already spectating a combat.")
            return
        if caller.combat.state in combat.ndb.combatants:
            caller.msg("You are already involved in this combat.")
            return
        combat.add_observer(caller)


class CmdFightStatus(ArxCommand):
    """
    Displays the status of combat

    Usage:
        +combatstatus

    Displays status of fight at your room.
    """
    key = "+combatstatus"
    aliases = ["+fightstatus", "+cs"]
    locks = "cmd:all()"
    help_category = "Combat"

    def func(self):
        """Executes the flee command"""
        combat = check_combat(self.caller)
        if not combat:
            return
        combat.build_status_table()
        combat.display_phase_status(self.caller, disp_intro=False)


class CmdAdminCombat(ArxCommand):
    """
    Admin commands for combat
    Usage:
        @admin_combat/startfight - starts a fight at your location
        @admin_combat/managed  - toggles combat being in managed mode
        @admin_combat/add <character>
        @admin_combat/kick <character> - removes a character from combat.
        @admin_combat/force <character>=<action>
        @admin_combat/execute - makes current character execute their action
        @admin_combat/next - moves past current character, goes to next
        @admin_combat/requeue <character> - adds character back to initiative
        @admin_combat/check <character>=<stat>/<skill>,<difficulty>
        @admin_combat/checkall <action name> - rolls for all doing action
        @admin_combat/listrolls
        @admin_combat/ready <character> - Marks character as ready to proceed
        @admin_combat/stopfight - ends combat completely
        @admin_combat/afk <character> - Moves AFK player to observers
        @admin_combat/view <character> - shows combat stats
        @admin_combat/readyall - Marks all characters ready
        @admin_combat/cleave <NPC> - toggles ability to cleave
        @admin_combat/wild <NPC>=<percent> - chance of target-switching
        @admin_combat/risk <rating> - risk for the combat
        @admin_combat/modifiers <character>=<type>,<value>
        @admin_combat/addspecial <action name>=<stat>/<skill>,<difficulty>
        @admin_combat/rmspecial <preset action's number>

    A few commands to allow a GM to move combat along by removing AFK or
    stalling characters or forcing them to pass their turn or ending a
    fight completely. /startfight will automatically add you as an observer,
    otherwise use +specate_combat to watch.
    """
    key = "@admin_combat"
    locks = "cmd:perm(admin_combat) or perm(Wizards)"
    help_category = "Combat"
    modifier_categories = ("attack", "defense", "mitigation", "damage", "special_action")

    def func(self):
        """Execute command."""
        caller = self.caller
        if "startfight" in self.switches:
            return self.start_fight()
        combat = check_combat(caller)
        if not combat:
            return
        switches = self.switches
        if not switches:
            caller.msg("@admin_combat requires switches.")
            return
        if "listrolls" in switches:
            return self.list_rolls(combat)
        if "next" in switches:
            return self.next_turn(combat)
        if "checkall" in switches:
            return self.make_all_checks_for_action(combat)
        if "managed" in switches:
            return self.toggle_managed_mode(combat)
        # As a note, we use .key rather than .name for admins to ensure they use
        # their real GM name rather than some false name that .name can return
        if "stopfight" in switches:
            combat.msg("%s has ended the fight." % caller.key)
            combat.end_combat()
            return
        if "readyall" in switches:
            if combat.ndb.phase == 2:
                self.msg("They are already in phase 2.")
                return
            combat.start_phase_2()
            return
        if "risk" in switches:
            from server.utils.arx_utils import dict_from_choices_field
            from world.dominion.models import RPEvent
            try:
                choice = dict_from_choices_field(RPEvent, "RISK_CHOICES")[self.args]
            except KeyError:
                self.msg("Invalid choice: %s" % ", ".join(ob[1] for ob in RPEvent.RISK_CHOICES))
                return
            combat.ndb.risk = choice
            self.msg("Risk level set to %s (%s)." % (self.args, choice))
            return
        if "addspecial" in switches:
            return self.add_special_action(combat)
        if "rmspecial" in switches:
            return self.remove_special_action(combat)
        if "execute" in switches:
            return self.execute_current_action(combat)
        targ = caller.search(self.lhs)
        if "add" in self.switches:
            return self.add_combatant(targ, combat)
        if not check_targ(caller, targ, "Admin"):
            return
        if "check" in switches:
            return self.make_check_for_character(targ, combat)
        if "kick" in switches:
            combat.msg("%s has kicked %s." % (caller.key, targ.name))
            combat.remove_combatant(targ)
            return
        if "force" in switches:
            return self.force_action(targ, combat)
        if "ready" in switches:
            combat.msg("%s marks %s as ready to proceed." % (caller.key, targ.name))
            targ.combat.character_ready()
            return
        if "afk" in switches:
            combat.msg("%s has changed %s to an observer." % (caller.key, targ.name))
            combat.move_to_observer(targ)
            return
        if "view" in self.switches:
            cdat = combat.get_fighter_data(targ.id)
            caller.msg("{wStats for %s.{n" % cdat)
            caller.msg(cdat.display_stats())
            return
        if "cleave" in self.switches:
            return targ.combat.toggle_cleave(caller=caller)
        if "wild" in self.switches and self.rhs:
            return targ.combat.set_switch_chance(val=self.rhs, caller=caller)
        if "modifiers" in self.switches:
            return self.display_or_set_modifiers(targ)
        if "requeue" in switches:
            return self.add_to_initiative_list(targ, combat)
        else:
            caller.msg("Invalid switch or missing arg.")
            
    def display_or_set_modifiers(self, target):
        """Displays or sets a temporary modifier to target character for this combat"""
        if not target.combat.state:
            self.msg("They're not in combat, yo.")
            return
        if not self.rhs:
            # display modifiers
            return self.display_modifiers(target)
        # set modifiers
        try:
            mod_type = self.rhslist[0]
            value = int(self.rhslist[1])
            if mod_type.lower() not in self.modifier_categories:
                raise IndexError
        except (IndexError, ValueError):
            self.msg("Value must be a number, and modifier must be one of the following: %s"
                     % ", ".join(self.modifier_categories))
        else:
            setattr(target.combat.state, mod_type + "_modifier", value)
            self.display_modifiers(target)
            
    def display_modifiers(self, target):
        """Displays temporary modifiers for this combat for target character"""
        msg = "Modifiers for %s:\n" % target
        msg += ", ".join("%s: %s" % (mod_name, getattr(target.combat.state, mod_name + "_modifier"))
                         for mod_name in self.modifier_categories)
        self.msg(msg)

    def start_fight(self):
        """Starts a fight at our location"""
        combat = check_combat(self.caller, quiet=True)
        if combat:
            self.msg("There is already a fight at your location.")
            return
        combat = start_fight_at_room(self.caller.location, self.caller)
        combat.add_observer(self.caller)
        
    def add_combatant(self, target, combat):
        """
        Adds a character to the combat.
        
            Args:
                target: character we're adding
                combat: combat we're adding them to
        """
        if not target:
            return
        if combat.check_character_is_combatant(target):
            self.msg("%s is already in combat." % target)
            return
        combat.add_combatant(target, reset=True)
        self.msg("Added %s." % target)
        
    def add_special_action(self, combat):
        """Adds an action to the combat"""
        if not self.lhs:
            self.msg(combat.list_special_actions())
            return
        stat, skill, difficulty = self.get_check()
        if not stat:
            return
        combat.add_special_action(self.lhs, stat, skill, difficulty)
        self.msg(combat.list_special_actions())
        
    def get_check(self):
        """Get check we're going to require character to make from args"""
        skill = None
        try:
            stat_list = self.rhslist[0].split("/")
            stat = stat_list[0].strip()
            if len(stat_list) > 1:
                skill = stat_list[1].strip()
            difficulty = int(self.rhslist[1])
        except (IndexError, ValueError, TypeError):
            self.msg("Must provide a stat and difficulty.")
            return None, None, None
        return stat, skill, difficulty
        
    def remove_special_action(self, combat):
        """Removes an action from the combat."""
        try:
            combat.special_actions.pop(int(self.lhs) - 1)
            msg = "Action removed.\n"
        except (TypeError, ValueError, IndexError):
            msg = "No action by that number.\n"
        self.msg(msg + combat.list_special_actions())
        
    def list_rolls(self, combat):
        """List all rolls characters have made for special actions"""
        self.msg(combat.list_rolls_for_special_actions())
        combat.ndb.gm_afk_counter = 0
    
    def next_turn(self, combat):
        """Marks current character turn as done and go to next character"""
        if combat.ndb.phase == 1:
            self.msg("Currently in setup phase. Use /readyall to advance to next phase.")
            return
        self.msg("Advancing to next character.")
        combat.next_character_turn()
        combat.ndb.gm_afk_counter = 0
    
    def make_check_for_character(self, character, combat):
        """Makes a check for a character's special action."""
        stat, skill, difficulty = self.get_check()
        if not stat:
            return
        if not character.combat.state:
            self.add_combatant(character, combat)
        character.combat.state.do_check(stat, skill, difficulty)
        combat.ndb.gm_afk_counter = 0
    
    def make_all_checks_for_action(self, combat):
        """Makes checks for every character doing a given GM-defined special action."""
        try:
            action = combat.special_actions[int(self.lhs) - 1]
        except (TypeError, ValueError, IndexError):
            msg = "No action by that number.\n"
            self.msg(msg + combat.list_special_actions())
        else:
            self.msg("Making all checks for %s." % action)
            combat.make_all_checks_for_special_action(action)
        combat.ndb.gm_afk_counter = 0
    
    def toggle_managed_mode(self, combat):
        """Toggles whether combat will pause at each character."""
        combat.managed_mode = not combat.managed_mode
        if combat.managed_mode:
            # make sure the caller is in the list of GMs
            combat.add_gm(self.caller)
            self.msg("Combat is now in managed mode, and will pause before each character to allow for rolls.")
        else:
            self.msg("Combat is no longer in managed mode, and will automatically execute actions without pausing.")
        combat.ndb.gm_afk_counter = 0

    def add_to_initiative_list(self, character, combat):
        """Gives a character another action."""
        if combat.ndb.phase != 2:
            self.msg("Only usable in phase 2.")
            return
        if not character.combat.state:
            self.add_combatant(character, combat)
        combat.ndb.initiative_list.append(character.combat.state)
        self.msg("Giving %s an action at the end of initiative list." % character)
        combat.ndb.gm_afk_counter = 0
    
    def execute_current_action(self, combat):
        """Causes currently selected character's action to execute."""
        character = combat.ndb.active_character
        try:
            character.combat.state.do_roll_for_special_action()
        except AttributeError:
            self.msg("Could not roll for that character. Not their turn or no special action defined.")
        combat.ndb.gm_afk_counter = 0
            
    def force_action(self, character, combat):
        """Sets the action of the current character."""
        self.msg("Forcing %s to: %s" % (character, self.rhs))
        character.execute_cmd(self.rhs)
        combat.ndb.gm_afk_counter = 0
        combat.ndb.gm_afk_counter = 0


class CmdCreateAntagonist(ArxCommand):
    """
    Creates an object to act as an NPC antagonist for combat.
    Usage for Summon/dismiss:
        @spawn
        @spawn <ID #>[=<Spawn Message>]
        @spawn/dismiss <monster>
        
    Creation:
        @spawn/boss <name>=<boss rating>,<threat>
        @spawn/mooks <name>=<quantity>,<threat>
        
    Customization:
        @spawn/name <ID #>=<new name>
        @spawn/desc <ID #>=<new description>
        @spawn/threat <ID #>=<new threat rating>
        @spawn/boss_rating <ID #>=<boss rating>
        @spawn/quantity <ID #>=<quantity>
        @spawn/mirror <ID #>=<player character>

    Created npc antagonists to use. NPCs are created with a threat value which
    controls the base values of all their skills: A threat 5 group of mooks 
    will all have 5s in weapon skills, for example. Mooks are intended to be a 
    group of mobs with a quantity that you specify, while a boss can be a much
    tougher individual mob. A boss rating is a hugely impactful stat that 
    greatly increases the health and damage of an npc. Expect for boss rating 
    of 5 to one-shot most npcs.
    """
    key = "@spawn"
    locks = "cmd:perm(spawn) or perm(Builders)"
    help_category = "GMing"
    MOOKS = "typeclasses.npcs.npc.MultiNpc"
    BOSS = "typeclasses.npcs.npc.Npc"
    ntype = 0  # guard combat_type used by default
    creation_switches = ("boss", "mook", "mooks")
    customization_switches = ("name", "desc", "description", "threat", "boss_rating", 
                              "quantity", "mirror", "darklink")
    
    @property
    def npc_queryset(self):
        """Queryset for spawned npcs"""
        return ObjectDB.objects.filter(Q(db_typeclass_path=self.MOOKS) | Q(db_typeclass_path=self.BOSS))

    def func(self):
        """Execute command."""
        if not self.switches and not self.args:
            # list available types
            return self.list_available_spawns()
        if self.check_switches(self.creation_switches):
            return self.create_new_spawn()
        npc = self.get_npc(self.lhs)
        if not npc:
            return
        if not self.switches:
            return self.spawn_npc(npc)
        elif self.check_switches(self.customization_switches):
            return self.customize_spawned_npc(npc)
        elif 'dismiss' in self.switches:
            return self.dismiss_spawned_npc(npc)
        self.msg("Invalid switch.")
    
    def list_available_spawns(self):
        """Displays table of available spawn npcs"""
        ntypes = npc_types.npc_templates.keys()
        npcs = self.npc_queryset
        self.msg("Valid npc types: %s" % ", ".join(ntypes))
        table = evtable.EvTable("ID", "Name", "Type", "Amt", "Threat", "Location", width=78)
        for npc in npcs:
            ntype = npc_types.get_npc_singular_name(npc.db.npc_type)
            num = npc.db.num_living if ntype.lower() != "champion" else "Unique"
            table.add_row(npc.id, npc.key or "None", ntype, num,
                          npc.db.npc_quality, npc.location.id if npc.location else None)
        self.msg(str(table), options={'box': True})
        
    def create_new_spawn(self):
        """Creates a new boss or group of mooks."""
        name = self.lhs
        try:
            value, threat = int(self.rhslist[0]), int(self.rhslist[1])
        except (ValueError, TypeError, IndexError):
            self.msg("Must give two integer values on right hand side.")
            return
        msg = "Created new "
        if "boss" in self.switches:
            npc = create.create_object(key=name, typeclass=self.BOSS)
            npc.boss_rating = value
            qty = 1
            msg += "boss with rating of %s " % value
        else:
            npc = create.create_object(key=name, typeclass=self.MOOKS)
            qty = value
            msg += "mooks with quantity of %s " % qty
        msg +=  "and threat of %s." % threat
        npc.setup_npc(self.ntype, threat, qty, sing_name=name, plural_name=name)
        self.msg(msg)
    
    def get_npc(self, args):
        """Gets an npc by ID"""
        try:
            if args.isdigit():
                return self.npc_queryset.get(id=args)
            return self.npc_queryset.get(db_key__iexact=args)
        except (ObjectDB.DoesNotExist, ValueError):
            self.msg("No npc by that ID.")
        except ObjectDB.MultipleObjectsReturned:
            self.msg("More than one match for %s." % args)
            
    def spawn_npc(self, npc):
        """Spawns the npc if it isn't already in game"""
        if npc.location:
            self.msg("That is not an inactive npc. Dismiss it, or create a new npc instead.")
            return
        npc.location = self.caller.location
        self.msg("You spawn %s." % npc)
        if self.rhs:
            self.caller.location.msg_contents(self.rhs)
    
    def customize_spawned_npc(self, npc):
        if not self.rhs:
            self.msg("This switch requires some form of argument.")
            return
        if "mirror" in self.switches or "darklink" in self.switches:
            return self.mirror_character(npc)
        elif "name" in self.switches:
            return self.adjust_spawn_name(npc)
        elif "desc" in self.switches or "description" in self.switches:
            npc.set_npc_new_desc(self.rhs)
            self.msg("Description for %s set as: %s" % (npc, self.rhs))
            return
        elif "threat" in self.switches:
            return self.adjust_spawn_threat(npc)
        elif "boss_rating" in self.switches:
            pass
        elif "quantity" in self.switches:
            return self.adjust_spawn_quantity(npc)
    
    def dismiss_spawned_npc(self, npc):
        if not hasattr(npc, 'dismiss'):
            self.msg("Invalid target - you cannot dismiss that.")
            return
        npc.dismiss()
        self.msg("Dismissed %s." % npc)
    
    def mirror_character(self, npc):
        """Copies a player character's stats to an NPC."""
        character = self.caller.search(self.rhs)
        if not character:
            self.msg("No character found. Use #ID if they're not in the room.")
            return
        for stat in ("strength", "stamina", "dexterity"):
            val = character.attributes.get(stat, 0)
            npc.attributes.add(stat, val)
        skills = character.db.skills
        npc.attributes.add("skills", dict(skills))
    
    def adjust_spawn_name(self, npc):
        oldname = str(npc)
        kwarg_type = "sing"
        if npc.db_typeclass_path == self.MOOKS:
            kwarg_type = "plural"
        kwarg_type += "_name"
        kwargs = { kwarg_type: self.rhs }
        npc.set_npc_new_name(**kwargs)
        self.msg("Renamed %s to: %s" % (oldname, self.rhs))
        
    def adjust_spawn_threat(self, npc):
        try:
            npc.setup_stats(self.ntype, int(self.rhs))
        except (TypeError, ValueError):
            self.msg("Threat must be a number.")
        else:
            self.msg("%s threat set to %s." % (npc, self.rhs))
    
    def adjust_spawn_quantity(self, npc):
        try:
            npc.db.num_living = int(self.rhs)
        except (TypeError, ValueError):
            self.msg("Quantity must be a number.")
        else:
            self.msg("%s quantity set to %s." % (npc, self.rhs))


class CmdHarm(ArxCommand):
    """
    Harms characters and sends them a message

    Usage:
        @harm[/mercy] <character1, char2...>=<amount>[/<message>]
        @harm/private <same as above>
        @harm/noarmor <same as above>
        @harm/global <same as above - GM-Only usage>

    Causes damage to characters. If /mercy switch is used, a character cannot 
    be killed by the attack, only further damaged.
    <Message> is broadcast to the room. If /private switch is used, <message>
    is sent only to the characters involved.
    """
    key = "@harm"
    locks = "cmd:all()"
    help_category = "GMing"

    def func(self):
        """Executes the harm command"""
        message = None
        damage = 0
        rhs = self.rhs or ""
        rhslist = rhs.split("/", 1)
        if len(rhslist) > 1:
            message = rhslist[1]
        try:
            if not self.lhs or not self.rhslist:
                raise ValueError
            damage = int(rhslist[0])
            if damage < 0:
                damage = 0
        except (TypeError, ValueError):
            self.msg("Must provide at least one character = number for damage amount.")
            return
        victims = []
        global_search = "global" in self.switches and self.caller.check_permstring("builders")
        for arg in self.lhslist:
            victim = self.caller.search(arg, global_search=global_search)
            if victim:
                victims.append(victim)
        if not self.can_harm_others():
            if any(ob for ob in victims if ob != self.caller):
                self.msg("Non-GM usage. Pruning others from your list.")
            victims = [ob for ob in victims if ob == self.caller]
        if not victims:
            return
        from typeclasses.scripts.combat.attacks import Attack
        use_mitigation = "noarmor" not in self.switches
        can_kill = "mercy" not in self.switches
        private = "private" in self.switches
        attack = Attack(targets=victims, affect_real_dmg=True, damage=damage, use_mitigation=use_mitigation, 
                        can_kill=can_kill, private=private, story=message, inflictor=self.caller)
        try:
            attack.execute()
        except combat_settings.CombatError as err:
            self.msg(err)
        else:
            if damage > 0:
                inform_staff("{c%s{n used @harm for %s damage on %s." % (self.caller, damage, 
                                                                         list_to_string(victims)))
        
    def can_harm_others(self):
        """Checks if the caller can harm other players"""
        if self.caller.check_permstring("builders"):
            return True
        event = self.caller.location.event
        if not event:
            return False
        return self.caller.player_ob.Dominion in event.gms.all()


class CmdHeal(ArxCommand):
    """
    Administers medical care to a character.
    Usage:
        +heal <character>
        +heal/permit <character>
        +heal/global <same as above - GM-Only usage>
        +heal/gmallow <character>[=<bonus if positive, negative for penalty>]

    Helps administer medical care to a character who is not
    presently in combat. This will attempt to wake them up
    if they have been knocked unconscious. You must have permission
    to attempt to heal someone, which is granted via the /permit switch.
    """
    key = "+heal"
    locks = "cmd:all()"
    help_category = "Combat"

    def func(self):
        """Execute command."""
        caller = self.caller
        global_search = "global" in self.switches and caller.check_permstring("builders")
        targ = caller.search(self.lhs, global_search=global_search)
        if not targ:
            return
        if "permit" in self.switches:
            permits = targ.ndb.healing_permits or set()
            permits.add(caller)
            targ.ndb.healing_permits = permits
            self.msg("{wYou permit {c%s {wto heal you." % targ)
            targ.msg("{c%s {whas permitted you to heal them." % caller)
            return
        event = caller.location.event
        if "gmallow" in self.switches:
            if not event or caller.player.Dominion not in event.gms.all() and not caller.check_permstring("builders"):
                self.msg("This may only be used by the GM of an event.")
                return
            modifier = 0
            if self.rhs:
                try:
                    modifier = int(self.rhs)
                except ValueError:
                    self.msg("Modifier must be a number.")
                    return
            targ.ndb.healing_gm_allow = modifier
            noun = "bonus" if modifier > 0 else "penalty"
            self.msg("You have allowed %s to use +heal, with a %s to their roll of %s." % (targ, noun, abs(modifier)))
            return
        if not targ.dmg:
            caller.msg("%s does not require any medical attention." % targ)
            return
        if not hasattr(targ, 'recovery_test'):
            caller.msg("%s is not capable of being healed." % targ)
            return
        combat = check_combat(caller, quiet=True)
        if combat:
            if caller in combat.ndb.combatants or targ in combat.ndb.combatants:
                caller.msg("You cannot heal someone in combat.")
                return
        if event and event.gms.all() and caller.ndb.healing_gm_allow is None:
            self.msg("There is an event here and you have not been granted GM permission to use +heal.")
            return
        aid_given = caller.db.administered_aid or {}
        # timestamp of aid time
        aid_time = aid_given.get(targ.id, 0)
        import time
        timediff = time.time() - aid_time
        if timediff < 3600:
            caller.msg("You have assisted them too recently.")
            caller.msg("You can help again in %s seconds." % (3600 - timediff))
            return
        permits = caller.ndb.healing_permits or set()
        if targ.player and targ not in permits:
            self.msg("%s has not granted you permission to heal them. Have them use +heal/permit." % targ)
            targ.msg("%s wants to heal you, but isn't permitted. You can let them with +heal/permit." % caller)
            return
        # record healing timestamp
        aid_given[targ.id] = time.time()
        caller.db.administered_aid = aid_given
        modifier = 0
        if caller.ndb.healing_gm_allow is not None:
            modifier = caller.ndb.healing_gm_allow
            caller.ndb.healing_gm_allow = None
        # give healin'
        blessed = caller.db.blessed_by_lagoma
        antimagic_aura = random.randint(0, 5)
        try:
            antimagic_aura += int(caller.location.db.antimagic_aura or 0)
        except (TypeError, ValueError):
            pass
        # if they have Lagoma's favor, we see if the Despite of Fable stops it
        if blessed:
            try:
                blessed = random.randint(0, blessed + 1)
            except (TypeError, ValueError):
                blessed = 0
            blessed -= antimagic_aura
            if blessed > 0:
                caller.msg("{cYou feel Lagoma's favor upon you.{n")
            else:
                blessed = 0
            keep = blessed + caller.db.skills.get("medicine", 0) + 2
            modifier += 5 * blessed
            heal_roll = do_dice_check(caller, stat_list=["mana", "intellect"], skill="medicine",
                                      difficulty=15-modifier, keep_override=keep)
        else:
            heal_roll = do_dice_check(caller, stat="intellect", skill="medicine", difficulty=15-modifier)
        caller.msg("You rolled a %s on your heal roll." % heal_roll)
        targ.msg("%s tends to your wounds, rolling %s on their heal roll." % (caller, heal_roll))
        script = targ.scripts.get("Recovery")
        if script:
            script = script[0]
            script.attempt_heal(heal_roll, caller)


class CmdStandYoAssUp(ArxCommand):
    """
    Heals up a player character
    Usage:
        +standyoassup <character>
        +standyoassup/noheal <character>
        +standyoassup/global <character>

    Heals a puny mortal and wakes them up. Use /noheal if you just wanna wake
    them but want them to remain injured.
    """
    key = "+standyoassup"
    locks = "cmd:perm(wizards)"
    help_category = "GMing"

    def func(self):
        """Execute command."""
        caller = self.caller
        global_search = "global" in self.switches
        targ = caller.search(self.args, global_search=global_search)
        if not targ:
            return
        if "noheal" not in self.switches:
            targ.dmg = 0
            targ.msg("You have been healed.")
            caller.msg("You heal %s because they're a sissy mortal who needs everything done for them." % targ)
        targ.wake_up()
        return
