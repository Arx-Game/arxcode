"""
Disguises and Masks
"""
from typeclasses.wearable.wearable import Wearable, EquipError
from typeclasses.consumable.consumable import Consumable


class Mask(Wearable):
    """
    Wearable mask that replaces name with 'Someone wearing <short desc> mask'.
    Also grants a temp_desc. Charges equal to quality, loses a charge when worn.
    """
    def at_object_creation(self):
        """
        Run at Wearable creation.
        """
        self.is_worn = False

    def at_post_remove(self, wearer):
        """Hook called after removing succeeds."""
        self.remove_mask(wearer)
        super(Mask, self).at_post_remove(wearer)

    def at_pre_wear(self, wearer):
        """Hook called before wearing for any checks."""
        super(Mask, self).at_pre_wear(wearer)
        if self.db.quality_level == 0:
            raise EquipError("needs repair")

    def at_post_wear(self, wearer):
        """Hook called after wearing succeeds."""
        self.wear_mask(wearer)
        self.degrade_mask()
        if wearer.additional_desc:
            wearer.msg("{yYou currently have a +tempdesc set, which you may want to remove with +tempdesc.{n")
        super(Mask, self).at_post_wear(wearer)

    def degrade_mask(self):
        """Mirrormasks and GM masks don't need repairs, but others will."""
        if not self.tags.get("mirrormask"):
            # set attr if it's not set to avoid errors
            if self.db.quality_level is None:
                self.db.quality_level = 0
            # Negative quality level or above 10 are infinite-use
            elif 0 < self.db.quality_level < 11:
                self.db.quality_level -= 1

    def wear_mask(self, wearer):
        """Change the visible identity of our wearer."""
        wearer.db.mask = self
        wearer.fakename = "Someone wearing %s" % self
        wearer.temp_desc = self.db.maskdesc

    def remove_mask(self, wearer):
        """Restore the visible identity of our wearer."""
        wearer.attributes.remove("mask")
        del wearer.fakename
        del wearer.temp_desc
        wearer.msg("%s is no longer altering your identity or description." % self)


class DisguiseKit(Consumable):
    """
    morestoof
    """
    def check_target(self, target, caller):
        """
        Determines if a target is valid.
        """
        from evennia.utils.utils import inherits_from
        return inherits_from(target, self.valid_typeclass_path)
