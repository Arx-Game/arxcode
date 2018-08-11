"""
Wearable objects. Clothing and armor. No distinction between
clothing and armor except armor will have an armor value
defined as an attribute.

is_wearable boolean is the check to see if we're a wearable
object. currently_worn is a boolean saying our worn state - True if being worn,
False if not worn.
"""

from typeclasses.objects import Object
from time import time
from typeclasses.containers.container import Container
from world.fashion.mixins import FashionableMixins


# noinspection PyMethodMayBeStatic
# noinspection PyUnusedLocal
class Wearable(FashionableMixins, Object):
    """
    Class for wearable objects
    """
    def at_object_creation(self):
        """
        Run at Wearable creation.
        """
        self.db.currently_worn = False
        self.db.desc = "A piece of clothing or armor."
        self.db.armor_class = 0
        self.at_init()

    def remove(self, wearer):
        """
        Takes off the armor
        """
        if not self.at_pre_remove(wearer):
            return False
        self.db.currently_worn = False
        self.at_post_remove(wearer)
        return True

    def softdelete(self):
        """Fake-deletes the object so that it can still be cancelled, is purged in weekly maintenance"""
        wearer = self.location
        super(Wearable, self).softdelete()
        self.db.currently_worn = False
        self.at_post_remove(wearer)

    # noinspection PyAttributeOutsideInit
    def wear(self, wearer):
        """
        Puts item on the wearer
        """
        # Assume any fail messages are written in at_pre_wear
        if not self.at_pre_wear(wearer):
            return False
        self.db.currently_worn = True
        if self.location != wearer:
            self.location = wearer
        self.db.worn_time = time()
        self.calc_armor()
        self.at_post_wear(wearer)
        return True

    def at_before_move(self, destination, **kwargs):
        """Checks if the object can be moved"""
        caller = kwargs.get('caller', None)
        if caller and self.db.currently_worn:
            caller.msg("%s is currently worn and cannot be moved." % self)
            return False
        return super(Wearable, self).at_before_move(destination, **kwargs)

    def at_after_move(self, source_location, **kwargs):
        """If new location is not our wearer, remove."""
        location = self.location
        wearer = source_location
        if self.db.currently_worn and location != wearer:
            self.remove(wearer)

    def at_pre_wear(self, wearer):
        """Hook called before wearing for any checks."""
        return True

    def at_post_wear(self, wearer):
        """Hook called after wearing for any checks."""
        return True

    def at_pre_remove(self, wearer):
        """Hook called before removing."""
        return True

    def at_post_remove(self, wearer):
        """Hook called after removing."""
        self.attributes.remove("worn_by")
        return True

    def calc_armor(self):
        """
        If we have crafted armor, return the value from the recipe and
        quality.
        """
        quality = self.quality_level
        recipe_id = self.db.recipe
        from world.dominion.models import CraftingRecipe
        try:
            recipe = CraftingRecipe.objects.get(id=recipe_id)
        except CraftingRecipe.DoesNotExist:
            return self.db.armor_class or 0, self.db.penalty or 0, self.db.armor_resilience or 0
        base = float(recipe.resultsdict.get("baseval", 0.0))
        scaling = float(recipe.resultsdict.get("scaling", (base/10.0) or 0.2))
        penalty = float(recipe.resultsdict.get("penalty", 0.0))
        resilience = penalty / 3
        if quality >= 10:
            crafter = self.db.crafted_by
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
        self.ndb.purported_value = armor
        if self.db.forgery_penalty:
            try:
                armor /= self.db.forgery_penalty
            except (ValueError, TypeError):
                armor = 0
        self.ndb.cached_armor_value = armor
        self.ndb.cached_penalty_value = penalty
        self.ndb.cached_resilience = resilience
        return armor, penalty, resilience

    def _get_armor(self):
        # if we have no recipe or we are set to ignore it, use armor_class
        if not self.db.recipe or self.db.ignore_crafted:
            return self.db.armor_class
        if self.ndb.cached_armor_value is not None:
            return self.ndb.cached_armor_value
        return self.calc_armor()[0]

    def _set_armor(self, value):
        """
        Manually sets the value of our armor, ignoring any crafting recipe we have.
        """
        self.db.armor_class = value
        self.db.ignore_crafted = True
        self.ndb.cached_armor_value = value

    armor = property(_get_armor, _set_armor)

    def _get_penalty(self):
        # if we have no recipe or we are set to ignore it, use penalty
        if not self.db.recipe or self.db.ignore_crafted:
            return self.db.penalty or 0
        if self.ndb.cached_penalty_value is not None:
            return self.ndb.cached_penalty_value
        return self.calc_armor()[1]
    penalty = property(_get_penalty)

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
        return recipe.resultsdict.get("slot", None)

    @property
    def slot_limit(self):
        """how many can be worn on that slot"""
        recipe = self.recipe
        if not recipe:
            return self.db.slot_limit or 0
        try:
            return int(recipe.resultsdict.get("slot_limit", 1))
        except (TypeError, ValueError):
            return 1

    def check_fashion_ready(self):
        super(Wearable, self).check_fashion_ready()
        if not self.db.currently_worn:
            from server.utils.exceptions import FashionError
            raise FashionError("Please wear %s before trying to model it as fashion." % self)
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

    def _get_armor(self):
        return 0

    def _calc_armor(self):
        return
    armor = property(_get_armor)
