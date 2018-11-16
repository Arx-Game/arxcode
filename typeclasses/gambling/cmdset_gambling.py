"""
This defines the cmdset for the red_button. Here we have defined
the commands and the cmdset in the same module, but if you
have many different commands to merge it is often better
to define the cmdset separately, picking and choosing from
among the available commands as to what should be included in the
cmdset - this way you can often re-use the commands too.
"""

import random
from evennia import CmdSet
from commands.base import ArxCommand


class CmdRoll(ArxCommand):
    """
    rolls dice

    Usage:
        roll <number of dice>=<size of die>

    Rolls dice for random checks. You can specify dice of any number of sides,
    and between 1 and 50 dice.
    """
    key = "roll"
    locks = "cmd:all()"
    help_category = "Social"

    def func(self):
        """Implements command"""
        caller = self.caller
        rolls = []
        try:
            num_dice = int(self.lhs)
            sides = int(self.rhs)
            if sides <= 0:
                raise ValueError
        except (ValueError, TypeError):
            self.msg("Please enter positive numbers for number of dice and sides.")
            return
        if num_dice < 1 or num_dice > 50:
            self.msg("Please specify a number of dice between 1 and 50.")
            return
        for x in range(num_dice):
            roll = random.randint(1, sides)
            rolls.append(roll)
        rolls.sort()
        rolls = [str(ob) for ob in rolls]
        caller.msg("You have rolled: %s" % ", ".join(rolls))
        caller.location.msg_contents("%s has rolled %s %s-sided dice: %s" % (caller.name, num_dice, sides,
                                                                             ", ".join(rolls)),
                                     exclude=caller, options={"roll": True})
        

class DiceCmdSet(CmdSet):
    """
    The default cmdset always sits
    on the button object and whereas other
    command sets may be added/merge onto it
    and hide it, removing them will always
    bring it back. It's added to the object
    using obj.cmdset.add_default().
    """
    key = "Dice"
    # if we have multiple wearable objects, just keep
    # one cmdset, ditch others
    key_mergetype = {"Dice": "Replace"}
    priority = 0
    duplicates = False

    def at_cmdset_creation(self):
        """Init the cmdset"""
        self.add(CmdRoll())
