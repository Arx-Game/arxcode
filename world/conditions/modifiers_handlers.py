"""
Handlers for roll modifiers. Primarily this is for caching: Doing multiple queries on every dice roll
could rapidly get really out of hand during combat where there might be dozens of simultaneous rolls,
for example.
"""
from server.utils.arx_utils import CachedProperty
from world.conditions.models import RollModifier


class ModifierHandler(object):
    """Caches and handles various RollModifier queries"""
    def __init__(self, obj):
        self.obj = obj

    @CachedProperty
    def knacks(self):
        return list(self.obj.modifiers.filter(modifier_type=RollModifier.KNACK))

    def get_knack_by_name(self, name):
        """
        Gets a knack by its name
        Args:
            name: Name of the knack
        Returns:
            The knack or None
        """
        matches = [ob for ob in self.knacks if name.lower() == ob.name.lower()]
        if matches:
            return matches[0]

    def create_knack(self, name, stat, skill, desc=""):
        """
        Creates a new knack for the character
        Args:
            name: Knack name
            stat: stat for the knack
            skill: skill for the knack
            desc: Description of the knack

        Returns:
            The new knack
        """
        knack = self.obj.modifiers.create(modifier_type=RollModifier.KNACK, name=name, stat=stat, skill=skill,
                                          description=desc, value=1)
        del self.knacks  # clear cache
        return knack

    def display_knacks(self):
        msg = "Knacks for {}:\n".format(self.obj.key)
        msg += "\n".join(knack.display_knack() for knack in self.knacks)
        return msg

    def get_total_roll_modifiers(self, stats, skills):
        """Returns the modifiers for given stats and skills"""
        total = 0
        for knack in self.knacks:
            if knack.stat in stats and knack.skill in skills:
                total += knack.value
        return total
        # TODO: Refactor of modifier mixins and combat to move everything here, including temp mods, items, location

    def get_crit_modifiers(self, stats, skills):
        """Returns the total crit modifier from our knacks"""
        total = 0
        for knack in self.knacks:
            if knack.stat in stats and knack.skill in skills:
                # 1 + half the value of an applicable knack is added to our crit chance
                total += knack.crit_chance_bonus
        return total
