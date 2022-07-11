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
import time

# one hour between recovery tests
MIN_TIME = 3600


class SleepCmdSet(CmdSet):
    """CmdSet for players who are currently sleeping. Lower priority than death cmdset, so it's overriden."""

    key = "SleepCmdSet"
    key_mergetype = {"DefaultCharacter": "Replace"}
    priority = 120
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
        self.add(CmdWake())
        self.add(CmdMoveOverride())
        self.add(CmdNoFighting())


class SleepCommand(ArxCommand):
    """
    You are sleeping. Many character commands will no longer function.
    """

    key = "sleep"
    locks = "cmd:all()"

    def get_help(self, caller, cmdset):
        """Returns same help string for all commands"""
        return """
    You are sleeping. Many character commands will no longer function.
    """

    def func(self):
        """Let the player know they can't do anything."""
        self.msg(
            "You can't do that while sleeping. To wake up, use the {wwake{n command."
        )
        return


class CmdMoveOverride(SleepCommand):
    """Prevents movement"""

    key = "north"
    aliases = ["n", "s", "w", "e"]


class CmdWake(ArxCommand):
    """
    Attempt to wake up from sleep. Automatic if uninjured.
    """

    key = "wake"
    locks = "cmd:all()"

    def func(self):
        """Try to wake."""
        caller = self.caller
        if not hasattr(caller, "wake_up"):
            caller.cmdset.delete(SleepCmdSet)
            caller.msg("Deleting SleepCmdSet from non-character object.")
            return
        caller.wake_up(light_waking=True)


class CmdGet(SleepCommand):
    """
    You are sleeping. Many character commands will no longer function.
    """

    key = "get"


class CmdDrop(SleepCommand):
    """
    You are sleeping. Many character commands will no longer function.
    """

    key = "drop"


class CmdGive(SleepCommand):
    """
    You are sleeping. Many character commands will no longer function.
    """

    key = "give"


class CmdSay(SleepCommand):
    """
    You are sleeping. Many character commands will no longer function.
    """

    key = "say"


class CmdWhisper(SleepCommand):
    """
    You are sleeping. Many character commands will no longer function.
    """

    key = "whisper"


class CmdFollow(SleepCommand):
    """
    You are sleeping. Many character commands will no longer function.
    """

    key = "follow"


class CmdDitch(SleepCommand):
    """
    You are sleeping. Many character commands will no longer function.
    """

    key = "ditch"


class CmdShout(SleepCommand):
    """
    You are sleeping. Many character commands will no longer function.
    """

    key = "shout"


class CmdNoFighting(SleepCommand):
    """Prevents fighting, etc"""

    key = "fight"
    aliases = ["train"]


class CmdCoinFlip(SleepCommand):
    """You are unconscious. Many character commands will no longer function."""

    key = "coinflip"
