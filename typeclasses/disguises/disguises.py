"""
Disguises and Masks 
"""
from typeclasses.wearable.wearable import Wearable
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
        pass
    
    def at_pre_wear(self, wearer):
        """Hook called before wearing for any checks."""
        # setting a negative quality gives someone an infinite use mask!
        if self.db.quality_level == 0:
            wearer.msg("%s seems too damaged to wear. It needs to be repaired." % self)
            return False
        return True

    def at_post_wear(self, wearer):
        """Hook called after wearing for any checks."""
        self.wear_mask(wearer)
        # we'll have mirrormasks be free
        if not self.tags.get("mirrormask"):
            # set attr if it's not set to avoid errors
            if self.db.quality_level is None:
                self.db.quality_level = 0
            # Negative quality level or one above 10 are infinite
            elif 0 < self.db.quality_level < 11:
                self.db.quality_level -= 1
        if wearer.additional_desc:
            wearer.msg("{yYou currently have a +tempdesc set, which you may want to remove or modify with +tempdesc.{n")
        return True
            
    def at_post_remove(self, wearer):
        """Hook called after removing."""
        self.attributes.remove("worn_by")
        self.remove_mask(wearer)
        return True
        
    def wear_mask(self, wearer):
        # TODO if show_alias = True, add check here for rapsheet
        # Then can don alias by putting on any mask maybe?
        gender = "Someone"
        # try:
        #     if wearer.db.gender.lower().startswith("f"):
        #         gender = "A Lady"
        #     if wearer.db.gender.lower().startswith("m"):
        #         gender = "A Man"
        # except AttributeError:
        #     pass
        wearer.db.mask = self
        wearer.fakename = "%s wearing %s" % (gender, self)
        wearer.temp_desc = self.db.maskdesc
        return
    
    def remove_mask(self, wearer):
        wearer.attributes.remove("mask")
        del wearer.fakename
        del wearer.temp_desc
        wearer.msg("%s is no longer altering your identity or description." % self)
        return
    
    
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
