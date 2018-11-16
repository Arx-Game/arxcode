"""
Commands for banking.
"""

from evennia.commands.cmdset import CmdSet
from evennia.utils import evtable
from commands.base import ArxCommand
from world.dominion import setup_utils
from world.dominion.models import CraftingMaterials, AccountTransaction, AssetOwner


class BankCmdSet(CmdSet):
    """CmdSet for a market."""
    key = "BankCmdSet"
    priority = 101
    duplicates = False
    no_exits = False
    no_objs = False

    def at_cmdset_creation(self):
        """
        This is the only method defined in a cmdset, called during
        its creation. It should populate the set with command instances.

        Note that it can also take other cmdsets as arguments, which will
        be used by the character default cmdset to add all of these onto
        the internal cmdset stack. They will then be able to removed or
        replaced as needed.
        """
        self.add(CmdBank())


class CmdBank(ArxCommand):
    """
    bank
    Usage:
        bank
        bank/deposit  <amount>[=<account holder name>]
        bank/withdraw <amount>[=<account holder name>]
        bank/depositmats <type>,<amt>=<account holder name>
        bank/withdrawmats <type>,<amt>=<account holder name>
        bank/withdrawres <type>,<amt>=<account holder name>
        bank/depositres <type>,<amt>=<account holder name>
        bank/payments
        bank/payments <sender>,<amt>=<receiver>
        bank/endpayment <#>
        bank/adjustpayment <#>=<new amount>

    Used to interact with your bank account. You may deposit or
    withdraw money from your own account or any organization for
    which you have 'withdraw' permissions. You may deposit or
    withdraw materials from an organization's vault. You may also
    set up or end weekly payments to or from another entity.
    """
    key = "bank"
    aliases = ["+bank"]
    locks = "cmd:all()"
    help_category = "Bank"

    def match_account(self, all_accounts, matchstr=None):
        """Get the account matching self.rhs"""
        name = matchstr or self.rhs or ""
        name = name.lower()
        matches = [ob for ob in all_accounts if str(ob.owner).lower() == name]
        if not matches:
            self.caller.msg("No matches. Choose one of the following: %s" % ", ".join(str(ob.owner) for ob in
                                                                                      all_accounts))
            return
        return matches[0]

    @staticmethod
    def get_debt_table(debts):
        x = 0
        table = evtable.EvTable("{w#{n", "{wReceiver{n", "{wAmount{n", "{wTime Remaining{n", width=60)
        for debt in debts:
            x += 1
            time = "Permanent" if debt.repetitions_left == -1 else debt.repetitions_left
            table.add_row(debt.id, debt.receiver, debt.weekly_amount, time)
        return table

    @staticmethod
    def check_money(account, amt):
        debits = 0
        for debt in account.debts.all():
            debits += debt.weekly_amount
        debits += amt
        return account.vault - debits

    def inform_owner(self, owner, verb, amt, attr_type="silver", mat_str="silver"):
        attr_name = "min_%s_for_inform" % attr_type
        if amt >= getattr(owner, attr_name):
            preposition = "to" if "deposit" in verb.lower() else "from"
            msg = ("%s has %s %s %s %s %s account." % (self.caller, verb, amt, mat_str, preposition, owner))
            owner.inform(msg, category="Bank Transaction")

    def func(self):
        """Execute command."""
        caller = self.caller
        try:
            dompc = caller.player.Dominion
        except AttributeError:
            dompc = setup_utils.setup_dom_for_char(caller)
        org_accounts = [member.organization.assets for member in dompc.memberships.filter(deguilded=False)]
        all_accounts = [dompc.assets] + org_accounts
        if ("payments" in self.switches or "endpayment" in self.switches or "adjustpayment" in self.switches
                or "payment" in self.switches):
            debts = list(dompc.assets.debts.all())
            for acc in org_accounts:
                if acc.can_be_viewed_by(caller) and acc.debts.all():
                    debts += list(acc.debts.all())
            if not self.args:
                caller.msg(str(self.get_debt_table(debts)), options={'box': True})
                return
            if "endpayment" in self.switches or "adjustpayment" in self.switches:
                try:
                    if "endpayment" in self.switches:
                        debts += list(dompc.assets.incomes.all())
                    val = int(self.lhs)
                    debt = AccountTransaction.objects.get(id=val, id__in=(ob.id for ob in debts))
                except (ValueError, AccountTransaction.DoesNotExist):
                    caller.msg("Invalid number. Select one of the following:")
                    caller.msg(str(self.get_debt_table(debts)), options={'box': True})
                    return
                if "endpayment" in self.switches:
                    debt.delete()
                    caller.msg("Payment cancelled.")
                    return
                try:
                    amt = int(self.rhs)
                    if amt <= 0:
                        raise ValueError
                except ValueError:
                    caller.msg("Please give a positive value as the new amount.")
                    return
                check = self.check_money(debt.sender, (amt - debt.weekly_amount))
                if check < 0:
                    caller.msg("Insufficient funds. You need %s more." % (-check))
                    return
                debt.weekly_amount = amt
                debt.save()
                caller.msg("Weekly payment amount is now %s." % amt)
                return
            # set up a new payment
            try:
                sender = self.match_account(all_accounts, self.lhslist[0])
                if not sender:
                    return
                if not sender.access(caller, 'withdraw'):
                    caller.msg("You lack permission to set up a payment.")
                    return
                amt = int(self.lhslist[1])
                if amt <= 0:
                    raise ValueError
                try:
                    receiver = AssetOwner.objects.get(player__player__username__iexact=self.rhs)
                except AssetOwner.DoesNotExist:
                    receiver = AssetOwner.objects.get(organization_owner__name__iexact=self.rhs)
                if sender == receiver:
                    caller.msg("Sender and receiver must be different.")
                    return
            except (ValueError, IndexError):
                caller.msg("Must give a positive number as an amount.")
                return
            except (AssetOwner.DoesNotExist, AssetOwner.MultipleObjectsReturned):
                caller.msg("Could find neither a player nor organization by that name.")
                return
            check = self.check_money(sender, amt)
            if check < 0:
                caller.msg("Insufficient funds: %s more required to set up payment." % (-check))
                return
            sender.debts.create(receiver=receiver, weekly_amount=amt, repetitions_left=-1)
            caller.msg("New weekly payment set up: %s pays %s to %s every week." % (sender, amt, receiver))
            return
        if not self.args:
            msg = "{wAccounts{n".center(60)
            msg += "\n"
            actable = evtable.EvTable("{wOwner{n", "{wBalance{n", "{wNet Income{n", "{wMaterials{n",
                                      "{wEcon{n", "{wSoc{n", "{wMil{n", width=78, border="cells")

            for account in all_accounts:
                if not account.can_be_viewed_by(self.caller):
                    continue
                mats = ", ".join(str(mat) for mat in account.materials.filter(amount__gte=1))
                actable.add_row(str(account.owner), str(account.vault), str(account.net_income),
                                mats, account.economic, account.social, account.military)
                actable.reformat_column(0, width=14)
                actable.reformat_column(1, width=11)
                actable.reformat_column(2, width=10)
                actable.reformat_column(3, width=21)
                actable.reformat_column(4, width=8)
                actable.reformat_column(5, width=7)
                actable.reformat_column(6, width=7)
                incomes = account.incomes.all()
                debts = account.debts.all()
                if incomes:
                    msg += ("{w%s Incomes{n" % str(account)).center(60)
                    msg += "\n"
                    table = evtable.EvTable("{wSender{n", "{wAmount{n", "{wTime Remaining{n", width=60)
                    for inc in incomes:
                        time = "Permanent" if inc.repetitions_left == -1 else inc.repetitions_left
                        table.add_row(inc.sender, inc.weekly_amount, time)
                    msg += str(table)
                    msg += "\n"
                if debts:
                    msg += ("{w%s Payments{n" % str(account)).center(60)
                    msg += "\n"
                    msg += str(self.get_debt_table(debts))
                    msg += "\n"
            msg += str(actable)
            caller.msg(msg, options={'box': True})
            return
        if ("depositmats" in self.switches or "withdrawmats" in self.switches
                or "depositres" in self.switches or "withdrawres" in self.switches):
            account = self.match_account(all_accounts)
            if not account:
                return
            if account == dompc.assets:
                caller.msg("Characters always have access to their own materials as an "
                           "abstraction, so withdraws and deposits " +
                           "are only between organizations and characters.")
                return
            usingmats = "depositmats" in self.switches or "withdrawmats" in self.switches
            if usingmats:
                attr_type = "materials"
            else:
                attr_type = "resources"
            if "depositmats" in self.switches or "depositres" in self.switches:
                sender = dompc.assets
                receiver = account
                verb = "deposit"
            else:
                if not account.access(caller, 'withdraw'):
                    caller.msg("You do not have permission to withdraw from that account.")
                    return
                receiver = dompc.assets
                sender = account
                verb = "withdraw"
            try:
                matname, val = self.lhslist[0], int(self.lhslist[1])
                source = sender
                targ = receiver
                if val <= 0:
                    caller.msg("You must specify a positive number.")
                    return
                if usingmats:
                    source = sender.materials.get(type__name__iexact=matname)
                    if source.amount < val:
                        caller.msg("You tried to %s %s %s, but only %s available." % (
                            verb, val, source.type.name, source.amount))
                        return
                    try:
                        targ = receiver.materials.get(type__name__iexact=matname)
                    except CraftingMaterials.DoesNotExist:
                        targ = receiver.materials.create(type=source.type, amount=0)
                    source.amount -= val
                    targ.amount += val
                    samt = source.amount
                    tamt = targ.amount
                else:
                    restypes = ("economic", "social", "military")
                    matname = matname.lower()
                    if matname not in restypes:
                        caller.msg("Resource must be one of: %s" % ", ".join(restypes))
                        return
                    sresamt = getattr(sender, matname)
                    if sresamt < val:
                        matname += " resources"
                        caller.msg("You tried to %s %s %s, but only %s available." % (
                            verb, val, matname, sresamt))
                        return
                    tresamt = getattr(receiver, matname)
                    samt = sresamt - val
                    tamt = tresamt + val
                    setattr(sender, matname, samt)
                    setattr(receiver, matname, tamt)
                    matname += " resources"
                source.save()
                targ.save()
                caller.msg("You have transferred %s %s from %s to %s." % (
                    val, matname, sender, receiver))
                if account.can_be_viewed_by(caller):
                    caller.msg("Sender now has %s, receiver has %s." % (samt, tamt))
                else:
                    caller.msg("Transaction successful.")
                self.inform_owner(account, verb, val, attr_type, matname)
            except CraftingMaterials.DoesNotExist:
                caller.msg("No match for that material. Valid materials: %s" % ", ".join(
                    str(mat) for mat in sender.materials.all()))
                return
            except (ValueError, IndexError):
                caller.msg("Invalid usage.")
                return
            return
        try:
            amount = int(self.lhs)
            if amount <= 0:
                caller.msg("Amount must be positive.")
                return
        except ValueError:
            caller.msg("Amount must be a number.")
            return
        if not self.rhs:
            account = dompc.assets
        else:
            account = self.match_account(all_accounts)
            if not account:
                return
        if "deposit" in self.switches:
            cash = caller.db.currency or 0.0
            if not cash:
                caller.msg("You have no money to deposit.")
                return
            if amount > cash:
                caller.msg("You tried to deposit %s, but only have %s on hand." % (amount, cash))
                return
            account.vault += amount
            caller.db.currency = cash - amount
            account.save()
            if account.can_be_viewed_by(caller):
                caller.msg("You have deposited %s. The new balance is %s." % (amount, account.vault))
            else:
                caller.msg("You have deposited %s." % amount)
            self.inform_owner(account, "deposited", amount)
            return
        if "withdraw" in self.switches:
            if not account.access(caller, "withdraw"):
                caller.msg("You do not have permission to withdraw from that account.")
                return
            cash = caller.db.currency or 0.0
            check = self.check_money(account, amount)
            if check < 0:
                caller.msg("You cannot withdraw more than the balance minus an account's debt obligations.")
                caller.msg("You want to withdraw %s but only %s is available after debt obligations." % (amount,
                                                                                                         check+amount))
                if account.debts.all():
                    caller.msg("Cancelling payments would increase the amount available.")
                    return
                return
            account.vault -= amount
            caller.db.currency = cash + amount
            account.save()
            caller.msg("You have withdrawn %s. New balance is %s." % (amount, account.vault))
            self.inform_owner(account, "withdrawn", amount)
            return
        else:
            caller.msg("Unrecognized switch.")
            return
