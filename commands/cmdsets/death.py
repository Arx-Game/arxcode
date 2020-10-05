"""
This cmdset is to try to define the state of being dead.
It will replace the mobile command set, and then specific
other commands.

This is for a character who is dead. Not undead, such as
a sexy vampire or a shambling zombie. Not braindead, such
as someone who approaches RP as a competition. No, this is
for dead-dead. Stone dead. Super dead. The deadest.

Not that they will necessarily STAY that way. But while
this is on them, they are dead.

"""

from evennia import CmdSet
from commands.base import ArxCommand


class DeathCmdSet(CmdSet):
    """CmdSet for players who are currently dead. Should be highest priority cmdset."""

    key = "DeathCmdSet"
    key_mergetype = {"DefaultCharacter": "Replace"}
    priority = 200
    duplicates = False
    no_exits = True
    no_objs = True

    def at_cmdset_creation(self):
        """
        This is the only method defined in a cmdset, called during
        its creation. It should populate the set with command instances.

        Note that it can also take other cmdsets as arguments, which will
        be used by the character default cmdset to add all of these onto
        the internal cmdset stack. They will then be able to removed or
        replaced as needed.
        """
        from commands.cmdsets.standard import OOCCmdSet

        self.add(OOCCmdSet)
        from commands.cmdsets.standard import StateIndependentCmdSet

        self.add(StateIndependentCmdSet)
        from commands.cmdsets.standard import StaffCmdSet

        self.add(StaffCmdSet)
        self.add(CmdGet())
        self.add(CmdDrop())
        self.add(CmdGive())
        self.add(CmdSay())
        self.add(CmdWhisper())
        self.add(CmdFollow())
        self.add(CmdDitch())
        self.add(CmdShout())
        self.add(CmdMoveOverride())
        self.add(CmdFight())
        self.add(CmdDonate())
        self.add(CmdOrgs)


class DeathCommand(ArxCommand):
    """
    You are dead. Many character commands will no longer function.
    """

    key = "dead"
    locks = "cmd:all()"

    def get_help(self, caller, cmdset):
        return """
    You are dead. Many character commands will no longer function.
    """

    def func(self):
        """Let the player know they can't do anything."""
        self.msg("You are dead. You cannot do that.")
        return


class CmdMoveOverride(DeathCommand):
    key = "movement"
    aliases = ["n", "s", "w", "e"]


class CmdGet(DeathCommand):
    """
    You are dead. Many character commands will no longer function.
    """

    key = "get"


class CmdDrop(DeathCommand):
    """
    You are dead. Many character commands will no longer function.
    """

    key = "drop"


class CmdGive(DeathCommand):
    """
    You are dead. Many character commands will no longer function.
    """

    key = "give"


class CmdSay(DeathCommand):
    """
    You are dead. Many character commands will no longer function.
    """

    key = "say"


class CmdWhisper(DeathCommand):
    """
    You are dead. Many character commands will no longer function.
    """

    key = "whisper"


class CmdFollow(DeathCommand):
    """
    You are dead. Many character commands will no longer function.
    """

    key = "follow"


class CmdDitch(DeathCommand):
    """
    You are dead. Many character commands will no longer function.
    """

    key = "ditch"


class CmdShout(DeathCommand):
    """No shouting"""

    key = "shout"


class CmdFight(DeathCommand):
    """No fighting"""

    key = "fight"
    aliases = ["train", "heal"]


class CmdDonate(DeathCommand):
    """No donating"""

    key = "donate"
    aliases = "praise"


class CmdOrgs(DeathCommand):
    """No org stuff"""

    key = "@org"
    aliases = ["@domain", "@army"]
