"""Exceptions for Typeclasses!"""


class EquipError(Exception):
    """Errors when donning equipment"""

    pass


class InvalidTargetError(ValueError):
    """Errors when trying to use a command/ability on an invalid target"""

    pass
