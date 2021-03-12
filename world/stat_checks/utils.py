"""
Just a few utilities. Should NOT import anything in global scope to avoid
circular imports.
"""


def get_check_by_name(name: str):
    """
    Convenience method to avoid worrying about circular imports when
    fetching checks.
    """
    from world.stat_checks.models import StatCheck

    check = StatCheck.get_instance_by_name(name)
    if not check:
        raise StatCheck.DoesNotExist(f"No check exists by name '{name}'")
    return check


def get_check_maker_by_name(name: str, character, **kwargs):
    from world.stat_checks.check_maker import DefinedCheckMaker

    return DefinedCheckMaker(
        character=character, check=get_check_by_name(name), **kwargs
    )
