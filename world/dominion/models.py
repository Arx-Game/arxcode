"""
So, what is Dominion?

Dominion is the design for making the world come alive in an immersive way.
The classic problem most MMOs and MUSHes have is ultimately limiting how
much a player can impact the world. It's understandable, of course - an
MMO would be utterly broken if a single player gets to call the shots. But
MUSHes are a different animal in that we're much smaller, and trying to
create an immersive RP experience that's similar to tabletop RPGs, just
with much more people involved. So what Dominion is attempting to do is
create consequences for player characters interacting with the economy,
owning land, leading armies, or having NPCs in their organizations that
will do their bidding. Dominion is the power and influence that a character
can exert that isn't directly tied to their stats or what they carry on
their person - it's what you can order npcs to do, how the world can
change based on your choices, and ultimately attempts to make the world
feel much more 'real' as a result.

Dominion consists of several moving parts. First is the economy - it's
to try to represent how having wealth can directly translate into power,
and will try to create a fairly believable (albeit abstract) economic
model for the world. With the economy, all forms of wealth, income,
debts, and holdings should be represented for every inhabitant in the
game world.

The second part is organizations, and giving who obey you orders, and
trying to represent how those orders are obeyed. It's where we establish
ranks, relationships such as loyalty and morale, and give strong
consequences to social systems such as prestiege or your reputation
because it will determine how npcs will react to a character on a macro
level.

The last part is military might - a war system for controlling armies,
and the effects of war on the world as a whole.

Models for Dominion:

For the economy, we have: AssetOwner, Ledger, AccountTransaction, and
Domain. AssetOwner receives income from Ledger and Domain objects, with
AccountTransaction handling positive/negative income/debt adjustments to
a Ledger.

For the world map, we have: Region and Land. Player-held Domain objects
will be positioned in Land squares, limited by available area.

For domains, we have: Domain, DomainProject, Castle, and Military. Domain
represents everything within a lord/noble's holding - the people, economy,
military, etc. It is situated within a given Land square.

Every week, a script is called that will run execute_orders() on every
Army, and then do weekly_adjustment() in every assetowner. So only domains
that currently have a ruler designated will change on a weekly basis.
"""
from datetime import datetime
from random import randint
import traceback

from evennia.utils.idmapper.models import SharedMemoryModel
from evennia.locks.lockhandler import LockHandler
from evennia.utils.utils import lazy_property
from evennia.utils import create
from django.db import models
from django.db.models import Q, Count, F, Sum
from django.conf import settings
from django.core.urlresolvers import reverse

from . import unit_types, unit_constants
from .reports import WeeklyReport
from .battle import Battle
from .agenthandler import AgentHandler
from .managers import CrisisManager, OrganizationManager, LandManager
from server.utils.arx_utils import get_week, inform_staff, passthrough_properties, CachedProperty, CachedPropertiesMixin
from server.utils.exceptions import ActionSubmissionError, PayError
from typeclasses.npcs import npc_types
from typeclasses.mixins import InformMixin
from web.character.models import AbstractPlayerAllocations
from world.stats_and_skills import do_dice_check

# Dominion constants
BASE_WORKER_COST = 0.10
SILVER_PER_BUILDING = 225.00
FOOD_PER_FARM = 100.00
# default value for a global modifier to Dominion income, can be set as a ServerConfig value on a per-game basis
DEFAULT_GLOBAL_INCOME_MOD = -0.25
# each point in a dominion skill is a 5% bonus
BONUS_PER_SKILL_POINT = 0.10
# number of workers for a building to be at full production
SERFS_PER_BUILDING = 20.0
# population cap for housing
POP_PER_HOUSING = 1000
BASE_POP_GROWTH = 0.01
DEATHS_PER_LAWLESS = 0.0025
LAND_SIZE = 10000
LAND_COORDS = 9
LIFESTYLES = {
    0: (-100, -1000),
    1: (0, 0),
    2: (100, 2000),
    3: (200, 3000),
    4: (500, 4000),
    5: (1500, 7000),
    6: (5000, 10000),
    }
PRESTIGE_DECAY_AMOUNT = 0.35

PAGEROOT = "http://play.arxgame.org"


# Create your models here.
class PlayerOrNpc(SharedMemoryModel):
    """
    This is a simple model that represents that the entity can either be a PC
    or an NPC who has no presence in game, and exists only as a name in the
    database.
    """
    player = models.OneToOneField(settings.AUTH_USER_MODEL, related_name='Dominion', blank=True, null=True)
    npc_name = models.CharField(blank=True, null=True, max_length=255)
    parents = models.ManyToManyField("self", symmetrical=False, related_name='children', blank=True)
    spouses = models.ManyToManyField("self", blank=True)
    alive = models.BooleanField(default=True, blank=True)
    patron = models.ForeignKey('self', related_name='proteges', null=True, blank=True,
                               on_delete=models.SET_NULL)
    lifestyle_rating = models.PositiveSmallIntegerField(default=1, blank=1)
    # --- Dominion skills----
    # bonus to population growth
    population = models.PositiveSmallIntegerField(default=0, blank=0)
    # bonus to income sources
    income = models.PositiveSmallIntegerField(default=0, blank=0)
    # bonus to harvests
    farming = models.PositiveSmallIntegerField(default=0, blank=0)
    # costs for projects/commands
    productivity = models.PositiveSmallIntegerField(default=0, blank=0)
    # upkeep costs
    upkeep = models.PositiveSmallIntegerField(default=0, blank=0)
    # loyalty mod of troops/serfs
    loyalty = models.PositiveSmallIntegerField(default=0, blank=0)
    # bonus to all military combat commands
    warfare = models.PositiveSmallIntegerField(default=0, blank=0)

    def __str__(self):
        if self.player:
            name = self.player.key.capitalize()
            if not self.alive:
                name += "(RIP)"
            return name
        name = self.npc_name
        if not self.alive:
            name += "(RIP)"
        return name

    def _get_siblings(self):
        return PlayerOrNpc.objects.filter(Q(parents__in=self.all_parents) &
                                          ~Q(id=self.id)).distinct()

    def _parents_and_spouses(self):
        return PlayerOrNpc.objects.filter(Q(children__id=self.id) | Q(spouses__children__id=self.id)).distinct()
    all_parents = property(_parents_and_spouses)

    @property
    def grandparents(self):
        """Returns queryset of our grandparents"""
        return PlayerOrNpc.objects.filter(Q(children__children=self) | Q(spouses__children__children=self) |
                                          Q(children__spouses__children=self) |
                                          Q(spouses__children__children__spouses=self) |
                                          Q(children__children__spouses=self) |
                                          Q(spouses__children__spouses__children=self)).distinct()

    @property
    def greatgrandparents(self):
        """Returns queryset of our great grandparents"""
        return PlayerOrNpc.objects.filter(Q(children__in=self.grandparents) | Q(spouses__children__in=self.grandparents)
                                          ).distinct()

    @property
    def second_cousins(self):
        """Returns queryset of our second cousins"""
        return PlayerOrNpc.objects.filter(~Q(id=self.id) & ~Q(id__in=self.cousins) &
                                          ~Q(id__in=self.siblings) & ~Q(id__in=self.spouses.all())
                                          & (
                                            Q(parents__parents__parents__in=self.greatgrandparents) |
                                            Q(parents__parents__parents__spouses__in=self.greatgrandparents) |
                                            Q(parents__parents__spouses__parents__in=self.greatgrandparents) |
                                            Q(parents__spouses__parents__parents__in=self.greatgrandparents)
                                          )).distinct()

    def _get_cousins(self):
        return PlayerOrNpc.objects.filter((Q(parents__parents__in=self.grandparents) |
                                           Q(parents__parents__spouses__in=self.grandparents) |
                                           Q(parents__spouses__parents__in=self.grandparents)) & ~Q(id=self.id)
                                          & ~Q(id__in=self.siblings) & ~Q(id__in=self.spouses.all())).distinct()

    cousins = property(_get_cousins)
    siblings = property(_get_siblings)

    def display_immediate_family(self):
        """
        Creates lists of our family relationships and converts the lists to sets
        to remove duplicates. At the very end, convert each one to a string with
        join. Then return all these strings added together.
        """
        ggparents = self.greatgrandparents
        grandparents = []
        parents = self.all_parents
        unc_or_aunts = []
        for parent in parents:
            grandparents += list(parent.all_parents)
            for sibling in parent.siblings:
                unc_or_aunts.append(sibling)
                for spouse in sibling.spouses.all():
                    unc_or_aunts.append(spouse)
        spouses = self.spouses.all()
        siblings = self.siblings
        neph_or_nieces = []
        for sib in siblings:
            neph_or_nieces += list(sib.children.all())
        for spouse in self.spouses.all():
            for sib in spouse.siblings:
                neph_or_nieces += list(sib.children.all())
        children = self.children.all()
        grandchildren = []
        for child in children:
            grandchildren += list(child.children.all())
        cousins = self.cousins
        second_cousins = self.second_cousins
        # convert lists to sets that remove duplicates
        unc_or_aunts = set(unc_or_aunts)
        grandparents = set(grandparents)
        neph_or_nieces = set(neph_or_nieces)
        grandchildren = set(grandchildren)
        # convert to strings
        if ggparents:
            ggparents = "{wGreatgrandparents{n: %s\n" % (", ".join(str(ggparent) for ggparent in ggparents))
        else:
            ggparents = ''
        if grandparents:
            grandparents = "{wGrandparents{n: %s\n" % (", ".join(str(gparent) for gparent in grandparents))
        else:
            grandparents = ''
        if parents:
            parents = "{wParents{n: %s\n" % (", ".join(str(parent) for parent in parents))
        else:
            parents = ''
        if spouses:
            spouses = "{wSpouses{n: %s\n" % (", ".join(str(spouse) for spouse in spouses))
        else:
            spouses = ''
        if unc_or_aunts:
            unc_or_aunts = "{wUncles/Aunts{n: %s\n" % (", ".join(str(unc) for unc in unc_or_aunts))
        else:
            unc_or_aunts = ''
        if siblings:
            siblings = "{wSiblings{n: %s\n" % (", ".join(str(sib) for sib in siblings))
        else:
            siblings = ''
        if neph_or_nieces:
            neph_or_nieces = "{wNephews/Nieces{n: %s\n" % (", ".join(str(neph) for neph in neph_or_nieces))
        else:
            neph_or_nieces = ''
        if children:
            children = "{wChildren{n: %s\n" % (", ".join(str(child) for child in children))
        else:
            children = ''
        if grandchildren:
            grandchildren = "{wGrandchildren{n: %s\n" % (", ".join(str(gchild) for gchild in grandchildren))
        else:
            grandchildren = ''
        if cousins:
            cousins = "{wCousins{n: %s\n" % (", ".join(str(cousin) for cousin in cousins))
        else:
            cousins = ''
        if second_cousins:
            second_cousins = "{wSecond Cousins{n: %s\n" % (", ".join(str(seco) for seco in second_cousins))
        else:
            second_cousins = ''
        return (ggparents + grandparents + parents + unc_or_aunts + spouses + siblings
                + children + neph_or_nieces + cousins + second_cousins + grandchildren)

    def msg(self, *args, **kwargs):
        """Passthrough method to call msg in the player attached to us"""
        self.player.msg(*args, **kwargs)

    def gain_reputation(self, org, affection, respect):
        """Adjusts our reputation with a given org."""
        try:
            reputation = self.reputations.get(organization=org)
            reputation.affection += affection
            reputation.respect += respect
            reputation.save()
        except Reputation.DoesNotExist:
            self.reputations.create(organization=org, affection=affection, respect=respect)

    @property
    def current_orgs(self):
        """Returns Organizations we have not been deguilded from"""
        org_ids = self.memberships.filter(deguilded=False).values_list('organization', flat=True)
        return Organization.objects.filter(id__in=org_ids)

    @property
    def public_orgs(self):
        """Returns non-secret organizations we haven't been deguilded from"""
        org_ids = self.memberships.filter(deguilded=False, secret=False).values_list('organization', flat=True)
        return Organization.objects.filter(id__in=org_ids, secret=False)

    @property
    def secret_orgs(self):
        """Returns secret organizations we haven't been deguilded from"""
        secret_ids = self.memberships.filter(deguilded=False, secret=True).values_list('organization', flat=True)
        return Organization.objects.filter(Q(secret=True) | Q(id__in=secret_ids)).distinct()

    def pay_lifestyle(self, report=None):
        """Pays for our lifestyle and adjusts our prestige"""
        try:
            assets = self.assets
        except AttributeError:
            return False
        life_lvl = self.lifestyle_rating
        cost = LIFESTYLES.get(life_lvl, (0, 0))[0]
        prestige = LIFESTYLES.get(life_lvl, (0, 0))[1]
        try:
            clout = self.player.char_ob.social_clout
            bonus = int(prestige * clout * 3 * 0.01)
            if bonus > 0:
                prestige += bonus
        except (AttributeError, TypeError, ValueError):
            pass

        def pay_and_adjust(payer):
            """Helper function to make the payment, adjust prestige, and send a report"""
            payer.vault -= cost
            payer.save()
            assets.adjust_prestige(prestige)
            payname = "You" if payer == assets else str(payer)
            if report:
                report.lifestyle_msg = "%s paid %s for your lifestyle and you gained %s prestige.\n" % (payname, cost,
                                                                                                        prestige)
        if assets.vault > cost:
            pay_and_adjust(assets)
            return True
        orgs = [ob for ob in self.current_orgs if ob.access(self.player, 'withdraw')]
        if not orgs:
            return False
        for org in orgs:
            if org.assets.vault > cost:
                pay_and_adjust(org.assets)
                return True
        # no one could pay for us
        if report:
            report.lifestyle_msg = "You were unable to afford to pay for your lifestyle.\n"
        return False

    @CachedProperty
    def support_cooldowns(self):
        """Returns our support cooldowns, from cache if it's already been calculated"""
        return self.calc_support_cooldowns()

    def calc_support_cooldowns(self):
        """Calculates support used in last three weeks, builds a dictionary"""
        cdowns = {}
        # noinspection PyBroadException
        try:
            week = get_week()
        except Exception:
            import traceback
            traceback.print_exc()
            return cdowns
        try:
            max_support = self.player.db.char_ob.max_support
        except AttributeError:
            import traceback
            traceback.print_exc()
            return cdowns
        qs = SupportUsed.objects.select_related('supporter__task__member__player').filter(Q(supporter__player=self) &
                                                                                          Q(supporter__fake=False))

        def process_week(qset, week_offset=0):
            """Helper function for changing support cooldowns"""
            qset = qset.filter(week=week + week_offset)
            for used in qset:
                member = used.supporter.task.member
                pc = member.player.player.db.char_ob
                points = cdowns.get(pc.id, max_support)
                points -= used.rating
                cdowns[pc.id] = points
            if week_offset:
                for name in cdowns.keys():
                    cdowns[name] += max_support/3
                    if max_support % 3:
                        cdowns[name] += 1
                    if cdowns[name] >= max_support:
                        del cdowns[name]
        for offset in range(-3, 1):
            process_week(qs, offset)
        return cdowns

    @property
    def remaining_points(self):
        """
        Calculates how many points we've spent this week, and returns how
        many points we should have remaining.
        """
        week = get_week()
        try:
            max_support = self.player.db.char_ob.max_support
            points_spent = sum(SupportUsed.objects.filter(Q(week=week) & Q(supporter__player=self) &
                                                          Q(supporter__fake=False)).values_list('rating', flat=True))

        except (ValueError, TypeError, AttributeError):
            return 0
        return max_support - points_spent

    def get_absolute_url(self):
        """Returns the absolute_url of our associated character"""
        try:
            return self.player.char_ob.get_absolute_url()
        except AttributeError:
            pass

    def inform(self, text, category=None, append=False):
        """Passthrough method to send an inform to our player"""
        player = self.player
        week = get_week()
        if player:
            player.inform(text, category=category, week=week, append=append)

    @property
    def recent_actions(self):
        """Returns queryset of recent actions that weren't cancelled and aren't still in draft"""
        from datetime import timedelta
        offset = timedelta(days=-PlotAction.num_days)
        old = datetime.now() + offset
        return self.actions.filter(Q(date_submitted__gte=old) &
                                   ~Q(status__in=(PlotAction.CANCELLED, PlotAction.DRAFT)) &
                                   Q(free_action=False))

    @property
    def recent_assists(self):
        """Returns queryset of all assists from the past 30 days"""
        from datetime import timedelta
        offset = timedelta(days=-PlotAction.num_days)
        old = datetime.now() + offset
        actions = PlotAction.objects.filter(Q(date_submitted__gte=old) &
                                            ~Q(status__in=(PlotAction.CANCELLED, PlotAction.DRAFT)) &
                                            Q(free_action=False))
        return self.assisting_actions.filter(plot_action__in=actions, free_action=False).distinct()

    @property
    def past_actions(self):
        """Returns queryset of our old published actions"""
        return self.actions.filter(status=PlotAction.PUBLISHED)

    def clear_cached_values_in_appointments(self):
        """Clears cache in ruler/minister appointments"""
        for minister in self.appointments.all():
            minister.clear_domain_cache()
        try:
            self.ruler.clear_domain_cache()
        except AttributeError:
            pass

    @property
    def events_hosted(self):
        """Events we acted as a host for"""
        return self.events.filter(pc_event_participation__status__in=(PCEventParticipation.HOST,
                                                                      PCEventParticipation.MAIN_HOST))

    @property
    def events_gmd(self):
        """Events we GM'd"""
        return self.events.filter(pc_event_participation__gm=True)

    @property
    def events_attended(self):
        """Events we were a guest at or invited to attend"""
        return self.events.filter(pc_event_participation__status=PCEventParticipation.GUEST)

    @property
    def num_fealties(self):
        """How many distinct fealties we're a part of."""
        no_fealties = self.current_orgs.filter(fealty__isnull=True).count()
        query = Q()
        for category in Organization.CATEGORIES_WITH_FEALTY_PENALTIES:
            query |= Q(category__iexact=category)
        redundancies = self.current_orgs.filter(query).values_list('category').annotate(num=Count('category') - 1)
        no_fealties += sum(ob[1] for ob in redundancies)
        return Fealty.objects.filter(orgs__in=self.current_orgs).distinct().count() + no_fealties

    @property
    def active_plots(self):
        return self.plots.filter(dompc_involvement__activity_status=PCPlotInvolvement.ACTIVE,
                                 usage__in=(Plot.GM_PLOT, Plot.PLAYER_RUN_PLOT))

    @property
    def plots_we_can_gm(self):
        return self.active_plots.filter(dompc_involvement__admin_status__gte=PCPlotInvolvement.GM)


class AssetOwner(CachedPropertiesMixin, SharedMemoryModel):
    """
    This model describes the owner of an asset, such as money
    or a land resource. The owner can either be an in-game object
    and use the object_owner field, or an organization and use
    the organization_owner field. The 'owner' property will check
    for an object first, then an organization, and return None if
    it's not owned by either. An organization or character will
    access this model with object.assets, and their income will
    be adjusted on a weekly basis with object.assets.do_weekly_adjustment().
    """
    player = models.OneToOneField('PlayerOrNpc', related_name="assets", blank=True, null=True)
    organization_owner = models.OneToOneField('Organization', related_name='assets', blank=True, null=True)

    # money stored in the bank
    vault = models.PositiveIntegerField(default=0, blank=0)
    # prestige we've earned
    fame = models.IntegerField(default=0, blank=0)
    legend = models.IntegerField(default=0, blank=0)
    # resources
    economic = models.PositiveIntegerField(default=0, blank=0)
    military = models.PositiveIntegerField(default=0, blank=0)
    social = models.PositiveIntegerField(default=0, blank=0)

    min_silver_for_inform = models.PositiveIntegerField(default=0)
    min_resources_for_inform = models.PositiveIntegerField(default=0)
    min_materials_for_inform = models.PositiveIntegerField(default=0)

    @CachedProperty
    def prestige(self):
        """Our prestige used for different mods. aggregate of fame, legend, and grandeur"""
        return self.fame + self.total_legend + self.grandeur + self.propriety

    @CachedProperty
    def propriety(self):
        """A modifier to our fame based on tags we have"""
        percentage = max(sum(ob.percentage for ob in self.proprieties.all()), -100)
        base = self.fame + self.total_legend
        # if we have negative fame, then positive propriety mods lessens that, while neg mods makes it worse
        if base < 0:
            percentage *= -1
        value = int(base * percentage/100.0)
        if self.player:
            favor = (self.player.reputations.filter(Q(favor__gt=0) | Q(favor__lt=0))
                                            .annotate(val=((F('organization__assets__fame')
                                                           + F('organization__assets__legend'))/20) * F('favor')
                                                      )
                                            .aggregate(Sum('val'))).values()[0] or 0
            value += favor
        return value

    @CachedProperty
    def honor(self):
        """A modifier to our legend based on our actions"""
        return sum(ob.amount for ob in self.honorifics.all())

    @property
    def total_legend(self):
        """Sum of legend and honor"""
        return self.legend + self.honor

    @property
    def prestige_mod(self):
        """Modifier derived from prestige used as bonus for resource gain, org income, etc"""
        prestige = self.prestige
        if prestige >= 0:
            return prestige ** (1. / 3.)
        return -(-prestige) ** (1. / 3.)

    def get_bonus_resources(self, base_amount, random_percentage=None):
        """Calculates the amount of bonus resources we get from prestige."""
        mod = self.prestige_mod
        bonus = (mod * base_amount)/100.0
        if random_percentage is not None:
            bonus = (bonus * randint(50, random_percentage))/100.0
        return int(bonus)

    def get_bonus_income(self, base_amount):
        """Calculates the bonus to domain/org income we get from prestige."""
        return self.get_bonus_resources(base_amount)/4

    def _get_owner(self):
        if self.player:
            return self.player
        if self.organization_owner:
            return self.organization_owner
        return None
    owner = property(_get_owner)

    def __unicode__(self):
        return "%s" % self.owner

    def __repr__(self):
        return "<Owner (#%s): %s>" % (self.id, self.owner)

    @property
    def grandeur(self):
        """Value used for prestige that represents prestige from external sources"""
        if self.organization_owner:
            return self.get_grandeur_from_members()
        val = 0
        val += self.get_grandeur_from_patron()
        val += self.get_grandeur_from_proteges()
        val += self.get_grandeur_from_orgs()
        return val

    @property
    def base_grandeur(self):
        """The amount we contribute to other people when they're totalling up grandeur"""
        return int(self.fame/10.0 + self.total_legend/10.0 + self.propriety/10.0)

    def get_grandeur_from_patron(self):
        """Gets our grandeur value from our patron, if we have one"""
        try:
            return self.player.patron.assets.base_grandeur
        except AttributeError:
            return 0

    def get_grandeur_from_proteges(self):
        """Gets grandeur value from each of our proteges, if any"""
        base = 0
        for protege in self.player.proteges.all():
            base += protege.assets.base_grandeur
        return base

    def get_grandeur_from_orgs(self):
        """Gets grandeur value from orgs we're a member of."""
        base = 0
        memberships = list(self.player.memberships.filter(deguilded=False, secret=False,
                                                          organization__secret=False).distinct())
        too_many_org_penalty = max(len(memberships) * 0.5, 1.0)
        for member in memberships:
            rank_divisor = max(member.rank, 1)
            grandeur = member.organization.assets.base_grandeur / rank_divisor
            grandeur /= too_many_org_penalty
            base += grandeur
        return int(base)

    def get_grandeur_from_members(self):
        """Gets grandeur for an org from its members"""
        base = 0
        members = list(self.organization_owner.active_members)
        ranks = 0
        for member in members:
            rank_divisor = max(member.rank, 1)
            grandeur = member.player.assets.base_grandeur / rank_divisor
            base += grandeur
            ranks += 11 - member.rank
        too_many_members_mod = max(ranks/200.0, 0.01)
        base /= too_many_members_mod
        sign = -1 if base < 0 else 1
        return min(abs(int(base)), abs(self.fame + self.legend) * 2) * sign

    def adjust_prestige(self, value, force=False):
        """
        Adjusts our prestige. We gain fame equal to the value, and then our legend is modified
        if the value of the hit is greater than our current legend or the force flag is set.
        """
        self.fame += value
        if value > self.legend or force:
            self.legend += value / 100
        self.save()

    @CachedProperty
    def income(self):
        income = 0
        if self.organization_owner:
            income += self.organization_owner.amount
        for amt in self.incomes.filter(do_weekly=True).exclude(category="vassal taxes"):
            income += amt.weekly_amount
        if not hasattr(self, 'estate'):
            return income
        for domain in self.estate.holdings.all():
            income += domain.total_income
        return income

    @CachedProperty
    def costs(self):
        costs = 0
        for debt in self.debts.filter(do_weekly=True).exclude(category="vassal taxes"):
            costs += debt.weekly_amount
        for army in self.armies.filter(domain__isnull=True):
            costs += army.costs
        for army in self.loaned_armies.filter(domain__isnull=True):
            costs += army.costs
        if not hasattr(self, 'estate'):
            return costs
        for domain in self.estate.holdings.all():
            costs += domain.costs
        return costs

    def _net_income(self):
        return self.income - self.costs

    net_income = property(_net_income)

    @property
    def inform_target(self):
        """
        Determines who should get some sort of inform for this assetowner
        """
        if self.player and self.player.player:
            target = self.player.player
        else:
            target = self.organization_owner
        return target

    def prestige_decay(self):
        """Decreases our fame for the week"""
        self.fame -= int(self.fame * PRESTIGE_DECAY_AMOUNT)
        self.save()

    def do_weekly_adjustment(self, week, inform_creator=None):
        """
        Does weekly adjustment of all monetary/prestige stuff for this asset owner and all their holdings. A report
        is generated and sent to the owner.

            Args:
                week (int): The week where this occurred
                inform_creator: A bulk inform creator, if any

            Returns:
                The amount our vault changed.
        """
        amount = 0
        report = None
        npc = True
        inform_target = self.inform_target
        org = self.organization_owner
        if inform_target and inform_target.can_receive_informs:
            report = WeeklyReport(inform_target, week, inform_creator)
            npc = False
        if hasattr(self, 'estate'):
            for domain in self.estate.holdings.all():
                amount += domain.do_weekly_adjustment(week, report, npc)
        for agent in self.agents.all():
            amount -= agent.cost
        # WeeklyTransactions
        for income in self.incomes.filter(do_weekly=True):
            amount += income.process_payment(report)
            # income.post_repeat()
        if org:
            # record organization's income
            amount += self.organization_owner.amount

        # debts that won't be processed by someone else's income, since they have no receiver
        for debt in self.debts.filter(receiver__isnull=True, do_weekly=True):
            amount -= debt.amount
        self.vault += amount
        self.save()
        if (self.player and self.player.player and hasattr(self.player.player, 'roster')
                and self.player.player.roster.roster.name == "Active"):
            self.player.pay_lifestyle(report)
        if report:
            report.record_income(self.vault, amount)
            report.send_report()
        return amount

    def display(self):
        """Returns formatted string display of this AssetOwner"""
        msg = "{wName{n: %s\n" % self.owner
        msg += "{wVault{n: %s\n" % self.vault
        msg += "{wPrestige{n: %s\n" % self.grandeur
        if hasattr(self, 'estate'):
            msg += "{wHoldings{n: %s\n" % ", ".join(str(dom) for dom in self.estate.holdings.all())
        msg += "{wAgents{n: %s\n" % ", ".join(str(agent) for agent in self.agents.all())
        return msg

    def inform_owner(self, message, category=None, week=0, append=False):
        """Sends an inform to our owner."""
        target = self.inform_target
        if not week:
            week = get_week()
        if target:
            target.inform(message, category=category, week=week, append=append)

    # alias for inform_owner
    inform = inform_owner

    def access(self, accessing_obj, access_type='agent', default=False):
        """Performs access check on our owner for accessing_obj"""
        if self.organization_owner:
            return self.organization_owner.access(accessing_obj, access_type, default)
        # it's a player, check if it's our player
        if self.player.player == accessing_obj:
            return True
        # it's a character, check if it's the character of our player
        try:
            return accessing_obj.player_ob == self.player.player
        except AttributeError:
            return default

    def can_be_viewed_by(self, player):
        """Helper method to quickly show whether a player can view us"""
        if player.check_permstring("builders"):
            return True
        return self.access(player, "withdraw") or self.access(player, "viewassets")


class Propriety(SharedMemoryModel):
    """
    Tags that can be attached to a given AssetOwner that represent societal approval or
    disapproval. These act as percentile modifiers to their fame.
    """
    name = models.CharField(unique=True, max_length=120)
    percentage = models.SmallIntegerField(default=0)
    owners = models.ManyToManyField('AssetOwner', related_name="proprieties")

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        """Override of save to clear cache in associated owners when changed"""
        super(Propriety, self).save(*args, **kwargs)
        if self.pk:
            for owner in self.owners.all():
                owner.clear_cached_properties()


class Honorific(SharedMemoryModel):
    """
    A record of a significant action that permanently alters the legend of an AssetOwner,
    bringing them fame or notoriety.
    """
    owner = models.ForeignKey('AssetOwner', related_name="honorifics")
    title = models.CharField(db_index=True, max_length=200)
    description = models.TextField()
    amount = models.IntegerField(default=0)

    def save(self, *args, **kwargs):
        """Clears cache in owner when saved"""
        super(Honorific, self).save(*args, **kwargs)
        self.owner.clear_cached_properties()

    def delete(self, *args, **kwargs):
        """Clears cache in owner when deleted"""
        if self.owner:
            self.owner.clear_cached_properties()
        super(Honorific, self).delete(*args, **kwargs)


class PraiseOrCondemn(SharedMemoryModel):
    """
    Praises or Condemns are a record of someone trying to influence public opinion to increase
    a character's prestige.
    """
    praiser = models.ForeignKey('PlayerOrNpc', related_name='praises_given')
    target = models.ForeignKey('AssetOwner', related_name='praises_received')
    message = models.TextField(blank=True)
    week = models.PositiveSmallIntegerField(default=0, blank=0)
    db_date_created = models.DateTimeField(auto_now_add=True)
    value = models.IntegerField(default=0)
    number_used = models.PositiveSmallIntegerField(help_text="Number of praises/condemns used from weekly pool",
                                                   default=1)

    @property
    def verb(self):
        """Helper property for distinguishing which verb to use in strings"""
        return "praised" if self.value >= 0 else 'condemned'

    def do_prestige_adjustment(self):
        """Adjusts the prestige of the target after they're praised."""
        self.target.adjust_prestige(self.value)
        msg = "%s has %s you. " % (self.praiser, self.verb)
        msg += "Your prestige has been adjusted by %s." % self.value
        self.target.inform(msg, category=self.verb.capitalize())


class CharitableDonation(SharedMemoryModel):
    """
    Represents all donations from a character to an Organization or Npc Group. They receive some affection
    and prestige in exchange for giving silver.
    """
    giver = models.ForeignKey('AssetOwner', related_name='donations')
    organization = models.ForeignKey('Organization', related_name='donations', blank=True, null=True)
    npc_group = models.ForeignKey('InfluenceCategory', related_name='donations', blank=True, null=True)
    amount = models.PositiveIntegerField(default=0)

    @property
    def receiver(self):
        """Alias to return the receiver of the donation"""
        return self.organization or self.npc_group

    def __str__(self):
        return str(self.receiver)

    def donate(self, value, caller):
        """
        Handles adding more to their donations to this group in exchange for prestige. Caller might be a
        different individual than the giver in order to use their social stats for the prestige roll.
        """
        from world.stats_and_skills import do_dice_check
        self.amount += value
        self.save()
        character = self.giver.player.player.char_ob
        roll = do_dice_check(caller=caller, stat="charm", skill="propaganda", difficulty=10)
        roll += caller.social_clout
        if roll <= 1:
            roll = 1
        roll /= 100.0
        roll *= value/2.0
        prest = int(roll)
        self.giver.adjust_prestige(prest)
        player = self.giver.player
        if caller != character:
            msg = "%s donated %s silver to %s on your behalf.\n" % (caller, value, self.receiver)
        else:
            msg = "You donate %s silver to %s.\n" % (value, self.receiver)
        if self.organization and player:
            reputation = player.reputations.filter(organization=self.organization).first()
            affection = 0
            respect = 0
            if reputation:
                if roll < reputation.affection:
                    msg += " Though the charity is appreciated, your reputation" \
                           " with %s does not change. Ingrates.\n" % self.organization
                else:
                    affection += 1
            else:
                affection += 1
            if affection:
                player.gain_reputation(self.organization, affection, respect)
                val = affection
                msg += "You gain %s affection with %s.\n" % (val, self.organization)
            self.organization.assets.adjust_prestige(prest)
            msg += "%s has gained %s prestige.\n" % (self.organization, prest)
        if caller != character:
            caller.msg("You donated and they gain %s prestige." % prest)
            msg += "You gain %s prestige." % prest
            player.inform(msg)
        else:
            msg += "You gain %s prestige." % prest
            player.msg(msg)
        return prest


class AccountTransaction(SharedMemoryModel):
    """
    Represents both income and costs that happen on a weekly
    basis. This is stored in those receiving the money as
    object.Dominion.assets.incomes, and the object who is sending
    the money as object.Dominion.assets.debts. During weekly adjustment,
    those who have it stored as an income have the amount added to
    their bank_amount stored in assets.money.bank_amount, and those
    have it as a debt have the same value subtracted.
    """
    receiver = models.ForeignKey('AssetOwner', related_name='incomes', blank=True, null=True, db_index=True)

    sender = models.ForeignKey('AssetOwner', related_name='debts', blank=True, null=True, db_index=True)
    # quick description of the type of transaction. taxes between liege/vassal, etc
    category = models.CharField(blank=True, null=True, max_length=255)

    weekly_amount = models.PositiveIntegerField(default=0, blank=0)

    # if this is false, this is a debt that continues to accrue
    do_weekly = models.BooleanField(default=True, blank=True)

    repetitions_left = models.SmallIntegerField(default=-1, blank=-1)

    def post_repeat(self):
        """If this is a transaction that only happens X times, we count down."""
        if self.repetitions_left > 0:
            self.repetitions_left -= 1
        elif self.repetitions_left < 0:
            return
        if self.repetitions_left == 0:
            self.delete()
        else:
            self.save()

    def _get_amount(self):
        return self.weekly_amount

    def __unicode__(self):
        receiver = self.receiver
        if receiver:
            receiver = receiver.owner
        sender = self.sender
        if sender:
            sender = sender.owner
        return "%s -> %s. Amount: %s" % (sender, receiver, self.weekly_amount)

    def process_payment(self, report=None):
        """
        If sender can't pay, return 0. Else, subtract their money
        and return the amount paid.
        """
        sender = self.sender
        if not sender:
            return self.weekly_amount
        if self.can_pay:
            if report:
                report.add_payment(self)
            sender.vault -= self.weekly_amount
            sender.save()
            return self.weekly_amount
        else:
            if report:
                report.payment_fail(self)
            return 0

    amount = property(_get_amount)

    @property
    def can_pay(self):
        """prevent possible caching errors with a refresh check on sender, and then check if they can pay"""
        self.sender.refresh_from_db()
        return self.sender.vault >= self.weekly_amount

    def save(self, *args, **kwargs):
        """Saves changes and clears any caches"""
        super(AccountTransaction, self).save(*args, **kwargs)
        if self.sender:
            self.sender.clear_cached_properties()
        if self.receiver:
            self.receiver.clear_cached_properties()


class Region(SharedMemoryModel):
    """
    A region of Land squares. The 'origin' x,y coordinates are by our convention
    the 'southwest' corner of the region, though builders will not be held to that
    constraint - it's just to get a feel for where each region is situated without
    precise list of their dimensions.
    """
    name = models.CharField(max_length=80, blank=True, null=True)
    # the Southwest corner of the region
    origin_x_coord = models.SmallIntegerField(default=0, blank=0)
    origin_y_coord = models.SmallIntegerField(default=0, blank=0)

    color_code = models.CharField(max_length=8, blank=True)

    def __unicode__(self):
        return self.name or "Unnamed Region (#%s)" % self.id

    def __repr__(self):
        return "<Region: %s(#%s)>" % (self.name, self.id)


class Land(SharedMemoryModel):
    """
    A Land square on the world grid. It contains coordinates of its map space,
    the type of terrain it has, and is part of a region. It can contain many
    different domains of different lords, all of which have their own economies
    and militaries. It is a 100 square mile area, with domains taking up free space
    within the square.
    """
    # region types
    COAST = 1
    DESERT = 2
    GRASSLAND = 3
    HILL = 4
    MOUNTAIN = 5
    OCEAN = 6
    PLAINS = 7
    SNOW = 8
    TUNDRA = 9
    FOREST = 10
    JUNGLE = 11
    MARSH = 12
    ARCHIPELAGO = 13
    FLOOD_PLAINS = 14
    ICE = 15
    LAKES = 16
    OASIS = 17

    TERRAIN_CHOICES = (
        (COAST, 'Coast'),
        (DESERT, 'Desert'),
        (GRASSLAND, 'Grassland'),
        (HILL, 'Hill'),
        (MOUNTAIN, 'Mountain'),
        (OCEAN, 'Ocean'),
        (PLAINS, 'Plains'),
        (SNOW, 'Snow'),
        (TUNDRA, 'Tundra'),
        (FOREST, 'Forest'),
        (JUNGLE, 'Jungle'),
        (MARSH, 'Marsh'),
        (ARCHIPELAGO, 'Archipelago'),
        (FLOOD_PLAINS, 'Flood Plains'),
        (ICE, 'Ice'),
        (LAKES, 'Lakes'),
        (OASIS, 'Oasis'),
        )

    name = models.CharField(max_length=80, blank=True, null=True)
    desc = models.TextField(blank=True, null=True)
    x_coord = models.SmallIntegerField(default=0, blank=0)
    y_coord = models.SmallIntegerField(default=0, blank=0)

    terrain = models.PositiveSmallIntegerField(choices=TERRAIN_CHOICES, default=PLAINS)

    region = models.ForeignKey('Region', on_delete=models.SET_NULL, blank=True, null=True)
    # whether we can have boats here
    landlocked = models.BooleanField(default=True, blank=True)

    objects = LandManager()

    def _get_farming_mod(self):
        """
        Returns an integer that is a percent modifier for farming.
        100% means no change. 0% would imply that farming fails here.
        Food production isn't strictly farming per se, but also includes
        hunting, so 0% would only be accurate if there's nothing living
        there at all that could be hunted.
        """
        min_farm = (Land.DESERT, Land.SNOW, Land.ICE)
        low_farm = (Land.TUNDRA, Land.MARSH, Land.MOUNTAIN)
        # 'farm' also refers to fishing for coast
        high_farm = (Land.COAST, Land.LAKES, Land.PLAINS, Land.GRASSLAND, Land.FLOOD_PLAINS)
        if self.terrain in min_farm:
            return 25
        if self.terrain in low_farm:
            return 50
        if self.terrain in high_farm:
            return 125
        return 100

    def _get_mining_mod(self):
        high_mine = (Land.HILL, Land.MOUNTAIN)
        if self.terrain in high_mine:
            return 125
        return 100

    def _get_lumber_mod(self):
        # may add more later. comma is necessary to make it a tuple, otherwise not iterable
        high_lumber = (Land.FOREST,)
        if self.terrain in high_lumber:
            return 125
        return 100
    farm_mod = property(_get_farming_mod)
    mine_mod = property(_get_mining_mod)
    lumber_mod = property(_get_lumber_mod)

    def _get_occupied_area(self):
        total_area = 0
        for location in self.locations.all():
            for domain in location.domains.all():
                total_area += domain.area
        return total_area
    occupied_area = property(_get_occupied_area)

    def _get_hostile_area(self):
        total_area = 0
        for hostile in self.hostiles.all():
            total_area += hostile.area
        return total_area
    hostile_area = property(_get_hostile_area)

    def _get_free_area(self):
        return LAND_SIZE - (self.occupied_area + self.hostile_area)
    free_area = property(_get_free_area)

    def __unicode__(self):
        return self.name

    def __repr__(self):
        name = self.name or "(%s, %s)" % (self.x_coord, self.y_coord)
        return "<Land (#%s): %s>" % (self.id, name)


class HostileArea(SharedMemoryModel):
    """
    This is an area on a land square that isn't a domain, but is
    also considered uninhabitable. It could be because of a group
    of bandits, a massive monster, fell magic, dead and barren
    land, whatever. If we contain hostile units, then they're contained
    in the self.hostiles property.
    """
    land = models.ForeignKey('Land', related_name='hostiles', blank=True, null=True)
    desc = models.TextField(blank=True, null=True)
    from django.core.validators import MaxValueValidator
    area = models.PositiveSmallIntegerField(validators=[MaxValueValidator(LAND_SIZE)], default=0, blank=0)
    # the type of hostiles controlling this area
    type = models.PositiveSmallIntegerField(default=0, blank=0)
    # we'll have HostileArea.units.all() to describe any military forces we have

    def _get_units(self):
        return self.units.all()
    hostiles = property(_get_units)


class MapLocation(SharedMemoryModel):
    """
    A simple model that maps a given map location, for use with Domains, Landmarks,
    and Shardhavens.
    """
    name = models.CharField(blank=True, null=True, max_length=80)
    land = models.ForeignKey('Land', on_delete=models.SET_NULL, related_name='locations', blank=True, null=True)
    from django.core.validators import MaxValueValidator
    x_coord = models.PositiveSmallIntegerField(validators=[MaxValueValidator(LAND_COORDS)], default=0)
    y_coord = models.PositiveSmallIntegerField(validators=[MaxValueValidator(LAND_COORDS)], default=0)

    def __str__(self):
        if self.name:
            label = self.name
        else:
            label = "(#%d)" % self.id

            def label_maker(such_items):
                """Format names of each object in Location"""
                return "[%s] " % ", ".join(wow.name for wow in such_items)
            if self.landmarks.all():
                label += label_maker(self.landmarks.all())
            if self.shardhavens.all():
                label += label_maker(self.shardhavens.all())
            if self.domains.all():
                label += label_maker(self.domains.all())
            else:
                label = "%s - sub %d, %d" % (self.land, self.x_coord, self.y_coord)
        return label


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
    location = models.ForeignKey('MapLocation', on_delete=models.SET_NULL, related_name='domains',
                                 blank=True, null=True)
    # The house that rules this domain
    ruler = models.ForeignKey('Ruler', on_delete=models.SET_NULL, related_name='holdings', blank=True, null=True,
                              db_index=True)
    # cosmetic info
    name = models.CharField(blank=True, null=True, max_length=80)
    desc = models.TextField(blank=True, null=True)
    title = models.CharField(blank=True, null=True, max_length=255)
    destroyed = models.BooleanField(default=False, blank=False)

    # how much of the territory in our land square we control
    from django.core.validators import MaxValueValidator
    area = models.PositiveSmallIntegerField(validators=[MaxValueValidator(LAND_SIZE)], default=0, blank=0)

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
        tax = float(self.tax_rate)/100.0
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
        return workers/req

    def get_resource_income(self, building, workers):
        """Generates base income from resources"""
        base = SILVER_PER_BUILDING * building
        worker_req = self.required_worker_mod(building, workers)
        return base * worker_req

    def _get_mining_income(self):
        base = self.get_resource_income(self.num_mines, self.mining_serfs)
        if self.land:
            base = (base * self.land.mine_mod)/100.0
        return base

    def _get_lumber_income(self):
        base = self.get_resource_income(self.num_lumber_yards, self.lumber_serfs)
        if self.land:
            base = (base * self.land.lumber_mod)/100.0
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
        amount = (amount * self.income_modifier)/100.0
        global_mod = ServerConfig.objects.conf("GLOBAL_INCOME_MOD", default=DEFAULT_GLOBAL_INCOME_MOD)
        try:
            amount += int(amount * global_mod)
        except (TypeError, ValueError):
            print("Error: Improperly Configured GLOBAL_INCOME_MOD: %s" % global_mod)
        try:
            amount += self.ruler.house.get_bonus_income(amount)
        except AttributeError:
            pass
        if self.ruler and self.ruler.castellan:
            bonus = self.get_bonus('income') * amount
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
        cost *= (100 - self.slave_labor_percentage)/100
        if self.ruler and self.ruler.castellan:
            # every point in upkeep skill reduces cost
            reduction = 1.00 + self.get_bonus('upkeep')
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
            except AccountTransaction.DoesNotExist:
                amt = (self.total_income * self.liege_taxes)/100
                self.ruler.house.debts.create(category="vassal taxes", receiver=self.ruler.liege.house,
                                              weekly_amount=amt)
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
        except AccountTransaction.DoesNotExist:
            transaction = self.ruler.house.debts.create(category="vassal taxes", receiver=self.ruler.liege.house,
                                                        weekly_amount=amt)
        transaction.weekly_amount = amt
        transaction.save()

    def _get_food_production(self):
        """
        How much food the region produces.
        """
        mod = self.required_worker_mod(self.num_farms, self.farming_serfs)
        amount = (self.num_farms * FOOD_PER_FARM) * mod
        if self.ruler and self.ruler.castellan:
            bonus = self.get_bonus('farming') * amount
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
        return self.mill_serfs + self.mining_serfs + self.farming_serfs + self.lumber_serfs

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
            worker_types = ["farming_serfs", "mining_serfs", "mill_serfs", "lumber_serfs"]
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
        max_pillage = army.size/10
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
            bonus = float(self.max_pop)/self.total_serfs
            if self.ruler and self.ruler.castellan:
                bonus += bonus * self.get_bonus('population')
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

    def __unicode__(self):
        return "%s (#%s)" % (self.name or 'Unnamed Domain', self.id)

    def __repr__(self):
        return "<Domain (#%s): %s>" % (self.id, self.name or 'Unnamed')

    def do_weekly_adjustment(self, week, report=None, npc=False):
        """
        Determine how much money we're passing up to the ruler of our domain. Make
        all the people and armies of this domain eat their food for the week. Bad
        things will happen if they don't have enough food.
        """
        if npc:
            return self.total_income - self.costs
        self.stored_food += self.food_production
        self.stored_food += self.shipped_food
        hunger = self.food_consumption - self.stored_food
        loot = 0
        if hunger > 0:
            self.stored_food = 0
            self.lawlessness += 5
            # unless we have a very large population, we'll only lose 1 serf as a penalty
            lost_serfs = hunger / 100 + 1
            self.kill_serfs(lost_serfs)
        else:  # hunger is negative, we have enough food for it
            self.stored_food += hunger
        for army in self.armies.all():
            army.do_weekly_adjustment(week, report)
            if army.plunder:
                loot += army.plunder
                army.plunder = 0
                army.save()
        self.adjust_population()
        for project in list(self.projects.all()):
            project.advance_project(report)
        total_amount = (self.total_income + loot) - self.costs
        # reset the amount of money that's been plundered from us
        self.amount_plundered = 0
        self.save()
        self.reset_expected_tax_payment()
        return total_amount

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
                mssg += "  {c%s{n   {wCategory:{n %s  {wTitle:{n %s\n" % (minister.player,
                                                                          minister.get_category_display(),
                                                                          minister.title)
        mssg += "{wDesc{n: %s\n" % self.desc
        mssg += "{wArea{n: %s {wFarms{n: %s {wHousing{n: %s " % (self.area, self.num_farms, self.num_housing)
        mssg += "{wMines{n: %s {wLumber{n: %s {wMills{n: %s\n" % (self.num_mines, self.num_lumber_yards, self.num_mills)
        mssg += "{wTotal serfs{n: %s " % self.total_serfs
        mssg += "{wAssignments: Mines{n: %s {wMills{n: %s " % (self.mining_serfs, self.mill_serfs)
        mssg += "{wLumber yards:{n %s {wFarms{n: %s\n" % (self.lumber_serfs, self.farming_serfs)
        mssg += "{wTax Rate{n: %s {wLawlessness{n: %s " % (self.tax_rate, self.lawlessness)
        mssg += "{wCosts{n: %s {wIncome{n: %s {wLiege's tax rate{n: %s\n" % (self.costs, self.total_income,
                                                                             self.liege_taxes)
        mssg += "{wFood Production{n: %s {wFood Consumption{n: %s {wStored Food{n: %s\n" % (self.food_production,
                                                                                            self.food_consumption,
                                                                                            self.stored_food)
        mssg += "\n{wCastles:{n\n"
        mssg += "{w================================={n\n"
        for castle in self.castles.all():
            mssg += castle.display()
        mssg += "\n{wArmies:{n\n"
        mssg += "{w================================={n\n"
        for army in self.armies.all():
            mssg += army.display()
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

    PROJECT_CHOICES = ((BUILD_HOUSING, 'Build Housing'),
                       (BUILD_FARMS, 'Build Farms'),
                       (BUILD_MINES, 'Build Mines'),
                       (BUILD_MILLS, 'Build Mills'),
                       (BUILD_DEFENSES, 'Build Defenses'),
                       (BUILD_SIEGE_WEAPONS, 'Build Siege Weapons'),
                       (MUSTER_TROOPS, 'Muster Troops'),
                       (BUILD_TROOP_EQUIPMENT, 'Build Troop Equipment'),)

    type = models.PositiveSmallIntegerField(choices=PROJECT_CHOICES, default=BUILD_HOUSING)
    amount = models.PositiveSmallIntegerField(blank=1, default=1)
    unit_type = models.PositiveSmallIntegerField(default=1, blank=1)
    time_remaining = models.PositiveIntegerField(default=1, blank=1)
    domain = models.ForeignKey("Domain", related_name="projects", blank=True, null=True)
    castle = models.ForeignKey("Castle", related_name="projects", blank=True, null=True)
    military = models.ForeignKey("Army", related_name="projects", blank=True, null=True)
    unit = models.ForeignKey("MilitaryUnit", related_name="projects", blank=True, null=True)

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
                self.military.units.create(unit_type=self.unit_type, quantity=self.amount)
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
        (MOTTE_AND_BAILEY, 'Motte and Bailey'),
        (TIMBER_CASTLE, 'Timber Castle'),
        (STONE_CASTLE, 'Stone Castle'),
        (CASTLE_WITH_CURTAIN_WALL, 'Castle with Curtain Wall'),
        (FORTIFIED_CASTLE, 'Fortified Castle'),
        (EPIC_CASTLE, 'Epic Castle'))
    level = models.PositiveSmallIntegerField(default=MOTTE_AND_BAILEY)
    domain = models.ForeignKey("Domain", related_name="castles", blank=True, null=True)
    damage = models.PositiveSmallIntegerField(default=0, blank=0)
    # cosmetic info:
    name = models.CharField(null=True, blank=True, max_length=80)
    desc = models.TextField(null=True, blank=True)

    def display(self):
        """Returns formatted string for a castle's display"""
        msg = "{wName{n: %s {wLevel{n: %s (%s)\n" % (self.name, self.level, self.get_level_display())
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

    def __unicode__(self):
        return "%s (#%s)" % (self.name or "Unnamed Castle", self.id)

    def __repr__(self):
        return "<Castle (#%s): %s>" % (self.id, self.name)


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
    castellan = models.OneToOneField("PlayerOrNpc", blank=True, null=True)
    # the house that owns the domain
    house = models.OneToOneField("AssetOwner", on_delete=models.SET_NULL, related_name="estate", blank=True, null=True)
    # a ruler object that this object owes its alliegance to
    liege = models.ForeignKey("self", on_delete=models.SET_NULL, related_name="vassals", blank=True, null=True,
                              db_index=True)

    def _get_titles(self):
        return ", ".join(domain.title for domain in self.domains.all())
    titles = property(_get_titles)

    def __unicode__(self):
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
        except (Minister.DoesNotExist, Minister.MultipleObjectsReturned, AttributeError):
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
        return sum(ob.weekly_amount for ob in self.house.incomes.filter(category="vassal taxes"))

    @property
    def liege_taxes(self):
        """Total silver we pay to our liege"""
        if not self.house:
            return 0
        return sum(ob.weekly_amount for ob in self.house.debts.filter(category="vassal taxes"))

    def clear_domain_cache(self):
        """Clears cache for all domains under our rule"""
        for domain in self.holdings.all():
            domain.clear_cached_properties()


class Plot(SharedMemoryModel):
    """
    A plot being run in the game. This can either be a crisis affecting organizations or the entire gameworld,
    a gm plot for some subset of players, a player-run plot for players, or a subplot of any of the above. In
    general, a crisis is a type of plot that allows offscreen actions to be submitted and is resolved at regular
    intervals: This is more or less intended for large-scale events. GM Plots and Player Run Plots will tend to
    be focused on smaller groups of players.
    """
    CRISIS, GM_PLOT, PLAYER_RUN_PLOT, PITCH = range(4)
    USAGE_CHOICES = ((CRISIS, "Crisis"), (GM_PLOT, "GM Plot"), (PLAYER_RUN_PLOT, "Player-Run Plot"),
                     (PITCH, "Pitch"))
    name = models.CharField(blank=True, null=True, max_length=255, db_index=True)
    usage = models.SmallIntegerField(choices=USAGE_CHOICES, default=CRISIS)
    headline = models.CharField("News-style bulletin", max_length=255, blank=True, null=True)
    desc = models.TextField(blank=True, null=True)
    orgs = models.ManyToManyField('Organization', related_name='plots', blank=True, through="OrgPlotInvolvement")
    dompcs = models.ManyToManyField('PlayerOrNpc', blank=True, related_name='plots', through="PCPlotInvolvement",
                                    through_fields=("plot", "dompc"))
    parent_plot = models.ForeignKey('self', related_name="subplots", blank=True, null=True, on_delete=models.SET_NULL)
    escalation_points = models.SmallIntegerField(default=0, blank=0)
    results = models.TextField(blank=True, null=True)
    modifiers = models.TextField(blank=True, null=True)
    public = models.BooleanField(default=True, blank=True)
    required_clue = models.ForeignKey('character.Clue', related_name="crises", blank=True, null=True,
                                      on_delete=models.SET_NULL)
    resolved = models.BooleanField(default=False)
    start_date = models.DateTimeField(blank=True, null=True)
    end_date = models.DateTimeField(blank=True, null=True)
    chapter = models.ForeignKey('character.Chapter', related_name="crises", blank=True, null=True,
                                on_delete=models.SET_NULL)
    search_tags = models.ManyToManyField("character.SearchTag", blank=True, related_name="plots")
    objects = CrisisManager()

    class Meta:
        """Define Django meta options"""
        verbose_name_plural = "Plots"

    def __str__(self):
        return self.name

    @property
    def time_remaining(self):
        """Returns timedelta of how much time is left before the crisis updates"""
        now = datetime.now()
        if self.end_date and self.end_date > now:
            return self.end_date - now

    @property
    def rating(self):
        """Returns how much rating is left in our crisis"""
        if self.escalation_points:
            return self.escalation_points - sum(ob.outcome_value for ob in self.actions.filter(
                status=PlotAction.PUBLISHED))

    @property
    def beats(self):
        """Returns updates that have descs written, meaning they aren't pending/future events."""
        return self.updates.exclude(desc="")

    def display_base(self):
        """Common plot display information"""
        msg = "|w[%s|w]{n" % self
        if self.rating:
            msg += " |w(%s Rating)|n" % self.rating
        if self.time_remaining:
            msg += " {yTime Remaining:{n %s" % str(self.time_remaining).split(".")[0]
        msg += "\n%s" % self.desc
        return msg

    def display(self, display_connected=True, staff_display=False):
        """Returns string display for the plot and its latest update/beat"""
        msg = self.display_base()
        beats = list(self.beats)
        if display_connected:
            orgs, clue, cast = self.orgs.all(), self.required_clue, self.cast_list
            if clue:
                msg += "\n{wRequired Clue:{n %s" % self.required_clue
            if staff_display:
                subplots, clues, revs = self.subplots.all(), self.clues.all(), self.revelations.all()
                if self.parent_plot:
                    msg += "\n{wMain Plot:{n %s (#%s)" % (self.parent_plot, self.parent_plot.id)
                if subplots:
                    msg += "\n{wSubplots:{n %s" % ", ".join(("%s (#%s)" % (ob, ob.id)) for ob in subplots)
                if clues:
                    msg += "\n{wClues:{n %s" % "; ".join(("%s (#%s)" % (ob, ob.id)) for ob in clues)
                if revs:
                    msg += "\n{wRevelations:{n %s" % "; ".join(("%s (#%s)" % (ob, ob.id)) for ob in revs)
            if cast:
                msg += "\n%s" % cast
            if orgs:
                msg += "\n{wInvolved Organizations:{n %s" % ", ".join(str(ob) for ob in orgs)
        if beats:
            last = beats[-1]
            if self.usage in (self.PLAYER_RUN_PLOT, self.GM_PLOT):
                msg += "\n{wBeat IDs:{n %s" % ", ".join(str(ob.id) for ob in beats)
            msg += "\n%s" % last.display_beat(display_connected=display_connected)
        return msg

    def display_timeline(self):
        """Base plot description plus all beats/updates displays"""
        msg = self.display_base() + "\n"
        beats = list(self.beats)
        msg += "\n".join([ob.display_beat() for ob in beats])
        return msg

    def check_taken_action(self, dompc):
        """Whether player has submitted action for the current crisis update."""
        return self.actions.filter(Q(dompc=dompc) & Q(beat__isnull=True)
                                   & ~Q(status__in=(PlotAction.DRAFT, PlotAction.CANCELLED))).exists()

    def raise_submission_errors(self):
        """Raises errors if it's not valid to submit an action for this crisis"""
        if self.resolved:
            raise ActionSubmissionError("%s has been marked as resolved." % self)
        if self.end_date and datetime.now() > self.end_date:
            raise ActionSubmissionError("It is past the deadline for %s." % self)

    def raise_creation_errors(self, dompc):
        """Raise errors if dompc shouldn't be allowed to submit an action for this crisis"""
        self.raise_submission_errors()
        if self.check_taken_action(dompc=dompc):
            raise ActionSubmissionError("You have already submitted an action for this stage of the crisis.")

    def create_update(self, gemit_text, caller=None, gm_notes=None, do_gemit=True,
                      episode_name=None, episode_synopsis=None):
        """
        Creates an update for the crisis. An update functions as saying the current round/turn of actions is
        over, and announces to the game a synopsis of what occurred. After the update, if the crisis is not
        resolved, players would be free to put in another action.
        Args:
            gemit_text: Summary of what happened in this update
            caller: The GM who published this
            gm_notes: Notes to other GMs about what happened
            do_gemit: Whether to announce this to the whole game
            episode_name: The name of the episode this happened during
            episode_synopsis: Summary of an episode if we're creating one
        """
        from server.utils.arx_utils import broadcast_msg_and_post
        gm_notes = gm_notes or ""
        from web.character.models import Episode, Chapter
        if not episode_name:
            latest_episode = Episode.objects.last()
        else:
            latest_episode = Chapter.objects.last().episodes.create(name=episode_name, synopsis=episode_synopsis)
        update = self.updates.create(date=datetime.now(), desc=gemit_text, gm_notes=gm_notes, episode=latest_episode)
        qs = self.actions.filter(status__in=(PlotAction.PUBLISHED, PlotAction.PENDING_PUBLISH,
                                             PlotAction.CANCELLED), beat__isnull=True)
        pending = []
        already_published = []
        for action in qs:
            if action.status == PlotAction.PENDING_PUBLISH:
                action.send(update=update, caller=caller)
                pending.append(str(action.id))
            else:
                action.update = update
                action.save()
                already_published.append(str(action.id))
        if do_gemit:
            broadcast_msg_and_post(gemit_text, caller, episode_name=latest_episode.name)
        pending = "Pending actions published: %s" % ", ".join(pending)
        already_published = "Already published actions for this update: %s" % ", ".join(already_published)
        post = "Gemit:\n%s\nGM Notes: %s\n%s\n%s" % (gemit_text, gm_notes, pending, already_published)
        subject = "Update for %s" % self
        inform_staff("Crisis update posted by %s for %s:\n%s" % (caller, self, post), post=True, subject=subject)

    def check_can_view(self, user):
        """Checks if user can view this plot"""
        if self.public:
            return True
        if not user or not user.is_authenticated():
            return False
        if user.is_staff or user.check_permstring("builders"):
            return True
        return self.required_clue in user.roster.clues.all()

    @property
    def finished_actions(self):
        """Returns queryset of all published actions"""
        return self.actions.filter(status=PlotAction.PUBLISHED)

    def get_viewable_actions(self, user):
        """Returns actions that the user can view - published actions they participated in, or all if they're staff."""
        if not user or not user.is_authenticated():
            return self.finished_actions.filter(public=True)
        if user.is_staff or user.check_permstring("builders"):
            return self.finished_actions
        dompc = user.Dominion
        return self.finished_actions.filter(Q(dompc=dompc) | Q(assistants=dompc)).order_by('-date_submitted')

    def add_dompc(self, dompc, status=None, recruiter=None):
        """Invites a dompc to join the plot."""
        from server.utils.exceptions import CommandError
        status_types = [ob[1].split()[0].lower() for ob in PCPlotInvolvement.CAST_STATUS_CHOICES]
        del status_types[-1]
        status = status if status else "main"
        if status not in status_types:
            raise CommandError("Status must be one of these: %s" % ", ".join(status_types))
        try:
            involvement = self.dompc_involvement.get(dompc_id=dompc.id)
            if involvement.activity_status <= PCPlotInvolvement.INVITED:
                raise CommandError("They are already invited.")
        except PCPlotInvolvement.DoesNotExist:
            involvement = PCPlotInvolvement(dompc=dompc, plot=self)
        involvement.activity_status = PCPlotInvolvement.INVITED
        involvement.cast_status = status_types.index(status)
        involvement.save()
        inf_msg = "You have been invited to join plot '%s'" % self
        inf_msg += (" by %s" % recruiter) if recruiter else ""
        inf_msg += ". Use 'plots %s' for details, including other participants. " % self.id
        inf_msg += "To accept this invitation, use the following command: "
        inf_msg += "plots/accept %s[=<IC description of character's involvement>]." % self.id
        if recruiter:
            inf_msg += "\nIf you accept, a small XP reward can be given to %s (and yourself) with: " % recruiter
            inf_msg += "'plots/rewardrecruiter %s=%s'. For more help see 'help plots'." % (self.id, recruiter)
        dompc.inform(inf_msg, category="Plot Invite")

    @property
    def first_owner(self):
        """Returns the first owner-level PlayerOrNpc, or None"""
        owner_inv = self.dompc_involvement.filter(admin_status=PCPlotInvolvement.OWNER).first()
        if owner_inv:
            return owner_inv.dompc

    @property
    def cast_list(self):
        """Returns string of the cast's status and admin levels."""
        cast = self.dompc_involvement.filter(activity_status__lte=PCPlotInvolvement.INVITED).order_by('cast_status')
        msg = "Involved Characters:\n" if cast else ""
        for role in cast:
            invited = "*Invited* " if role.activity_status == role.INVITED else ""
            msg += "%s|c%s|n" % (invited, role.dompc)
            status = []
            if role.cast_status <= 2:
                status.append(role.get_cast_status_display())
            if role.admin_status >= 2:
                status.append(role.get_admin_status_display())
            if any(status):
                msg += " (%s)" % ", ".join([ob for ob in status])
            msg += "\n"
        return msg


class OrgPlotInvolvement(SharedMemoryModel):
    """An org's participation in a plot"""
    plot = models.ForeignKey("Plot", related_name="org_involvement")
    org = models.ForeignKey("Organization", related_name="plot_involvement")
    auto_invite_members = models.BooleanField(default=False)
    gm_notes = models.TextField(blank=True)


class PCPlotInvolvement(SharedMemoryModel):
    """A character's participation in a plot"""
    REQUIRED_CAST, MAIN_CAST, SUPPORTING_CAST, EXTRA, TANGENTIAL = range(5)
    ACTIVE, INACTIVE, INVITED, HAS_RP_HOOK, LEFT, NOT_ADDED = range(6)
    SUBMITTER, PLAYER, RECRUITER, GM, OWNER = range(5)
    CAST_STATUS_CHOICES = ((REQUIRED_CAST, "Required Cast"), (MAIN_CAST, "Main Cast"),
                           (SUPPORTING_CAST, "Supporting Cast"),
                           (EXTRA, "Extra"), (TANGENTIAL, "Tangential"))
    ACTIVITY_STATUS_CHOICES = ((ACTIVE, "Active"), (INACTIVE, "Inactive"), (INVITED, "Invited"),
                               (HAS_RP_HOOK, "Has RP Hook"), (LEFT, "Left"), (NOT_ADDED, "Not Added"))
    ADMIN_STATUS_CHOICES = ((OWNER, "Owner"), (GM, "GM"), (RECRUITER, "Recruiter"), (PLAYER, "Player"),
                            (SUBMITTER, "Submitting Player"))
    plot = models.ForeignKey("Plot", related_name="dompc_involvement")
    dompc = models.ForeignKey("PlayerOrNpc", related_name="plot_involvement")
    cast_status = models.PositiveSmallIntegerField(choices=CAST_STATUS_CHOICES, default=MAIN_CAST)
    activity_status = models.PositiveSmallIntegerField(choices=ACTIVITY_STATUS_CHOICES, default=ACTIVE)
    admin_status = models.PositiveSmallIntegerField(choices=ADMIN_STATUS_CHOICES, default=PLAYER)
    recruiter_story = models.TextField(blank=True)
    recruited_by = models.ForeignKey("PlayerOrNpc", blank=True, null=True, related_name="plot_recruits",
                                     on_delete=models.SET_NULL)
    gm_notes = models.TextField(blank=True)

    def __str__(self):
        return str(self.dompc)

    def get_modified_status_display(self):
        """Modifies status display with whether we're a GM"""
        msg = self.get_cast_status_display()
        if self.admin_status > self.PLAYER:
            msg += " (%s)" % self.get_admin_status_display()
        return msg

    def display_plot_involvement(self):
        msg = self.plot.display()
        clues = self.plot.clues.all()
        revs = self.plot.revelations.all()
        theories = self.plot.theories.all()
        our_plots = self.dompc.active_plots.all()
        subplots = set(self.plot.subplots.all()) & set(our_plots)

        def format_name(obj, unknown):
            name = "%s(#%s)" % (obj, obj.id)
            if obj in unknown:
                name += "({rX{n)"
            return name

        if self.plot.parent_plot and self.plot.parent_plot in our_plots:
            # noinspection PyTypeChecker
            msg += "\n{wParent Plot:{n %s" % format_name(self.plot.parent_plot, [])
        if subplots:
            msg += "\n{wSubplots:{n %s" % ", ".join(format_name(ob, []) for ob in subplots)
        if clues:
            msg += "\n{wRelated Clues:{n "
            pc_clues = list(self.dompc.player.roster.clues.all())
            unknown_clues = [ob for ob in clues if ob not in pc_clues]
            msg += "; ".join(format_name(ob, unknown_clues) for ob in clues)
        if revs:
            msg += "\n{wRelated Revelations:{n "
            pc_revs = list(self.dompc.player.roster.revelations.all())
            unknown_revs = [ob for ob in revs if ob not in pc_revs]
            msg += "; ".join(format_name(ob, unknown_revs) for ob in revs)
        if theories:
            msg += "\n{wRelated Theories:{n "
            pc_theories = list(self.dompc.player.known_theories.all())
            unknown_theories = [ob for ob in theories if ob not in pc_theories]
            msg += "; ".join(format_name(ob, unknown_theories) for ob in theories)
        return msg

    def accept_invitation(self, description=""):
        self.activity_status = self.ACTIVE
        if description:
            if self.gm_notes:
                self.gm_notes += "\n"
            self.gm_notes += description
        self.save()

    def leave_plot(self):
        self.activity_status = self.LEFT
        self.save()


class PlotUpdate(SharedMemoryModel):
    """
    Container for showing all the Plot Actions during a period and their corresponding
    result on the crisis
    """
    plot = models.ForeignKey("Plot", related_name="updates", db_index=True)
    desc = models.TextField("Story of what happened this update", blank=True)
    gm_notes = models.TextField("Any ooc notes of consequences", blank=True)
    date = models.DateTimeField(blank=True, null=True)
    episode = models.ForeignKey("character.Episode", related_name="plot_updates", blank=True, null=True,
                                on_delete=models.SET_NULL)
    search_tags = models.ManyToManyField("character.SearchTag", blank=True, related_name="plot_updates")

    @property
    def noun(self):
        return "Beat" if self.plot.usage == Plot.PLAYER_RUN_PLOT else "Update"

    def __str__(self):
        return "%s #%s for %s" % (self.noun, self.id, self.plot)

    def display_beat(self, display_connected=True):
        """Return string display of this update/beat"""
        msg = "|w[%s|w]|n" % self
        if self.date:
            msg += " {wDate{n %s" % self.date.strftime("%x %X")
        msg += "\n%s" % self.desc if self.desc else "\nPending %s placeholder." % self.noun
        if display_connected:
            for attr in ("actions", "events", "emits", "flashbacks"):
                qs = getattr(self, attr).all()
                if qs:
                    msg += "\n{w%s:{n %s" % (attr.capitalize(), ", ".join("%s (#%s)" % (ob, ob.id) for ob in qs))
        return msg


class AbstractAction(AbstractPlayerAllocations):
    """Abstract parent class representing a player's participation in an action"""
    NOUN = "Action"
    BASE_AP_COST = 50
    secret_actions = models.TextField("Secret actions the player is taking", blank=True)
    attending = models.BooleanField(default=True)
    traitor = models.BooleanField(default=False)
    date_submitted = models.DateTimeField(blank=True, null=True)
    editable = models.BooleanField(default=True)
    resource_types = ('silver', 'military', 'economic', 'social', 'ap', 'action points', 'army')
    free_action = models.BooleanField(default=False)
    difficulty = None

    class Meta:
        abstract = True

    @property
    def submitted(self):
        """Whether they've submitted this or not"""
        return bool(self.date_submitted)

    @property
    def ap_refund_amount(self):
        """How much AP to refund"""
        return self.action_points + self.BASE_AP_COST

    def pay_action_points(self, amount):
        """Passthrough method to make the player pay action points"""
        return self.dompc.player.pay_action_points(amount)

    def refund(self):
        """Method for refunding a player's resources, AP, etc."""
        self.pay_action_points(-self.ap_refund_amount)
        for resource in ('military', 'economic', 'social'):
            value = getattr(self, resource)
            if value:
                self.dompc.player.gain_resources(resource, value)
        if self.silver:
            self.dompc.assets.vault += self.silver
            self.dompc.assets.save()

    def check_view_secret(self, caller):
        """Whether caller can view the secret part of this action"""
        if not caller:
            return
        if caller.check_permstring("builders") or caller == self.dompc.player:
            return True

    def get_action_text(self, secret=False, disp_summary=False):
        """Gets the text of their action"""
        noun = self.NOUN
        author = " by {c%s{w" % self.author
        if secret:
            prefix_txt = "Secret "
            action = self.secret_actions
            if self.traitor:
                prefix_txt += "{rTraitorous{w "
            suffix_txt = ":{n %s" % action
        else:
            prefix_txt = ""
            action = self.actions
            if noun == "Action":
                noun = "%s" % self.pretty_str
                author = ""
            summary = ""
            if disp_summary:
                summary = "\n%s" % self.get_summary_text()
            suffix_txt = "%s\n{wAction:{n %s" % (summary, action)
        return "\n{w%s%s%s%s{n" % (prefix_txt, noun, author, suffix_txt)

    def get_summary_text(self):
        """Returns brief formatted summary of this action"""
        return "{wSummary:{n %s" % self.topic

    @property
    def ooc_intent(self):
        """Returns the question that acts as this action's OOC intent - what the player wants"""
        try:
            return self.questions.get(is_intent=True)
        except ActionOOCQuestion.DoesNotExist:
            return None

    def set_ooc_intent(self, text):
        """Sets the action's OOC intent"""
        ooc_intent = self.ooc_intent
        if not ooc_intent:
            self.questions.create(text=text, is_intent=True)
        else:
            ooc_intent.text = text
            ooc_intent.save()

    def ask_question(self, text):
        """Adds an OOC question to GMs by the player"""
        msg = "{c%s{n added a comment/question about Action #%s:\n%s" % (self.author, self.main_id, text)
        inform_staff(msg)
        if self.gm:
            self.gm.inform(msg, category="Action questions")
        return self.questions.create(text=text)

    @property
    def is_main_action(self):
        """Whether this is the main action. False means we're an assist"""
        return self.NOUN == "Action"

    @property
    def author(self):
        """The author of this action - the main originating character who others are assisting"""
        return self.dompc

    def inform(self, text, category="Actions", append=False):
        """Passthrough method to send an inform to the player"""
        self.dompc.inform(text, category=category, append=append)

    def submit(self):
        """Attempts to submit this action. Can raise ActionSubmissionErrors."""
        self.raise_submission_errors()
        self.on_submit_success()

    def on_submit_success(self):
        """If no errors were raised, we mark ourselves as submitted and no longer allow edits."""
        if not self.date_submitted:
            self.date_submitted = datetime.now()
        self.editable = False
        self.save()
        self.post_edit()

    def raise_submission_errors(self):
        """Raises errors if this action is not ready for submission."""
        fields = self.check_incomplete_required_fields()
        if fields:
            raise ActionSubmissionError("Incomplete fields: %s" % ", ".join(fields))
        from server.utils.arx_utils import check_break
        if check_break():
            raise ActionSubmissionError("Cannot submit an action while staff are on break.")

    def check_incomplete_required_fields(self):
        """Returns any required fields that are not yet defined."""
        fields = []
        if not self.actions:
            fields.append("action text")
        if not self.ooc_intent:
            fields.append("ooc intent")
        if not self.topic:
            fields.append("tldr")
        if not self.skill_used or not self.stat_used:
            fields.append("roll")
        return fields

    def post_edit(self):
        """In both child classes this check occurs after a resubmit."""
        pass

    @property
    def plot_attendance(self):
        """Returns list of actions we are attending - physically present for"""
        attended_actions = list(self.dompc.actions.filter(Q(beat__isnull=True)
                                                          & Q(attending=True)
                                                          & Q(plot__isnull=False)
                                                          & ~Q(status=PlotAction.CANCELLED)
                                                          & Q(date_submitted__isnull=False)))
        attended_actions += list(self.dompc.assisting_actions.filter(Q(plot_action__beat__isnull=True)
                                                                     & Q(attending=True)
                                                                     & Q(plot_action__plot__isnull=False)
                                                                     & ~Q(plot_action__status=PlotAction.CANCELLED)
                                                                     & Q(date_submitted__isnull=False)))
        return attended_actions

    def check_plot_omnipresence(self):
        """Raises an ActionSubmissionError if we are already attending for this crisis"""
        if self.attending:
            already_attending = [ob for ob in self.plot_attendance if ob.plot == self.plot]
            if already_attending:
                already_attending = already_attending[-1]
                raise ActionSubmissionError("You are marked as physically present at %s. Use @action/toggleattend"
                                            " and also ensure this story reads as a passive role." % already_attending)

    def check_plot_overcrowd(self):
        """Raises an ActionSubmissionError if too many people are attending"""
        attendees = self.attendees
        if len(attendees) > self.attending_limit and not self.prefer_offscreen:
            excess = len(attendees) - self.attending_limit
            raise ActionSubmissionError("An onscreen action can have %s people attending in person. %s of you should "
                                        "check your story, then change to a passive role with @action/toggleattend. "
                                        "Alternately, the action can be marked as preferring offscreen resolution. "
                                        "Current attendees: %s" % (self.attending_limit, excess,
                                                                   ",".join(str(ob) for ob in attendees)))

    def check_plot_errors(self):
        """Raises ActionSubmissionErrors if anything should stop our submission"""
        if self.plot:
            self.plot.raise_submission_errors()
            self.check_plot_omnipresence()
        self.check_plot_overcrowd()

    def mark_attending(self):
        """Marks us as physically attending, raises ActionSubmissionErrors if it shouldn't be allowed."""
        self.check_plot_errors()
        self.attending = True
        self.save()

    def add_resource(self, r_type, value):
        """
        Adds a resource to this action of the specified type and value
        Args:
            r_type (str or unicode): The resource type
            value (str or unicode): The value passed.

        Raises:
            ActionSubmissionError if we run into bad values passed or cannot otherwise submit an action, and ValueError
            if they submit a value that isn't a positive integer when an amount is specified.
        """
        if not self.actions:
            raise ActionSubmissionError("Join first with the /setaction switch.")
        if self.plot:
            try:
                self.plot.raise_creation_errors(self.dompc)
            except ActionSubmissionError as err:
                raise ActionSubmissionError(err)
        r_type = r_type.lower()
        if r_type not in self.resource_types:
            raise ActionSubmissionError("Invalid type of resource.")
        if r_type == "army":
            try:
                return self.add_army(value)
            except ActionSubmissionError as err:
                raise ActionSubmissionError(err)
        try:
            value = int(value)
            if value <= 0:
                raise ValueError
        except ValueError:
            raise ActionSubmissionError("Amount must be a positive number.")
        if r_type == "silver":
            try:
                self.dompc.player.char_ob.pay_money(value)
            except PayError:
                raise ActionSubmissionError("You cannot afford that.")
        elif r_type == 'ap' or r_type == 'action points':
            if not self.dompc.player.pay_action_points(value):
                raise ActionSubmissionError("You do not have enough action points to exert that kind of effort.")
            r_type = "action_points"
        else:
            if not self.dompc.player.pay_resources(r_type, value):
                raise ActionSubmissionError("You cannot afford that.")
        value += getattr(self, r_type)
        setattr(self, r_type, value)
        self.save()

    def add_army(self, name_or_id):
        """Adds army orders to this action. Army can be specified by name or ID."""
        try:
            if name_or_id.isdigit():
                army = Army.objects.get(id=int(name_or_id))
            else:
                army = Army.objects.get(name__iexact=name_or_id)
        except (AttributeError, Army.DoesNotExist):
            raise ActionSubmissionError("No army by that ID# was found.")
        if self.is_main_action:
            action = self
            action_assist = None
        else:
            action = self.plot_action
            action_assist = self
        orders = army.send_orders(player=self.dompc.player, order_type=Orders.CRISIS, action=action,
                                  action_assist=action_assist)
        if not orders:
            raise ActionSubmissionError("Failed to send orders to the army.")

    def do_roll(self, stat=None, skill=None, difficulty=None, reset_total=True):
        """
        Does a roll for this action
        Args:
            stat: stat to override stat currently set in the action
            skill: skill to override skill currently set in the action
            difficulty: difficulty to override difficulty currently set in the action
            reset_total: Whether to recalculate the outcome value

        Returns:
            An integer result of the roll.
        """
        from world.stats_and_skills import do_dice_check
        self.stat_used = stat or self.stat_used
        self.skill_used = skill or self.skill_used
        if difficulty is not None:
            self.difficulty = difficulty
        self.roll = do_dice_check(self.dompc.player.char_ob, stat=self.stat_used, skill=self.skill_used,
                                  difficulty=self.difficulty)
        self.save()
        if reset_total:
            self.calculate_outcome_value()
        return self.roll

    def display_followups(self):
        """Returns string of the display of all of our questions."""
        return "\n".join(question.display() for question in self.questions.all())

    def add_answer(self, gm, text):
        """Adds a GM's answer to an OOC question"""
        unanswered = self.unanswered_questions
        if unanswered:
            unanswered.last().add_answer(gm, text)
        else:
            self.questions.last().add_answer(gm, text)

    def mark_answered(self, gm):
        """Marks a question as resolved"""
        for question in self.unanswered_questions:
            question.mark_answered = True
            question.save()
        inform_staff("%s has marked action %s's questions as answered." % (gm, self.main_id))

    @property
    def main_id(self):
        """ID of the main action"""
        return self.main_action.id

    @property
    def unanswered_questions(self):
        """Returns queryset of an OOC questions without an answer"""
        return self.questions.filter(answers__isnull=True).exclude(Q(is_intent=True) | Q(mark_answered=True))


class PlotAction(AbstractAction):
    """
    An action that a player is taking. May be in response to a Crisis.
    """
    NOUN = "Action"
    EASY_DIFFICULTY = 15
    NORMAL_DIFFICULTY = 30
    HARD_DIFFICULTY = 60
    week = models.PositiveSmallIntegerField(default=0, blank=0, db_index=True)
    dompc = models.ForeignKey("PlayerOrNpc", db_index=True, blank=True, null=True, related_name="actions")
    plot = models.ForeignKey("Plot", db_index=True, blank=True, null=True, related_name="actions")
    beat = models.ForeignKey("PlotUpdate", db_index=True, blank=True, null=True, related_name="actions",
                             on_delete=models.SET_NULL)
    public = models.BooleanField(default=False, blank=True)
    gm_notes = models.TextField("Any ooc notes for other GMs", blank=True)
    story = models.TextField("Story written by the GM for the player", blank=True)
    secret_story = models.TextField("Any secret story written for the player", blank=True)
    difficulty = models.SmallIntegerField(default=0, blank=0)
    outcome_value = models.SmallIntegerField(default=0, blank=0)
    assistants = models.ManyToManyField("PlayerOrNpc", blank=True, through="PlotActionAssistant",
                                        related_name="assisted_actions")
    prefer_offscreen = models.BooleanField(default=False, blank=True)
    gemit = models.ForeignKey("character.StoryEmit", blank=True, null=True, related_name="actions")
    gm = models.ForeignKey(settings.AUTH_USER_MODEL, blank=True, null=True, related_name="gmd_actions",
                           on_delete=models.SET_NULL)
    search_tags = models.ManyToManyField("character.SearchTag", blank=True, related_name="actions")

    UNKNOWN, COMBAT, SUPPORT, SABOTAGE, DIPLOMACY, SCOUTING, RESEARCH = range(7)

    CATEGORY_CHOICES = ((UNKNOWN, 'Unknown'), (COMBAT, 'Combat'), (SUPPORT, 'Support'), (SABOTAGE, 'Sabotage'),
                        (DIPLOMACY, 'Diplomacy'), (SCOUTING, 'Scouting'), (RESEARCH, 'Research'))
    category = models.PositiveSmallIntegerField(choices=CATEGORY_CHOICES, default=UNKNOWN)

    DRAFT, NEEDS_PLAYER, NEEDS_GM, CANCELLED, PENDING_PUBLISH, PUBLISHED = range(6)

    STATUS_CHOICES = ((DRAFT, 'Draft'), (NEEDS_PLAYER, 'Needs Player Input'), (NEEDS_GM, 'Needs GM Input'),
                      (CANCELLED, 'Cancelled'), (PENDING_PUBLISH, 'Pending Resolution'),(PUBLISHED, 'Resolved'))
    status = models.PositiveSmallIntegerField(choices=STATUS_CHOICES, default=DRAFT)
    max_requests = 2
    num_days = 30
    attending_limit = 5

    def __str__(self):
        if self.plot:
            plot = " for %s" % self.plot
        else:
            plot = ""
        return "%s by %s%s" % (self.NOUN, self.author, plot)

    @property
    def commafied_participants(self):
        dompc_list = [str(self.dompc)]
        for assist in self.assistants.all():
            dompc_list.append(str(assist))
        if len(dompc_list) == 1:
            return str(self.dompc)
        elif len(dompc_list) == 2:
            return dompc_list[0] + " and " + dompc_list[1]
        else:
            return ", ".join(dompc_list[:-2] + [" and ".join(dompc_list[-2:])])

    @property
    def pretty_str(self):
        """Returns formatted display of this action"""
        if self.plot:
            plot = " for {m%s{n" % self.plot
        else:
            plot = ""
        return "%s by {c%s{n%s" % (self.NOUN, self.author, plot)

    @property
    def sent(self):
        """Whether this action is published"""
        return bool(self.status == self.PUBLISHED)

    @property
    def total_social(self):
        """Total social resources spent"""
        return self.social + sum(ob.social for ob in self.assisting_actions.all())

    @property
    def total_economic(self):
        """Total economic resources spent"""
        return self.economic + sum(ob.economic for ob in self.assisting_actions.all())

    @property
    def total_military(self):
        """Total military resources spent"""
        return self.military + sum(ob.military for ob in self.assisting_actions.all())

    @property
    def total_silver(self):
        """Total silver spent"""
        return self.silver + sum(ob.silver for ob in self.assisting_actions.all())

    @property
    def total_action_points(self):
        """Total action points spent"""
        return self.action_points + sum(ob.action_points for ob in self.assisting_actions.all())

    @property
    def action_and_assists_and_invites(self):
        """List of this action and all our assists, whether they've accepted invite or not"""
        return [self] + list(self.assisting_actions.all())

    @property
    def action_and_assists(self):
        """Listof actions and assists if they've written anything"""
        return [ob for ob in self.action_and_assists_and_invites if ob.actions]

    @property
    def all_editable(self):
        """List of all actions and assists if they're currently editable"""
        return [ob for ob in self.action_and_assists_and_invites if ob.editable]

    def send(self, update=None, caller=None):
        """Publishes this action"""
        if self.plot:
            msg = "{wGM Response to action for crisis:{n %s" % self.plot
        else:
            msg = "{wGM Response to story action of %s" % self.author
        msg += "\n{wRolls:{n %s" % self.outcome_value
        msg += "\n\n{wStory Result:{n %s\n\n" % self.story
        self.week = get_week()
        if update:
            self.beat = update
        if self.status != PlotAction.PUBLISHED:
            self.inform(msg)
            for assistant in self.assistants.all():
                assistant.inform(msg, category="Actions")
            for orders in self.orders.all():
                orders.complete = True
                orders.save()
            self.status = PlotAction.PUBLISHED
        if not self.gm:
            self.gm = caller
        self.save()
        if not update:
            subject = "Action %s Published by %s" % (self.id, caller)
            post = self.view_tldr()
            post += "\n{wStory Result:{n %s" % self.story
            if self.secret_story:
                post += "\n{wSecret Story{n %s" % self.secret_story
            inform_staff("Action %s has been published by %s:\n%s" % (self.id, caller, msg),
                         post=post, subject=subject)

    def view_action(self, caller=None, disp_pending=True, disp_old=False, disp_ooc=True):
        """
        Returns a text string of the display of an action.

            Args:
                caller: Player who is viewing this
                disp_pending (bool): Whether to display pending questions
                disp_old (bool): Whether to display answered questions
                disp_ooc (bool): Whether to only display IC information

            Returns:
                Text string to display.
        """
        msg = "\n"
        if caller:
            staff_viewer = caller.check_permstring("builders")
            participant_viewer = caller == self.dompc.player or caller.Dominion in self.assistants.all()
        else:
            staff_viewer = False
            participant_viewer = False
        if not self.public and not (staff_viewer or participant_viewer):
            return msg
        # print out actions of everyone
        all_actions = self.action_and_assists
        view_main_secrets = staff_viewer or self.check_view_secret(caller)
        if disp_ooc:
            msg += "{wAction ID:{n #%s" % self.id
            msg += " {wCategory:{n %s" % self.get_category_display()
            if self.date_submitted:
                msg += "  {wDate:{n %s" % self.date_submitted.strftime("%x %X")
            if staff_viewer:
                if self.gm is not None:
                    msg += "  {wGM:{n %s" % self.gm
        for ob in all_actions:
            view_secrets = staff_viewer or ob.check_view_secret(caller)
            msg += ob.get_action_text(disp_summary=view_secrets)
            if ob.secret_actions and view_secrets:
                msg += ob.get_action_text(secret=True)
            if view_secrets and disp_ooc:
                attending = "[%s]" % ("physically present" if ob.attending else "offscreen")
                msg += "\n{w%s{n {w%s{n (stat) + {w%s{n (skill) at difficulty {w%s{n" % (
                    attending,
                    ob.stat_used.capitalize() or "No stat set",
                    ob.skill_used.capitalize() or "No skill set",
                    self.difficulty)
                if self.sent or (ob.roll_is_set and staff_viewer):
                    msg += "{w [Dice Roll: %s%s{w]{n " % (self.roll_color(ob.roll), ob.roll_string)
                if ob.ooc_intent:
                    msg += "\n%s" % ob.ooc_intent.display()
            msg += "\n"
        if (disp_pending or disp_old) and disp_ooc:
            q_and_a_str = self.get_questions_and_answers_display(answered=disp_old, staff=staff_viewer, caller=caller)
            if q_and_a_str:
                msg += "\n{wOOC Notes and GM responses\n%s" % q_and_a_str
        if staff_viewer and self.gm_notes or self.prefer_offscreen:
            offscreen = "[Offscreen resolution preferred.] " if self.prefer_offscreen else ""
            msg += "\n{wGM Notes:{n %s%s" % (offscreen, self.gm_notes)
        if self.sent or staff_viewer:
            if disp_ooc:
                msg += "\n{wOutcome Value:{n %s%s{n" % (self.roll_color(self.outcome_value), self.outcome_value)
            msg += "\n{wStory Result:{n %s" % self.story
            if self.secret_story and view_main_secrets:
                msg += "\n{wSecret Story{n %s" % self.secret_story
        if disp_ooc:
            msg += "\n" + self.view_total_resources_msg()
            orders = []
            for ob in all_actions:
                orders += list(ob.orders.all())
            orders = set(orders)
            if len(orders) > 0:
                msg += "\n{wArmed Forces Appointed:{n %s" % ", ".join(str(ob.army) for ob in orders)
            needs_edits = ""
            if self.status == PlotAction.NEEDS_PLAYER:
                needs_edits = " Awaiting edits to be submitted by: %s" % \
                              ", ".join(ob.author for ob in self.all_editable)
            msg += "\n{w[STATUS: %s]{n%s" % (self.get_status_display(), needs_edits)
        return msg

    @staticmethod
    def roll_color(val):
        """Returns a color string based on positive or negative value."""
        return "{r" if (val < 0) else "{g"

    def view_tldr(self):
        """Returns summary message of the action and assists"""
        msg = "{wSummary of action %s{n" % self.id
        for action in self.action_and_assists:
            msg += "\n%s: %s\n" % (action.pretty_str, action.get_summary_text())
        return msg

    def view_total_resources_msg(self):
        """Returns string of all resources spent"""
        msg = ""
        fields = {'extra action points': self.total_action_points,
                  'silver': self.total_silver,
                  'economic': self.total_economic,
                  'military': self.total_military,
                  'social': self.total_social}
        totals = ", ".join("{c%s{n %s" % (key, value) for key, value in fields.items() if value > 0)
        if totals:
            msg = "{wTotal resources:{n %s" % totals
        return msg

    def cancel(self):
        """Cancels and refunds this action"""
        for action in self.assisting_actions.all():
            action.cancel()
        self.refund()
        if not self.date_submitted:
            self.delete()
        else:
            self.status = PlotAction.CANCELLED
            self.save()

    def check_incomplete_required_fields(self):
        """Checks which fields are incomplete"""
        fields = super(PlotAction, self).check_incomplete_required_fields()
        if not self.category:
            fields.append("category")
        return fields

    def raise_submission_errors(self):
        """Raises errors that prevent submission"""
        super(PlotAction, self).raise_submission_errors()
        self.check_plot_errors()
        self.check_draft_errors()

    def check_draft_errors(self):
        """Checks any errors that occur only during initial creation"""
        if self.status != PlotAction.DRAFT:
            return
        self.check_action_against_maximum_allowed()
        self.check_warning_prompt_sent()

    def check_action_against_maximum_allowed(self):
        """Checks if we're over our limit on number of actions"""
        if self.free_action:
            return
        recent_actions = self.dompc.recent_actions
        num_actions = len(recent_actions)
        # we allow them to use unspent actions for assists, but not vice-versa
        num_assists = self.dompc.recent_assists.count()
        num_assists -= PlotActionAssistant.MAX_ASSISTS
        if num_assists >= 0:
            num_actions += num_assists
        if num_actions >= self.max_requests:
            raise ActionSubmissionError("You are permitted %s action requests every %s days. Recent actions: %s"
                                        % (self.max_requests, self.num_days,
                                           ", ".join(str(ob.id) for ob in recent_actions)))

    def check_warning_prompt_sent(self):
        """Sends a warning message to the player if they don't have one yet"""
        if self.dompc.player.ndb.action_submission_prompt != self:
            self.dompc.player.ndb.action_submission_prompt = self
            warning = ("{yBefore submitting this action, make certain that you have invited all players you wish to "
                       "help with the action, and add any resources necessary. Any invited players who have incomplete "
                       "actions will have their assists deleted.")
            unready = ", ".join(str(ob.author) for ob in self.get_unready_assisting_actions())
            if unready:
                warning += "\n{rThe following assistants are not ready and will be deleted: %s" % unready
            warning += "\n{yWhen ready, /submit the action again.{n"
            raise ActionSubmissionError(warning)

    def get_unready_assisting_actions(self):
        """Gets list of assists that are not yet ready"""
        unready = []
        for ob in self.assisting_actions.all():
            try:
                ob.raise_submission_errors()
            except ActionSubmissionError:
                unready.append(ob)
        return unready

    def check_unready_assistant(self, dompc):
        """Checks a given dompc being unready"""
        try:
            assist = self.assisting_actions.get(dompc=dompc)
            assist.raise_submission_errors()
        except PlotActionAssistant.DoesNotExist:
            return False
        except ActionSubmissionError:
            return True
        else:
            return False

    @property
    def attendees(self):
        """Returns list of authors of all actions and assists if physically present"""
        return [ob.author for ob in self.action_and_assists if ob.attending]

    def on_submit_success(self):
        """Announces us after successful submission. refunds any assistants who weren't ready"""
        if self.status == PlotAction.DRAFT:
            self.status = PlotAction.NEEDS_GM
            for assist in self.assisting_actions.filter(date_submitted__isnull=True):
                assist.submit_or_refund()
            inform_staff("%s submitted action #%s. %s" % (self.author, self.id, self.get_summary_text()))
        super(PlotAction, self).on_submit_success()

    def post_edit(self):
        """Announces that we've finished editing our action and are ready for a GM"""
        if self.status == PlotAction.NEEDS_PLAYER and not self.all_editable:
            self.status = PlotAction.NEEDS_GM
            self.save()
            inform_staff("%s has been resubmitted for GM review." % self)
            if self.gm:
                self.gm.inform("Action %s has been updated." % self.id, category="Actions")

    def invite(self, dompc):
        """Invites an assistant, sending them an inform"""
        if self.assistants.filter(player=dompc.player).exists():
            raise ActionSubmissionError("They have already been invited.")
        if dompc == self.dompc:
            raise ActionSubmissionError("The owner of an action cannot be an assistant.")
        self.assisting_actions.create(dompc=dompc, stat_used="", skill_used="")
        msg = "You have been invited by %s to assist with action #%s." % (self.author, self.id)
        msg += " It will now display under the {w@action{n command. To assist, simply fill out"
        msg += " the required fields, starting with {w@action/setaction{n, and then {w@action/submit %s{n." % self.id
        msg += " If the owner submits the action to the GMs before your assist is valid, it will be"
        msg += " deleted and you will be refunded any AP and resources."
        msg += " When creating your assist, please only write a story about attempting to modify"
        msg += " the main action you're assisting. Assists which are unrelated to the action"
        msg += " should be their own independent @action. Secret actions attempting to undermine"
        msg += " the action/crisis should use the '/traitor' switch."
        msg += " To decline this invitation, use {w@action/cancel %s{n." % self.id
        dompc.inform(msg, category="Action Invitation")

    def roll_all(self):
        """Rolls for every action and assist, changing outcome value"""
        for ob in self.action_and_assists:
            ob.do_roll(reset_total=False)
        return self.calculate_outcome_value()

    def calculate_outcome_value(self):
        """Calculates total value of the action"""
        value = sum(ob.roll for ob in self.action_and_assists)
        self.outcome_value = value
        self.save()
        return self.outcome_value

    def get_questions_and_answers_display(self, answered=False, staff=False, caller=None):
        """Displays all OOC questions and answers"""
        qs = self.questions.filter(is_intent=False)
        if not answered:
            qs = qs.filter(answers__isnull=True, mark_answered=False)
        if not staff:
            dompc = caller.Dominion
            # players can only see questions they wrote themselves and their answers
            qs = qs.filter(Q(action_assist__dompc=dompc) | Q(Q(action__dompc=dompc) & Q(action_assist__isnull=True)))
        qs = list(qs)
        if staff:
            for ob in self.assisting_actions.all():
                if answered:
                    qs.extend(list(ob.questions.filter(is_intent=False)))
                else:
                    qs.extend(list(ob.questions.filter(answers__isnull=True, is_intent=False, mark_answered=False)))
        return "\n".join(question.display() for question in set(qs))

    @property
    def main_action(self):
        """Returns ourself as the main action"""
        return self

    def make_public(self):
        """Makes an action public for all players to see"""
        if self.public:
            raise ActionSubmissionError("That action has already been made public.")
        if self.status != PlotAction.PUBLISHED:
            raise ActionSubmissionError("The action must be finished before you can make details of it public.")
        self.public = True
        self.save()
        xp_value = 2
        if self.plot and not self.plot.public:
            xp_value = 1
        self.dompc.player.char_ob.adjust_xp(xp_value)
        self.dompc.msg("You have gained %s xp for making your action public." % xp_value)
        inform_staff("Action %s has been made public." % self.id)


NAMES_OF_PROPERTIES_TO_PASS_THROUGH = ['plot', 'action_and_assists', 'status', 'prefer_offscreen', 'attendees',
                                       'all_editable', 'outcome_value', 'difficulty', 'gm', 'attending_limit']


@passthrough_properties('plot_action', *NAMES_OF_PROPERTIES_TO_PASS_THROUGH)
class PlotActionAssistant(AbstractAction):
    """An assist for a plot action - a player helping them out and writing how."""
    NOUN = "Assist"
    BASE_AP_COST = 10
    MAX_ASSISTS = 2
    plot_action = models.ForeignKey("PlotAction", db_index=True, related_name="assisting_actions")
    dompc = models.ForeignKey("PlayerOrNpc", db_index=True, related_name="assisting_actions")

    class Meta:
        unique_together = ('plot_action', 'dompc')

    def __str__(self):
        return "%s assisting %s" % (self.author, self.plot_action)

    @property
    def pretty_str(self):
        """Formatted string of the assist"""
        return "{c%s{n assisting %s" % (self.author, self.plot_action)

    def cancel(self):
        """Cancels and refunds this assist, then deletes it"""
        if self.actions:
            self.refund()
        self.delete()

    def view_total_resources_msg(self):
        """Passthrough method to return total resources msg"""
        return self.plot_action.view_total_resources_msg()

    def calculate_outcome_value(self):
        """Passthrough method to calculate outcome value"""
        return self.plot_action.calculate_outcome_value()

    def submit_or_refund(self):
        """Submits our assist if we're ready, or refunds us"""
        try:
            self.submit()
        except ActionSubmissionError:
            main_action_msg = "Cancelling incomplete assist: %s\n" % self.author
            assist_action_msg = "Your assist for %s was incomplete and has been refunded." % self.plot_action
            self.plot_action.inform(main_action_msg)
            self.inform(assist_action_msg)
            self.cancel()

    def post_edit(self):
        """Passthrough hook for after editing"""
        self.plot_action.post_edit()

    @property
    def has_paid_initial_ap_cost(self):
        """Returns if we've paid our AP cost"""
        return bool(self.actions)

    @property
    def main_action(self):
        """Returns the action we're assisting"""
        return self.plot_action

    def set_action(self, story):
        """
        Sets our assist's actions. If the action has not been set yet, we'll attempt to pay the initial ap cost,
        raising an error if that fails.

            Args:
                story (str or unicode): The story of the character's actions, written by the player.

            Raises:
                ActionSubmissionError if we have not yet paid our AP cost and the player fails to do so here.
        """
        self.check_max_assists()
        if not self.has_paid_initial_ap_cost:
            self.pay_initial_ap_cost()
        self.actions = story
        self.save()

    def ask_question(self, text):
        """Asks GMs an OOC question"""
        question = super(PlotActionAssistant, self).ask_question(text)
        question.action = self.plot_action
        question.save()

    def pay_initial_ap_cost(self):
        """Pays our initial AP cost or raises an ActionSubmissionError"""
        if not self.pay_action_points(self.BASE_AP_COST):
            raise ActionSubmissionError("You do not have enough action points.")

    def view_action(self, caller=None, disp_pending=True, disp_old=False, disp_ooc=True):
        """Returns display of the action"""
        return self.plot_action.view_action(caller=caller, disp_pending=disp_pending, disp_old=disp_old,
                                            disp_ooc=disp_ooc)

    def check_max_assists(self):
        """Raises an error if we've assisted too many actions"""
        # if we haven't spent all our actions, we'll let them use it on assists
        if self.free_action or self.plot_action.free_action:
            return
        num_actions = self.dompc.recent_actions.count() - 2
        num_assists = self.dompc.recent_assists.count()
        if num_actions < 0:
            num_assists += num_actions
        if num_assists >= self.MAX_ASSISTS:
            raise ActionSubmissionError("You are assisting too many actions.")

    def raise_submission_errors(self):
        """Raises errors that prevent submission"""
        super(PlotActionAssistant, self).raise_submission_errors()
        self.check_max_assists()


class ActionOOCQuestion(SharedMemoryModel):
    """
    OOC Question about a plot. Can be associated with a given action
    or asked about independently.
    """
    action = models.ForeignKey("PlotAction", db_index=True, related_name="questions", null=True, blank=True)
    action_assist = models.ForeignKey("PlotActionAssistant", db_index=True, related_name="questions", null=True,
                                      blank=True)
    text = models.TextField(blank=True)
    is_intent = models.BooleanField(default=False)
    mark_answered = models.BooleanField(default=False)

    def __str__(self):
        return "%s %s: %s" % (self.author, self.noun, self.text)

    @property
    def target(self):
        """The action or assist this question is from"""
        if self.action_assist:
            return self.action_assist
        return self.action

    @property
    def author(self):
        """Who wrote this question"""
        return self.target.author

    @property
    def noun(self):
        """String display of whether we're ooc intentions or a question"""
        return "OOC %s" % ("intentions" if self.is_intent else "Question")

    def display(self):
        """Returns string display of this object"""
        msg = "{c%s{w %s:{n %s" % (self.author, self.noun, self.text)
        answers = self.answers.all()
        if answers:
            msg += "\n%s" % "\n".join(ob.display() for ob in answers)
        return msg

    @property
    def text_of_answers(self):
        """Returns this question and all the answers to it"""
        return "\n".join("%s wrote: %s" % (ob.gm, ob.text) for ob in self.answers.all())

    @property
    def main_id(self):
        """ID of the target of this question"""
        return self.target.main_id

    def add_answer(self, gm, text):
        """Adds an answer to this question"""
        self.answers.create(gm=gm, text=text)
        self.target.inform("GM %s has posted a followup to action %s: %s" % (gm, self.main_id, text))
        answer = "{c%s{n wrote: %s\n{c%s{n answered: %s" % (self.author, self.text, gm, text)
        inform_staff("%s has posted a followup to action %s: %s" % (gm, self.main_id, text), post=answer,
                     subject="Action %s followup" % self.action.id)


class ActionOOCAnswer(SharedMemoryModel):
    """
    OOC answer from a GM about a plot.
    """
    gm = models.ForeignKey(settings.AUTH_USER_MODEL, blank=True, null=True, related_name="answers_given")
    question = models.ForeignKey("ActionOOCQuestion", db_index=True, related_name="answers")
    text = models.TextField(blank=True)

    def display(self):
        """Returns string display of this answer"""
        return "{wReply by {c%s{w:{n %s" % (self.gm, self.text)


class OrgRelationship(SharedMemoryModel):
    """
    The relationship between two or more organizations.
    """
    name = models.CharField("Name of the relationship", max_length=255, db_index=True, blank=True)
    orgs = models.ManyToManyField('Organization', related_name='relationships', blank=True, db_index=True)
    status = models.SmallIntegerField(default=0, blank=0)
    history = models.TextField("History of these organizations", blank=True)


class Reputation(SharedMemoryModel):
    """
    A player's reputation to an organization.
    """
    player = models.ForeignKey('PlayerOrNpc', related_name='reputations', blank=True, null=True, db_index=True)
    organization = models.ForeignKey('Organization', related_name='reputations', blank=True, null=True, db_index=True)
    # negative affection is dislike/hatred
    affection = models.IntegerField(default=0, blank=0)
    # positive respect is respect/fear, negative is contempt/dismissal
    respect = models.IntegerField(default=0, blank=0)
    favor = models.IntegerField(help_text="A percentage of the org's prestige applied to player's propriety.",
                                default=0)
    npc_gossip = models.TextField(blank=True)
    date_gossip_set = models.DateTimeField(null=True)

    def __str__(self):
        return "%s for %s (%s)" % (self.player, self.organization, self.favor)

    class Meta:
        unique_together = ('player', 'organization')

    def save(self, *args, **kwargs):
        """Saves changes and wipes cache"""
        super(Reputation, self).save(*args, **kwargs)
        try:
            self.player.assets.clear_cached_properties()
        except (AttributeError, ValueError, TypeError):
            pass

    @property
    def propriety_amount(self):
        """Amount that we modify propriety by for our player"""
        if not self.favor:
            return 0
        try:
            return self.favor * (self.organization.assets.fame + self.organization.assets.legend)/20
        except AttributeError:
            return 0

    @property
    def favor_description(self):
        """String display of our favor"""
        msg = "%s (%s)" % (self.organization, self.propriety_amount)
        if self.npc_gossip:
            msg += ": %s" % self.npc_gossip
        return msg

    def wipe_favor(self):
        """Wipes out our favor and npc_gossip string"""
        self.favor = 0
        self.npc_gossip = ""
        self.date_gossip_set = None
        self.save()


class Fealty(SharedMemoryModel):
    """
    Represents the loyalty of different organizations for grouping them together.
    """
    name = models.CharField(unique=True, max_length=200)

    class Meta:
        verbose_name_plural = "Fealties"

    def __str__(self):
        return self.name


class Organization(InformMixin, SharedMemoryModel):
    """
    An in-game entity, which may contain both player characters and
    non-player characters, the latter possibly not existing outside
    of the Dominion system. For purposes of the economy, an organization
    can substitute for an object as an asset holder. This allows them to
    have their own money, incomes, debts, etc.
    """
    CATEGORIES_WITH_FEALTY_PENALTIES = ("Law", "Discipleship")
    name = models.CharField(blank=True, null=True, max_length=255, db_index=True)
    desc = models.TextField(blank=True, null=True)
    category = models.CharField(blank=True, null=True, default="noble", max_length=255)
    fealty = models.ForeignKey("Fealty", blank=True, null=True, related_name="orgs")
    # In a RP game, titles are IMPORTANT. And we need to divide them by gender.
    rank_1_male = models.CharField(default="Prince", blank=True, null=True, max_length=255)
    rank_1_female = models.CharField(default="Princess", blank=True, null=True, max_length=255)
    rank_2_male = models.CharField(default="Voice", blank=True, null=True, max_length=255)
    rank_2_female = models.CharField(default="Voice", blank=True, null=True, max_length=255)
    rank_3_male = models.CharField(default="Noble Family", blank=True, null=True, max_length=255)
    rank_3_female = models.CharField(default="Noble Family", blank=True, null=True, max_length=255)
    rank_4_male = models.CharField(default="Trusted House Servants", blank=True, null=True, max_length=255)
    rank_4_female = models.CharField(default="Trusted House Servants", blank=True, null=True, max_length=255)
    rank_5_male = models.CharField(default="Noble Vassals", blank=True, null=True, max_length=255)
    rank_5_female = models.CharField(default="Noble Vassals", blank=True, null=True, max_length=255)
    rank_6_male = models.CharField(default="Vassals of Esteem", blank=True, null=True, max_length=255)
    rank_6_female = models.CharField(default="Vassals of Esteem", blank=True, null=True, max_length=255)
    rank_7_male = models.CharField(default="Known Commoners", blank=True, null=True, max_length=255)
    rank_7_female = models.CharField(default="Known Commoners", blank=True, null=True, max_length=255)
    rank_8_male = models.CharField(default="Sworn Commoners", blank=True, null=True, max_length=255)
    rank_8_female = models.CharField(default="Sworn Commoners", blank=True, null=True, max_length=255)
    rank_9_male = models.CharField(default="Forgotten Commoners", blank=True, null=True, max_length=255)
    rank_9_female = models.CharField(default="Forgotten Commoners", blank=True, null=True, max_length=255)
    rank_10_male = models.CharField(default="Serf", blank=True, null=True, max_length=255)
    rank_10_female = models.CharField(default="Serf", blank=True, null=True, max_length=255)
    npc_members = models.PositiveIntegerField(default=0, blank=0)
    income_per_npc = models.PositiveSmallIntegerField(default=0, blank=0)
    cost_per_npc = models.PositiveSmallIntegerField(default=0, blank=0)
    morale = models.PositiveSmallIntegerField(default=100, blank=100)
    # this is used to represent temporary windfalls or crises that must be resolved
    income_modifier = models.PositiveSmallIntegerField(default=100, blank=100)
    # whether players can use the @work command
    allow_work = models.BooleanField(default=False, blank=False)
    # whether we can be publicly viewed
    secret = models.BooleanField(default=False, blank=False)
    # lockstring
    lock_storage = models.TextField('locks', blank=True, help_text='defined in setup_utils')
    special_modifiers = models.TextField(blank=True, null=True)
    motd = models.TextField(blank=True, null=True)
    # used for when resource gain
    economic_influence = models.IntegerField(default=0)
    military_influence = models.IntegerField(default=0)
    social_influence = models.IntegerField(default=0)
    base_support_value = models.SmallIntegerField(default=5)
    member_support_multiplier = models.SmallIntegerField(default=5)
    clues = models.ManyToManyField('character.Clue', blank=True, related_name="orgs",
                                   through="ClueForOrg")
    theories = models.ManyToManyField('character.Theory', blank=True, related_name="orgs")
    org_channel = models.OneToOneField('comms.ChannelDB', blank=True, null=True, related_name="org",
                                       on_delete=models.SET_NULL)
    org_board = models.OneToOneField('objects.ObjectDB', blank=True, null=True, related_name="org",
                                     on_delete=models.SET_NULL)
    objects = OrganizationManager()

    def get_modifier_from_influence(self, resource_name):
        """The modifier for an org based on their total influence"""
        from math import sqrt
        influence = getattr(self, "%s_influence" % resource_name)
        influence /= 3000
        if not influence:
            return 0
        sign = 1 if influence >= 0 else -1
        return int(sqrt(abs(influence)) * sign)

    def get_progress_to_next_modifier(self, resource_name):
        """Gets our percentage progress toward next modifier"""
        influence = getattr(self, "%s_influence" % resource_name)
        goal_level = self.get_modifier_from_influence(resource_name) + 1
        influence_required = pow(goal_level, 2) * 3000
        base = pow(goal_level - 1, 2) * 3000
        influence_required -= base
        influence -= base
        return round(influence/float(influence_required), 2) * 100

    @property
    def economic_modifier(self):
        """Gets our economic mod"""
        return self.get_modifier_from_influence("economic")

    @property
    def military_modifier(self):
        """Gets our military mod"""
        return self.get_modifier_from_influence("military")

    @property
    def social_modifier(self):
        """Gets our social mod"""
        return self.get_modifier_from_influence("social")

    def _get_npc_money(self):
        npc_income = self.npc_members * self.income_per_npc
        npc_income = (npc_income * self.income_modifier)/100.0
        npc_income += self.assets.get_bonus_income(npc_income)
        npc_cost = self.npc_members * self.cost_per_npc
        return int(npc_income) - npc_cost
    amount = property(_get_npc_money)

    def __str__(self):
        return self.name or "Unnamed organization (#%s)" % self.id

    def __unicode__(self):
        return self.name or "Unnamed organization (#%s)" % self.id

    def __repr__(self):
        return "<Org (#%s): %s>" % (self.id, self.name)

    def display_members(self, start=1, end=10, viewing_member=None, show_all=False):
        """Returns string display of the org"""
        pcs = self.all_members
        active = self.active_members
        if viewing_member:
            # exclude any secret members that are higher in rank than viewing member
            members_to_exclude = pcs.filter(Q(rank__lte=viewing_member.rank) & ~Q(id=viewing_member.id))
            if not self.secret:
                members_to_exclude = members_to_exclude.filter(secret=True)
            pcs = pcs.exclude(id__in=members_to_exclude)
        elif not show_all:
            pcs = pcs.exclude(secret=True)
        msg = ""
        for rank in range(start, end+1):
            chars = pcs.filter(rank=rank)
            male_title = getattr(self, 'rank_%s_male' % rank)
            female_title = getattr(self, 'rank_%s_female' % rank)
            if male_title == female_title:
                title = male_title
            else:
                title = "%s/%s" % (male_title.capitalize(), female_title.capitalize())

            def char_name(charob):
                """Helper function to format character name"""
                c_name = str(charob)
                if charob not in active:
                    c_name = "(R)" + c_name
                if not self.secret and charob.secret:
                    c_name += "(Secret)"
                return c_name
            if len(chars) > 1:
                msg += "{w%s{n (Rank %s): %s\n" % (title, rank,
                                                   ", ".join(char_name(char) for char in chars))
            elif len(chars) > 0:
                char = chars[0]
                name = char_name(char)
                char = char.player.player.db.char_ob
                gender = char.db.gender or "Male"
                if gender.lower() == "male":
                    title = male_title
                else:
                    title = female_title
                msg += "{w%s{n (Rank %s): %s\n" % (title, rank, name)
        return msg

    def display_public(self, show_all=False):
        """Public display of this org"""
        msg = "\n{wName{n: %s\n" % self.name
        msg += "{wDesc{n: %s\n" % self.desc
        if not self.secret:
            msg += "\n{wLeaders of %s:\n%s\n" % (self.name, self.display_members(end=2, show_all=show_all))
        webpage = PAGEROOT + self.get_absolute_url()
        msg += "{wWebpage{n: %s\n" % webpage
        return msg

    def display(self, viewing_member=None, display_clues=False, show_all=False):
        """Returns string display of org"""
        if hasattr(self, 'assets'):
            money = self.assets.vault
            try:
                display_money = not viewing_member or self.assets.can_be_viewed_by(viewing_member.player.player)
            except AttributeError:
                display_money = False
            prestige = self.assets.prestige
            if hasattr(self.assets, 'estate'):
                holdings = self.assets.estate.holdings.all()
            else:
                holdings = []
        else:
            money = 0
            display_money = False
            prestige = 0
            holdings = []
        msg = self.display_public(show_all=show_all)
        if self.secret:
            # if we're secret, we display the leaders only to members. And then
            # only if they're not marked secret themselves
            start = 1
        else:
            start = 3
        members = self.display_members(start=start, viewing_member=viewing_member, show_all=show_all)
        if members:
            members = "{wMembers of %s:\n%s" % (self.name, members)
        msg += members
        if display_money:
            msg += "\n{wMoney{n: %s" % money
            msg += " {wPrestige{n: %s" % prestige
            prestige_mod = self.assets.prestige_mod
            resource_mod = int(prestige_mod)

            def mod_string(amount):
                """Helper function to format resource modifier string"""
                return "%s%s%%" % ("+" if amount > 0 else "", amount)

            income_mod = int(prestige_mod/4)
            msg += " {wResource Mod:{n %s {wIncome Mod:{n %s" % (mod_string(resource_mod), mod_string(income_mod))
            msg += "\n{wResources{n: Economic: %s, Military: %s, Social: %s" % (self.assets.economic,
                                                                                self.assets.military,
                                                                                self.assets.social)
        econ_progress = self.get_progress_to_next_modifier("economic")
        mil_progress = self.get_progress_to_next_modifier("military")
        soc_progress = self.get_progress_to_next_modifier("social")
        msg += "\n{wMods: Economic:{n %s (%s/100), {wMilitary:{n %s (%s/100), {wSocial:{n %s (%s/100)\n" % (
            self.economic_modifier, int(econ_progress), self.military_modifier, int(mil_progress),
            self.social_modifier, int(soc_progress))
        # msg += "{wSpheres of Influence:{n %s\n" % ", ".join("{w%s{n: %s" % (ob.category, ob.rating)
        #                                                     for ob in self.spheres.all())
        msg += self.display_work_settings()
        clues = self.clues.all()
        if display_clues:
            if clues:
                msg += "\n{wClues Known:{n %s\n" % "; ".join(str(ob) for ob in clues)
            theories = self.theories.all()
            if theories:
                msg += "\n{wTheories Known:{n %s\n" % "; ".join("%s (#%s)" % (ob, ob.id) for ob in theories)
        if holdings:
            msg += "{wHoldings{n: %s\n" % ", ".join(ob.name for ob in holdings)
        if self.motd and (viewing_member or show_all):
            msg += "|yMessage of the day for %s set to:|n %s\n" % (self, self.motd)
        if viewing_member:
            msg += "\n{wMember stats for {c%s{n\n" % viewing_member
            msg += viewing_member.display()
        return msg

    def display_work_settings(self):
        """Gets table of work settings"""
        from server.utils.prettytable import PrettyTable
        work_settings = self.work_settings.all().order_by('resource')
        msg = "\n{wWork Settings:{n"
        if not work_settings:
            return msg + " None found.\n"
        table = PrettyTable(["{wResource{n", "{wStat{n", "{wSkill{n"])
        for setting in work_settings:
            table.add_row([setting.get_resource_display(), setting.stat, setting.skill])
        msg += "\n" + str(table) + "\n"
        return msg

    def __init__(self, *args, **kwargs):
        super(Organization, self).__init__(*args, **kwargs)
        self.locks = LockHandler(self)

    @property
    def default_access_rank(self):
        """What rank to default to if they don't set permission"""
        return 2 if self.secret else 10

    def access(self, accessing_obj, access_type='read', default=False):
        """
        Determines if another object has permission to access.
        accessing_obj - object trying to access this one
        access_type - type of access sought
        default - what to return if no lock of access_type was found
        """
        if access_type not in self.locks.locks.keys():
            try:
                obj = accessing_obj.player_ob or accessing_obj
                member = obj.Dominion.memberships.get(deguilded=False, organization=self)
                return member.rank <= self.default_access_rank
            except (AttributeError, Member.DoesNotExist):
                return False
        return self.locks.check(accessing_obj, access_type=access_type, default=default)

    def msg(self, message, prefix=True, use_channel_color=True, *args, **kwargs):
        """Sends msg to all active members"""
        color = "|w" if not use_channel_color else self.channel_color
        if prefix:
            message = "%s%s organization-wide message:|n %s" % (color, self, message)
        elif use_channel_color:
            message = color + message + "|n"
        for pc in self.online_members:
            pc.msg(message, *args, **kwargs)

    def gemit_to_org(self, gemit):
        """
        Messages online members, informs offline members, and makes an org
        bboard story post.
        """
        category = "%s Story Update" % self
        bboard = self.org_board
        if bboard:
            bboard.bb_post(poster_obj=gemit.sender, msg=gemit.text, subject=category, poster_name="Story")
        for pc in self.offline_members:
            pc.inform(gemit.text, category=category, append=False)
        box_chars = '\n' + '*' * 70 + '\n'
        msg = box_chars + '[' + category + '] ' + gemit.text + box_chars
        self.msg(msg, prefix=False)

    @property
    def active_members(self):
        """Returns queryset of players in active roster and not deguilded"""
        return self.members.filter(Q(player__player__roster__roster__name="Active") & Q(deguilded=False)).distinct()

    @property
    def living_members(self):
        """Returns queryset of players in active or available roster and not deguilded"""
        return self.members.filter((Q(player__player__roster__roster__name="Active") |
                                    Q(player__player__roster__roster__name="Available"))
                                   & Q(deguilded=False)).distinct()

    @property
    def can_receive_informs(self):
        """Whether this org can get informs"""
        return bool(self.active_members)

    @property
    def all_members(self):
        """Returns all members who aren't booted, active or not"""
        return self.members.filter(deguilded=False)

    @property
    def online_members(self):
        """Returns members who are currently online"""
        return self.active_members.filter(player__player__db_is_connected=True).distinct()

    @property
    def offline_members(self):
        """Returns members who are currently offline"""
        return self.active_members.exclude(id__in=self.online_members)

    @property
    def support_pool(self):
        """Returns our current support pool"""
        return self.base_support_value + (self.active_members.count()) * self.member_support_multiplier

    def save(self, *args, **kwargs):
        """Saves changes and wipes cache"""
        super(Organization, self).save(*args, **kwargs)
        try:
            self.assets.clear_cached_properties()
        except (AttributeError, ValueError, TypeError):
            pass
        # make sure that any cached AP modifiers based on Org fealties are invalidated
        from web.character.models import RosterEntry
        RosterEntry.clear_ap_cache_in_cached_instances()

    def get_absolute_url(self):
        """Returns URL of the org webpage"""
        return reverse('help_topics:display_org', kwargs={'object_id': self.id})

    @property
    def channel_color(self):
        """Color for their channel"""
        color = "|w"
        channel = self.org_channel
        if channel:
            color = channel.db.colorstr or color
        return color

    def notify_inform(self, new_inform):
        """Notifies online players that there's a new inform"""
        index = list(self.informs.all()).index(new_inform) + 1
        members = [pc for pc in self.online_members if pc.player and pc.player.player and self.access(pc.player.player,
                                                                                                      "informs")]
        for pc in members:
            pc.msg("{y%s has new @informs. Use {w@informs/org %s/%s{y to read them." % (self, self, index))

    def setup(self):
        """Sets up the org with channel and board"""
        from typeclasses.channels import Channel
        from typeclasses.bulletin_board.bboard import BBoard
        from evennia.utils.create import create_object, create_channel
        lockstr = "send: organization(%s) or perm(builders);listen: organization(%s) or perm(builders)" % (self, self)
        if not self.org_channel:
            self.org_channel = create_channel(key=str(self.name), desc="%s channel" % self, locks=lockstr,
                                              typeclass=Channel)
        if not self.org_board:
            lockstr = lockstr.replace("send", "read").replace("listen", "write")
            self.org_board = create_object(typeclass=BBoard, key=str(self.name), locks=lockstr)
        self.save()

    def set_motd(self, message):
        """Sets our motd, notifies people, sets their flags."""
        self.motd = message
        self.save()
        self.msg("|yMessage of the day for %s set to:|n %s" % (self, self.motd), prefix=False)
        for pc in self.offline_members.filter(has_seen_motd=True):
            pc.has_seen_motd = False
            pc.save()


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


class ClueForOrg(SharedMemoryModel):
    """Model that shows a clue known by an org"""
    clue = models.ForeignKey('character.Clue', related_name="org_discoveries", db_index=True)
    org = models.ForeignKey('Organization', related_name="clue_discoveries", db_index=True)
    revealed_by = models.ForeignKey('character.RosterEntry', related_name="clues_added_to_orgs", blank=True, null=True,
                                    db_index=True)

    class Meta:
        unique_together = ('clue', 'org')


class Agent(SharedMemoryModel):
    """
    Types of npcs that can be employed by a player or an organization. The
    Agent instance represents a class of npc - whether it's a group of spies,
    armed guards, hired assassins, a pet dragon, whatever. Type is an integer
    that will be defined elsewhere in an agent file. ObjectDB points to Agent
    as a foreignkey, and we access that set through self.agent_objects.
    """
    GUARD = npc_types.GUARD
    THUG = npc_types.THUG
    SPY = npc_types.SPY
    ASSISTANT = npc_types.ASSISTANT
    CHAMPION = npc_types.CHAMPION
    ANIMAL = npc_types.ANIMAL
    SMALL_ANIMAL = npc_types.SMALL_ANIMAL
    NPC_TYPE_CHOICES = (
        (GUARD, 'Guard'),
        (THUG, 'Thug'),
        (SPY, 'Spy'),
        (ASSISTANT, 'Assistant'),
        (CHAMPION, 'Champion'),
        (ANIMAL, 'Animal'),
        (SMALL_ANIMAL, 'Small Animal'))
    name = models.CharField(blank=True, max_length=80)
    colored_name = models.CharField(blank=True, max_length=80)
    desc = models.TextField(blank=True)
    cost_per_guard = models.PositiveSmallIntegerField(default=0)
    # unassigned agents
    quantity = models.PositiveIntegerField(default=0)
    # level of our agents
    quality = models.PositiveSmallIntegerField(default=0)
    # numerical type of our agents. 0==regular guards, 1==spies, etc
    type = models.PositiveSmallIntegerField(choices=NPC_TYPE_CHOICES, default=GUARD)
    # assetowner, so either a player or an organization
    owner = models.ForeignKey("AssetOwner", on_delete=models.SET_NULL, related_name="agents", blank=True, null=True,
                              db_index=True)
    secret = models.BooleanField(default=False)
    # if this class of Agent is a unique individual, and as such the quantity cannot be more than 1
    unique = models.BooleanField(default=False)
    xp = models.PositiveSmallIntegerField(default=0)
    modifiers = models.TextField(blank=True)
    loyalty = models.PositiveSmallIntegerField(default=100)

    def _get_cost(self):
        return self.cost_per_guard * self.quantity
    cost = property(_get_cost)

    @property
    def type_str(self):
        """Returns string of the npc's type"""
        return self.npcs.get_type_name(self.type)

    # total of all agent obs + our reserve quantity
    def _get_total_num(self):
        return self.quantity + sum(self.agent_objects.values_list("quantity", flat=True))
    total = property(_get_total_num)

    def _get_active(self):
        return self.agent_objects.filter(quantity__gte=1)
    active = property(_get_active)

    def __unicode__(self):
        name = self.name or self.type_str
        if self.unique or self.quantity == 1:
            return name
        return "%s %s" % (self.quantity, self.name)

    @property
    def pretty_name(self):
        """Returns name or colored name"""
        return self.colored_name or self.name or self.type_str

    def __repr__(self):
        return "<Agent (#%s): %s>" % (self.id, self.name)

    def display(self, show_assignments=True, caller=None):
        """Returns string display of an agent"""
        msg = "\n\n{wID{n: %s {wName{n: %s {wType:{n %s  {wLevel{n: %s" % (
            self.id, self.pretty_name, self.type_str, self.quality)
        if not self.unique:
            msg += " {wUnassigned:{n %s\n" % self.quantity
        else:
            msg += "\n{wXP:{n %s {wLoyalty{n: %s\n" % (self.xp, self.loyalty)
        if not show_assignments:
            return msg
        msg += ", ".join(agent.display(caller=caller) for agent in self.agent_objects.filter(quantity__gt=0))
        return msg

    def assign(self, targ, num):
        """
        Assigns num agents to target character object.
        """
        if num > self.quantity:
            raise ValueError("Agent only has %s to assign, asked for %s." % (self.quantity, num))
        self.npcs.assign(targ, num)

    def find_assigned(self, player):
        """
        Asks our agenthandler to find the AgentOb with a dbobj assigned
        to guard the given character. Returns the first match, returns None
        if not found.
        """
        return self.npcs.find_agentob_by_character(player.db.char_ob)

    @property
    def dbobj(self):
        """Return dbobj of an agent_ob when we are unique"""
        agentob = self.agent_objects.get(dbobj__isnull=False)
        return agentob.dbobj

    @property
    def buyable_abilities(self):
        """Returns list of the abilities that can be bought"""
        try:
            return self.dbobj.buyable_abilities
        except AttributeError:
            return []

    def __init__(self, *args, **kwargs):
        super(Agent, self).__init__(*args, **kwargs)
        self.npcs = AgentHandler(self)

    def access(self, accessing_obj, access_type='agent', default=False):
        """Checks access for the agent by accessing_obj"""
        return self.owner.access(accessing_obj, access_type, default)

    def get_stat_cost(self, attr):
        """Returns cost for buying stat for agent"""
        return self.dbobj.get_stat_cost(attr)

    def get_skill_cost(self, attr):
        """Returns cost for buying skill for agent"""
        return self.dbobj.get_skill_cost(attr)

    def get_ability_cost(self, attr):
        """Returns cost for buying ability for agent"""
        return self.dbobj.get_ability_cost(attr)

    def get_attr_maximum(self, attr, category):
        """Returns maximum attribute for agent"""
        if category == "level":
            if self.type_str in attr:
                attr_max = 6
            else:
                attr_max = self.quality - 1
        elif category == "armor":
            attr_max = (self.quality * 15) + 10
        elif category == "stat":
            attr_max = self.dbobj.get_stat_maximum(attr)
        elif category == "skill":
            attr_max = self.dbobj.get_skill_maximum(attr)
        elif category == "ability":
            attr_max = self.dbobj.get_ability_maximum(attr)
        elif category == "weapon":
            if attr == 'weapon_damage':
                attr_max = (self.quality + 2) * 2
            elif attr == 'difficulty_mod':
                attr_max = (self.quality + 1) * 2
            else:
                raise ValueError("Undefined weapon attribute")
        else:
            raise ValueError("Undefined category")
        return attr_max

    def adjust_xp(self, value):
        """Adjusts the xp of the agent"""
        self.xp += value
        self.save()

    @property
    def xp_transfer_cap(self):
        """Shows how much xp can be transferred to the agent"""
        return self.dbobj.xp_transfer_cap

    @xp_transfer_cap.setter
    def xp_transfer_cap(self, value):
        self.dbobj.xp_transfer_cap = value

    def set_name(self, name):
        """Sets the name of the agent"""
        from evennia.utils.ansi import strip_ansi
        self.colored_name = name
        self.name = strip_ansi(name)
        self.save()
        for agent in self.agent_objects.all():
            if agent.dbobj:
                agent.dbobj.setup_name()


class AgentMission(SharedMemoryModel):
    """
    Missions that AgentObs go on.
    """
    agentob = models.ForeignKey("AgentOb", related_name="missions", blank=True, null=True)
    active = models.BooleanField(default=True, blank=True)
    success_level = models.SmallIntegerField(default=0, blank=0)
    description = models.TextField(blank=True, null=True)
    category = models.CharField(blank=True, null=True, max_length=80)
    mission_details = models.TextField(blank=True, null=True)
    results = models.TextField(blank=True, null=True)


class AgentOb(SharedMemoryModel):
    """
    Allotment from an Agent class that has a representation in-game.
    """
    agent_class = models.ForeignKey("Agent", related_name="agent_objects", blank=True, null=True,
                                    db_index=True)
    dbobj = models.OneToOneField("objects.ObjectDB", blank=True, null=True)
    quantity = models.PositiveIntegerField(default=0, blank=0)
    # whether they're imprisoned, by whom, difficulty to free them, etc
    status_notes = models.TextField(blank=True, null=True)

    @property
    def guarding(self):
        """Returns who the agent is guarding"""
        if not self.dbobj:
            return None
        return self.dbobj.db.guarding

    def __str__(self):
        return "%s%s" % (self.agent_class, (" guarding %s" % self.guarding) if self.guarding else "")

    def recall(self, num):
        """
        We try to pull out X number of agents from our dbobj. If it doesn't
        have enough, it returns the number it was able to get. It also calls
        unassign if it runs out of troops.
        """
        num = self.dbobj.lose_agents(num) or 0
        self.agent_class.quantity += num
        self.agent_class.save()
        return num

    def unassign(self):
        """
        Called from our associated dbobj, already having done the work to
        disassociate the npc from whoever it was guarding. This just cleans
        up AgentOb and returns our agents to the agent class.
        """
        self.agent_class.quantity += self.quantity
        self.agent_class.save()
        self.quantity = 0
        self.save()

    def reinforce(self, num):
        """
        Increase our troops by num.
        """
        if num < 0:
            raise ValueError("Must pass a positive number to reinforce.")
        self.quantity += num
        self.dbobj.gain_agents(num)
        self.save()
        return num

    def display(self, caller=None):
        """Returns string display of the agent"""
        if not self.quantity:
            return ""
        return self.dbobj.display(caller=caller)

    def lose_agents(self, num):
        """Remove some of the numberof guards"""
        self.quantity -= num
        if self.quantity < 0:
            self.quantity = 0
        self.save()

    def access(self, accessing_obj, access_type='agent', default=False):
        """Checks whether someone can control the agent"""
        return self.agent_class.access(accessing_obj, access_type, default)


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


class WorkSetting(SharedMemoryModel):
    """
    An Organization's options for work performed by its members. For a particular
    resource, a number of work_settings may exist and the member's highest Skill
    will primarily decide which one is used. If a member relies on their protege,
    the highest skill between them both will be used to choose a work_setting.
    """
    RESOURCE_TYPES = ('Economic', 'Military', 'Social')
    RESOURCE_CHOICES = tuple(enumerate(RESOURCE_TYPES))

    organization = models.ForeignKey('Organization', related_name='work_settings')
    stat = models.CharField(blank=True, null=True, max_length=80)
    skill = models.CharField(blank=True, null=True, max_length=80)
    resource = models.PositiveSmallIntegerField(choices=RESOURCE_CHOICES, default=0)
    message = models.TextField(blank=True)

    def __str__(self):
        return "%s-%s for %s" % (self.get_resource_display(), self.skill.capitalize(), self.organization)

    @classmethod
    def get_choice_from_string(cls, string):
        """Checks if a string names a type of resource and returns its choice number."""
        for int_constant, name in cls.RESOURCE_CHOICES:
            if string.lower() == name.lower():
                return int_constant
        raise ValueError("Type must be one of these: %s." % ", ".join(sorted(cls.RESOURCE_TYPES)))

    @classmethod
    def create_work(cls, organization, resource_key):
        """Creates a new WorkSetting with default stat and skill chosen."""
        default_settings = {0: ['intellect', 'economics'], 1: ['command', 'war'], 2: ['charm', 'diplomacy']}
        stat = default_settings[resource_key][0]
        skill = default_settings[resource_key][1]
        return cls.objects.create(organization=organization, stat=stat, skill=skill, resource=resource_key)

    def do_work(self, member, clout, protege=None):
        """Does rolls for a given WorkSetting for Member/protege and returns roll and the msg"""
        msg_spacer = " " if self.message else ""
        difficulty = 15 - clout
        org_mod = getattr(self.organization, "%s_modifier" % self.get_resource_display().lower())
        roller = member.char
        if protege:
            skill_val = member.char.db.skills.get(self.skill, 0)
            if protege.player.char_ob.db.skills.get(self.skill, 0) > skill_val:
                roller = protege.player.char_ob
        roll_msg = "\n%s%s%s rolling %s and %s. " % (self.message, msg_spacer, roller.key, self.stat, self.skill)
        outcome = do_dice_check(roller, stat=self.stat, skill=self.skill, difficulty=difficulty,
                                bonus_dice=org_mod, bonus_keep=org_mod//2)
        outcome //= 3
        return outcome, roll_msg


class Member(SharedMemoryModel):
    """
    Membership information for a character in an organization. This may or
    may not be an actual in-game object. If pc_exists is true, we expect a
    character object to be defined. If not, then this is just an off-screen
    npc who fills some purpose in the structure of the organization, but should
    generally not appear in game - more active npcs are probably Agents under
    control of a player character. Agents should also not be defined here,
    since they're usually more of a class of npc rather than individuals.
    Although they might be employed by an organization, we track them separately.
    This does mean they don't have any formal 'rank', but if the situation
    arises, you could always create a duplicate NPC Member who is one of your
    agents, just as a separation of their off-screen and on-screen duties.

    As far as salary goes, anyone in the Member model can have a WeeklyTransaction
    set up with their Organization.
    """
    player = models.ForeignKey('PlayerOrNpc', related_name='memberships', blank=True, null=True, db_index=True)
    commanding_officer = models.ForeignKey('self', on_delete=models.SET_NULL, related_name='subordinates', blank=True,
                                           null=True)
    organization = models.ForeignKey('Organization', related_name='members', blank=True, null=True, db_index=True)
    # work they've gained
    work_this_week = models.PositiveSmallIntegerField(default=0, blank=0)
    work_total = models.PositiveSmallIntegerField(default=0, blank=0)
    # amount of org influence they've gained
    investment_this_week = models.SmallIntegerField(default=0)
    investment_total = models.SmallIntegerField(default=0)
    secret = models.BooleanField(blank=False, default=False)
    deguilded = models.BooleanField(blank=False, default=False)

    # a rare case of us not using a player object, since we may designate any type of object as belonging
    # to an organization - character objects without players (npcs), rooms, exits, items, etc.
    object = models.ForeignKey('objects.ObjectDB', related_name='memberships', blank=True, null=True)

    rank = models.PositiveSmallIntegerField(blank=10, default=10)

    pc_exists = models.BooleanField(blank=True, default=True,
                                    help_text="Whether this member is a player character in the database")
    # stuff that players may set for their members:
    desc = models.TextField(blank=True, default=True)
    public_notes = models.TextField(blank=True, default=True)
    officer_notes = models.TextField(blank=True, default=True)
    has_seen_motd = models.BooleanField(default=False)

    class Meta:
        ordering = ['rank']

    def _get_char(self):
        if self.player and self.player.player and self.player.player.char_ob:
            return self.player.player.char_ob
    char = property(_get_char)

    def __str__(self):
        return str(self.player)

    def __repr__(self):
        return "<Member %s (#%s)>" % (self.player, self.id)

    def fake_delete(self):
        """
        Alternative to deleting this object. That way we can just readd them if they
        rejoin and conserve their rank/description.
        """
        self.deguilded = True
        self.save()
        org_channel = self.organization.org_channel
        if org_channel:
            org_channel.disconnect(self.player.player)
        board = self.organization.org_board
        if board:
            board.unsubscribe_bboard(self.player.player)

    def setup(self):
        """
        Add ourselves to org channel/board if applicable
        """
        board = self.organization.org_board
        if board:
            board.subscribe_bboard(self.player.player)
        # if we're a secret member of non-secret org, don't auto-join
        if self.secret and not self.organization.secret:
            return
        org_channel = self.organization.org_channel
        if org_channel:
            org_channel.connect(self.player.player)

    def __getattr__(self, name):
        """So OP for getting player's inform or msg methods."""
        if name in ("msg", "inform") and self.player:
            return getattr(self.player, name)
        raise AttributeError("%r object has no attribute %r" % (self.__class__, name))

    def work(self, resource_type, ap_cost, protege=None):
        """
        Perform work in a week for our Organization. If a protege is specified we use their skills and add their
        social clout to the roll.

            Raises:
                ValueError if resource_type is invalid or ap_cost is greater than Member's AP
        """
        resource_type = resource_type.lower()
        clout = self.char.social_clout
        msg = "Your social clout "
        protege_clout = 0
        if protege:
            protege_clout = protege.player.char_ob.social_clout
            msg += "combined with that of your protege "
        clout += protege_clout
        msg += "reduces difficulty by %s." % clout
        outcome, roll_msg = self.get_work_roll(resource_type, clout, protege)
        msg += roll_msg
        if not self.player.player.pay_action_points(ap_cost):
            raise ValueError("You cannot afford the AP cost to work.")

        def adjust_resources(assets, amount):
            """helper function to add resources from string name"""
            if amount <= 0:
                return
            current = getattr(assets, resource_type)
            bonus = assets.get_bonus_resources(amount, random_percentage=120)
            bonus_msg = ""
            setattr(assets, resource_type, current + amount + bonus)
            assets.save()
            if bonus:
                bonus_msg += " Amount modified by %s%s resources due to prestige." % ("+" if bonus > 0 else "", bonus)
            if assets != self.player.assets:
                inform_msg = "%s has been hard at work, and %s has gained %s %s resources." % (
                              self, assets, amount, resource_type)
                assets.inform(inform_msg + bonus_msg, category="Work", append=True)
            else:
                self.player.player.msg(msg + bonus_msg)

        def get_amount_after_clout(clout_value, added=100, minimum=0):
            """helper function to calculate clout modifier on outcome amount"""
            percent = (clout_value + added)/100.0
            total = int(outcome * percent)
            if total < minimum:
                total = minimum
            return total

        patron_amount = get_amount_after_clout(clout, minimum=randint(1, 10))
        if randint(0, 100) < 4:
            # we got a big crit, hooray. Add a base of 1-30 resources to bonus, then triple the bonus
            patron_amount += randint(1, 50)
            patron_amount *= 3
            msg += " Luck has gone %s's way, and they get a bonus!" % self
        msg += "You have gained %s %s resources." % (patron_amount, resource_type)
        adjust_resources(self.player.assets, patron_amount)
        org_amount = patron_amount//5
        if org_amount:
            adjust_resources(self.organization.assets, org_amount)
            self.work_this_week += org_amount
            self.work_total += org_amount
            self.save()
        if protege:
            adjust_resources(protege.assets, get_amount_after_clout(protege_clout, added=25, minimum=1))

    def invest(self, resource_type, ap_cost, protege=None, resources=0):
        """
        Perform work in a week for our Organization. If a protege is specified we use their skills and add their
        social clout to the roll.

            Raises:
                ValueError if resource_type is invalid or ap_cost is greater than Member's AP
        """
        resource_type = resource_type.lower()
        clout = self.char.social_clout
        msg = "Your social clout "
        protege_clout = 0
        if protege:
            protege_clout = protege.player.char_ob.social_clout
            msg += "combined with that of your protege "
        clout += protege_clout
        msg += "reduces difficulty by %s." % clout
        outcome, roll_msg = self.get_work_roll(resource_type, clout, protege)
        msg += roll_msg
        assets = self.player.assets
        if getattr(assets, resource_type) < resources:
            raise ValueError("You cannot afford to pay %s resources." % resources)
        if not self.player.player.pay_action_points(ap_cost):
            raise ValueError("You cannot afford the AP cost to work.")
        self.player.player.pay_resources(resource_type, resources)
        percent = (clout + 100) / 100.0
        outcome = int(outcome * percent)
        org_amount = outcome + resources
        prestige = ((clout * 5) + 50) * org_amount
        if org_amount:
            self.investment_this_week += org_amount
            self.investment_total += org_amount
            self.save()
            current = getattr(self.organization, "%s_influence" % resource_type)
            setattr(self.organization, "%s_influence" % resource_type, current + org_amount)
            self.organization.save()
        msg += "\nYou and %s both gain %d prestige." % (self.organization, prestige)
        self.player.assets.adjust_prestige(prestige)
        self.organization.assets.adjust_prestige(prestige)
        msg += "\nYou have increased the %s influence of %s by %d." % (resource_type, self.organization, org_amount)
        mod = getattr(self.organization, "%s_modifier" % resource_type)
        progress = self.organization.get_progress_to_next_modifier(resource_type)
        msg += "\nCurrent modifier is %s, progress to next is %d/100." % (mod, progress)
        self.msg(msg)

    def get_work_roll(self, resource_type, clout, protege=None):
        """
        Gets the result of a roll

            Args:
                resource_type (str): The type of resource
                protege (PlayerOrNpc): Protege if any
                clout (int): How much clout they have

            Returns:
                An outcome and a message

            Raises:
                ValueError if resource_type is invalid
        """
        resource_key = WorkSetting.get_choice_from_string(resource_type)
        all_assignments = self.organization.work_settings.filter(resource=resource_key)
        if not all_assignments:
            assignment = WorkSetting.create_work(self.organization, resource_key)
        elif len(all_assignments) > 1:
            from random import choice as random_choice
            skills_we_have = dict(self.char.db.skills)
            if protege:
                protege_skills = dict(protege.player.char_ob.db.skills)
                for skill, value in protege_skills.items():
                    if skill not in skills_we_have or value > skills_we_have[skill]:
                        skills_we_have[skill] = value
            assignments = all_assignments.filter(skill__in=skills_we_have.keys())
            if not assignments:
                assignment = random_choice(all_assignments)
            elif len(assignments) > 1:
                valid_skills = [ob.skill for ob in assignments]
                skill_list = [(value, skill) for (skill, value) in skills_we_have.items() if skill in valid_skills]
                highest_num = sorted(skill_list, reverse=True)[0][0]
                top_skills = [ob[1] for ob in skill_list if ob[0] >= highest_num]
                assignments = assignments.filter(skill__in=top_skills)
                assignment = random_choice(assignments)
            else:
                assignment = assignments[0]
        else:
            assignment = all_assignments[0]
        outcome, roll_msg = assignment.do_work(self, clout, protege)
        return outcome, roll_msg

    @property
    def pool_share(self):
        """Returns how much of support pool this member gets"""
        def calc_share(rank):
            """
            These are not percentages. These are the number of shares they
            get based on rank, so they are only relative to each other.
            """
            if rank == 1:
                return 30
            if rank == 2:
                return 25
            if rank == 3:
                return 20
            if rank == 4:
                return 15
            if rank == 5:
                return 5
            if rank == 6:
                return 4
            if rank == 7:
                return 3
            if rank == 8:
                return 2
            if rank == 9:
                return 1
            return 0
        total = self.organization.support_pool
        shares = 0
        active = self.organization.active_members
        if self not in active:
            return 0
        for member in active:
            shares += calc_share(member.rank)
        if not shares:
            return 0
        myshare = calc_share(self.rank)
        myshare = (myshare*total)/shares
        if total % shares:
            myshare += 1
        return myshare

    def points_used(self, catname):
        """Returns how many points they've used from a given sphere"""
        week = get_week()
        try:
            sphere = self.organization.spheres.get(category__name__iexact=catname)
        except SphereOfInfluence.DoesNotExist:
            return 0
        return sum(sphere.usage.filter(Q(supporter__player=self.player) &
                                       Q(supporter__fake=False) &
                                       Q(week=week)).values_list('rating', flat=True))

    def get_total_points_used(self, week):
        """Gets how many points they've used total"""
        total = 0
        for sphere in self.organization.spheres.all():
            total += sum(sphere.usage.filter(Q(supporter__player=self.player) &
                                             Q(supporter__fake=False) &
                                             Q(week=week)).values_list('rating', flat=True))
        return total

    @property
    def total_points_used(self):
        """Returns all points used for this current week"""
        week = get_week()
        total = self.get_total_points_used(week)
        return total

    @property
    def current_points(self):
        """Returns points remaining"""
        return self.pool_share - self.total_points_used

    def display(self):
        """Returns display of this member"""
        poolshare = self.pool_share
        used = self.total_points_used
        tasks = self.tasks.filter(finished=True)
        try:
            rep = self.organization.reputations.get(player=self.player)
        except Reputation.DoesNotExist:
            rep = None
        msg = "\n{wRank{n: %s" % self.rank
        msg += "\n{wSupport Pool Share{n: %s/%s" % (poolshare - used, poolshare)
        msg += "\n{wTotal Work{n: %s" % self.work_total
        msg += "\n{wTasks Completed{n: %s, {wTotal Rating{n: %s" % (tasks.count(), sum(task.total for task in tasks))
        if rep:
            msg += "\n{wReputation{n: {wAffection{n: %s, {wRespect:{n %s" % (rep.affection, rep.respect)
        return msg

    @property
    def rank_title(self):
        """Returns title for this member"""
        try:
            male = self.player.player.db.char_ob.db.gender.lower().startswith('m')
        except (AttributeError, ValueError, TypeError):
            male = False
        if male:
            rankstr = "rank_%s_%s" % (self.rank, "male")
        else:
            rankstr = "rank_%s_%s" % (self.rank, "female")
        return getattr(self.organization, rankstr)


class Task(SharedMemoryModel):
    """
    A task that a guild creates and then assigns to members to carry out,
    to earn them and the members income. Used to create RP.
    """
    name = models.CharField(blank=True, null=True, max_length=80, db_index=True)
    org = models.ManyToManyField('Organization', related_name='tasks', blank=True, db_index=True)
    category = models.CharField(null=True, blank=True, max_length=80)
    room_echo = models.TextField(blank=True, null=True)
    active = models.BooleanField(default=False, blank=False)
    week = models.PositiveSmallIntegerField(blank=0, default=0, db_index=True)
    desc = models.TextField(blank=True, null=True)
    difficulty = models.PositiveSmallIntegerField(blank=0, default=0)
    results = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name

    @property
    def reqs(self):
        """Returns string display of task requirements"""
        return ", ".join(str(ob.category) for ob in self.requirements.all())


class AssignedTask(SharedMemoryModel):
    """
    A task assigned to a player.
    """
    task = models.ForeignKey('Task', related_name='assigned_tasks', blank=True, null=True, db_index=True)
    member = models.ForeignKey('Member', related_name='tasks', blank=True, null=True, db_index=True)
    finished = models.BooleanField(default=False, blank=False)
    week = models.PositiveSmallIntegerField(blank=0, default=0, db_index=True)
    notes = models.TextField(blank=True, null=True)
    observer_text = models.TextField(blank=True, null=True)
    alt_echo = models.TextField(blank=True, null=True)

    @property
    def current_alt_echo(self):
        """
        Alt-echoes are a series of ; seprated strings. We return
        the first if we have one. Every new alt_echo is added at
        the start.
        """
        if not self.alt_echo:
            return self.task.room_echo
        return self.alt_echo.split(";")[0]

    @property
    def member_amount(self):
        """Reward amount for a player"""
        base = 3 * self.task.difficulty
        oflow = self.overflow
        if oflow > 0:
            base += oflow
        return base

    def get_org_amount(self, category):
        """Reward amount for an org"""
        try:
            mod = getattr(self.org, category+"_modifier") + 1
        except (TypeError, ValueError, AttributeError):
            mod = 1
        base = self.task.difficulty * mod
        oflow = self.overflow
        if oflow > 0:
            if mod > 2:
                mod = 2
            base += (mod * oflow)/2
        return base

    @property
    def overflow(self):
        """Returns how much over difficulty we got"""
        return self.total - self.task.difficulty

    @property
    def org(self):
        """Passthrough property for the org"""
        return self.member.organization

    @property
    def dompc(self):
        """Passthrough property for the PlayerOrNpc"""
        return self.member.player

    @property
    def player(self):
        """Passthrogh property for the AccountDB object"""
        return self.dompc.player

    def cleanup_request_list(self):
        """Cleans the Attribute that lists who we requested support from"""
        char = self.player.db.char_ob
        try:
            del char.db.asked_supporters[self.id]
        except (AttributeError, KeyError, TypeError, ValueError):
            pass

    def payout_check(self, week):
        """Whether this task should complete. If so, do rewards"""
        total = self.total
        category_list = self.task.category.split(",")
        if total < self.task.difficulty:
            # we failed
            return
        org = self.org
        total_rep = 0
        # set week to the week we finished
        self.week = week
        self.cleanup_request_list()
        msg = "You have completed the task: %s\n" % self.task.name
        for category in category_list:
            category = category.strip().lower()
            div = len(category_list)
            self.finished = True
            # calculate rewards. Mod for org is based on our modifier
            amt = self.member_amount
            rep = amt
            amt /= div
            # calculate resources for org. We compare multiplier for org to player mod, calc through that
            orgres = self.get_org_amount(category)/div
            memassets = self.dompc.assets
            orgassets = org.assets
            current = getattr(memassets, category)
            setattr(memassets, category, current + amt)
            current = getattr(orgassets, category)
            setattr(orgassets, category, current + orgres)
            # self.dompc.gain_reputation(org, amt, amt)
            self.save()
            memassets.save()
            orgassets.save()
            total_rep += rep
            msg += "%s Resources earned: %s\n" % (category, amt)
        # msg += "Reputation earned: %s\n" % total_rep
        # for support in self.supporters.all():
        #     support.award_renown()
        self.player.inform(msg, category="task", week=week,
                                         append=True)

    @CachedProperty
    def total(self):
        """Total support accumulated"""
        try:
            val = 0
            for sup in self.supporters.filter(fake=False):
                val += sup.rating
        except (AttributeError, TypeError, ValueError):
            val = 0
        return val

    def display(self):
        """Returns display for this task"""
        msg = "{wName{n: %s\n" % self.task.name
        msg += "{wOrganization{n %s\n" % self.member.organization.name
        msg += "{wWeek Finished{n: %s\n" % self.week
        msg += "{wTotal support{n: %s\n" % self.total
        msg += "{wSupporters:{n %s\n" % ", ".join(str(ob) for ob in self.supporters.all())
        msg += "{wNotes:{n\n%s\n" % self.notes
        msg += "{wCurrent Alt Echo:{n %s\n" % self.current_alt_echo
        msg += "{wStory:{n\n%s\n" % self.story
        return msg

    @property
    def story(self):
        """Returns story written for this task"""
        msg = self.observer_text or ""
        if not msg:
            return msg
        msg += "\n\n"
        msg += "\n\n".join(ob.observer_text for ob in self.supporters.all() if ob.observer_text)
        return msg

    def __str__(self):
        return "%s's %s" % (self.member, self.task)

    @property
    def elapsed_time(self):
        """Returns how long ago this task occurred"""
        elapsed = get_week() - self.week
        if elapsed < 1:
            return "Recently"
        if elapsed == 1:
            return "Last week"
        return "%s weeks ago" % elapsed


class TaskSupporter(SharedMemoryModel):
    """
    A player that has pledged support to someone doing a task
    """
    player = models.ForeignKey('PlayerOrNpc', related_name='supported_tasks', blank=True, null=True, db_index=True)
    task = models.ForeignKey('AssignedTask', related_name='supporters', blank=True, null=True, db_index=True)
    fake = models.BooleanField(default=False)
    spheres = models.ManyToManyField('SphereOfInfluence', related_name='supported_tasks', blank=True,
                                     through='SupportUsed')
    observer_text = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    additional_points = models.PositiveSmallIntegerField(default=0, blank=0)

    def __str__(self):
        return "%s supporting %s" % (self.player, self.task) or "Unknown supporter"

    @property
    def rating(self):
        """
        Total up our support used from different spheres of influence of our
        organizations. Add in freebie bonuses
        """
        total = 0
        if self.fake:
            return 0
        # freebie point
        total += 1
        week = get_week()
        total += (week - self.first_week)
        if self.player.supported_tasks.filter(task__member=self.task.member).first() == self:
            total += 5
        for usage in self.allocation.all():
            total += usage.rating
        total += self.additional_points
        return total

    @property
    def week(self):
        """Week this support was granted"""
        try:
            return self.allocation.all().last().week
        except AttributeError:
            return get_week()

    @property
    def first_week(self):
        """week tracking was first entered, so we have 14 to replace null values"""
        try:
            return self.allocation.all().first().week or 14
        except AttributeError:
            return 14


class Mats(object):
    """helper classes for crafting recipe to simplify API - allow for 'recipe.materials.all()'"""
    def __init__(self, mat, amount):
        self.mat = mat
        self.id = mat.id
        self.type = mat
        self.amount = amount


class MatList(object):
    """Helper class for list of mats used"""
    def __init__(self):
        self.mats = []

    def all(self):
        """All method to simplify API"""
        return self.mats


class CraftingRecipe(SharedMemoryModel):
    """
    For crafting, a recipe has a name, description, then materials. A lot of information
    is saved as a parsable text string in the 'result' text field. It'll
    take a form like: "baseval:0;scaling:1" and so on. baseval is a value
    the object has (for armor, say) for minimum quality level, while
    scaling is the increase per quality level to stats. "slot" and "slot limit"
    are used for wearable objects to denote the slot they're worn in and
    how many other objects may be worn in that slot, respectively.
    """
    name = models.CharField(blank=True, null=True, max_length=255, db_index=True)
    desc = models.TextField(blank=True, null=True)
    # organizations or players that know this recipe
    known_by = models.ManyToManyField('AssetOwner', blank=True, related_name='recipes', db_index=True)
    primary_materials = models.ManyToManyField('CraftingMaterialType', blank=True, related_name='recipes_primary')
    secondary_materials = models.ManyToManyField('CraftingMaterialType', blank=True, related_name='recipes_secondary')
    tertiary_materials = models.ManyToManyField('CraftingMaterialType', blank=True, related_name='recipes_tertiary')
    primary_amount = models.PositiveSmallIntegerField(blank=0, default=0)
    secondary_amount = models.PositiveSmallIntegerField(blank=0, default=0)
    tertiary_amount = models.PositiveSmallIntegerField(blank=0, default=0)
    difficulty = models.PositiveSmallIntegerField(blank=0, default=0)
    additional_cost = models.PositiveIntegerField(blank=0, default=0)
    # the ability/profession that is used in creating this
    ability = models.CharField(blank=True, null=True, max_length=80, db_index=True)
    skill = models.CharField(blank=True, null=True, max_length=80, db_index=True)
    # the type of object we're creating
    type = models.CharField(blank=True, null=True, max_length=80)
    # level in ability this recipe corresponds to. 1 through 6, usually
    level = models.PositiveSmallIntegerField(blank=1, default=1)
    # the result is a text field that we can later parse to determine what we create
    result = models.TextField(blank=True, null=True)
    allow_adorn = models.BooleanField(default=True, blank=True)
    # lockstring
    lock_storage = models.TextField('locks', blank=True, help_text='defined in setup_utils')

    def __init__(self, *args, **kwargs):
        super(CraftingRecipe, self).__init__(*args, **kwargs)
        self.locks = LockHandler(self)
        self.resultsdict = self.parse_result(self.result)
        self.materials = MatList()
        # create throws errors on __init__ for many to many fields
        if self.pk:
            if self.primary_amount:
                for mat in self.primary_materials.all():
                    self.materials.mats.append(Mats(mat, self.primary_amount))
            if self.secondary_amount:
                for mat in self.secondary_materials.all():
                    self.materials.mats.append(Mats(mat, self.secondary_amount))
            if self.tertiary_amount:
                for mat in self.tertiary_materials.all():
                    self.materials.mats.append(Mats(mat, self.tertiary_amount))

    def access(self, accessing_obj, access_type='learn', default=False):
        """
        Determines if another object has permission to access.
        accessing_obj - object trying to access this one
        access_type - type of access sought
        default - what to return if no lock of access_type was found
        """
        return self.locks.check(accessing_obj, access_type=access_type, default=default)

    @staticmethod
    def parse_result(results):
        """
        Given a string, return a dictionary of the different
        key:value pairs separated by semicolons
        """
        if not results:
            return {}
        rlist = results.split(";")
        keyvalpairs = [pair.split(":") for pair in rlist]
        keydict = {pair[0].strip(): pair[1].strip() for pair in keyvalpairs if len(pair) == 2}
        return keydict

    def display_reqs(self, dompc=None, full=False):
        """Returns string display for recipe"""
        msg = ""
        if full:
            msg += "{wName:{n %s\n" % self.name
            msg += "{wDescription:{n %s\n" % self.desc
        msg += "{wSilver:{n %s\n" % self.additional_cost
        tups = ((self.primary_amount, "{wPrimary Materials:{n\n", self.primary_materials),
                (self.secondary_amount, "\n{wSecondary Materials:{n\n", self.secondary_materials),
                (self.tertiary_amount, "\n{wTertiary Materials:{n\n", self.tertiary_materials),)
        for tup in tups:
            if tup[0]:
                msg += tup[1]
                if dompc:
                    msglist = []
                    for mat in tup[2].all():
                        try:
                            pcmat = dompc.assets.materials.get(type=mat)
                            amt = pcmat.amount
                        except CraftingMaterials.DoesNotExist:
                            amt = 0
                        msglist.append("%s: %s (%s/%s)" % (str(mat), tup[0], amt, tup[0]))
                    msg += ", ".join(msglist)
                else:
                    msg += ", ".join("%s: %s" % (str(ob), tup[0]) for ob in tup[2].all())
        return msg

    @CachedProperty
    def value(self):
        """Returns total cost of all materials used"""
        val = self.additional_cost
        for mat in self.primary_materials.all():
            val += mat.value * self.primary_amount
        for mat in self.secondary_materials.all():
            val += mat.value * self.secondary_amount
        for mat in self.tertiary_materials.all():
            val += mat.value * self.tertiary_amount
        return val

    def __unicode__(self):
        return self.name or "Unknown"

    @property
    def baseval(self):
        """Returns baseval used in recipes"""
        return float(self.resultsdict.get("baseval", 0.0))


class CraftingMaterialType(SharedMemoryModel):
    """
    Different types of crafting materials. We have a silver value per unit
    stored. Similar to results in CraftingRecipe, mods holds a dictionary
    of key,value pairs parsed from our acquisition_modifiers textfield. For
    CraftingMaterialTypes, this includes the category of material, and how
    difficult it is to fake it as another material of the same category
    """
    # the type of material we are
    name = models.CharField(max_length=80, db_index=True)
    desc = models.TextField(blank=True, null=True)
    # silver value per unit
    value = models.PositiveIntegerField(blank=0, default=0)
    category = models.CharField(blank=True, null=True, max_length=80, db_index=True)
    # Text we can parse for notes about cost modifiers for different orgs, locations to obtain, etc
    acquisition_modifiers = models.TextField(blank=True, null=True)

    def __init__(self, *args, **kwargs):
        super(CraftingMaterialType, self).__init__(*args, **kwargs)
        # uses same method from CraftingRecipe in order to create a dict of our mods
        self.mods = CraftingRecipe.parse_result(self.acquisition_modifiers)

    def __unicode__(self):
        return self.name or "Unknown"

    def create_instance(self, quantity):
        name_string = self.name
        if quantity > 1:
            name_string = "{} {}".format(quantity, self.name)

        result = create.create_object(key=name_string,
                                      typeclass="world.dominion.dominion_typeclasses.CraftingMaterialObject")
        result.db.desc = self.desc
        result.db.material_type = self.id
        result.db.quantity = quantity
        return result


class CraftingMaterials(SharedMemoryModel):
    """
    Materials used for crafting. Can be stored by an AssetOwner as part of their
    collection, -or- used in a recipe to measure how much they need of a material.
    If it is used in a recipe, do NOT set it owned by any asset owner, or by changing
    the amount they'll change the amount required in a recipe!
    """
    type = models.ForeignKey('CraftingMaterialType', blank=True, null=True, db_index=True)
    amount = models.PositiveIntegerField(blank=0, default=0)
    owner = models.ForeignKey('AssetOwner', blank=True, null=True, related_name='materials', db_index=True)

    class Meta:
        """Define Django meta options"""
        verbose_name_plural = "Crafting Materials"

    def __unicode__(self):
        return "%s %s" % (self.amount, self.type)

    @property
    def value(self):
        """Returns value of materials they have"""
        return self.type.value * self.amount


class RPEvent(SharedMemoryModel):
    """
    A model to store RP events created by either players or GMs. We use the PlayerOrNpc
    model instead of directly linking to players so that we can have npcs creating
    or participating in events in our history for in-character transformations of
    the event into stories. Events can be public or private, and run by a gm or not.
    Events can have money tossed at them in order to generate prestige, which
    is indicated by the celebration_tier.
    """
    NONE, COMMON, REFINED, GRAND, EXTRAVAGANT, LEGENDARY = range(6)

    LARGESSE_CHOICES = ((NONE, 'Small'), (COMMON, 'Average'), (REFINED, 'Refined'), (GRAND, 'Grand'),
                        (EXTRAVAGANT, 'Extravagant'), (LEGENDARY, 'Legendary'),)
    # costs and prestige awards
    LARGESSE_VALUES = ((NONE, (0, 0)), (COMMON, (100, 1000)), (REFINED, (1000, 5000)), (GRAND, (10000, 20000)),
                       (EXTRAVAGANT, (100000, 100000)), (LEGENDARY, (500000, 400000)))

    NO_RISK = 0
    MINIMAL_RISK = 1
    LOW_RISK = 2
    REDUCED_RISK = 3
    NORMAL_RISK = 4
    SLIGHTLY_ELEVATED_RISK = 5
    MODERATELY_ELEVATED_RISK = 6
    HIGHLY_ELEVATED_RISK = 7
    VERY_HIGH_RISK = 8
    EXTREME_RISK = 9
    SUICIDAL_RISK = 10

    RISK_CHOICES = (
        (NO_RISK, "No Risk"), (MINIMAL_RISK, "Minimal Risk"), (LOW_RISK, "Low Risk"), (REDUCED_RISK, "Reduced Risk"),
        (NORMAL_RISK, "Normal Risk"), (SLIGHTLY_ELEVATED_RISK, "Slightly Elevated Risk"),
        (MODERATELY_ELEVATED_RISK, "Moderately Elevated Risk"), (HIGHLY_ELEVATED_RISK, "Highly Elevated Risk"),
        (VERY_HIGH_RISK, "Very High Risk"), (EXTREME_RISK, "Extreme Risk"), (SUICIDAL_RISK, "Suicidal Risk"),
        )
    dompcs = models.ManyToManyField('PlayerOrNpc', blank=True, related_name='events', through='PCEventParticipation')
    orgs = models.ManyToManyField('Organization', blank=True, related_name='events', through='OrgEventParticipation')
    name = models.CharField(max_length=255, db_index=True)
    desc = models.TextField(blank=True, null=True)
    location = models.ForeignKey('objects.ObjectDB', blank=True, null=True, related_name='events_held',
                                 on_delete=models.SET_NULL)
    date = models.DateTimeField(blank=True, null=True)
    celebration_tier = models.PositiveSmallIntegerField(choices=LARGESSE_CHOICES, default=NONE, blank=True)
    gm_event = models.BooleanField(default=False)
    public_event = models.BooleanField(default=True)
    finished = models.BooleanField(default=False)
    results = models.TextField(blank=True, null=True)
    room_desc = models.TextField(blank=True, null=True)
    # a beat with a blank desc will be used for connecting us to a Plot before the Event is finished
    beat = models.ForeignKey("PlotUpdate", blank=True, null=True, related_name="events", on_delete=models.SET_NULL)
    plotroom = models.ForeignKey('PlotRoom', blank=True, null=True, related_name='events_held_here')
    risk = models.PositiveSmallIntegerField(choices=RISK_CHOICES, default=NORMAL_RISK, blank=True)
    search_tags = models.ManyToManyField('character.SearchTag', blank=True, related_name="events")

    @property
    def prestige(self):
        """Prestige granted by RP Event"""
        cel_level = self.celebration_tier
        prestige = dict(self.LARGESSE_VALUES)[cel_level][1]
        if not self.public_event:
            prestige /= 2
        return prestige

    @property
    def cost(self):
        """Silver cost of the event"""
        return dict(self.LARGESSE_VALUES)[self.celebration_tier][0]

    def can_view(self, player):
        """Who can view this RPEvent"""
        if self.public_event:
            return True
        if player.check_permstring("builders"):
            return True
        dom = player.Dominion
        if dom in self.gms.all() or dom in self.hosts.all() or dom in self.participants.all():
            return True
        if dom.current_orgs.filter(events=self).exists():
            return True

    def can_end_or_move(self, player):
        """Whether an in-progress event can be stopped or moved by a host"""
        dompc = player.Dominion
        return self.can_admin(player) or dompc in self.hosts.all() or dompc in self.gms.all()

    def can_admin(self, player):
        """Who can run admin commands for this event"""
        if player.check_permstring("builders"):
            return True
        if self.gm_event:
            return False
        try:
            dompc = player.Dominion
            if not dompc:
                return False
            return dompc == self.main_host
        except AttributeError:
            return False

    def create_room(self):
        """Creates a temp room for this RPEvent's plotroom"""
        if self.location:
            return

        if self.plotroom is None:
            return

        self.location = self.plotroom.spawn_room()
        self.save()
        return

    def clear_room(self):
        """Gets rid of a temp room"""
        if self.plotroom is None:
            return

        if self.location is None:
            return

        self.location = None
        self.save()
        return

    @property
    def hosts(self):
        """Our host or main host"""
        return self.dompcs.filter(event_participation__status__in=(PCEventParticipation.HOST,
                                                                   PCEventParticipation.MAIN_HOST))

    @property
    def participants(self):
        """Any guest who was invited/attended"""
        return self.dompcs.filter(event_participation__status=PCEventParticipation.GUEST)

    @property
    def gms(self):
        """GMs for GM Events or PRPs"""
        return self.dompcs.filter(event_participation__gm=True)

    @property
    def location_name(self):
        if self.plotroom:
            return self.plotroom.ansi_name()
        elif self.location:
            return self.location.key
        else:
            return ""

    def display(self):
        """Returns string display for event"""
        msg = "{wName:{n %s\n" % self.name
        msg += "{wHosts:{n %s\n" % ", ".join(str(ob) for ob in self.hosts.all())
        if self.beat:
            msg += "{wPlot:{n %s\n" % self.beat.plot
        if self.gms.all():
            msg += "{wGMs:{n %s\n" % ", ".join(str(ob) for ob in self.gms.all())
        if not self.finished and not self.public_event:
            # prevent seeing names of invites once a private event has started
            if self.date > datetime.now():
                msg += "{wInvited:{n %s\n" % ", ".join(str(ob) for ob in self.participants.all())
        orgs = self.orgs.all()
        if orgs:
            msg += "{wOrgs:{n %s\n" % ", ".join(str(ob) for ob in orgs)
        msg += "{wLocation:{n %s\n" % self.location_name
        if not self.public_event:
            msg += "{wPrivate:{n Yes\n"
        msg += "{wEvent Scale:{n %s\n" % self.get_celebration_tier_display()
        msg += "{wDate:{n %s\n" % self.date.strftime("%x %H:%M")
        msg += "{wDesc:{n\n%s\n" % self.desc
        webpage = PAGEROOT + self.get_absolute_url()
        msg += "{wEvent Page:{n %s\n" % webpage
        comments = self.comments.filter(db_tags__db_key="white_journal").order_by('-db_date_created')
        if comments:
            from server.utils.prettytable import PrettyTable
            msg += "\n{wComments:{n"
            table = PrettyTable(["#", "{wName{n"])
            x = 1
            for comment in comments:
                sender = ", ".join(str(ob) for ob in comment.senders)
                table.add_row([x, sender])
                x += 1
            msg += "\n%s" % (str(table))
        return msg

    def __str__(self):
        return self.name

    def __unicode__(self):
        return self.name

    @property
    def hostnames(self):
        """Returns string of all hosts"""
        return ", ".join(str(ob) for ob in self.hosts.all())

    @property
    def log(self):
        """Returns our logfile"""
        try:
            from typeclasses.scripts.event_manager import LOGPATH
            filename = LOGPATH + "event_log_%s.txt" % self.id
            with open(filename) as log:
                msg = log.read()
            return msg
        except IOError:
            return ""

    @property
    def tagkey(self):
        """
        Tagkey MUST be unique. So we have to incorporate the ID of the event
        for the tagkey in case of duplicate event names.
        """
        return "%s_%s" % (self.name.lower(), self.id)

    @property
    def tagdata(self):
        """Returns data our tag should have"""
        return str(self.id)

    @property
    def comments(self):
        """Returns queryset of Journals written about us"""
        from world.msgs.models import Journal
        return Journal.objects.filter(db_tags__db_data=self.tagdata, db_tags__db_category="event")

    @property
    def main_host(self):
        """Returns who the main host was"""
        return self.dompcs.filter(event_participation__status=PCEventParticipation.MAIN_HOST).first()

    def tag_obj(self, obj):
        """Attaches a tag to obj about this event"""
        obj.tags.add(self.tagkey, data=self.tagdata, category="event")
        return obj

    @property
    def public_comments(self):
        """Returns queryset of public comments about this event"""
        return self.comments.filter(db_tags__db_key="white_journal")

    def get_absolute_url(self):
        """Gets absolute URL for the RPEvent from their display view"""
        return reverse('dominion:display_event', kwargs={'pk': self.id})

    @CachedProperty
    def attended(self):
        """List of dompcs who attended our event, cached to avoid query with every message"""
        return list(self.dompcs.filter(event_participation__attended=True))

    def record_attendance(self, dompc):
        """Records that dompc attended the event"""
        del self.attended
        part, _ = self.pc_event_participation.get_or_create(dompc=dompc)
        part.attended = True
        part.save()

    def add_host(self, dompc, main_host=False, send_inform=True):
        """Adds a host for the event"""
        status = PCEventParticipation.MAIN_HOST if main_host else PCEventParticipation.HOST
        self.invite_dompc(dompc, 'status', status, send_inform)

    def change_host_to_guest(self, dompc):
        """Changes a host to a guest"""
        part = self.pc_event_participation.get(dompc=dompc)
        part.status = PCEventParticipation.GUEST
        part.save()

    def add_gm(self, dompc, send_inform=True):
        """Adds a gm for the event"""
        self.invite_dompc(dompc, 'gm', True, send_inform)
        if not self.gm_event and (dompc.player.is_staff or dompc.player.check_permstring("builders")):
            self.gm_event = True
            self.save()

    def untag_gm(self, dompc):
        """Removes GM tag from a participant"""
        part = self.pc_event_participation.get(dompc=dompc)
        part.gm = False
        part.save()

    def add_guest(self, dompc, send_inform=True):
        """Adds a guest to the event"""
        self.invite_dompc(dompc, 'status', PCEventParticipation.GUEST, send_inform)

    def invite_dompc(self, dompc, field, value, send_inform=True):
        """Invites a dompc to be a host, gm, or guest"""
        part, _ = self.pc_event_participation.get_or_create(dompc=dompc)
        setattr(part, field, value)
        part.save()
        if send_inform:
            self.invite_participant(part)

    def invite_org(self, org):
        """Invites an org to attend or sponsor the event"""
        part, _ = self.org_event_participation.get_or_create(org=org)
        self.invite_participant(part)

    def get_sponsor_praise_value(self, org):
        """
        Gets the multiplier and minimum for an organization sponsor of this event
        Args:
            org: Organization that's invited to the event
        Returns:
            A muliplier (float) for praises, and a minimum value for each praise.
        Raises:
            OrgEventParticipation.DoesNotExist if the org is not invited.
        """
        part = self.org_event_participation.get(org=org)
        return (part.social + 1) * (5 + (2 * self.celebration_tier))

    def invite_participant(self, participant):
        """Sends an invitation if we're not finished"""
        if not self.finished:
            participant.invite()

    def add_sponsorship(self, org, amount):
        """Adds social resources to an org's sponsorship"""
        part = self.org_event_participation.get(org=org)
        if org.assets.social < amount:
            raise PayError("%s does not have enough social resources." % org)
        org.assets.social -= amount
        part.social += amount
        part.save()
        org.assets.save()
        return part

    def remove_guest(self, dompc):
        """Removes a record of guest's attendance"""
        part = self.pc_event_participation.get(dompc=dompc)
        part.delete()

    def remove_org(self, org):
        """Removes org's invitation"""
        part = self.org_event_participation.get(org=org)
        if self.date > datetime.now():
            org.assets.social += part.social
            org.assets.save()
        part.delete()

    def make_announcement(self, msg):
        from typeclasses.accounts import Account
        msg = "{y(Private Message) %s" % msg
        guildies = Member.objects.filter(organization__in=self.orgs.all(), deguilded=False)
        all_dompcs = PlayerOrNpc.objects.filter(Q(id__in=self.dompcs.all()) | Q(memberships__in=guildies))
        audience = Account.objects.filter(Dominion__in=all_dompcs, db_is_connected=True).distinct()
        for ob in audience:
            ob.msg(msg)


class PCEventParticipation(SharedMemoryModel):
    """A PlayerOrNPC participating in an event"""
    MAIN_HOST, HOST, GUEST = range(3)
    STATUS_CHOICES = ((MAIN_HOST, "Main Host"), (HOST, "Host"), (GUEST, "Guest"))
    dompc = models.ForeignKey('PlayerOrNpc', related_name="event_participation")
    event = models.ForeignKey('RPEvent', related_name="pc_event_participation")
    status = models.PositiveSmallIntegerField(choices=STATUS_CHOICES, default=GUEST)
    gm = models.BooleanField(default=False)
    attended = models.BooleanField(default=False)

    def invite(self):
        """Sends an invitation to someone if we're not a main host"""
        if self.status != self.MAIN_HOST:
            if self.gm:
                msg = "You have been invited to GM"
            else:
                msg = "You have been invited to be a %s" % self.get_status_display()
            msg += " at {c%s.{n" % self.event
            msg += "\nFor details about this event, use {w@cal %s{n" % self.event.id
            self.dompc.inform(msg, category="Event Invitations")


class OrgEventParticipation(SharedMemoryModel):
    """An org participating in an event"""
    org = models.ForeignKey("Organization", related_name="event_participation")
    event = models.ForeignKey("RPEvent", related_name="org_event_participation")
    social = models.PositiveSmallIntegerField("Social Resources spent by the Org Sponsor", default=0)

    def invite(self):
        """Informs the org of their invitation"""
        self.org.inform("Your organization has been invited to attend %s." % self.event, category="Event Invitations")


class InfluenceCategory(SharedMemoryModel):
    """This model describes influence with different npc groups, used for organizations, players, and tasks"""
    name = models.CharField(max_length=255, unique=True, db_index=True)
    orgs = models.ManyToManyField("Organization", through="SphereOfInfluence")
    players = models.ManyToManyField("PlayerOrNpc", through="Renown")
    tasks = models.ManyToManyField("Task", through="TaskRequirement")

    class Meta:
        """Define Django meta options"""
        verbose_name_plural = "Influence Categories"

    def __str__(self):
        return self.name


class Renown(SharedMemoryModel):
    """Renown is a player's influence with an npc group, represented by InfluenceCategory"""
    category = models.ForeignKey("InfluenceCategory", db_index=True)
    player = models.ForeignKey("PlayerOrNpc", related_name="renown", db_index=True)
    rating = models.IntegerField(blank=0, default=0)

    class Meta:
        verbose_name_plural = "Renown"
        unique_together = ("category", "player")

    def __str__(self):
        return "%s's rating in %s: %s" % (self.player, self.category, self.rating)

    @property
    def level(self):
        """scaling for how our renown will be represented"""
        if self.rating <= 0:
            return 0
        if self.rating <= 1000:
            return self.rating/200
        if self.rating <= 3000:
            return 5 + (self.rating-1000)/400
        if self.rating <= 6000:
            return 10 + (self.rating-2000)/800
        if self.rating <= 13000:
            return 15 + (self.rating-4000)/1600
        return 20


class SphereOfInfluence(SharedMemoryModel):
    """Influence categories for organization - npc groups they have some influence with"""
    category = models.ForeignKey("InfluenceCategory", db_index=True)
    org = models.ForeignKey("Organization", related_name="spheres", db_index=True)
    rating = models.IntegerField(blank=0, default=0)

    class Meta:
        verbose_name_plural = "Spheres of Influence"
        unique_together = ("category", "org")

    def __str__(self):
        return "%s's rating in %s: %s" % (self.org, self.category, self.rating)

    @property
    def level(self):
        """example idea for scaling"""
        if self.rating <= 150:
            return self.rating/10
        if self.rating <= 350:
            return 15 + (self.rating-150)/20
        if self.rating <= 750:
            return 25 + (self.rating-350)/40
        if self.rating <= 1550:
            return 35 + (self.rating-750)/80
        return 45 + (self.rating-1550)/100


class TaskRequirement(SharedMemoryModel):
    """NPC groups that are required for tasks"""
    category = models.ForeignKey("InfluenceCategory", db_index=True)
    task = models.ForeignKey("Task", related_name="requirements", db_index=True)
    minimum_amount = models.PositiveSmallIntegerField(blank=0, default=0)

    def __str__(self):
        return "%s requirement: %s" % (self.task, self.category)


class SupportUsed(SharedMemoryModel):
    """Support given by a TaskSupporter for a specific task, using an npc group under 'sphere'"""
    week = models.PositiveSmallIntegerField(default=0, blank=0)
    supporter = models.ForeignKey("TaskSupporter", related_name="allocation", db_index=True)
    sphere = models.ForeignKey("SphereOfInfluence", related_name="usage", db_index=True)
    rating = models.PositiveSmallIntegerField(blank=0, default=0)

    def __str__(self):
        return "%s using %s of %s" % (self.supporter, self.rating, self.sphere)


class PlotRoom(SharedMemoryModel):
    """Model for creating templates that can be used repeatedly for temporary rooms for RP events"""
    name = models.CharField(blank=False, null=False, max_length=78, db_index=True)
    description = models.TextField(max_length=4096)
    creator = models.ForeignKey('PlayerOrNpc', related_name='created_plot_rooms', blank=True, null=True, db_index=True)
    public = models.BooleanField(default=False)

    location = models.ForeignKey('MapLocation', related_name='plot_rooms', blank=True, null=True)
    domain = models.ForeignKey('Domain', related_name='plot_rooms', blank=True, null=True)
    wilderness = models.BooleanField(default=True)

    shardhaven_type = models.ForeignKey('exploration.ShardhavenType', related_name='tilesets', blank=True, null=True)

    @property
    def land(self):
        """Returns land square from our MapLocation or domain"""
        if self.location:
            return self.location.land
        if self.domain and self.domain.location:
            return self.domain.location.land
        return None

    def ansi_name(self):
        """Returns formatted string of the platroom with region name"""
        region = self.get_region()
        region_color = "|y"
        if region and region.color_code:
            region_color = region.color_code

        if self.domain and not self.wilderness:
            if self.domain.id == 1:
                result = "|yArx"
                region_color = "|y"
            else:
                result = "|yOutside Arx"
                result += region_color + " - " + self.domain.name
            result += region_color + " - " + self.name
        elif region:
            result = "|yOutside Arx"
            result += region_color + " - " + self.get_detailed_region_name() + " - " + self.name
        else:
            result = "|yOutside Arx - " + self.name

        result += "|n"

        return result

    def get_region(self):
        """Returns the region this plotroom is located in"""
        region = None

        if self.land:
            region = self.land.region

        return region

    def get_region_name(self):
        """Returns the name of our region"""
        region = self.get_region()
        if not region:
            return "Unknown"
        else:
            return region.name

    def get_detailed_region_name(self):
        """Returns verbose name, showing the domain we're closest to"""
        if self.domain:
            if self.wilderness:
                return self.domain.land.region.name + " near " + self.domain.name
            else:
                return self.domain.name
        elif self.land:
            return self.land.region.name
        else:
            return "Unknown Territory"

    def spawn_room(self, arx_exit=True):
        """Creates and returns a temporary room"""
        room = create.create_object(typeclass='typeclasses.rooms.TempRoom',
                                    key=self.ansi_name())
        room.db.raw_desc = self.description
        room.db.desc = self.description

        if arx_exit:
            from typeclasses.rooms import ArxRoom
            try:
                city_center = ArxRoom.objects.get(id=13)
                create.create_object(settings.BASE_EXIT_TYPECLASS,
                                     key="Back to Arx <Arx>",
                                     location=room,
                                     aliases=["arx", "back to arx", "out"],
                                     destination=city_center)
            except ArxRoom.DoesNotExist:
                # Just abort and return the room
                return room

        return room

    def __str__(self):
        return "%s (%s)" % (self.name, self.get_region_name())


class Landmark(SharedMemoryModel):
    """
    This model is used to store landmarks on the map, tying them to a plot of land.
    Down the road, the domain pages can map to this via Domain -> Land -> Landmarks
    to show landmarks near a given domain.
    """

    TYPE_UNKNOWN = 0
    TYPE_FAITH = 1
    TYPE_CULTURAL = 2
    TYPE_HISTORICAL = 3

    CHOICES_TYPE = (
        (TYPE_UNKNOWN, 'Unknown'),
        (TYPE_FAITH, 'Faith'),
        (TYPE_CULTURAL, 'Cultural'),
        (TYPE_HISTORICAL, 'Historical')
    )

    name = models.CharField(blank=False, null=False, max_length=32, db_index=True)
    description = models.TextField(max_length=2048)
    location = models.ForeignKey('MapLocation', related_name='landmarks', blank=True, null=True)
    landmark_type = models.PositiveSmallIntegerField(choices=CHOICES_TYPE, default=TYPE_UNKNOWN)

    def __str__(self):
        return "<Landmark #%d: %s>" % (self.id, self.name)
