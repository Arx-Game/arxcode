"""
Utilities file for combat - shared functions, etc.
"""
from random import randint, choice


def npc_target_choice(targ, targets, prev_targ, switch_chance):
    """
    Selects a target for an npc.

        Args:
            targ: Our primary target, which we see if it will change.
            targets: Our list of valid targets, if we switch.
            prev_targ: Our previously attacked target.
            switch_chance: Our chance of switching targets (0 to 100)

        Returns:
            targ: Our selected target.
    """
    # while we never consecutively attack the same target twice, we still will
    # try to use a lot of our attacks on our 'main' target the player set for the npc
    if len(targets) > 1:
        removed_previous = False
        if prev_targ and not prev_targ.db.num_living and prev_targ in targets:
            removed_previous = True
            targets.remove(prev_targ)
        if randint(1, 100) <= switch_chance:
            targ = choice(targets)
        if removed_previous:
            targets.append(prev_targ)
    defenders = targ.combat.get_defenders()
    # if our target selection has defenders, we hit one of them instead
    if defenders:
        targ = choice(defenders)
    return targ
