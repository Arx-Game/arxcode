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

# error return function, needed by wear/remove command
AT_SEARCH_RESULT = utils.variable_from_module(*settings.SEARCH_AT_RESULT.rsplit('.', 1))

# ------------------------------------------------------------
# Commands defined for wearable
# ------------------------------------------------------------


class CmdWield(ArxCommand):
    """
    Chooses the method you use to attack.
    Usage:
            wield
            wield <weapon>
            
    Makes a weapon ready for use. 'Weapon' is something of an abstraction
    in that it can be a sword, a pair of daggers, a rock you intend to
    throw at someone, vile magics, poison, whatever. The command just shows
    your intent and readiness to use it in a manner that could be detected,
    either in the very obvious case (brandishing a sword), to the very
    subtle (magical auras, discreet poisons).
    """
    key = "wield"
    locks = "cmd:all()"
    help_category = "Combat"

    def func(self):
        """Look for object in inventory that matches args to wear"""
        caller = self.caller
        args = self.args
        if not args:
            caller.msg("Wear what?")
            return
        # Because the wear command by definition looks for items
        # in inventory, call the search function using location = caller
        results = caller.search(args, location=caller, quiet=True)
        # now we send it into the error handler (this will output consistent
        # error messages if there are problems).
        obj = AT_SEARCH_RESULT(results, caller, args, False,
                               nofound_string="You don't carry %s." % args,
                               multimatch_string="You carry more than one %s:" % args)
        if not obj:
            return

        if not obj.db.is_wieldable:
            caller.msg("You can't wield that.")
            return
        if obj.db.currently_wielded:
            caller.msg("You're already wielding %s." % obj.name)
            return
        if caller.db.weapon:
            caller.msg("You are already wielding a weapon. Sheathe it first.")
            return
        cscript = caller.location.ndb.combat_manager
        if cscript and caller in cscript.ndb.combatants:
            if cscript.ndb.phase == 2:
                caller.msg("You may only change weapons during the setup phase.")
                return
        if obj.wield_by(caller):
            caller.msg("You equip %s." % obj.name)
            exclude = [caller]
            if obj.db.stealth:
                # checks for sensing a stealthed weapon being wielded. those who fail are put in exclude list
                chars = [char for char in caller.location.contents if hasattr(char, 'sensing_check') and char != caller]
                for char in chars:
                    if char.sensing_check(obj, diff=obj.db.sensing_difficulty) < 1:
                        exclude.append(char)
            msg = obj.db.ready_phrase or "wields %s" % obj.name
            caller.location.msg_contents("%s %s." % (caller.name, msg),
                                         exclude=exclude)
            obj.at_post_wield(caller)
            return


class CmdUnwield(ArxCommand):
    """
    Removes a weapon from its current state of readiness.
    Usage:
        sheathe <item>
        
    Unequips a weapon. Since 'weapon' is a bit of an abstraction, this can
    take the form of sheathing a sword, slinging a bow around your back,
    discreetly wiping away poison with a rag, etc.
    """
    key = "sheathe"
    aliases = ["unwield"]
    locks = "cmd:all()"

    def func(self):
        """Look for object in inventory that matches args to wear"""
        caller = self.caller
        args = self.args
        if not args:
            caller.msg("Unwield what?")
            return
        # Because the wear command by definition looks for items
        # in inventory, call the search function using location = caller
        results = caller.search(args, location=caller, quiet=True)

        # now we send it into the error handler (this will output consistent
        # error messages if there are problems).
        obj = AT_SEARCH_RESULT(results, caller, args, False,
                               nofound_string="You don't carry %s." % args,
                               multimatch_string="You carry more than one %s:" % args)
        if not obj:
            return
        if not obj.db.currently_wielded or obj.db.wielded_by != caller:
            caller.msg("You're not wielding %s." % obj.name)
            return
        cscript = caller.location.ndb.combat_manager
        if cscript and caller in cscript.ndb.combatants:
            if cscript.ndb.phase == 2:
                caller.msg("You may only change weapons during the setup phase.")
                return
        if obj.sheathe(caller):
            caller.msg("You put away %s." % obj.name)
            obj.at_post_remove(caller)
            return
        

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
        self.add(CmdUnwield())


# prevent errors with old saved typeclass paths
DefaultCmdSet = WeaponCmdSet
