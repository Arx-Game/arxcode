from django.contrib import admin

from evennia.objects.admin import ObjectDBAdmin
from evennia.objects.models import ObjectDB
from evennia_extensions.object_extensions.models import Dimensions, Permanence

from web.character.models import Clue
from world.traits.models import CharacterTraitValue, Trait


class DimensionsAdmin(admin.ModelAdmin):
    list_display = ("pk", "size", "weight", "capacity", "quantity")
    search_fields = ("pk", "objectdb__db_key")
    raw_id_fields = ("objectdb",)


class PermanenceAdmin(admin.ModelAdmin):
    list_display = ("pk", "put_time", "deleted_time")
    search_fields = ("pk", "objectdb__db_key")
    raw_id_fields = ("objectdb",)


class ClueForCharacterInline(admin.StackedInline):
    model = Clue
    extra = 0
    raw_id_fields = (
        "tangible_object",
        "author",
    )
    filter_horizontal = ("search_tags",)
    show_change_link = True


class CharacterTraitValueInline(admin.TabularInline):
    model = CharacterTraitValue
    extra = 0
    ordering = ("trait__trait_type", "trait__name")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Orders the material type selection"""
        if db_field.name == "trait":
            kwargs["queryset"] = Trait.objects.order_by("name")
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class PermanenceInline(admin.TabularInline):
    model = Permanence
    extra = 0


class DimensionsInline(admin.TabularInline):
    model = Dimensions
    extra = 0


class ArxObjectDBAdmin(ObjectDBAdmin):
    search_fields = ["=id", "db_key"]
    inlines = list(ObjectDBAdmin.inlines) + [
        ClueForCharacterInline,
        CharacterTraitValueInline,
        DimensionsInline,
        PermanenceInline,
    ]


admin.site.register(Dimensions, DimensionsAdmin)
admin.site.register(Permanence, PermanenceAdmin)
admin.site.unregister(ObjectDB)
admin.site.register(ObjectDB, ArxObjectDBAdmin)
