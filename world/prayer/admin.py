from django.contrib import admin
from world.prayer.models import Prayer, PrayerAnswer, InvocableEntity, EntityAlias


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
            (None, "Unanswered"),
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


class PrayerAdmin(admin.ModelAdmin):
    list_display = ("character", "entity", "is_answered", "some_text")
    raw_id_fields = ("character",)
    inlines = (PrayerAnswerInline,)
    ordering = ("-db_date_created",)
    search_fields = ("character__db_key", "entity__name", "text")

    @staticmethod
    def some_text(obj):
        return obj.text[:40]


class EntityAliasInline(admin.StackedInline):
    model = EntityAlias
    extra = 0


class InvocableEntityAdmin(admin.ModelAdmin):
    list_display = ("name", "public")
    raw_id_fields = ("character",)
    inlines = (EntityAliasInline,)


admin.site.register(Prayer, PrayerAdmin)
admin.site.register(InvocableEntity, InvocableEntityAdmin)
