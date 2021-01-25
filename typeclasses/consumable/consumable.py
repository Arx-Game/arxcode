"""
Consumable object.
"""

from typeclasses.objects import Object
from world.crafting.craft_handlers import ConsumableCraftHandler
from evennia.utils.utils import inherits_from


class Consumable(Object):
    """
    Consumable object. We will use the quality level in order to determine
    the number of uses we have remaining.
    """

    craft_handler_class = ConsumableCraftHandler
    default_desc = "A consumable object"

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
