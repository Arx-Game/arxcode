"""
Disguises and Masks
"""
from typeclasses.wearable.wearable import Wearable, EquipError
from typeclasses.consumable.consumable import Consumable
from world.crafting.craft_data_handlers import MaskDataHandler
from evennia.utils.logger import log_file


class Mask(Wearable):
    """
    Wearable mask that replaces name with 'Someone wearing <short desc> mask'.
    Also grants a temp_desc. Charges equal to quality, loses a charge when worn.
    """

    item_data_class = MaskDataHandler

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
        if self.item_data.quality_level == 0:
            raise EquipError("needs repair")

    def at_post_wear(self, wearer):
        """Hook called after wearing succeeds."""
        self.log_mask(wearer)
        self.wear_mask(wearer)
        if wearer.item_data.additional_desc:
            wearer.msg(
                "{yYou currently have a +tempdesc set, which you may want to remove with +tempdesc.{n"
            )
        super(Mask, self).at_post_wear(wearer)

    def log_mask(self, wearer):
        """Logging players using masks to keep track of shennigans"""
        log_file(f"{wearer} ({wearer.id}) put on {self} ({self.id})", "player_masks.log")

    def wear_mask(self, wearer):
        """Change the visible identity of our wearer."""
        wearer.db.mask = self
        wearer.fakename = "Someone wearing %s" % self
        wearer.temp_desc = self.item_data.mask_desc

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
