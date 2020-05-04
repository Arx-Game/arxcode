from commands.base import ArxCommand
from commands.base_commands.overrides import args_are_currency, check_volume
from world.dominion.models import CraftingMaterials


class TradeError(Exception):
    pass


class PersonalTradeInProgress:
    def __init__(self, caller, target):
        self.caller = caller
        self.target = target
        caller.ndb.personal_trade_in_progress = self
        target.ndb.personal_trade_in_progress = self
        self.items = {caller: [], target: []}
        self.silver = {caller: 0, target: 0}

    @classmethod
    def create_trade(cls, caller, target):
        for trader in (caller, target):
            if trader.ndb.personal_trade_in_progress:
                raise TradeError(f"{trader} has a trade already in progress.")

    def cancel_trade(self):
        self.clean_up()
        self.message_participants("The exchange has been cancelled.")

    def add_item(self, trader, obj):
        if obj in self.items[trader]:
            raise TradeError(f"{obj} is already being traded.")
        self.items[trader].append(obj)
        self.message_participants(f"{trader} adds {obj} to the trade.")

    def add_silver(self, trader, amount):
        if self.silver[trader]:
            raise TradeError("Silver has already been specified. Cancel the transaction instead")
        if amount < 1:
            raise TradeError("Amount must be a positive number that you can afford.")
        self.silver[trader] = amount
        self.message_participants(f"{trader} adds |c{amount}|n silver to the trade.")

    def mark_acceptance(self, trader):
        pass  # TODO

    def check_acceptance(self):
        pass  # TODO

    def wipe_acceptance(self):
        pass  # TODO

    def finish(self):
        self.check_can_pay()
        for obj in self.items[self.caller]:
            obj.move_to(self.target)
        for obj in self.items[self.target]:
            obj.move_to(self.caller)
        if self.silver[self.caller]:
            self.caller.pay_money(self.silver[self.caller], self.target)
        if self.silver[self.target]:
            self.target.pay_money(self.silver[self.target], self.caller)
        self.clean_up()
        self.message_participants("The exchange has been completed.")

    def check_can_pay(self):
        for trader in (self.caller, self.target):
            if self.silver[trader] > trader.currency:
                raise TradeError(f"{trader} does not have enough silver to complete the trade.")

    def message_participants(self, msg):
        self.caller.msg(msg)
        self.target.msg(msg)

    def clean_up(self):
        self.caller.ndb.personal_trade_in_progress = None
        self.target.ndb.personal_trade_in_progress = None


class CmdTrade(ArxCommand):
    """
    Sets up a trade transaction with another character

    trade <character>
    trade/item <item>
    trade/silver <amount>
    trade/agree
    trade/cancel
    """


class CmdGive(ArxCommand):
    """
    give away things

    Usage:
      give <inventory obj> = <target>
      give <inventory obj> to <target>
      give <amount> silver to <target>
      give/mats <type>,<amount> to <target>
      give/resource <type>,<amount> to <target>

    Gives an items from your inventory to another character,
    placing it in their inventory. give/resource does not require
    you to be in the same room.
    """
    key = "give"
    locks = "cmd:all()"

    # noinspection PyAttributeOutsideInit
    def func(self):
        """Implement give"""

        caller = self.caller
        to_give = None
        if not self.args:
            caller.msg("Usage: give <inventory object> = <target>")
            return
        if not self.rhs:
            arglist = self.args.split(" to ")
            if len(arglist) < 2:
                caller.msg("Usage: give <inventory object> to <target>")
                return
            self.lhs, self.rhs = arglist[0], arglist[1]
        if "resource" in self.switches:
            player = caller.player.search(self.rhs)
            if not player:
                return
            target = player.char_ob
        else:
            target = caller.search(self.rhs)
        if not target:
            return
        if target == caller:
            caller.msg("You cannot give things to yourself.")
            return
        if not target.player_ob:
            self.msg("You cannot give anything to them. Use 'put' instead.")
            return
        if "mats" in self.switches:
            lhslist = self.lhs.split(",")
            try:
                mat = caller.player_ob.Dominion.assets.materials.get(type__name__iexact=lhslist[0])
                amount = int(lhslist[1])
                if amount < 1:
                    raise ValueError
            except (IndexError, ValueError):
                caller.msg("Invalid syntax.")
                return
            except CraftingMaterials.DoesNotExist:
                caller.msg("No materials by that name.")
                return
            if mat.amount < amount:
                caller.msg("Not enough materials.")
                return
            try:
                tmat = target.player_ob.Dominion.assets.materials.get(type=mat.type)
            except CraftingMaterials.DoesNotExist:
                tmat = target.player_ob.Dominion.assets.materials.create(type=mat.type)
            mat.amount -= amount
            tmat.amount += amount
            mat.save()
            tmat.save()
            caller.msg("You give %s %s to %s." % (amount, mat.type, target))
            target.msg("%s gives %s %s to you." % (caller, amount, mat.type))
            return
        if "resource" in self.switches:
            rtypes = ("economic", "social", "military")
            lhslist = self.lhs.split(",")
            try:
                rtype = lhslist[0].lower()
                amount = int(lhslist[1])
                if amount < 1:
                    raise ValueError
            except (IndexError, ValueError):
                caller.msg("Invalid syntax.")
                return
            if rtype not in rtypes:
                caller.msg("Type must be in %s." % ", ".join(rtypes))
                return
            cres = getattr(caller.player_ob.Dominion.assets, rtype)
            if cres < amount:
                caller.msg("You do not have enough %s resources." % rtype)
                return
            tres = getattr(target.player_ob.Dominion.assets, rtype)
            cres -= amount
            tres += amount
            setattr(target.player_ob.Dominion.assets, rtype, tres)
            setattr(caller.player_ob.Dominion.assets, rtype, cres)
            target.player_ob.Dominion.assets.save()
            caller.player_ob.Dominion.assets.save()
            caller.msg("You give %s %s resources to %s." % (amount, rtype, target))
            target.player_ob.inform("%s has given %s %s resources to you." % (caller, amount, rtype),
                                    category="Resources")
            return
        if args_are_currency(self.lhs):
            arglist = self.lhs.split()
            val = round(float(arglist[0]), 2)
            if val <= 0:
                self.msg("Amount must be positive.")
                return
            currency = round(float(caller.db.currency or 0), 2)
            if val > currency:
                caller.msg("You do not have that much money to give.")
                return
            caller.pay_money(val, target)
            caller.msg("You give coins worth %s silver pieces to %s." % (val, target))
            target.msg("%s has given you coins worth %s silver pieces." % (caller, val))
            return
        # if we didn't find a match in currency that we're giving
        if not to_give:
            to_give = caller.search(self.lhs)
        if not (to_give and target):
            return
        if target == caller:
            caller.msg("You keep %s to yourself." % to_give.key)
            to_give.at_get(caller)
            return
        if not to_give.location == caller:
            caller.msg("You are not holding %s." % to_give.key)
            return
        if not check_volume(to_give, target, quiet=True):
            caller.msg("%s can't hold %s." % (target.name, to_give.name))
            return
        if not to_give.at_before_move(target, caller=caller):
            return
        # give object
        to_give.move_to(target, quiet=True)
        caller.msg("You give %s to %s." % (to_give.key, target))
        target.msg("%s gives you %s." % (caller, to_give.key))
        to_give.at_get(target)
