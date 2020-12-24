"""

Placeholder class. Currently identical to regular
objects.
"""
from commands.base import ArxCommand
from evennia import CmdSet
from typeclasses.objects import Object as DefaultObject


class Bauble(DefaultObject):
    """
    Essentially a placeolder in case we wanna do anything with it
    later.
    """

    pass


class PortBauble(DefaultObject):
    """
    This will be baubles that have cmdsets added to them for magical items
    """

    def at_after_move(self, source_location, **kwargs):
        location = self.location

        if location and location.is_character:
            self.cmdset.add_default(PortCmdSet, permanent=True)

        else:
            self.cmdset.delete_default()


class PortCmdSet(CmdSet):
    key = "PortCmd"
    priority = 0
    duplicates = True

    def at_cmdset_creation(self):
        self.add(CmdTouchCrystal())
        self.add(CmdAttuneCrystal())


class CmdTouchCrystal(ArxCommand):
    """
    Teleports the holder to the Prismatic Order's Crystal Expanse by touching their teleportation crystal.

    Usage:
        touch crystal
    """

    key = "touch crystal"
    locks = "cmd:all()"

    def func(self):
        caller = self.caller
        obj = self.obj
        port_target = obj.db.port_target
        if not port_target:
            caller.msg("The crystal grows dark when touched. It is not attuned.")
            return
        caller.msg_location_or_contents(
            f"{caller} touches a crystal and fades from view."
        )
        caller.move_to(port_target)
        caller.msg_location_or_contents(
            f"{caller} suddenly appears in a burst of light."
        )


class CmdAttuneCrystal(ArxCommand):
    """
    This attunes a teleportation crystal to your current room.
    Usage: 'attune crystal'
    """

    key = "attune crystal"
    locks = "cmd:all()"

    def func(self):
        if "tp_okay" not in self.caller.location.tags.all():
            self.msg("You cannot attune to this location.")
            return
        self.obj.db.port_target = self.caller.location
        self.msg(f"{self.obj} glows as it is attuned to this location.")


class GlitterMawDustPouch(DefaultObject):
    """
    This is the GlitterMaw dust pouch that has his glitter and holds the cmdsets
    """

    def at_after_move(self, source_location, **kwargs):
        location = self.location

        if location and location.is_character:
            self.cmdset.add_default(SprinkleCmdSet, permanent=True)

        else:
            self.cmdset.delete_default()


class SprinkleCmdSet(CmdSet):
    key = "SprinkleCmd"
    priority = 0
    duplicates = True

    def at_cmdset_creation(self):
        self.add(CmdSprinkleGlitter())


class CmdSprinkleGlitter(ArxCommand):
    """
    Congratulations, you are a friend of Glittermaw and carry around his glitter! Sprinkling his glitter may improve the
     quality of an object.
    Usage: "sprinkle glitter on <object name>"
    """

    key = "sprinkle glitter"
    locks = "cmd:all()"
