"""
This commandset attempts to define the combat state.
Combat in Arx isn't designed to mimic the real-time
nature of MMOs, or even a lot of MUDs. Our model is
closer to tabletop RPGs - a turn based system that
can only proceed when everyone is ready. The reason
for this is that having 'forced' events based on a
time limit, while perfectly appropriate for a video
game, is unacceptable when attempting to have a game
that is largely an exercise in collaborative story-
telling. It's simply too disruptive, and often creates
situations that are damaging to immersion and the
creative process.
"""
from random import randint

from evennia import CmdSet
from evennia.utils.logger import log_info
from commands.base import ArxCommand
from server.utils import prettytable
from evennia.utils.create import create_object
from world.dominion.models import (PlayerOrNpc)
from world.crafting.models import CraftingMaterialType, OwnedMaterial
from world.dominion import setup_utils
from world.stats_and_skills import do_dice_check


RESOURCE_VAL = 250
BOOK_PRICE = 1
other_items = {"book": [BOOK_PRICE, "parchment",
                        "typeclasses.readable.readable.Readable",
                        "A book that you can write in and others can read."],
               }


class OtherMaterial(object):
    """Class for handling transactions of buying generic items in shop"""
    def __init__(self, otype):
        self.name = "book"
        self.value = other_items[otype][0]
        self.category = other_items[otype][1]
        self.path = other_items[otype][2]
        self.desc = other_items[otype][3]

    def __str__(self):
        return self.name

    def create(self, caller):
        """Create the object after buying it"""
        stacking = [ob for ob in caller.contents if ob.typeclass_path == self.path and ob.db.can_stack]
        if stacking:
            obj = stacking[0]
            obj.set_num(obj.db.num_instances + 1)
        else:
            obj = create_object(typeclass=self.path, key=self.name,
                                location=caller, home=caller)
        return obj


class MarketCmdSet(CmdSet):
    """CmdSet for a market."""
    key = "MarketCmdSet"
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
        from world.petitions.petitions_commands import CmdBroker
        self.add(CmdMarket())
        self.add(CmdHaggle())
        self.add(CmdBroker())


# noinspection PyUnresolvedReferences
class CmdMarket(ArxCommand):
    """
    market
    Usage:
        market
        market/buy <material>=<amount>
        market/sell <material>=<amount>
        market/info <material>
        market/import <material>=<amount>
    Purchase with silver:
        market/economic <amount>
        market/social <amount>
        market/military <amount>

    Used to buy and sell materials at the market. Materials can be
    sold to the market for 5% of the cost. Economic resources are worth
    250 silver for buying materials. Resources cost 500 silver each.
    """
    key = "market"
    aliases = ["buy", "sell"]
    locks = "cmd:all()"
    help_category = "Market"

    def func(self):
        """Execute command."""
        caller = self.caller
        usemats = True
        material = None
        if self.cmdstring == "buy" and not ('economic' in self.switches or
                                            'social' in self.switches or
                                            'military' in self.switches):
            # allow for buy/economic, etc. buy switch precludes that, so we
            # only add it if we don't have the above switches
            self.switches.append("buy")
        if self.cmdstring == "sell":
            # having other switches is misleading. They could think they can sell
            # other things.
            if self.switches:
                caller.msg("Use market/sell or just 'sell' as the command.")
                return
            self.switches.append("sell")
        materials = CraftingMaterialType.objects.filter(value__gte=0).order_by("value")
        if not caller.check_permstring("builders"):
            materials = materials.exclude(acquisition_modifiers__icontains="nosell")
        if not self.args:
            mtable = prettytable.PrettyTable(["{wMaterial",
                                              "{wCategory",
                                              "{wCost"])
            for mat in materials:
                mtable.add_row([mat.name, mat.category, str(mat.value)])
            # add other items by hand
            for mat in other_items:
                mtable.add_row([mat, other_items[mat][1], other_items[mat][0]])
            caller.msg("\n{w" + "="*60 + "{n\n%s" % mtable)
            pmats = OwnedMaterial.objects.filter(owner__player__player=caller.player)
            if pmats:
                caller.msg("\n{wYour materials:{n %s" % ", ".join(str(ob) for ob in pmats))
            return
        if not ("economic" in self.switches or "buyeconomic" in self.switches or "social" in self.switches or
                "military" in self.switches):
            try:
                material = materials.get(name__icontains=self.lhs)
            except CraftingMaterialType.DoesNotExist:
                if self.lhs not in other_items:
                    caller.msg("No material found for name %s." % self.lhs)
                    return
                material = OtherMaterial(self.lhs)
                usemats = False
            except CraftingMaterialType.MultipleObjectsReturned:
                try:
                    material = materials.get(name__iexact=self.lhs)
                except (CraftingMaterialType.DoesNotExist, CraftingMaterialType.MultipleObjectsReturned):
                    caller.msg("Unable to get a unique match for that.")
                    return
        if 'buy' in self.switches or 'import' in self.switches:
            if not usemats:
                amt = 1
            else:
                try:
                    amt = int(self.rhs)
                except (ValueError, TypeError):
                    caller.msg("Amount must be a number.")
                    return
                if amt < 1:
                    caller.msg("Amount must be a positive number")
                    return
            cost = material.value * amt
            try:
                dompc = caller.player_ob.Dominion
            except AttributeError:
                dompc = setup_utils.setup_dom_for_char(caller)
            if "buy" in self.switches:
                # use silver
                if cost > caller.db.currency:
                    caller.msg("That would cost %s silver coins, and you only have %s." % (cost, caller.db.currency))
                    return
                caller.pay_money(cost)
                paystr = "%s silver" % cost
            else:
                # use economic resources
                eamt = cost/RESOURCE_VAL
                # round up if not exact
                if cost % RESOURCE_VAL:
                    eamt += 1
                assets = dompc.assets
                if assets.economic < eamt:
                    caller.msg("That costs %s economic resources, and you have %s." % (eamt, assets.economic))
                    return
                assets.economic -= eamt
                assets.save()
                paystr = "%s economic resources" % eamt
                # check if they could have bought more than the amount they specified
                optimal_amt = (eamt * RESOURCE_VAL)/(material.value or 1)
                if amt < optimal_amt:
                    caller.msg("You could get %s for the same price, so doing that instead." % optimal_amt)
                    amt = optimal_amt
            if usemats:
                try:
                    mat = dompc.assets.materials.get(type=material)
                    mat.amount += amt
                    mat.save()
                except OwnedMaterial.DoesNotExist:
                    dompc.assets.materials.create(type=material, amount=amt)
            else:
                material.create(caller)
            caller.msg("You buy %s %s for %s." % (amt, material, paystr))
            return
        if 'sell' in self.switches:
            try:
                amt = int(self.rhs)
            except (ValueError, TypeError):
                caller.msg("Amount must be a number.")
                return
            if amt < 1:
                caller.msg("Must be a positive number.")
                return
            if not usemats:
                caller.msg("The market will only buy raw materials.")
                return
            try:
                dompc = PlayerOrNpc.objects.get(player=caller.player)
            except PlayerOrNpc.DoesNotExist:
                dompc = setup_utils.setup_dom_for_char(caller)
            try:
                mat = dompc.assets.materials.get(type=material)
            except OwnedMaterial.DoesNotExist:
                caller.msg("You don't have any of %s." % material.name)
                return
            if mat.amount < amt:
                caller.msg("You want to sell %s %s, but only have %s." % (amt, material, mat.amount))
                return
            mat.amount -= amt
            mat.save()
            money = caller.db.currency or 0.0
            sale = amt * material.value/20
            money += sale
            caller.db.currency = money
            caller.msg("You have sold %s %s for %s silver coins." % (amt, material.name, sale))
            return
        if 'info' in self.switches:
            msg = "{wInformation on %s:{n %s\n" % (material.name, material.desc)
            price = material.value
            msg += "{wPrice in silver: {c%s{n\n" % price
            cost = price/250
            if price % 250:
                cost += 1
            msg += "{wPrice in economic resources: {c%s{n" % cost
            caller.msg(msg)
            return
        if "economic" in self.switches or "military" in self.switches or "social" in self.switches:
            try:
                assets = caller.player_ob.Dominion.assets
                amt = int(self.args)
                if amt <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                caller.msg("Must specify a positive number.")
                return
            cost = 500 * amt
            if cost > caller.db.currency:
                caller.msg("That would cost %s and you have %s." % (cost, caller.db.currency))
                return
            caller.pay_money(cost)
            if "economic" in self.switches:
                assets.economic += amt
            elif "social" in self.switches:
                assets.social += amt
            elif "military" in self.switches:
                assets.military += amt
            assets.save()
            caller.msg("You have bought %s resources for %s." % (amt, cost))
            return
        caller.msg("Invalid switch.")
        return


class HaggleError(Exception):
    """Errors raised when haggling"""
    pass


class HaggledDeal(object):
    """Helper class for trying to haggle a deal"""
    VALID_RESOURCES = ('economic', 'military', 'social')

    def __init__(self, caller):
        self.caller = caller
        # build from SaverDict stored in haggling_deal attribute
        deal = self.caller.db.haggling_deal
        self.transaction_type = deal[0]
        # the material type we're trying to buy, and how much
        if deal[1] in self.VALID_RESOURCES:
            self.resource_type = deal[1]
            self.material = None
        else:
            self.material = CraftingMaterialType.objects.get(id=deal[1])
            self.resource_type = None
        self.amount = deal[2]
        # discount_roll will be None if they haven't haggled at all yet
        self.discount_roll = deal[3]
        self.roll_bonus = deal[4]
        # store cached reference to this object for use in haggle command
        self.caller.ndb.haggling_deal = self

    def accept(self):
        """Accepts the deal"""
        if not self.discount_roll:
            raise HaggleError("You haven't struck a deal yet. You must negotiate the deal before you can accept it.")
        if self.transaction_type == "sell":
            self.sell_materials()
        else:
            self.buy_materials()
        self.post_deal_cleanup()

    def decline(self):
        """Declines the deal"""
        self.caller.msg("You have cancelled the deal.")
        self.post_deal_cleanup()

    def post_deal_cleanup(self):
        """Cleans up the Evennia Attribute used for storage, haggling deal"""
        del self.caller.ndb.haggling_deal
        self.caller.attributes.remove("haggling_deal")

    def display(self):
        """Returns a user-friendly string of the status of our deal"""
        msg = "{wAttempting to %s:{n %s %s.\n" % (self.transaction_type, self.amount, self.material_display)
        noun = "Discount" if self.transaction_type == "buy" else "Markup Bonus"
        msg += "{wCurrent %s:{n %s\n" % (noun, self.discount)
        noun = "Value" if self.transaction_type == "sell" else "Cost"
        msg += "{wSilver %s:{n %s (Base Cost Per Unit: %s)" % (noun, self.silver_value, self.base_cost)
        msg += "\n{wRoll Modifier:{n %s" % self.roll_bonus
        return msg

    @property
    def material_display(self):
        """Displays material type we're after"""
        if self.resource_type:
            return "%s resources" % self.resource_type
        return str(self.material)

    def haggle(self):
        """Alters the terms of our deal. Pray they do not alter it further."""
        if not self.caller.player_ob.pay_action_points(5):
            return
        self.noble_discovery_check()
        difficulty = randint(-15, 65) - self.roll_bonus
        clout = self.caller.social_clout
        if clout > 0:
            difficulty -= randint(0, clout)
        roll = do_dice_check(self.caller, stat="charm", skill_list=["haggling", "haggling", "haggling", "streetwise"],
                             difficulty=difficulty)
        if roll <= self.discount_roll:
            self.caller.msg("You failed to find a better deal.\n%s" % self.display())
        else:
            self.discount_roll = roll
            self.save()
            self.caller.msg("You have found a better deal:\n%s" % self.display())

    def noble_discovery_check(self):
        """Checks if a noble loses fame for haggling"""
        rank = self.caller.db.social_rank or 10
        if rank > 6:
            return
        msg = "Engaging in crass mercantile haggling is considered beneath those of high social rank."
        if do_dice_check(stat="wits", skill="stealth", difficulty=30) < 1:
            fame_loss = self.caller.player_ob.Dominion.assets.fame // 100
            if not fame_loss:
                msg += " You were noticed, but fortunately, so few people know of you that it hardly matters."
            else:
                msg += " Unfortunately, you were noticed and lose %d fame." % fame_loss
                self.caller.player_ob.Dominion.assets.fame -= fame_loss
                self.caller.player_ob.Dominion.assets.save()
        else:
            msg += " Fortunately, no one noticed this time."
        self.caller.msg(msg)

    def save(self):
        """Saves the deal in the underlying Evennia Attribute so progress is not lost if server restarts"""
        self.caller.db.haggling_deal = (self.transaction_type, self.resource_type or self.material.id,
                                        self.amount, self.discount_roll, self.roll_bonus)

    @property
    def discount(self):
        """Calculate some value from discount roll"""
        discount = self.discount_roll
        base_value = 10 if self.transaction_type == "sell" else 0
        if discount <= 40:
            return discount + base_value
        if discount <= 60:
            return (41 + (discount - 40)//2) + base_value
        if discount <= 100:
            return (51 + (discount - 60)//4) + base_value
        if discount <= 160:
            return (61 + (discount - 100)//5) + base_value
        discount = 73 + (discount - 160)//6  # roll of 262 to cap
        if discount > 90:
            discount = 90
        return discount + base_value

    @property
    def silver_value(self):
        """Calculates silver value of the deal"""
        if self.transaction_type == "buy":
            discount = 100 - self.discount
        else:
            discount = self.discount
        return (self.base_cost * discount/100.0) * self.amount

    @property
    def base_cost(self):
        if self.resource_type:
            cost = 500.0
        else:
            if self.transaction_type == "buy":
                cost = self.material.value
            else:
                cost = round(pow(self.material.value, 0.9))
        return cost

    def sell_materials(self):
        """Attempt to sell the materials we made the deal for"""
        if self.resource_type:
            if not self.caller.player_ob.pay_resources(self.resource_type, amt=self.amount):
                raise HaggleError("You do not have enough resources to sell.")
        else:  # crafting materials
            err = "You do not have enough %s to sell." % self.material
            try:
                mats = self.caller.player_ob.Dominion.assets.materials.get(type=self.material)
                if mats.amount < self.amount:
                    raise HaggleError(err)
                mats.amount -= self.amount
                mats.save()
            except OwnedMaterial.DoesNotExist:
                raise HaggleError(err)
        silver = self.silver_value
        self.caller.pay_money(-silver)
        self.caller.msg("You have sold %s %s and gained %s silver." % (self.amount, self.material_display, silver))
        log_msg = "%s has sold %s %s and gained %s silver." % (self.caller, self.amount, self.material_display, silver)
        log_info("Haggle Log: %s" % log_msg)

    def buy_materials(self):
        """Attempt to buy the materials we made the deal for"""
        err = "You cannot afford the silver cost of %s."
        if self.resource_type:
            cost = self.silver_value
            if cost > self.caller.currency:
                raise HaggleError(err % cost)
            self.caller.player_ob.gain_resources(self.resource_type, self.amount)
        else:
            cost = self.silver_value
            if cost > self.caller.currency:
                raise HaggleError(err % cost)
            mat, _ = self.caller.player_ob.Dominion.assets.materials.get_or_create(type=self.material)
            mat.amount += self.amount
            mat.save()
        self.caller.pay_money(cost)
        self.caller.msg("You have bought %s %s for %s silver." % (self.amount, self.material_display, cost))
        log_msg = "%s has bought %s %s for %s silver." % (self.caller, self.amount, self.material_display, cost)
        log_info("Haggle Log: %s" % log_msg)


class CmdHaggle(ArxCommand):
    """
    Haggle to get a discount on goods
    Usage:
        haggle
        haggle/roll
        haggle/findbuyer <material>[,target]=<amount>[,minimum bonus]
        haggle/findseller <material>[,target]=<amount>[,minimum bonus]
        haggle/accept
        haggle/decline

    This can buy/sell materials and resources. You must first attempt to find
    a buyer or seller for your deal. Once found, you can /roll to attempt to
    negotiate the terms of the deal with them. Nobles should beware - it's
    considered extremely crass to haggle, and if they are discovered doing
    so, their reputation will suffer.

    Both looking for a deal and negotiating the agreement costs 5 AP per
    attempt. A deal can be found for another character to do the haggling
    roll by specifying an optional target in findbuyer/findseller. If a
    minimum bonus is specified, the deal will only be sent to them if the
    search roll gets that bonus or higher, otherwise the deal is discarded.
    The maximum bonus that can be returned from a search attempt is 25.

    Resources can be bought or sold by specifying the type of resource as
    the 'material'.
    """
    key = "haggle"
    locks = "cmd:all()"
    help_category = "Market"

    @property
    def deal(self):
        """
        We find if the caller has a HagglingTransaction cached. If so, we return the cached object. If they
        have a SaverDict in an evennia Attribute that can build the transaction, we build the transaction,
        cache it, and return it.
        """
        if self.caller.ndb.haggling_deal:
            return self.caller.ndb.haggling_deal
        if self.caller.db.haggling_deal is None:
            return None
        return HaggledDeal(self.caller)

    def send_deal(self, target, deal):
        """ Sends a deal to the target
        Args:
            target: Character we're sending it to
            deal: tuple that will be built into a HaggledDeal
        """
        target.db.haggling_deal = deal
        deal = HaggledDeal(target)
        if target != self.caller:
            msg = "You have been sent a deal that you can choose to haggle by %s." % self.caller
            msg += "\n%s" % deal.display()
            target.player_ob.inform(msg, category="Deal Offer")

    def func(self):
        """Execute haggle command"""
        try:
            if not self.args and not self.switches:
                return self.display_current_deal()
            if "findbuyer" in self.switches or "findseller" in self.switches:
                return self.find_deal()
            if not self.deal:
                raise HaggleError("You must have a deal first.")
            if "roll" in self.switches:
                return self.deal.haggle()
            if "accept" in self.switches:
                return self.deal.accept()
            if "decline" in self.switches:
                return self.deal.decline()
        except HaggleError as err:
            self.msg(err)
            return
        self.msg("Invalid switch.")

    def display_current_deal(self):
        """Outputs our current deal"""
        if not self.deal:
            raise HaggleError("You currently haven't found a deal to negotiate. Use haggle/findbuyer or "
                              "haggle/findseller first.")
        self.msg(self.deal.display())

    def find_deal(self):
        """Attempts to find a HaggledDeal for our caller"""
        target = self.caller
        min_bonus = None
        if len(self.lhslist) > 1:
            target = target.player.search(self.lhslist[1])
            if not target:
                return
            target = target.char_ob
        if target.db.haggling_deal:
            if target == self.caller:
                err = "You already have a deal in progress: please decline it first.\n%s" % self.deal.display()
            else:
                err = "They already have a deal in progress. Ask them to decline it first."
            raise HaggleError(err)
        try:
            material, amount = self.lhslist[0], int(self.rhslist[0])
            if amount < 1:
                raise ValueError
            if len(self.rhslist) > 1:
                try:
                    min_bonus = min(int(self.rhslist[1]), 25)
                except ValueError:
                    raise HaggleError("The optional minimum bonus must be a number.")
        except (TypeError, ValueError, IndexError):
            raise HaggleError("You must provide a material type and a positive amount for the transaction.")
        if material not in HaggledDeal.VALID_RESOURCES:
            try:
                material = CraftingMaterialType.objects.exclude(acquisition_modifiers__icontains="nosell")\
                                                       .get(name__iexact=material)
                material_identifier = material.id
            except CraftingMaterialType.DoesNotExist:
                raise HaggleError("No material found for the name '%s'." % material)
        else:
            material_identifier = material
        if not self.caller.player_ob.pay_action_points(5):
            return
        # transaction type is what we're doing, buying or selling. their_verb is for the display of the other party
        transaction_type = "buy" if "findseller" in self.switches else "sell"
        their_verb = "sell" if transaction_type == "buy" else "buy"
        amount, roll_bonus = self.search_for_deal_roll(material, amount)
        if min_bonus is not None:
            if roll_bonus < min_bonus:
                raise HaggleError("The roll bonus of %s was below the minimum of %s, so the deal is cancelled." % (
                    roll_bonus, min_bonus))
        self.send_deal(target, (transaction_type, material_identifier, amount, 0, roll_bonus))
        msg = "You found someone willing to %s %s %s." % (their_verb, amount, material)
        if target == self.caller:
            msg += " You can use /roll to try to negotiate the price."
        else:
            msg += " You let %s know that a deal is on the way." % target.key
        self.msg(msg)

    def search_for_deal_roll(self, material, amount):
        """Does the roll to search for a deal. Positive roll * 5000 is how
        much of the value of the material they're able to buy/sell.
            Args:
                material: The type of material we're looking for
                amount: Max amount much we're looking to buy/sell
            Returns:
                The amount we're able to buy/sell and a modifier to haggling rolls
            Raises:
                HaggleError if they fail to find a deal.
        """
        from math import ceil
        skill = "economics" if self.caller.db.skills.get("economics", 0) > self.caller.db.skills.get("streetwise", 0) \
            else "streetwise"
        difficulty = 20
        bonus = 0
        roll = do_dice_check(self.caller, skill=skill, stat="perception", difficulty=difficulty, quiet=False)
        if roll < 0:
            raise HaggleError("You failed to find anyone willing to deal with you at all.")
        if material in HaggledDeal.VALID_RESOURCES:
            # resources are worth 500 each
            value_per_object = 500
        else:
            value_per_object = round(pow(material.value, 1.05))
        value_we_found = roll * 5000.0
        value_for_amount = value_we_found / value_per_object
        if value_for_amount < 1.0:
            penalty = int((1.0 - value_for_amount) * -100)
            amount_found = 1
            self.msg("You had trouble finding a deal for such a valuable item. "
                     "Haggling rolls will have a penalty of %s." % penalty)
            return amount_found, penalty
        # minimum of 1
        amount_found = max(int(ceil(value_we_found / value_per_object)), 1)
        if amount_found > amount:
            bonus = min(amount_found - amount, 25)
            self.msg("Due to your success in searching for a deal, haggling rolls will have a bonus of %s." % bonus)
        return min(amount, amount_found), bonus
