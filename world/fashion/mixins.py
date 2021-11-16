"""
Fashionable Mixins
"""
from world.fashion.exceptions import FashionError
from world.fashion.models import FashionSnapshot


class FashionableMixins(object):
    """
    Handles the fashion requirements of wearable items. Requires that the object
    using the mixin is an ObjectDB/Typeclass instance.
    """

    fashion_ap_cost = 1

    def check_fashion_ready(self):
        """Raises FashionError if the object is not ready to be modeled."""
        if self.modeled_by:
            raise FashionError("%s has already been used to model fashion." % self)
        if not self.crafted_by_mortals:
            raise FashionError(
                "%s was wrought by no mortal hand, and from it no mortal fame can be earned."
                % self
            )
        return True

    def model_for_fashion(self, player, org, outfit=None):
        """Our spine:
        Checks the item's availability as well as the model's. Makes snapshot object
        and has it calculate fame. Then fame is awarded and a record of it made.
        """
        self.check_fashion_ready()
        if not outfit and not player.pay_action_points(self.fashion_ap_cost):
            msg = "It costs %d AP to model %s; you do not have enough energy." % (
                self.fashion_ap_cost,
                self,
            )
            raise FashionError(msg)
        snapshot = FashionSnapshot.objects.create(
            fashion_model=player.Dominion,
            fashion_item=self,
            org=org,
            designer=self.designer.Dominion,
            outfit=outfit,
        )
        snapshot.roll_for_fame()
        snapshot.apply_fame()
        snapshot.inform_fashion_clients()
        return snapshot.fame

    def return_appearance(
        self, pobject, detailed=False, format_desc=False, show_contents=True
    ):
        """Override of return appearance to add our modeled-by snapshots"""
        ret = super(FashionableMixins, self).return_appearance(
            pobject,
            detailed=detailed,
            format_desc=format_desc,
            show_contents=show_contents,
        )
        mod = self.modeled_by
        if mod:
            ret += "\n%s" % mod
        return ret

    def invalidate_snapshots_cache(self):
        """Clears cached snapshots"""
        self.ndb.snapshots_cache = None

    @property
    def item_worth(self):
        """
        Recipe value is affected by the multiplier before adornment costs are added.
        """
        from world.crafting.models import AdornedMaterial

        if not self.crafted_by_mortals:
            return 0
        value = self.item_data.recipe.value * self.fashion_mult
        value += AdornedMaterial.objects.filter(objectdb=self).total_value()
        return int(value)

    @property
    def fashion_mult(self):
        """
        Returns a multiplier for fashion fame based on its recipe's 'baseval'.
        Recipes with no baseval recieve a bonus to fame awarded. The awarded
        amount swiftly decreases if recipe armor/damage is over 2, unless admin
        overrides with "fashion_mult" in the recipe's 'result' field.
        """
        if self.fashion_mult_override is not None:
            return float(self.fashion_mult_override)
        recipe_base = self.item_data.recipe.base_value
        if not recipe_base:
            return 3.0
        elif recipe_base <= 2:
            return 2.0
        elif recipe_base == 3:
            return 1.5
        elif recipe_base == 4:
            return 1.25
        else:
            return 1.0

    @property
    def fashion_mult_override(self):
        """Returns a recipe's overriding fashion multiplier, or None."""
        return self.item_data.recipe.fashion_mult

    @property
    def modeled_by(self):
        """
        Sets snapshots_cache to be a list of snapshots. Returns their display
        on separate lines, or empty string.
        """
        msg = ""
        if self.ndb.snapshots_cache is None:
            self.ndb.snapshots_cache = list(self.fashion_snapshots.all())
        snapshots = self.ndb.snapshots_cache
        if snapshots:
            msg += "\n".join([ob.display for ob in snapshots])
        return msg

    @property
    def designer(self):
        """Returns the item's creator player"""
        creator = self.item_data.crafted_by
        if creator and hasattr(creator, "player_ob"):
            return self.item_data.crafted_by.player_ob

    @property
    def crafted_by_mortals(self):
        return bool(
            self.item_data.recipe
            and self.designer
            and not self.designer.check_permstring("builders")
        )
