from commands.base import ArxCommand


class CmdApplyConsumable(ArxCommand):
    """
    Uses/applies a consumable object

        Usage:
            use <object> on <target>

    Use a consumable object on a target. Different
    consumable objects have requirements on what they
    can be used on. For example, 'incense' may only be
    usable on a room, or 'perfume' on a character.
    """
    key = "use"
    locks = "cmd:all()"
    help_category = "General"

    def func(self):
        try:
            arglist = self.args.split(" on ")
            potion = self.caller.search(arglist[0], location=self.caller)
            if not potion:
                return
            target = self.caller.search(arglist[1])
            if not target:
                return
        except IndexError:
            self.msg("Requires an object and a target.")
            return
        try:
            if not potion.check_target(target, self.caller):
                self.msg("%s is not a valid target for %s." % (target, potion))
                return
            if not potion.consume():
                self.msg("%s doesn't have enough left to use. It needs to be replenished." % potion)
                return
            # the call method will handle most messaging
            potion.use_on_target(target, self.caller)
            self.msg("Used %s on %s." % (potion, target))
        except AttributeError:
            self.msg("%s is not a usable object." % potion)
            return
