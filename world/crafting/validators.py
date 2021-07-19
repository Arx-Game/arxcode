"""
Various functions for validating/getting values that django's
normal field transformations won't do, such as getting a model
by ID or name. Every validator function should be a callable
with a single argument, and return the cleaned/validated value.
"""
from evennia_extensions.object_extensions.validators import get_model_by_id_or_name


def get_recipe(value):
    from world.crafting.models import CraftingRecipe

    return get_model_by_id_or_name(CraftingRecipe, value)


def get_material(value):
    from world.crafting.models import CraftingMaterialType

    return get_model_by_id_or_name(CraftingMaterialType, value)
