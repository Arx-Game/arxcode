from django.contrib import admin

from world.crafting.models import (
    CraftingMaterialType,
    CraftingRecipe,
    RequiredMaterial,
    CraftingRecord,
    RefineAttempt,
)


class RequiredMaterialInline(admin.StackedInline):
    model = RequiredMaterial
    extra = 0
    raw_id_fields = ("type",)


class MaterialTypeAdmin(admin.ModelAdmin):
    """Admin for Crafting Material Types, creating/changing the types that exist"""

    list_display = ("id", "name", "desc", "value", "category")
    ordering = ["value"]
    search_fields = ["name", "desc", "category"]
    list_filter = ("category",)


class RecipeAdmin(admin.ModelAdmin):
    """Admin for crafting recipes"""

    list_display = ("id", "name", "skill", "ability", "level", "difficulty")
    ordering = ["ability", "level", "name"]
    search_fields = ["name", "ability", "skill"]
    list_filter = ("ability",)
    filter_horizontal = [
        "known_by",
    ]
    inlines = (RequiredMaterialInline,)


class RefineAttemptInline(admin.StackedInline):
    model = RefineAttempt
    extra = 0
    raw_id_fields = ("crafter",)


class CraftingRecordAdmin(admin.ModelAdmin):
    list_display = ("object_name", "crafter_name", "quality_level", "recipe")
    raw_id_fields = ("objectdb", "crafted_by", "recipe")
    search_fields = ("objectdb__db_key", "=objectdb__id", "=crafted_by__db_key", "recipe__name")
    inlines = (RefineAttemptInline,)

    @staticmethod
    def object_name(obj):
        return obj.objectdb.db_key

    object_name.short_description = "Crafted Object"

    @staticmethod
    def crafter_name(obj):
        if not obj.crafted_by:
            return ""
        return obj.crafted_by.db_key

    crafter_name.short_description = "Crafter"


admin.site.register(CraftingMaterialType, MaterialTypeAdmin)
admin.site.register(CraftingRecipe, RecipeAdmin)
admin.site.register(CraftingRecord, CraftingRecordAdmin)
