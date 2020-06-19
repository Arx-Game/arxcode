"""
Admin for Quests
"""
from django import forms
from django.contrib import admin

from .models import Quest, QuestStep, QuestStatus, QuestEffort


class StatusDateMixin:
    """A mixin keeping readonly dates DRY."""
    @staticmethod
    def started(obj):
        return obj.db_date_created.strftime('%Y-%m-%d')

    @staticmethod
    def completed(obj):
        if obj.quest_completed:
            return obj.quest_completed.strftime('%Y-%m-%d')
        else:
            return "no"


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


class QuestStepInline(admin.StackedInline):
    """Inline of steps for a quest"""
    model = QuestStep
    ordering = ('step_number',)
    extra = 0
    classes = ['collapse']
    fields = (('name', 'step_number'), 'ic_desc', 'gm_note')


class QuestStatusInline(admin.TabularInline, StatusDateMixin):
    """Inline of quester-statuses on a quest."""
    model = QuestStatus
    extra = 0
    show_change_link = True
    raw_id_fields = ('entity',)
    readonly_fields = ('started', 'completed',)
    classes = ['collapse']
    fields = ('entity', 'started', 'completed')


class QuestAdmin(admin.ModelAdmin):
    """Admin for Quest model."""
    list_display = ('id', '__str__', 'questers', 'finished')
    search_fields = (
        'name', '=id', 'search_tags__name', '=entities__player__player__username',
        '=entities__organization_owner__name')
    filter_horizontal = ('search_tags',)
    list_filter = (QuestListFilter,)
    fields = ('name', 'ic_desc', 'gm_note', 'search_tags')
    inlines = [QuestStepInline, QuestStatusInline]
    save_on_top = True

    @staticmethod
    def questers(obj):
        return obj.statuses.all().count()

    @staticmethod
    def finished(obj):
        return obj.statuses.filter(quest_completed__isnull=False).count()


class QuestStatusListFilter(QuestListFilter):
    """Separates quest statuses of Characters from Organizations."""
    def queryset(self, request, queryset):
        if self.value() == 'org':
            return queryset.filter(entity__organization_owner__isnull=False).distinct()
        if self.value() == 'char':
            return queryset.filter(entity__player__isnull=False).distinct()


class QuestEffortForm(forms.ModelForm):
    """Form that limits the 'step' selection to only steps in our particular quest."""
    step = forms.ModelChoiceField(queryset=None, label='Quest Step', required=True)


class QuestEffortInline(admin.StackedInline):
    """Inline allowing Efforts to be added to a quest status."""
    model = QuestEffort
    form = QuestEffortForm
    list_select_related = ('status__entity',)
    ordering = ('step__step_number', 'step__name', 'attempt_number')
    raw_id_fields = ('event', 'flashback', 'clue', 'org_clue', 'revelation', 'action', 'quest')
    extra = 0
    fk_name = 'status'
    fieldsets = [(None, {'fields': [('step', 'attempt_number', 'step_completed')]}),
                 (None, {'fields': ['event', 'action', 'flashback', 'clue', 'revelation', 'org_clue', 'quest'],
                         'description': "Please choose only one field:"})]

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        if obj:
            step_field = formset.form.declared_fields['step']
            step_field.queryset = QuestStep.objects.filter(quest=obj.quest_id).order_by('step_number')
        return formset


class QuestStatusForm(forms.ModelForm):
    """Form for status of someone's progress on a quest."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = getattr(self, 'instance', None)
        if instance and instance.pk:
            # noinspection PyStatementEffect
            self.fields['quest'].widget.attrs['readonly']


class QuestStatusAdmin(admin.ModelAdmin, StatusDateMixin):
    """Admin for the status of someone's progress on a quest."""
    list_display = ('id', '__str__', 'started', 'completed')
    search_fields = ('=id', 'quest__name', '=entity__player__player__username', '=entity__organization_owner__name')
    list_filter = (QuestStatusListFilter,)
    raw_id_fields = ('entity',)
    readonly_fields = ('started', 'completed',)
    fieldsets = [(None, {'fields': [('quest', 'entity'), ('started', 'completed')]}),
                 (None, {'fields': ['ic_desc', 'gm_note'],
                         'description': "Summary linking efforts toward quest resolution."})]
    inlines = [QuestEffortInline]
    save_on_top = True

    def get_inline_instances(self, request, obj=None):
        if obj:
            return [ob(self.model, self.admin_site) for ob in self.inlines]
        return []


# Register your models here.
admin.site.register(Quest, QuestAdmin)
admin.site.register(QuestStatus, QuestStatusAdmin)
