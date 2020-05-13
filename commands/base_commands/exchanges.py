from django.db import transaction

from commands.base import ArxCommand
from commands.base_commands.overrides import args_are_currency, check_volume
from world.dominion.models import CraftingMaterials
from server.utils.arx_utils import text_box


class TradeError(Exception):
    pass


class PersonalTradeInProgress:
    HEADER_MSG = "|w[|nPersonal Trade|w]|n "
    FAIL_MSG = "Could not finish the exchange."
    def __init__(self, caller, target):
        self.caller = caller
        self.target = target
        self.names = {caller: str(caller), target: str(target)}
        caller.ndb.personal_trade_in_progress = self
        target.ndb.personal_trade_in_progress = self
        self.items = {caller: [], target: []}
        self.silver = {caller: 0, target: 0}
        self.agreements = {caller: False, target: False}

    @classmethod
    def create_trade(cls, caller, targ_name):
        target = caller.search(targ_name)
        if not target:
            return
        if target == caller or not target.player_ob:
            raise TradeError(f"You cannot trade with {target}.")
        for trader in (caller, target):
            if trader.ndb.personal_trade_in_progress:
                target.msg(f"{cls.HEADER_MSG}{caller} wants to trade, but you have one in progress.")
                raise TradeError(f"{trader} has a trade already in progress.")
        trade = cls(caller, target)
        trade.message_participants(
            f"{trade.caller} has initiated a trade with {trade.target}. (See |w/help trade|n)"
        )

    def cancel_trade(self):
        "Scrubs this instance from traders and messages them."
        self.clean_up()
        self.message_participants("|yYour trade has been cancelled.|n")

    def display_trade(self):
        "Creates a string about the state of the trade."
        def print_manifest(trader):
            txt = f"{self.names[trader]} offers"
            if self.silver[trader]:
                txt += f" |c{self.silver[trader]}|n silver and"
            txt += ":"
            if self.items[trader]:
                txt += "\n" + "\n".join([str(ob) for ob in self.items[trader]])
            else:
                txt += " (no items)"
            return txt

        def print_declaration(trader):
            bull = self.agreements[trader]  # :3 bool luv u
            color = "|351" if bull else "|y"
            adverb = "" if bull else "not yet "
            return f"{self.names[trader]} has {color}{adverb}agreed|n. "

        dbl = "\n\n"
        msg = "".join(
            (self.HEADER_MSG, print_manifest(self.caller), dbl, print_manifest(self.target),
             dbl, print_declaration(self.caller), print_declaration(self.target)))
        return text_box(msg)

    def add_item(self, trader, obj):
        "Locates item and adds it to the trade."
        item = trader.search(obj)
        if not item:
            return
        if item in self.items[trader]:
            raise TradeError(f"{item} is already being traded.")
        self.items[trader].append(item)
        self.reset_agreements(f"{self.names[trader]} offers {item}.")

    def add_silver(self, trader, amount):
        "Verifies amount and adds silver to the trade."
        if self.silver[trader]:
            raise TradeError(
                "Your silver is already specified. Cancel trade and restart if it is the wrong amount."
            )
        try:
            amount = int(amount)
            if amount < 1:
                raise ValueError
        except (ValueError, TypeError):
            raise TradeError("Amount must be a positive number that you can afford.")
        self.silver[trader] = amount
        self.reset_agreements(f"{self.names[trader]} offers |c{amount}|n silver.")

    def finish(self):
        "Runs checks before performing the exchange, then scrubs this instance from traders."
        self.check_trader_location()
        self.check_can_pay()
        self.check_items()
        for obj in self.items[self.caller]:
            obj.move_to(self.target)
        for obj in self.items[self.target]:
            obj.move_to(self.caller)
        if self.silver[self.caller]:
            self.caller.pay_money(self.silver[self.caller], self.target)
        if self.silver[self.target]:
            self.target.pay_money(self.silver[self.target], self.caller)
        self.clean_up()
        self.message_participants("|351Your exchange is complete!|n")

    def check_trader_location(self):
        "Ensures traders are in the same place and resets agreements if they are not."
        if self.caller.location != self.target.location:
            self.reset_agreements("Traders must be in the same location.")
            raise TradeError(self.FAIL_MSG)

    def check_can_pay(self):
        "Checks wallet and resets agreements if one of them can't afford the trade."
        for trader in (self.caller, self.target):
            if self.silver[trader] > trader.currency:
                self.reset_agreements(f"{self.names[trader]} does not have enough silver to complete the trade.")
                raise TradeError(self.FAIL_MSG)

    def check_items(self):
        "Checks items for permission to move them and resets agreements upon any failure."
        def check(trader, recipient):
            for obj in self.items[trader]:
                if not obj.at_before_move(recipient, caller=trader):
                    self.reset_agreements(f"{self.names[trader]} cannot trade {obj}.")
                    raise TradeError(self.FAIL_MSG)

        check(self.caller, self.target)
        check(self.target, self.caller)

    def mark_agreement(self, trader):
        "Trader's agreement becomes Truthy, then trade attempts to finish if all parties have agreed."
        self.agreements[trader] = True
        if all(self.agreements.values()):
            self.finish()
        else:
            self.message_participants(f"{self.names[trader]} has agreed to the trade.")

    def reset_agreements(self, msg=""):
        "Checks for trade agreements and nullifies them, giving feedback if any were reset."
        message = msg
        if any(self.agreements.values()):
            self.agreements = {key: False for key in self.agreements.keys()}
            sep = " " if message else ""
            message += f"{sep}|wAgreements have been reset.|n"
        if message:
            self.message_participants(message)

    def message_participants(self, msg):
        "Sends a message to traders with a small header attached."
        message = f"{self.HEADER_MSG}{msg}"
        self.caller.msg(message)
        self.target.msg(message)

    def clean_up(self):
        self.caller.ndb.personal_trade_in_progress = None
        self.target.ndb.personal_trade_in_progress = None


class CmdTrade(ArxCommand):
    """
    Set up a trade transaction with another character.

    Usage:
        trade [<character>]
        trade/item <item>
        trade/silver <amount>
        trade/agree
        trade/cancel

    After offering items and silver, both characters must agree in
    order to complete the exchange. Display the current offer by
    using this command with no args or switches.
    """
    key = "trade"
    locks = "cmd:all()"

    @transaction.atomic
    def func(self):
        try:
            if self.args and not self.switches:
                PersonalTradeInProgress.create_trade(self.caller, self.args)
                return
            trade = self.caller.ndb.personal_trade_in_progress
            if not trade:
                raise TradeError("You are not trading with anyone right now.")
            elif not self.switches and not self.args:
                self.msg(trade.display_trade())
                return
            elif self.check_switches(("agree", "accept")):
                trade.mark_agreement(self.caller)
                return
            elif self.check_switches(("cancel", "stop", "quit")):
                trade.cancel_trade()
                return
            elif self.check_switches(("item", "items")):
                trade.add_item(self.caller, self.args)
                return
            elif self.check_switches(("silver", "money")):
                trade.add_silver(self.caller, self.args)
                return
            raise TradeError("Incorrect switch. See |w/help trade|n.")
        except TradeError as err:
            self.msg(err)


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
