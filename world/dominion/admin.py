"""
Admin for Dominion
"""
from django.contrib import admin
from django.db.models import Q
from django.shortcuts import reverse
from django.utils.html import escape
from django.utils.safestring import mark_safe

from .models import (
    PlayerOrNpc,
    Organization,
    Agent,
    AgentOb,
    MapLocation,
    AssetOwner,
    Region,
    Land,
    WorkSetting,
    PraiseOrCondemn,
    Member,
    Task,
    RPEvent,
    AccountTransaction,
    AssignedTask,
    OrgRelationship,
    Reputation,
    TaskSupporter,
    InfluenceCategory,
    Renown,
    SphereOfInfluence,
    TaskRequirement,
    ClueForOrg,
    PlotRoom,
    Landmark,
    PrestigeTier,
    PrestigeCategory,
    PrestigeAdjustment,
    Honorific,
    Propriety,
    PCEventParticipation,
    OrgEventParticipation,
    Fealty,
)
from world.crafting.models import OwnedMaterial, CraftingMaterialType

from world.dominion.plots.models import (
    Plot,
    PlotAction,
    PlotUpdate,
    ActionOOCQuestion,
    PCPlotInvolvement,
    OrgPlotInvolvement,
    PlotActionAssistant,
    ActionRequirement,
)

from world.dominion.domain.models import (
    Army,
    Orders,
    MilitaryUnit,
    OrgUnitModifiers,
    Domain,
    Castle,
    Ruler,
    Minister,
)

from web.help_topics.templatetags.app_filters import mush_to_html
from world.exploration.models import Shardhaven, ShardhavenType


class DomAdmin(admin.ModelAdmin):
    """Base admin class"""

    list_display = ("id", "name")
    list_select_related = True
    save_as = True

    @staticmethod
    def name(obj):
        """For displaying name along with ID as a default/fallback"""
        return str(obj)


class ReputationInline(admin.TabularInline):
    """Character reputation with orgs admin"""

    model = Reputation
    raw_id_fields = ("player", "organization")
    extra = 0


class PCAdmin(DomAdmin):
    """Admin for main model of dominion, PlayerOrNpc, an extension of AUTH_USER_MODEL"""

    search_fields = ["=player__username", "npc_name"]
    filter_horizontal = ["parents", "spouses"]
    raw_id_fields = ("player", "patron")
    list_select_related = ("player",)
    inlines = (ReputationInline,)


class MemberInline(admin.StackedInline):
    """Inline for displaying Org members"""

    model = Member
    extra = 0
    raw_id_fields = ("commanding_officer", "player", "organization")
    exclude = (
        "object",
        "pc_exists",
        "salary",
        "commanding_officer",
        "public_notes",
        "officer_notes",
    )
    readonly_fields = (
        "work_this_week",
        "work_total",
        "investment_this_week",
        "investment_total",
        "has_seen_motd",
    )
    show_change_link = True


class MemberAdmin(DomAdmin):
    raw_id_fields = ("commanding_officer", "player", "organization", "object")


class WorkSettingInline(admin.StackedInline):
    """Inline for displaying WorkSettings for an Org"""

    model = WorkSetting
    extra = 0


class ClueForOrgInline(admin.TabularInline):
    """Inline for display clues orgs know"""

    model = ClueForOrg
    extra = 0
    readonly_fields = ("org", "revealed_by")
    raw_id_fields = ("clue", "org", "revealed_by")


class OrgUnitInline(admin.TabularInline):
    """Inline for display Unit modifiers that orgs have, creating special units unique to them"""

    model = OrgUnitModifiers
    extra = 0
    raw_id_fields = ("org",)


class OrgListFilter(admin.SimpleListFilter):
    """List filter for separating PC and NPC orgs"""

    title = "PC or NPC"
    parameter_name = "played"

    def lookups(self, request, model_admin):
        """Defines lookup display for list filter"""
        return (
            ("pc", "Has Players"),
            ("npc", "NPCs Only"),
        )

    def queryset(self, request, queryset):
        """Specifies queryset we get based on selected options"""
        if self.value() == "pc":
            return queryset.filter(members__player__player__isnull=False).distinct()
        if self.value() == "npc":
            return queryset.filter(members__player__player__isnull=True).distinct()


class OrgAdmin(DomAdmin):
    """Admin for organizations"""

    list_display = ("id", "name", "category", "fealty", "org_board", "org_channel")
    ordering = ["name"]
    search_fields = [
        "name",
        "category",
        "=members__player__player__username",
        "fealty__name",
    ]
    list_filter = (OrgListFilter,)
    filter_horizontal = ("theories",)
    # omit unused fields for now
    exclude = (
        "motd",
        "special_modifiers",
        "morale",
        "allow_work",
        "base_support_value",
        "member_support_multiplier",
    )
    inlines = [MemberInline, ClueForOrgInline, OrgUnitInline, WorkSettingInline]
    raw_id_fields = ("org_channel", "org_board")
    readonly_fields = ("economic_modifier", "social_modifier", "military_modifier")


class Supporters(admin.TabularInline):
    """Inline for Task Supporters, players helping out on Tasks"""

    model = TaskSupporter
    extra = 0
    readonly_fields = (
        "rating",
        "week",
    )


class AssignedTaskAdmin(DomAdmin):
    """Admin for display tasks players are working on"""

    list_display = ("member", "org", "task", "finished", "week", "support_total")
    search_fields = ("member__player__player__username", "task__name")
    inlines = [Supporters]

    @staticmethod
    def support_total(obj):
        """Total amount of support they've accumulated as an integer"""
        return obj.total

    @staticmethod
    def org(obj):
        """Displays the organization this task is for"""
        return obj.member.organization.name

    list_filter = ("finished",)
    list_select_related = ("member__player__player", "member__organization", "task")


class MinisterInline(admin.TabularInline):
    """Inline for ministers for a ruler"""

    model = Minister
    raw_id_fields = ("player", "ruler")
    extra = 0


class RulerListFilter(OrgListFilter):
    """List filter for display PC or NPC rulers from orgs"""

    def queryset(self, request, queryset):
        """Modify OrgListFilter based on query"""
        if self.value() == "pc":
            return queryset.filter(
                house__organization_owner__members__player__player__isnull=False
            ).distinct()
        if self.value() == "npc":
            return queryset.filter(
                house__organization_owner__members__player__player__isnull=True
            ).distinct()


class RulerAdmin(DomAdmin):
    """Admin for Ruler model, which runs domains"""

    list_display = ("id", "house", "liege", "castellan")
    ordering = ["house"]
    search_fields = ["house__organization_owner__name"]
    raw_id_fields = ("castellan", "house", "liege")
    inlines = (MinisterInline,)
    list_filter = (RulerListFilter,)


class CastleInline(admin.TabularInline):
    """Inline for castles in domains"""

    model = Castle
    extra = 0


class DomainListFilter(OrgListFilter):
    """List filter for separating PC and NPC domains"""

    def queryset(self, request, queryset):
        """modifies orglistfilter query for domains"""
        if self.value() == "pc":
            return queryset.filter(
                ruler__house__organization_owner__members__player__player__isnull=False
            ).distinct()
        if self.value() == "npc":
            return queryset.filter(
                ruler__house__organization_owner__members__player__player__isnull=True
            ).distinct()


class DomainAdmin(DomAdmin):
    """Admin for Domains, player/org offscreen holdings"""

    list_display = ("id", "name", "ruler", "location")
    ordering = ["name"]
    search_fields = ["name"]
    raw_id_fields = ("ruler", "location")
    list_filter = (DomainListFilter,)
    inlines = (CastleInline,)


class PCEventParticipantInline(admin.TabularInline):
    """PlayerOrNpcs in an RPEvent"""

    model = PCEventParticipation
    extra = 0
    raw_id_fields = ("dompc",)


class OrgEventParticipantInline(admin.TabularInline):
    """Orgs in an RPEvent"""

    model = OrgEventParticipation
    extra = 0
    raw_id_fields = ("org",)


class EventAdmin(DomAdmin):
    """Admin for RP Events/PRPs/GM Events"""

    list_display = ("id", "name", "date")
    search_fields = ["name", "=dompcs__player__username", "orgs__name", "=id"]
    ordering = ["date"]
    raw_id_fields = ("location", "beat", "plotroom")
    filter_horizontal = ("search_tags",)
    inlines = (PCEventParticipantInline, OrgEventParticipantInline)


class SendTransactionInline(admin.TabularInline):
    """Inline for transactions we're sending"""

    model = AccountTransaction
    fk_name = "sender"
    extra = 0
    raw_id_fields = ("receiver",)


class ReceiveTransactionInline(admin.TabularInline):
    """Inline for money we're receiving"""

    model = AccountTransaction
    fk_name = "receiver"
    extra = 0
    raw_id_fields = ("sender",)


class MaterialsInline(admin.TabularInline):
    """Inline for amounts of materials an assetowner has"""

    model = OwnedMaterial
    extra = 0

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Orders the material type selection"""
        if db_field.name == "type":
            kwargs["queryset"] = CraftingMaterialType.objects.order_by("name")
        return super(MaterialsInline, self).formfield_for_foreignkey(
            db_field, request, **kwargs
        )


class AssetAdmin(DomAdmin):
    """Admin for the assets of a player or organization"""

    list_display = (
        "id",
        "ownername",
        "vault",
        "prestige",
        "economic",
        "military",
        "social",
    )
    search_fields = [
        "player__npc_name",
        "=player__player__username",
        "organization_owner__name",
    ]
    inlines = [SendTransactionInline, ReceiveTransactionInline, MaterialsInline]
    raw_id_fields = ("player", "organization_owner")

    @staticmethod
    def ownername(obj):
        """Gets the name of the entity we hold assets for"""
        return obj.owner


class AgentObInline(admin.TabularInline):
    """Inline for who agents are assigned to"""

    model = AgentOb
    raw_id_fields = ("dbobj", "agent_class")
    readonly_fields = ("guarding",)
    extra = 0

    @staticmethod
    def guarding(obj):
        """Displays the player their dbobj Character instance is assigned to, if anyone"""
        if not obj.dbobj:
            return None
        return obj.dbobj.item_data.guarding


class TaskRequirementsInline(admin.TabularInline):
    """Inline that specifies requirements for a task"""

    model = TaskRequirement
    extra = 0
    raw_id_fields = ("task",)


class TaskAdmin(DomAdmin):
    """Admin for Tasks, abstracted things players do for money which are awful and need to be revamped"""

    list_display = ("id", "name", "orgs", "category", "active", "difficulty")
    search_fields = ("name", "org__name")
    inlines = [TaskRequirementsInline]

    @staticmethod
    def orgs(obj):
        """names of organizations involved"""
        return ", ".join([p.name for p in obj.org.all()])

    filter_horizontal = ["org"]

    def formfield_for_manytomany(self, db_field, request=None, **kwargs):
        """Limits queryset to orgs with players"""
        if db_field.name == "org":
            kwargs["queryset"] = (
                Organization.objects.filter(members__player__player__isnull=False)
                .distinct()
                .order_by("name")
            )
        return super(TaskAdmin, self).formfield_for_manytomany(
            db_field, request, **kwargs
        )


class PlotUpdateTagMixin(object):
    readonly_fields = (
        "tagged_actions",
        "tagged_story_emits",
        "tagged_events",
        "tagged_flashbacks",
    )

    @mark_safe
    def tagged_actions(self, obj):
        return "<br>".join(
            '<a href="%s">%s</a>'
            % (
                reverse("admin:dominion_plotaction_change", args=[action.id]),
                escape(str(action)),
            )
            for action in obj.actions.all()
        )

    tagged_actions.allow_tags = True

    @mark_safe
    def tagged_story_emits(self, obj):
        return "<br>".join(
            '<a href="%s">%s</a>'
            % (
                reverse("admin:character_storyemit_change", args=[emit.id]),
                escape(emit.id),
            )
            for emit in obj.emits.all()
        )

    tagged_story_emits.allow_tags = True

    @mark_safe
    def tagged_events(self, obj):
        return "<br>".join(
            '<a href="%s">%s</a>'
            % (reverse("admin:dominion_rpevent_change", args=[ev.id]), escape(ev.name))
            for ev in obj.events.all()
        )

    tagged_events.allow_tags = True

    @mark_safe
    def tagged_flashbacks(self, obj):
        return "<br>".join(
            '<a href="%s">%s</a>'
            % (
                reverse("admin:character_flashback_change", args=[fb.id]),
                escape(fb.title),
            )
            for fb in obj.flashbacks.all()
        )

    tagged_flashbacks.allow_tags = True


class PlotUpdateInline(PlotUpdateTagMixin, admin.StackedInline):
    """Inline showing plot updates"""

    model = PlotUpdate
    extra = 0
    raw_id_fields = ("episode",)
    filter_horizontal = ("search_tags",)
    classes = ["collapse"]
    show_change_link = True


class PlotOrgInvolvementInline(admin.StackedInline):
    """Inline for Orgs involved in plots"""

    model = OrgPlotInvolvement
    extra = 0
    raw_id_fields = ("org",)
    classes = ["collapse"]


class PCPlotInvolvementInline(admin.StackedInline):
    """Inline for PC involvement in plots"""

    model = PCPlotInvolvement
    extra = 0
    raw_id_fields = ("dompc", "recruited_by")
    classes = ["collapse"]


class PlotRecruiterListFilter(OrgListFilter):
    """List filter for showing Plots that are recruiting"""

    title = "Currently Recruiting"
    parameter_name = "recruiting"

    def lookups(self, request, model_admin):
        """Defines lookup display for list filter"""
        return (("recruiting", "Has Recruiters"),)

    def queryset(self, request, queryset):
        """modifies orglistfilter query for domains"""
        if self.value() == "recruiting":
            return queryset.filter(
                Q(dompc_involvement__activity_status=PCPlotInvolvement.ACTIVE)
                & Q(dompc_involvement__admin_status__gte=PCPlotInvolvement.RECRUITER)
                & ~Q(dompc_involvement__recruiter_story="")
            ).distinct()


class ActionRequirementInline(admin.TabularInline):
    model = ActionRequirement
    extra = 0
    raw_id_fields = (
        "item",
        "spell",
        "rfr",
        "clue",
        "revelation",
        "skill_node",
        "fulfilled_by",
    )


class PlotAdmin(DomAdmin):
    """Admin for Crises, macro-level events affecting the game/metaplot"""

    list_display = ("id", "name", "desc", "end_date", "parent_plot")
    filter_horizontal = ["orgs", "search_tags"]
    raw_id_fields = ("required_clue", "parent_plot")
    search_fields = ("name", "desc", "=dompcs__player__username", "=id")
    list_filter = ("resolved", "usage", PlotRecruiterListFilter)
    inlines = (PlotUpdateInline, PlotOrgInvolvementInline, PCPlotInvolvementInline)


class PlotUpdateAdmin(PlotUpdateTagMixin, DomAdmin):
    """Admin for Plot Updates"""

    list_display = (
        "id",
        "plot",
        "desc",
        "date",
    )
    filter_horizontal = ("search_tags",)
    raw_id_fields = ("plot",)


class PlotActionAssistantInline(admin.StackedInline):
    """Inline of someone helping out on an Action"""

    model = PlotActionAssistant
    extra = 0
    raw_id_fields = (
        "plot_action",
        "dompc",
    )
    readonly_fields = ("ooc_intent",)
    fieldsets = [
        (None, {"fields": [("dompc", "topic")]}),
        (
            "Status",
            {
                "fields": [("editable", "attending", "traitor", "free_action")],
                "classes": ["collapse"],
            },
        ),
        (
            "Story",
            {
                "fields": ["actions", "secret_actions", "ooc_intent"],
                "classes": ["collapse"],
            },
        ),
        (
            "Roll",
            {
                "fields": [("stat_used", "skill_used")],
                "description": "Stuff for roll and result",
                "classes": ["collapse"],
            },
        ),
        (
            "Resources",
            {
                "fields": [
                    ("military", "silver"),
                    ("social", "action_points"),
                    "economic",
                ],
                "classes": ["collapse"],
            },
        ),
    ]


class CrisisArmyOrdersInline(admin.TabularInline):
    """Inline of army orders for an action"""

    model = Orders
    show_change_link = True
    extra = 0
    raw_id_fields = ("army", "target_land", "assisting", "action_assist")
    exclude = (
        "target_domain",
        "target_character",
        "type",
        "week",
    )
    readonly_fields = ("troops_sent",)
    fieldsets = [
        ("Troops", {"fields": ["army", "troops_sent"]}),
        ("Costs", {"fields": ["coin_cost", "food_cost"]}),
    ]


class ActionOOCQuestionInline(admin.StackedInline):
    """Inline of questions players are asking re: their action"""

    model = ActionOOCQuestion
    extra = 0
    readonly_fields = ("text_of_answers", "action_assist")

    def get_queryset(self, request):
        """Limit queryset to things which aren't their OOC intentions - additional questions only"""
        qs = super(ActionOOCQuestionInline, self).get_queryset(request)
        return qs.filter(is_intent=False)

    fieldsets = [(None, {"fields": [("action", "action_assist"), "text_of_answers"]})]


class PlotActionAdmin(DomAdmin):
    """Admin for @actions that players are taking, one of their primary ways of participating in the game's plot."""

    list_display = ("id", "dompc", "plot", "player_action", "week", "status")
    search_fields = ("plot__name", "=dompc__player__username", "=id")
    list_filter = ("plot", "status")
    raw_id_fields = ("dompc", "gemit", "gm", "plot", "beat")
    readonly_fields = ("ooc_intent",)
    filter_horizontal = ("search_tags",)
    fieldsets = [
        (None, {"fields": [("dompc", "topic"), ("search_tags",)]}),
        (
            "Status",
            {
                "fields": [
                    ("attending", "traitor", "prefer_offscreen"),
                    ("status", "public", "editable", "free_action"),
                    ("plot", "beat", "gemit"),
                    ("week", "date_submitted"),
                ],
                "classes": ["collapse"],
                "description": "Current ooc status of the action",
            },
        ),
        (
            "Story",
            {
                "fields": [
                    "category",
                    "actions",
                    "secret_actions",
                    "story",
                    "secret_story",
                    "gm_notes",
                    "ooc_intent",
                ],
                "description": "The player's story, and GM response to it.",
                "classes": ["collapse"],
            },
        ),
        (
            "Roll",
            {
                "fields": [
                    ("stat_used", "skill_used", "target_rank"),
                    (
                        "max_points_silver",
                        "max_points_social",
                        "max_points_economic",
                        "max_points_military",
                        "max_points_ap",
                        "max_points_assists",
                    ),
                    (
                        "silver_divisor",
                        "social_divisor",
                        "economic_divisor",
                        "military_divisor",
                        "ap_divisor",
                        "assist_divisor",
                        "additional_modifiers",
                    ),
                    "roll_result",
                ],
                "description": "Stuff for roll and result",
                "classes": ["collapse"],
            },
        ),
        (
            "Resources",
            {
                "fields": [
                    ("military", "silver"),
                    ("social", "action_points"),
                    "economic",
                ],
                "classes": ["collapse"],
            },
        ),
    ]
    inlines = (
        PlotActionAssistantInline,
        CrisisArmyOrdersInline,
        ActionOOCQuestionInline,
        ActionRequirementInline,
    )

    @staticmethod
    def player_action(obj):
        """Reformats what they've written without ansi markup"""
        return mush_to_html(obj.actions)


class OrgRelationshipAdmin(DomAdmin):
    """Admin for showing relationships orgs have with one another. Not really used at present, but should be."""

    filter_horizontal = ["orgs"]


class ReputationAdmin(DomAdmin):
    """Admin for reputation players have with organizations."""

    list_display = ("player", "organization", "affection", "respect")
    raw_id_fields = ("player", "organization")
    search_fields = ("=player__player__username", "organization__name")


class SpheresInline(admin.TabularInline):
    """Showing npc groups that orgs have influence over"""

    model = SphereOfInfluence
    extra = 0
    raw_id_fields = ("org",)

    def formfield_for_foreignkey(self, db_field, request=None, **kwargs):
        """Limit queryset to orgs that have players"""
        if db_field.name == "org":
            kwargs["queryset"] = (
                Organization.objects.filter(members__player__player__isnull=False)
                .distinct()
                .order_by("name")
            )
        return super(SpheresInline, self).formfield_for_foreignkey(
            db_field, request, **kwargs
        )


class RenownInline(admin.TabularInline):
    """Inline showing renown, a player's influence with npc groups"""

    model = Renown
    extra = 0


class InfluenceCategoryAdmin(DomAdmin):
    """Showing the different npc groups organizations/players can have influence with, and that tasks use"""

    list_display = ("name", "organizations", "task_requirements")
    ordering = ["name"]
    search_fields = ["name", "orgs__name", "tasks__name"]

    @staticmethod
    def organizations(obj):
        """Display name of orgs"""
        return ", ".join([p.name for p in obj.orgs.all().order_by("name")])

    @staticmethod
    def task_requirements(obj):
        """Display name of tasks"""
        return ", ".join([p.name for p in obj.tasks.all().order_by("name")])

    inlines = [SpheresInline, TaskRequirementsInline]


class AgentAdmin(DomAdmin):
    """Admin for agents, npcs owned by players or orgs"""

    list_display = ("id", "name", "quantity", "quality", "owner")
    raw_id_fields = ("owner",)
    search_fields = (
        "name",
        "=owner__player__player__username",
        "owner__organization_owner__name",
    )
    inlines = [AgentObInline]


class MilitaryUnitInline(admin.TabularInline):
    """Inline for showing military units in an army"""

    model = MilitaryUnit
    extra = 0
    raw_id_fields = ("origin", "commander", "orders")


class ArmyListFilter(OrgListFilter):
    """List filter for display armies owned by pcs or npcs"""

    def queryset(self, request, queryset):
        """Modifies query of OrgListFilter for armies"""
        if self.value() == "pc":
            return queryset.filter(
                owner__organization_owner__members__player__player__isnull=False
            ).distinct()
        if self.value() == "npc":
            return queryset.filter(
                owner__organization_owner__members__player__player__isnull=True
            ).distinct()


class ArmyAdmin(DomAdmin):
    """Admin for armies owned by organizations or players"""

    list_display = ("id", "name", "owner", "domain")
    raw_id_fields = (
        "owner",
        "domain",
        "land",
        "castle",
        "general",
        "temp_owner",
        "group",
    )
    search_fields = (
        "name",
        "domain__name",
        "=owner__player__player__username",
        "owner__organization_owner__name",
        "=temp_owner__player__player__username",
        "temp_owner__organization_owner__name",
        "id",
    )
    inlines = (MilitaryUnitInline,)
    list_filter = (ArmyListFilter,)


class OrdersAdmin(DomAdmin):
    """Admin for orders of armies"""

    list_display = ("id", "army", "type", "action", "complete")
    raw_id_fields = (
        "army",
        "action",
        "action_assist",
        "assisting",
        "target_land",
        "target_domain",
        "target_character",
    )
    list_filter = ("complete",)


class RegionFilter(admin.SimpleListFilter):
    """List filter for plot rooms, letting us see what regions they're in"""

    title = "Region"
    parameter_name = "region"

    def lookups(self, request, model_admin):
        """Get lookup names derived from Regions"""
        regions = Region.objects.all().order_by("name")
        result = []
        for region in regions:
            result.append((region.id, region.name))
        return result

    def queryset(self, request, queryset):
        """Filter queryset by Region selection"""
        if not self.value():
            return queryset

        try:
            region_id = int(self.value())
            region = Region.objects.get(id=region_id)
        except (ValueError, Region.DoesNotExist):
            region = None

        if not region:
            return queryset

        return self.finish_queryset_by_region(queryset, region)

    # noinspection PyMethodMayBeStatic
    def finish_queryset_by_region(self, queryset, region):
        """Finishes modifying the queryset. Overridden in subclasses"""
        return queryset.filter(location__land__region=region)


class ShardhavenTypeFilter(admin.SimpleListFilter):
    """List filter for plot rooms, letting us see what regions they're in"""

    title = "Shardhaven Type"
    parameter_name = "shardhaven_type"

    def lookups(self, request, model_admin):
        """Get lookup names derived from Regions"""
        haven_types = ShardhavenType.objects.all().order_by("name")
        result = []
        for haven_type in haven_types:
            result.append((haven_type.id, haven_type.name))
        return result

    def queryset(self, request, queryset):
        """Filter queryset by Region selection"""
        if not self.value():
            return queryset

        try:
            haven_id = int(self.value())
            haven = ShardhavenType.objects.get(id=haven_id)
        except (ValueError, ShardhavenType.DoesNotExist):
            haven = None

        if not haven:
            return queryset

        return self.finish_queryset_by_haventype(queryset, haven)

    # noinspection PyMethodMayBeStatic
    def finish_queryset_by_haventype(self, queryset, haven_type):
        """Finishes modifying the queryset. Overridden in subclasses"""
        return queryset.filter(shardhaven_type=haven_type)


class PlotRoomAdmin(DomAdmin):
    """Admin for plotrooms, templates that can be used repeatedly for temprooms for events"""

    list_display = ("id", "domain", "location", "name", "public")
    search_files = ("name", "description")
    raw_id_fields = ("creator", "domain")
    list_filter = ("public", RegionFilter, ShardhavenTypeFilter)


class DomainInline(admin.TabularInline):
    """inline for domains"""

    model = Domain
    extra = 0
    raw_id_fields = ("ruler",)


class LandmarkInline(admin.TabularInline):
    """inline for landmarks"""

    model = Landmark
    extra = 0


class ShardhavenInline(admin.TabularInline):
    """inline for Shardhavens"""

    model = Shardhaven
    extra = 0


@admin.register(MapLocation)
class MapLocationAdmin(DomAdmin):
    """Admin for map locations"""

    list_display = ("id", "name", "land", "x_coord", "y_coord", "domains_here")
    search_fields = ("name", "domains__name", "shardhavens__name", "landmarks__name")
    inlines = (LandmarkInline, DomainInline, ShardhavenInline)
    raw_id_fields = ("land",)

    @staticmethod
    def domains_here(obj):
        """Gets domain names for this MapLocation"""
        return ", ".join(ob.name for ob in obj.domains.all())


class LandmarkAdmin(DomAdmin):
    """Admin for Landmarks found in the world"""

    list_display = ("id", "name", "landmark_type", "location")
    search_fields = ("name", "description")
    list_filter = (
        "landmark_type",
        RegionFilter,
    )


class MapLocationInline(admin.TabularInline):
    """Inline for Map Locations"""

    model = MapLocation
    extra = 0
    show_change_link = True


class LandAdmin(DomAdmin):
    """Admin for Land Squares that make up the global map"""

    list_display = ("id", "name", "terrain", "location_names")
    search_fields = ("name", "region__name", "locations__name")
    list_filter = ("region", "landlocked")
    inlines = (MapLocationInline,)

    @staticmethod
    def location_names(obj):
        """Names of locations in this space"""
        return ", ".join(str(ob) for ob in obj.locations.all())


class WorkSettingAdmin(DomAdmin):
    """Non-inline admin for WorkSettings"""

    list_display = ("organization", "resource", "stat", "skill", "message")
    search_fields = ("organization__name", "stat", "skill")


class PraiseAdmin(DomAdmin):
    """Admin for PraiseOrCondemn"""

    list_display = ("praiser", "target", "message", "week", "value")
    search_fields = ("=praiser__player__username", "=target__player__username")


class ProprietyAdmin(DomAdmin):
    """Admin for Propriety"""

    list_display = ("name", "percentage")
    search_fields = (
        "name",
        "owners__organization_owner__name",
        "=owners__player__player__username",
    )
    filter_horizontal = ("owners",)


class HonorificAdmin(DomAdmin):
    """Admin for Honorifics"""

    list_display = ("owner", "title", "amount")
    search_fields = (
        "=owner__player__player__username",
        "owner__organization_owner__name",
        "title",
    )
    raw_id_fields = ("owner",)


class FealtyAdmin(DomAdmin):
    """Admin for Fealties"""

    list_display = ("name", "org_names")
    search_fields = ("name", "orgs__name")

    @staticmethod
    def org_names(obj):
        """Get names of organizations for this fealty"""
        return ", ".join(str(ob) for ob in obj.orgs.all())


class PrestigeCategoryAdmin(DomAdmin):
    """Admin for PrestigeCategory"""

    list_display = ("name", "male_noun", "female_noun")
    search_fields = ("name", "male_noun", "female_noun")


class PrestigeAdjustmentAdmin(DomAdmin):
    """Admin for Prestige Adjustments"""

    list_display = (
        "id",
        "asset_owner",
        "category",
        "adjusted_on",
        "adjusted_by",
        "adjustment_type",
    )
    search_fields = (
        "=asset_owner__player__player__username",
        "asset_owner__organization_owner__name",
    )
    raw_id_fields = ("asset_owner",)
    list_filter = ("category", "adjustment_type")
    readonly_fields = ("adjusted_by", "effective_value")


class PrestigeTierAdmin(DomAdmin):
    """Admin for Prestige Tiers"""

    list_display = ("rank_name", "minimum_prestige")
    search_fields = ("rank_name",)


class ClueForOrgAdmin(admin.ModelAdmin):
    """Admin for org clues."""

    list_display = ("clue", "org", "revealed_by")
    search_fields = ("clue__name", "org__name")
    raw_id_fields = ("clue", "org", "revealed_by")


# Register your models here.
admin.site.register(ClueForOrg, ClueForOrgAdmin)
admin.site.register(PlayerOrNpc, PCAdmin)
admin.site.register(Organization, OrgAdmin)
admin.site.register(Domain, DomainAdmin)
admin.site.register(Agent, AgentAdmin)
admin.site.register(AssetOwner, AssetAdmin)
admin.site.register(Army, ArmyAdmin)
admin.site.register(Orders, OrdersAdmin)
admin.site.register(Region, DomAdmin)
admin.site.register(Land, LandAdmin)
admin.site.register(Task, TaskAdmin)
admin.site.register(Ruler, RulerAdmin)
admin.site.register(RPEvent, EventAdmin)
admin.site.register(Plot, PlotAdmin)
admin.site.register(PlotUpdate, PlotUpdateAdmin)
admin.site.register(PlotAction, PlotActionAdmin)
admin.site.register(OrgRelationship, OrgRelationshipAdmin)
admin.site.register(Reputation, ReputationAdmin)
admin.site.register(AssignedTask, AssignedTaskAdmin)
admin.site.register(InfluenceCategory, InfluenceCategoryAdmin)
admin.site.register(PlotRoom, PlotRoomAdmin)
admin.site.register(Landmark, LandmarkAdmin)
admin.site.register(WorkSetting, WorkSettingAdmin)
admin.site.register(PraiseOrCondemn, PraiseAdmin)
admin.site.register(Honorific, HonorificAdmin)
admin.site.register(Propriety, ProprietyAdmin)
admin.site.register(Fealty, FealtyAdmin)
admin.site.register(PrestigeAdjustment, PrestigeAdjustmentAdmin)
admin.site.register(PrestigeCategory, PrestigeCategoryAdmin)
admin.site.register(PrestigeTier, PrestigeTierAdmin)
admin.site.register(Member, MemberAdmin)
