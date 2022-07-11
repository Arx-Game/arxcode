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
from collections import namedtuple
from datetime import datetime, timedelta
from random import randint, choice as random_choice
from typing import List

import typeclasses.npcs.constants
from evennia.utils.idmapper.models import SharedMemoryModel
from evennia.locks.lockhandler import LockHandler
from evennia.utils import create
from django.db import models
from django.db.models import Q, Count, F, Sum, Case, When
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.urls import reverse

from world.dominion.domain.models import LAND_SIZE, LAND_COORDS
from .reports import WeeklyReport
from .agenthandler import AgentHandler
from .managers import OrganizationManager, LandManager, RPEventQuerySet
from server.utils.arx_utils import (
    get_week,
    inform_staff,
    CachedProperty,
    CachedPropertiesMixin,
    classproperty,
    a_or_an,
    inform_guides,
    commafy,
    get_full_url,
)
from server.utils.exceptions import PayError
from typeclasses.mixins import InformMixin
from world.dominion.plots.models import Plot, PlotAction, PCPlotInvolvement
from world.stats_and_skills import do_dice_check

LIFESTYLES = {
    0: (-100, -1000),
    1: (0, 0),
    2: (100, 2000),
    3: (200, 3000),
    4: (500, 4000),
    5: (1500, 7000),
    6: (5000, 10000),
}
PRESTIGE_DECAY_AMOUNT = 0.50
MAX_PRESTIGE_HISTORY = 10


# Create your models here.
class PlayerOrNpc(SharedMemoryModel):
    """
    This is a simple model that represents that the entity can either be a PC
    or an NPC who has no presence in game, and exists only as a name in the
    database.
    """

    player = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        related_name="Dominion",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )
    npc_name = models.CharField(blank=True, null=True, max_length=255)
    parents = models.ManyToManyField(
        "self", symmetrical=False, related_name="children", blank=True
    )
    spouses = models.ManyToManyField("self", blank=True)
    alive = models.BooleanField(default=True, blank=True)
    patron = models.ForeignKey(
        "self",
        related_name="proteges",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    lifestyle_rating = models.PositiveSmallIntegerField(default=1, blank=1)
    # --- Dominion skills----
    # bonus to population growth
    population = models.PositiveSmallIntegerField(default=0, blank=True)
    # bonus to income sources
    income = models.PositiveSmallIntegerField(default=0, blank=True)
    # bonus to harvests
    farming = models.PositiveSmallIntegerField(default=0, blank=True)
    # costs for projects/commands
    productivity = models.PositiveSmallIntegerField(default=0, blank=True)
    # upkeep costs
    upkeep = models.PositiveSmallIntegerField(default=0, blank=True)
    # loyalty mod of troops/serfs
    loyalty = models.PositiveSmallIntegerField(default=0, blank=True)
    # bonus to all military combat commands
    warfare = models.PositiveSmallIntegerField(default=0, blank=True)

    def __str__(self):
        if self.player:
            name = self.player.key.capitalize()
            if not self.alive:
                name += "(RIP)"
            return name
        name = self.npc_name or ""
        if not self.alive:
            name += "(RIP)"
        return name

    @property
    def player_ob(self):
        return self.player

    def _get_siblings(self):
        return PlayerOrNpc.objects.filter(
            Q(parents__in=self.all_parents) & ~Q(id=self.id)
        ).distinct()

    def _parents_and_spouses(self):
        return PlayerOrNpc.objects.filter(
            Q(children__id=self.id) | Q(spouses__children__id=self.id)
        ).distinct()

    all_parents = property(_parents_and_spouses)

    @property
    def grandparents(self):
        """Returns queryset of our grandparents"""
        return PlayerOrNpc.objects.filter(
            Q(children__children=self)
            | Q(spouses__children__children=self)
            | Q(children__spouses__children=self)
            | Q(spouses__children__children__spouses=self)
            | Q(children__children__spouses=self)
            | Q(spouses__children__spouses__children=self)
        ).distinct()

    @property
    def greatgrandparents(self):
        """Returns queryset of our great grandparents"""
        return PlayerOrNpc.objects.filter(
            Q(children__in=self.grandparents)
            | Q(spouses__children__in=self.grandparents)
        ).distinct()

    @property
    def second_cousins(self):
        """Returns queryset of our second cousins"""
        return PlayerOrNpc.objects.filter(
            ~Q(id=self.id)
            & ~Q(id__in=self.cousins)
            & ~Q(id__in=self.siblings)
            & ~Q(id__in=self.spouses.all())
            & (
                Q(parents__parents__parents__in=self.greatgrandparents)
                | Q(parents__parents__parents__spouses__in=self.greatgrandparents)
                | Q(parents__parents__spouses__parents__in=self.greatgrandparents)
                | Q(parents__spouses__parents__parents__in=self.greatgrandparents)
            )
        ).distinct()

    def _get_cousins(self):
        return PlayerOrNpc.objects.filter(
            (
                Q(parents__parents__in=self.grandparents)
                | Q(parents__parents__spouses__in=self.grandparents)
                | Q(parents__spouses__parents__in=self.grandparents)
            )
            & ~Q(id=self.id)
            & ~Q(id__in=self.siblings)
            & ~Q(id__in=self.spouses.all())
        ).distinct()

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
            ggparents = "{wGreatgrandparents{n: %s\n" % (
                ", ".join(str(ggparent) for ggparent in ggparents)
            )
        else:
            ggparents = ""
        if grandparents:
            grandparents = "{wGrandparents{n: %s\n" % (
                ", ".join(str(gparent) for gparent in grandparents)
            )
        else:
            grandparents = ""
        if parents:
            parents = "{wParents{n: %s\n" % (
                ", ".join(str(parent) for parent in parents)
            )
        else:
            parents = ""
        if spouses:
            spouses = "{wSpouses{n: %s\n" % (
                ", ".join(str(spouse) for spouse in spouses)
            )
        else:
            spouses = ""
        if unc_or_aunts:
            unc_or_aunts = "{wUncles/Aunts{n: %s\n" % (
                ", ".join(str(unc) for unc in unc_or_aunts)
            )
        else:
            unc_or_aunts = ""
        if siblings:
            siblings = "{wSiblings{n: %s\n" % (", ".join(str(sib) for sib in siblings))
        else:
            siblings = ""
        if neph_or_nieces:
            neph_or_nieces = "{wNephews/Nieces{n: %s\n" % (
                ", ".join(str(neph) for neph in neph_or_nieces)
            )
        else:
            neph_or_nieces = ""
        if children:
            children = "{wChildren{n: %s\n" % (
                ", ".join(str(child) for child in children)
            )
        else:
            children = ""
        if grandchildren:
            grandchildren = "{wGrandchildren{n: %s\n" % (
                ", ".join(str(gchild) for gchild in grandchildren)
            )
        else:
            grandchildren = ""
        if cousins:
            cousins = "{wCousins{n: %s\n" % (
                ", ".join(str(cousin) for cousin in cousins)
            )
        else:
            cousins = ""
        if second_cousins:
            second_cousins = "{wSecond Cousins{n: %s\n" % (
                ", ".join(str(seco) for seco in second_cousins)
            )
        else:
            second_cousins = ""
        return (
            ggparents
            + grandparents
            + parents
            + unc_or_aunts
            + spouses
            + siblings
            + children
            + neph_or_nieces
            + cousins
            + second_cousins
            + grandchildren
        )

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
            self.reputations.create(
                organization=org, affection=affection, respect=respect
            )

    @property
    def current_orgs(self):
        """Returns Organizations we have not been deguilded from"""
        org_ids = self.memberships.filter(deguilded=False).values_list(
            "organization", flat=True
        )
        return Organization.objects.filter(id__in=org_ids)

    @property
    def public_orgs(self):
        """Returns non-secret organizations we haven't been deguilded from"""
        org_ids = self.memberships.filter(deguilded=False, secret=False).values_list(
            "organization", flat=True
        )
        return Organization.objects.filter(id__in=org_ids, secret=False)

    @property
    def secret_orgs(self):
        """Returns secret organizations we haven't been deguilded from"""
        secret_ids = self.memberships.filter(deguilded=False, secret=True).values_list(
            "organization", flat=True
        )
        return Organization.objects.filter(
            Q(secret=True) | Q(id__in=secret_ids)
        ).distinct()

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
                report.lifestyle_msg = (
                    "%s paid %s for your lifestyle and you gained %s prestige.\n"
                    % (payname, cost, prestige)
                )

        if assets.vault > cost:
            pay_and_adjust(assets)
            return True
        orgs = [ob for ob in self.current_orgs if ob.access(self.player, "withdraw")]
        if not orgs:
            return False
        for org in orgs:
            if org.assets.vault > cost:
                pay_and_adjust(org.assets)
                return True
        # no one could pay for us
        if report:
            report.lifestyle_msg = (
                "You were unable to afford to pay for your lifestyle.\n"
            )
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
            max_support = self.player.char_ob.max_support
        except AttributeError:
            import traceback

            traceback.print_exc()
            return cdowns
        qs = SupportUsed.objects.select_related(
            "supporter__task__member__player"
        ).filter(Q(supporter__player=self) & Q(supporter__fake=False))

        def process_week(qset, week_offset=0):
            """Helper function for changing support cooldowns"""
            qset = qset.filter(week=week + week_offset)
            for used in qset:
                member = used.supporter.task.member
                pc = member.player.player.char_ob
                points = cdowns.get(pc.id, max_support)
                points -= used.rating
                cdowns[pc.id] = points
            if week_offset:
                for name in cdowns.keys():
                    cdowns[name] += max_support / 3
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
            max_support = self.player.char_ob.max_support
            points_spent = sum(
                SupportUsed.objects.filter(
                    Q(week=week) & Q(supporter__player=self) & Q(supporter__fake=False)
                ).values_list("rating", flat=True)
            )

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
        return self.actions.filter(
            Q(date_submitted__gte=old)
            & ~Q(status__in=(PlotAction.CANCELLED, PlotAction.DRAFT))
            & Q(free_action=False)
        )

    @property
    def recent_assists(self):
        """Returns queryset of all assists from the past 30 days"""
        from datetime import timedelta

        offset = timedelta(days=-PlotAction.num_days)
        old = datetime.now() + offset
        actions = PlotAction.objects.filter(
            Q(date_submitted__gte=old)
            & ~Q(status__in=(PlotAction.CANCELLED, PlotAction.DRAFT))
            & Q(free_action=False)
        )
        return self.assisting_actions.filter(
            plot_action__in=actions, free_action=False
        ).distinct()

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
        return self.events.filter(
            pc_event_participation__status__in=(
                PCEventParticipation.HOST,
                PCEventParticipation.MAIN_HOST,
            )
        )

    @property
    def events_gmd(self):
        """Events we GM'd"""
        return self.events.filter(pc_event_participation__gm=True)

    @property
    def events_attended(self):
        """Events we were a guest at or invited to attend"""
        return self.events.filter(
            pc_event_participation__status=PCEventParticipation.GUEST
        )

    @property
    def num_fealties(self):
        """How many distinct fealties we're a part of."""
        no_fealties = self.current_orgs.filter(fealty__isnull=True).count()
        query = Q()
        for category in Organization.CATEGORIES_WITH_FEALTY_PENALTIES:
            query |= Q(category__iexact=category)
        redundancies = (
            self.current_orgs.filter(query)
            .values_list("category")
            .annotate(num=Count("category") - 1)
        )
        no_fealties += sum(ob[1] for ob in redundancies)
        return (
            Fealty.objects.filter(orgs__in=self.current_orgs).distinct().count()
            + no_fealties
        )

    @property
    def active_plots(self):
        return self.plots.filter(
            dompc_involvement__activity_status=PCPlotInvolvement.ACTIVE,
            usage__in=(Plot.GM_PLOT, Plot.PLAYER_RUN_PLOT),
        ).distinct()

    @property
    def plots_we_can_gm(self):
        return self.active_plots.filter(
            dompc_involvement__admin_status__gte=PCPlotInvolvement.GM
        ).distinct()


# noinspection PyMethodParameters,PyPep8Naming
class PrestigeCategory(SharedMemoryModel):
    """Categories of different kinds of prestige adjustments, whether it's from events, fashion, combat, etc."""

    name = models.CharField(max_length=30, blank=False, null=False)
    male_noun = models.CharField(max_length=30, blank=False, null=False)
    female_noun = models.CharField(max_length=30, blank=False, null=False)
    description = models.CharField(max_length=80, blank=True, null=True)

    CACHED_TYPES = {}

    @classmethod
    def category_for_name(cls, name):
        if name in cls.CACHED_TYPES:
            return cls.CACHED_TYPES[name]

        try:
            result = cls.objects.get(name=name)
            cls.CACHED_TYPES[name] = result
        except (
            PrestigeCategory.DoesNotExist,
            PrestigeCategory.MultipleObjectsReturned,
        ):
            return None

    @classproperty
    def FASHION(cls):
        return cls.category_for_name("Fashion")

    @classproperty
    def EVENT(cls):
        return cls.category_for_name("Event")

    @classproperty
    def CHAMPION(cls):
        return cls.category_for_name("Champion")

    @classproperty
    def ATHLETICS(cls):
        return cls.category_for_name("Athletics")

    @classproperty
    def MILITARY(cls):
        return cls.category_for_name("Military")

    @classproperty
    def DESIGN(cls):
        return cls.category_for_name("Design")

    @classproperty
    def INVESTMENT(cls):
        return cls.category_for_name("Investment")

    @classproperty
    def CHARITY(cls):
        return cls.category_for_name("Charity")

    def __str__(self):
        return self.name


class PrestigeAdjustment(SharedMemoryModel):
    """A record of adjusting an AssetOwner's prestige"""

    FAME = 0
    LEGEND = 1

    PRESTIGE_TYPES = ((FAME, "Fame"), (LEGEND, "Legend"))

    asset_owner = models.ForeignKey(
        "AssetOwner", related_name="prestige_adjustments", on_delete=models.CASCADE
    )
    category = models.ForeignKey(
        PrestigeCategory, related_name="+", on_delete=models.CASCADE
    )
    adjustment_type = models.PositiveSmallIntegerField(
        default=FAME, choices=PRESTIGE_TYPES
    )
    adjusted_on = models.DateTimeField(auto_now_add=True, blank=False, null=False)
    adjusted_by = models.IntegerField(default=0)
    reason = models.TextField(blank=True, null=True)
    long_reason = models.TextField(blank=True, null=True)

    @property
    def effective_value(self):
        if self.adjustment_type == PrestigeAdjustment.LEGEND:
            return self.adjusted_by

        now = datetime.now()
        weeks = (now - self.adjusted_on).days // 7
        decay_multiplier = PRESTIGE_DECAY_AMOUNT**weeks
        return int(round(self.adjusted_by * decay_multiplier))


class PrestigeTier(SharedMemoryModel):
    """Used for displaying people's descriptions of why they're prestigious"""

    rank_name = models.CharField(max_length=30, blank=False, null=False)
    minimum_prestige = models.PositiveIntegerField(blank=False, null=False)

    @classmethod
    def rank_for_prestige(cls, value, max_value):
        if value < -1000000:
            return "infamous"
        elif value < -100000:
            return "shameful"

        results = cls.objects.order_by("-minimum_prestige")
        percentage = round((value / (max_value or 1)) * 100)
        for result in results.all():
            if percentage >= result.minimum_prestige:
                return result.rank_name

        return None

    def __str__(self):
        return self.rank_name


class PrestigeNomination(SharedMemoryModel):
    """Used for storing a player nomination for a prestige adjustment."""

    TYPE_FAME = 0
    TYPE_LEGEND = 1

    TYPES = ((TYPE_FAME, "Fame"), (TYPE_LEGEND, "Legend"))

    SIZE_SMALL = 0
    SIZE_MEDIUM = 1
    SIZE_LARGE = 2
    SIZE_HUGE = 3

    SIZES = (
        (SIZE_SMALL, "Small"),
        (SIZE_MEDIUM, "Medium"),
        (SIZE_LARGE, "Large"),
        (SIZE_HUGE, "Huge"),
    )

    AMOUNTS = {
        TYPE_FAME: {
            SIZE_SMALL: 100000,
            SIZE_MEDIUM: 250000,
            SIZE_LARGE: 500000,
            SIZE_HUGE: 1000000,
        },
        TYPE_LEGEND: {
            SIZE_SMALL: 5000,
            SIZE_MEDIUM: 10000,
            SIZE_LARGE: 25000,
            SIZE_HUGE: 50000,
        },
    }

    pending = models.BooleanField(default=True)
    approved = models.BooleanField(default=False)

    nominator = models.ForeignKey(
        "PlayerOrNpc",
        blank=False,
        null=False,
        related_name="+",
        on_delete=models.CASCADE,
    )
    nominees = models.ManyToManyField("AssetOwner", related_name="+")
    category = models.ForeignKey(
        "PrestigeCategory",
        blank=False,
        null=False,
        related_name="+",
        on_delete=models.CASCADE,
    )
    adjust_type = models.PositiveSmallIntegerField(default=TYPE_FAME, choices=TYPES)
    adjust_size = models.PositiveSmallIntegerField(default=SIZE_SMALL, choices=SIZES)
    reason = models.CharField(max_length=40, blank=True, null=True)
    long_reason = models.TextField(blank=False, null=False)

    approved_by = models.ManyToManyField("PlayerOrNpc", related_name="+")
    denied_by = models.ManyToManyField("PlayerOrNpc", related_name="+")

    APPROVALS_REQUIRED = 3
    DENIALS_REQUIRED = 3

    def approve(self, caller):
        dom_obj = caller.player_ob.Dominion

        if dom_obj in self.approved_by.all():
            return

        if dom_obj in self.denied_by.all():
            self.denied_by.remove(dom_obj)

        self.approved_by.add(caller.player_ob.Dominion)
        self.save()
        if self.approved_by.count() >= self.__class__.APPROVALS_REQUIRED:
            self.apply()

    def deny(self, caller):
        dom_obj = caller.player_ob.Dominion

        if dom_obj in self.denied_by.all():
            return

        if dom_obj in self.approved_by.all():
            self.approved_by.remove(dom_obj)

        self.denied_by.add(caller.player_ob.Dominion)
        self.save()
        if self.denied_by.count() >= self.__class__.DENIALS_REQUIRED:
            inform_guides("|wPRESTIGE:|n Nomination %d has been denied." % self.id)
            self.pending = False
            self.approved = False
            self.save()

    def apply(self):
        if not self.pending:
            return

        adjust_amount = PrestigeNomination.AMOUNTS[self.adjust_type][self.adjust_size]
        targets = []
        for target in self.nominees.all():
            targets.append("|y" + str(target.owner) + "|n")
            if self.adjust_type == PrestigeNomination.TYPE_FAME:
                target.adjust_prestige(
                    adjust_amount,
                    category=self.category,
                    reason=self.reason,
                    long_reason=self.long_reason,
                )
            elif self.adjust_type == PrestigeNomination.TYPE_LEGEND:
                target.adjust_legend(
                    adjust_amount,
                    category=self.category,
                    reason=self.reason,
                    long_reason=self.long_reason,
                )

        comma_targets = commafy(targets)
        verb = "was"
        if len(targets) > 1:
            verb = "were"
        type_noun = "fame"
        if self.adjust_type == PrestigeNomination.TYPE_LEGEND:
            type_noun = "legend"

        size_name = "small"
        for size_tup in PrestigeNomination.SIZES:
            if size_tup[0] == self.adjust_size:
                size_name = size_tup[1].lower()

        inform_guides("|wPRESTIGE:|n Nomination %d has been approved." % self.id)
        summary = "%s %s just given %d %s %s: %s" % (
            comma_targets,
            verb,
            adjust_amount,
            str(self.category),
            type_noun,
            self.long_reason,
        )

        inform_staff(summary)

        from typeclasses.bulletin_board.bboard import BBoard

        board = BBoard.objects.get(db_key__iexact="vox populi")
        subject = "Reputation changes"
        post_msg = "%s %s just given %s %s %s adjustment:\n\n%s" % (
            comma_targets,
            verb,
            a_or_an(size_name),
            size_name,
            type_noun,
            self.long_reason,
        )
        post = board.bb_post(
            poster_obj=None,
            poster_name="Prestige Nomination",
            msg=post_msg,
            subject=subject,
        )
        post.tags.add("reputation_change")

        self.pending = False
        self.approved = True
        self.save()


# noinspection PyMethodParameters,PyPep8Naming,PyTypeChecker
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

    player = models.OneToOneField(
        "PlayerOrNpc",
        related_name="assets",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )
    organization_owner = models.OneToOneField(
        "Organization",
        related_name="assets",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )

    # money stored in the bank
    vault = models.PositiveIntegerField(default=0, blank=True)
    # prestige we've earned
    fame = models.IntegerField(default=0, blank=True)
    legend = models.IntegerField(default=0, blank=True)
    # resources
    economic = models.PositiveIntegerField(default=0, blank=True)
    military = models.PositiveIntegerField(default=0, blank=True)
    social = models.PositiveIntegerField(default=0, blank=True)

    min_silver_for_inform = models.PositiveIntegerField(default=0)
    min_resources_for_inform = models.PositiveIntegerField(default=0)
    min_materials_for_inform = models.PositiveIntegerField(default=0)

    _AVERAGE_PRESTIGE = {"last_check": None, "last_value": 0}
    _AVERAGE_FAME = {"last_check": None, "last_value": 0}
    _AVERAGE_LEGEND = {"last_check": None, "last_value": 0}
    _MEDIAN_PRESTIGE = {"last_check": None, "last_value": 0}
    _MEDIAN_FAME = {"last_check": None, "last_value": 0}
    _MEDIAN_LEGEND = {"last_check": None, "last_value": 0}

    @classproperty
    def AVERAGE_PRESTIGE(cls):
        last_check = cls._AVERAGE_PRESTIGE["last_check"]
        now = datetime.now()
        if not last_check or (now - last_check).days >= 1:
            cls._AVERAGE_PRESTIGE["last_check"] = now
            assets = list(
                AssetOwner.objects.filter(
                    player__player__roster__roster__name__in=(
                        "Active",
                        "Gone",
                        "Available",
                    )
                )
            )
            assets = sorted(assets, key=lambda x: x.prestige, reverse=True)
            total = 0
            for asset in assets:
                total += asset.prestige
            total = total / len(assets)
            cls._AVERAGE_PRESTIGE["last_value"] = total

        return cls._AVERAGE_PRESTIGE["last_value"]

    @classproperty
    def MEDIAN_PRESTIGE(cls):
        last_check = cls._MEDIAN_PRESTIGE["last_check"]
        now = datetime.now()
        if not last_check or (now - last_check).days >= 1:
            cls._MEDIAN_PRESTIGE["last_check"] = now
            assets = list(
                AssetOwner.objects.filter(
                    player__player__roster__roster__name__in=(
                        "Active",
                        "Gone",
                        "Available",
                    )
                )
            )
            assets = sorted(assets, key=lambda x: x.prestige, reverse=True)

            median = assets[len(assets) // 2].prestige

            cls._MEDIAN_PRESTIGE["last_value"] = median

        return cls._MEDIAN_PRESTIGE["last_value"]

    @classproperty
    def AVERAGE_FAME(cls):
        last_check = cls._AVERAGE_FAME["last_check"]
        now = datetime.now()
        if not last_check or (now - last_check).days >= 1:
            cls._AVERAGE_FAME["last_check"] = now
            assets = list(
                AssetOwner.objects.filter(
                    player__player__roster__roster__name__in=(
                        "Active",
                        "Gone",
                        "Available",
                    )
                ).order_by("-fame")
            )
            total = 0
            for asset in assets:
                total += asset.fame
            total = total / len(assets)
            cls._AVERAGE_FAME["last_value"] = total

        return cls._AVERAGE_FAME["last_value"]

    @classproperty
    def MEDIAN_FAME(cls):
        last_check = cls._MEDIAN_FAME["last_check"]
        now = datetime.now()
        if not last_check or (now - last_check).days >= 1:
            cls._MEDIAN_FAME["last_check"] = now
            assets = list(
                AssetOwner.objects.filter(
                    player__player__roster__roster__name__in=(
                        "Active",
                        "Gone",
                        "Available",
                    )
                )
            )
            assets = sorted(assets, key=lambda x: x.prestige, reverse=True)

            median = assets[len(assets) / 2].fame

            cls._MEDIAN_FAME["last_value"] = median

        return cls._MEDIAN_FAME["last_value"]

    @classproperty
    def AVERAGE_LEGEND(cls):
        last_check = cls._AVERAGE_LEGEND["last_check"]
        now = datetime.now()
        if not last_check or (now - last_check).days >= 1:
            cls._AVERAGE_LEGEND["last_check"] = now
            assets = list(
                AssetOwner.objects.filter(
                    player__player__roster__roster__name__in=(
                        "Active",
                        "Gone",
                        "Available",
                    )
                )
            )
            assets = sorted(assets, key=lambda x: x.total_legend, reverse=True)
            total = 0
            for asset in assets:
                total += asset.total_legend
            total = total / len(assets)
            cls._AVERAGE_LEGEND["last_value"] = total

        return cls._AVERAGE_LEGEND["last_value"]

    @classproperty
    def MEDIAN_LEGEND(cls):
        last_check = cls._MEDIAN_LEGEND["last_check"]
        now = datetime.now()
        if not last_check or (now - last_check).days >= 1:
            cls._MEDIAN_LEGEND["last_check"] = now
            assets = list(
                AssetOwner.objects.filter(
                    player__player__roster__roster__name__in=(
                        "Active",
                        "Gone",
                        "Available",
                    )
                )
            )
            assets = sorted(assets, key=lambda x: x.prestige, reverse=True)

            median = assets[len(assets) / 2].total_legend

            cls._MEDIAN_LEGEND["last_value"] = median

        return cls._MEDIAN_LEGEND["last_value"]

    @CachedProperty
    def prestige(self):
        """Our prestige used for different mods. aggregate of fame, legend, and grandeur"""
        return self.fame + self.total_legend + self.grandeur + self.propriety

    def descriptor_for_value_adjustment(
        self,
        value,
        max_value,
        best_adjust,
        include_reason=True,
        wants_long_reason=False,
    ):
        qualifier = PrestigeTier.rank_for_prestige(value, max_value)
        result = None
        reason = None
        long_reason = best_adjust and best_adjust.long_reason
        if best_adjust:
            if include_reason:
                reason = (
                    long_reason
                    if wants_long_reason and long_reason
                    else best_adjust.reason
                )
            char = self.player.player.char_ob
            gender = char.item_data.gender or "Male"
            if gender.lower() == "male":
                result = best_adjust.category.male_noun
            else:
                result = best_adjust.category.female_noun

        if not result:
            result = "citizen"

        if qualifier:
            result = "%s %s" % (qualifier, result)

        if reason:
            result = "%s, known for %s" % (result, reason)

        result = "%s, %s %s" % (self.player.player.name, a_or_an(result), result)

        return result

    def prestige_descriptor(
        self, adjust_type=None, include_reason=True, wants_long_reason=False
    ):
        if not self.player:
            return self.organization_owner.name

        value = self.prestige
        max_value = AssetOwner.MEDIAN_PRESTIGE

        return self.descriptor_for_value_adjustment(
            value,
            max_value,
            self.most_notable_adjustment(adjust_type=adjust_type),
            wants_long_reason=wants_long_reason,
            include_reason=include_reason,
        )

    @CachedProperty
    def propriety(self):
        """A modifier to our fame based on tags we have"""
        percentage = max(sum(ob.percentage for ob in self.proprieties.all()), -100)
        base = self.fame + self.total_legend
        # if we have negative fame, then positive propriety mods lessens that, while neg mods makes it worse
        if base < 0:
            percentage *= -1
        value = int(base * percentage / 100.0)
        if self.player:
            # It's not possible to use F expressions on datetime fields so we'll check a range of dates
            now = datetime.now()
            last_week = now - timedelta(days=7)
            two_weeks = now - timedelta(days=14)
            three_weeks = now - timedelta(days=21)
            four_weeks = now - timedelta(days=28)
            # number of weeks since the favor was set, + 1, cap at a month ago
            num_weeks = Case(
                When(date_gossip_set__isnull=True, then=1),
                When(date_gossip_set__lte=four_weeks, then=5),
                When(date_gossip_set__lte=three_weeks, then=4),
                When(date_gossip_set__lte=two_weeks, then=3),
                When(date_gossip_set__lte=last_week, then=2),
                default=1,
            )
            # the base prestige they get from each org, then modified by their favor value
            org_prestige = (
                F("organization__assets__fame") + F("organization__assets__legend")
            ) / (20 * F("num_weeks"))
            val = org_prestige * F("favor")
            favor = (
                self.player.reputations.filter(Q(favor__gt=0) | Q(favor__lt=0))
                .annotate(num_weeks=num_weeks)
                .annotate(val=val)
                .aggregate(sum=Sum("val"))
            )["sum"] or 0
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
            return prestige ** (1.0 / 3.0)
        return -((-prestige) ** (1.0 / 3.0))

    def get_bonus_resources(self, base_amount, random_percentage=None):
        """Calculates the amount of bonus resources we get from prestige."""
        mod = self.prestige_mod
        bonus = (mod * base_amount) / 100.0
        if random_percentage is not None:
            bonus = (bonus * randint(50, int(random_percentage))) / 100.0
        return int(bonus)

    def get_bonus_income(self, base_amount):
        """Calculates the bonus to domain/org income we get from prestige."""
        return self.get_bonus_resources(base_amount) / 4

    def _get_owner(self):
        if self.player:
            return self.player
        if self.organization_owner:
            return self.organization_owner
        return None

    owner = property(_get_owner)

    def __str__(self):
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
        return int(self.fame / 10.0 + self.total_legend / 10.0 + self.propriety / 10.0)

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
        memberships = list(
            self.player.memberships.filter(
                deguilded=False, secret=False, organization__secret=False
            ).distinct()
        )
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
        too_many_members_mod = max(ranks / 200.0, 0.01)
        base /= too_many_members_mod
        sign = -1 if base < 0 else 1
        return min(abs(int(base)), abs(self.fame + self.legend) * 2) * sign

    # noinspection PyMethodMayBeStatic
    def store_prestige_record(
        self,
        value,
        adjustment_type=PrestigeAdjustment.FAME,
        category=None,
        reason=None,
        long_reason=None,
    ):
        if not category:
            return

        old_adjustments = PrestigeAdjustment.objects.filter(
            asset_owner=self, adjustment_type=adjustment_type
        )
        new_adjustment = PrestigeAdjustment.objects.create(
            asset_owner=self,
            category=category,
            adjustment_type=adjustment_type,
            adjusted_by=value,
            reason=reason,
            long_reason=long_reason,
        )

        if old_adjustments.count() >= MAX_PRESTIGE_HISTORY:
            # Remove our least-notable adjustments to get us back under the limit
            extras = old_adjustments.count() - MAX_PRESTIGE_HISTORY
            for i in range(0, extras + 1):
                least = new_adjustment
                for adjustment in old_adjustments.all():
                    if adjustment.effective_value < least.effective_value:
                        least = adjustment

                least.delete()

    def most_notable_adjustment(self, adjust_type=None):
        greatest = None
        adjustments = PrestigeAdjustment.objects.filter(asset_owner=self)
        if adjust_type:
            adjustments = adjustments.filter(adjustment_type=adjust_type)

        for adjustment in adjustments.all():
            if not greatest or adjustment.effective_value > greatest.effective_value:
                greatest = adjustment

        return greatest

    def adjust_prestige(self, value, category=None, reason=None, long_reason=None):
        """
        Adjusts our prestige. We gain fame equal to the value. We no longer
        adjust the legend, per Apos.
        """
        self.fame += value
        self.save()

        if category:
            self.store_prestige_record(
                value,
                adjustment_type=PrestigeAdjustment.FAME,
                category=category,
                reason=reason,
                long_reason=long_reason,
            )

    def adjust_legend(self, value, category=None, reason=None, long_reason=None):
        """
        Adjusts our legend. We gain legend equal to the value.
        """
        self.legend += value
        self.save()

        if category:
            self.store_prestige_record(
                value,
                adjustment_type=PrestigeAdjustment.LEGEND,
                category=category,
                reason=reason,
                long_reason=long_reason,
            )

    @CachedProperty
    def income(self):
        income = 0
        if self.organization_owner:
            income += self.organization_owner.amount
        for amt in self.incomes.filter(do_weekly=True).exclude(category="vassal taxes"):
            income += amt.weekly_amount
        if not hasattr(self, "estate"):
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
        if not hasattr(self, "estate"):
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
        if hasattr(self, "estate"):
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
        if (
            self.player
            and self.player.player
            and hasattr(self.player.player, "roster")
            and self.player.player.roster.roster.name == "Active"
        ):
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
        if hasattr(self, "estate"):
            msg += "{wHoldings{n: %s\n" % ", ".join(
                str(dom) for dom in self.estate.holdings.all()
            )
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

    def access(self, accessing_obj, access_type="agent", default=False):
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
    owners = models.ManyToManyField("AssetOwner", related_name="proprieties")

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

    owner = models.ForeignKey(
        "AssetOwner", related_name="honorifics", on_delete=models.CASCADE
    )
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

    praiser = models.ForeignKey(
        "PlayerOrNpc", related_name="praises_given", on_delete=models.CASCADE
    )
    target = models.ForeignKey(
        "AssetOwner", related_name="praises_received", on_delete=models.CASCADE
    )
    message = models.TextField(blank=True)
    week = models.PositiveSmallIntegerField(default=0, blank=True)
    db_date_created = models.DateTimeField(auto_now_add=True)
    value = models.IntegerField(default=0)
    number_used = models.PositiveSmallIntegerField(
        help_text="Number of praises/condemns used from weekly pool", default=1
    )

    @property
    def verb(self):
        """Helper property for distinguishing which verb to use in strings"""
        return "praised" if self.value >= 0 else "condemned"

    def do_prestige_adjustment(self):
        """Adjusts the prestige of the target after they're praised."""
        self.target.adjust_prestige(self.value)
        msg = "%s has %s you. " % (self.praiser, self.verb)
        msg += "Your prestige has been adjusted by {:,}.".format(self.value)
        self.target.inform(msg, category=self.verb.capitalize())


class CharitableDonation(SharedMemoryModel):
    """
    Represents all donations from a character to an Organization or Npc Group. They receive some affection
    and prestige in exchange for giving silver.
    """

    giver = models.ForeignKey(
        "AssetOwner", related_name="donations", on_delete=models.CASCADE
    )
    organization = models.ForeignKey(
        "Organization",
        related_name="donations",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )
    npc_group = models.ForeignKey(
        "InfluenceCategory",
        related_name="donations",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )
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
        roll = do_dice_check(
            caller=caller, stat="charm", skill="propaganda", difficulty=10
        )
        roll += caller.social_clout
        if roll <= 1:
            roll = 1
        roll /= 4.0
        roll *= value / 2.0
        prest = int(roll)
        self.giver.adjust_prestige(prest, category=PrestigeCategory.CHARITY)
        player = self.giver.player
        if caller != character:
            msg = "%s donated %s silver to %s on your behalf.\n" % (
                caller,
                value,
                self.receiver,
            )
        else:
            msg = "You donate %s silver to %s.\n" % (value, self.receiver)
        if self.organization and player:
            reputation = player.reputations.filter(
                organization=self.organization
            ).first()
            affection = 0
            respect = 0
            if reputation:
                if roll < reputation.affection:
                    msg += (
                        " Though the charity is appreciated, your reputation"
                        " with %s does not change. Ingrates.\n" % self.organization
                    )
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

    receiver = models.ForeignKey(
        "AssetOwner",
        related_name="incomes",
        blank=True,
        null=True,
        db_index=True,
        on_delete=models.CASCADE,
    )

    sender = models.ForeignKey(
        "AssetOwner",
        related_name="debts",
        blank=True,
        null=True,
        db_index=True,
        on_delete=models.CASCADE,
    )
    # quick description of the type of transaction. taxes between liege/vassal, etc
    category = models.CharField(blank=True, null=True, max_length=255)

    weekly_amount = models.PositiveIntegerField(default=0, blank=True)

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

    def __str__(self):
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
    origin_x_coord = models.SmallIntegerField(default=0, blank=True)
    origin_y_coord = models.SmallIntegerField(default=0, blank=True)

    color_code = models.CharField(max_length=8, blank=True)

    def __str__(self):
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
        (COAST, "Coast"),
        (DESERT, "Desert"),
        (GRASSLAND, "Grassland"),
        (HILL, "Hill"),
        (MOUNTAIN, "Mountain"),
        (OCEAN, "Ocean"),
        (PLAINS, "Plains"),
        (SNOW, "Snow"),
        (TUNDRA, "Tundra"),
        (FOREST, "Forest"),
        (JUNGLE, "Jungle"),
        (MARSH, "Marsh"),
        (ARCHIPELAGO, "Archipelago"),
        (FLOOD_PLAINS, "Flood Plains"),
        (ICE, "Ice"),
        (LAKES, "Lakes"),
        (OASIS, "Oasis"),
    )

    name = models.CharField(max_length=80, blank=True, null=True)
    desc = models.TextField(blank=True, null=True)
    x_coord = models.SmallIntegerField(default=0, blank=True)
    y_coord = models.SmallIntegerField(default=0, blank=True)

    terrain = models.PositiveSmallIntegerField(choices=TERRAIN_CHOICES, default=PLAINS)

    region = models.ForeignKey(
        "Region", on_delete=models.SET_NULL, blank=True, null=True
    )
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
        high_farm = (
            Land.COAST,
            Land.LAKES,
            Land.PLAINS,
            Land.GRASSLAND,
            Land.FLOOD_PLAINS,
        )
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

    def __str__(self):
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

    land = models.ForeignKey(
        "Land", related_name="hostiles", blank=True, null=True, on_delete=models.CASCADE
    )
    desc = models.TextField(blank=True, null=True)
    from django.core.validators import MaxValueValidator

    area = models.PositiveSmallIntegerField(
        validators=[MaxValueValidator(LAND_SIZE)], default=0, blank=True
    )
    # the type of hostiles controlling this area
    type = models.PositiveSmallIntegerField(default=0, blank=True)
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
    land = models.ForeignKey(
        "Land",
        on_delete=models.SET_NULL,
        related_name="locations",
        blank=True,
        null=True,
    )
    from django.core.validators import MaxValueValidator

    x_coord = models.PositiveSmallIntegerField(
        validators=[MaxValueValidator(LAND_COORDS)], default=0
    )
    y_coord = models.PositiveSmallIntegerField(
        validators=[MaxValueValidator(LAND_COORDS)], default=0
    )

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


class OrgRelationship(SharedMemoryModel):
    """
    The relationship between two or more organizations.
    """

    name = models.CharField(
        "Name of the relationship", max_length=255, db_index=True, blank=True
    )
    orgs = models.ManyToManyField(
        "Organization", related_name="relationships", blank=True, db_index=True
    )
    status = models.SmallIntegerField(default=0, blank=True)
    history = models.TextField("History of these organizations", blank=True)


class Reputation(SharedMemoryModel):
    """
    A player's reputation to an organization.
    """

    player = models.ForeignKey(
        "PlayerOrNpc",
        related_name="reputations",
        blank=True,
        null=True,
        db_index=True,
        on_delete=models.CASCADE,
    )
    organization = models.ForeignKey(
        "Organization",
        related_name="reputations",
        blank=True,
        null=True,
        db_index=True,
        on_delete=models.CASCADE,
    )
    # negative affection is dislike/hatred
    affection = models.IntegerField(default=0)
    # positive respect is respect/fear, negative is contempt/dismissal
    respect = models.IntegerField(default=0)
    favor = models.IntegerField(
        help_text="A percentage of the org's prestige applied to player's propriety.",
        default=0,
    )
    npc_gossip = models.TextField(blank=True)
    date_gossip_set = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return "%s for %s (%s)" % (self.player, self.organization, self.favor)

    class Meta:
        unique_together = ("player", "organization")

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
            weeks = (
                (datetime.now() - (self.date_gossip_set or datetime.now())).days / 7
            ) + 1
            return (
                self.favor
                * (self.organization.assets.fame + self.organization.assets.legend)
                / (20 * weeks)
            )
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
    fealty = models.ForeignKey(
        "Fealty", blank=True, null=True, related_name="orgs", on_delete=models.SET_NULL
    )
    # In a RP game, titles are IMPORTANT. And we need to divide them by gender.
    rank_1_male = models.CharField(
        default="Prince", blank=True, null=True, max_length=255
    )
    rank_1_female = models.CharField(
        default="Princess", blank=True, null=True, max_length=255
    )
    rank_2_male = models.CharField(
        default="Voice", blank=True, null=True, max_length=255
    )
    rank_2_female = models.CharField(
        default="Voice", blank=True, null=True, max_length=255
    )
    rank_3_male = models.CharField(
        default="Noble Family", blank=True, null=True, max_length=255
    )
    rank_3_female = models.CharField(
        default="Noble Family", blank=True, null=True, max_length=255
    )
    rank_4_male = models.CharField(
        default="Trusted House Servants", blank=True, null=True, max_length=255
    )
    rank_4_female = models.CharField(
        default="Trusted House Servants", blank=True, null=True, max_length=255
    )
    rank_5_male = models.CharField(
        default="Noble Vassals", blank=True, null=True, max_length=255
    )
    rank_5_female = models.CharField(
        default="Noble Vassals", blank=True, null=True, max_length=255
    )
    rank_6_male = models.CharField(
        default="Vassals of Esteem", blank=True, null=True, max_length=255
    )
    rank_6_female = models.CharField(
        default="Vassals of Esteem", blank=True, null=True, max_length=255
    )
    rank_7_male = models.CharField(
        default="Known Commoners", blank=True, null=True, max_length=255
    )
    rank_7_female = models.CharField(
        default="Known Commoners", blank=True, null=True, max_length=255
    )
    rank_8_male = models.CharField(
        default="Sworn Commoners", blank=True, null=True, max_length=255
    )
    rank_8_female = models.CharField(
        default="Sworn Commoners", blank=True, null=True, max_length=255
    )
    rank_9_male = models.CharField(
        default="Forgotten Commoners", blank=True, null=True, max_length=255
    )
    rank_9_female = models.CharField(
        default="Forgotten Commoners", blank=True, null=True, max_length=255
    )
    rank_10_male = models.CharField(
        default="Serf", blank=True, null=True, max_length=255
    )
    rank_10_female = models.CharField(
        default="Serf", blank=True, null=True, max_length=255
    )
    npc_members = models.PositiveIntegerField(default=0, blank=True)
    income_per_npc = models.PositiveSmallIntegerField(default=0, blank=True)
    cost_per_npc = models.PositiveSmallIntegerField(default=0, blank=True)
    morale = models.PositiveSmallIntegerField(default=100, blank=100)
    # this is used to represent temporary windfalls or crises that must be resolved
    income_modifier = models.PositiveSmallIntegerField(default=100, blank=100)
    # whether players can use the @work command
    allow_work = models.BooleanField(default=False, blank=False)
    # whether we can be publicly viewed
    secret = models.BooleanField(default=False, blank=False)
    # lockstring
    lock_storage = models.TextField(
        "locks", blank=True, help_text="defined in setup_utils"
    )
    special_modifiers = models.TextField(blank=True, null=True)
    motd = models.TextField(blank=True, null=True)
    # used for when resource gain
    economic_influence = models.IntegerField(default=0)
    military_influence = models.IntegerField(default=0)
    social_influence = models.IntegerField(default=0)
    base_support_value = models.SmallIntegerField(default=5)
    member_support_multiplier = models.SmallIntegerField(default=5)
    clues = models.ManyToManyField(
        "character.Clue", blank=True, related_name="orgs", through="ClueForOrg"
    )
    theories = models.ManyToManyField(
        "character.Theory", blank=True, related_name="orgs"
    )
    org_channel = models.OneToOneField(
        "comms.ChannelDB",
        blank=True,
        null=True,
        related_name="org",
        on_delete=models.SET_NULL,
    )
    org_board = models.OneToOneField(
        "objects.ObjectDB",
        blank=True,
        null=True,
        related_name="org",
        on_delete=models.SET_NULL,
    )
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
        return round(influence / float(influence_required), 2) * 100

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
        npc_income = (npc_income * self.income_modifier) / 100.0
        npc_income += self.assets.get_bonus_income(npc_income)
        npc_cost = self.npc_members * self.cost_per_npc
        return int(npc_income) - npc_cost

    amount = property(_get_npc_money)

    def __str__(self):
        return self.name or "Unnamed organization (#%s)" % self.id

    def __repr__(self):
        return "<Org (#%s): %s>" % (self.id, self.name)

    def display_members(self, start=1, end=10, viewing_member=None, show_all=False):
        """Returns string display of the org"""
        pcs = self.all_members
        active = self.active_members
        if viewing_member:
            # exclude any secret members that are higher in rank than viewing member
            members_to_exclude = pcs.filter(
                Q(rank__lte=viewing_member.rank) & ~Q(id=viewing_member.id)
            )
            if not self.secret:
                members_to_exclude = members_to_exclude.filter(secret=True)
            pcs = pcs.exclude(id__in=members_to_exclude)
        elif not show_all:
            pcs = pcs.exclude(secret=True)
        msg = ""
        for rank in range(start, end + 1):
            chars = pcs.filter(rank=rank)
            male_title = getattr(self, "rank_%s_male" % rank)
            female_title = getattr(self, "rank_%s_female" % rank)
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
                msg += "{w%s{n (Rank %s): %s\n" % (
                    title,
                    rank,
                    ", ".join(char_name(char) for char in chars),
                )
            elif len(chars) > 0:
                char = chars[0]
                name = char_name(char)
                char = char.player.player.char_ob
                gender = char.item_data.gender or "Male"
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
            msg += "\n{wLeaders of %s:\n%s\n" % (
                self.name,
                self.display_members(end=2, show_all=show_all),
            )
        msg += "{wWebpage{n: %s\n" % get_full_url(self.get_absolute_url())
        return msg

    def display(self, viewing_member=None, display_clues=False, show_all=False):
        """Returns string display of org"""
        if hasattr(self, "assets"):
            money = self.assets.vault
            try:
                display_money = not viewing_member or self.assets.can_be_viewed_by(
                    viewing_member.player.player
                )
            except AttributeError:
                display_money = False
            prestige = self.assets.prestige
            if hasattr(self.assets, "estate"):
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
        members = self.display_members(
            start=start, viewing_member=viewing_member, show_all=show_all
        )
        if members:
            members = "{wMembers of %s:\n%s" % (self.name, members)
        msg += members
        if display_money:
            msg += "\n{{wMoney{{n: {:>10,}".format(money)
            msg += " {{wPrestige{{n: {:>10,}".format(prestige)
            prestige_mod = self.assets.prestige_mod
            resource_mod = int(prestige_mod)

            def mod_string(amount):
                """Helper function to format resource modifier string"""
                return "%s%s%%" % ("+" if amount > 0 else "", amount)

            income_mod = int(prestige_mod / 4)
            msg += " {wResource Mod:{n %s {wIncome Mod:{n %s" % (
                mod_string(resource_mod),
                mod_string(income_mod),
            )
            msg += "\n{wResources{n: Economic: %s, Military: %s, Social: %s" % (
                self.assets.economic,
                self.assets.military,
                self.assets.social,
            )
        econ_progress = self.get_progress_to_next_modifier("economic")
        mil_progress = self.get_progress_to_next_modifier("military")
        soc_progress = self.get_progress_to_next_modifier("social")
        msg += "\n"
        msg += "{wMods: Economic:{n %s (%s/100), " % (
            self.economic_modifier,
            int(econ_progress),
        )
        msg += "{wMilitary:{n %s (%s/100), " % (
            self.military_modifier,
            int(mil_progress),
        )
        msg += "{wSocial:{n %s (%s/100)\n" % (self.social_modifier, int(soc_progress))
        # msg += "{wSpheres of Influence:{n %s\n" % ", ".join("{w%s{n: %s" % (ob.category, ob.rating)
        #                                                     for ob in self.spheres.all())
        msg += self.display_work_settings()
        msg += self.display_story_coordinators()
        clues = self.clues.all()
        if display_clues:
            if viewing_member:
                entry = viewing_member.player.player.roster
                discovered_clues = entry.clues.all()
            else:
                discovered_clues = []
            if clues:
                msg += "\n{wClues Known:"
                for clue in clues:
                    if clue in discovered_clues:

                        msg += "{n %s;" % clue
                    else:
                        msg += "{w %s{n;" % clue
                msg += "\n"
            theories = self.theories.all()
            if theories:
                msg += "\n{wTheories Known:{n %s\n" % "; ".join(
                    "%s (#%s)" % (ob, ob.id) for ob in theories
                )
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

        work_settings = self.work_settings.all().order_by("resource")
        msg = "\n{wWork Settings:{n"
        if not work_settings:
            return msg + " None found.\n"
        table = PrettyTable(["{wResource{n", "{wStat{n", "{wSkill{n"])
        for setting in work_settings:
            table.add_row([setting.get_resource_display(), setting.stat, setting.skill])
        msg += "\n" + str(table) + "\n"
        return msg

    def display_story_coordinators(self):
        """Shows the story coordinators in the org"""
        sc = self.active_members.filter(story_coordinator=True)
        msg = "\n{wStory Coordinators:{n " + ", ".join(str(ob) for ob in sc) + "\n"
        return msg

    def __init__(self, *args, **kwargs):
        super(Organization, self).__init__(*args, **kwargs)
        self.locks = LockHandler(self)

    @property
    def default_access_rank(self):
        """What rank to default to if they don't set permission"""
        return 2 if self.secret else 10

    def access(self, accessing_obj, access_type="read", default=False):
        """
        Determines if another object has permission to access.
        accessing_obj - object trying to access this one
        access_type - type of access sought
        default - what to return if no lock of access_type was found
        """
        if access_type not in self.locks.locks.keys():
            try:
                obj = accessing_obj.player_ob or accessing_obj
                member = obj.Dominion.memberships.get(
                    deguilded=False, organization=self
                )
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
            bboard.bb_post(
                poster_obj=gemit.sender,
                msg=gemit.text,
                subject=category,
                poster_name="Story",
            )
        for pc in self.offline_members:
            pc.inform(gemit.text, category=category, append=False)
        box_chars = "\n" + "*" * 70 + "\n"
        msg = box_chars + "[" + category + "] " + gemit.text + box_chars
        self.msg(msg, prefix=False)

    @property
    def active_members(self):
        """Returns queryset of players in active roster and not deguilded"""
        return self.members.filter(
            Q(player__player__roster__roster__name="Active") & Q(deguilded=False)
        ).distinct()

    @property
    def story_coordinators(self):
        return self.active_members.filter(story_coordinator=True)

    @property
    def story_coordinator_names(self):
        return "; ".join(str(ob) for ob in self.story_coordinators)

    @property
    def living_members(self):
        """Returns queryset of players in active or available roster and not deguilded"""
        return self.members.filter(
            (
                Q(player__player__roster__roster__name="Active")
                | Q(player__player__roster__roster__name="Available")
            )
            & Q(deguilded=False)
        ).distinct()

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
        return self.active_members.filter(
            player__player__db_is_connected=True
        ).distinct()

    @property
    def offline_members(self):
        """Returns members who are currently offline"""
        return self.active_members.exclude(id__in=self.online_members)

    @property
    def support_pool(self):
        """Returns our current support pool"""
        return (
            self.base_support_value
            + (self.active_members.count()) * self.member_support_multiplier
        )

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
        return reverse("help_topics:display_org", kwargs={"object_id": self.id})

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
        members = [
            pc
            for pc in self.online_members
            if pc.player
            and pc.player.player
            and self.access(pc.player.player, "informs")
        ]
        for pc in members:
            pc.msg(
                "{y%s has new @informs. Use {w@informs/org %s/%s{y to read them."
                % (self, self, index)
            )

    def setup(self):
        """Sets up the org with channel and board"""
        from typeclasses.channels import Channel
        from typeclasses.bulletin_board.bboard import BBoard
        from evennia.utils.create import create_object, create_channel

        lockstr = (
            "send: organization(%s) or perm(builders);listen: organization(%s) or perm(builders)"
            % (self, self)
        )
        if not self.org_channel:
            self.org_channel = create_channel(
                key=str(self.name),
                desc="%s channel" % self,
                locks=lockstr,
                typeclass=Channel,
            )
        if not self.org_board:
            lockstr = lockstr.replace("send", "read").replace("listen", "write")
            self.org_board = create_object(
                typeclass=BBoard, key=str(self.name), locks=lockstr
            )
        self.save()

    def set_motd(self, message):
        """Sets our motd, notifies people, sets their flags."""
        self.motd = message
        self.save()
        self.msg(
            "|yMessage of the day for %s set to:|n %s" % (self, self.motd), prefix=False
        )
        for pc in self.offline_members.filter(has_seen_motd=True):
            pc.has_seen_motd = False
            pc.save()

    def display_plots_to_player(self, player, resolved=False) -> str:
        """Returns a message of org plots that the player has access to"""
        rank = 11
        if player.is_staff:
            rank = 1
        else:
            try:
                member = self.active_members.get(player__player=player)
                rank = member.rank
            except Member.DoesNotExist:
                pass
        # list of all plots
        plots = self.plot_involvement.filter(
            rank_requirement__gte=rank, plot__resolved=resolved
        )
        return "\n".join([ob.display_plot_for_org() for ob in plots])

    def add_plot(self, plot, rank):
        inv, _ = self.plot_involvement.get_or_create(plot=plot)
        inv.rank_requirement = rank
        inv.save()

    def remove_plot(self, plot):
        try:
            inv = self.plot_involvement.get(plot=plot)
            inv.delete()
        except ObjectDoesNotExist:
            pass


class ClueForOrg(SharedMemoryModel):
    """Model that shows a clue known by an org"""

    clue = models.ForeignKey(
        "character.Clue",
        related_name="org_discoveries",
        db_index=True,
        on_delete=models.CASCADE,
    )
    org = models.ForeignKey(
        "Organization",
        related_name="clue_discoveries",
        db_index=True,
        on_delete=models.CASCADE,
    )
    revealed_by = models.ForeignKey(
        "character.RosterEntry",
        related_name="clues_added_to_orgs",
        blank=True,
        null=True,
        db_index=True,
        on_delete=models.CASCADE,
    )

    class Meta:
        unique_together = ("clue", "org")

    def __str__(self):
        return f"{self.org} knows {self.clue}"


class Agent(SharedMemoryModel):
    """
    Types of npcs that can be employed by a player or an organization. The
    Agent instance represents a class of npc - whether it's a group of spies,
    armed guards, hired assassins, a pet dragon, whatever. Type is an integer
    that will be defined elsewhere in an agent file. ObjectDB points to Agent
    as a foreignkey, and we access that set through self.agent_objects.
    """

    GUARD = typeclasses.npcs.constants.GUARD
    THUG = typeclasses.npcs.constants.THUG
    SPY = typeclasses.npcs.constants.SPY
    ASSISTANT = typeclasses.npcs.constants.ASSISTANT
    CHAMPION = typeclasses.npcs.constants.CHAMPION
    ANIMAL = typeclasses.npcs.constants.ANIMAL
    SMALL_ANIMAL = typeclasses.npcs.constants.SMALL_ANIMAL
    NPC_TYPE_CHOICES = (
        (GUARD, "Guard"),
        (THUG, "Thug"),
        (SPY, "Spy"),
        (ASSISTANT, "Assistant"),
        (CHAMPION, "Champion"),
        (ANIMAL, "Animal"),
        (SMALL_ANIMAL, "Small Animal"),
    )
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
    owner = models.ForeignKey(
        "AssetOwner",
        on_delete=models.SET_NULL,
        related_name="agents",
        blank=True,
        null=True,
        db_index=True,
    )
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
        return self.quantity + sum(
            self.agent_objects.values_list("quantity", flat=True)
        )

    total = property(_get_total_num)

    def _get_active(self):
        return self.agent_objects.filter(quantity__gte=1)

    active = property(_get_active)

    def __str__(self):
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
            self.id,
            self.pretty_name,
            self.type_str,
            self.quality,
        )
        if not self.unique:
            msg += " {wUnassigned:{n %s\n" % self.quantity
        else:
            msg += "\n{wXP:{n %s {wLoyalty{n: %s\n" % (self.xp, self.loyalty)
        if not show_assignments:
            return msg
        msg += ", ".join(
            agent.display(caller=caller)
            for agent in self.agent_objects.filter(quantity__gt=0)
        )
        return msg

    def assign(self, targ, num):
        """
        Assigns num agents to target character object.
        """
        if num > self.quantity:
            raise ValueError(
                "Agent only has %s to assign, asked for %s." % (self.quantity, num)
            )
        self.npcs.assign(targ, num)

    def find_assigned(self, player):
        """
        Asks our agenthandler to find the AgentOb with a dbobj assigned
        to guard the given character. Returns the first match, returns None
        if not found.
        """
        return self.npcs.find_agentob_by_character(player.char_ob)

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

    def access(self, accessing_obj, access_type="agent", default=False):
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
            if attr == "weapon_damage":
                attr_max = (self.quality + 2) * 2
            elif attr == "difficulty_mod":
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

    @property
    def xp_training_cap(self):
        """How much xp can the agent be trained"""
        return self.dbobj.xp_training_cap

    @xp_training_cap.setter
    def xp_training_cap(self, value):
        self.dbobj.xp_training_cap = value

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

    agentob = models.ForeignKey(
        "AgentOb",
        related_name="missions",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )
    active = models.BooleanField(default=True, blank=True)
    success_level = models.SmallIntegerField(default=0, blank=True)
    description = models.TextField(blank=True, null=True)
    category = models.CharField(blank=True, null=True, max_length=80)
    mission_details = models.TextField(blank=True, null=True)
    results = models.TextField(blank=True, null=True)


class AgentOb(SharedMemoryModel):
    """
    Allotment from an Agent class that has a representation in-game.
    """

    agent_class = models.ForeignKey(
        "Agent",
        related_name="agent_objects",
        blank=True,
        null=True,
        db_index=True,
        on_delete=models.CASCADE,
    )
    dbobj = models.OneToOneField(
        "objects.ObjectDB", blank=True, null=True, on_delete=models.CASCADE
    )
    quantity = models.PositiveIntegerField(default=0, blank=True)
    # whether they're imprisoned, by whom, difficulty to free them, etc
    status_notes = models.TextField(blank=True, null=True)

    @property
    def guarding(self):
        """Returns who the agent is guarding"""
        if not self.dbobj:
            return None
        return self.dbobj.item_data.guarding

    def __str__(self):
        return "%s%s" % (
            self.agent_class,
            (" guarding %s" % self.guarding) if self.guarding else "",
        )

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

    def access(self, accessing_obj, access_type="agent", default=False):
        """Checks whether someone can control the agent"""
        return self.agent_class.access(accessing_obj, access_type, default)


class WorkSetting(SharedMemoryModel):
    """
    An Organization's options for work performed by its members. For a particular
    resource, a number of work_settings may exist and the member's highest Skill
    will primarily decide which one is used. If a member relies on their protege,
    the highest skill between them both will be used to choose a work_setting.
    """

    RESOURCE_TYPES = ("Economic", "Military", "Social")
    RESOURCE_CHOICES = tuple(enumerate(RESOURCE_TYPES))

    organization = models.ForeignKey(
        "Organization", related_name="work_settings", on_delete=models.CASCADE
    )
    stat = models.CharField(blank=True, null=True, max_length=80)
    skill = models.CharField(blank=True, null=True, max_length=80)
    resource = models.PositiveSmallIntegerField(choices=RESOURCE_CHOICES, default=0)
    message = models.TextField(blank=True)

    def __str__(self):
        return "%s-%s for %s" % (
            self.get_resource_display(),
            str(self.skill).capitalize(),
            self.organization,
        )

    @classmethod
    def get_choice_from_string(cls, string):
        """Checks if a string names a type of resource and returns its choice number."""
        for int_constant, name in cls.RESOURCE_CHOICES:
            if string.lower() == name.lower():
                return int_constant
        raise ValueError(
            "Type must be one of these: %s." % ", ".join(sorted(cls.RESOURCE_TYPES))
        )

    @classmethod
    def create_work(cls, organization, resource_key):
        """Creates a new WorkSetting with default stat and skill chosen."""
        default_settings = {
            0: ["intellect", "economics"],
            1: ["command", "war"],
            2: ["charm", "diplomacy"],
        }
        stat = default_settings[resource_key][0]
        skill = default_settings[resource_key][1]
        return cls.objects.create(
            organization=organization, stat=stat, skill=skill, resource=resource_key
        )

    def do_work(self, clout, roller):
        """Does rolls for a given WorkSetting for character/protege. Returns roll and msg."""
        msg_spacer = " " if self.message else ""
        difficulty = 15 - clout
        org_mod = getattr(
            self.organization, "%s_modifier" % self.get_resource_display().lower()
        )
        roll_msg = "\n%s%s%s rolling %s and %s. " % (
            self.message,
            msg_spacer,
            roller.key,
            self.stat,
            self.skill,
        )
        outcome = do_dice_check(
            roller,
            stat=self.stat,
            skill=self.skill,
            difficulty=difficulty,
            bonus_dice=org_mod,
            bonus_keep=org_mod // 2,
        )
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

    player = models.ForeignKey(
        "PlayerOrNpc",
        related_name="memberships",
        blank=True,
        null=True,
        db_index=True,
        on_delete=models.CASCADE,
    )
    commanding_officer = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        related_name="subordinates",
        blank=True,
        null=True,
    )
    organization = models.ForeignKey(
        "Organization",
        related_name="members",
        blank=True,
        null=True,
        db_index=True,
        on_delete=models.CASCADE,
    )
    story_coordinator = models.BooleanField(
        "Whether they're a coordinator for this org", default=False
    )
    # work they've gained
    work_this_week = models.PositiveSmallIntegerField(default=0, blank=True)
    work_total = models.PositiveSmallIntegerField(default=0, blank=True)
    # amount of org influence they've gained
    investment_this_week = models.SmallIntegerField(default=0)
    investment_total = models.SmallIntegerField(default=0)
    secret = models.BooleanField(blank=False, default=False)
    deguilded = models.BooleanField(blank=False, default=False)

    # a rare case of us not using a player object, since we may designate any type of object as belonging
    # to an organization - character objects without players (npcs), rooms, exits, items, etc.
    object = models.ForeignKey(
        "objects.ObjectDB",
        related_name="memberships",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )

    rank = models.PositiveSmallIntegerField(blank=10, default=10)

    pc_exists = models.BooleanField(
        blank=True,
        default=True,
        help_text="Whether this member is a player character in the database",
    )
    # stuff that players may set for their members:
    desc = models.TextField(blank=True)
    public_notes = models.TextField(blank=True)
    officer_notes = models.TextField(blank=True)
    has_seen_motd = models.BooleanField(default=False)

    class Meta:
        ordering = ["rank"]

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
                bonus_msg += " Amount modified by %s%s resources due to prestige." % (
                    "+" if bonus > 0 else "",
                    bonus,
                )
            if assets != self.player.assets:
                inform_msg = (
                    "%s has been hard at work, and %s has gained %s %s resources."
                    % (self, assets, amount, resource_type)
                )
                assets.inform(inform_msg + bonus_msg, category="Work", append=True)
            else:
                self.player.player.msg(msg + bonus_msg)

        def get_amount_after_clout(clout_value, added=100, minimum=0):
            """helper function to calculate clout modifier on outcome amount"""
            percent = (clout_value + added) / 100.0
            total = int(outcome * percent)
            if total < minimum:
                total = minimum
            return total

        patron_amount = get_amount_after_clout(clout, minimum=randint(1, 10))
        if randint(0, 100) < 4:
            # we got a big crit, hooray. Add a base of 1-30 resources to bonus, then triple the bonus
            patron_amount += randint(1, 50)
            patron_amount *= 3
            msg += " Luck has gone %s's way, and they get a bonus! " % self
        msg += "You have gained %s %s resources." % (patron_amount, resource_type)
        adjust_resources(self.player.assets, patron_amount)
        org_amount = patron_amount // 5
        if org_amount:
            adjust_resources(self.organization.assets, org_amount)
            self.work_this_week += org_amount
            self.work_total += org_amount
            self.save()
        if protege:
            adjust_resources(
                protege.assets,
                get_amount_after_clout(protege_clout, added=25, minimum=1),
            )

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
        prestige = ((clout * 5) + 50) * org_amount * 2
        if org_amount:
            self.investment_this_week += org_amount
            self.investment_total += org_amount
            self.save()
            current = getattr(self.organization, "%s_influence" % resource_type)
            setattr(
                self.organization, "%s_influence" % resource_type, current + org_amount
            )
            self.organization.save()
        msg += "\nYou and {} both gain {:,} prestige.".format(
            self.organization, prestige
        )
        self.player.assets.adjust_prestige(prestige, PrestigeCategory.INVESTMENT)
        self.organization.assets.adjust_prestige(prestige)
        msg += "\nYou have increased the {} influence of {} by {:,}.".format(
            resource_type, self.organization, org_amount
        )
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
        all_assignments = list(
            self.organization.work_settings.filter(resource=resource_key)
        )
        if not all_assignments:
            all_assignments.append(
                WorkSetting.create_work(self.organization, resource_key)
            )
        assignment, roller = self.get_assignment_and_roller(protege, all_assignments)
        outcome, roll_msg = assignment.do_work(clout, roller)
        return outcome, roll_msg

    def get_assignment_and_roller(self, protege, all_assignments):
        """
        Determines the assignment and the character attempting it.
        Args:
            protege (PlayerOrNpc): Protege or None
            all_assignments (list): list of assignments

        Returns:
            An assignment, and the character who will roll its skill check.
        """
        Assignment = namedtuple("Assignment", ["obj", "stat", "skill"])
        Knack = namedtuple("Knack", ["roller", "stat", "skill", "value"])
        Match = namedtuple("Match", ["assignment", "roller", "value"])

        def get_by_skill() -> Match:
            """Choosing based on skills when nobody has knacks."""
            Skill = namedtuple("Skill", ["roller", "skill", "value"])
            skills_we_have = dict(self.char.traits.skills)
            our_skills = [
                Skill(self.char, skill, value)
                for skill, value in skills_we_have.items()
            ]
            if protege:
                protege_skills = dict(protege.traits.skills)
                our_skills += [
                    Skill(protege, skill, value)
                    for skill, value in protege_skills.items()
                ]
            matches = []
            for skillset in our_skills:
                for job in clipboard:
                    if skillset.skill == job.skill:
                        matches.append(Match(job.obj, skillset.roller, skillset.value))
            if len(matches) < 1:
                assignment, roller = random_choice(clipboard), self.char
                rollers = [ob for ob in our_skills if ob.skill == assignment.skill]
                if protege and len(rollers) > 1:
                    roller = rollers[0].roller
                matches.append(
                    Match(
                        assignment.obj,
                        roller,
                        roller.traits.get_skill_value(assignment.skill),
                    )
                )
            return get_random_match_from_highest_values(matches)

        def get_random_match_from_highest_values(matches_list: List[Match]) -> Match:
            """
            Given a list of matches, determines highest value then returns random choice from
            any match that has that value.
            """
            high_value = max([ob.value for ob in matches_list])
            matches_list = [ob for ob in matches_list if ob.value >= high_value]
            return random_choice(matches_list)

        matches = []
        clipboard = [Assignment(ob, ob.stat, ob.skill) for ob in all_assignments]
        our_knacks = [
            Knack(ob.object, ob.stat, ob.skill, ob.value)
            for ob in self.char.mods.knacks
        ]
        if protege:
            protege = protege.player.char_ob
            our_knacks += [
                Knack(ob.object, ob.stat, ob.skill, ob.value)
                for ob in protege.mods.knacks
            ]
        if len(our_knacks) > 0:
            for job in clipboard:
                for knack in our_knacks:
                    if job.stat == knack.stat and job.skill == knack.skill:
                        matches.append(Match(job.obj, knack.roller, knack.value))
        if len(matches) < 1:
            match = get_by_skill()
        else:
            match = get_random_match_from_highest_values(matches)
        return match.assignment, match.roller

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
        myshare = (myshare * total) // shares
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
        return sum(
            sphere.usage.filter(
                Q(supporter__player=self.player)
                & Q(supporter__fake=False)
                & Q(week=week)
            ).values_list("rating", flat=True)
        )

    def get_total_points_used(self, week):
        """Gets how many points they've used total"""
        total = 0
        for sphere in self.organization.spheres.all():
            total += sum(
                sphere.usage.filter(
                    Q(supporter__player=self.player)
                    & Q(supporter__fake=False)
                    & Q(week=week)
                ).values_list("rating", flat=True)
            )
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
        msg += "\n{wTasks Completed{n: %s, {wTotal Rating{n: %s" % (
            tasks.count(),
            sum(task.total for task in tasks),
        )
        if rep:
            msg += "\n{wReputation{n: {wAffection{n: %s, {wRespect:{n %s" % (
                rep.affection,
                rep.respect,
            )
        return msg

    @property
    def rank_title(self):
        """Returns title for this member"""
        try:
            male = self.player.player.char_ob.item_data.gender.lower().startswith("m")
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
    org = models.ManyToManyField(
        "Organization", related_name="tasks", blank=True, db_index=True
    )
    category = models.CharField(null=True, blank=True, max_length=80)
    room_echo = models.TextField(blank=True, null=True)
    active = models.BooleanField(default=False, blank=False)
    week = models.PositiveSmallIntegerField(blank=True, default=0, db_index=True)
    desc = models.TextField(blank=True, null=True)
    difficulty = models.PositiveSmallIntegerField(blank=True, default=0)
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

    task = models.ForeignKey(
        "Task",
        related_name="assigned_tasks",
        blank=True,
        null=True,
        db_index=True,
        on_delete=models.CASCADE,
    )
    member = models.ForeignKey(
        "Member",
        related_name="tasks",
        blank=True,
        null=True,
        db_index=True,
        on_delete=models.CASCADE,
    )
    finished = models.BooleanField(default=False, blank=False)
    week = models.PositiveSmallIntegerField(blank=True, default=0, db_index=True)
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
            mod = getattr(self.org, category + "_modifier") + 1
        except (TypeError, ValueError, AttributeError):
            mod = 1
        base = self.task.difficulty * mod
        oflow = self.overflow
        if oflow > 0:
            if mod > 2:
                mod = 2
            base += (mod * oflow) / 2
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
        char = self.player.char_ob
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
            orgres = self.get_org_amount(category) / div
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
        self.player.inform(msg, category="task", week=week, append=True)

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
        msg += "{wSupporters:{n %s\n" % ", ".join(
            str(ob) for ob in self.supporters.all()
        )
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
        msg += "\n\n".join(
            ob.observer_text for ob in self.supporters.all() if ob.observer_text
        )
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

    player = models.ForeignKey(
        "PlayerOrNpc",
        related_name="supported_tasks",
        blank=True,
        null=True,
        db_index=True,
        on_delete=models.CASCADE,
    )
    task = models.ForeignKey(
        "AssignedTask",
        related_name="supporters",
        blank=True,
        null=True,
        db_index=True,
        on_delete=models.CASCADE,
    )
    fake = models.BooleanField(default=False)
    spheres = models.ManyToManyField(
        "SphereOfInfluence",
        related_name="supported_tasks",
        blank=True,
        through="SupportUsed",
    )
    observer_text = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    additional_points = models.PositiveSmallIntegerField(default=0, blank=True)

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
        total += week - self.first_week
        if (
            self.player.supported_tasks.filter(task__member=self.task.member).first()
            == self
        ):
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

    LARGESSE_CHOICES = (
        (NONE, "Small"),
        (COMMON, "Average"),
        (REFINED, "Refined"),
        (GRAND, "Grand"),
        (EXTRAVAGANT, "Extravagant"),
        (LEGENDARY, "Legendary"),
    )
    # costs and prestige awards
    LARGESSE_VALUES = (
        (NONE, (0, 0)),
        (COMMON, (100, 10000)),
        (REFINED, (1000, 50000)),
        (GRAND, (10000, 200000)),
        (EXTRAVAGANT, (100000, 1000000)),
        (LEGENDARY, (500000, 4000000)),
    )

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
        (NO_RISK, "No Risk"),
        (MINIMAL_RISK, "Minimal Risk"),
        (LOW_RISK, "Low Risk"),
        (REDUCED_RISK, "Reduced Risk"),
        (NORMAL_RISK, "Normal Risk"),
        (SLIGHTLY_ELEVATED_RISK, "Slightly Elevated Risk"),
        (MODERATELY_ELEVATED_RISK, "Moderately Elevated Risk"),
        (HIGHLY_ELEVATED_RISK, "Highly Elevated Risk"),
        (VERY_HIGH_RISK, "Very High Risk"),
        (EXTREME_RISK, "Extreme Risk"),
        (SUICIDAL_RISK, "Suicidal Risk"),
    )
    dompcs = models.ManyToManyField(
        "PlayerOrNpc", blank=True, related_name="events", through="PCEventParticipation"
    )
    orgs = models.ManyToManyField(
        "Organization",
        blank=True,
        related_name="events",
        through="OrgEventParticipation",
    )
    name = models.CharField(max_length=255, db_index=True)
    desc = models.TextField(blank=True, null=True)
    location = models.ForeignKey(
        "objects.ObjectDB",
        blank=True,
        null=True,
        related_name="events_held",
        on_delete=models.SET_NULL,
    )
    date = models.DateTimeField(blank=True, null=True)
    celebration_tier = models.PositiveSmallIntegerField(
        choices=LARGESSE_CHOICES, default=NONE, blank=True
    )
    gm_event = models.BooleanField(default=False)
    public_event = models.BooleanField(default=True)
    finished = models.BooleanField(default=False)
    results = models.TextField(blank=True, null=True)
    room_desc = models.TextField(blank=True, null=True)
    # a beat with a blank desc will be used for connecting us to a Plot before the Event is finished
    beat = models.ForeignKey(
        "PlotUpdate",
        blank=True,
        null=True,
        related_name="events",
        on_delete=models.SET_NULL,
    )
    plotroom = models.ForeignKey(
        "PlotRoom",
        blank=True,
        null=True,
        related_name="events_held_here",
        on_delete=models.SET_NULL,
    )
    risk = models.PositiveSmallIntegerField(
        choices=RISK_CHOICES, default=NORMAL_RISK, blank=True
    )
    search_tags = models.ManyToManyField(
        "character.SearchTag", blank=True, related_name="events"
    )

    objects = RPEventQuerySet.as_manager()

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
        if (
            dom in self.gms.all()
            or dom in self.hosts.all()
            or dom in self.participants.all()
        ):
            return True
        if dom.current_orgs.filter(events=self).exists():
            return True

    def can_end_or_move(self, player):
        """Whether an in-progress event can be stopped or moved by a host"""
        dompc = player.Dominion
        return (
            self.can_admin(player)
            or dompc in self.hosts.all()
            or dompc in self.gms.all()
        )

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
        return self.dompcs.filter(
            event_participation__status__in=(
                PCEventParticipation.HOST,
                PCEventParticipation.MAIN_HOST,
            )
        )

    @property
    def participants(self):
        """Any guest who was invited/attended"""
        return self.dompcs.filter(
            event_participation__status=PCEventParticipation.GUEST
        )

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
        gms = self.gms.all()
        if gms:
            msg += "{wGMs:{n %s\n" % ", ".join(str(ob) for ob in gms)
        if not self.finished and not self.public_event:
            # prevent seeing names of invites once a private event has started
            if self.date > datetime.now():
                msg += "{wInvited:{n %s\n" % ", ".join(
                    str(ob) for ob in self.participants.all()
                )
        orgs = self.orgs.all()
        if orgs:
            msg += "{wOrgs:{n %s\n" % ", ".join(str(ob) for ob in orgs)
        msg += "{wLocation:{n %s\n" % self.location_name
        if not self.public_event:
            msg += "{wPrivate:{n Yes\n"
        if gms:
            msg += "|wRisk:|n %s\n" % self.get_risk_display()
        msg += "{wEvent Scale:{n %s\n" % self.get_celebration_tier_display()
        msg += "{wDate:{n %s\n" % self.date.strftime("%x %H:%M")
        msg += "{wDesc:{n\n%s\n" % self.desc
        msg += "{wEvent Page:{n %s\n" % get_full_url(self.get_absolute_url())
        comments = self.comments.filter(db_tags__db_key="white_journal").order_by(
            "-db_date_created"
        )
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

        return Journal.objects.filter(
            db_tags__db_data=self.tagdata, db_tags__db_category="event"
        )

    @property
    def main_host(self):
        """Returns who the main host was"""
        return self.dompcs.filter(
            event_participation__status=PCEventParticipation.MAIN_HOST
        ).first()

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
        return reverse("dominion:display_event", kwargs={"pk": self.id})

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
        status = (
            PCEventParticipation.MAIN_HOST if main_host else PCEventParticipation.HOST
        )
        self.invite_dompc(dompc, "status", status, send_inform)

    def change_host_to_guest(self, dompc):
        """Changes a host to a guest"""
        part = self.pc_event_participation.get(dompc=dompc)
        part.status = PCEventParticipation.GUEST
        part.save()

    def add_gm(self, dompc, send_inform=True):
        """Adds a gm for the event"""
        self.invite_dompc(dompc, "gm", True, send_inform)
        if not self.gm_event and (
            dompc.player.is_staff or dompc.player.check_permstring("builders")
        ):
            self.gm_event = True
            self.save()

    def untag_gm(self, dompc):
        """Removes GM tag from a participant"""
        part = self.pc_event_participation.get(dompc=dompc)
        part.gm = False
        part.save()

    def add_guest(self, dompc, send_inform=True):
        """Adds a guest to the event"""
        self.invite_dompc(dompc, "status", PCEventParticipation.GUEST, send_inform)

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
        guildies = Member.objects.filter(
            organization__in=self.orgs.all(), deguilded=False
        )
        all_dompcs = PlayerOrNpc.objects.filter(
            Q(id__in=self.dompcs.all()) | Q(memberships__in=guildies)
        )
        audience = Account.objects.filter(
            Dominion__in=all_dompcs, db_is_connected=True
        ).distinct()
        for ob in audience:
            ob.msg(msg)


class PCEventParticipation(SharedMemoryModel):
    """A PlayerOrNPC participating in an event"""

    MAIN_HOST, HOST, GUEST = range(3)
    STATUS_CHOICES = ((MAIN_HOST, "Main Host"), (HOST, "Host"), (GUEST, "Guest"))
    dompc = models.ForeignKey(
        "PlayerOrNpc", related_name="event_participation", on_delete=models.CASCADE
    )
    event = models.ForeignKey(
        "RPEvent", related_name="pc_event_participation", on_delete=models.CASCADE
    )
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

    org = models.ForeignKey(
        "Organization", related_name="event_participation", on_delete=models.CASCADE
    )
    event = models.ForeignKey(
        "RPEvent", related_name="org_event_participation", on_delete=models.CASCADE
    )
    social = models.PositiveSmallIntegerField(
        "Social Resources spent by the Org Sponsor", default=0
    )

    def invite(self):
        """Informs the org of their invitation"""
        self.org.inform(
            "Your organization has been invited to attend %s." % self.event,
            category="Event Invitations",
        )


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

    category = models.ForeignKey(
        "InfluenceCategory", db_index=True, on_delete=models.CASCADE
    )
    player = models.ForeignKey(
        "PlayerOrNpc", related_name="renown", db_index=True, on_delete=models.CASCADE
    )
    rating = models.IntegerField(blank=True, default=0)

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
            return self.rating / 200
        if self.rating <= 3000:
            return 5 + (self.rating - 1000) / 400
        if self.rating <= 6000:
            return 10 + (self.rating - 2000) / 800
        if self.rating <= 13000:
            return 15 + (self.rating - 4000) / 1600
        return 20


class SphereOfInfluence(SharedMemoryModel):
    """Influence categories for organization - npc groups they have some influence with"""

    category = models.ForeignKey(
        "InfluenceCategory", db_index=True, on_delete=models.CASCADE
    )
    org = models.ForeignKey(
        "Organization", related_name="spheres", db_index=True, on_delete=models.CASCADE
    )
    rating = models.IntegerField(blank=True, default=0)

    class Meta:
        verbose_name_plural = "Spheres of Influence"
        unique_together = ("category", "org")

    def __str__(self):
        return "%s's rating in %s: %s" % (self.org, self.category, self.rating)

    @property
    def level(self):
        """example idea for scaling"""
        if self.rating <= 150:
            return self.rating / 10
        if self.rating <= 350:
            return 15 + (self.rating - 150) / 20
        if self.rating <= 750:
            return 25 + (self.rating - 350) / 40
        if self.rating <= 1550:
            return 35 + (self.rating - 750) / 80
        return 45 + (self.rating - 1550) / 100


class TaskRequirement(SharedMemoryModel):
    """NPC groups that are required for tasks"""

    category = models.ForeignKey(
        "InfluenceCategory", db_index=True, on_delete=models.CASCADE
    )
    task = models.ForeignKey(
        "Task", related_name="requirements", db_index=True, on_delete=models.CASCADE
    )
    minimum_amount = models.PositiveSmallIntegerField(blank=True, default=0)

    def __str__(self):
        return "%s requirement: %s" % (self.task, self.category)


class SupportUsed(SharedMemoryModel):
    """Support given by a TaskSupporter for a specific task, using an npc group under 'sphere'"""

    week = models.PositiveSmallIntegerField(default=0, blank=True)
    supporter = models.ForeignKey(
        "TaskSupporter",
        related_name="allocation",
        db_index=True,
        on_delete=models.CASCADE,
    )
    sphere = models.ForeignKey(
        "SphereOfInfluence",
        related_name="usage",
        db_index=True,
        on_delete=models.CASCADE,
    )
    rating = models.PositiveSmallIntegerField(blank=True, default=0)

    def __str__(self):
        return "%s using %s of %s" % (self.supporter, self.rating, self.sphere)


class PlotRoom(SharedMemoryModel):
    """Model for creating templates that can be used repeatedly for temporary rooms for RP events"""

    name = models.CharField(blank=False, null=False, max_length=78, db_index=True)
    description = models.TextField(max_length=4096)
    creator = models.ForeignKey(
        "PlayerOrNpc",
        related_name="created_plot_rooms",
        blank=True,
        null=True,
        db_index=True,
        on_delete=models.CASCADE,
    )
    public = models.BooleanField(default=False)

    location = models.ForeignKey(
        "MapLocation",
        related_name="plot_rooms",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )
    domain = models.ForeignKey(
        "Domain",
        related_name="plot_rooms",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )
    wilderness = models.BooleanField(default=True)

    shardhaven_type = models.ForeignKey(
        "exploration.ShardhavenType",
        related_name="tilesets",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )

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
            result += (
                region_color
                + " - "
                + self.get_detailed_region_name()
                + " - "
                + self.name
            )
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
        room = create.create_object(
            typeclass="typeclasses.rooms.TempRoom", key=self.ansi_name()
        )
        room.db.raw_desc = self.description
        room.db.desc = self.description

        if arx_exit:
            from typeclasses.rooms import ArxRoom

            try:
                city_center = ArxRoom.objects.get(id=13)
                create.create_object(
                    settings.BASE_EXIT_TYPECLASS,
                    key="Back to Arx <Arx>",
                    location=room,
                    aliases=["arx", "back to arx", "out"],
                    destination=city_center,
                )
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
        (TYPE_UNKNOWN, "Unknown"),
        (TYPE_FAITH, "Faith"),
        (TYPE_CULTURAL, "Cultural"),
        (TYPE_HISTORICAL, "Historical"),
    )

    name = models.CharField(blank=False, null=False, max_length=32, db_index=True)
    description = models.TextField(max_length=2048)
    location = models.ForeignKey(
        "MapLocation",
        related_name="landmarks",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )
    landmark_type = models.PositiveSmallIntegerField(
        choices=CHOICES_TYPE, default=TYPE_UNKNOWN
    )

    def __str__(self):
        return "<Landmark #%d: %s>" % (self.id, self.name)
