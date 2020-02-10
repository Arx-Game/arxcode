"""
Unit types:

All the stats for different kinds of military units are defined here and
will be used at runtime.
"""
import traceback
from .combat_grid import PositionActor
from random import randint
from . import unit_constants

_UNIT_TYPES = {}


def register_unit(unit_cls):
    """
    Registers decorated class in _UNIT_TYPES

    Args:
        unit_cls: UnitStats class/child class

    Returns:
        unit_cls
    """
    if unit_cls.id not in _UNIT_TYPES:
        _UNIT_TYPES[unit_cls.id] = unit_cls
    return unit_cls


def get_unit_class_by_id(unit_id, unit_model=None):
    """
    Looks up registered units by their ID
    Args:
        unit_id: ID that matches a UnitStats class id attribute
        unit_model: optional MilitaryUnit model passed along for debug info

    Returns:
        UnitStats class or subclass matching ID
    """
    try:
        cls = _UNIT_TYPES[unit_id]
    except KeyError:
        if unit_model:
            print("ERROR: Unit type not found for MilitaryUnit obj #%s!" % unit_model.id)
        print("Attempted Unit class ID was %s. Not found, using Infantry as fallback." % unit_id)
        traceback.print_exc()
        cls = unit_constants.INFANTRY
    return cls


def get_unit_stats(unit_model, grid=None):
    """
    Returns the type of unit class for combat that corresponds
    to a unit's database model instance. Because we don't want to have
    the entire weekly maintenance process that handles all dominion
    commands stop for an exception, we do a lot of handling with default
    values.
    """
    cls = get_unit_class_by_id(unit_model.unit_type, unit_model)
    unit = cls(unit_model, grid)
    return unit


def type_from_str(name_str):
    """
    Gets integer of unit type from a string

        Helper function for end-users entering the name of a unit type
        and retrieving the integer that is used in the database to represent
        it, which is then used for django filters.
    Args:
        name_str:

    Returns:
        int
    """
    cls = cls_from_str(name_str)
    if cls:
        return cls.id
    
    
def cls_from_str(name_str):
    """
    Gets class of unit type from a string

        Helper function for end-users entering the name of a unit type
        and retrieving the class that contains stats for that unit type.
    Args:
        name_str: str

    Returns:
        UnitStats
    """
    name_str = name_str.lower()
    for cls in _UNIT_TYPES.values():
        if cls.name.lower() == name_str:
            return cls
            

def print_unit_names():
    return ", ".join(cls.name for cls in _UNIT_TYPES.values())


class UnitStats(PositionActor):
    """
    Contains all the stats for a military unit.
    """
    id = -1
    name = "Default"
    # silver upkeep costs for 1 of a given unit
    silver_upkeep = 10
    food_upkeep = 1
    hiring_cost = 5
    # how powerful we are in melee combat
    melee_damage = 1
    # how powerful we are at range
    range_damage = 0
    # our defense against attacks
    defense = 0
    # defense against ANY number of attackers. Super powerful
    multi_defense = 0
    storm_damage = 0
    # how much damage each individual in unit can take
    hp = 1
    # if we are a ranged unit, this value is not 0. Otherwise it is 0.
    range = 0
    # the minimum range an enemy must be for us to use our ranged attack
    min_for_range = 1
    # our value in siege
    siege = 0
    movement = 0
    strategic_speed = 0
    # where the unit can be deployed: ground, naval, or flying
    environment = "ground"
    # how much more damage we take from things like dragon fire, spells, catapults, etc
    structure_damage_multiplier = 1
    xp_cost_multiplier = 1

    def __init__(self, dbobj, grid):
        super(UnitStats, self).__init__(grid)
        self.dbobj = dbobj
        self.formation = None
        self.log = None
        # how much damage we've taken
        self.damage = 0
        # how many troops from unit have died
        self.losses = 0
        self.routed = False
        self.destroyed = False
        # the target we are currently trying to engage
        self.target = None
        # whether we are currently storming a castle
        self.storming = False
        # if we know a castle position to storm
        self.storm_targ_pos = None
        # A castle object if we're in it
        self.castle = None
        self.flanking = None
        self.flanked_by = None
        try:
            self.commander = dbobj.commander
            if dbobj.army:
                self.morale = dbobj.army.morale
                self.commander = self.commander or dbobj.army.general
            else:
                self.morale = 80
            self.level = dbobj.level
            self.equipment = dbobj.equipment
            self.type = dbobj.unit_type
            self.quantity = dbobj.quantity
            self.starting_quantity = dbobj.quantity
        except AttributeError:
            print("ERROR: No dbobj for UnitStats found! Using default values.")
            traceback.print_exc()
            self.morale = 0
            self.level = 0
            self.equipment = 0
            self.type = unit_constants.INFANTRY
            self.quantity = 1
            self.starting_quantity = 1
            self.dbobj = None
            self.commander = None
        if dbobj.origin:
            from django.core.exceptions import ObjectDoesNotExist
            try:
                self.name = dbobj.origin.unit_mods.get(unit_type=self.id).name
            except (ObjectDoesNotExist, AttributeError):
                pass
            
    @classmethod
    def display_class_stats(cls):
        """
        Returns a string of stats about this class.
        
            Returns:
                msg (str): Formatted display of this class's stats
        """
        msg = "{wName:{n %s\n" % cls.name
        msg += "{wHiring Cost (military resources){n: %s\n" % cls.hiring_cost
        msg += "{wUpkeep Cost (silver){n: %s\n" % cls.silver_upkeep
        msg += "{wFood Upkeep{n: %s\n" % cls.food_upkeep
        return msg
            
    def _targ_in_range(self):
        if not self.target:
            return False
        return self.check_distance_to_actor(self.target) <= self.range
    targ_in_range = property(_targ_in_range)
    
    def _unit_active(self):
        return not self.routed and not self.destroyed
    active = property(_unit_active)
    
    def _unit_value(self):
        return self.quantity * self.silver_upkeep
    value = property(_unit_value)

    def __str__(self):
        return "%s's %s(%s)" % (str(self.formation), self.name, self.quantity)
   
    def swing(self, target, atk):
        """
        One unit trying to do damage to another. Defense is a representation
        of how much resistance to damage each individual unit has against
        attacks. For that reason, it's limited by the number of attacks the
        unit is actually receiving. multi_defense, however, is an additional
        defense that scales with the number of attackers, representing some
        incredible durability that can ignore small units. Essentially this
        is for dragons, archmages, etc, who are effectively war machines.
        """
        defense = target.defense
        defense += target.defense * target.level
        defense += target.defense * target.equipment
        def_mult = target.quantity
        if self.quantity < def_mult:
            def_mult = self.quantity
        defense *= def_mult
        # usually this will be 0. multi_defense is for dragons, mages, etc
        defense += target.multi_defense * self.quantity
        def_roll = randint(0, defense)
        if target.commander:
            def_roll += def_roll * target.commander.warfare
        if target.castle:
            def_roll += def_roll * target.castle.level
        attack = atk * self.quantity
        attack += atk * self.level
        attack += atk * self.equipment
        # have a floor of half our attack
        atk_roll = randint(attack/2, attack)
        if self.commander:
            atk_roll += atk_roll * self.commander.warfare
        damage = atk_roll - def_roll
        if damage < 0:
            damage = 0
        target.damage += damage
        self.log.info("%s attacked %s. Atk roll: %s Def roll: %s\nDamage:%s" % (
            str(self), str(target), atk_roll, def_roll, damage))
    
    def ranged_attack(self):
        if not self.range:
            return
        if not self.target:
            return
        if not self.targ_in_range:
            return
        self.swing(self.target, self.range_damage)
        
    def melee_attack(self):
        if not self.target:
            return
        if not self.targ_in_range:
            return
        if self.storming:
            self.swing(self.target, self.storm_damage)
        else:
            self.swing(self.target, self.melee_damage)
        self.target.swing(self, self.target.melee_damage)
   
    def advance(self):
        if self.target and not self.targ_in_range:
            self.move_toward_actor(self.target, self.movement)
        elif self.storm_targ_pos:
            try:
                x, y, z = self.storm_targ_pos
                self.move_toward_position(x, y, z, self.movement)
            except (TypeError, ValueError):
                print("ERROR when attempting to move toward castle. storm_targ_pos: %s" % str(self.storm_targ_pos))
        self.log.info("%s has moved. Now at pos: %s" % (self, str(self.position)))
    
    def cleanup(self):
        """
        Apply damage, destroy units/remove them, make units check for rout, check
        for rally.
        """
        if not self.damage:
            return
        hp = self.hp
        hp += self.hp * self.level
        hp += self.hp * self.equipment
        if self.damage >= hp:
            losses = self.damage/hp
            # save remainder
            self.losses += losses
            self.quantity -= losses
            if self.quantity <= 0:
                self.quantity = 0
                self.destroyed = True
                self.log.info("%s has been destroyed." % (str(self)))
                return
            self.damage %= hp
            self.rout_check()
        if self.routed:
            self.rally_check()
        
    def rout_check(self):
        """
        Chance for the unit to rout. Roll 1-100 to beat a difficulty number
        to avoid routing. Difficulty is based on our percentage of losses +
        any morale rating we have below 100. Reduced by 5 per troop level
        and commander level.
        """
        percent_losses = float(self.losses)/float(self.starting_quantity)
        percent_losses = int(percent_losses * 100)
        morale_penalty = 100 - self.morale
        difficulty = percent_losses + morale_penalty
        difficulty -= 5 * self.level
        if self.commander:
            difficulty -= 5 * self.commander.warfare
        if randint(1, 100) < difficulty:
            self.routed = True
    
    def rally_check(self):
        """
        Rallying is based almost entirely on the skill of the commander. It's
        a 1-100 roll trying to reach 100, with the roll being multiplied by
        our commander's level(+1). We add +10 for each level of troop training
        of the unit, as elite units will automatically rally. Yes, this means
        that it is impossible for level 10 or higher units to rout.
        """
        level = 0
        if self.commander:
            level = self.commander.warfare
        # a level 0 or no commander just means roll is unmodified
        level += 1
        roll = randint(1, 100)
        roll *= level
        roll += 10 * self.level
        self.log.info("%s has routed and rolled %s to rally." % (str(self), roll))
        if roll >= 100:
            self.routed = False
    
    def check_target(self):
        if not self.target:
            return
        if self.target.active:
            return self.target
    
    def acquire_target(self, enemy_formation):
        """
        Retrieve a target from the enemy formation based on various
        targeting criteria.
        """
        self.target = enemy_formation.get_target_from_formation_for_attacker(self)

    @property
    def levelup_cost(self):
        current = self.dbobj.level + 1
        return current * current * 50 * self.xp_cost_multiplier


@register_unit
class Infantry(UnitStats):
    id = unit_constants.INFANTRY
    name = "Infantry"
    silver_upkeep = 5
    melee_damage = 3
    storm_damage = 3
    defense = 1
    hp = 30
    movement = 2
    strategic_speed = 2
    hiring_cost = 10


@register_unit
class Pike(UnitStats):
    id = unit_constants.PIKE
    name = "Pike"
    silver_upkeep = 8
    melee_damage = 5
    storm_damage = 3
    defense = 1
    hp = 30
    movement = 2
    strategic_speed = 2
    hiring_cost = 15


@register_unit
class Cavalry(UnitStats):
    id = unit_constants.CAVALRY
    name = "Cavalry"
    silver_upkeep = 15
    melee_damage = 10
    storm_damage = 3
    defense = 3
    hp = 60
    movement = 6
    strategic_speed = 2
    hiring_cost = 30
    xp_cost_multiplier = 2


@register_unit
class Archers(UnitStats):
    id = unit_constants.ARCHERS
    name = "Archers"
    silver_upkeep = 10
    melee_damage = 1
    range_damage = 5
    storm_damage = 3
    defense = 1
    hp = 20
    range = 6
    siege = 5
    movement = 2
    strategic_speed = 2
    hiring_cost = 20
    xp_cost_multiplier = 2


@register_unit
class Longship(UnitStats):
    id = unit_constants.LONGSHIP
    name = "Longships"
    silver_upkeep = 75
    food_upkeep = 20
    movement = 6
    melee_damage = 60
    range_damage = 100
    hp = 500
    environment = "naval"
    strategic_speed = 12
    structure_damage_multiplier = 20
    hiring_cost = 150
    xp_cost_multiplier = 10


@register_unit
class SiegeWeapon(UnitStats):
    id = unit_constants.SIEGE_WEAPON
    name = "Siege Weapon"
    silver_upkeep = 500
    food_upkeep = 20
    movement = 1
    melee_damage = 20
    range_damage = 300
    defense = 10
    hp = 400
    storm_damage = 600
    strategic_speed = 1
    structure_damage_multiplier = 20
    hiring_cost = 1000
    xp_cost_multiplier = 30


@register_unit
class Galley(UnitStats):
    id = unit_constants.GALLEY
    name = "Galleys"
    silver_upkeep = 250
    food_upkeep = 60
    movement = 5
    melee_damage = 240
    range_damage = 400
    hp = 2000
    environment = "naval"
    strategic_speed = 10
    structure_damage_multiplier = 20
    hiring_cost = 500
    xp_cost_multiplier = 50


@register_unit
class Cog(UnitStats):
    id = unit_constants.COG
    name = "Cogs"
    silver_upkeep = 500
    food_upkeep = 120
    movement = 6
    melee_damage = 700
    range_damage = 2000
    hp = 5000
    environment = "naval"
    strategic_speed = 12
    hiring_cost = 1000
    xp_cost_multiplier = 75


@register_unit
class Dromond(UnitStats):
    id = unit_constants.DROMOND
    name = "Dromonds"
    silver_upkeep = 1000
    food_upkeep = 300
    movement = 3
    melee_damage = 2500
    range_damage = 5000
    hp = 20000
    environment = "naval"
    strategic_speed = 8
    structure_damage_multiplier = 20
    hiring_cost = 2000
    xp_cost_multiplier = 100
