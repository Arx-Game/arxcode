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
from server.utils.arx_utils import ArxCommand

# ------------------------------------------------------------
# Commands defined for wearable
# ------------------------------------------------------------


class CmdWear(ArxCommand):
    """
    Put on an item of clothing or armor.

    Usage:
        wear <item>

    Wears the given item on your character. The object must be in
    your inventory to wear it.
    """
    key = "wear"
    locks = "cmd:all()"

    def func(self):
        """Look for object in inventory that matches args to wear"""
        caller = self.caller
        args = self.args
        if not args:
            caller.msg("Wear what?")
            return
        if args == "all":
            obj_list = [ob for ob in caller.contents if hasattr(ob, 'wear')]
        else:
            obj = caller.search(args, location=caller)
            if not obj:
                return
            obj_list = [obj]
        success = []
        for obj in obj_list:
            if not hasattr(obj, 'wear'):
                caller.msg("You can't wear that.")
                continue
            if obj.db.currently_worn:
                caller.msg("You're already wearing %s." % obj.name)
                continue
            slot_limit = obj.slot_limit
            slot = obj.slot
            if slot_limit and slot:
                worn = [ob for ob in caller.contents if ob.db.currently_worn and ob.slot == slot]
                if len(worn) >= slot_limit:
                    caller.msg("You are wearing too many things on your %s for it to fit." % slot)
                    continue
            if obj.wear(caller):
                success.append(obj)
        if not success:
            self.msg("You wore nothing.")
            return
        self.msg("You put on %s." % ", ".join(obj.name for obj in success))


class CmdRemove(ArxCommand):
    """
    Remove an item of clothing or armor.
    Usage:
        remove <item>

    Takes off the given item from your character. The object must
    be in your inventory and currently worn to remove it.
    """
    key = "remove"
    locks = "cmd:all()"

    def func(self):
        """Look for object in inventory that matches args to wear"""
        caller = self.caller
        args = self.args
        if not args:
            caller.msg("Remove what?")
            return
        obj = caller.search(args, location=caller)
        if not obj:
            return
        if not obj.db.currently_worn and not obj.db.sheathed_by:
            caller.msg("You're not wearing %s." % obj.name)
            return
        if obj.remove(caller):
            caller.msg("You take off %s." % obj.name)
            return
        pass


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
        self.add(CmdRemove())
