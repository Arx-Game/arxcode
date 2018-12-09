"""
Commands for dominion. This will be the interface through which
players interact with the system, as well as commands for staff
to make changes.
"""
from ast import literal_eval

from django.conf import settings
from django.db.models import Q, F

from evennia.objects.models import ObjectDB
from evennia.accounts.models import AccountDB
from evennia.utils.evtable import EvTable

from server.utils.arx_utils import caller_change_field, inform_staff
from commands.base import ArxCommand, ArxPlayerCommand
from server.utils.exceptions import CommandError
from server.utils.prettytable import PrettyTable
from . import setup_utils
from web.character.models import Clue
from world.dominion.models import (Region, Domain, Land, PlayerOrNpc, Army, ClueForOrg, Reputation,
                                   Castle, AssetOwner, MilitaryUnit,
                                   Ruler, Organization, Member, SphereOfInfluence,
                                   InfluenceCategory, Minister, PlotRoom)
from .unit_types import type_from_str
from world.stats_and_skills import do_dice_check

# Constants for Dominion projects
BUILDING_COST = 1000
# cost will be base * 5^(new level)
BASE_CASTLE_COST = 4000


# ---------------------Admin commands-------------------------------------------------

class CmdAdmDomain(ArxPlayerCommand):
    """
    @admin_domain
    Usage:
      @admin_domain
      @admin_domain/create player=region[, social rank]
      @admin_domain/replacevassal receiver=domain_id, numvassals
      @admin_domain/createvassal receiver=liege_domain_id, numvassals
      @admin_domain/transferowner receiver=domain_id
      @admin_domain/transferrule char=domain_id
      @admin_domain/liege domain_id=family
      @admin_domain/list <fealty, eg: 'Velenosa'>
      @admin_domain/list_char player
      @admin_domain/list_land (x,y)
      @admin_domain/view domain_id
      @admin_domain/delete domain_id
      @admin_domain/move domain_id=(x,y)
      @admin_domain/farms domain_id=#
    switches for information/creation/transfer/deletion:
      create - creates a new domain
      npc_create - creates a new domain for an npc
      replacevassal - replaces npc vassal, creates vassals of their own
      transferowner - make character and their family ruler of a domain
      transferrule - Just change who is castellan/acting ruler
      liege - sets the liege of a domain to be given family
      list - all domains for a particular fealty, like Velenosa
      list_land - lists all domains in a given x,y land square
      list_char - lists all domains for a given character name
      view - get stats on a domain
      move - moves domain to new land square if it has room
      delete - destroy a domain
    switches for changing values in a domain:
      name - Domain's name
      title - Title for holder of domain
      desc - description/history of domain
      area - total area of domain
      tax_rate
      slave_labor_percentage
      num_farms - changes the number of farms to value
      num_mines - like farms
      num_mills - like farms
      num_lumber_yards - same
      stored_food - stored food
      farming_serfs
      mine_serfs
      mill_serfs
      lumber_serfs
      unassigned_serfs - serfs not currently working in a building
      amount_plundered - amount stolen from them this week
      income_modifier - default 100 for normal production
    """
    key = "@admin_domain"
    locks = "cmd:perm(Wizards)"
    aliases = ["@admin_domains", "@admdomain", "@admdomains", "@adm_domain", "@adm_domains"]
    help_category = "Dominion"
    
    def func(self):
        caller = self.caller
        if not self.args:
            pcdomains = ", ".join((repr(dom) for dom in Domain.objects.filter(ruler__castellan__isnull=False)))
            caller.msg("{wPlayer domains:{n %s" % pcdomains)
            npcdomains = ", ".join((repr(dom) for dom in Domain.objects.filter(ruler__castellan__player__isnull=True)))
            caller.msg("{wNPC domains:{n %s" % npcdomains)
            return
        if "create" in self.switches:
            # usage: @admin_domain/create player=region[, social rank]
            if not self.rhs:
                caller.msg("Invalid usage. Requires player=region.")
                return
            player = caller.search(self.lhs)
            if not player:
                caller.msg("No player found by name %s." % self.lhs)
                return
            char = player.db.char_ob
            if not char:
                caller.msg("No valid character object for %s." % self.lhs)
                return
            if len(self.rhslist) > 1:
                region = self.rhslist[0]
                srank = self.rhslist[1]
            else:
                region = self.rhs
                srank = char.db.social_rank
            # Get our social rank and region from rhs arguments
            try:
                srank = int(srank)
                region = Region.objects.get(name__iexact=region)
            except ValueError:
                caller.msg("Character's Social rank must be a number. It was %s." % srank)
                return
            except Region.DoesNotExist:
                caller.msg("No region found of name %s." % self.rhslist[0])
                caller.msg("List of regions: %s" % ", ".join(str(region) for region in Region.objects.all()))
                return
            # we will only create an npc liege if our social rank is 4 or higher
            create_liege = srank > 3
            # The player has no Dominion object, so we must create it.
            if not hasattr(player, 'Dominion'):
                caller.msg("Creating a new domain of rank %s for %s." % (srank, char))
                dom = setup_utils.setup_dom_for_char(char, create_dompc=True, create_assets=True,
                                                     region=region, srank=srank, create_liege=create_liege)
            # Has a dominion object, so just set up the domain
            else:
                needs_assets = not hasattr(player.Dominion, 'assets')
                caller.msg("Setting up Dominion for player %s, and creating a new domain of rank %s." % (char, srank))
                dom = setup_utils.setup_dom_for_char(char, create_dompc=False, create_assets=needs_assets,
                                                     region=region, srank=srank, create_liege=create_liege)
            if not dom:
                caller.msg("Dominion failed to create a new domain.")
                return
            if srank == 2:
                try:
                    house = Organization.objects.get(name__iexact="Grayson")
                    if dom.ruler != house.assets.estate:
                        dom.ruler.liege = house.assets.estate
                        dom.ruler.save()
                except Organization.DoesNotExist:
                    caller.msg("Dominion could not find a suitable liege.")
            if srank == 3:
                try:
                    if region.name == "Lyceum":
                        house = Organization.objects.get(name__iexact="Velenosa")
                    elif region.name == "Oathlands":
                        house = Organization.objects.get(name__iexact="Valardin")
                    elif region.name == "Mourning Isles":
                        house = Organization.objects.get(name__iexact="Thrax")
                    elif region.name == "Northlands":
                        house = Organization.objects.get(name__iexact="Redrain")
                    elif region.name == "Crownlands":
                        house = Organization.objects.get(name__iexact="Grayson")
                    else:
                        self.msg("House for that region not found.")
                        return
                    # Make sure we're not the same house
                    if dom.ruler != house.assets.estate:
                        dom.ruler.liege = house.assets.estate
                        dom.ruler.save()
                except (Organization.DoesNotExist, AttributeError):
                    caller.msg("Dominion could not find a suitable liege.")
            caller.msg("New Domain #%s created: %s in land square: %s" % (dom.id, str(dom), str(dom.land)))
            return
        if ("transferowner" in self.switches or "transferrule" in self.switches
                or "replacevassal" in self.switches or "createvassal" in self.switches):
            # usage: @admin_domain/transfer receiver=domain_id
            if not self.rhs or not self.lhs:
                caller.msg("Usage: @admin_domain/transfer receiver=domain's id")
                return
            player = caller.search(self.lhs)
            if not player:
                caller.msg("No player by the name %s." % self.lhs)
                return
            try:
                d_id = int(self.rhslist[0])
                if len(self.rhslist) > 1:
                    num_vassals = int(self.rhslist[1])
                else:
                    num_vassals = 2
                dom = Domain.objects.get(id=d_id)
            except ValueError:
                caller.msg("Domain's id must be a number.")
                return
            except Domain.DoesNotExist:
                caller.msg("No domain by that id number.")
                return
            if "createvassal" in self.switches:
                try:
                    region = dom.land.region
                    setup_utils.setup_dom_for_char(player.char_ob, liege_domain=dom, region=region)
                    caller.msg("Vassal created.")
                except Exception as err:
                    caller.msg(err)
                    import traceback
                    traceback.print_exc()
                return
            if "replacevassal" in self.switches:
                try:
                    setup_utils.replace_vassal(dom, player, num_vassals)
                    caller.msg("%s now ruled by %s." % (dom, player))
                except Exception as err:
                    caller.msg(err)
                    import traceback
                    traceback.print_exc()
                return
            if not hasattr(player, 'Dominion'):
                dompc = setup_utils.setup_dom_for_char(player.db.char_ob)
            else:
                dompc = player.Dominion
            if "transferowner" in self.switches:
                family = player.db.char_ob.db.family
                try:
                    house = Organization.objects.get(name__iexact=family)
                    owner = house.assets
                    # if the organization's AssetOwner has no Ruler object
                    if hasattr(owner, 'estate'):
                        ruler = owner.estate
                    else:
                        ruler = Ruler.objects.create(house=owner, castellan=dompc)
                except Organization.DoesNotExist:
                    ruler = setup_utils.setup_ruler(family, dompc)
                dom.ruler = ruler
                dom.save()
                caller.msg("%s set to rule %s." % (ruler, dom))
                return
            if not dom.ruler:
                dom.ruler.create(castellan=dompc)
            else:
                dom.ruler.castellan = dompc
                dom.ruler.save()
            dom.save()
            caller.msg("Ruler set to be %s." % str(dompc))
            return
        if "list_land" in self.switches:
            x, y = None, None
            try:
                # ast.literal_eval will parse a string into a tuple
                x, y = literal_eval(self.lhs)
                land = Land.objects.get(x_coord=x, y_coord=y)
            # literal_eval gets SyntaxError if it gets no argument, not ValueError
            except (SyntaxError, ValueError):
                caller.msg("Must provide 'x,y' values for a Land square.")
                valid_land = ", ".join(str(land) for land in Land.objects.all())
                caller.msg("Valid land squares: %s" % valid_land)
                return
            except Land.DoesNotExist:
                caller.msg("No land square matches (%s,%s)." % (x, y))
                valid_land = ", ".join(str(land) for land in Land.objects.all())
                caller.msg("Valid land squares: %s" % valid_land)
                return
            doms = ", ".join(str(dom) for dom in land.domains.all())
            caller.msg("Domains at (%s, %s): %s" % (x, y, doms))
            return
        if "list_char" in self.switches:
            player = caller.search(self.args)
            if not player:
                try:
                    dompc = PlayerOrNpc.objects.get(npc_name__iexact=self.args)
                except PlayerOrNpc.DoesNotExist:
                    dompc = None
                except PlayerOrNpc.MultipleObjectsReturned as err:
                    caller.msg("More than one match for %s: %s" % (self.args, err))
                    return
            else:
                if not hasattr(player, 'Dominion'):
                    caller.msg("%s has no Dominion object." % player)
                    return
                dompc = player.Dominion
            if not dompc:
                caller.msg("No character by name: %s" % self.args)
                return
            ruled = "None"
            owned = "None"
            family = None
            if player.db.char_ob and player.db.char_ob.db.family:
                family = player.db.char_ob.db.family
            if hasattr(dompc, 'ruler'):
                ruled = ", ".join(str(ob) for ob in Domain.objects.filter(ruler_id=dompc.ruler.id))
            if player.db.char_ob and player.db.char_ob.db.family:
                owned = ", ".join(str(ob) for ob in Domain.objects.filter(
                    ruler__house__organization_owner__name__iexact=family))
            caller.msg("{wDomains ruled by {c%s{n: %s" % (dompc, ruled))
            caller.msg("{wDomains owned directly by {c%s {wfamily{n: %s" % (family, owned))
            return
        if "list" in self.switches:
            valid_fealty = ("Grayson", "Velenosa", "Redrain", "Valardin", "Thrax")
            fealty = self.args.capitalize()
            if fealty not in valid_fealty:
                caller.msg("Listing by fealty must be in %s, you provided %s." % (valid_fealty, fealty))
                return
            house = Ruler.objects.filter(house__organization_owner__name__iexact=fealty)
            if not house:
                caller.msg("No matches for %s." % fealty)
                return
            house = house[0]
            caller.msg("{wDomains of %s{n" % fealty)
            caller.msg("{wDirect holdings:{n %s" % ", ".join(str(ob) for ob in house.holdings.all()))
            if house.vassals.all():
                caller.msg("{wDirect vassals of %s:{n %s" % (fealty, ", ".join(str(ob) for ob in house.vassals.all())))
            pcdomlist = []
            for pc in AccountDB.objects.filter(Dominion__ruler__isnull=False):
                if pc.db.char_ob and pc.db.char_ob.db.fealty == fealty:
                    if pc.db.char_ob.db.family != fealty:
                        for dom in pc.Dominion.ruler.holdings.all():
                            pcdomlist.append(dom)
            if pcdomlist:
                caller.msg("{wPlayer domains under %s:{n %s" % (fealty, ", ".join(str(ob) for ob in pcdomlist)))
                return
            return
        if "move" in self.switches:
            x, y = None, None
            try:
                dom = Domain.objects.get(id=int(self.lhs))
                x, y = literal_eval(self.rhs)
                land = Land.objects.get(x_coord=x, y_coord=y)
            # Syntax for no self.rhs, Type for no lhs, Value for not for lhs/rhs not being digits
            except (SyntaxError, TypeError, ValueError):
                caller.msg("Usage: @admdomain/move dom_id=(x,y)")
                caller.msg("You entered: %s" % self.args)
                return
            except Domain.DoesNotExist:
                caller.msg("No domain with that id.")
                return
            except Land.DoesNotExist:
                caller.msg("No land with coords (%s,%s)." % (x, y))
                return
            if land.free_area < dom.area:
                caller.msg("%s only has %s free area, need %s." % (str(land), land.free_area, dom.area))
                return
            old = dom.land
            dom.land = land
            dom.save()
            caller.msg("Domain %s moved from %s to %s." % (str(dom), str(old), str(land)))
            return
        # after this point, self.lhs must be the domain
        if not self.lhs:
            caller.msg("Must provide a domain number.")
            return
        try:
            if self.lhs.isdigit():
                dom = Domain.objects.get(id=self.lhs)
            else:
                dom = Domain.objects.get(name__iexact=self.lhs)
        except ValueError:
            caller.msg("Domain must be a number for the domain's ID.")
            return
        except Domain.DoesNotExist:
            caller.msg("No domain by that number or name.")
            return
        if "liege" in self.switches:
            try:
                house = Organization.objects.get(name__iexact=self.rhs)
                estate = house.assets.estate
            except (Organization.DoesNotExist, AttributeError):
                caller.msg("Family %s does not exist or has not been set up properly." % self.rhs)
                return
            caller_change_field(caller, dom.ruler, "liege", estate)
            return
        if "view" in self.switches or not self.switches:
            mssg = dom.display()
            caller.msg(mssg)
            return
        if "delete" in self.switches:
            # this nullifies its values and removes it from play, doesn't fully delete it
            # keeps description/name intact for historical reasons
            dom.fake_delete()
            caller.msg("Domain %s has been removed." % dom.id)
            return
        # after this point, we're matching the switches to fields in the domain
        # to change them
        attr_switches = ("name", "desc", "title", "area", "stored_food", "tax_rate",
                         "num_mines", "num_lumber_yards", "num_mills", "num_housing",
                         "num_farms", "unassigned_serfs", "slave_labor_percentage",
                         "mining_serfs", "lumber_serfs", "farming_serfs", "mill_serfs",
                         "lawlessness", "amount_plundered", "income_modifier")
        switches = [switch for switch in self.switches if switch in attr_switches]
        if not switches:
            caller.msg("All switches must be in the following: %s. You passed %s." % (str(attr_switches),
                                                                                      str(self.switches)))
            return
        if not self.rhs:
            caller.msg("You must pass a value to change the domain field to.")
            return
        # if switch isn't 'name', 'desc', or 'title', val will be a number
        if any(True for ob in switches if ob not in ("name", "desc", "title")):
            try:
                val = int(self.rhs)
            except ValueError:
                caller.msg("Right hand side value must be a number.")
                return
        else:  # switch is 'name', 'desc', or 'title', so val will be a string
            val = self.rhs
        for switch in switches:
            caller_change_field(caller, dom, switch, val)
        dom.save()


class CmdAdmCastle(ArxPlayerCommand):
    """
    @admin_castle
    Usage:
        @admin_castle
        @admin_castle castle_id
        @admin_castle/view castle_id
        @admin_castle/desc castle_id=description
        @admin_castle/name castle_id=name
        @admin_castle/level castle_id=level
        @admin_castle/transfer castle_id=new domain_id
    """
    key = "@admin_castle"
    locks = "cmd:perm(Wizards)"
    help_category = "Dominion"
    aliases = ["@admcastle", "@adm_castle"]

    def func(self):
        caller = self.caller
        if not self.args:
            castles = ", ".join(str(castle) for castle in Castle.objects.all())
            caller.msg("Castles: %s" % castles)
            return
        try:
            castle = Castle.objects.get(id=int(self.lhs))
        except (TypeError, ValueError, Castle.DoesNotExist):
            caller.msg("Could not find a castle for id %s." % self.lhs)
            return
        if not self.switches or "view" in self.switches:
            caller.msg(castle.display())
            return
        if not self.rhs:
            caller.msg("Must specify a right hand side argument for that switch.")
            return
        if "desc" in self.switches:
            caller_change_field(caller, castle, "desc", self.rhs)
            return
        if "name" in self.switches:
            caller_change_field(caller, castle, "name", self.rhs)
            return
        if "level" in self.switches:
            try:
                level = int(self.rhs)
            except (TypeError, ValueError):
                caller.msg("Level must be a number.")
                return
            caller_change_field(caller, castle, "level", level)
            return
        if "transfer" in self.switches:
            try:
                dom = Domain.objects.get(id=int(self.rhs))
            except (TypeError, ValueError, Domain.DoesNotExist):
                caller.msg("Could not find a domain with id of %s" % self.rhs)
                return
            caller_change_field(caller, castle, "domain", dom)
            return


class CmdAdmArmy(ArxPlayerCommand):
    """
    @admin_army
    Usage:
        @admin_army
        @admin_army army_id
        @admin_army/view army_id
        @admin_army/list domain_id
        @admin_army/name army_id=name
        @admin_army/desc army_id=desc
        @admin_army/unit army_id=type,amount,level,equipment
        @admin_army/setservice army_id=domain_id
        @admin_army/owner army_id=organization
        @admin_army/move army_id=(x,y)
    """
    key = "@admin_army"
    locks = "cmd:perm(Wizards)"
    help_category = "Dominion"
    aliases = ["@admarmy", "@adm_army"]

    def func(self):
        caller = self.caller
        if not self.args:
            armies = ", ".join(str(army) for army in Army.objects.all())
            caller.msg("All armies: %s" % armies)
            return
        if "list" in self.switches:
            try:
                dom = Domain.objects.get(id=int(self.args))
                armies = ", ".join(str(army) for army in dom.armies.all())
                caller.msg("All armies for %s: %s" % (str(dom), armies))
                return
            except (Domain.DoesNotExist, TypeError, ValueError):
                caller.msg("@admin_army/list requires the number of a valid domain.")
                return
        # after this point, self.lhs will be our army_id
        try:
            army = Army.objects.get(id=int(self.lhs))
        except (Army.DoesNotExist, TypeError, ValueError):
            caller.msg("Invalid army id of %s." % self.lhs)
            return
        if "view" in self.switches or not self.switches:
            caller.msg(army.display())
            return
        # after this point, require a self.rhs
        if not self.rhs:
            caller.msg("Need an argument after = for 'army_id=<value>'.")
            return
        if "name" in self.switches:
            caller_change_field(caller, army, "name", self.rhs)
            return
        if "desc" in self.switches:
            caller_change_field(caller, army, "desc", self.rhs)
            return
        if "unit" in self.switches:
            u_types = ("infantry", "cavalry", "pike", "archers", "warships", "siege weapons")
            try:
                utype = self.rhslist[0].lower()
                quantity = int(self.rhslist[1])
                level = int(self.rhslist[2])
                equip = int(self.rhslist[3])
            except IndexError:
                caller.msg("Needs four arguments: type of unit, amount of troops, training level, equipment level.")
                caller.msg("Example usage: @admdomain/unit 5=infantry,300,1,1")
                return
            except (TypeError, ValueError):
                caller.msg("Amount of troops, training level, and equipment level must all be numbers.")
                caller.msg("Example usage: @admdomain/unit 5=infantry,300,1,1")
                return
            if utype not in u_types:
                caller.msg("The first argument after = must be one of the following: %s" % str(u_types))
                return
            utype = type_from_str(utype)
            unit = army.find_unit(utype)
            if level < 0 or equip < 0:
                caller.msg("Negative numbers for level or equipment are not supported.")
                return
            if not unit:
                if quantity <= 0:
                    caller.msg("Cannot create a unit without troops.")
                    return
                unit = army.create(unit_type=utype, quantity=quantity, level=level, equipment=equip)
            else:
                if quantity <= 0:
                    unit.delete()
                    caller.msg("Quantity was 0. Unit deleted.")
                    return
                unit.unit_type = utype
                unit.quantity = quantity
                unit.level = level
                unit.equipment = equip
                unit.save()
            caller.msg("Unit created: %s" % unit.display())
            return
        if "owner" in self.switches:
            try:
                owner = AssetOwner.objects.get(organization_owner__name__iexact=self.rhs)
            except (AssetOwner.DoesNotExist, ValueError, TypeError):
                caller.msg("No org/family by name of %s." % self.rhs)
                return
            caller_change_field(caller, army, "owner", owner)
            return
        if "setservice" in self.switches:
            try:
                dom = Domain.objects.get(id=int(self.rhs))
            except (Domain.DoesNotExist, ValueError, TypeError):
                caller.msg("No domain found for id of %s." % self.rhs)
                return
            caller_change_field(caller, army, "domain", dom)
            return
        if "move" in self.switches:
            x, y = None, None
            try:
                x, y = literal_eval(self.rhs)
                land = Land.objects.get(x_coord=x, y_coord=y)
            # Syntax for no self.rhs, Type for no lhs, Value for not for lhs/rhs not being digits
            except (SyntaxError, TypeError, ValueError):
                caller.msg("Usage: @admarmy/move army_id=(x,y)")
                caller.msg("You entered: %s" % self.args)
                return
            except Land.DoesNotExist:
                caller.msg("No land with coords (%s,%s)." % (x, y))
                return
            caller_change_field(caller, army, "land", land)
            return


class CmdAdmAssets(ArxPlayerCommand):
    """
    @admin_assets
    @admin_assets/player <player name>
    @admin_assets/org <org name>
    @admin_assets/setup player
    @admin_assets/money <owner id or name>=money
    @admin_assets/transfer <owner id or name>=<receiver id>, <value>
    @admin_assets/prestige <owner id or name>=<+/-value>/<reason>

    The /player and /org tags display AssetOwner lists
    that correspond to players and organizations, respectively.
    """
    key = "@admin_assets"
    locks = "cmd:perm(Wizards)"
    help_category = "Dominion"
    aliases = ["@admassets", "@admasset", "@adm_asset", "@adm_assets"]

    @staticmethod
    def get_owner(args):
        if args.isdigit():
            owner = AssetOwner.objects.get(id=int(args))
        else:
            player_matches = AssetOwner.objects.filter(player__player__username__iexact=args)
            npc_matches = AssetOwner.objects.filter(player__npc_name__iexact=args)
            org_matches = AssetOwner.objects.filter(organization_owner__name__iexact=args)
            if player_matches:
                owner = player_matches[0]
            elif npc_matches:
                owner = npc_matches[0]
            elif org_matches:
                owner = org_matches[0]
            else:
                raise AssetOwner.DoesNotExist
        return owner

    def print_owner(self):
        """Prints out an asset owner based on args"""
        try:
            if "player" in self.switches:
                owner = AssetOwner.objects.get(player__player__username__iexact=self.args)
            else:
                owner = AssetOwner.objects.get(organization_owner__name__iexact=self.args)
        except (AssetOwner.DoesNotExist, AssetOwner.MultipleObjectsReturned):
            self.msg("No unique match for %s." % self.args)
            other_matches = AssetOwner.objects.filter(Q(player__player__username__icontains=self.args) |
                                                      Q(organization_owner__name__icontains=self.args))
            if other_matches:
                self.msg("Other matches: %s" % ", ".join(repr(ob) for ob in other_matches))
        else:
            self.msg("Owner: %r" % owner)
        
    def func(self):
        caller = self.caller
        if not self.switches and not self.args:
            assets = ", ".join(repr(owner) for owner in AssetOwner.objects.all())
            caller.msg(assets)
            return
        if 'player' in self.switches or 'org' in self.switches:
            return self.print_owner()
        if "setup" in self.switches:
            player = caller.search(self.lhs)
            if not player:
                return
            nodom = not hasattr(player, 'Dominion')
            if not nodom:
                noassets = not hasattr(player.Dominion, 'assets')
            else:
                noassets = True
            setup_utils.setup_dom_for_char(player.db.char_ob, nodom, noassets)
            caller.msg("Dominion initialized for %s. No domain created." % player)
            return
        try:
            owner = self.get_owner(self.lhs)
        except (TypeError, ValueError, AssetOwner.DoesNotExist):
            caller.msg("No assetowner found for %s." % self.lhs)
            return
        if not self.rhs:
            caller.msg(owner.display(), options={'box': True})
            return
        if "money" in self.switches or not self.switches:
            try:
                caller_change_field(caller, owner, "vault", int(self.rhs))
            except (AttributeError, ValueError, TypeError):
                caller.msg("Could not change account to %s." % self.rhs)
            return
        if "transfer" in self.switches:
            tar = None
            try:
                tar, amt = self.rhslist
                tar = self.get_owner(tar)
                amt = int(amt)
                old = owner.vault
                tarold = tar.vault
                owner.vault -= amt
                tar.vault += amt
                owner.save()
                tar.save()
                caller.msg("%s: %s, %s: %s before transfer." % (owner, old, tar, tarold))
                caller.msg("%s: %s, %s: %s after transfer of %s." % (owner, owner.vault, tar, tar.vault, amt))
                return
            except AssetOwner.DoesNotExist:
                caller.msg("Could not find an owner of id %s." % tar)
                return
            except (ValueError, TypeError, AttributeError):
                caller.msg("Invalid arguments of %s." % self.rhs)
                return
        if "prestige" in self.switches:
            rhslist = self.rhs.split("/")
            message = ""
            try:
                value = int(rhslist[0])
            except (ValueError, TypeError):
                caller.msg("Value must be a number.")
                return
            if len(rhslist) == 2:
                message = rhslist[1]
            affected = owner.adjust_prestige(value)
            caller.msg("You have adjusted %s's prestige by %s." % (owner, value))
            for obj in affected:
                obj.msg("%s adjusted %s's prestige by %s for the following reason: %s" % (caller, owner,
                                                                                          value, message))
            # post to a board about it
            from typeclasses.bulletin_board.bboard import BBoard
            board = BBoard.objects.get(db_key="Prestige Changes")
            msg = "{wName:{n %s\n" % str(owner)
            msg += "{wAdjustment:{n %s\n" % value
            msg += "{wGM:{n %s\n" % caller.key.capitalize()
            msg += "{wReason:{n %s\n" % message
            board.bb_post(poster_obj=caller, msg=msg, subject="Prestige Change for %s" % str(owner))


class CmdAdmOrganization(ArxPlayerCommand):
    """
    @admin_org
    Usage:
        @admin_org <org name or number>
        @admin_org/all
        @admin_org/members <org name or number>
        @admin_org/boot <org name or number>=<player>
        @admin_org/add <org name or number>=<player>,<rank>
        @admin_org/setrank <org name or number>=<player>,<rank>
        @admin_org/create <org name>
        @admin_org/setup <org name>
        @admin_org/desc <org name or number>=<desc>
        @admin_org/name <org name or number>=<new name>
        @admin_org/title <orgname or number>=<rank>,<name>
        @admin_org/femaletitle <orgname or number>=<rank>,<name>
        @admin_org/setinfluence <org name or number>=<inf name>,<value>
        @admin_org/cptasks <target org>=<org to copy>
        @admin_org/addclue <org name or number>=<clue ID>

    Allows you to change or control organizations. Orgs can be accessed either by
    their ID number or name. /setup creates a board and channel for them.
    """
    key = "@admin_org"
    locks = "cmd:perm(Wizards)"
    help_category = "Dominion"
    aliases = ["@admorg", "@adm_org"]

    def set_influence(self, org):
        try:
            name, value = self.rhslist[0], int(self.rhslist[1])
        except (TypeError, ValueError, IndexError):
            self.msg("Must provide an influence name and value.")
            return
        try:
            cat = InfluenceCategory.objects.get(name__iexact=name)
        except InfluenceCategory.DoesNotExist:
            self.msg("No InfluenceCategory by that name.")
            self.msg("Valid ones are: %s" % ", ".join(ob.name for ob in InfluenceCategory.objects.all()))
            return
        try:
            sphere = org.spheres.get(category=cat)
        except SphereOfInfluence.DoesNotExist:
            sphere = org.spheres.create(category=cat)
        sphere.rating = value
        sphere.save()
        self.msg("Set %s's rating in %s to be %s." % (org, cat, value))

    def func(self):
        try:
            caller = self.caller
            if not self.args:
                if 'all' in self.switches:
                    orgs = ", ".join(repr(org) for org in Organization.objects.all())
                else:
                    orgs = ", ".join(repr(org) for org in Organization.objects.all()
                                     if org.members.filter(player__player__isnull=False))
                caller.msg("{wOrganizations:{n %s" % orgs)
                return
            if 'create' in self.switches:
                if self.lhs.isdigit():
                    raise CommandError("Organization name must be a name, not a number.")
                from .setup_utils import org_lockstring
                org = Organization.objects.create(name=self.lhs, lock_storage=org_lockstring)
                # create Org's asset owner also
                AssetOwner.objects.create(organization_owner=org)
                caller.msg("Created organization %s." % org)
                return
            org = self.get_by_name_or_id(Organization, self.lhs)
            if not self.switches:
                caller.msg(org.display(show_all=True))
                return
            # already found an existing org
            if 'create' in self.switches:
                caller.msg("Organization %s already exists." % org)
                return
            if 'setup' in self.switches:
                org.setup()
                self.msg("Created board and channel for %s." % org)
                return
            if 'members' in self.switches:
                caller.msg(org.display_members(show_all=True))
                return
            if 'boot' in self.switches:
                try:
                    member = org.members.get(player__player__username__iexact=self.rhs)
                    caller.msg("%s removed from %s." % (str(member), str(org)))
                    member.fake_delete()
                    return
                except Member.DoesNotExist:
                    caller.msg("Could not remove member #%s." % self.rhs)
                    return
            if 'desc' in self.switches:
                caller_change_field(caller, org, "desc", self.rhs)
                return
            if 'name' in self.switches:
                caller_change_field(caller, org, "name", self.rhs)
                return
            if 'add' in self.switches:
                try:
                    if len(self.rhslist) > 1:
                        player = caller.search(self.rhslist[0])
                        rank = int(self.rhslist[1])
                    else:
                        player = caller.search(self.rhs)
                        rank = 10
                    dompc = player.Dominion
                    matches = org.members.filter(player__player_id=player.id)
                    if matches:
                        match = matches[0]
                        if match.deguilded:
                            match.deguilded = False
                            match.rank = rank
                            caller.msg("Readded %s to the org." % match)
                            match.save()
                            match.setup()
                            return
                        caller.msg("%s is already a member." % match)
                        return
                    secret = org.secret
                    member = dompc.memberships.create(organization=org, rank=rank, secret=secret)
                    caller.msg("%s added to %s at rank %s." % (dompc, org, rank))
                    member.setup()
                    return
                except (AttributeError, ValueError, TypeError):
                    caller.msg("Could not add %s. May need to run @admin_assets/setup on them." % self.rhs)
                    return
            if 'title' in self.switches or 'femaletitle' in self.switches:
                male = 'femaletitle' not in self.switches
                try:
                    rank, name = int(self.rhslist[0]), self.rhslist[1]
                except (ValueError, TypeError, IndexError):
                    caller.msg("Invalid usage.")
                    return
                if male:
                    setattr(org, 'rank_%s_male' % rank, name)
                    org.save()
                else:
                    setattr(org, 'rank_%s_female' % rank, name)
                    org.save()
                caller.msg("Rank %s title changed to %s." % (rank, name))
                return
            if 'setrank' in self.switches:
                try:
                    member = Member.objects.get(organization_id=org.id,
                                                player__player__username__iexact=self.rhslist[0])
                    caller_change_field(caller, member, "rank", int(self.rhslist[1]))
                except Member.DoesNotExist:
                    caller.msg("No member found by name of %s." % self.rhslist[0])
                except (ValueError, TypeError, AttributeError, KeyError):
                    caller.msg("Usage: @admorg/set_rank <org> = <player>, <1-10>")
            if 'setinfluence' in self.switches:
                self.set_influence(org)
            if 'cptasks' in self.switches:
                org2 = self.get_by_name_or_id(Organization, self.rhs)
                current_tasks = org.tasks.all()
                tasks = org2.tasks.all().exclude(id__in=current_tasks)
                OrgTaskModel = Organization.tasks.through
                bulk_list = []
                for task in tasks:
                    bulk_list.append(OrgTaskModel(organization=org, task=task))
                OrgTaskModel.objects.bulk_create(bulk_list)
                self.msg("Tasks copied from %s to %s." % (org2, org))
            if 'addclue' in self.switches:
                try:
                    clue = Clue.objects.get(id=self.rhs)
                except Clue.DoesNotExist:
                    self.msg("Could not find a clue by that number.")
                    return
                if clue in org.clues.all():
                    self.msg("%s already knows about %s." % (org, clue))
                    return
                if not clue.allow_sharing:
                    self.msg("%s cannot be shared." % clue)
                    return
                ClueForOrg.objects.create(clue=clue, org=org, revealed_by=caller.roster)
                category = "%s: Clue Added" % org
                share_str = str(clue)
                targ_type = "clue"
                briefing_type = "/briefing"
                text = "%s has shared the %s {w%s{n to {c%s{n. It can now be used in a %s." % (caller.db.char_ob,
                                                                                               targ_type, share_str,
                                                                                               org,
                                                                                               briefing_type)
                org.inform(text, category)
                self.msg("Added clue {w%s{n to {c%s{n" % (clue, org))
        except CommandError as err:
            self.msg(err)


class CmdAdmFamily(ArxPlayerCommand):
    """
    @admin_family
    Usage:
        @admin_family <character>
        @admin_family/addparent <character>=<character parent>
        @admin_family/createparent <character>=<npc name>
        @admin_family/addchild <character>=<character child>
        @admin_family/createchild <character>=<npc name>
        @admin_family/addspouse <character>=<character spouse>
        @admin_family/createspouse <character>=<npc name>
        @admin_family/replacenpc <character>=<player>
        @admin_family/rmchild <character>=<character child>
        @admin_family/rmparent <character>=<character parent>
        @admin_family/rmspouse <character>=<character spouse>
        @admin_family/alive <character>=<True or False>

    Add switches are used if both characters already exist, either
    as players or a Dominion npc. create switches are if only one
    exists, creating a Dominion npc as the child or parent. The
    replacenpc switch allows you to replace a Dominion npc with
    a player.
    """
    key = "@admin_family"
    locks = "cmd:perm(Wizards)"
    help_category = "Dominion"
    aliases = ["@admfamily", "@adm_family"]
    
    def match_player(self, args):
        pcs = PlayerOrNpc.objects.filter(player__username__iexact=args)
        npcs = PlayerOrNpc.objects.filter(npc_name__iexact=args)
        matches = list(set(list(pcs) + list(npcs)))
        if not matches:
            self.caller.msg("No matches found for %s. They may not be added to Dominion." % args)
            return
        if len(matches) > 1:
            self.caller.msg("Too many matches for %s: %s." % (args, ", ".join(str(ob) for ob in matches)))
            return
        return matches[0]
    
    def func(self):
        caller = self.caller
        if not self.args:
            pcs = ", ".join(str(ob) for ob in PlayerOrNpc.objects.all())
            caller.msg("{wPlayer/NPCs in Dominion{n: %s" % pcs)
            return
        char = self.match_player(self.lhs)
        if not char:
            return
        if not self.switches:
            caller.msg("Family of %s:" % char)
            caller.msg(char.display_immediate_family())
            return
        if "createparent" in self.switches or "createchild" in self.switches or "createspouse" in self.switches:
            if PlayerOrNpc.objects.filter(npc_name=self.rhs):
                caller.msg("An npc with that name already exists.")
                return
        if "createparent" in self.switches:
            char.parents.create(npc_name=self.rhs)
            caller.msg("Created a parent named %s for %s." % (self.rhs, char))
            return
        if "createchild" in self.switches:
            char.children.create(npc_name=self.rhs)
            caller.msg("Created a child named %s for %s." % (self.rhs, char))
            return
        if "createspouse" in self.switches:
            char.spouses.create(npc_name=self.rhs)
            caller.msg("Created a spouse named %s for %s." % (self.rhs, char))
            return
        if "replacenpc" in self.switches:
            player = caller.search(self.rhs)
            if hasattr(player, "Dominion"):
                caller.msg("Error. The player %s has Dominion set up." % player)
                caller.msg("This means we'd have two PlayerOrNpc objects, and one of them has to be deleted.")
                caller.msg("Get the administrator to resolve this.")
                return
            if char.player:
                caller.msg("%s already has %s defined as their player. Aborting." % (char, char.player))
                return
            char.player = player
            char.npc_name = None
            char.save()
            caller.msg("Character has been replaced by %s." % player)
            return
        if "alive" in self.switches:
            rhs = self.rhs.lower()
            alive = rhs != 'false'
            char.alive = alive
            char.save()
            caller.msg("%s alive status has been set to %s." % (char, alive))
            return
        tarchar = self.match_player(self.rhs)
        if not tarchar:
            return
        if "addparent" in self.switches:
            char.parents.add(tarchar)
            caller.msg("%s is now a parent of %s." % (tarchar, char))
            return
        if "addchild" in self.switches:
            char.children.add(tarchar)
            caller.msg("%s is now a child of %s." % (tarchar, char))
            return
        if "addspouse" in self.switches:
            char.spouses.add(tarchar)
            caller.msg("%s is now married to %s." % (tarchar, char))
            return
        if "rmparent" in self.switches:
            char.parents.remove(tarchar)
            caller.msg("%s is no longer a parent of %s." % (tarchar, char))
            return
        if "rmchild" in self.switches:
            char.children.remove(tarchar)
            caller.msg("%s has disowned %s. BAM. GET LOST, KID." % (char, tarchar))
            return
        if "rmspouse" in self.switches:
            char.spouses.remove(tarchar)
            caller.msg("%s and %s are no longer married." % (char, tarchar))
            return


class CmdSetRoom(ArxCommand):
    """
    @setroom
    Usage:
        @setroom/barracks <owner name>
        @setroom/market
        @setroom/bank
        @setroom/rumormill
        @setroom/home owner1,owner2,etc=entrance_id,entrance_id2,etc
        @setroom/homeaddowner owner1,owner2,etc
        @setroom/homermowner owner1,owner2,etc
        @setroom/none

    Sets the space you're currently in as being the place where the owner
    can execute their agent commands if it's barracks, or use a number
    of other commandsets based on the switch.

    Setting a home requires you to specify the IDs of the exits that lead
    into that room for it to work properly. @ex each exit to get its id,
    and then use them like '@setroom/home bob=374,375,352'.
    """
    key = "@setroom"
    locks = "cmd:perm(Wizards)"
    help_category = "Dominion"
    allowed_switches = ("barracks", "market", "bank", "rumormill", "home",
                        "homeaddowner", "homermowner", "none")
    MARKETCMD = "commands.cmdsets.market.MarketCmdSet"
    BANKCMD = "commands.cmdsets.bank.BankCmdSet"
    RUMORCMD = "commands.cmdsets.rumor.RumorCmdSet"
    HOMECMD = "commands.cmdsets.home.HomeCmdSet"

    def func(self):
        default_home = ObjectDB.objects.get(id=13)
        caller = self.caller
        if not (set(self.switches) & set(self.allowed_switches)):
            caller.msg("Please select one of the following: %s" % str(self.allowed_switches))
            return
        loc = caller.location
        if not loc or loc.typeclass_path != settings.BASE_ROOM_TYPECLASS:
            caller.msg("You are not in a valid room.")
            return 
        if "barracks" in self.switches:
            if not self.args:
                caller.msg("Valid owners: %s" % ", ".join(str(owner.owner) for owner in AssetOwner.objects.all()))
                return           
            players = AssetOwner.objects.filter(player__player__username__iexact=self.args)
            npcs = AssetOwner.objects.filter(player__npc_name__iexact=self.args)
            orgs = AssetOwner.objects.filter(organization_owner__name__iexact=self.args)
            matches = players | npcs | orgs
            if len(matches) > 1:
                caller.msg("Too many matches: %s" % ", ".join(owner.owner for owner in matches))
                return
            if not matches:
                caller.msg("No matches found. If you entered a player's name, they may not be set up for Dominion.")
                return
            owner = matches[0]
            tagname = str(owner.owner) + "_barracks"
            loc.tags.add(tagname)
            loc.db.barracks_owner = owner.id
            caller.msg("Barracks for %s have been set up in %s." % (owner.owner, loc))
            return
        if "market" in self.switches:
            if "MarketCmdSet" in [ob.key for ob in loc.cmdset.all()]:
                caller.msg("This place is already a market.")
                return
            loc.cmdset.add(self.MARKETCMD, permanent=True)
            loc.tags.add("market")
            caller.msg("%s now has market commands." % loc)
            return
        if "rumormill" in self.switches:
            if "RumorCmdSet" in [ob.key for ob in loc.cmdset.all()]:
                caller.msg("This place is already a rumormill.")
                return
            loc.cmdset.add(self.RUMORCMD, permanent=True)
            loc.tags.add("rumormill")
            caller.msg("%s now has rumor commands." % loc)
            return
        if "none" in self.switches:
            loc.cmdset.delete(self.MARKETCMD)
            loc.cmdset.delete(self.RUMORCMD)
            loc.cmdset.delete(self.BANKCMD)
            loc.cmdset.delete(self.HOMECMD)
            btags = [tag for tag in loc.tags.all() if "barracks" in tag]
            btags.extend(("market", "rumormill", "home", "bank"))
            for tag in btags:
                loc.tags.remove(tag)
                caller.msg("Removed tag %s" % tag)
            loc.attributes.remove("owner")
            if loc.db.entrances:
                for ent in loc.db.entrances:
                    ent.attributes.remove("err_traverse")
                    ent.attributes.remove("success_traverse")
            if loc.db.keylist:
                for char in loc.db.keylist:
                    if char.db.keylist and loc in char.db.keylist:
                        char.db.keylist.remove(loc)
            loc.attributes.remove("keylist")
            caller.msg("Room commands removed.")
            return
        if "bank" in self.switches:
            if "BankCmdSet" in [ob.key for ob in loc.cmdset.all()]:
                caller.msg("This place is already a bank.")
                return
            loc.cmdset.add(self.BANKCMD, permanent=True)
            loc.tags.add("bank")
            caller.msg("%s now has bank commands." % loc)
            return
        if "home" in self.switches or "homeaddowner" in self.switches or "homermowner" in self.switches:
            owners = loc.db.owners or []
            targs = []
            rmkeys = []
            for lhs in self.lhslist:
                player = caller.player.search(lhs)
                if not player:
                    continue
                char = player.db.char_ob
                if not char:
                    caller.msg("No character found.")
                    continue
                targs.append(char)
            if "home" in self.switches:
                # remove keys from all old owners since 'home' overwrites
                rmkeys = [char for char in owners if char not in targs]
            elif "homermowner" in self.switches:
                rmkeys = targs
            if "home" in self.switches or "homeaddowner" in self.switches:
                for char in targs:
                    keys = char.db.keylist or []
                    if loc not in keys:
                        keys.append(loc)
                    char.db.keylist = keys
                    if char not in owners:
                        owners.append(char)
                    if "home" in self.switches:
                        if not char.home or char.home == default_home:
                            char.home = loc
                            char.save()
            for char in rmkeys:
                keys = char.db.keylist or []
                if loc in keys:
                    keys.remove(loc)
                char.db.keylist = keys
                if char in owners:
                    owners.remove(char)
                if char.home == loc:
                    try:
                        # set them to default home square if this was their home
                        home = ObjectDB.objects.get(id=13)
                        char.home = home
                        char.save()
                    except ObjectDB.DoesNotExist:
                        pass
            loc.tags.add("home")
            loc.db.owners = owners
            caller.msg("Owners set to: %s." % ", ".join(str(char) for char in owners))
            if "homeaddowner" in self.switches or "homermowner" in self.switches:
                return
            try:
                id_list = [int(val) for val in self.rhslist]
            except (ValueError, TypeError):
                caller.msg("Some of the rhs failed to convert to numbers.")
                caller.msg("Aborting setup.")
                return
            
            entrances = list(ObjectDB.objects.filter(id__in=id_list))
            valid_entrances = list(ObjectDB.objects.filter(db_destination=loc))
            invalid = [ent for ent in entrances if ent not in valid_entrances]
            if invalid:
                caller.msg("Some of the entrances do not connect to this room: %s" % ", ".join(str(ob)
                                                                                               for ob in invalid))
                caller.msg("Valid entrances are: %s" % ", ".join(str(ob.id) for ob in valid_entrances))
                return
            for ent in entrances:
                ent.locks.add("usekey: perm(builders) or roomkey(%s)" % loc.id)
            if entrances:
                caller.msg("Setup entrances: %s" % ", ".join(str(ent) for ent in entrances))
                old_entrances = loc.db.entrances or []
                old_entrances = [ob for ob in old_entrances if ob not in entrances]
                for ob in old_entrances:
                    ob.locks.add("usekey: perm(builders)")
                if old_entrances:
                    caller.msg("Removed these old exits: %s" % ", ".join(str(ent) for ent in old_entrances))
                loc.db.entrances = entrances
            else:
                if loc.db.entrances:
                    entrances = loc.db.entrances
                    caller.msg("Current entrances are: %s" % ", ".join(str(ob.id) for ob in entrances))
                    caller.msg("Valid entrances are: %s" % ", ".join(str(ob.id) for ob in valid_entrances))
                caller.msg("No entrances set. To change this, run the command again with valid entrances.")
                if not entrances:
                    caller.msg("This room will initialize itself to all entrances the first time +home is used.")
            if "HomeCmdSet" in [ob.key for ob in loc.cmdset.all()]:
                caller.msg("This place is already a home.")
                return
            loc.cmdset.add(self.HOMECMD, permanent=True)
            caller.msg("%s now has home commands." % loc)


# Player/OOC commands for dominion---------------------
class CmdDomain(ArxPlayerCommand):
    """
    @domain
    Usage:
        @domain
        @domain/castellan <domain ID>=<player>
        @domain/minister <domain ID>=<player>,<category>
        @domain/resign <domain ID>
        @domain/strip <domain ID>=<player>
        @domain/title <domain ID>=<minister>,<title>

    Commands to view and control your domain.

    Unfinished
    """
    key = "@domain"
    locks = "cmd:all()"
    help_category = "Dominion"
    aliases = ["@domains"]
    valid_categories = ("farming", "income", "loyalty", "population", "productivity", "upkeep", "warfare")
    minister_dict = dict((key.lower(), value) for (value, key) in Minister.MINISTER_TYPES)

    @property
    def orgs(self):
        return [org for org in self.caller.Dominion.current_orgs if org.access(self.caller, "command")]

    @property
    def org_domains(self):
        return Domain.objects.filter(ruler__house__organization_owner__in=self.orgs)

    @property
    def ruled_domains(self):
        return Domain.objects.filter(ruler__castellan=self.caller.Dominion)

    @property
    def ministered_domains(self):
        return Domain.objects.filter(ruler__ministers__player=self.caller.Dominion)

    @property
    def domains(self):
        org_owned = self.org_domains
        ruled = self.ruled_domains
        minister = self.ministered_domains
        return (org_owned | ruled | minister).distinct()

    def list_domains(self):
        table = EvTable("ID", "Domain", "House", "Castellan", "Ministers", width=78)
        for domain in self.domains:
            table.add_row(domain.id, domain.name, domain.ruler.house, domain.ruler.castellan,
                          ", ".join(str(ob.player) for ob in domain.ruler.ministers.all()))
        self.msg(str(table))

    def check_member(self, domain, player):
        player.refresh_from_db()
        if domain.ruler.house.organization_owner not in player.current_orgs:
            self.msg("%s is not a member of %s." % (player, domain.ruler.house))
            self.msg("current orgs: %s" % ", ".join(ob.name for ob in player.current_orgs
                                                    if self.caller == player.player))
            return False
        return True

    def busy_check(self, dompc):
        if dompc.appointments.all() or getattr(dompc, 'ruler', None):
            self.msg("They are already holding an office, and cannot hold another.")
            return True
        return False

    def func(self):
        if not self.args and not self.switches:
            self.list_domains()
            return
        # for other switches, get our domain from lhs
        try:
            if self.lhs.isdigit():
                dom = self.domains.get(id=self.lhs)
            else:
                dom = self.domains.get(name__iexact=self.lhs)
        except Domain.DoesNotExist:
            self.list_domains()
            self.msg("No domain found by that name or ID.")
            return
        if not self.switches:
            self.msg(dom.display())
            return
        if "castellan" in self.switches:
            if dom not in (self.org_domains | self.ruled_domains).distinct():
                self.msg("You do not have the authority to set a ruler.")
                return
            targ = self.caller.search(self.rhs)
            if not targ:
                return
            dompc = targ.Dominion
            if not self.check_member(dom, dompc):
                return
            if self.busy_check(dompc):
                return
            dom.ruler.castellan = dompc
            dom.ruler.save()
            self.msg("Castellan set to %s." % dompc)
            return
        if "minister" in self.switches:
            if len(self.rhslist) != 2:
                self.msg("Specify both a player and a category.")
                self.msg("Valid categories: %s" % ", ".join(self.valid_categories))
                return
            targ = self.caller.search(self.rhslist[0])
            if not targ:
                return
            if dom not in (self.org_domains | self.ruled_domains).distinct():
                self.msg("You do not have the authority to set a minister.")
                return
            dompc = targ.Dominion
            try:
                category = self.minister_dict[self.rhslist[1]]
            except KeyError:
                self.msg("Valid categories: %s" % ", ".join(self.valid_categories))
                return
            # if not self.check_member(dom, dompc):
            #     return
            if self.busy_check(dompc):
                return
            try:
                minister = dom.ruler.ministers.get(category=category)
                minister.player = dompc
                minister.save()
            except Minister.DoesNotExist:
                dom.ruler.ministers.create(player=dompc, category=category)
            self.msg("%s's Minister of %s set to be %s." % (dom, self.rhslist[1], dompc))
            return
        if "resign" in self.switches:
            if dom in self.ruled_domains:
                dom.ruler.castellan = None
                dom.ruler.save()
                self.msg("You resign as ruler of %s." % dom)
                return
            if dom in self.ministered_domains:
                minister = dom.ruler.ministers.get(player=self.caller.Dominion)
                minister.delete()
                self.msg("You resign as minister of %s." % dom)
                return
            self.msg("You are not a ruler or minister of %s." % dom)
            return
        if "strip" in self.switches or "title" in self.switches:
            if dom not in (self.org_domains | self.ruled_domains).distinct():
                self.msg("You do not have the authority to strip someone of their position or grant a title.")
                return
            if "strip" in self.switches:
                rhs = self.rhs
            else:
                rhs = self.rhslist[0]
            targ = self.caller.search(rhs)
            if not targ:
                return
            dompc = targ.Dominion
            if "strip" in self.switches:
                if dom.ruler.castellan == dompc:
                    self.msg("Removing %s as castellan.")
                    dom.ruler.castellan = None
                    dom.ruler.save()
                    return
                try:
                    minister = dom.ruler.ministers.get(player=dompc)
                    minister.delete()
                    self.msg("You have removed %s as a minister." % dompc)
                except Minister.DoesNotExist:
                    self.msg("They are neither a minister nor castellan for that domain.")
                return
            else:
                try:
                    minister = dom.ruler.ministers.get(player=dompc)
                    minister.title = self.rhslist[1]
                    minister.save()
                    self.msg("Setting title of %s to be: %s" % (dompc, self.rhslist[1]))
                except Minister.DoesNotExist:
                    self.msg("They are neither a minister nor castellan for that domain.")
                return
        self.msg("Invalid switch.")


class CmdArmy(ArxPlayerCommand):
    """
    @army

    Usage:
        @army [army name or #]
        @army/create <org>=<army name>
        @army/dissolve <army name or #>
        @army/rename <army>=<new name>
        @army/desc <army>=<description>
        @army/hire <army>=<unit type>,<quantity>
        @army/combine <destination unit ID>=<unit ID>
        @army/split <unit ID>=<quantity>
        @army/discharge <unit ID>=<quantity>
        @army/transfer <unit ID>=<new army>
        @army/general <army>=<character>
        @army/commander <unit ID>=<character>
        @army/resign
        @army/grant <army>=<character or org>
        @army/recall <army>
        @army/propaganda <character>=<action points in addition to 30 base>
        @army/morale <army>=<action points>
        @army/viewclass <unit type>

    View details of your army or an army-group therein. Create or dissolve
    smaller army-groups using the main army's units. Hire, discharge, combine,
    split or transfer units between army-groups. Assign a character to be general
    of an army-group or commander of a unit. Grant allows a character or org
    to give orders to an army-group until it is recalled. When hiring new units,
    asking someone to generate propaganda first bestows an XP bonus. Keeping
    an army's morale high is essential.
    """
    key = "@army"
    locks = "cmd:all()"
    help_category = "Dominion"
    unit_switches = ("combine", "split", "discharge", "transfer", "commander")

    def display_armies(self):
        caller = self.caller
        if not hasattr(caller, 'Dominion'):
            caller.msg("You have no armies to command.")
            return
        my_orgs = caller.Dominion.current_orgs
        owned = Army.objects.filter(owner__player__player=caller)
        temp_owned = Army.objects.filter(temp_owner__player__player=caller)
        org_owned = Army.objects.filter(owner__organization_owner__in=my_orgs)
        temp_org_owned = Army.objects.filter(temp_owner__organization_owner__in=my_orgs)
        commanded = Army.objects.filter(general__player=caller)
        caller.msg("Armies Owned: %s" % ", ".join(str(ob) for ob in owned))
        caller.msg("Provisional Armies: %s" % ", ".join(str(ob) for ob in temp_owned))
        caller.msg("Org-Owned Armies: %s" % ", ".join(str(ob) for ob in org_owned))
        caller.msg("Provisional Org Armies: %s" % ", ".join(str(ob) for ob in temp_org_owned))
        caller.msg("Armies You Command: %s" % ", ".join(str(ob) for ob in commanded))

    def find_army(self, args):
        try:
            if args.isdigit():
                army = Army.objects.get(id=int(args))
            else:
                army = Army.objects.get(name__iexact=args)
        except (AttributeError, Army.DoesNotExist):
            self.msg("No armies found by that name or number.")
            return
        return army

    def find_unit(self, args):
        try:
            unit = MilitaryUnit.objects.get(id=int(args))
        except (ValueError, TypeError, MilitaryUnit.DoesNotExist):
            self.msg("No units found by that number.")
            return
        if not unit.army.can_change(self.caller):
            self.msg("You do not have permission to change that unit.")
            return
        return unit

    def get_commander(self, args):
        """Fetches a player if available to lead

        Looks for a player and checks to see if they're already general of an
        army or commander of a unit. If they are, sends caller a message and
        returns. Otherwise passes the player onward.

        Args:
            args: a str that is hopefully a player

        Returns:
            A player object
        """
        commander = self.caller.search(args)
        if not commander:
            return
        if commander.Dominion.armies.exists() or commander.Dominion.units.exists():
            self.msg("%s is already in charge of a military force." % commander)
            return
        return commander

    def check_army_has_space(self, army):
        if army.at_capacity:
            self.msg("The army is full. Its units must be transferred to a different army or combined first.")
            return False
        return True
        
    def view_class_stats(self):
        """
        Views stats for a unit class determined from our args.
        """
        from .unit_types import cls_from_str, print_unit_names
        cls = cls_from_str(self.args)
        if not cls:
            self.msg("{wValid types:{n %s" % print_unit_names())
            return
        self.msg(cls.display_class_stats())

    def func(self):
        caller = self.caller
        if "resign" in self.switches:
            # clear() disassociates related objects. The More You Know.
            self.caller.Dominion.armies.clear()
            self.caller.Dominion.units.clear()
            self.msg("You have resigned any military command you held.")
            return
        if "viewclass" in self.switches:
            self.view_class_stats()
            return
        if not self.args:
            self.display_armies()
            return
        if not self.switches:
            army = self.find_army(self.lhs)
            if not army:
                return
            if not army.can_view(caller):
                self.msg("You do not have permission to see that army's details.")
                return
            caller.msg(army.display())
            return
        if "propaganda" in self.switches:
            target = self.caller.search(self.lhs)
            if not target:
                return
            base = 30
            try:
                ap = int(self.rhs)
                if ap < 0:
                    raise ValueError
            except (ValueError, TypeError):
                ap = 0
            if not self.caller.pay_action_points(ap + base):
                self.msg("You do not have enough action points.")
                return
            result = do_dice_check(self.caller.db.char_ob, difficulty=60 - ap, stat="charm", skill="propaganda",
                                   quiet=False)
            if result <= 0:
                self.msg("Your efforts at propaganda were not successful in helping recruitment.")
                return
            prop_dict = target.db.propaganda_mods or {}
            prop_dict[self.caller] = result
            target.db.propaganda_mods = prop_dict
            target.inform("%s has added a result of %s to propaganda for recruitment." % (self.caller, result))
            self.msg("You add a result of %s for propaganda to help %s's recruitment." % (result, target))
            return
        if "create" in self.switches:
            # get owner for army from self.lhs
            dompc = caller.Dominion
            try:
                org = dompc.current_orgs.get(name__iexact=self.lhs)
            except Organization.DoesNotExist:
                self.msg("You are not in an organization by that name.")
                return
            name = self.rhs
            if not name:
                caller.msg("The army needs a name.")
                return
            if not org.access(caller, "army") and not dompc.appointments.filter(category=Minister.WARFARE,
                                                                                ruler__house=org.assets):
                caller.msg("You don't hold rank in %s for building armies." % org)
                return
            # create army
            try:
                domain = org.assets.estate.holdings.first()
            except AttributeError:
                domain = None
            org.assets.armies.create(name=name, domain=domain)
            self.msg("Army created.")
            return
        # checks if the switch is one requiring unit permissions
        if set(self.switches) & set(self.unit_switches):
            unit = self.find_unit(self.lhs)
            if not unit:
                return
            # TODO Maybe check pending orders here, so ppl don't cheat
            if "combine" in self.switches:
                # TODO maybe check a unit property for max quantity
                targ_unit = self.find_unit(self.rhs)
                if not targ_unit:
                    return
                if targ_unit.unit_type != unit.unit_type:
                    self.msg("Unit types must match.")
                    return
                unit.combine_units(targ_unit)
                self.msg("You have combined the units.")
                return
            if "split" in self.switches or "discharge" in self.switches:
                try:
                    qty = int(self.rhs)
                except (TypeError, ValueError):
                    self.msg("Quantity must be a number.")
                    return
                if "discharge" in self.switches:
                    if unit.quantity <= qty:
                        self.msg("Unit %s has been discharged." % unit.id)
                        unit.delete()
                        return
                    unit.quantity -= qty
                    unit.save()
                    self.msg(
                        "%s of unit %s are now discharged from service, and %s remain." % (qty, unit.id, unit.quantity))
                    return
                if not self.check_army_has_space(unit.army):
                    return
                if unit.quantity <= qty:
                    self.msg("You cannot split the entirety of a unit.")
                    return
                unit.split(qty)
                self.msg("Splitting unit %s. %s will go to a new unit and %s remain." % (unit.id, qty, unit.quantity))
                return
            if "transfer" in self.switches:
                army = self.find_army(self.rhs)
                if not army or not army.can_change(caller):
                    return
                if not army.general:
                    self.msg("You may not transfer units to an army with no general.")
                    return
                if not self.check_army_has_space(army):
                    return
                unit.army = army
                unit.save()
                self.msg("Transferred unit %s to army: %s." % (unit.id, army))
                return
            if "commander" in self.switches:
                if not self.rhs:
                    self.msg("You remove the commander from unit %s" % unit.id)
                    unit.change_commander(self.caller, None)
                    return
                commander = self.get_commander(self.rhs)
                if not commander:
                    return
                self.msg("You set %s to command unit %s." % (commander, unit.id))
                unit.change_commander(self.caller, commander)
                return
        army = self.find_army(self.lhs)
        if not army:
            return
        if "morale" in self.switches:
            pass
        if not army.can_change(caller):
            self.msg("You do not meet the required permission check for 'army' for the army's owner.")
            self.msg("Org permissions can be set with org/perm and a minimum rank.")
            return
        if "dissolve" in self.switches:
            if army.units.all():
                self.msg("Army still has units. Must transfer or discharge them.")
                return
            army.delete()
            self.msg("Army disbanded.")
            return
        if "rename" in self.switches or "desc" in self.switches or "name" in self.switches:
            if not self.rhs:
                self.msg("Change it how?")
                return
            if "desc" in self.switches:
                army.desc = self.rhs
            else:
                if len(self.rhs) > 80:
                    self.msg("Too long to be a name.")
                    return
                army.name = self.rhs
            army.save()
            self.msg(army.display())
            return
        if "hire" in self.switches:
            if not army.general:
                self.msg("You may not hire units for an army with no general.")
                return
            if not self.check_army_has_space(army):
                return
            try:
                qty = int(self.rhslist[1])
            except (TypeError, ValueError, IndexError):
                self.msg("Quantity must be a number.")
                return
            # get unit_types cls from the string they specify
            cls = army.get_unit_class(self.rhslist[0])
            if not cls:
                self.msg("Found no unit types for this army called %s." % self.rhslist[0])
                return
            # use the cls to determine the total cost
            cost = cls.hiring_cost * qty
            if self.caller.ndb.army_cost_check != cost:
                self.caller.ndb.army_cost_check = cost
                self.msg("Cost will be %s military resources, use command again to confirm." % cost)
                return
            self.caller.ndb.army_cost_check = None
            if army.owner.military < cost:
                self.msg("%s does not have enough military resources." % army.owner)
                return
            army.owner.military -= cost
            army.owner.save()
            prop_dict = self.caller.db.propaganda_mods or {}
            bonus = sum(prop_dict.values())
            unit = army.units.create(unit_type=cls.id, origin=army.owner.organization_owner, quantity=qty)
            self.msg("Successfully hired %s unit of %s for army: %s." % (self.rhslist[0], qty, army))
            unit.gain_xp(bonus)
            self.msg("Unit %s has gained %s xp divided among its members." % (unit.id, bonus))
            self.caller.attributes.remove("propaganda_mods")
            return
        if "general" in self.switches:
            if not self.rhs:
                self.msg("You remove the general from army: %s" % army)
                army.change_general(self.caller, None)
                return
            general = self.get_commander(self.rhs)
            if not general:
                return
            self.msg("You set %s to be the general of army: %s." % (general, army))
            army.change_general(self.caller, general)
            return
        if "grant" in self.switches:
            if not self.rhs:
                self.msg("Grant temporary control of the army to who?")
                return
            try:
                # looking for this assetowner to be an org first
                temp_owner = Organization.objects.get(name__iexact=self.rhs)
            except Organization.DoesNotExist:
                # if it isn't an org, must be a player
                temp_owner = caller.search(self.rhs)
                if not temp_owner:
                    return
                temp_owner = temp_owner.Dominion
            self.msg("You grant temporary control of army: %s to %s" % (army, temp_owner))
            army.change_temp_owner(self.caller, temp_owner.assets)
            return
        if "recall" in self.switches:
            self.msg("You retrieved your army: %s" % army)
            army.change_temp_owner(self.caller, None)
            return
        self.msg("Invalid switch.")
        

class CmdOrganization(ArxPlayerCommand):
    """
    @org
    Usage:
        @org
        @org <name>
        @org/invite <player>[=<org name>]
        @org/setrank <player>=<rank>[, <org name>]
        @org/setdesc <player>=<desc>[, <org name>]
        @org/boot <player>[=<org name>]
        @org/setruler <player>[=<org name>]
        @org/perm <type>=<rank>[, <org name>]
        @org/motd <message>[=<org name>]
        @org/rankname <name>=<rank>[, <org name>][,male or female]
        @org/accept
        @org/decline
        @org/memberview <player>[=<org name>]
        @org/secret <player>[=<org name>]
        @org/addclue <clue #>[=<org name>]
        @org/briefing <player>/<clue name>[=<org name>]
        @org/addtheory <theory #>[=<org name>]
        @org/theorybriefing <player>/<theory #>[=<org name>]

    Lists the houses/organizations your character is a member
    of. Give the name of an organization for more detailed information.
    @org/accept will accept an invtation to join an organization, while
    @org/decline will decline the invitation.

    @org/perm sets permissions for the organization. Use @org/perm with
    no arguments to see the type of permissions you can set.

    @org/briefing and @org/theorybriefing work off of the list of clues
    and theories associated with the org, which you can see by viewing
    the org information itself with @org <name> -- if, for instance,
    you checked @org Valardin and saw a clue there called 'Honor in
    the Oathlands', you could do @org/briefing <yourname>/Honor in the
    Oathlands=Valardin to learn that clue yourself, or the name of
    another player to brief them on the clue.
    """
    key = "@org"
    locks = "cmd:all()"
    help_category = "Dominion"
    org_locks = ("edit", "boot", "withdraw", "setrank", "invite",
                 "setruler", "view", "guards", "build", "briefing", 
                 "declarations", "army", "informs", "transactions",
                 "viewassets", "memberdesc", "motd", "admin_petition", "view_petition")

    @staticmethod
    def get_org_and_member(caller, myorgs, args):
        """
        Returns an organization and member for caller

        Args:
            caller: Player
            myorgs: Organization
            args: str

        Returns:
            :rtype: (Organization, Member)
        """
        org = myorgs.get(name__iexact=args)
        member = caller.Dominion.memberships.get(organization=org)
        return org, member
    
    def disp_org_locks(self, caller, org):
        table = PrettyTable(["{wPermission{n", "{wRank{n"])
        for lock in self.org_locks:
            lockstr = org.locks.get(lock)
            if lockstr:
                olock = org.locks.get(lock).split(":")
                if len(olock) > 1:
                    olock = olock[1].strip()
            else:
                olock = "rank(%s)" % org.default_access_rank
            table.add_row([lock, olock])
        caller.msg(table, options={'box': True})

    def display_permtypes(self):
        self.msg("Type must be one of the following: %s" % ", ".join(self.org_locks))

    def get_org_from_myorgs(self, myorgs):
        if len(myorgs) == 1:
            org = myorgs[0]
        else:
            try:
                org, _ = self.get_org_and_member(self.caller, myorgs, self.rhs)
            except Organization.DoesNotExist:
                self.msg("You are not a member of any organization named %s." % self.rhs)
                return
        return org

    def get_member_from_player(self, org, player):
        try:
            return player.Dominion.memberships.get(organization=org)
        except Member.DoesNotExist:
            self.msg("%s is not a member of %s." % (player, org))
            return
    
    def func(self):
        caller = self.caller
        myorgs = Organization.objects.filter(Q(members__player__player=caller)
                                             & Q(members__deguilded=False))
        if 'motd' in self.switches:
            return self.set_motd(myorgs)
        if 'briefing' in self.switches or 'theorybriefing' in self.switches:
            org = self.get_org_from_myorgs(myorgs)
            if not org:
                return
            try:
                targname, clue_name_or_theory_id = self.lhs.split("/", 1)
            except (TypeError, ValueError, IndexError):
                self.msg("You must specify the name of a character and a clue. Ex: bob/secrets of haberdashery")
                return
            try:
                tarmember = org.active_members.get(player__player__username__iexact=targname)
            except Member.DoesNotExist:
                self.msg("There is no active member in %s by the name %s." % (org, targname))
                return
            entry = tarmember.player.player.roster
            entry.refresh_from_db()
            if tarmember.player.player.db.char_ob.location != self.caller.db.char_ob.location:
                self.msg("You must be in the same room to brief them.")
                self.msg("Please actually have roleplay about briefing things - "
                         "a 'clue dump' without context is against the rules.")
                return

            def check_clues_or_theories(check_type):
                """
                Helper function for saying if our org has clues/theories to share
                Args:
                    check_type (str): Either "clues" or "theories".

                Returns:
                    True or False, based on whether we have clues or theories.
                """
                if not getattr(org, check_type).all():
                    self.msg("Your organization has no %s to share." % check_type)
                    return False
                return True

            def get_org_clue_or_theory(check_type):
                """
                Helper function to get a theory or clue object from our org.

                Args:
                    check_type (str): Either "clues" or "theories"

                Returns:
                    A Theory or Clue object based on our check_type, or None and send an error message
                    to the caller.
                """
                from web.character.models import Clue, Theory
                plural = "clues" if check_type == "clue" else "theories"
                queryset = getattr(org, plural).all()
                attr = "id"
                try:
                    if clue_name_or_theory_id.isdigit() or check_type == "theory":
                        return queryset.get(id=clue_name_or_theory_id)
                    else:
                        attr = "name"
                        return queryset.get(name__iexact=clue_name_or_theory_id)
                except (Clue.DoesNotExist, Theory.DoesNotExist, ValueError):
                    self.msg("%s does not know of a %s named %s." % (org, check_type, clue_name_or_theory_id))
                    self.msg("Org %s: %s" % (plural, ", ".join(str(getattr(qs_obj, attr)) for qs_obj in queryset)))
                    return

            if "briefing" in self.switches:
                if not check_clues_or_theories("clues"):
                    return
                clue = get_org_clue_or_theory("clue")
                if not clue:
                    return
                cost = (caller.clue_cost / (org.social_modifier + 4)) + 1
                if not org.access(caller, 'briefing'):
                    self.msg("You do not have permissions to do a briefing.")
                    return
                if caller.ndb.briefing_cost_warning != org:
                    caller.ndb.briefing_cost_warning = org
                    self.msg("The cost of the briefing will be %s. Execute the command again to brief them." % cost)
                    return
                caller.ndb.briefing_cost_warning = None
                # check if they don't need this at all
                discovered_clues = entry.clues.all()
                if clue in discovered_clues:
                    self.msg("They cannot learn anything from this briefing.")
                    return
                if not caller.pay_action_points(cost):
                    self.msg("You cannot afford to pay %s action points." % cost)
                    return
                discovery = entry.discover_clue(clue=clue, method="Briefing")
                share_type = "clue"
                cmd_string = "@clue %d" % clue.id
                share_str = "\n" + discovery.display()
            else:
                if not check_clues_or_theories("theories"):
                    return
                theory = get_org_clue_or_theory("theory")
                if not theory:
                    return
                player = entry.player
                if theory in player.known_theories.all():
                    self.msg("They already know that theory.")
                    return
                theory.share_with(player)
                share_type = "theory"
                cmd_string = "@theories %d" % theory.id
                share_str = theory
            text = "You've been briefed and learned a %s. Use {w%s{n to view them: %s" % (share_type, cmd_string,
                                                                                          share_str)
            tarmember.player.player.msg("%s has briefed you on %s's secrets." % (caller.db.char_ob, org))
            tarmember.player.player.inform(text, category="%s briefing" % org)
            self.msg("You have briefed %s on your organization's secrets." % tarmember)
            return
        if 'addclue' in self.switches or 'addtheory' in self.switches:
            from web.character.models import ClueDiscovery
            org = self.get_org_from_myorgs(myorgs)
            if not org:
                return
            if 'addclue' in self.switches:
                try:
                    clue = caller.roster.clues.get(id=self.lhs)
                except (ClueDiscovery.DoesNotExist, ValueError):
                    self.msg("No clue by that number found.")
                    return
                if clue in org.clues.all():
                    self.msg("%s already knows about %s." % (org, clue))
                    return
                if not clue.allow_sharing:
                    self.msg("%s cannot be shared." % clue)
                    return
                cost = 20 - (2 * org.social_modifier)
                if cost < 1:
                    cost = 1
                if caller.ndb.org_clue_cost_warning != org:
                    caller.ndb.org_clue_cost_warning = org
                    self.msg("The cost will be %s. Execute the command again to pay it." % cost)
                    return
                caller.ndb.org_clue_cost_warning = None
                if not caller.pay_action_points(cost):
                    self.msg("You cannot afford to pay %s AP." % cost)
                    return
                ClueForOrg.objects.create(clue=clue, org=org, revealed_by=caller.roster)
                category = "%s: Clue Added" % org
                share_str = str(clue)
                targ_type = "clue"
                briefing_type = "/briefing"
            else:
                from web.character.models import Theory
                try:
                    theories = set(caller.editable_theories.all()) | set(caller.created_theories.all())
                    theory = Theory.objects.filter(id__in=(ob.id for ob in theories)).get(id=self.lhs)
                except (Theory.DoesNotExist, ValueError):
                    self.msg("No theory by that ID found.")
                    return
                if theory in org.theories.all():
                    self.msg("%s already knows about %s." % (org, theory))
                    return
                org.theories.add(theory)
                category = "%s: Theory Added" % theory
                share_str = "%s (#%s)" % (theory, theory.id)
                targ_type = "theory"
                briefing_type = "/theorybriefing"
            text = "%s has shared the %s {w%s{n to {c%s{n. It can now be used in a %s." % (caller.db.char_ob,
                                                                                           targ_type, share_str, org,
                                                                                           briefing_type)
            org.inform(text, category)
            return
        if 'accept' in self.switches:
            org = caller.ndb.orginvite
            if not org:
                caller.msg("You have no current invitations.")
                return
            if org in myorgs:
                caller.msg("You are already a member.")
                caller.ndb.orginvite = None
                return

            for alt in caller.roster.alts:
                altorgs = Organization.objects.filter(Q(members__player__player=alt.player)
                                                      & Q(members__deguilded=False))
                if org in altorgs:
                    inform_staff("{r%s has joined %s, but their alt %s is already a member.{n" % (caller, org, alt))

            # check if they were previously booted out, then we just have them rejoin
            try:
                member = caller.Dominion.memberships.get(Q(deguilded=True)
                                                         & Q(organization=org))
                member.deguilded = False
                member.rank = 10
                member.save()
            except Member.DoesNotExist:
                secret = org.secret
                member = caller.Dominion.memberships.create(organization=org, secret=secret)
            try:
                if org.category != "noble" or member.rank < 5:
                    caller.Dominion.reputations.get(organization=org).wipe_favor()
            except Reputation.DoesNotExist:
                pass
            caller.msg("You have joined %s." % org.name)
            org.msg("%s has joined %s." % (caller, org.name))
            inform_staff("%s has joined {c%s{n." % (caller, org))
            member.setup()
            caller.ndb.orginvite = None
            return
        if 'decline' in self.switches:
            org = caller.ndb.orginvite
            if not org:
                caller.msg("You have no current invitations.")
                return
            caller.msg("You have declined the invitation to join %s." % org.name)
            caller.ndb.orginvite = None
            return
        if not self.args:
            if not myorgs:
                caller.msg("You are not a member of any organizations.")
                return
            if len(myorgs) == 1:
                if "perm" in self.switches:
                    self.disp_org_locks(caller, myorgs[0])
                    return
                member = caller.Dominion.memberships.get(organization=myorgs[0])
                display_clues = myorgs[0].access(caller, "briefing") or caller.check_permstring("builders")
                caller.msg(myorgs[0].display(member, display_clues=display_clues), options={'box': True})
                return
            caller.msg("Your organizations: %s" % ", ".join(org.name for org in myorgs))
            return
        if not self.switches:
            try:
                org, member = self.get_org_and_member(caller, myorgs, self.lhs)
                display_clues = org.access(caller, "briefing") or caller.check_permstring("builders")
                caller.msg(org.display(member, display_clues=display_clues), options={'box': True})
                return
            except Organization.DoesNotExist:
                caller.msg("You are not a member of any organization named %s." % self.lhs)
                return
        player = None
        if not ('perm' in self.switches or 'rankname' in self.switches or 'addclue' in self.switches):
            player = caller.search(self.lhs)
            if not player:
                return
        if 'setdesc' in self.switches:
            if len(myorgs) < 2:
                # if they supplied the org even though they don't have to
                rhs = self.rhs
                if len(self.rhslist) > 1:
                    rhs = self.rhslist[0]
                new_desc = rhs or ""
                org = myorgs[0]
            else:
                if len(self.rhslist) < 2:
                    caller.msg("You belong to more than one organization, so must supply both rank number and" +
                               " the organization name.")
                    return
                try:
                    org, member = self.get_org_and_member(caller, myorgs, self.rhslist[1])
                    new_desc = self.rhslist[0] or ""
                except Organization.DoesNotExist:
                    caller.msg("You are not a member of any organization named %s." % self.rhslist[1])
                    return
                except (ValueError, TypeError, AttributeError, KeyError):
                    caller.msg("Invalid syntax. @org/memberdesc player=desc,orgname")
                    return
            if not org.access(caller, 'memberdesc'):
                caller.msg("You do not have permission to set member descriptions.")
                return
            tarmember = self.get_member_from_player(org, player)
            if not tarmember:
                caller.msg("They are not a member of the organization.")
                return
            tarmember.desc = new_desc
            tarmember.save()
            if new_desc:
                caller.msg("%s has had their org desc set to '%s'" % (player, new_desc))
            else:
                caller.msg("%s has had their org desc cleared." % player)
            return
        if 'setrank' in self.switches or 'perm' in self.switches or 'rankname' in self.switches:
            if not self.rhs:
                if 'perm' in self.switches:
                    try:
                        org, member = self.get_org_and_member(caller, myorgs, self.lhs)
                        self.disp_org_locks(caller, org)
                        return
                    except Organization.DoesNotExist:
                        pass
                    self.display_permtypes()
                    return
                caller.msg("You must supply a rank number.")
                return
            if len(myorgs) < 2:
                # if they supplied the org even though they don't have to
                rhs = self.rhs
                if len(self.rhslist) > 1:
                    rhs = self.rhslist[0]
                if not self.rhs.isdigit():
                    caller.msg("Rank must be a number.")
                    return
                rank = int(rhs)
                org = myorgs[0]
                member = caller.Dominion.memberships.get(organization=org)
            else:
                if len(self.rhslist) < 2:
                    caller.msg("You belong to more than one organization, so must supply both rank number and" +
                               " the organization name.")
                    return
                try:
                    org, member = self.get_org_and_member(caller, myorgs, self.rhslist[1])
                    rank = int(self.rhslist[0])
                except Organization.DoesNotExist:
                    caller.msg("You are not a member of any organization named %s." % self.rhslist[1])
                    return
                except (ValueError, TypeError, AttributeError, KeyError):
                    caller.msg("Invalid syntax. @org/setrank player=rank,orgname")
                    return
            if rank < 1 or rank > 10:
                caller.msg("Rank must be between 1 and 10.")
                return
            # setting permissions
            if 'perm' in self.switches:
                ltype = self.lhs.lower() if self.lhs else ""
                if ltype not in self.org_locks:
                    self.display_permtypes()
                    return
                if not org.access(caller, 'edit'):
                    caller.msg("You do not have permission to edit permissions.")
                    return
                org.locks.add("%s:rank(%s)" % (ltype, rank))
                org.save()
                caller.msg("Permission %s set to require rank %s or higher." % (ltype, rank))
                return
            if 'rankname' in self.switches:
                rankname = self.lhs
                if not org.access(caller, 'edit'):
                    caller.msg("You do not have permission to edit rank names.")
                    return
                maleonly = femaleonly = False
                if len(self.rhslist) == 3:
                    if self.rhslist[2].lower() == "male":
                        maleonly = True
                    elif self.rhslist[2].lower() == "female":
                        femaleonly = True
                if not femaleonly:
                    setattr(org, "rank_%s_male" % rank, rankname)
                    caller.msg("Title for rank %s male characters set to: %s" % (rank, rankname))
                if not maleonly:
                    setattr(org, "rank_%s_female" % rank, rankname)
                    caller.msg("Title for rank %s female characters set to: %s" % (rank, rankname))
                org.save()
                return
            # 'setrank' now
            if not org.access(caller, 'setrank'):
                caller.msg("You do not have permission to change ranks.")
                return
            # this check also prevents promoting yourself
            if rank < member.rank:
                caller.msg("You cannot set someone to be higher rank than yourself.")
                return
            tarmember = self.get_member_from_player(org, player)
            if not tarmember:
                return
            # can demote yourself, but otherwise only people lower than yourself
            if tarmember.rank <= member.rank and tarmember != member:
                caller.msg("You cannot change the rank of someone equal to you or higher.")
                return
            if tarmember.rank <= 2 < rank and tarmember != member:
                caller.msg("Only staff can demote leaders.")
                return
            tarmember.rank = rank
            tarmember.save()
            if rank < 5 and org.category == "noble":
                try:
                    rep = tarmember.player.reputations.get(organization=org)
                    rep.wipe_favor()
                except Reputation.DoesNotExist:
                    pass
            caller.msg("You have set %s's rank to %s." % (player, rank))
            player.msg("Your rank has been set to %s in %s." % (rank, org))
            return
        # other switches can omit the org name if we're only a member of one org   
        if not self.rhs:
            if len(myorgs) > 1:
                caller.msg("You belong to more than one organization and must give its name.")
                return
            if not myorgs:
                caller.msg("You are not in any organizations.")
                return
            org = myorgs[0]
            member = caller.Dominion.memberships.get(organization=org)
        else:
            try:
                org, member = self.get_org_and_member(caller, myorgs, self.rhs)
            except Organization.DoesNotExist:
                caller.msg("You are not a member of any organization named %s." % self.rhs)
                return
        if 'invite' in self.switches:
            if not org.access(caller, 'invite'):
                caller.msg("You do not have permission to invite new members.")
                return
            if Member.objects.filter(Q(deguilded=False)
                                     & Q(organization=org)
                                     & Q(player__player=player)).exists():
                caller.msg("They are already a member of your organization.")
                return
            char = player.db.char_ob
            if not hasattr(player, 'Dominion'):
                setup_utils.setup_dom_for_char(char)
            if not player.is_connected:
                caller.msg("%s must be logged in to be invited." % player)
                return
            if player.ndb.orginvite:
                caller.msg("Player already has an outstanding invite they must accept or decline.")
                return
            player.ndb.orginvite = org
            caller.msg("You have invited %s to %s." % (player, org.name))
            msg = "You have been invited to join %s.\n" % org.name
            msg += "To accept, type {w@org/accept %s{n. To decline, type {worg/decline %s{n." % (org.name, org.name)
            player.inform(msg, category="Invitation")
            return
        tarmember = self.get_member_from_player(org, player)
        if not tarmember:
            return
        if 'boot' in self.switches:
            if tarmember != member:
                if not org.access(caller, 'boot'):
                    caller.msg("You do not have permission to boot players.")
                    return
                if tarmember.rank <= member.rank:
                    caller.msg("You cannot boot someone who is equal or higher rank.")
                    return
                if tarmember.rank <= 2:
                    caller.msg("Only staff can boot leaders.")
                    return
            tarmember.fake_delete()
            caller.msg("Booted %s from %s." % (player, org))
            player.msg("You have been removed from %s." % org)
            inform_staff("%s has been removed from {c%s{n by %s." % (player, org, caller))
            return
        if 'memberview' in self.switches:
            if org.secret and not org.access(caller, 'view'):
                caller.msg("You do not have permission to view players.")
                return
            caller.msg("{wMember info for {c%s{n" % tarmember)
            caller.msg(tarmember.display())
            return
        if 'secret' in self.switches:
            if not org.access(caller, 'setrank'):
                caller.msg("You do not have permission to change member status.")
                return
            member = caller.Dominion.memberships.get(organization=org)
            if member.rank > tarmember.rank:
                caller.msg("You cannot change someone who is higher ranked than you.")
                return
            tarmember.secret = not tarmember.secret
            tarmember.save()
            caller.msg("Their secret status is now %s" % tarmember.secret)
            return
        if 'setruler' in self.switches:
            if not org.access(caller, 'setruler'):
                caller.msg("You do not have permission to set who handles ruling of your organization's estates.")
                return
            targ = tarmember.player
            # if the character is already a ruler, they'd violate unique constraint to be reassigned
            try:
                ruler_check = targ.ruler
                caller.msg("%s is already acting as a ruler. Tell them to abdicate." % targ)
                targ.player.msg("You cannot be assigned as a ruler while you are acting as %s's ruler." % ruler_check)
                return
            except Ruler.DoesNotExist:
                pass
            house = org.assets
            try:
                ruler = Ruler.objects.get(house=house)
            except Ruler.DoesNotExist:
                ruler = Ruler.objects.create(house=house)
            old = ruler.castellan
            ruler.castellan = targ
            ruler.save()
            if old:
                caller.msg("Command of armies and holdings has passed from %s to %s." % (old, player))
                return
            caller.msg("%s has been placed in command of all of the armies and holdings of %s." % (player, org))
            return
        self.msg("Invalid switch.")

    def set_motd(self, myorgs):
        """Sets a message of the day for an organization"""
        org = self.get_org_from_myorgs(myorgs)
        if not org:
            return
        if not org.access(self.caller, "motd"):
            self.msg("You do not have permission to set the motd.")
            return
        org.set_motd(self.lhs)


class CmdFamily(ArxPlayerCommand):
    """
    @family

    Usage:
        @family
        @family <player>

    Displays family information about a given character, if
    available.
    """
    key = "@family"
    locks = "cmd:all()"
    help_category = "Dominion"

    def func(self):
        caller = self.caller
        if not self.args:
            player = caller
            show_private = True
        else:
            from typeclasses.accounts import Account
            try:
                player = Account.objects.get(username__iexact=self.args)
            except (Account.DoesNotExist, Account.MultipleObjectsReturned):
                player = None
            show_private = False
        try:
            if not player:
                dompc = PlayerOrNpc.objects.get(npc_name__iexact=self.args)
            else:
                dompc = player.Dominion
            caller.msg("\n{c%s's{w family:{n" % dompc)
            famtree = dompc.display_immediate_family()
            if not famtree:
                famtree = "No relatives found for {c%s{n.\n" % dompc
            caller.msg(famtree)
            if player:
                try:
                    family = player.db.char_ob.db.family
                    fam_org = Organization.objects.get(name__iexact=family)
                    details = fam_org.display_public()
                    caller.msg("%s family information:\n%s" % (family, details))
                    return
                except Organization.DoesNotExist:
                    # display nothing
                    pass
            return
        except PlayerOrNpc.DoesNotExist:
            caller.msg("No relatives found for {c%s{n." % self.args)
            return

max_proteges = {
    1: 5,
    2: 4,
    3: 3,
    4: 3,
    5: 2,
    6: 2,
    7: 1,
    8: 1,
    }


class CmdPatronage(ArxPlayerCommand):
    """
    @patron

    Usage:
        @patronage
        @patronage <player>
        @patronage/addprotege <player>
        @patronage/dismiss <player>
        @patronage/accept
        @patronage/reject
        @patronage/abandon

    Displays and manages patronage.
    """
    key = "@patronage"
    locks = "cmd:all()"
    help_category = "Dominion"

    @staticmethod
    def display_patronage(dompc):
        patron = dompc.patron
        proteges = dompc.proteges.all()
        msg = "{wPatron and Proteges for {c%s{n:\n" % str(dompc)
        msg += "{wPatron:{n %s\n" % ("{c%s{n" % patron if patron else "None")
        msg += "{wProteges:{n %s" % ", ".join("{c%s{n" % str(ob) for ob in proteges)
        return msg

    def check_social_rank_difference(self, target):
        """Determines if social rank is great enough"""
        our_rank = self.caller.char_ob.db.social_rank or 10
        targ_rank = target.db.social_rank or 0
        if our_rank < 3:
            diff = 3
        elif our_rank < 6:
            diff = 2
        else:
            diff = 1
        if our_rank + diff > targ_rank:
            self.msg("Your social rank must be at least %d higher than your target." % diff)
            return False
        return True

    def func(self):
        caller = self.caller
        try:
            dompc = self.caller.Dominion
        except AttributeError:
            dompc = setup_utils.setup_dom_for_char(self.caller.db.char_ob)
        if not self.args and not self.switches:        
            caller.msg(self.display_patronage(dompc), options={'box': True})
            return
        if self.args:
            player = caller.search(self.args)
            if not player:
                return
            char = player.db.char_ob
            if not char:
                caller.msg("No character found for %s." % player)
                return
            try:
                tdompc = player.Dominion
            except AttributeError:
                tdompc = setup_utils.setup_dom_for_char(char)
            if not self.switches:
                caller.msg(self.display_patronage(tdompc), options={'box': True})
                return
            if "addprotege" in self.switches:
                if not player.is_connected:
                    caller.msg("They must be online to add them as a protege.")
                    return
                if tdompc.patron:
                    caller.msg("They already have a patron.")
                    return
                num = dompc.proteges.all().count()
                psrank = caller.db.char_ob.db.social_rank
                max_p = max_proteges.get(psrank, 0)
                if num >= max_p:
                    caller.msg("You already have the maximum number of proteges for your social rank.")
                    return
                if not self.check_social_rank_difference(char):
                    return
                player.ndb.pending_patron = caller
                msg = "{c%s {wwants to become your patron. " % caller.key.capitalize()
                msg += " Use @patronage/accept to accept {wthis offer, or @patronage/reject to reject it.{n"
                player.msg(msg)
                caller.msg("{wYou have extended the offer of patronage to {c%s{n." % player.key.capitalize())
                return
            if "dismiss" in self.switches:
                if tdompc not in dompc.proteges.all():
                    caller.msg("They are not one of your proteges.")
                    return
                dompc.proteges.remove(tdompc)
                caller.msg("{c%s {wis no longer one of your proteges.{n" % char)
                player.msg("{c%s {wis no longer your patron.{n" % caller.key.capitalize())
                return
            caller.msg("Unrecognized switch.")
            return
        pending = caller.ndb.pending_patron
        if 'accept' in self.switches:
            if not pending:
                caller.msg("You have no pending invitation.")
                return
            dompc.patron = pending.Dominion
            dompc.save()
            caller.msg("{c%s {wis now your patron.{n" % pending.key.capitalize())
            pending.msg("{c%s {whas accepted your patronage, and is now your protege.{n" % caller.key.capitalize())
            caller.ndb.pending_patron = None
            return
        if 'reject' in self.switches:
            if not pending:
                caller.msg("You have no pending invitation.")
                return
            caller.msg("You decline %s's invitation." % pending.key.capitalize())
            pending.msg("%s has declined your patronage." % caller.key.capitalize())
            caller.ndb.pending_patron = None
            return
        if 'abandon' in self.switches:
            old = dompc.patron          
            if old:
                dompc.patron = None
                dompc.save()
                old.player.msg("{c%s {rhas abandoned your patronage, and is no longer your protege.{n" % dompc)
                caller.msg("{rYou have abandoned {c%s{r's patronage, and are no longer their protege.{n" % old)
            else:
                caller.msg("You don't have a patron.")
            return
        caller.msg("Unrecognized switch.")
        return


# Character/IC commands------------------------------


class CmdWork(ArxPlayerCommand):
    """
    Does work for a given organization to generate resources

    Usage:
        work <organization>,<type>[=protege to use]
        work/invest <organization>,<type>,<amount>[=protege to use]
        work/score <organization>

    Spends 15 action points to have work done for an organization,
    either by yourself or by one of your proteges, to generate
    resources.

    The stat/skill used for the roll is based on the resource type.
    Economic: intellect + economics
    Military: command + war
    Social: charm + diplomacy

    Social clout of you and your protege lowers the difficulty and
    increases results, and the roller is whoever has higher skill.
    """
    key = "work"
    help_category = "Dominion"
    locks = "cmd:all()"
    aliases = ["task", "support"]
    ap_cost = 15

    @property
    def dompc(self):
        """caller's dompc"""
        return self.caller.Dominion

    def func(self):
        """Perform work command"""
        try:
            if self.cmdstring.lower() in self.aliases:
                raise CommandError("Command does not exist. Please see 'help work'.")
            if not self.switches:
                return self.do_work()
            if "invest" in self.switches:
                return self.do_invest()
            if "score" in self.switches:
                return self.do_score()
        except (CommandError, ValueError) as err:
            self.msg(err)

    def do_work(self):
        """Performs work"""
        res_type = self.get_resource_type()
        member = self.get_member(org_name=self.lhslist[0])
        protege = self.get_protege()
        member.work(res_type, self.ap_cost, protege)

    def get_member(self, org_name):
        """Gets membership from an org"""
        try:
            return self.dompc.memberships.get(deguilded=False, organization__name__iexact=org_name)
        except Member.DoesNotExist:
            raise CommandError("No match for an org by the name: %s." % org_name)

    def get_protege(self):
        """Gets a protege"""
        if self.rhs:
            try:
                return self.dompc.proteges.get(player__username__iexact=self.rhs)
            except PlayerOrNpc.DoesNotExist:
                raise CommandError("No protege by that name.")

    def get_resource_type(self):
        """Gets resource type or raises a command error"""
        try:
            return self.lhslist[1]
        except IndexError:
            raise CommandError("Must give a name and type of resource.")

    def do_invest(self):
        """Does an investment"""
        res_type = self.get_resource_type()
        member = self.get_member(org_name=self.lhslist[0])
        protege = self.get_protege()
        try:
            amount = int(self.lhslist[2])
            if amount < 10:
                raise ValueError
        except (TypeError, ValueError, IndexError):
            raise CommandError("You must specify at least 10 resources to invest.")
        member.invest(resource_type=res_type, ap_cost=5, protege=protege, resources=amount)

    def do_score(self):
        """Lists scoreboard for members"""
        from django.db.models import ExpressionWrapper, IntegerField
        if not self.caller.is_staff:
            org = self.get_member(org_name=self.lhs).organization
            if org.secret:
                raise CommandError("Cannot list data for secret orgs.")
            qs = org.active_members.exclude(secret=True)
        else:
            try:
                org = Organization.objects.get(name__iexact=self.lhs)
            except Organization.DoesNotExist:
                raise CommandError("Bad name for org: %s" % self.lhs)
            qs = org.active_members
        members = (qs.annotate(combined=ExpressionWrapper(F('work_total') + F('investment_total'),
                                                          output_field=IntegerField()))
                     .exclude(combined__lte=0)
                     .values_list('player__player__username', 'work_total', 'investment_total', 'combined')
                     .order_by('-combined'))
        table = PrettyTable(["Member", "Total Work", "Total Invested", "Combined"])
        table.align="r"
        for member in members:
            member = [member[0].capitalize()] + list(member[1:])
            member = list(member)
            member[1]="{:,}".format(member[1])
            member[2]="{:,}".format(member[2])
            member[3]="{:,}".format(member[3])
            table.add_row(member)
        self.msg(str(table))


class CmdPlotRoom(ArxCommand):
    """
    @plotroom

    Usage:
        @plotroom
        @plotroom <id>
        @plotroom/new
        @plotroom/name <name>
        @plotroom/desc <desc>
        @plotroom/near <domain>
        @plotroom/wilderness
        @plotroom/public
        @plotroom/review
        @plotroom/finish
        @plotroom/cancel

    The first form of this command will list all available plotrooms, for use
    on a @calendar event.  It will show the rooms the current player has created,
    or those which are flagged public.  The second form will show the details
    for a specific room.

    The remaining switches are used to define a new plotroom and add it to the list.
    The name should only be the actual room name, like 'Ancient Workshop'.  The 'near'
    domain will used to build a properly-colored name with all proper prefixes, as
    well as to allow staff to easily find where rooms are located.  Public toggles
    whether or not others can use this plotroom.  Wilderness toggles whether or not
    the room is in the 'near' domain you put, or just nearby.  Finish will submit the
    plotroom, and cancel will abort your current effort.

    These plotrooms can be used with @cal/plotroom when creating a calendar event.
    """
    key = "@plotroom"
    locks = "cmd:all()"
    help_category = "Dominion"

    def display_room(self, room):
        self.msg("|/Id     : " + str(room.id))
        self.msg("Name   : " + room.name)
        self.msg("Creator: " + str(room.creator))
        self.msg("Public : " + (room.public and "Yes" or "No"))
        self.msg("Region : " + room.get_detailed_region_name())
        self.msg("Desc   :|/" + room.description + "|/")

    def display_form(self, form):
        self.msg("|/Name   : " + form[0])
        self.msg("Public : " + (form[2] and "Yes" or "No"))

        region = "Unknown"
        if form[3] != 0:
            try:
                domain = Domain.objects.get(id=form[3])
                if form[4]:
                    # Wilderness
                    region = domain.land.region.name + " near " + domain.name
                else:
                    region = domain.name
            except Domain.DoesNotExist:
                region = "Unknown Region (Internal Error)"

        self.msg("Region : " + region)
        self.msg("Desc   :|/" + form[1] + "|/")

    def func(self):
        form = self.caller.db.plotroom_form
        try:
            owner = self.caller.player.Dominion
        except AttributeError:
            self.msg("Internal error: unable to resolve current player!")
            return

        if not self.args and not self.switches:
            # @plotroom
            rooms = PlotRoom.objects.filter(Q(creator=owner) | Q(public=True))
            if not rooms:
                self.msg("Unable to view plot rooms.")
                return

            table = EvTable("", "Region", "Name", "Creator", "Public")
            for room in rooms:
                table.add_row(room.id, room.get_region_name(), room.name, room.creator,
                              room.public and "X" or "")

            self.msg(table)

        elif not self.switches:
            # @plotroom <id>
            room = None
            room_id = None
            try:
                room_id = int(self.args)
            except ValueError:
                rooms = PlotRoom.objects.filter(Q(name__icontains=self.args) &
                                                (Q(creator=owner) | Q(public=True)))
                if not rooms:
                    self.msg("Could not find a room matching " + self.args)
                    return
                if len(rooms) > 1:
                    self.msg("Found multiple matching rooms:")
                    for outroom in rooms:
                        self.msg("  %s (%s)" % (outroom.name, outroom.get_detailed_region_name()))
                    return
                room = rooms[0]

            if not room and room_id is not None:
                try:
                    room = PlotRoom.objects.get(id=room_id)
                except PlotRoom.DoesNotExist:
                    self.msg("You cannot view that room.")
                    return

            if room is not None:
                if room.creator is not owner and not room.public:
                    room = None

            if not room:
                self.msg("You cannot view that room.")
                return

            self.display_room(room)

        elif "new" in self.switches:
            form = ["", "", False, 0, True]
            self.caller.db.plotroom_form = form
            self.display_form(form)

        elif "name" in self.switches:
            if form is None:
                self.msg("You must do @plotroom/new before setting up a room!")
                return

            form[0] = self.args
            self.caller.db.plotroom_form = form
            self.display_form(form)

        elif "desc" in self.switches:
            if form is None:
                self.msg("You must do @plotroom/new before setting up a room!")
                return

            form[1] = self.args
            self.caller.db.plotroom_form = form
            self.display_form(form)

        elif "public" in self.switches:
            if form is None:
                self.msg("You must do @plotroom/new before setting up a room!")
                return

            form[2] = not form[2]
            self.caller.db.plotroom_form = form
            self.display_form(form)

        elif "near" in self.switches:
            if form is None:
                self.msg("You must do @plotroom/new before setting up a room!")
                return

            domain = Domain.objects.filter(name__icontains=self.args)
            if not domain:
                self.msg("Did not find a matching domain.")
                return

            if len(domain) > 1:
                self.msg("Found more than one domain matching that name: ")
                for dom in domain:
                    self.msg("  " + dom.name)
                return

            form[3] = domain[0].id
            self.caller.db.plotroom_form = form
            self.display_form(form)

        elif "wilderness" in self.switches:
            if form is None:
                self.msg("You must do @plotroom/new before setting up a room!")
                return

            form[4] = not form[4]
            self.caller.db.plotroom_form = form
            self.display_form(form)

        elif "review" in self.switches:
            if form is None:
                self.msg("You must do @plotroom/new before setting up a room!")
                return

            self.display_form(form)

        elif "cancel" in self.switches:
            if form is None:
                self.msg("No room setup to cancel.")
                return

            self.caller.attributes.remove('plotroom_form')
            self.msg("Room creation cancelled.")

        elif "finish" in self.switches:
            if form is None:
                self.msg("You must do @plotroom/new before setting up a room!")
                return

            name = form[0]
            desc = form[1]
            public = form[2]
            domain_id = form[3]
            wilderness = form[4]

            if len(name) < 5:
                self.msg("Name is too short!")
                return

            if len(desc) < 100:
                self.msg("Desc is too short!")
                return

            if domain_id == 0:
                self.msg("You need to provide a location!")
                return

            try:
                domain = Domain.objects.get(id=domain_id)
            except Domain.DoesNotExist:
                self.msg("Internal error: invalid domain.  Contact Tehom or Pax!")
                return

            room = PlotRoom(name=name, description=desc, public=public, domain=domain,
                            location=domain.location, wilderness=wilderness, creator=owner)
            room.save()
            self.msg("Saved room %d." % room.id)
            self.caller.attributes.remove('plotroom_form')

        else:
            self.msg("Invalid usage.")


class CmdCleanupDomain(ArxPlayerCommand):
    """
    This is a temporary one-off command that will clean out the old NPC domains
    and orgs.  It should be run only once!
    """
    key = "@onetimedomaincleanup"
    locks = "cmd:perm(Wizards)"
    help_category = "Dominion"

    def delete_and_report(self, name, qs):
        self.msg("Deleting NPC %s..." % name)
        output = qs.delete()
        output = "Total: %s, %s" % (output[0], ", ".join("%s: %s" % (key, value) for key, value in output[1].items()))
        self.msg("Deleted: %s" % output)

    def func(self):
        domains = Domain.objects \
            .filter(ruler__house__organization_owner__members__player__player__isnull=True).distinct()
        self.delete_and_report("domains", domains)

        assetowners = AssetOwner.objects.filter(organization_owner__isnull=False)\
            .filter(organization_owner__members__player__player__isnull=True).distinct()
        self.delete_and_report("organization asset owners", assetowners)

        npc_asset_owners = AssetOwner.objects.filter(organization_owner__isnull=True,
                                                     player__player__isnull=True).distinct()
        self.delete_and_report("PlayerOrNpc asset owners", npc_asset_owners)

        armies = Army.objects.filter(owner__isnull=True).distinct()
        self.delete_and_report("armies", armies)

        rulers = Ruler.objects.filter(house__organization_owner__members__player__player__isnull=True).distinct()
        self.delete_and_report("rulers", rulers)

        orgs = Organization.objects.filter(members__player__player__isnull=True).distinct()
        MilitaryUnit.objects.filter(origin__in=orgs).update(origin=None)
        self.delete_and_report("organizations", orgs)

        self.msg("Done!")
