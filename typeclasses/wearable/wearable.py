"""
Wearable objects. Clothing and armor. No distinction between
clothing and armor except armor will have an armor value
defined as an attribute.
"""

from typeclasses.objects import Object
from time import time
from typeclasses.containers.container import Container
from world.crafting.constants import DEFAULT_LAYER
from world.fashion.mixins import FashionableMixins
from typeclasses.exceptions import EquipError


# noinspection PyMethodMayBeStatic
# noinspection PyUnusedLocal
class Wearable(FashionableMixins, Object):
    """
    Class for wearable objects
    """
    default_desc = "A piece of clothing or armor."

    def softdelete(self):
        """Fake-deletes the object so that it can still be cancelled, is purged in weekly maintenance"""
        if self.is_worn:
            wearer = self.location
            self.set_removed()
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
        caller = kwargs.get('caller', None)
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
        self.set_removed()
        self.at_post_remove(wearer)

    def at_post_remove(self, wearer):
        """Hook called after removing succeeds."""
        return True

    # noinspection PyAttributeOutsideInit
    def wear(self, wearer, layer=None):
        """
        Puts item on the wearer.
        """
        # Assume fail exceptions are raised at_pre_wear
        self.at_pre_wear(wearer, layer=layer)
        self.set_worn()
        self.at_post_wear(wearer)

    def set_worn(self):
        self.tags.add("currently_worn")
        if self.decorative:
            self.db.worn_time = time()

    def set_removed(self):
        self.tags.remove("currently_worn")
        if self.decorative:
            self.attributes.remove("worn_time")

    def at_pre_wear(self, wearer, layer=None):
        """Hook called before wearing for any checks."""
        if self.is_worn:
            raise EquipError("already worn")
        if self.location != wearer:
            raise EquipError("misplaced")
        if layer is None:
            layer = self.default_layer
        if layer not in self.allowed_layers:
            raise EquipError("cannot be worn on that layer")
        self.slot_check(wearer, layer)

    @property
    def default_layer(self):
        try:
            return self.recipe.wearable_stats.default_layer
        except AttributeError:
            return DEFAULT_LAYER

    def slot_check(self, wearer, layer):
        slot, slot_volume = self.slot, self.slot_volume
        if slot and slot_volume:
            total = wearer.get_total_volume_for_slot_and_layer(slot, layer)
            if slot_volume + total > 100:
                raise EquipError("You are wearing too much on '%s' slot: %s/100" % (slot, total))

    def at_post_wear(self, wearer):
        """Hook called after wearing succeeds."""
        self.calc_armor()

    def calc_armor(self):
        """
        If we have crafted armor, return the value from the recipe and
        quality.
        """
        quality = self.quality_level
        recipe = self.recipe
        if not recipe:
            return self.db.armor_class or 0, self.db.penalty or 0, self.db.armor_resilience or 0
        base = recipe.baseval / 100.0
        scaling = recipe.scaling
        if scaling is None:
            scaling = (base / 10.0) or 0.2
        else:
            scaling /= 100.0
        penalty = recipe.wearable_stats.penalty / 100.0
        resilience = penalty / 3
        if quality >= 10:
            crafter = self.crafted_by
            if (recipe.level > 3) or not crafter or crafter.check_permstring("builders"):
                base += 1
        if not base:
            self.ndb.cached_armor_value = 0
            self.ndb.cached_penalty_value = penalty
            self.ndb.cached_resilience = resilience
            return self.ndb.cached_armor_value, self.ndb.cached_penalty_value, self.ndb.cached_resilience
        try:
            armor = base + (scaling * quality)
        except (TypeError, ValueError):
            armor = 0
        self.ndb.cached_armor_value = armor
        self.ndb.cached_penalty_value = penalty
        self.ndb.cached_resilience = resilience
        return armor, penalty, resilience

    def check_fashion_ready(self):
        super(Wearable, self).check_fashion_ready()
        if not self.is_worn:
            from world.fashion.exceptions import FashionError
            raise FashionError("Please wear %s before trying to model it as fashion." % self)
        return True

    @property
    def armor(self):
        # if we have no recipe or we are set to ignore it, use armor_class
        if not self.recipe or self.db.ignore_crafted:
            return self.db.armor_class
        if self.ndb.cached_armor_value is not None:
            return self.ndb.cached_armor_value
        return self.calc_armor()[0]

    @armor.setter
    def armor(self, value):
        """
        Manually sets the value of our armor, ignoring any crafting recipe we have.
        """
        self.db.armor_class = value
        self.db.ignore_crafted = True
        self.ndb.cached_armor_value = value

    @property
    def penalty(self):
        # if we have no recipe or we are set to ignore it, use penalty
        if not self.db.recipe or self.db.ignore_crafted:
            return self.db.penalty or 0
        if self.ndb.cached_penalty_value is not None:
            return self.ndb.cached_penalty_value
        return self.calc_armor()[1]

    @property
    def armor_resilience(self):
        """How hard the armor is to penetrate"""
        if not self.db.recipe or self.db.ignore_crafted:
            return 0
        if self.ndb.cached_resilience is not None:
            return self.ndb.cached_resilience
        return self.calc_armor()[2]

    @property
    def slot(self):
        """slot the armor is worn on"""
        recipe = self.recipe
        if not recipe:
            return self.db.slot
        return recipe.wearable_stats.slot

    @property
    def allowed_layers(self):
        """Layer that this item can be worn on"""
        recipe = self.recipe
        if not recipe:
            return self.db.allowed_layers or []
        return recipe.wearable_stats.allowed_layers

    @property
    def slot_volume(self):
        """how many can be worn on that slot"""
        recipe = self.recipe
        if not recipe:
            return self.db.slot_volume or 100
        return recipe.wearable_stats.slot_volume

    @property
    def is_wearable(self):
        return True

    @property
    def layer(self):
        """Returns tuple"""
        try:
            return self.equipped_details.layer
        except AttributeError:
            return None

    @property
    def is_worn(self):
        try:
            return self.equipped_details.is_worn
        except AttributeError:
            return False

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
        if self.ndb.container_reset or not self.cmdset.has_cmdset("_containerset", must_be_default=True):
            # we are resetting, or no container-cmdset was set. Create one dynamically.
            self.cmdset.add_default(self.create_container_cmdset(self), permanent=False)
            self.ndb.container_reset = False

    def calc_armor(self):
        """Wearable containers have no armor value."""
        return 0, 0, 0

    @property
    def armor(self):
        return 0
