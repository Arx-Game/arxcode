COMBAT_STYLES = ("melee", "close", "brawling", "archery", "magic")
COMBAT_STATUS = ("active", "subdued", "incapacitated")
COMBAT_STANCES = ("defensive", "guarded", "balanced", "aggressive", "reckless")
STANCE_ATK_MOD = {
    "defensive": 10,
    "guarded": 5,
    "balanced": 0,
    "aggressive": -10,
    "reckless": -20,
    None: 0,
}
STANCE_DEF_MOD = {
    "defensive": -10,
    "guarded": -5,
    "balanced": 0,
    "aggressive": 10,
    "reckless": 20,
    None: 0,
}

COMBAT_INTRO = """
Combat makes commands available to you, which you can see by
looking at '{whelp combat{n'. While in combat, you can {rnot{n use
room exits: attempting to use an exit will return 'What?' as
an unrecognized command. The only way to move from the room is with the
successful use of a {wflee{n command. Combat is turn-based in
order to allow ample time for RP - please use poses and emits
to describe the results of your actions to the room, and show
respect to other players by being patient. Combat
continues until all active parties agree to end by a vote or
have otherwise disengaged from the fight. Please note that
deliberately terminating your connection to avoid fights is
against the rules.
"""

PHASE1_INTRO = """
{wEntering Setup Phase:{n

The setup phase allows you to finish adding characters to combat or to
perform preliminary RP that may stop the combat before things proceed
further. During this phase, other characters may enter combat via the
{w+fight{n command and be able to act during the same turn. No characters
may escape via exits at this stage - they may only attempt to {wflee{n once
the fighting begins, during their turn. Combat may be exited without any
fighting if all parties vote to {w+end_combat{n. Otherwise, combat begins
when all characters involved have selected to {wcontinue{n.
"""

PHASE2_INTRO = """
{wEntering Resolution Phase:{n

The resolution phase allows characters to perform combat actions. Initiative
is rolled for every character along with tiebreakers to determine the order
characters act. During another character's turn, you may still pose or say
as normal, but you cannot perform any combat actions. After a character has
performed an action, the result is displayed to all combatants, and control
passes to the next character. Please give some time for people to respond
appropriately to actions with poses as needed.
"""

MAX_AFK = 120
ROUND_DELAY = 300


class CombatError(Exception):
    pass
