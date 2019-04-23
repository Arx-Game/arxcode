from evennia.utils.idmapper.models import SharedMemoryModel
from evennia.utils.utils import lazy_property
from django.db import models
from django.db.models import Q
from world.dominion import unit_types, unit_constants
from world.dominion.battle import Battle

import traceback


class Minister(SharedMemoryModel):
    """
    A minister appointed to assist a ruler in a category.
    """
    POP, INCOME, FARMING, PRODUCTIVITY, UPKEEP, LOYALTY, WARFARE = range(7)
    MINISTER_TYPES = (
        (POP, 'Population'),
        (INCOME, 'Income'),
        (FARMING, 'Farming'),
        (PRODUCTIVITY, 'Productivity'),
        (UPKEEP, 'Upkeep'),
        (LOYALTY, 'Loyalty'),
        (WARFARE, 'Warfare'),
        )
    title = models.CharField(blank=True, null=True, max_length=255)
    player = models.ForeignKey("PlayerOrNpc", related_name="appointments", blank=True, null=True, db_index=True)
    ruler = models.ForeignKey("Ruler", related_name="ministers", blank=True, null=True, db_index=True)
    category = models.PositiveSmallIntegerField(choices=MINISTER_TYPES, default=INCOME)

    def __str__(self):
        return "%s acting as %s minister for %s" % (self.player, self.get_category_display(), self.ruler)

    def clear_domain_cache(self):
        """Clears cache for the ruler of this minister"""
        return self.ruler.clear_domain_cache()


class Army(SharedMemoryModel):
    """
    Any collection of military units belonging to a given domain.
    """
    name = models.CharField(blank=True, null=True, max_length=80, db_index=True)
    desc = models.TextField(blank=True, null=True)
    # the domain that we obey the orders of. Not the same as who owns us, necessarily
    domain = models.ForeignKey("Domain", on_delete=models.SET_NULL, related_name="armies", blank=True, null=True,
                               db_index=True)
    # current location of this army
    land = models.ForeignKey("Land", on_delete=models.SET_NULL, related_name="armies", blank=True, null=True)
    # if the army is located as a castle garrison
    castle = models.ForeignKey("Castle", on_delete=models.SET_NULL, related_name="garrison", blank=True, null=True)
    # The field leader of this army. Units under his command may have their own commanders
    general = models.ForeignKey("PlayerOrNpc", on_delete=models.SET_NULL, related_name="armies", blank=True, null=True,
                                db_index=True)
    # an owner who may be the same person who owns the domain. Or not, in the case of mercs, sent reinforcements, etc
    owner = models.ForeignKey("AssetOwner", on_delete=models.SET_NULL, related_name="armies", blank=True, null=True,
                              db_index=True)
    # Someone giving orders for now, like a mercenary group's current employer
    temp_owner = models.ForeignKey("AssetOwner", on_delete=models.SET_NULL, related_name="loaned_armies", blank=True,
                                   null=True, db_index=True)
    # a relationship to self for smaller groups within the army
    group = models.ForeignKey("self", on_delete=models.SET_NULL, related_name="armies", blank=True, null=True,
                              db_index=True)
    # food we're carrying with us on transports or whatever
    stored_food = models.PositiveSmallIntegerField(default=0, blank=0)
    # whether the army is starving. 0 = not starving, 1 = starting to starve, 2 = troops dying/deserting
    starvation_level = models.PositiveSmallIntegerField(default=0, blank=0)
    morale = models.PositiveSmallIntegerField(default=100, blank=100)
    # how much booty an army is carrying.
    plunder = models.PositiveSmallIntegerField(default=0, blank=0)

    class Meta:
        """Define Django meta options"""
        verbose_name_plural = "Armies"

    def display(self):
        """
        Like domain.display(), returns a string for the mush of our
        different attributes.
        """
        # self.owner is an AssetOwner, so its string name is AssetOwner.owner
        owner = self.owner
        if owner:
            owner = owner.owner
        msg = "{wName{n: %s {wGeneral{n: %s\n" % (self.name, self.general)
        msg += "{wDomain{n: %s {wLocation{n: %s\n" % (self.domain, self.land)
        msg += "{wOwner{n: %s\n" % owner
        msg += "{wDescription{n: %s\n" % self.desc
        msg += "{wMorale{n: %s {wFood{n: %s {wStarvation Level{n: %s {wPlunder{n: %s\n" % (self.morale, self.plunder,
                                                                                           self.starvation_level,
                                                                                           self.plunder)
        msg += "{wUnits{n:\n"
        from evennia.utils.evtable import EvTable
        table = EvTable("{wID{n", "{wCommander{n", "{wType{n", "{wAmt{n", "{wLvl{n", "{wEquip{n", "{wXP{n", width=78,
                        border="cells")
        for unit in self.units.all():
            typestr = unit.type.capitalize()
            cmdstr = ""
            if unit.commander:
                cmdstr = "{c%s{n" % unit.commander
            table.add_row(unit.id, cmdstr, typestr, unit.quantity, unit.level, unit.equipment, unit.xp)
        msg += str(table)
        return msg

    def can_change(self, player):
        """
        Checks if a given player has permission to change the structure of this
        army, edit it, or destroy it.
        """
        # check if player is staff
        if player.check_permstring("builder"):
            return True
        # checks player's access because our owner can be an Org
        if self.owner.access(player, "army"):
            return True
        if player.Dominion.appointments.filter(category=Minister.WARFARE, ruler__house=self.owner):
            return True
        return False

    def can_order(self, player):
        """
        Checks if a given player has permission to issue orders to this army.
        """
        # if we can change the army, we can also order it
        if self.can_change(player):
            return True
        dompc = player.Dominion
        # check if we're appointed as general of this army
        if dompc == self.general:
            return True
        # check player's access because temp owner can also be an org
        if self.temp_owner and self.temp_owner.access(player, "army"):
            return True
        if self.temp_owner and dompc.appointments.filter(category=Minister.WARFARE, ruler__house=self.temp_owner):
            return True
        return False

    def can_view(self, player):
        """
        Checks if given player has permission to view Army details.
        """
        # if we can order army, we can also view it
        if self.can_order(player):
            return True
        # checks if we're a unit commander
        if player.Dominion.units.filter(army=self):
            return True
        # checks if we're part of the org the army belongs to
        if player.Dominion.memberships.filter(Q(deguilded=False) & (
                    Q(organization__assets=self.owner) | Q(organization__assets=self.temp_owner))):
            return True

    @property
    def pending_orders(self):
        """
        Returns pending orders if they exist.
        """
        return self.orders.filter(complete=False)

    def send_orders(self, player, order_type, target_domain=None, target_land=None, target_character=None,
                    action=None, action_assist=None, assisting=None):
        """
        Checks permission to send orders to an army, then records the category
        of orders and their target.
        """
        # first checks for access
        if not self.can_order(player):
            player.msg("You don't have access to that Army.")
            return
        # create new orders for this unit
        if self.pending_orders:
            player.msg("That army has pending orders that must be canceled first.")
            return
        return self.orders.create(type=order_type, target_domain=target_domain, target_land=target_land,
                                  target_character=target_character, action=action, action_assist=action_assist,
                                  assisting=assisting)

    def find_unit(self, unit_type):
        """
        Find a unit that we have of the given unit_type. Armies should only have one of each unit_type
        of unit in them, so we can always just return the first match of the queryset.
        """
        qs = self.units.filter(unit_type=unit_type)
        if len(qs) < 1:
            return None
        return qs[0]

    def change_general(self, caller, general):
        """Change an army's general. Informs old and new generals of change.

        Sets an Army's general to new character or to None and informs the old
        general of the change, if they exist.

        Args:
            caller: a player object
            general: a player object
        """
        if self.general:
            self.general.inform("%s has relieved you from duty as general of army: %s." % (caller, self))
        if general:
            self.general = general.Dominion
            self.save()
            general.inform("%s has set you as the general of army: %s." % (caller, self))
            return
        self.general = None
        self.save()

    def change_temp_owner(self, caller, temp_owner):
        """Change an army's temp_owner. Informs old and new temp_owners of change.

        Sets an Army's temp_owner to new character or to None and informs the old
        temp_owner of the change, if they exist.

        Args:
            caller: a player object
            temp_owner: an AssetOwner
        """
        if self.temp_owner:
            self.temp_owner.inform_owner("%s has retrieved an army that you temporarily controlled: %s." % (caller,
                                                                                                            self))
        self.temp_owner = temp_owner
        self.save()
        if temp_owner:
            temp_owner.inform_owner("%s has given you temporary control of army: %s." % (caller, self))

    @property
    def max_units(self):
        """How many units can be in the army"""
        if not self.general:
            return 0
        # TODO maybe look at general's command/leadership
        return 5

    @property
    def at_capacity(self):
        """Whether the army is maxxed out"""
        if self.units.count() >= self.max_units:
            return True

    def get_unit_class(self, name):
        """Gets the class of a unit type, special or otherwise"""
        try:
            match = self.owner.organization_owner.unit_mods.get(name__iexact=name)
            # get unit type from match and return it
            return unit_types.get_unit_class_by_id(match.unit_type)
        except (AttributeError, OrgUnitModifiers.DoesNotExist):
            pass
        # no match, get unit type from string and return it
        return unit_types.cls_from_str(name)

    def get_food_consumption(self):
        """
        Total food consumption for our army
        """
        hunger = 0
        for unit in self.units.all():
            hunger += unit.food_consumption
        return hunger

    def consume_food(self, report=None):
        """
        To do: have food eaten while we're executing orders, which limits
        how far out we can be. Otherwise we're just a drain on our owner
        or temp owner domain, or it's converted into money cost
        """
        total = self.get_food_consumption()
        consumed = 0
        if self.domain:
            if self.domain.stored_food > total:
                self.domain.stored_food -= total
                consumed = total
                total = 0
            else:
                consumed = self.domain.stored_food
                total -= self.domain.stored_food
                self.domain.stored_food = 0
            self.domain.save()
        cost = total * 10
        if cost:
            owner = self.temp_owner or self.owner
            if owner:
                owner.vault -= cost
                owner.save()
        report.add_army_consumption_report(self, food=consumed, silver=cost)

    def starve(self):
        """
        If our hunger is too great, troops start to die and desert.
        """
        for unit in self.units.all():
            unit.decimate()

    # noinspection PyMethodMayBeStatic
    def countermand(self):
        """
        Erases our orders, refunds the value to our domain.
        """
        pass

    def execute_orders(self, week, report=None):
        """
        Execute our orders. This will be called from the Weekly Script,
        along with do_weekly_adjustment. Error checking on the validity
        of orders should be done at the player-command level, not here.
        """
        # stoof here later
        self.orders.filter(week__lt=week - 1, action__isnull=True).update(complete=True)
        # if not orders:
        #     self.morale += 1
        #     self.save()
        #     return
        # for order in orders:
        #     if order.type == Orders.TRAIN:
        #         for unit in self.units.all():
        #             unit.train()
        #         return
        #     if order.type == Orders.EXPLORE:
        #         explore = Exploration(self, self.land, self.domain, week)
        #         explore.event()
        #         return
        #     if order.type == Orders.RAID:
        #         if self.do_battle(order.target_domain, week):
        #             # raid was successful
        #             self.pillage(order.target_domain, week)
        #         else:
        #             self.morale -= 10
        #             self.save()
        #     if order.type == Orders.CONQUER:
        #         if self.do_battle(order.target_domain, week):
        #             # conquest was successful
        #             self.conquer(order.target_domain, week)
        #         else:
        #             self.morale -= 10
        #             self.save()
        #     if order.type == Orders.ENFORCE_ORDER:
        #         self.pacify(self.domain)
        #     if order.type == Orders.BESIEGE:
        #         # to be implemented later
        #         pass
        #     if order.type == Orders.MARCH:
        #         if order.target_domain:
        #             self.domain = order.target_domain
        #         self.land = order.target_land
        #         self.save()
        # to do : add to report here
        if report:
            print("Placeholder for army orders report")

    def do_battle(self, tdomain, week):
        """
        Returns True if attackers win, False if defenders
        win or if there was a stalemate/tie.
        """
        # noinspection PyBroadException
        try:
            e_armies = tdomain.armies.filter(land_id=tdomain.land.id)
            if not e_armies:
                # No opposition. We win without a fight
                return True
            atkpc = self.general
            defpc = None
            if self.domain and self.domain.ruler and self.domain.ruler.castellan:
                atkpc = self.domain.ruler.castellan
            if tdomain and tdomain.ruler and tdomain.ruler.castellan:
                defpc = tdomain.ruler.castellan
            battle = Battle(armies_atk=self, armies_def=e_armies, week=week,
                            pc_atk=atkpc, pc_def=defpc, atk_domain=self.domain, def_domain=tdomain)
            result = battle.begin_combat()
            # returns True if result shows ATK_WIN, False otherwise
            return result == Battle.ATK_WIN
        except Exception:
            print("ERROR: Could not generate battle on domain.")
            traceback.print_exc()

    def pillage(self, target, week):
        """
        Successfully pillaging resources from the target domain
        and adding them to our own domain.
        """
        loot = target.plundered_by(self, week)
        self.plunder += loot
        self.save()

    def pacify(self, target):
        """Puts down unreset"""
        percent = float(self.quantity)/target.total_serfs
        percent *= 100
        percent = int(percent)
        target.lawlessness -= percent
        target.save()
        self.morale -= 1
        self.save()

    def conquer(self, target, week):
        """
        Conquers a domain. If the army has a domain, that domain will
        absorb the target if they're bordering, or just change the rulers
        while keeping it intact otherwise. If the army has no domain, then
        the general will be set as the ruler of the domain.
        """
        bordering = None
        ruler = None
        other_domains = None
        # send remaining armies to other domains
        if target.ruler:
            other_domains = Domain.objects.filter(ruler_id=target.ruler.id).exclude(id=target.id)
        if other_domains:
            for army in target.armies.all():
                army.domain = other_domains[0]
                army.save()
        else:  # armies have nowhere to go, so having their owning domain wiped
            target.armies.clear()
        for castle in target.castles.all():
            castle.garrison.clear()
        if not self.domain:
            # The general becomes the ruler
            if self.owner:
                castellan = None
                if self.general:
                    castellan = self.general.player
                ruler_list = Ruler.objects.filter(house_id=self.owner)
                if ruler_list:
                    ruler = ruler_list[0]
                else:
                    ruler = Ruler.objects.create(house=self.owner, castellan=castellan)
            # determine if we have a bordering domain that can absorb this
        else:
            ruler = self.domain.ruler
            if ruler:
                bordering = Domain.objects.filter(land_id=target.land.id).filter(
                    ruler_id=ruler.id)
        # we have a bordering domain. We will annex/absorb the domain into it
        if bordering:
            if self.domain in bordering:
                conqueror = self.domain
            else:
                conqueror = bordering[0]
            conqueror.annex(target, week, self)
        else:  # no bordering domain. So domain intact, but changing owner
            # set the domain's ruler
            target.ruler = ruler
            target.lawlessness += 50
            target.save()
            # set army as occupying the domain
            self.domain = target
            self.save()

    # noinspection PyUnusedLocal
    def do_weekly_adjustment(self, week, report=None):
        """
        Weekly maintenance for the army. Consume food.
        """
        self.consume_food(report)

    def _get_costs(self):
        """
        Costs for the army.
        """
        cost = 0
        for unit in self.units.all():
            cost += unit.costs
        return cost
    costs = property(_get_costs)

    def _get_size(self):
        """
        Total size of our army
        """
        size = 0
        for unit in self.units.all():
            size += unit.quantity
        return size
    size = property(_get_size)

    def __unicode__(self):
        return "%s (#%s)" % (self.name or "Unnamed army", self.id)

    def __repr__(self):
        return "<Army (#%s): %s>" % (self.id, self.name)

    def save(self, *args, **kwargs):
        """Saves changes and clears cache"""
        super(Army, self).save(*args, **kwargs)
        try:
            self.owner.clear_cached_properties()
        except (AttributeError, ValueError, TypeError):
            pass


class Orders(SharedMemoryModel):
    """
    Orders for an army that will be executed during weekly maintenance. These
    are macro-scale orders for the entire army. Tactical commands during battle
    will not be handled in the model level, but in a separate combat simulator.
    Orders cannot be given to individual units. For separate units to be given
    orders, they must be separated into different armies. This will be handled
    by player commands for Dominion.
    """
    TRAIN = 1
    EXPLORE = 2
    RAID = 3
    CONQUER = 4
    ENFORCE_ORDER = 5
    BESIEGE = 6
    MARCH = 7
    DEFEND = 8
    PATROL = 9
    ASSIST = 10
    BOLSTER = 11
    EQUIP = 12
    CRISIS = 13

    ORDER_CHOICES = (
        (TRAIN, 'Troop Training'),
        (EXPLORE, 'Explore territory'),
        (RAID, 'Raid Domain'),
        (CONQUER, 'Conquer Domain'),
        (ENFORCE_ORDER, 'Enforce Order'),
        (BESIEGE, 'Besiege Castle'),
        (MARCH, 'March'),
        (DEFEND, 'Defend'),
        # like killing bandits
        (PATROL, 'Patrol'),
        # assisting other armies' orders
        (ASSIST, 'Assist'),
        # restoring morale
        (BOLSTER, 'Bolster Morale'),
        (EQUIP, 'Upgrade Equipment'),
        # using army in a crisis action
        (CRISIS, 'Crisis Response'))
    army = models.ForeignKey("Army", related_name="orders", null=True, blank=True, db_index=True)
    # for realm PVP and realm offense/defense
    target_domain = models.ForeignKey("Domain", related_name="orders", null=True, blank=True, db_index=True)
    # for travel and exploration
    target_land = models.ForeignKey("Land", related_name="orders", null=True, blank=True)
    # an individual's support for training, morale, equipment
    target_character = models.ForeignKey("PlayerOrNpc", on_delete=models.SET_NULL, related_name="orders", blank=True,
                                         null=True, db_index=True)
    # if we're targeting an action or asist. omg skorpins.
    action = models.ForeignKey("PlotAction", related_name="orders", null=True, blank=True, db_index=True)
    action_assist = models.ForeignKey("PlotActionAssistant", related_name="orders", null=True, blank=True,
                                      db_index=True)
    # if we're assisting another army's orders
    assisting = models.ForeignKey("self", related_name="assisting_orders", null=True, blank=True, db_index=True)
    type = models.PositiveSmallIntegerField(choices=ORDER_CHOICES, default=TRAIN)
    coin_cost = models.PositiveIntegerField(default=0, blank=0)
    food_cost = models.PositiveIntegerField(default=0, blank=0)
    # If orders were given this week, they're still pending
    week = models.PositiveSmallIntegerField(default=0, blank=0)
    complete = models.BooleanField(default=False, blank=False)

    class Meta:
        """Define Django meta options"""
        verbose_name_plural = "Army Orders"

    def calculate_cost(self):
        """
        Calculates cost for an action and assigns self.coin_cost
        """
        DIV = 100
        costs = sum((ob.costs/DIV) + 1 for ob in self.units.all())
        self.coin_cost = costs
        self.save()

    @property
    def troops_sent(self):
        """Returns display of troops being ordered"""
        return ", ".join("%s %s" % (ob.quantity, ob.type) for ob in self.army.units.all())


class UnitTypeInfo(models.Model):
    """Abstract base class with information about military units"""
    INFANTRY = unit_constants.INFANTRY
    PIKE = unit_constants.PIKE
    CAVALRY = unit_constants.CAVALRY
    ARCHERS = unit_constants.ARCHERS
    LONGSHIP = unit_constants.LONGSHIP
    SIEGE_WEAPON = unit_constants.SIEGE_WEAPON
    GALLEY = unit_constants.GALLEY
    DROMOND = unit_constants.DROMOND
    COG = unit_constants.COG

    UNIT_CHOICES = (
        (INFANTRY, 'Infantry'),
        (PIKE, 'Pike'),
        (CAVALRY, 'Cavalry'),
        (ARCHERS, 'Archers'),
        (LONGSHIP, 'Longship'),
        (SIEGE_WEAPON, 'Siege Weapon'),
        (GALLEY, 'Galley'),
        (COG, 'Cog'),
        (DROMOND, 'Dromond'),
        )
    # type will be used to derive units and their stats elsewhere
    unit_type = models.PositiveSmallIntegerField(choices=UNIT_CHOICES, default=0, blank=0)

    class Meta:
        abstract = True


class OrgUnitModifiers(UnitTypeInfo):
    """Model that has modifiers from an org to make a special unit"""
    org = models.ForeignKey('Organization', related_name="unit_mods", db_index=True)
    mod = models.SmallIntegerField(default=0, blank=0)
    name = models.CharField(blank=True, null=True, max_length=80)

    class Meta:
        """Define Django meta options"""
        verbose_name_plural = "Unit Modifiers"


class MilitaryUnit(UnitTypeInfo):
    """
    An individual unit belonging to an army for a domain. Each unit can have its own
    commander, while the overall army has its general. It is assumed that every
    unit in an army is in the same space, and will all respond to the same orders.

    Most combat stats for a unit will be generated at runtime based on its 'type'. We'll
    only need to store modifiers for a unit that are specific to it, modifiers it has
    accured.
    """
    origin = models.ForeignKey('Organization', related_name='units', blank=True, null=True, db_index=True)
    commander = models.ForeignKey("PlayerOrNpc", on_delete=models.SET_NULL, related_name="units", blank=True, null=True)
    army = models.ForeignKey("Army", related_name="units", blank=True, null=True, db_index=True)
    orders = models.ForeignKey("Orders", related_name="units", on_delete=models.SET_NULL, blank=True, null=True,
                               db_index=True)
    quantity = models.PositiveSmallIntegerField(default=1, blank=1)
    level = models.PositiveSmallIntegerField(default=0, blank=0)
    equipment = models.PositiveSmallIntegerField(default=0, blank=0)
    # can go negative, such as when adding new recruits to a unit
    xp = models.SmallIntegerField(default=0, blank=0)
    # if a hostile area has bandits or whatever, we're not part of an army, just that
    hostile_area = models.ForeignKey("HostileArea", on_delete=models.SET_NULL, related_name="units", blank=True,
                                     null=True)

    def display(self):
        """
        Returns a string representation of this unit's stats.
        """
        cmdstr = ""
        if self.commander:
            cmdstr = "{c%s{n " % self.commander
        msg = "{wID:{n#%s %s{wType{n: %-12s {wAmount{n: %-7s" % (self.id, cmdstr, self.type.capitalize(), self.quantity)
        msg += " {wLevel{n: %s {wEquip{n: %s {wXP{n: %s" % (self.level, self.equipment, self.xp)
        return msg

    def change_commander(self, caller, commander):
        """Informs commanders of a change, if they exist.

        Sets a unit's commander to new character or to None and informs the old
        commander of the change.

        Args:
            caller: a player object
            commander: a player object
        """
        old_commander = self.commander
        if old_commander:
            old_commander.inform("%s has relieved you of command of unit %s." % (caller, self.id))
        if commander:
            self.commander = commander.Dominion
            self.save()
            commander.inform("%s has set you in command of unit %s." % (caller, self.id))
            return
        self.commander = None
        self.save()

    def split(self, qty):
        """Create a duplicate unit with a specified quantity.

        Copies a unit, but with a specific quantity and no commander to simulate
        it being split.

        Args:
            qty: an integer
        """
        self.quantity -= qty
        self.save()
        MilitaryUnit.objects.create(origin=self.origin, army=self.army, orders=self.orders, quantity=qty,
                                    level=self.level, equipment=self.equipment, xp=self.xp,
                                    hostile_area=self.hostile_area, unit_type=self.unit_type)

    def decimate(self, amount=0.10):
        """
        Losing a percentage of our troops. Generally this is due to death
        from starvation or desertion. In this case, we don't care which.
        """
        # Ten percent of our troops
        losses = self.quantity * amount
        # lose it, rounded up
        self.do_losses(int(round(losses)))

    def do_losses(self, losses):
        """
        Lose troops. If we have 0 left, this unit is gone.
        """
        self.quantity -= losses
        if self.quantity <= 0:
            self.delete()

    def train(self, val=1):
        """
        Getting xp, and increasing our level if we have enough. The default
        value is for weekly troop training as a command. Battles will generally
        give much more than normal training.
        """
        self.gain_xp(val)

    # noinspection PyMethodMayBeStatic
    def adjust_readiness(self, troops, training=0, equip=0):
        """
        Degrades the existing training and equipment level of our troops
        when we merge into others. This does not perform the merger, only
        changes our readiness by the given number of troops, training level,
        and equipment level.
        """
        pass

    @lazy_property
    def stats(self):
        """Returns stats for this type of unit"""
        return unit_types.get_unit_stats(self)

    def _get_costs(self):
        """
        Costs for the unit.
        """
        try:
            cost = self.stats.silver_upkeep
        except AttributeError:
            print("Type %s is not a recognized MilitaryUnit type!" % self.unit_type)
            print("Warning. No cost assigned to <MilitaryUnit- ID: %s>" % self.id)
            cost = 0
        cost *= self.quantity
        return cost

    def _get_food_consumption(self):
        """
        Food for the unit
        """
        try:
            hunger = self.stats.food_upkeep
        except AttributeError:
            print("Type %s is not a recognized Military type!" % self.unit_type)
            print("Warning. No food upkeep assigned to <MilitaryUnit - ID: %s>" % self.id)
            hunger = 0
        hunger *= self.quantity
        return hunger

    food_consumption = property(_get_food_consumption)
    costs = property(_get_costs)

    def _get_type_name(self):
        try:
            return self.stats.name.lower()
        except AttributeError:
            return "unknown type"
    type = property(_get_type_name)

    def __unicode__(self):
        return "%s %s" % (self.quantity, self.type)

    def __repr__(self):
        return "<Unit (#%s): %s %s>" % (self.id, self.quantity, self.type)

    def save(self, *args, **kwargs):
        """Saves changes and clears cache"""
        super(MilitaryUnit, self).save(*args, **kwargs)
        try:
            self.army.owner.clear_cached_properties()
        except (AttributeError, TypeError, ValueError):
            pass

    def combine_units(self, target):
        """
        Combine our units. get average of both worlds. Mediocrity wins!
        """
        total = self.quantity + target.quantity
        self.level = ((self.level * self.quantity) + (target.level * target.quantity))/total
        self.equipment = ((self.equipment * self.quantity) + (target.equipment * target.quantity))/total
        self.quantity = total
        self.xp = ((self.quantity * self.xp) + (target.quantity * target.xp))/total
        self.save()
        target.delete()

    def gain_xp(self, amount):
        """
        Gain xp, divided among our quantity
        Args:
            amount: int
        """
        gain = int(round(float(amount)/self.quantity))
        # always gain at least 1 xp
        if gain < 1:
            gain = 1
        self.xp += gain
        levelup_cost = self.stats.levelup_cost
        if self.xp > levelup_cost:
            self.xp -= levelup_cost
            self.level += 1
        self.save()

