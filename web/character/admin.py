"""
Admin models for Character app
"""
from django.contrib import admin
from django.forms import ModelForm
from django.utils.safestring import mark_safe
from .models import (
    Roster,
    RosterEntry,
    Photo,
    SearchTag,
    FlashbackPost,
    Flashback,
    FlashbackInvolvement,
    Story,
    Chapter,
    Episode,
    StoryEmit,
    Milestone,
    FirstContact,
    CluePlotInvolvement,
    RevelationPlotInvolvement,
    PlayerAccount,
    AccountHistory,
    InvestigationAssistant,
    Mystery,
    Revelation,
    Clue,
    Investigation,
    RevelationDiscovery,
    ClueDiscovery,
    ClueForRevelation,
    Theory,
    TheoryPermissions,
    PlayerInfoEntry,
    Goal,
    GoalUpdate,
    PlayerPosition,
)
from django.db.models import (
    F,
    Subquery,
    OuterRef,
    IntegerField,
    ExpressionWrapper,
    Q,
    Sum,
)
from django.shortcuts import reverse
from django.utils.html import escape


class BaseCharAdmin(admin.ModelAdmin):
    """Base admin settings"""

    list_select_related = True
    save_as = True


class NoDeleteAdmin(BaseCharAdmin):
    """Prevent deletion in Base Admin for some critical models"""

    def get_actions(self, request):
        """Disable delete"""
        actions = super(BaseCharAdmin, self).get_actions(request)
        try:
            del actions["delete_selected"]
        except KeyError:
            pass
        return actions

    def has_delete_permission(self, request, obj=None):
        """Disable delete"""
        return False


class EntryForm(ModelForm):
    """Form for RosterEntry admin. Used to limit profile picture queryset"""

    def __init__(self, *args, **kwargs):
        super(EntryForm, self).__init__(*args, **kwargs)
        self.fields["profile_picture"].queryset = Photo.objects.filter(
            owner=self.instance.character
        )


class PhotoAdmin(BaseCharAdmin):
    """Admin for Cloudinary photos"""

    list_display = ("id", "title", "owner", "alt_text")
    raw_id_fields = ("owner",)


class AccountHistoryInline(admin.TabularInline):
    """Inline for AccountHistory"""

    model = AccountHistory
    can_delete = False
    extra = 0
    raw_id_fields = ("account", "entry")


class AccountEntryInline(admin.TabularInline):
    """Inline for AccountHistory"""

    model = PlayerInfoEntry
    raw_id_fields = ("account", "author")
    extra = 0


class AccountAdmin(BaseCharAdmin):
    """Admin for AccountHistory"""

    list_display = ("id", "email", "player_characters")
    search_fields = ("email", "characters__character__db_key")
    inlines = (AccountHistoryInline, AccountEntryInline)

    @staticmethod
    def player_characters(obj):
        """List names of our characters for list display"""
        return ", ".join([str(ob) for ob in obj.characters.all()])


class EmitInline(admin.TabularInline):
    """Inline admin of Gemits"""

    list_display = ("id",)
    model = StoryEmit
    extra = 0
    raw_id_fields = ("sender", "beat", "episode", "chapter", "orgs", "search_tags")


class ChapterAdmin(BaseCharAdmin):
    """Admin for chapters"""

    list_display = ("id", "name", "story", "synopsis", "start_date", "end_date")
    inlines = [EmitInline]


class EpisodeAdmin(BaseCharAdmin):
    """Admin for episodes"""

    list_display = ("id", "name", "chapter", "synopsis", "date")
    inlines = [EmitInline]


class MysteryAdmin(BaseCharAdmin):
    """Admin of mystery"""

    list_display = ("id", "name", "category", "used_for")
    search_fields = ("name", "category", "revelations__name")
    list_filter = ("category",)
    readonly_fields = ("used_for",)

    @mark_safe
    def used_for(self, obj):
        return ", ".join(
            '<a href="%s">%s</a>'
            % (
                reverse("admin:character_revelation_change", args=[rev.id]),
                escape(rev.name),
            )
            for rev in obj.revelations.all()
        )

    used_for.allow_tags = True


class ClueForRevInline(admin.TabularInline):
    """Inline of clues required for a revelation"""

    model = ClueForRevelation
    extra = 0
    raw_id_fields = (
        "clue",
        "revelation",
    )


class RevDiscoInline(admin.TabularInline):
    """Inline of revelation discoveries"""

    model = RevelationDiscovery
    extra = 0
    raw_id_fields = (
        "character",
        "investigation",
        "revealed_by",
        "revelation",
        "milestone",
    )
    classes = ["collapse"]


class RevPlotInvolvementInline(admin.TabularInline):
    """Inline for RevelationPlotInvolvement"""

    model = RevelationPlotInvolvement
    extra = 0
    raw_id_fields = ("revelation", "plot")
    classes = ["collapse"]


class RevelationListFilter(admin.SimpleListFilter):
    """List filter for showing whether an investigation will finish this week or not"""

    title = "Obtainable"
    parameter_name = "obtainable"

    def lookups(self, request, model_admin):
        """Values for the GET request and how they display"""
        return (("true", "True"), ("false", "False"))

    def queryset(self, request, queryset):
        """
        This performs a total tally of all clues for a given revelation, annotating the
        queryset accordingly, which is used in a subquery to determine if the requirements
        for this revelation can actually be met by players or not.
        """
        qs = queryset
        clues = (
            Clue.objects.filter(revelations=OuterRef("id"))
            .order_by()
            .values("revelations")
        )
        total_rating = clues.annotate(total=Sum("rating")).values("total")
        if self.value() == "true":
            qs = qs.filter(required_clue_value__lte=Subquery(total_rating))
        if self.value() == "false":
            qs = qs.filter(required_clue_value__gt=Subquery(total_rating))
        return qs


class RevelationAdmin(BaseCharAdmin):
    """Admin for revelations"""

    list_display = ("id", "name", "known_by", "requires")
    inlines = [ClueForRevInline, RevDiscoInline, RevPlotInvolvementInline]
    search_fields = ("=id", "name", "mysteries__name", "search_tags__name")
    list_filter = (RevelationListFilter, "mysteries")
    filter_horizontal = ("search_tags", "mysteries")
    raw_id_fields = ("author",)

    @staticmethod
    def known_by(obj):
        """Names of people who've discovered this revelation"""
        return ", ".join([str(ob.character) for ob in obj.discoveries.all()])


class ClueDiscoInline(admin.TabularInline):
    """Inline of Clue Discoveries"""

    model = ClueDiscovery
    extra = 0
    raw_id_fields = ("clue", "character", "investigation", "revealed_by", "milestone")


class CluePlotInvolvementInline(admin.TabularInline):
    """Inline for Plot involvement for clues"""

    model = CluePlotInvolvement
    extra = 0
    raw_id_fields = ("clue", "plot")
    classes = ["collapse"]


class ClueListTagFilter(admin.SimpleListFilter):
    """List filter for clues with or without search tags"""

    title = "Search Tags"
    parameter_name = "search tags"

    def lookups(self, request, model_admin):
        """Values for the GET request and how they display"""
        return (("have_tags", "Have Tags"), ("no_tags", "No Tags"))

    def queryset(self, request, queryset):
        """Modifies the queryset of Clues to filter those with, or without, search_tags"""
        qs = queryset
        if self.value() == "have_tags":
            return qs.filter(search_tags__isnull=False)
        elif self.value() == "no_tags":
            return qs.filter(search_tags__isnull=True)


class ClueAdmin(BaseCharAdmin):
    """Admin for Clues"""

    list_display = ("id", "name", "rating", "used_for")
    search_fields = ("=id", "name", "=search_tags__name")
    inlines = (ClueForRevInline, CluePlotInvolvementInline)
    filter_horizontal = ("search_tags",)
    raw_id_fields = (
        "author",
        "tangible_object",
    )
    list_filter = ("clue_type", "allow_investigation", ClueListTagFilter)
    readonly_fields = ("discovered_by", "current_investigations")

    @mark_safe
    def used_for(self, obj):
        return ", ".join(
            '<a href="%s">%s</a>'
            % (
                reverse("admin:character_revelation_change", args=[rev.id]),
                escape(rev.name),
            )
            for rev in obj.revelations.all()
        )

    used_for.allow_tags = True

    @mark_safe
    def discovered_by(self, obj):
        return ", ".join(
            '<a href="%s">%s</a>'
            % (
                reverse("admin:character_rosterentry_change", args=[ros.id]),
                escape(str(ros)),
            )
            for ros in obj.characters.all()
        )

    discovered_by.allow_tags = True

    @mark_safe
    def current_investigations(self, obj):
        return ", ".join(
            '<a href="%s">%s</a>'
            % (
                reverse("admin:character_investigation_change", args=[inv.id]),
                escape(str(inv)),
            )
            for inv in obj.investigation_set.filter(ongoing=True)
        )

    current_investigations.allow_tags = True


class ClueDiscoveryAdmin(BaseCharAdmin):
    """Admin for ClueDiscoveries"""

    list_display = (
        "id",
        "clue",
        "character",
        "discovery_method",
        "revealed_by",
        "investigation",
    )
    search_fields = ("=id", "clue__name", "=character__character__db_key")
    raw_id_fields = ("clue", "character", "investigation", "revealed_by")


class RevelationDiscoveryAdmin(BaseCharAdmin):
    """Admin for ClueDiscoveries"""

    list_display = (
        "id",
        "revelation",
        "character",
        "discovery_method",
        "revealed_by",
        "investigation",
    )
    search_fields = ("=id", "revelation__name", "=character__character__db_key")
    raw_id_fields = ("revelation", "character", "investigation", "revealed_by")


class RevForEntry(RevDiscoInline):
    """Inline of revelation discoveries"""

    fk_name = "character"
    raw_id_fields = (
        "character",
        "revelation",
        "investigation",
        "revealed_by",
        "milestone",
    )


class EntryAdmin(NoDeleteAdmin):
    """The primary admin model, the RosterEntry/Character Sheet for a player/character combination"""

    list_display = ("id", "character", "roster", "current_alts")
    ordering = ["roster", "character__db_key"]
    search_fields = ["character__db_key", "roster__name"]
    raw_id_fields = (
        "current_account",
        "profile_picture",
    )
    readonly_fields = (
        "character",
        "player",
    )
    list_filter = ("roster", "frozen", "inactive")
    form = EntryForm
    inlines = [RevForEntry, AccountHistoryInline]

    @staticmethod
    def current_alts(obj):
        """Names of alts for the RosterEntry"""
        return ", ".join([str(ob) for ob in obj.alts])


class InvestigationAssistantInline(admin.TabularInline):
    """Inline showing assistants for an investigation"""

    model = InvestigationAssistant
    extra = 0
    raw_id_fields = (
        "investigation",
        "char",
    )


class InvestigationListFilter(admin.SimpleListFilter):
    """List filter for showing whether an investigation will finish this week or not"""

    title = "Progress"
    parameter_name = "progress"

    def lookups(self, request, model_admin):
        """Values for the GET request and how they display"""
        return (("finishing", "Will Finish"), ("not_finishing", "Won't Finish"))

    def queryset(self, request, queryset):
        """
        So the queryset for this will be heavily annotated using django's Subquery and OuterRef classes.
        Basically we annotate the values of the total progress we need, how much progress is stored in
        the investigation's ClueDiscovery, and then determine if the total progress of our roll plus
        the clue's saved progress is high enough to meet that goal.
        Args:
            request: the HttpRequest object
            queryset: the Investigation queryset

        Returns:
            queryset that can be modified to either show those finishing or those who won't.
        """
        qs = queryset.annotate(
            total_progress=ExpressionWrapper(
                F("roll") + F("progress"), output_field=IntegerField()
            )
        )
        if self.value() == "finishing":
            # checking roll by itself in case there isn't a ClueDiscovery yet and would finish in one week
            return qs.filter(
                Q(total_progress__gte=F("completion_value"))
                | Q(roll__gte=F("completion_value"))
            )
        if self.value() == "not_finishing":
            return qs.filter(
                Q(total_progress__lt=F("completion_value"))
                & ~Q(roll__gte=F("completion_value"))
            )


class InvestigationAdmin(BaseCharAdmin):
    """Admin class for Investigations"""

    list_display = (
        "id",
        "character",
        "topic",
        "clue_target",
        "active",
        "ongoing",
        "automate_result",
    )
    list_filter = ("active", "ongoing", "automate_result", InvestigationListFilter)
    search_fields = (
        "=character__character__db_key",
        "topic",
        "clue_target__name",
        "=id",
    )
    inlines = [RevDiscoInline, ClueDiscoInline, InvestigationAssistantInline]
    raw_id_fields = (
        "clue_target",
        "character",
    )


class TheoryPermissionInline(admin.StackedInline):
    """Inline of TheoryPermissions for TheoryAdmin"""

    model = TheoryPermissions
    extra = 0
    raw_id_fields = ("player",)


class TheoryAdmin(BaseCharAdmin):
    """Admin class for Theory"""

    list_display = ("id", "creator", "topic", "description", "shared_with")
    filter_horizontal = ("known_by", "related_clues", "related_theories")
    inlines = (TheoryPermissionInline,)

    @staticmethod
    def shared_with(obj):
        """Who knows the theory"""
        return ", ".join(str(ob) for ob in obj.known_by.all())

    @mark_safe
    def description(self, obj):
        """Formatted description"""
        from web.help_topics.templatetags.app_filters import mush_to_html

        return mush_to_html(obj.desc)

    description.allow_tags = True


class StoryEmitAdmin(BaseCharAdmin):
    """Admin for Gemits"""

    list_display = ("id", "chapter", "episode", "text", "sender")
    filter_horizontal = ("search_tags",)


class SearchTagAdmin(BaseCharAdmin):
    """Admin for Search Tags. Has to exist for Clue's filter_horizontal to have an add box"""

    list_display = (
        "id",
        "name",
    )
    search_fields = (
        "=id",
        "name",
    )
    readonly_fields = (
        "tagged_revelations",
        "tagged_clues",
        "tagged_plots",
        "tagged_plot_updates",
        "tagged_actions",
        "tagged_story_emits",
        "tagged_objects",
        "tagged_events",
    )
    raw_id_fields = ("game_objects",)

    @mark_safe
    def tagged_revelations(self, obj):
        return "<br>".join(
            '<a href="%s">%s</a>'
            % (
                reverse("admin:character_revelation_change", args=[rev.id]),
                escape(rev.name),
            )
            for rev in obj.revelations.all()
        )

    tagged_revelations.allow_tags = True

    @mark_safe
    def tagged_clues(self, obj):
        return "<br>".join(
            '<a href="%s">%s</a>'
            % (
                reverse("admin:character_clue_change", args=[clue.id]),
                escape(clue.name),
            )
            for clue in obj.clues.all()
        )

    tagged_clues.allow_tags = True

    @mark_safe
    def tagged_plots(self, obj):
        return "<br>".join(
            '<a href="%s">%s</a>'
            % (reverse("admin:dominion_plot_change", args=[plot.id]), escape(plot.name))
            for plot in obj.plots.all()
        )

    tagged_plots.allow_tags = True

    @mark_safe
    def tagged_plot_updates(self, obj):
        return "<br>".join(
            '<a href="%s">%s</a>'
            % (
                reverse("admin:dominion_plotupdate_change", args=[update.id]),
                escape(str(update)),
            )
            for update in obj.plot_updates.all()
        )

    tagged_plot_updates.allow_tags = True

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
    def tagged_objects(self, obj):
        return "<br>".join(
            '<a href="%s">%s</a>'
            % (
                reverse("admin:objects_objectdb_change", args=[objdb.id]),
                escape(objdb.db_key),
            )
            for objdb in obj.game_objects.all()
        )

    tagged_objects.allow_tags = True

    @mark_safe
    def tagged_events(self, obj):
        return "<br>".join(
            '<a href="%s">%s</a>'
            % (reverse("admin:dominion_rpevent_change", args=[ev.id]), escape(ev.name))
            for ev in obj.events.all()
        )

    tagged_events.allow_tags = True


class FirstContactAdmin(BaseCharAdmin):
    """Admin for First Impressions"""

    list_display = ("id", "from_name", "summary", "to_name")
    search_fields = (
        "=id",
        "from_account__entry__player__username",
        "to_account__entry__player__username",
    )
    readonly_fields = ("from_account", "to_account")

    @staticmethod
    def from_name(obj):
        """name of the sender"""
        return str(obj.from_account.entry)

    @staticmethod
    def to_name(obj):
        """Name of the receiver"""
        return str(obj.to_account.entry)


class PostInline(admin.StackedInline):
    """Inline for Flashback Posts"""

    model = FlashbackPost
    extra = 0
    exclude = ("readable_by", "db_date_created")
    raw_id_fields = ("poster",)
    fieldsets = [
        (None, {"fields": []}),
        ("Posts", {"fields": ["poster", "actions"], "classes": ["collapse"]}),
    ]
    classes = ["collapse"]


class FBParticipantsInline(admin.TabularInline):
    """Inline for Flashback Participants"""

    model = FlashbackInvolvement
    extra = 0
    exclude = ("roll",)
    readonly_fields = ("num_posts",)
    raw_id_fields = ("participant",)
    classes = ["collapse"]

    @staticmethod
    def num_posts(obj):
        return obj.contributions.count()


class FlashbackAdmin(BaseCharAdmin):
    """Admin for Flashbacks"""

    list_display = (
        "id",
        "title",
        "owner",
    )
    search_fields = ("=id", "title", "participants__player__username")
    inlines = [FBParticipantsInline, PostInline]
    fieldsets = [(None, {"fields": ["title", "summary"]})]

    @staticmethod
    def owner(obj):
        """List names of our characters for list display"""
        return str(obj.owner).capitalize()


class GoalUpdateInline(admin.StackedInline):
    """Inline for Goal Updates"""

    model = GoalUpdate
    extra = 0
    raw_id_fields = ("beat",)


class GoalAdmin(BaseCharAdmin):
    """Admin for Goals"""

    list_display = ("id", "entry", "summary", "status", "scope", "plot")
    search_fields = (
        "=id",
        "entry__player__username",
        "summary",
        "description",
        "gm_notes",
    )
    raw_id_fields = ("entry", "plot")
    list_filter = ("scope", "status")
    inlines = (GoalUpdateInline,)


class PlayerPositionsAdmin(BaseCharAdmin):
    list_display = ("name",)
    filter_horizontal = ("players",)


# Register your models here.
admin.site.register(Roster, BaseCharAdmin)
admin.site.register(RosterEntry, EntryAdmin)
admin.site.register(FirstContact, FirstContactAdmin)
admin.site.register(Photo, PhotoAdmin)
admin.site.register(Story, BaseCharAdmin)
admin.site.register(Chapter, ChapterAdmin)
admin.site.register(Episode, EpisodeAdmin)
admin.site.register(Milestone, BaseCharAdmin)
admin.site.register(PlayerAccount, AccountAdmin)
admin.site.register(StoryEmit, StoryEmitAdmin)
admin.site.register(Mystery, MysteryAdmin)
admin.site.register(Revelation, RevelationAdmin)
admin.site.register(RevelationDiscovery, RevelationDiscoveryAdmin)
admin.site.register(Clue, ClueAdmin)
admin.site.register(ClueDiscovery, ClueDiscoveryAdmin)
admin.site.register(Investigation, InvestigationAdmin)
admin.site.register(Theory, TheoryAdmin)
admin.site.register(Flashback, FlashbackAdmin)
admin.site.register(SearchTag, SearchTagAdmin)
admin.site.register(Goal, GoalAdmin)
admin.site.register(PlayerPosition, PlayerPositionsAdmin)
