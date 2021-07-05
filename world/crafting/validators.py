"""
Various functions for validating/getting values that django's
normal field transformations won't do, such as getting a model
by ID or name. Every validator function should be a callable
with a single argument, and return the cleaned/validated value.
"""
from django.core.exceptions import (
    ValidationError,
    ObjectDoesNotExist,
    MultipleObjectsReturned,
)


def get_model_by_id_or_name(model, value, name_attr="name"):
    if isinstance(value, model):
        return value
    try:
        try:
            return model.objects.get(id=int(value))
        except (TypeError, ValueError):
            arg_dict = {f"{name_attr}__iexact": value}
            try:
                return model.objects.get(**arg_dict)
            except MultipleObjectsReturned:
                arg_dict = {name_attr: value}
                return model.objects.get(**arg_dict)
    except ObjectDoesNotExist:
        raise ValidationError(f"Could not find a {model} for value of {value}.")


def get_recipe(value):
    from world.crafting.models import CraftingRecipe

    return get_model_by_id_or_name(CraftingRecipe, value)


def get_material(value):
    from world.crafting.models import CraftingMaterialType

    return get_model_by_id_or_name(CraftingMaterialType, value)


def get_character(value):
    from typeclasses.characters import Character

    return get_model_by_id_or_name(Character, value, "db_key")
