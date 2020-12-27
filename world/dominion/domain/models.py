from evennia.utils.idmapper.models import SharedMemoryModel
from evennia.utils.utils import lazy_property
from django.db import models
from django.db.models import Q
from django.core.exceptions import ObjectDoesNotExist

from server.utils.arx_utils import CachedPropertiesMixin, CachedProperty
from world.dominion import unit_types, unit_constants
from world.dominion.battle import Battle

import traceback

# Dominion constants
# default value for a global modifier to Dominion income, can be set as a ServerConfig value on a per-game basis
SILVER_PER_BUILDING = 225.00
FOOD_PER_FARM = 100.00
DEFAULT_GLOBAL_INCOME_MOD = -0.25
# each point in a dominion skill is a 5% bonus
BONUS_PER_SKILL_POINT = 0.10
# number of workers for a building to be at full production
SERFS_PER_BUILDING = 20.0
# population cap for housing
BASE_WORKER_COST = 0.10
POP_PER_HOUSING = 1000
BASE_POP_GROWTH = 0.01
DEATHS_PER_LAWLESS = 0.0025
LAND_SIZE = 10000
LAND_COORDS = 9


class Minister(SharedMemoryModel):
    """
    A minister appointed to assist a ruler in a category.
    """

    POP, INCOME, FARMING, PRODUCTIVITY, UPKEEP, LOYALTY, WARFARE = range(7)
    MINISTER_TYPES = (
        (POP, "Population"),
        (INCOME, "Income"),
        (FARMING, "Farming"),
        (PRODUCTIVITY, "Productivity"),
        (UPKEEP, "Upkeep"),
        (LOYALTY, "Loyalty"),
        (WARFARE, "Warfare"),
    )
    title = models.CharField(blank=True, null=True, max_length=255)
    player = models.ForeignKey(
        "PlayerOrNpc",
        related_name="appointments",
        blank=True,
        null=True,
        db_index=True,
        on_delete=models.CASCADE,
    )
    ruler = models.ForeignKey(
        "Ruler",
        related_name="ministers",
        blank=True,
        null=True,
        db_index=True,
        on_delete=models.CASCADE,
    )
    category = models.PositiveSmallIntegerField(choices=MINISTER_TYPES, default=INCOME)

    def __str__(self):
        return "%s acting as %s minister for %s" % (
            self.player,
            self.get_category_display(),
            self.ruler,
        )

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
    domain = models.ForeignKey(
        "Domain",
        on_delete=models.SET_NULL,
        related_name="armies",
        blank=True,
        null=True,
        db_index=True,
    )
    # current location of this army
    land = models.ForeignKey(
        "Land", on_delete=models.SET_NULL, related_name="armies", blank=True, null=True
    )
    # if the army is located as a castle garrison
    castle = models.ForeignKey(
        "Castle",
        on_delete=models.SET_NULL,
        related_name="garrison",
        blank=True,
        null=True,
    )
    # The field leader of this army. Units under his command may have their own commanders
    general = models.ForeignKey(
        "PlayerOrNpc",
        on_delete=models.SET_NULL,
        related_name="armies",
        blank=True,
        null=True,
        db_index=True,
    )
    # an owner who may be the same person who owns the domain. Or not, in the case of mercs, sent reinforcements, etc
    owner = models.ForeignKey(
        "AssetOwner",
        on_delete=models.SET_NULL,
        related_name="armies",
        blank=True,
        null=True,
        db_index=True,
    )
    # Someone giving orders for now, like a mercenary group's current employer
    temp_owner = models.ForeignKey(
        "AssetOwner",
        on_delete=models.SET_NULL,
        related_name="loaned_armies",
        blank=True,
        null=True,
        db_index=True,
    )
    # a relationship to self for smaller groups within the army
    group = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        related_name="armies",
        blank=True,
        null=True,
        db_index=True,
    )
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
        msg += (
            "{wMorale{n: %s {wFood{n: %s {wStarvation Level{n: %s {wPlunder{n: %s\n"
            % (self.morale, self.plunder, self.starvation_level, self.plunder)
        )
        msg += "{wUnits{n:\n"
        from evennia.utils.evtable import EvTable

        table = EvTable(
            "{wID{n",
            "{wCommander{n",
            "{wType{n",
            "{wAmt{n",
            "{wLvl{n",
            "{wEquip{n",
            "{wXP{n",
            width=78,
            border="cells",
        )
        for unit in self.units.all():
            typestr = unit.type.capitalize()
            cmdstr = ""
            if unit.commander:
                cmdstr = "{c%s{n" % unit.commander
            table.add_row(
                unit.id,
                cmdstr,
                typestr,
                unit.quantity,
                unit.level,
                unit.equipment,
                unit.xp,
            )
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
        if player.Dominion.appointments.filter(
            category=Minister.WARFARE, ruler__house=self.owner
        ):
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
        if self.temp_owner and dompc.appointments.filter(
            category=Minister.WARFARE, ruler__house=self.temp_owner
        ):
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
        if player.Dominion.memberships.filter(
            Q(deguilded=False)
            & (
                Q(organization__assets=self.owner)
                | Q(organization__assets=self.temp_owner)
            )
        ):
            return True

    @property
    def pending_orders(self):
        """
        Returns pending orders if they exist.
        """
        return self.orders.filter(complete=False)

    def send_orders(
        self,
        player,
        order_type,
        target_domain=None,
        target_land=None,
        target_character=None,
        action=None,
        action_assist=None,
        assisting=None,
    ):
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
        return self.orders.create(
            type=order_type,
            target_domain=target_domain,
            target_land=target_land,
            target_character=target_character,
            action=action,
            action_assist=action_assist,
            assisting=assisting,
        )

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
            self.general.inform(
                "%s has relieved you from duty as general of army: %s." % (caller, self)
            )
        if general:
            self.general = general.Dominion
            self.save()
            general.inform(
                "%s has set you as the general of army: %s." % (caller, self)
            )
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
            self.temp_owner.inform_owner(
                "%s has retrieved an army that you temporarily controlled: %s."
                % (caller, self)
            )
        self.temp_owner = temp_owner
        self.save()
        if temp_owner:
            temp_owner.inform_owner(
                "%s has given you temporary control of army: %s." % (caller, self)
            )

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
            battle = Battle(
                armies_atk=self,
                armies_def=e_armies,
                week=week,
                pc_atk=atkpc,
                pc_def=defpc,
                atk_domain=self.domain,
                def_domain=tdomain,
            )
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
        percent = float(self.quantity) / target.total_serfs
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
            other_domains = Domain.objects.filter(ruler_id=target.ruler.id).exclude(
                id=target.id
            )
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
                    ruler_id=ruler.id
                )
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

    def __str__(self):
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
        (TRAIN, "Troop Training"),
        (EXPLORE, "Explore territory"),
        (RAID, "Raid Domain"),
        (CONQUER, "Conquer Domain"),
        (ENFORCE_ORDER, "Enforce Order"),
        (BESIEGE, "Besiege Castle"),
        (MARCH, "March"),
        (DEFEND, "Defend"),
        # like killing bandits
        (PATROL, "Patrol"),
        # assisting other armies' orders
        (ASSIST, "Assist"),
        # restoring morale
        (BOLSTER, "Bolster Morale"),
        (EQUIP, "Upgrade Equipment"),
        # using army in a crisis action
        (CRISIS, "Crisis Response"),
    )
    army = models.ForeignKey(
        "Army",
        related_name="orders",
        null=True,
        blank=True,
        db_index=True,
        on_delete=models.CASCADE,
    )
    # for realm PVP and realm offense/defense
    target_domain = models.ForeignKey(
        "Domain",
        related_name="orders",
        null=True,
        blank=True,
        db_index=True,
        on_delete=models.CASCADE,
    )
    # for travel and exploration
    target_land = models.ForeignKey(
        "Land", related_name="orders", null=True, blank=True, on_delete=models.CASCADE
    )
    # an individual's support for training, morale, equipment
    target_character = models.ForeignKey(
        "PlayerOrNpc",
        on_delete=models.SET_NULL,
        related_name="orders",
        blank=True,
        null=True,
        db_index=True,
    )
    # if we're targeting an action or asist. omg skorpins.
    action = models.ForeignKey(
        "PlotAction",
        related_name="orders",
        null=True,
        blank=True,
        db_index=True,
        on_delete=models.CASCADE,
    )
    action_assist = models.ForeignKey(
        "PlotActionAssistant",
        related_name="orders",
        null=True,
        blank=True,
        db_index=True,
        on_delete=models.CASCADE,
    )
    # if we're assisting another army's orders
    assisting = models.ForeignKey(
        "self",
        related_name="assisting_orders",
        null=True,
        blank=True,
        db_index=True,
        on_delete=models.CASCADE,
    )
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
        costs = sum((ob.costs / DIV) + 1 for ob in self.units.all())
        self.coin_cost = costs
        self.save()

    @property
    def troops_sent(self):
        """Returns display of troops being ordered"""
        return ", ".join(
            "%s %s" % (ob.quantity, ob.type) for ob in self.army.units.all()
        )


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
    CARAVEL = unit_constants.CARAVEL

    UNIT_CHOICES = (
        (INFANTRY, "Infantry"),
        (PIKE, "Pike"),
        (CAVALRY, "Cavalry"),
        (ARCHERS, "Archers"),
        (LONGSHIP, "Longship"),
        (SIEGE_WEAPON, "Siege Weapon"),
        (GALLEY, "Galley"),
        (COG, "Cog"),
        (DROMOND, "Dromond"),
        (CARAVEL, "Caravel"),
    )
    # type will be used to derive units and their stats elsewhere
    unit_type = models.PositiveSmallIntegerField(
        choices=UNIT_CHOICES, default=0, blank=0
    )

    class Meta:
        abstract = True


class OrgUnitModifiers(UnitTypeInfo):
    """Model that has modifiers from an org to make a special unit"""

    org = models.ForeignKey(
        "Organization",
        related_name="unit_mods",
        db_index=True,
        on_delete=models.CASCADE,
    )
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

    origin = models.ForeignKey(
        "Organization",
        related_name="units",
        blank=True,
        null=True,
        db_index=True,
        on_delete=models.CASCADE,
    )
    commander = models.ForeignKey(
        "PlayerOrNpc",
        on_delete=models.SET_NULL,
        related_name="units",
        blank=True,
        null=True,
    )
    army = models.ForeignKey(
        "Army",
        related_name="units",
        blank=True,
        null=True,
        db_index=True,
        on_delete=models.CASCADE,
    )
    orders = models.ForeignKey(
        "Orders",
        related_name="units",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        db_index=True,
    )
    quantity = models.PositiveSmallIntegerField(default=1, blank=1)
    level = models.PositiveSmallIntegerField(default=0, blank=0)
    equipment = models.PositiveSmallIntegerField(default=0, blank=0)
    # can go negative, such as when adding new recruits to a unit
    xp = models.SmallIntegerField(default=0, blank=0)
    # if a hostile area has bandits or whatever, we're not part of an army, just that
    hostile_area = models.ForeignKey(
        "HostileArea",
        on_delete=models.SET_NULL,
        related_name="units",
        blank=True,
        null=True,
    )

    def display(self):
        """
        Returns a string representation of this unit's stats.
        """
        cmdstr = ""
        if self.commander:
            cmdstr = "{c%s{n " % self.commander
        msg = "{wID:{n#%s %s{wType{n: %-12s {wAmount{n: %-7s" % (
            self.id,
            cmdstr,
            self.type.capitalize(),
            self.quantity,
        )
        msg += " {wLevel{n: %s {wEquip{n: %s {wXP{n: %s" % (
            self.level,
            self.equipment,
            self.xp,
        )
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
            old_commander.inform(
                "%s has relieved you of command of unit %s." % (caller, self.id)
            )
        if commander:
            self.commander = commander.Dominion
            self.save()
            commander.inform(
                "%s has set you in command of unit %s." % (caller, self.id)
            )
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
        MilitaryUnit.objects.create(
            origin=self.origin,
            army=self.army,
            orders=self.orders,
            quantity=qty,
            level=self.level,
            equipment=self.equipment,
            xp=self.xp,
            hostile_area=self.hostile_area,
            unit_type=self.unit_type,
        )

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
            print(
                "Warning. No food upkeep assigned to <MilitaryUnit - ID: %s>" % self.id
            )
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

    def __str__(self):
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
        self.level = (
            (self.level * self.quantity) + (target.level * target.quantity)
        ) / total
        self.equipment = (
            (self.equipment * self.quantity) + (target.equipment * target.quantity)
        ) / total
        self.quantity = total
        self.xp = ((self.quantity * self.xp) + (target.quantity * target.xp)) / total
        self.save()
        target.delete()

    def gain_xp(self, amount):
        """
        Gain xp, divided among our quantity
        Args:
            amount: int
        """
        gain = int(round(float(amount) / self.quantity))
        # always gain at least 1 xp
        if gain < 1:
            gain = 1
        self.xp += gain
        levelup_cost = self.stats.levelup_cost
        if self.xp > levelup_cost:
            self.xp -= levelup_cost
            self.level += 1
        self.save()


class Domain(CachedPropertiesMixin, SharedMemoryModel):
    """
    A domain owned by a noble house that resides on a particular Land square on
    the map we'll generate. This model contains information specifically to
    the noble's holding, with all the relevant economic data. All of this is
    assumed to be their property, and its income is drawn upon as a weekly
    event. It resides in a specific Land square, but a Land square can hold
    several domains, up to a total area.

    A player may own several different domains, but each should be in a unique
    square. Conquering other domains inside the same Land square should annex
    them into a single domain.
    """

    # 'grid' square where our domain is. More than 1 domain can be on a square
    location = models.ForeignKey(
        "MapLocation",
        on_delete=models.SET_NULL,
        related_name="domains",
        blank=True,
        null=True,
    )
    # The house that rules this domain
    ruler = models.ForeignKey(
        "Ruler",
        on_delete=models.SET_NULL,
        related_name="holdings",
        blank=True,
        null=True,
        db_index=True,
    )
    # cosmetic info
    name = models.CharField(blank=True, null=True, max_length=80)
    desc = models.TextField(blank=True, null=True)
    title = models.CharField(blank=True, null=True, max_length=255)
    destroyed = models.BooleanField(default=False, blank=False)

    # how much of the territory in our land square we control
    from django.core.validators import MaxValueValidator

    area = models.PositiveSmallIntegerField(
        validators=[MaxValueValidator(LAND_SIZE)], default=0, blank=0
    )

    # granaries, food for emergencies, etc
    stored_food = models.PositiveIntegerField(default=0, blank=0)

    # food from other sources - trade, other holdings of player, etc
    # this is currently 'in transit', and will be added to food_stored if it arrives
    shipped_food = models.PositiveIntegerField(default=0, blank=0)

    # percentage out of 100
    tax_rate = models.PositiveSmallIntegerField(default=10, blank=10)

    # our economic resources
    num_mines = models.PositiveSmallIntegerField(default=0, blank=0)
    num_lumber_yards = models.PositiveSmallIntegerField(default=0, blank=0)
    num_mills = models.PositiveSmallIntegerField(default=0, blank=0)
    num_housing = models.PositiveIntegerField(default=0, blank=0)
    num_farms = models.PositiveSmallIntegerField(default=0, blank=0)
    # workers who are not currently employed in a resource
    unassigned_serfs = models.PositiveIntegerField(default=0, blank=0)
    # what proportion of our serfs are slaves and will have no money upkeep
    slave_labor_percentage = models.PositiveSmallIntegerField(default=0, blank=0)
    # workers employed in different buildings
    mining_serfs = models.PositiveSmallIntegerField(default=0, blank=0)
    lumber_serfs = models.PositiveSmallIntegerField(default=0, blank=0)
    farming_serfs = models.PositiveSmallIntegerField(default=0, blank=0)
    mill_serfs = models.PositiveSmallIntegerField(default=0, blank=0)

    # causes mo' problems.
    lawlessness = models.PositiveSmallIntegerField(default=0, blank=0)
    amount_plundered = models.PositiveSmallIntegerField(default=0, blank=0)
    income_modifier = models.PositiveSmallIntegerField(default=100, blank=100)

    @property
    def land(self):
        """Returns land square from our location"""
        if not self.location:
            return None
        return self.location.land

    # All income sources are floats for modifier calculations. We'll convert to int at the end

    @CachedProperty
    def tax_income(self):
        tax = float(self.tax_rate) / 100.0
        if tax > 1.00:
            tax = 1.00
        tax *= float(self.total_serfs)
        if self.ruler:
            vassals = self.ruler.vassals.all()
            for vassal in vassals:
                try:
                    for domain in vassal.holdings.all():
                        amt = domain.liege_taxed_amt
                        tax += amt
                except (AttributeError, TypeError, ValueError):
                    pass
        return tax

    @staticmethod
    def required_worker_mod(buildings, workers):
        """
        Returns what percentage (as a float between 0.0 to 1.0) we have of
        the workers needed to run these number of buildings at full strength.
        """
        req = buildings * SERFS_PER_BUILDING
        # if we have more than enough workers, we're at 100%
        if workers >= req:
            return 1.0
        # percentage of our efficiency
        return workers / req

    def get_resource_income(self, building, workers):
        """Generates base income from resources"""
        base = SILVER_PER_BUILDING * building
        worker_req = self.required_worker_mod(building, workers)
        return base * worker_req

    def _get_mining_income(self):
        base = self.get_resource_income(self.num_mines, self.mining_serfs)
        if self.land:
            base = (base * self.land.mine_mod) / 100.0
        return base

    def _get_lumber_income(self):
        base = self.get_resource_income(self.num_lumber_yards, self.lumber_serfs)
        if self.land:
            base = (base * self.land.lumber_mod) / 100.0
        return base

    def _get_mill_income(self):
        base = self.get_resource_income(self.num_mills, self.mill_serfs)
        return base

    def get_bonus(self, attr):
        """
        Checks bonus of ruler for a given skill
        Args:
            attr: Skill name to check

        Returns:
            A percentage multiplier based on their skill
        """
        try:
            skill_value = self.ruler.ruler_skill(attr)
            skill_value *= BONUS_PER_SKILL_POINT
            return skill_value
        except AttributeError:
            return 0.0

    @CachedProperty
    def total_income(self):
        """
        Returns our total income after all modifiers. All income sources are
        floats, which we'll convert to an int once we're all done.
        """
        from evennia.server.models import ServerConfig

        amount = self.tax_income
        amount += self.mining_income
        amount += self.lumber_income
        amount += self.mill_income
        amount = (amount * self.income_modifier) / 100.0
        global_mod = ServerConfig.objects.conf(
            "GLOBAL_INCOME_MOD", default=DEFAULT_GLOBAL_INCOME_MOD
        )
        try:
            amount += int(amount * global_mod)
        except (TypeError, ValueError):
            print("Error: Improperly Configured GLOBAL_INCOME_MOD: %s" % global_mod)
        try:
            amount += self.ruler.house.get_bonus_income(amount)
        except AttributeError:
            pass
        if self.ruler and self.ruler.castellan:
            bonus = self.get_bonus("income") * amount
            amount += bonus
        # we'll dump the remainder
        return int(amount)

    def _get_liege_tax(self):
        if not self.ruler:
            return 0
        if not self.ruler.liege:
            return 0
        if self.ruler.liege.holdings.all():
            return self.ruler.liege.holdings.first().tax_rate
        return 0

    def worker_cost(self, number):
        """
        Cost of workers, reduced if they are slaves
        """
        if self.slave_labor_percentage > 99:
            return 0
        cost = BASE_WORKER_COST * number
        cost *= (100 - self.slave_labor_percentage) / 100
        if self.ruler and self.ruler.castellan:
            # every point in upkeep skill reduces cost
            reduction = 1.00 + self.get_bonus("upkeep")
            cost /= reduction
        return int(cost)

    @CachedProperty
    def costs(self):
        """
        Costs/upkeep for all of our production.
        """
        costs = 0
        for army in self.armies.all():
            costs += army.costs
        costs += self.worker_cost(self.mining_serfs)
        costs += self.worker_cost(self.lumber_serfs)
        costs += self.worker_cost(self.mill_serfs)
        costs += self.amount_plundered
        costs += self.liege_taxed_amt
        return costs

    def _get_liege_taxed_amt(self):
        if self.liege_taxes:
            amt = self.ruler.liege_taxes
            if amt:
                return amt
            # check if we have a transaction
            try:
                transaction = self.ruler.house.debts.get(category="vassal taxes")
                return transaction.weekly_amount
            except ObjectDoesNotExist:
                amt = (self.total_income * self.liege_taxes) / 100
                self.ruler.house.debts.create(
                    category="vassal taxes",
                    receiver=self.ruler.liege.house,
                    weekly_amount=amt,
                )
                return amt
        return 0

    def reset_expected_tax_payment(self):
        """Sets the weekly amount that will be paid to their liege"""
        amt = (self.total_income * self.liege_taxes) / 100
        if not amt:
            return
        try:
            transaction = self.ruler.house.debts.get(category="vassal taxes")
            if transaction.receiver != self.ruler.liege.house:
                transaction.receiver = self.ruler.liege.house
        except ObjectDoesNotExist:
            transaction = self.ruler.house.debts.create(
                category="vassal taxes",
                receiver=self.ruler.liege.house,
                weekly_amount=amt,
            )
        transaction.weekly_amount = amt
        transaction.save()

    def _get_food_production(self):
        """
        How much food the region produces.
        """
        mod = self.required_worker_mod(self.num_farms, self.farming_serfs)
        amount = (self.num_farms * FOOD_PER_FARM) * mod
        if self.ruler and self.ruler.castellan:
            bonus = self.get_bonus("farming") * amount
            amount += bonus
        return int(amount)

    def _get_food_consumption(self):
        """
        How much food the region consumes from workers. Armies/garrisons will
        draw upon stored food during do_weekly_adjustment.
        """
        return self.total_serfs

    def _get_max_pop(self):
        """
        Maximum population.
        """
        return self.num_housing * POP_PER_HOUSING

    def _get_employed_serfs(self):
        """
        How many serfs are currently working on a field.
        """
        return (
            self.mill_serfs + self.mining_serfs + self.farming_serfs + self.lumber_serfs
        )

    def _get_total_serfs(self):
        """
        Total of all serfs
        """
        return self.employed + self.unassigned_serfs

    def kill_serfs(self, deaths, serf_type=None):
        """
        Whenever we lose serfs, we need to lose some that are employed in some field.
        If serf_type is specified, then we kill serfs who are either 'farming' serfs,
        'mining' serfs, 'mill' serfs, or 'lumber' sefs. Otherwise, we kill whichever
        field has the most employed.
        """
        if serf_type == "farming":
            worker_type = "farming_serfs"
        elif serf_type == "mining":
            worker_type = "mining_serfs"
        elif serf_type == "mill":
            worker_type = "mill_serfs"
        elif serf_type == "lumber":
            worker_type = "lumber_serfs"
        else:
            # if we have more deaths than unemployed serfs
            more_deaths = deaths - self.unassigned_serfs
            if more_deaths < 1:  # only unemployed die
                self.unassigned_serfs -= deaths
                self.save()
                return
            # gotta kill more
            worker_types = [
                "farming_serfs",
                "mining_serfs",
                "mill_serfs",
                "lumber_serfs",
            ]
            # sort it from most to least
            worker_types.sort(key=lambda x: getattr(self, x), reverse=True)
            worker_type = worker_types[0]
            # now we'll kill the remainder after killing unemployed above
            self.unassigned_serfs = 0
            deaths = more_deaths
        num_workers = getattr(self, worker_type, 0)
        if num_workers:
            num_workers -= deaths
        if num_workers < 0:
            num_workers = 0
        setattr(self, worker_type, num_workers)
        self.save()

    def plundered_by(self, army, week):
        """
        An army has successfully pillaged us. Determine the economic impact.
        """
        print("%s plundered during week %s" % (self, week))
        max_pillage = army.size / 10
        pillage = self.total_income
        if pillage > max_pillage:
            pillage = max_pillage
        self.amount_plundered = pillage
        self.lawlessness += 10
        self.save()
        return pillage

    def annex(self, target, week, army):
        """
        Absorbs the target domain into this one. We'll take all buildings/serfs
        from the target, then delete old domain.
        """
        # add stuff from target domain to us
        self.area += target.area
        self.stored_food += target.stored_food
        self.unassigned_serfs += target.unassigned_serfs
        self.mill_serfs += target.mill_serfs
        self.lumber_serfs += target.lumber_serfs
        self.mining_serfs += target.mining_serfs
        self.farming_serfs += target.farming_serfs
        self.num_farms += target.num_farms
        self.num_housing += target.num_housing
        self.num_lumber_yards += target.num_lumber_yards
        self.num_mills += target.num_mills
        self.num_mines += target.num_mines
        for castle in target.castles.all():
            castle.domain = self
            castle.save()
        # now get rid of annexed domain and save changes
        target.fake_delete()
        self.save()
        army.domain = self
        army.save()
        print("%s annexed during week %s" % (self, week))

    def fake_delete(self):
        """
        Makes us an inactive domain without a presence in the world, but kept for
        historical reasons (such as description/name).
        """
        self.destroyed = True
        self.area = 0
        self.stored_food = 0
        self.unassigned_serfs = 0
        self.mill_serfs = 0
        self.lumber_serfs = 0
        self.mining_serfs = 0
        self.farming_serfs = 0
        self.num_farms = 0
        self.num_housing = 0
        self.num_lumber_yards = 0
        self.num_mills = 0
        self.num_mines = 0
        self.castles.clear()
        self.armies.clear()
        self.save()

    def adjust_population(self):
        """
        Increase or decrease population based on our housing and lawlessness.
        """
        base_growth = (BASE_POP_GROWTH * self.total_serfs) + 1
        deaths = 0
        # if we have no food or no room, population cannot grow
        if self.stored_food <= 0 or self.total_serfs >= self.max_pop:
            base_growth = 0
        else:  # bonuses for growth
            # bonus for having a lot of room to grow
            bonus = float(self.max_pop) / self.total_serfs
            if self.ruler and self.ruler.castellan:
                bonus += bonus * self.get_bonus("population")
            bonus = int(bonus) + 1
            base_growth += bonus
        if self.lawlessness > 0:
            # at 100% lawlessness, we have a 5% death rate per week
            deaths = (self.lawlessness * DEATHS_PER_LAWLESS) * self.total_serfs
            deaths = int(deaths) + 1
        adjustment = base_growth - deaths
        if adjustment < 0:
            self.kill_serfs(adjustment)
        else:
            self.unassigned_serfs += adjustment

    food_production = property(_get_food_production)
    food_consumption = property(_get_food_consumption)
    mining_income = property(_get_mining_income)
    lumber_income = property(_get_lumber_income)
    mill_income = property(_get_mill_income)
    max_pop = property(_get_max_pop)
    employed = property(_get_employed_serfs)
    total_serfs = property(_get_total_serfs)
    liege_taxes = property(_get_liege_tax)
    liege_taxed_amt = property(_get_liege_taxed_amt)

    def __str__(self):
        return "%s (#%s)" % (self.name or "Unnamed Domain", self.id)

    def __repr__(self):
        return "<Domain (#%s): %s>" % (self.id, self.name or "Unnamed")

    def do_weekly_adjustment(self, week, report=None, npc=False):
        """
        Determine how much money we're passing up to the ruler of our domain. Make
        all the people and armies of this domain eat their food for the week. Bad
        things will happen if they don't have enough food.
        """
        if npc:
            return self.total_income - self.costs

        # self.harvest_and_feed_the_populace()
        loot = 0
        for army in self.armies.all():
            army.do_weekly_adjustment(week, report)
            if army.plunder:
                loot += army.plunder
                army.plunder = 0
                army.save()
        # self.adjust_population()
        for project in list(self.projects.all()):
            project.advance_project(report)
        total_amount = (self.total_income + loot) - self.costs
        # reset the amount of money that's been plundered from us
        self.amount_plundered = 0
        self.save()
        self.reset_expected_tax_payment()
        return total_amount

    def harvest_and_feed_the_populace(self):
        """Feeds the population and adjusts lawlessness"""
        self.stored_food += self.food_production
        self.stored_food += self.shipped_food
        hunger = self.food_consumption - self.stored_food
        if hunger > 0:
            self.stored_food = 0
            self.lawlessness += 5
            # unless we have a very large population, we'll only lose 1 serf as a penalty
            lost_serfs = hunger / 100 + 1
            self.kill_serfs(lost_serfs)
        else:  # hunger is negative, we have enough food for it
            self.stored_food += hunger

    def display(self):
        """Returns formatted string display for a domain"""
        castellan = None
        liege = "Crownsworn"
        ministers = []
        if self.ruler:
            castellan = self.ruler.castellan
            liege = self.ruler.liege
            ministers = self.ruler.ministers.all()
        mssg = "{wDomain{n: %s\n" % self.name
        mssg += "{wLand{n: %s\n" % self.land
        mssg += "{wHouse{n: %s\n" % str(self.ruler)
        mssg += "{wLiege{n: %s\n" % str(liege)
        mssg += "{wRuler{n: {c%s{n\n" % castellan
        if ministers:
            mssg += "{wMinisters:{n\n"
            for minister in ministers:
                mssg += "  {c%s{n   {wCategory:{n %s  {wTitle:{n %s\n" % (
                    minister.player,
                    minister.get_category_display(),
                    minister.title,
                )
        mssg += "{wDesc{n: %s\n" % self.desc
        mssg += "{wArea{n: %s {wFarms{n: %s {wHousing{n: %s " % (
            self.area,
            self.num_farms,
            self.num_housing,
        )
        mssg += "{wMines{n: %s {wLumber{n: %s {wMills{n: %s\n" % (
            self.num_mines,
            self.num_lumber_yards,
            self.num_mills,
        )
        mssg += "{wTotal serfs{n: %s " % self.total_serfs
        mssg += "{wAssignments: Mines{n: %s {wMills{n: %s " % (
            self.mining_serfs,
            self.mill_serfs,
        )
        mssg += "{wLumber yards:{n %s {wFarms{n: %s\n" % (
            self.lumber_serfs,
            self.farming_serfs,
        )
        mssg += "{wTax Rate{n: %s {wLawlessness{n: %s " % (
            self.tax_rate,
            self.lawlessness,
        )
        mssg += "{wCosts{n: %s {wIncome{n: %s {wLiege's tax rate{n: %s\n" % (
            self.costs,
            self.total_income,
            self.liege_taxes,
        )
        mssg += (
            "{wFood Production{n: %s {wFood Consumption{n: %s {wStored Food{n: %s\n"
            % (self.food_production, self.food_consumption, self.stored_food)
        )
        frame = "=" * 15
        mssg += "\n|w{0} Castles {0}|n".format(frame)
        for castle in self.castles.all():
            mssg += "\n" + castle.display()
        mssg += "\n|w{0} Armies {0}|n".format(frame)
        for army in self.armies.all():
            mssg += "\n" + army.display()
        return mssg

    def clear_cached_properties(self):
        """Clears cached income/cost data"""
        super(Domain, self).clear_cached_properties()
        try:
            self.ruler.house.clear_cached_properties()
        except (AttributeError, ValueError, TypeError):
            pass


class DomainProject(SharedMemoryModel):
    """
    Construction projects with a domain. In general, each should take a week,
    but may come up with ones that would take more.
    """

    # project types
    BUILD_HOUSING = 1
    BUILD_FARMS = 2
    BUILD_MINES = 3
    BUILD_MILLS = 4
    BUILD_DEFENSES = 5
    BUILD_SIEGE_WEAPONS = 6
    MUSTER_TROOPS = 7
    BUILD_TROOP_EQUIPMENT = 9

    PROJECT_CHOICES = (
        (BUILD_HOUSING, "Build Housing"),
        (BUILD_FARMS, "Build Farms"),
        (BUILD_MINES, "Build Mines"),
        (BUILD_MILLS, "Build Mills"),
        (BUILD_DEFENSES, "Build Defenses"),
        (BUILD_SIEGE_WEAPONS, "Build Siege Weapons"),
        (MUSTER_TROOPS, "Muster Troops"),
        (BUILD_TROOP_EQUIPMENT, "Build Troop Equipment"),
    )

    type = models.PositiveSmallIntegerField(
        choices=PROJECT_CHOICES, default=BUILD_HOUSING
    )
    amount = models.PositiveSmallIntegerField(blank=1, default=1)
    unit_type = models.PositiveSmallIntegerField(default=1, blank=1)
    time_remaining = models.PositiveIntegerField(default=1, blank=1)
    domain = models.ForeignKey(
        "Domain",
        related_name="projects",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )
    castle = models.ForeignKey(
        "Castle",
        related_name="projects",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )
    military = models.ForeignKey(
        "Army", related_name="projects", blank=True, null=True, on_delete=models.CASCADE
    )
    unit = models.ForeignKey(
        "MilitaryUnit",
        related_name="projects",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )

    def advance_project(self, report=None, increment=1):
        """Makes progress on a project for a domain"""
        self.time_remaining -= increment
        if self.time_remaining < 1:
            self.finish_project(report)
        self.save()

    def finish_project(self, report=None):
        """
        Does whatever the project set out to do. For muster troops, we'll need to first
        determine if the unit type we're training more of already exists in the army.
        If so, we add to the value, and if not, we create a new unit.
        """
        if self.type == self.BUILD_HOUSING:
            self.domain.num_housing += self.amount
        if self.type == self.BUILD_FARMS:
            self.domain.num_farms += self.amount
        if self.type == self.BUILD_MINES:
            self.domain.num_mines += self.amount
        if self.type == self.BUILD_MILLS:
            self.domain.num_mills += self.amount
        if self.type < self.BUILD_DEFENSES:
            self.domain.save()
        if self.type == self.BUILD_DEFENSES:
            self.castle.level += self.amount
            self.castle.save()
        if self.type == self.MUSTER_TROOPS:
            existing_unit = self.military.find_unit(self.unit_type)
            if existing_unit:
                existing_unit.adjust_readiness(self.amount)
                existing_unit.quantity += self.amount
                existing_unit.save()
            else:
                self.military.units.create(
                    unit_type=self.unit_type, quantity=self.amount
                )
        if self.type == self.TRAIN_TROOPS:
            self.unit.train(self.amount)
        if self.type == self.BUILD_TROOP_EQUIPMENT:
            self.unit.equipment += self.amount
            self.unit.save()
        if report:
            # add a copy of this project's data to the report
            report.add_project_report(self)
        # we're all done. goodbye, cruel world
        self.delete()


class Castle(SharedMemoryModel):
    """
    Castles within a given domain. Although typically we would only have one,
    it's possible a player might have more than one in a Land square by annexing
    multiple domains within a square. Castles will have a defense level that augments
    the strength of any garrison.

    Currently, castles have no upkeep costs. Any costs for their garrison is paid
    by the domain that owns that army.
    """

    MOTTE_AND_BAILEY = 1
    TIMBER_CASTLE = 2
    STONE_CASTLE = 3
    CASTLE_WITH_CURTAIN_WALL = 4
    FORTIFIED_CASTLE = 5
    EPIC_CASTLE = 6

    FORTIFICATION_CHOICES = (
        (MOTTE_AND_BAILEY, "Motte and Bailey"),
        (TIMBER_CASTLE, "Timber Castle"),
        (STONE_CASTLE, "Stone Castle"),
        (CASTLE_WITH_CURTAIN_WALL, "Castle with Curtain Wall"),
        (FORTIFIED_CASTLE, "Fortified Castle"),
        (EPIC_CASTLE, "Epic Castle"),
    )
    level = models.PositiveSmallIntegerField(default=MOTTE_AND_BAILEY)
    domain = models.ForeignKey(
        "Domain",
        related_name="castles",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )
    damage = models.PositiveSmallIntegerField(default=0, blank=0)
    # cosmetic info:
    name = models.CharField(null=True, blank=True, max_length=80)
    desc = models.TextField(null=True, blank=True)

    def display(self):
        """Returns formatted string for a castle's display"""
        msg = "{wName{n: %s {wLevel{n: %s (%s)\n" % (
            self.name,
            self.level,
            self.get_level_display(),
        )
        msg += "{wDescription{n: %s\n" % self.desc
        return msg

    def get_level_display(self):
        """
        Although we have FORTIFICATION_CHOICES defined, we're not actually using
        'choices' for the level field, because we don't want to have a maximum
        set for castle.level. So we're going to override the display method
        that choices normally adds in order to return the string value for the
        maximum for anything over that threshold value.
        """
        for choice in self.FORTIFICATION_CHOICES:
            if self.level == choice[0]:
                return choice[1]
        # if level is too high, return the last element in choices
        return self.FORTIFICATION_CHOICES[-1][1]

    def __str__(self):
        return "%s (#%s)" % (self.name or "Unnamed Castle", self.id)

    def __repr__(self):
        return "<Castle (#%s): %s>" % (self.id, self.name)


class Ruler(SharedMemoryModel):
    """
    This represents the ruling house/entity that controls a domain, along
    with the liege/vassal relationships. The Castellan is a PcOrNpc object
    that may be the ruler of the domain or someone they appointed in their
    place - in either case, they use the skills for governing. The house
    is the AssetOwner that actually owns the domain and gets the incomes
    from it - it's assumed to be an Organization. liege is how we establish
    the liege/vassal relationships between ruler objects.
    """

    # the person who's skills are used to govern the domain
    castellan = models.OneToOneField(
        "PlayerOrNpc", blank=True, null=True, on_delete=models.CASCADE
    )
    # the house that owns the domain
    house = models.OneToOneField(
        "AssetOwner",
        on_delete=models.SET_NULL,
        related_name="estate",
        blank=True,
        null=True,
    )
    # a ruler object that this object owes its alliegance to
    liege = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        related_name="vassals",
        blank=True,
        null=True,
        db_index=True,
    )

    def _get_titles(self):
        return ", ".join(domain.title for domain in self.domains.all())

    titles = property(_get_titles)

    def __str__(self):
        if self.house:
            return str(self.house.owner)
        return str(self.castellan) or "Undefined Ruler (#%s)" % self.id

    def __repr__(self):
        if self.house:
            owner = self.house.owner
        else:
            owner = self.castellan
        return "<Ruler (#%s): %s>" % (self.id, owner)

    def minister_skill(self, attr):
        """
        Given attr, which must be one of the dominion skills defined in PlayerOrNpc, returns an integer which is
        the value of the Minister which corresponds to that category. If there is no Minister or more than 1,
        both of which are errors, we return 0.
        :param attr: str
        :return: int
        """
        try:
            if attr == "population":
                category = Minister.POP
            elif attr == "warfare":
                category = Minister.WARFARE
            elif attr == "farming":
                category = Minister.FARMING
            elif attr == "income":
                category = Minister.INCOME
            elif attr == "loyalty":
                category = Minister.LOYALTY
            elif attr == "upkeep":
                category = Minister.UPKEEP
            else:
                category = Minister.PRODUCTIVITY
            minister = self.ministers.get(category=category)
            return getattr(minister.player, attr)
        except (
            Minister.DoesNotExist,
            Minister.MultipleObjectsReturned,
            AttributeError,
        ):
            return 0

    def ruler_skill(self, attr):
        """
        Returns the DomSkill value of the castellan + his ministers
        :param attr: str
        :return: int
        """
        try:
            return getattr(self.castellan, attr) + self.minister_skill(attr)
        except AttributeError:
            return 0

    @property
    def vassal_taxes(self):
        """Total silver we get from our vassals"""
        if not self.house:
            return 0
        return sum(
            ob.weekly_amount
            for ob in self.house.incomes.filter(category="vassal taxes")
        )

    @property
    def liege_taxes(self):
        """Total silver we pay to our liege"""
        if not self.house:
            return 0
        return sum(
            ob.weekly_amount for ob in self.house.debts.filter(category="vassal taxes")
        )

    def clear_domain_cache(self):
        """Clears cache for all domains under our rule"""
        for domain in self.holdings.all():
            domain.clear_cached_properties()
