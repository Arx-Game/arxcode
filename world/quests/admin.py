"""
Admin for Quests
"""
from django.contrib import admin
from .models import Quest


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


class QuestAdmin(admin.ModelAdmin):
    """Admin for Quest model."""
    list_display = ('id', 'name', 'num_steps', 'has', 'done')
    search_fields = (
    'name', '=id', 'search_tags', '=entities__player__player__username', '=entities__organization_owner__name')
    filter_horizontal = ('search_tags')
    list_filter = (QuestListFilter,)
    inlines = []

    @staticmethod
    def num_steps(obj):
        return obj.steps.all().count()

    @staticmethod
    def has(obj):
        return obj.statuses.all().count()

    @staticmethod
    def done(obj):
        return obj.statuses.filter(quest_completed__isnull=False).count()


admin.site.register(Quest, QuestAdmin)
