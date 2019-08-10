"""
Consumable object.
"""

from typeclasses.objects import Object
from evennia.utils.utils import inherits_from


class Consumable(Object):
    """
    Consumable object. We will use the quality level in order to determine
    the number of uses we have remaining.
    """
    default_desc = "A consumable object"

    def consume(self):
        """
        Use a charge if it has any remaining. Return True if successful
        :return:
        """
        if not self.charges:
            return False
        self.charges -= 1
        return True

    @property
    def charges(self):
        if self.db.quality_level is None:
            self.db.quality_level = 0
        return self.db.quality_level

    @charges.setter
    def charges(self, val):
        self.db.quality_level = val

    def get_quality_appearance(self):
        if self.charges >= 0:
            msg = "\nIt has %s uses remaining." % self.charges
        else:
            msg = "\nIt has infinite uses."
        msg += " It can be used with the {wuse{n command."
        return msg

    @property
    def valid_typeclass_path(self):
        return "typeclasses.objects.DefaultObject"

    # noinspection PyUnusedLocal
    def check_target(self, target, caller):
        """
        Determines if a target is valid.
        """
        return inherits_from(target, self.valid_typeclass_path)

    # noinspection PyMethodMayBeStatic
    def use_on_target(self, target, caller):
        """
        Uses us on the target to produce some effect. Consume
        was already called.
        """
        pass
