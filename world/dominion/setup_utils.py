"""
Utilities to setup the different aspects of Dominion, such
as creating Land squares of random terrain based on a regional
climate, and setup a character's initial domain based on their
social rank.
"""
from world.dominion.models import (Land, PlayerOrNpc, AssetOwner, Organization)
from world.dominion.domain.models import Domain, Ruler
from . import unit_constants
from django.core.exceptions import ObjectDoesNotExist
import random

CAPITALS = [(0, 1),  # Sanctum
            (3, -5),  # Lenosia
            (9, 2),  # Arx
            (3, 7),  # Farhaven
            (12, 2),  # Maelstrom
            ]

org_lockstring = ("edit:rank(2);boot:rank(2);guards:rank(2);withdraw:rank(2)" +
                  ";setrank:rank(2);invite:rank(2);setruler:rank(2);view:rank(10)" +
                  ";command:rank(2);build:rank(2);agents:rank(2)")


def setup_dom_for_player(player):
    if hasattr(player, 'Dominion'):
        # they already have one
        return player.Dominion
    return PlayerOrNpc.objects.create(player=player)


def setup_assets(dompc, amt):
    if hasattr(dompc, 'assets'):
        return
    return AssetOwner.objects.create(player=dompc, vault=amt)


def starting_money(srank):
    try:
        srank = int(srank)
        if srank > 10 or srank < 1:
            raise TypeError
    except TypeError:
        print("Invalid Social rank. Using rank 10 as a default.")
        srank = 10
    val = 11 - srank
    return val * val * val


def get_domain_resources(area):
    """
    Given the size of a domain, returns a dictionary of
    the keys 'mills', 'mines', 'lumber', 'farms', 'housing'
    with appropriate values to be assigned to a domain. We just
    go round robin incrementing the values.
    """

    res_order = ['farms', 'housing', 'mills', 'mines', 'lumber']
    initial = area/5
    area %= 5
    resources = {resource: initial for resource in res_order}
    counter = 0
    while area > 0:
        resource = res_order[counter]
        resources[resource] += 1
        area -= 1
        counter += 1
        if counter >= len(res_order):
            counter = 0
    return resources


def srank_dom_stats(srank, region, name, male=True):
    if srank == 6:
        if male:
            title = "Baron of %s" % region.name
        else:
            title = "Baroness of %s" % region.name
        name = "%s's Barony" % name
        dom_size = 200
        castle_level = 1
    elif srank == 5:
        if male:
            title = "Count of %s" % region.name
        else:
            title = "Countess of %s" % region.name
        name = "%s's Countship" % name
        dom_size = 400
        castle_level = 2
    elif srank == 4:
        if male:
            title = "Marquis of %s" % region.name
        else:
            title = "Marquessa of %s" % region.name
        name = "%s's March" % name
        dom_size = 700
        castle_level = 3
    elif srank == 3:
        if male:
            title = "Duke of %s" % region.name
        else:
            title = "Duchess of %s" % region.name
        name = "%s's Duchy" % name
        dom_size = 1200
        castle_level = 4
    elif srank == 2:
        if male:
            title = "Prince of %s" % region.name
        else:
            title = "Princess of %s" % region.name
        name = "%s's Principality" % name
        dom_size = 2000
        castle_level = 5
    elif srank == 1:
        if male:
            title = "King of %s" % region.name
        else:
            title = "Queen of %s" % region.name
        name = "%s's Kingdom" % name
        dom_size = 5000
        castle_level = 6
    else:
        raise ValueError("Invalid social rank of %s. Aborting." % srank)
    return title, name, dom_size, castle_level


def setup_domain(dompc, region, srank, male=True, ruler=None, liege=None):
    """
    Sets up the domain for a given PlayerOrNpc object passed by
    'dompc'. region must be a Region instance, and srank must be
    an integer between 1 and 6. Ruler should be a defined Ruler
    object with vassals/lieges already set.
    """
    name = str(dompc)
    if not ruler:
        if hasattr(dompc, 'assets'):
            assetowner = dompc.assets
        else:
            assetowner = AssetOwner.objects.create(player=dompc)
        ruler, _ = Ruler.objects.get_or_create(castellan=dompc, house=assetowner, liege=liege)
    else:
        assetowner = ruler.house
    title, name, dom_size, castle_level = srank_dom_stats(srank, region, name, male)
    squares = Land.objects.filter(region_id=region.id)
    squares = [land for land in squares if land.free_area >= dom_size and (land.x_coord, land.y_coord) not in CAPITALS]
    if not squares:
        raise ValueError("No squares that match our minimum land requirement in region.")
    land = random.choice(squares)
    # get a dict of the domain's resources
    resources = get_domain_resources(dom_size)
    location = land.locations.create()
    domain = Domain.objects.create(location=location, ruler=ruler,
                                   name=name, area=dom_size, title=title)
    set_domain_resources(domain, resources)
    armyname = "%s's army" % str(dompc)
    setup_army(domain, srank, armyname, assetowner)
    castle_name = "%s's castle" % str(dompc)
    domain.castles.create(level=castle_level, name=castle_name)
    return domain


def set_domain_resources(domain, resources):
    # resources
    domain.num_farms = resources['farms']
    domain.num_housing = resources['housing']
    domain.num_mills = resources['mills']
    domain.num_mines = resources['mines']
    domain.num_lumber_yards = resources['lumber']
    domain.stored_food = resources['farms'] * 100
    # serfs
    domain.mining_serfs = resources['farms'] * 10
    domain.lumber_serfs = resources['lumber'] * 10
    domain.farming_serfs = resources['farms'] * 10
    domain.mill_serfs = resources['mills'] * 10
    domain.save()


def convert_domain(domain, srank=None, male=None):
    region = domain.land.region
    if not male or not srank:
        char = domain.ruler.castellan.player.char_ob
        if not male:
            male = char.db.gender.lower() == "male"
        if not srank:
            srank = char.db.social_rank
        name = char.key
    else:
        name = str(domain.ruler.castellan)
    title, name, dom_size, castle_level = srank_dom_stats(srank, region, name, male)
    resources = get_domain_resources(dom_size)
    domain.area = dom_size
    set_domain_resources(domain, resources)
    if domain.armies.all():
        aname = domain.armies.all()[0].name
    else:
        aname = "Army of %s." % domain
    setup_army(domain, srank, aname, domain.ruler.house)
    if domain.castles.all():
        castle = domain.castles.all()[0]
        castle.level = castle_level
        castle.save()
            

def setup_army(domain, srank, name, owner, replace=False, setup_armies=True, setup_navy=True):
    """
    Creates an army for a given domain. We determine if the domain is a land or naval
    power and adjust the strength of their army or navy, respectively. If it's a normal
    domain, its naval and land strengths will be normal for its social rank. We can determine
    whether we set up both our army and our navy with the setup_army and setup_navy optional
    arguments.
    
        Args:
            domain: Domain object model
            srank (int): our ruler's social rank, determines our strength
            name (str): Name to give the army
            owner (AssetOwner): The object that owns this army
            replace (bool): Whether we replace existing troops rather than add to them.
            setup_armies (bool): Whether to set up an army.
            setup_navy (bool): Whether to set up a navy
    """
    land_srank = srank
    navy_srank = srank
    # Determine if we should have different navy and land strengths
    # If the Domain's land's region is the Mourning Isles, it's a naval power
    if domain.land.region.name == "Mourning Isles":
        navy_srank -= 1
        land_srank += 1
    # If the Domain is landlocked, it can't have a navy
    elif domain.land.landlocked:
        navy_srank = 11
        land_srank -= 1
    if not setup_armies:
        land_srank = None
    if not setup_navy:
        navy_srank = None
    try:
        army = domain.armies.all()[0]
        if name:
            army.name = name
        army.save()
    except (IndexError, AttributeError):
        army = domain.armies.create(name=name, land=domain.land, owner=owner)
    setup_units(army, land_srank, navy_srank, replace)
    

def setup_land_units(srank):
    """
    Sets up our land forces for an effective social rank. We go through an populate a dictionary
    of constants that represent the IDs of unit types and their quantities. That dict is then
    returned to setup_units for setting the base size of our navy.
    
        Args:
            srank (int): Our effective social rank for determing the size of our army.
            
        Returns:
            A dict of unit IDs to the quanity of those troops.
    """
    INF = unit_constants.INFANTRY
    PIK = unit_constants.PIKE
    CAV = unit_constants.CAVALRY
    ARC = unit_constants.ARCHERS
    units = {}
    # add more units based on srank
    if srank > 6:
        units[INF] = 75
        units[PIK] = 30
        units[CAV] = 15
        units[ARC] = 30
    elif srank == 6:
        units[INF] = 200
        units[PIK] = 70
        units[CAV] = 40
        units[ARC] = 70
    elif srank == 5:
        units[INF] = 375
        units[PIK] = 125
        units[CAV] = 70
        units[ARC] = 125
    elif srank == 4:
        units[INF] = 750
        units[PIK] = 250
        units[CAV] = 125
        units[ARC] = 250
    elif srank == 3:
        units[INF] = 1500
        units[PIK] = 500
        units[CAV] = 250
        units[ARC] = 500
    elif srank == 2:
        units[INF] = 3000
        units[PIK] = 1000
        units[CAV] = 500
        units[ARC] = 1000
    elif srank == 1:
        units[INF] = 5000
        units[PIK] = 1500
        units[CAV] = 1000
        units[ARC] = 1500
    elif srank < 1:
        units[INF] = 10000
        units[PIK] = 3000
        units[CAV] = 2000
        units[ARC] = 3000
    return units


def setup_naval_units(srank):
    """
    Sets up our naval forces for an effective social rank. We go through an populate a dictionary
    of constants that represent the IDs of unit types and their quantities. That dict is then
    returned to setup_units for setting the base size of our navy.
    
        Args:
            srank (int): Our effective social rank for determing the size of our navy.
            
        Returns:
            A dict of unit IDs to the quanity of those ships.
    """
    LS = unit_constants.LONGSHIP
    GAL = unit_constants.GALLEY
    DRO = unit_constants.DROMOND
    units = {}
    if srank == 6:
        units[LS] = 3
    elif srank == 5:
        units[LS] = 3
        units[GAL] = 1
    elif srank == 4:
        units[LS] = 6
        units[GAL] = 2
    elif srank == 3:
        units[LS] = 10
        units[GAL] = 3
        units[DRO] = 1
    elif srank == 2:
        units[LS] = 20
        units[GAL] = 5
        units[DRO] = 2
    elif srank == 1:
        units[LS] = 40
        units[GAL] = 10
        units[DRO] = 3
    elif srank < 1:
        units[LS] = 80
        units[GAL] = 20
        units[DRO] = 4
    return units


def setup_units(army, land_srank=None, naval_srank=None, replace=False):
    """
    Sets up the units for a given army. When this is called, we should already have determined
    if the army belongs to a land or naval power, which sets its land_rank and naval_srank.
    Those values determine the size of its army and navy, respectively.
    
        Args:
            army (Army): The army object that we'll be adding units to.
            land_srank (int): Our effective social rank for determining the size of land forces.
            naval_srank (int): Our social rank for determining the size of naval forces.
            replace (bool): Whether we replace existing troops rather than add to them.
    """
    units = {}
    # get our land and naval unit amounts
    if land_srank is not None:
        units.update(setup_land_units(land_srank))
    if naval_srank is not None:
        units.update(setup_naval_units(naval_srank))
    # populate the army with units
    for unit in units:
        try:
            squad = army.units.get(unit_type=unit)
            if replace:
                squad.quantity = units[unit]
            else:
                squad.quantity += units[unit]
            squad.save()
        except ObjectDoesNotExist:
            army.units.create(unit_type=unit, quantity=units[unit])
    

def setup_family(dompc, family, create_liege=True, create_vassals=True,
                 character=None, srank=None, region=None, liege=None,
                 num_vassals=2):
    """
    Creates a ruler object and either retrieves a house
    organization or creates it. Then we also create similar
    ruler objects for an npc liege (if we should have one),
    and npc vassals (if we should have any). We return a tuple of
    our ruler object, our liege's ruler object or None, and a list
    of vassals' ruler objects.
    """
    vassals = []
    # create a liege only if we don't have one already
    if create_liege and not liege:
        name = "Liege of %s" % family
        liege = setup_ruler(name)
    ruler = setup_ruler(family, dompc, liege)
    if create_vassals:
        vassals = setup_vassals(family, ruler, region, character, srank, num=num_vassals) 
    return ruler, liege, vassals


def setup_vassals(family, ruler, region, character, srank, num=2):
    vassals = []
    for x in range(num):
        name = "Vassal of %s (#%s)" % (family, x + 1)
        vassals.append(setup_ruler(name, liege=ruler))
    for y in range(len(vassals)):
        name = "Vassal #%s of %s" % (y + 1, character)
        setup_dom_for_npc(name, srank=srank + 1, region=region, ruler=vassals[y])
    return vassals


def setup_vassals_for_player(player, num=2):
    dompc = player.Dominion
    char = player.char_ob
    family = char.db.family
    ruler = dompc.ruler
    srank = char.db.social_rank
    region = ruler.holdings.all()[0].land.region
    setup_vassals(family, ruler, region, char, srank, num)


def setup_ruler(name, castellan=None, liege=None):
    """
    We may have to create up to three separate models to fully create
    our ruler object. First is the House as an Organization, then the
    economic holdings of that house (its AssetOwner instance), then the
    ruler object that sets it up as a ruler of a domain, with the liege/vassal
    relationships
    """
    try:
        house_org = Organization.objects.get(name__iexact=name)
    except Organization.DoesNotExist:
        house_org = Organization.objects.create(name=name, lock_storage=org_lockstring)
    if not hasattr(house_org, 'assets'):
        house = AssetOwner.objects.create(organization_owner=house_org)
    else:
        house = house_org.assets
    try:
        ruler = Ruler.objects.get(house_id=house.id)
    except Ruler.DoesNotExist:
        ruler = Ruler.objects.create(house=house)
    if castellan:
        ruler.castellan = castellan
        if not castellan.memberships.filter(organization_id=house_org.id):
            castellan.memberships.create(organization=house_org, rank=1)
    if liege:
        ruler.liege = liege
    ruler.save()
    return ruler


def setup_dom_for_char(character, create_dompc=True, create_assets=True,
                       region=None, srank=None, family=None, liege_domain=None,
                       create_domain=True, create_liege=True, create_vassals=True,
                       num_vassals=2):
    """
    Creates both a PlayerOrNpc instance and an AssetOwner instance for
    a given character. If region is defined and create_domain is True,
    we create a domain for the character. Family is the House that will
    be created (or retrieved, if it already exists) as an owner of the
    domain, while 'fealty' will be the Organization that is set as their
    liege.
    """
    pc = character.player_ob
    if not pc:
        raise TypeError("No player object found for character %s." % character)
    if create_dompc:
        dompc = setup_dom_for_player(pc)
    else:
        dompc = pc.Dominion
    if not srank:
        srank = character.db.social_rank
    if create_assets:
        amt = starting_money(srank)
        setup_assets(dompc, amt)
    # if region is provided, we will setup a domain unless explicitly told not to
    if create_domain and region:       
        if character.db.gender and character.db.gender.lower() == 'male':
            male = True
        else:
            male = False
        if not family:
            family = character.db.family or "%s Family" % character
        # We make vassals if our social rank permits it
        if create_vassals:
            create_vassals = srank < 6
        # if we're setting them as vassals to a house, then we don't create a liege
        liege = None
        if liege_domain:
            create_liege = False
            liege = liege_domain.ruler
        ruler, liege, vassals = setup_family(dompc, family, create_liege=create_liege, create_vassals=create_vassals,
                                             character=character, srank=srank, region=region, liege=liege,
                                             num_vassals=num_vassals)
        # if we created a liege, finish setting them up
        if create_liege:
            name = "%s's Liege" % character
            setup_dom_for_npc(name, srank=srank - 1, region=region, ruler=liege)
        # return the new domain if we were supposed to create one
        return setup_domain(dompc, region, srank, male, ruler)
    else:  # if we're not setting up a new domain, return Dominion object
        return dompc


def setup_dom_for_npc(name, srank, gender='male', region=None, ruler=None,
                      create_domain=True, liege=None):
    """
    If create_domain is True and region is defined, we also create a domain for
    this npc. Otherwise we just setup their PlayerOrNpc model and AssetOwner
    model.
    """
    if gender.strip().lower() != 'male':
        male = False
    else:
        male = True
    domnpc, _ = PlayerOrNpc.objects.get_or_create(npc_name=name)
    setup_assets(domnpc, starting_money(srank))
    if create_domain and region:
        setup_domain(domnpc, region, srank, male, ruler, liege)


def replace_vassal(domain, player, num_vassals=2):
    """
    Replaces the npc ruler of a domain that is someone's vassal, and then
    creates vassals of their own.
    """
    char = player.char_ob
    if not char:
        raise ValueError("Character not found.")
    family = char.db.family
    if not family:
        raise ValueError("Family not defined on character.")
    srank = char.db.social_rank
    if not srank:
        raise ValueError("Social rank undefined")
    ruler = domain.ruler
    assets = domain.ruler.house
    org = assets.organization_owner
    npc = ruler.castellan
    if npc:
        if npc.player:
            raise ValueError("This domain already has a player ruler.")
        npc.npc_name = None
        npc.player = player
        npc.save()
    org.name = family
    org.save()
    # create their vassals
    setup_vassals(family, ruler, domain.land.region, char, srank, num=num_vassals)


REGION_TYPES = ("coast", "temperate", "continental", "tropical")


def get_terrain(land_type):
    terrain = Land.PLAINS
    landlocked = False
    if land_type == "coast":
        types = [Land.COAST, Land.PLAINS, Land.ARCHIPELAGO, Land.LAKES, Land.FOREST, Land.FLOOD_PLAINS, Land.MARSH]   
    elif land_type == "temperate":
        types = [Land.PLAINS, Land.FOREST, Land.GRASSLAND, Land.HILL, Land.MARSH, Land.LAKES, Land.MOUNTAIN]
        landlocked = random.choice((True, False, False))
    elif land_type == "continental":
        types = [Land.TUNDRA, Land.HILL, Land.MOUNTAIN, Land.PLAINS, Land.LAKES, Land.FOREST, Land.GRASSLAND]
        landlocked = random.choice((True, False, False))
    elif land_type == "tropical":
        types = [Land.JUNGLE, Land.OASIS, Land.PLAINS, Land.GRASSLAND, Land.HILL, Land.LAKES, Land.MARSH]
        landlocked = random.choice((True, False, False))
    else:
        return terrain, landlocked
    terrain = random.choice(types)
    return terrain, landlocked


def populate(region, end_x, end_y, region_type):
    region_type = region_type.lower()
    if region_type not in REGION_TYPES:
        raise TypeError("Region-region_type %s not in %s." % (region_type, str(REGION_TYPES)))
    try:
        start_x = region.origin_x_coord
        start_y = region.origin_y_coord
    except AttributeError:
        print ("Invalid object %s passed as region. Cannot populate." % str(region))
        return
    for x in range(start_x, end_x + 1):
        for y in range(start_y, end_y + 1):
            name = "%s (%s, %s)" % (region.name, x, y)
            terrain, landlocked = get_terrain(region_type)
            try:
                Land.objects.get(x_coord=x, y_coord=y)
                # already exists at this x,y, so pass
            except Land.DoesNotExist:
                region.land_set.create(name=name, terrain=terrain, landlocked=landlocked, x_coord=x, y_coord=y)


def update_navies_and_armies(adjust_armies=False, adjust_navies=True, replace=False):
    """
    Script we ran a single time in order to update domains with navies.
    
        Args:
            adjust_armies (bool): Whether we adjust their armies too, or just their navies
            adjust_navies (bool): Whether we should adjust navies.
            replace (bool): Whether we're replacing existing units or incrementing them
    """
    pc_domains = Domain.objects.filter(ruler__house__organization_owner__members__isnull=False).distinct()
    for domain in pc_domains:
        owner = domain.ruler.house
        name = ""  # Do not override existing name
        try:
            srank = domain.ruler.castellan.player.char_ob.db.social_rank
            if not srank or srank < 1 or srank > 6:
                raise ValueError
        except AttributeError:
            raise ValueError("%s does not have valid srank for ruler." % domain)
        setup_army(domain, srank, name, owner, replace=replace, setup_armies=adjust_armies, setup_navy=adjust_navies)
        
        
def do_thrax_script():
    """
    Call our update_navies_and_armies script with appropriate values to set Thrax and others
    with the values we want.
    """
    # call it twice, with different values
    # update navies
    update_navies_and_armies()
    # now update armies
    update_navies_and_armies(replace=True, adjust_armies=True, adjust_navies=False)
