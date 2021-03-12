from django.contrib import admin
from world.traits.models import Trait, CharacterTraitValue


class TraitAdmin(admin.ModelAdmin):
    list_display = ("name", "trait_type", "category")
    list_filter = ("trait_type", "category")
    search_fields = ("name",)


class TraitValueListFilter(admin.SimpleListFilter):
    """List filter for separating PC and NPC trait values"""

    title = "Roster or Agent"
    parameter_name = "char_type"

    def lookups(self, request, model_admin):
        """Defines lookup display for list filter"""
        return (
            ("is_agent", "Agent"),
            ("all", "All"),
        )

    def queryset(self, request, queryset):
        """Specifies queryset we get based on selected options"""
        if self.value() == "is_agent":
            return queryset.filter(character__roster__isnull=True)
        if self.value() is None:
            return queryset.filter(character__roster__isnull=False)
        if self.value() == "all":
            return queryset.all()

    def choices(self, changelist):
        yield {
            "selected": self.value() is None,
            "query_string": changelist.get_query_string(remove=[self.parameter_name]),
            "display": "Roster Character",
        }
        for lookup, title in self.lookup_choices:
            yield {
                "selected": self.value() == str(lookup),
                "query_string": changelist.get_query_string(
                    {self.parameter_name: lookup}
                ),
                "display": title,
            }


class CharacterTraitValueAdmin(admin.ModelAdmin):
    list_display = ("character_name", "name", "value")
    search_fields = ("trait__name", "character__db_key")
    raw_id_fields = ("character",)
    list_filter = (TraitValueListFilter,)

    @staticmethod
    def character_name(obj):
        return obj.character.db_key

    character_name.admin_order_field = "character__db_key"


admin.site.register(Trait, TraitAdmin)
admin.site.register(CharacterTraitValue, CharacterTraitValueAdmin)
