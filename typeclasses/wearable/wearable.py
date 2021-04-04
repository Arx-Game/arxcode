"""
Wearable objects. Clothing and armor. No distinction between
clothing and armor except armor will have an armor value
defined as an attribute.
"""

from typeclasses.objects import Object
from time import time
from typeclasses.containers.container import Container
from world.fashion.mixins import FashionableMixins
from typeclasses.exceptions import EquipError
from world.crafting.craft_data_handlers import WearableDataHandler


# noinspection PyMethodMayBeStatic
# noinspection PyUnusedLocal
class Wearable(FashionableMixins, Object):
    """
    Class for wearable objects
    """

    item_data_class = WearableDataHandler

    default_desc = "A piece of clothing or armor."
    baseval_scaling_divisor = 10.0
    default_scaling = 0.2
    default_currently_worn = False
    default_worn_time = 0.0

    def at_object_creation(self):
        """
        Run at Wearable creation.
        """
        self.is_worn = False
        self.at_init()

    def softdelete(self):
        """Fake-deletes the object so that it can still be cancelled, is purged in weekly maintenance"""
        if self.is_worn:
            wearer = self.location
            self.is_worn = False
            self.at_post_remove(wearer)
        modi = self.modusornamenta_set.all()
        for mo in modi:
            outfit = mo.fashion_outfit
            mo.delete()
            if outfit.pk:
                outfit.invalidate_outfit_caches()
                outfit.check_existence()
        self.invalidate_snapshots_cache()
        super(Wearable, self).softdelete()

    def at_before_move(self, destination, **kwargs):
        """Checks if the object can be moved"""
        caller = kwargs.get("caller", None)
        if caller and self.is_worn:
            caller.msg("%s is currently worn and cannot be moved." % self)
            return False
        return super(Wearable, self).at_before_move(destination, **kwargs)

    def at_after_move(self, source_location, **kwargs):
        """If new location is not our wearer, remove."""
        if self.is_worn and self.location != source_location:
            self.remove(source_location)
        super(Wearable, self).at_after_move(source_location, **kwargs)

    def remove(self, wearer):
        """
        Takes off the armor
        """
        if not self.is_worn:
            raise EquipError("not equipped")
        self.is_worn = False
        self.at_post_remove(wearer)

    def at_post_remove(self, wearer):
        """Hook called after removing succeeds."""
        return True

    # noinspection PyAttributeOutsideInit
    def wear(self, wearer):
        """
        Puts item on the wearer.
        """
        # Assume fail exceptions are raised at_pre_wear
        self.at_pre_wear(wearer)
        self.is_worn = True
        if self.decorative:
            self.item_data.worn_time = time()
        self.at_post_wear(wearer)

    def at_pre_wear(self, wearer):
        """Hook called before wearing for any checks."""
        if self.is_worn:
            raise EquipError("already worn")
        if self.location != wearer:
            raise EquipError("misplaced")
        self.slot_check(wearer)

    def slot_check(self, wearer):
        slot, slot_limit = self.item_data.slot, self.item_data.slot_limit
        if slot and slot_limit:
            worn = [ob for ob in wearer.worn if ob.item_data.slot == slot]
            if len(worn) >= slot_limit:
                raise EquipError(f"{slot} slot full. Worn there: {worn}")

    def at_post_wear(self, wearer):
        """Hook called after wearing succeeds."""
        return True

    @property
    def modified_baseval(self):
        recipe = self.item_data.recipe
        base = float(recipe.base_value)
        if self.item_data.quality_level >= 10:
            crafter = self.item_data.crafted_by
            if (
                (recipe.level > 3)
                or not crafter
                or crafter.check_permstring("builders")
            ):
                base += 1
        return base

    @property
    def quality_scaling(self):
        recipe = self.item_data.recipe
        return float(
            recipe.scaling
            or (self.modified_baseval / self.baseval_scaling_divisor)
            or self.default_scaling
        )

    @property
    def default_penalty(self):
        if self.item_data.recipe:
            return float(self.item_data.recipe.armor_penalty)
        return 0

    @property
    def default_armor_resilience(self):
        return self.item_data.penalty / 3

    def check_fashion_ready(self):
        super(Wearable, self).check_fashion_ready()
        if not self.is_worn:
            from world.fashion.exceptions import FashionError

            raise FashionError(
                "Please wear %s before trying to model it as fashion." % self
            )
        return True

    @property
    def armor(self):
        # if we have no recipe or we are set to ignore it, 0
        if not self.item_data.recipe:
            return 0
        return self.modified_baseval + (
            self.quality_scaling * self.item_data.quality_level
        )

    @property
    def default_slot(self):
        """slot the armor is worn on"""
        recipe = self.item_data.recipe
        if not recipe:
            return ""
        return recipe.slot

    @property
    def default_slot_limit(self):
        """how many can be worn on that slot"""
        recipe = self.item_data.recipe
        if not recipe:
            return 1
        try:
            return recipe.slot_limit
        except (TypeError, ValueError):
            return 1

    @property
    def is_wearable(self):
        return True

    @property
    def is_worn(self):
        return self.item_data.currently_worn

    @is_worn.setter
    def is_worn(self, bull):
        """Bool luvs u"""
        self.item_data.currently_worn = bull

    @property
    def is_equipped(self):
        """shared property just for checking worn/wielded/otherwise-used status."""
        return self.is_worn

    @property
    def decorative(self):
        """Armor and clothing is always decorative."""
        return True


# noinspection PyMethodMayBeStatic
class WearableContainer(Wearable, Container):
    """Combines Wearable and Container for backpacks, etc"""

    def at_object_creation(self):
        """Creates the object, calls both superclasses"""
        Wearable.at_object_creation(self)
        Container.at_object_creation(self)

    def at_cmdset_get(self, **kwargs):
        """
        Called when the cmdset is requested from this object, just before the
        cmdset is actually extracted. If no container-cmdset is cached, create
        it now.
        """
        if self.ndb.container_reset or not self.cmdset.has_cmdset(
            "_containerset", must_be_default=True
        ):
            # we are resetting, or no container-cmdset was set. Create one dynamically.
            self.cmdset.add_default(self.create_container_cmdset(self), permanent=False)
            self.ndb.container_reset = False

    @property
    def armor(self):
        return 0
