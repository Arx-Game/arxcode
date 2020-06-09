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
            ('org', 'Organizations'),
            ('char', 'Characters'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'org':
            return queryset.filter(entities__organization_owner__isnull=False).distinct()
        if self.value() == 'char':
            return queryset.filter(entities__player__isnull=False).distinct()


class QuestStepInline(admin.TabularInline):
    """Inline of steps for a quest"""
    model = QuestStep
    ordering = ('step_number',)
    extra = 0
    fieldsets = [(None, {'fields': [('step_number', 'name')]}),
                 (None, {'fields': ['ic_desc', 'gm_note'],
                         'description': "Optional details or instruction for this Quest Step.", })]


class QuestStatusInline(admin.TabularInline):
    """Inline of statuses of entities on a quest"""
    model = QuestStatus
    extra = 0
    show_change_link = True
    raw_id_fields = ('entity',)
    readonly_fields = ('db_date_created', 'quest_completed',)
    classes = ['collapse']
    fieldsets = [(None, {'fields': [('entity', 'db_date_created', 'quest_completed')]}),
                 (None, {'fields': ['ic_desc', 'gm_note'],
                         'classes': ['collapse']})]


class QuestAdmin(admin.ModelAdmin):
    """Admin for Quest model."""
    list_display = ('id', 'name', 'num_steps', 'has', 'done')
    search_fields = (
    '=name', 'id', '=search_tags__name', '=entities__player__player__username', '=entities__organization_owner__name')
    filter_horizontal = ('search_tags',)
    list_filter = (QuestListFilter,)
    fields = ('name', 'ic_note', 'gm_note', 'search_tags')
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
    list_select_related = ('status__entity', 'step')
    ordering = ('step__step_number', 'attempt_number')
    raw_id_fields = ('event', 'flashback', 'clue', 'org_clue', 'revelation', 'action', 'quest')
    extra = 0
    fk_name = 'status'
    fieldsets = [(None, {'fields': [('step', 'attempt_number', 'step_completed')]}),
                 (None, {'fields': [('event', 'action', 'flashback'), ('clue', 'revelation', 'org_clue', 'quest')],
                         'description': "Please choose only one field per Effort.",
                         'classes': ['collapse']})]


class QuestStatusAdmin(admin.ModelAdmin):
    """Admin for the status of entities' progress on a quest."""
    list_display = ('id', 'status_name', 'db_date_created', 'quest_completed')
    search_fields = ('id', '=quest__name', '=entity__player__player__username', '=entity__organization_owner__name')
    list_filter = (QuestStatusListFilter,)
    raw_id_fields = ('entity',)
    readonly_fields = ('quest', 'quest_completed',)
    fieldsets = [(None, {'fields': [('quest', 'entity', 'quest_completed')]}),
                 (None, {'fields': ['ic_desc', 'gm_note'],
                         'description': "A story linking efforts toward quest resolution.",})]
    inlines = [QuestStepEffortInline]

    @staticmethod
    def status_name(obj):
        return str(obj)


admin.site.register(Quest, QuestAdmin)
admin.site.register(QuestStatus, QuestStatusAdmin)

#TODO ask whether Effort model's on-save queries are unevaluated, as variables.
#TODO ask whether QuestStepEffortInline needs 'step' in select_related
#TODO in quest admin, make sure queststatus inline is collapsing overall
#TODO make migrations
