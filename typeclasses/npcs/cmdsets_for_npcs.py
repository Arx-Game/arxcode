"""
This defines the cmdset for the red_button. Here we have defined
the commands and the cmdset in the same module, but if you
have many different commands to merge it is often better
to define the cmdset separately, picking and choosing from
among the available commands as to what should be included in the
cmdset - this way you can often re-use the commands too.
"""
from evennia import CmdSet
from server.utils.arx_utils import ArxCommand


# ------------------------------------------------------------
# Commands defined for wearable
# ------------------------------------------------------------


class CmdHugPoro(ArxCommand):
    """
    Because you should.

    Usage:
        hug poro

    You know you want to.
    """
    key = "hug poro"
    locks = "cmd:all()"
    help_category = "Poro-based commands"

    def func(self):
        """Implements command"""
        caller = self.caller
        caller.location.msg_contents("%s hugs the poro, and it squeaks adorably." % caller)
        return

        
class PoroCmdSet(CmdSet):
    """
    The default cmdset always sits
    on the button object and whereas other
    command sets may be added/merge onto it
    and hide it, removing them will always
    bring it back. It's added to the object
    using obj.cmdset.add_default().
    """
    key = "Poro"
    # if we have multiple wearable objects, just keep
    # one cmdset, ditch others
    key_mergetype = {"Poro": "Replace"}
    priority = 0
    duplicates = False

    def at_cmdset_creation(self):
        """Init the cmdset"""
        self.add(CmdHugPoro())
