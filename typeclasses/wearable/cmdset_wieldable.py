"""
This defines the cmdset for the red_button. Here we have defined
the commands and the cmdset in the same module, but if you
have many different commands to merge it is often better
to define the cmdset separately, picking and choosing from
among the available commands as to what should be included in the
cmdset - this way you can often re-use the commands too.
"""

from django.conf import settings
from evennia import CmdSet, utils
from server.utils.arx_utils import ArxCommand
from typeclasses.exceptions import EquipError

# error return function, needed by wear/remove command
AT_SEARCH_RESULT = utils.variable_from_module(*settings.SEARCH_AT_RESULT.rsplit('.', 1))

# ------------------------------------------------------------
# Commands defined for wearable
# ------------------------------------------------------------


class CmdWield(ArxCommand):
    """
    Manages the weapon you use to attack.
    Usage:
        wield <weapon name>
        sheathe <weapon name>
        remove <weapon name>

    Wield makes a weapon ready for combat, showing your intent and readiness
    to use it in a manner that could be detected. Sheathe lets you wear the
    weapon. Remove places the weapon in your inventory, neither worn nor
    wielded.
    """
    key = "wield"
    locks = "cmd:all()"
    aliases = ["sheathe"]
    help_category = "Combat"

    def func(self):
        from typeclasses.scripts.combat.combat_settings import CombatError
        try:
            if not self.args:
                raise EquipError("What are you trying to %s?" % self.cmdstring.lower())
            self.wield_or_sheathe_item()
        except (CombatError, EquipError) as err:
            self.msg(err)

    def wield_or_sheathe_item(self):
        item_list = [self.caller.search(self.args, location=self.caller)]
        if not any(item_list):
            return
        self.caller.equip_or_remove(self.cmdstring.lower(), item_list)


class WeaponCmdSet(CmdSet):
    """
    The default cmdset always sits
    on the wieldable object and whereas other
    command sets may be added/merge onto it
    and hide it, removing them will always
    bring it back. It's added to the object
    using obj.cmdset.add_default().
    """
    key = "WieldableDefault"
    # if we have multiple wearable objects, just keep
    # one cmdset, ditch others
    key_mergetype = {"WieldableDefault": "Replace"}
    priority = 0
    duplicates = False

    def at_cmdset_creation(self):
        """Init the cmdset"""
        self.add(CmdWield())


# prevent errors with old saved typeclass paths
DefaultCmdSet = WeaponCmdSet
