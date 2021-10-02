from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html_join

from evennia_extensions.character_extensions.models import (
    Characteristic,
    CharacteristicValue,
    CharacterSheetValue,
    CharacterSheet,
    CharacterMessengerSettings,
    CharacterCombatSettings,
    CharacterTitle,
    Race,
    HeldKey,
)


class CharacteristicValueInline(admin.TabularInline):
    model = CharacteristicValue
    extra = 0
    fields = ("value",)


class CharacterSheetValueInline(admin.TabularInline):
    model = CharacterSheetValue
    extra = 0
    raw_id_fields = ("character_sheet", "characteristic", "characteristic_value")


class PCOnlyFilter(admin.SimpleListFilter):
    """List filter for getting PCs"""

    title = "PCs"
    parameter_name = "pcs"

    def lookups(self, request, model_admin):
        """Defines lookup display for list filter"""
        return (
            ("pc", "PCs Only"),
            ("npc", "NPCs Only"),
        )

    def queryset(self, request, queryset):
        """Specifies queryset we get based on selected options"""
        if self.value() == "pc":
            return queryset.filter(
                objectdb__roster__roster__name__in=["Active", "Available"]
            ).distinct()
        if self.value() == "npc":
            return queryset.exclude(
                objectdb__roster__roster__name__in=["Active", "Available", "Incomplete"]
            ).distinct()


class OnlyPCCharacteristicsFilter(PCOnlyFilter):
    def queryset(self, request, queryset):
        if self.value() == "pc":
            return queryset.filter(
                sheet_values__character_sheet__objectdb__roster__roster__name__in=[
                    "Active",
                    "Available",
                ]
            ).distinct()
        if self.value() == "npc":
            return queryset.exclude(
                sheet_values__character_sheet__objectdb__roster__roster__name__in=[
                    "Active",
                    "Available",
                    "Incomplete",
                ]
            ).distinct()


class CharacteristicValueAdmin(admin.ModelAdmin):
    list_display = ("characteristic", "value")
    search_fields = ("=characteristic__name", "value")
    list_filter = ("characteristic", OnlyPCCharacteristicsFilter)
    raw_id_fields = ("characteristic",)
    readonly_fields = ("used_by",)
    filter_horizontal = ("allowed_races",)

    def used_by(self, obj):
        return format_html_join(
            ",",
            '<a href="{}">{}</a>',
            [
                (
                    reverse(
                        "admin:character_extensions_charactersheet_change",
                        args=[val.character_sheet_id],
                    ),
                    val.character_sheet.objectdb.db_key,
                )
                for val in obj.sheet_values.all()
            ],
        )

    used_by.allow_tags = True
    used_by.verbose_name = "Used By"


class RaceAdmin(admin.ModelAdmin):
    list_display = ("name", "race_type")
    filter_horizontal = ("allowed_characteristic_values",)


class CharacterExtensionAdmin(admin.ModelAdmin):
    list_display = ("pk", "character_name")
    search_fields = ("=objectdb__id", "objectdb__db_key")
    raw_id_fields = ("objectdb",)

    def character_name(self, obj):
        return obj.objectdb.db_key

    character_name.verbose_name = "Character Name"


class CharacterSheetAdmin(CharacterExtensionAdmin):
    list_display = CharacterExtensionAdmin.list_display + (
        "age",
        "social_rank",
        "family",
        "vocation",
    )
    inlines = (CharacterSheetValueInline,)
    list_filter = (PCOnlyFilter,)


class CombatSettingsAdmin(CharacterExtensionAdmin):
    raw_id_fields = CharacterExtensionAdmin.raw_id_fields + ("guarding",)


class MessengerSettingsAdmin(CharacterExtensionAdmin):
    raw_id_fields = CharacterExtensionAdmin.raw_id_fields + (
        "custom_messenger",
        "discreet_messenger",
    )
    search_fields = CharacterExtensionAdmin.search_fields + (
        "custom_messenger__db_key",
        "=custom_messenger__id",
    )


class CharacterTitlesAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "character_name",
        "title",
    )
    search_fields = ("=id", "character__db_key", "title")
    raw_id_fields = ("character",)

    def character_name(self, obj):
        return obj.character.db_key

    character_name.verbose_name = "Character Name"


class CharacteristicAdmin(admin.ModelAdmin):
    list_display = ("pk", "name", "description")


class HeldKeyAdmin(admin.ModelAdmin):
    list_display = ("character_name", "keyed_name", "key_type")
    list_filter = ("key_type",)
    raw_id_fields = ("character", "keyed_object")
    search_fields = (
        "character__db_key",
        "=keyed_object__id",
        "=character__id",
        "keyed_object__db_key",
    )

    def character_name(self, obj):
        return obj.character.db_key

    character_name.verbose_name = "Character Name"

    def keyed_name(self, obj):
        return obj.keyed_object.db_key

    keyed_name.verbose_name = "Keyed Object"


# Register your models here.
admin.site.register(CharacteristicValue, CharacteristicValueAdmin)
admin.site.register(Race, RaceAdmin)
admin.site.register(CharacterSheet, CharacterSheetAdmin)
admin.site.register(CharacterCombatSettings, CombatSettingsAdmin)
admin.site.register(CharacterMessengerSettings, MessengerSettingsAdmin)
admin.site.register(CharacterTitle, CharacterTitlesAdmin)
admin.site.register(Characteristic, CharacteristicAdmin)
admin.site.register(HeldKey, HeldKeyAdmin)
