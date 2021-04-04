from django.contrib import admin

from evennia.objects.admin import ObjectDBAdmin
from evennia.objects.models import ObjectDB
from evennia_extensions.object_extensions.models import Dimensions, Permanence

from web.character.models import Clue
from world.traits.models import CharacterTraitValue, Trait
from world.crafting.models import (
    CraftingRecord,
    AdornedMaterial,
    TranslatedDescription,
    WeaponOverride,
    ArmorOverride,
    PlaceSpotsOverride,
    MaskedDescription,
)


class DimensionsAdmin(admin.ModelAdmin):
    list_display = ("pk", "size", "weight", "capacity", "quantity")
    search_fields = ("pk", "objectdb__db_key")
    raw_id_fields = ("objectdb",)


class PermanenceAdmin(admin.ModelAdmin):
    list_display = ("pk", "put_time", "deleted_time")
    search_fields = ("pk", "objectdb__db_key")
    raw_id_fields = ("objectdb",)


class SecretsInline(admin.StackedInline):
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
    raw_id_fields = ("objectdb",)


class DimensionsInline(admin.TabularInline):
    model = Dimensions
    extra = 0
    raw_id_fields = ("objectdb",)


class CraftingRecordInline(admin.TabularInline):
    model = CraftingRecord
    extra = 0
    raw_id_fields = ("crafted_by", "recipe", "objectdb")
    fk_name = "objectdb"


class TranslatedDescriptionInline(admin.StackedInline):
    model = TranslatedDescription
    extra = 0
    raw_id_fields = ("objectdb",)


class AdornedMaterialInline(admin.StackedInline):
    model = AdornedMaterial
    extra = 0
    raw_id_fields = ("type", "objectdb")


class MaskedDescriptionInline(admin.TabularInline):
    model = MaskedDescription
    extra = 0
    raw_id_fields = ("objectdb",)


class PlaceSpotsOverrideInline(admin.TabularInline):
    model = PlaceSpotsOverride
    extra = 0
    raw_id_fields = ("objectdb",)


class ArmorOverrideInline(admin.TabularInline):
    model = ArmorOverride
    extra = 0
    raw_id_fields = ("objectdb",)


class WeaponOverrideInline(admin.TabularInline):
    model = WeaponOverride
    extra = 0
    raw_id_fields = ("objectdb",)


class ArxObjectDBAdmin(ObjectDBAdmin):
    search_fields = ["=id", "db_key"]
    inlines = list(ObjectDBAdmin.inlines) + [
        SecretsInline,
        DimensionsInline,
        PermanenceInline,
    ]
    character_inlines = [CharacterTraitValueInline]
    crafted_inlines = [
        CraftingRecordInline,
        TranslatedDescriptionInline,
        AdornedMaterialInline,
    ]
    mask_inlines = [MaskedDescriptionInline]
    place_inlines = [PlaceSpotsOverrideInline]
    wearable_inlines = [ArmorOverrideInline]
    wieldable_inlines = [WeaponOverrideInline]

    def get_inline_instances(self, request, obj=None):
        from typeclasses.characters import Character
        from typeclasses.objects import Object as CraftedObject
        from typeclasses.disguises.disguises import Mask
        from typeclasses.places.places import Place
        from typeclasses.wearable.wearable import Wearable
        from typeclasses.wearable.wieldable import Wieldable

        if obj:
            final_inlines = list(self.inlines)
            if isinstance(obj, Character):
                final_inlines += self.character_inlines
            if isinstance(obj, CraftedObject):
                final_inlines += self.crafted_inlines
            if isinstance(obj, Mask):
                final_inlines += self.mask_inlines
            if isinstance(obj, Place):
                final_inlines += self.place_inlines
            if isinstance(obj, Wearable):
                final_inlines += self.wearable_inlines
            if isinstance(obj, Wieldable):
                final_inlines += self.wieldable_inlines
            return [
                inline(self.model, self.admin_site) for inline in set(final_inlines)
            ]
        return []


admin.site.register(Dimensions, DimensionsAdmin)
admin.site.register(Permanence, PermanenceAdmin)
admin.site.unregister(ObjectDB)
admin.site.register(ObjectDB, ArxObjectDBAdmin)
