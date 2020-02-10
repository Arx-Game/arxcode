"""
wearable weapons
"""
from typeclasses.wearable.wieldable import Wieldable


class DecorativeWieldable(Wieldable):
    """
    Legacy Class for wieldable objects that, when worn, are not considered
    'sheathed' weapons but as normal wearables.
    """
    @property
    def decorative(self):
        """We decorate. AND we murder."""
        return True
