from evennia_extensions.object_extensions.validators import get_model_by_id_or_name


def race_validator(value):
    from evennia_extensions.character_extensions.models import Race

    return get_model_by_id_or_name(Race, value)


def fealty_validator(value):
    from world.dominion.models import Fealty

    return get_model_by_id_or_name(Fealty, value)


def religion_validator(value):
    from world.prayer.models import Religion

    return get_model_by_id_or_name(Religion, value)
