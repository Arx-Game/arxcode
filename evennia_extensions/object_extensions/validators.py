from django.core.exceptions import (
    MultipleObjectsReturned,
    ObjectDoesNotExist,
    ValidationError,
)
from decimal import Decimal


def get_model_by_id_or_name(model, value, name_attr="name"):
    if isinstance(value, model):
        return value
    try:
        try:
            value = value.lstrip("#").strip()
        except AttributeError:
            pass
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
    except MultipleObjectsReturned:
        raise ValidationError(f"Too many matches, please match by ID.")


def get_character(value):
    from typeclasses.characters import Character

    return get_model_by_id_or_name(Character, value, "db_key")


def get_objectdb(value):
    from evennia.objects.models import ObjectDB

    return get_model_by_id_or_name(ObjectDB, value, "db_key")


def get_room(value):
    from typeclasses.rooms import ArxRoom

    # noinspection PyTypeChecker
    return get_model_by_id_or_name(ArxRoom, value, "db_key")


def get_int(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        raise ValidationError("Value must be an integer")


def get_decimal(value):
    """Converts value to a decimal, or raises a ValidationError."""
    try:
        new_value = Decimal(value or 0)
        if new_value > 100000000000000:
            raise ValidationError("Value is too large")
        return new_value
    except (TypeError, ValueError):
        raise ValidationError("Value must be a decimal")
