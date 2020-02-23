"""
This defines the cmdset for the red_button. Here we have defined
the commands and the cmdset in the same module, but if you
have many different commands to merge it is often better
to define the cmdset separately, picking and choosing from
among the available commands as to what should be included in the
cmdset - this way you can often re-use the commands too.
"""

from django.conf import settings
from evennia.commands.cmdset import CmdSet
from evennia import utils
from commands.base import ArxCommand
from typeclasses.exceptions import EquipError

# ------------------------------------------------------------
# Commands defined for wearable
# ------------------------------------------------------------


class CmdWear(ArxCommand):
    """
    Put on or take off an article of clothing or armor.

    Usage:
        wear <item name or "all">
        wear/unseen <item name>
        wear/outfit <outfit name>
        remove <item or "all">
        remove/outfit <outfit name>
        undress

    Wears the item on your character. Typing "all" attempts to wear all gear
    in your inventory. If you have created an outfit (see 'help outfit') the
    /outfit switch will first undress you and then attempt to put it on.
    Using wear/unseen will wear an item under other clothes, where it will
    not be visible. You can have one seen and one unseen object per worn
    location.

    'Remove' will take off specified worn items, with 'undress' being an
    alias for 'remove all'.
    """
    key = "wear"
    locks = "cmd:all()"
    aliases = ["remove", "undress", "removeall"]
    undress_cmds = ("undress", "removeall")

    def func(self):
        cmdstr = self.cmdstring.lower()
        undress = cmdstr in self.undress_cmds
        remove_all = all((cmdstr == "remove", self.args, self.args == "all"))
        from typeclasses.scripts.combat.combat_settings import CombatError
        from world.fashion.exceptions import FashionError
        try:
            if undress or remove_all:
                self.caller.undress()
                return
            elif not self.args:
                raise EquipError("What are you trying to %s?" % cmdstr)
            if "outfit" in self.switches or "outfits" in self.switches:
                self.equip_or_remove_outfit()
            else:
                self.wear_or_remove_item()
        except (CombatError, EquipError, FashionError) as err:
            self.msg(err)

    def equip_or_remove_outfit(self):
        from world.fashion.fashion_commands import get_caller_outfit_from_args
        outfit = get_caller_outfit_from_args(self.caller, self.args)
        if not outfit.is_carried:
            raise EquipError("Outfit components must be on your person and not in any containers.")
        getattr(outfit, self.cmdstring.lower())()

    def wear_or_remove_item(self):
        item_list = []
        if not "all" == self.args.lower():
            item_list = [self.caller.search(self.args, location=self.caller)]
            if not any(item_list):
                return
        self.caller.equip_or_remove(self.cmdstring.lower(), item_list)


class DefaultCmdSet(CmdSet):
    """
    Legacy commandset that doesn't do anything, but required so that
    old wearables don't throw errors due to a nonexistent pathname
    """
    key = "OldWearableDefault"


class WearCmdSet(CmdSet):
    """
    The default cmdset always sits
    on the button object and whereas other
    command sets may be added/merge onto it
    and hide it, removing them will always
    bring it back. It's added to the object
    using obj.cmdset.add_default().
    """
    key = "WearableDefault"
    # if we have multiple wearable objects, just keep
    # one cmdset, ditch others
    key_mergetype = {"WearableDefault": "Replace"}
    priority = 0
    duplicates = False

    def at_cmdset_creation(self):
        """Init the cmdset"""
        self.add(CmdWear())
