"""
Admin for Quests
"""
from django.contrib import admin
from .models import Quest, QuestStep, QuestStatus, QuestStepEffort


class QuestListFilter(admin.SimpleListFilter):
    """Separates character quests from organization quests."""
    title = "Org or Char"
    parameter_name = "for"

    def lookups(self, request, model_admin):
        return (
            ('org', 'For Organizations'),
            ('char', 'For Characters'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'org':
            return queryset.filter(entities__organization_owner__isnull=False).distinct()
        if self.value() == 'char':
            return queryset.filter(entities__player__isnull=False).distinct()


class QuestStepInline(admin.TabularInline):
    """Inline of steps for a quest"""
    model = QuestStep
    extra = 0


class QuestStatusInline(admin.TabularInline):
    """Inline of statuses of entities on a quest"""
    model = QuestStatus
    extra = 0
    show_change_link = True
    raw_id_fields = ('entity',)


class QuestAdmin(admin.ModelAdmin):
    """Admin for Quest model."""
    list_display = ('id', 'name', 'num_steps', 'has', 'done')
    search_fields = (
    'name', '=id', '=search_tags__name', '=entities__player__player__username', 'entities__organization_owner__name')
    filter_horizontal = ('search_tags',)
    list_filter = (QuestListFilter,)
    inlines = [QuestStepInline, QuestStatusInline]

    @staticmethod
    def num_steps(obj):
        return obj.steps.all().count()

    @staticmethod
    def has(obj):
        return obj.statuses.all().count()

    @staticmethod
    def done(obj):
        return obj.statuses.filter(quest_completed__isnull=False).count()


class QuestStatusListFilter(QuestListFilter):
    """Separates quest statuses of Characters from Organizations."""
    def queryset(self, request, queryset):
        if self.value() == 'org':
            return queryset.filter(entity__organization_owner__isnull=False).distinct()
        if self.value() == 'char':
            return queryset.filter(entity__player__isnull=False).distinct()


class QuestStepEffortInline(admin.TabularInline):
    model = QuestStepEffort
    ordering = ('step__step_number', 'attempt_number')
    raw_id_fields = ('event', 'flashback', 'char_clue', 'org_clue', 'revelation', 'action', 'quest_status')
    extra = 0
    fk_name = 'status'


class QuestStatusAdmin(admin.ModelAdmin):
    """Admin for the status of entities' progress on a quest."""
    list_display = ('status_name', 'db_date_created', 'quest_completed')
    search_fields = ('=id', 'quest__name', '=entity__player__player__username', 'entity__organization_owner__name')
    list_filter = (QuestStatusListFilter,)
    raw_id_fields = ('entity',)
    inlines = [QuestStepEffortInline]

    @staticmethod
    def status_name(obj):
        return str(obj)


admin.site.register(Quest, QuestAdmin)
admin.site.register(QuestStatus, QuestStatusAdmin)
