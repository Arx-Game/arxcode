from django.contrib import admin
from world.prayer.models import (
    Prayer,
    PrayerAnswer,
    InvocableEntity,
    EntityAlias,
    Religion,
)
from django.shortcuts import reverse
from django.utils.html import escape
from django.utils.safestring import mark_safe
from evennia.utils.utils import crop


class PrayerAnswerInline(admin.TabularInline):
    model = PrayerAnswer
    raw_id_fields = ("vision", "manifestation", "miracle")
    extra = 0


class PrayerListFilter(admin.SimpleListFilter):
    """List filter for separating PC and NPC orgs"""

    title = "Answered or Unanswered"
    parameter_name = "answered"

    def lookups(self, request, model_admin):
        """Defines lookup display for list filter"""
        return (
            ("is_answered", "Answered"),
            ("all", "All"),
        )

    def queryset(self, request, queryset):
        """Specifies queryset we get based on selected options"""
        if self.value() == "is_answered":
            return queryset.filter(answer__isnull=False)
        if self.value() is None:
            return queryset.filter(answer__isnull=True)
        if self.value() == "all":
            return queryset.all()

    def choices(self, changelist):
        yield {
            "selected": self.value() is None,
            "query_string": changelist.get_query_string(remove=[self.parameter_name]),
            "display": "Unanswered",
        }
        for lookup, title in self.lookup_choices:
            yield {
                "selected": self.value() == str(lookup),
                "query_string": changelist.get_query_string(
                    {self.parameter_name: lookup}
                ),
                "display": title,
            }


class PrayerAdmin(admin.ModelAdmin):
    list_display = ("id", "character_name", "entity", "status", "prayer_text")
    raw_id_fields = ("character",)
    inlines = (PrayerAnswerInline,)
    ordering = ("-db_date_created",)
    search_fields = ("character__db_key", "entity__name", "text")
    list_filter = (PrayerListFilter,)

    def prayer_text(self, obj):
        return crop(obj.text, width=120)

    prayer_text.short_description = "Start of Prayer"

    @mark_safe
    def character_name(self, obj):
        character_url = reverse(
            "admin:objects_objectdb_change", args=[obj.character.id]
        )
        return f"<a href={character_url}>{escape(obj.character.db_key)}</a>"

    character_name.allow_tags = True
    character_name.short_description = "Character Name"
    character_name.admin_order_field = "character__db_key"


class EntityAliasInline(admin.StackedInline):
    model = EntityAlias
    extra = 0


class InvocableEntityAdmin(admin.ModelAdmin):
    list_display = ("name", "public")
    raw_id_fields = ("character",)
    inlines = (EntityAliasInline,)


class ReligionAdmin(admin.ModelAdmin):
    list_display = ("name",)


admin.site.register(Prayer, PrayerAdmin)
admin.site.register(InvocableEntity, InvocableEntityAdmin)
admin.site.register(Religion, ReligionAdmin)
