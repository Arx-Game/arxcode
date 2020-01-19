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

    @property
    def slot(self):
        """slot the armor is worn on"""
        recipe = self.recipe
        if not recipe:
            return self.db.slot
        return recipe.wearable_stats.slot
