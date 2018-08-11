"""
Fashionable Mixins
"""
from server.utils.exceptions import FashionError
from .models import FashionSnapshot


class FashionableMixins(object):
    """
    Handles the fashion requirements of wearable items. Requires that the object
    using the mixin is an ObjectDB/Typeclass instance.
    """
    fashion_ap_cost = 1

    def check_fashion_ready(self):
        """Raises FashionError if the object is not ready to be modeled."""
        if self.modeled_by:
            # If someday we wanna reuse items in fashion, change this check.
            raise FashionError("%s has already been used to model fashion." % self)
        try:
            if not self.db.recipe or self.designer.check_permstring("builders"):
                raise AttributeError
        except AttributeError:
            raise FashionError("%s was wrought by no mortal hand, and from it no mortal fame can be earned." % self)
        return True

    def model_for_fashion(self, player, org):
        """ Our spine:
        Checks the item's availability as well as the model's. Makes snapshot object
        and has it calculate fame. Then fame is awarded and a record of it made.
        """
        self.check_fashion_ready()
        if not player.pay_action_points(self.fashion_ap_cost):
            raise FashionError("You cannot afford the %d AP cost to model." % self.fashion_ap_cost)
        snapshot = FashionSnapshot.objects.create(fashion_model=player.Dominion, fashion_item=self, org=org,
                                                  designer=self.designer.Dominion)
        snapshot.roll_for_fame()
        snapshot.apply_fame()
        snapshot.inform_fashion_clients()
        return snapshot.fame

    @property
    def designer(self):
        """Returns the item's creator player"""
        return self.db.crafted_by.player_ob

    @property
    def modeled_by(self):
        """Sets snapshots_cache to be a list of snapshots. Returns their strings on separate lines, or empty string."""
        msg = ""
        if self.ndb.snapshots_cache is None:
            self.ndb.snapshots_cache = list(self.fashion_snapshots.all())
        snapshots = self.ndb.snapshots_cache
        msg += "\n".join([str(ob) for ob in snapshots])
        return msg

    def invalidate_snapshots_cache(self):
        """Clears cached snapshots"""
        self.ndb.snapshots_cache = None

    def return_appearance(self, pobject, detailed=False, format_desc=False,
                          show_contents=True):
        """Override of return appearance to add our modeled-by snapshots"""
        ret = super(FashionableMixins, self).return_appearance(pobject, detailed=detailed, format_desc=format_desc,
                                                               show_contents=show_contents)
        mod = self.modeled_by
        if mod:
            ret += "\n%s." % mod
        return ret
