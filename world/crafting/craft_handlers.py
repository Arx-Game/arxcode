"""
Handler for hiding implementation details of data storage for a crafted object
behind an abstraction layer
"""


class CraftHandler:
    """Encapsulates data/methods for any crafted object in game"""

    def __init__(self, obj):
        self.obj = obj

    def get_crafting_desc(self):
        """
        :type self: ObjectDB
        """
        string = ""
        adorns = self.adorn_objects
        # adorns are a dict of the ID of the crafting material type to amount
        if adorns:
            adorn_strs = ["%s %s" % (amt, mat.name) for mat, amt in adorns.items()]
            string += "\nAdornments: %s" % ", ".join(adorn_strs)
        # recipe is an integer matching the CraftingRecipe ID
        if hasattr(self.obj, "type_description") and self.obj.type_description:
            from server.utils.arx_utils import a_or_an

            td = self.obj.type_description
            part = a_or_an(td)
            string += "\nIt is %s %s." % (part, td)
        if self.quality_level:
            string += self.get_quality_appearance()
        if hasattr(self, "origin_description") and self.origin_description:
            string += self.origin_description
        if self.translation:
            string += "\nIt contains script in a foreign tongue."
        # signed_by is a crafter's character object
        signed = self.signed_by
        if signed:
            string += "\n%s" % (signed.crafter_signature or "")
        return string

    @property
    def adorn_objects(self):
        """
        Returns a dict of crafting materials we have.

        :type self: ObjectDB
            Returns:
                ret (dict): dict of crafting materials as keys to amt

        SharedMemoryModel causes all .get by ID to be cached inside the class,
        so these queries will only hit the database once. After that, we're just
        building a dict so it'll be insignificant.
        """
        from world.dominion.models import CraftingMaterialType

        ret = {}
        adorns = self.adorns
        for adorn_id in adorns:
            if isinstance(adorn_id, CraftingMaterialType):
                mat = adorn_id
                amt = self.obj.db.adorns.pop(adorn_id)
                self.obj.db.adorns[adorn_id.id] = amt
            else:
                try:
                    mat = CraftingMaterialType.objects.get(id=adorn_id)
                except CraftingMaterialType.DoesNotExist:
                    continue
            ret[mat] = adorns[adorn_id]
        return ret

    @property
    def adorns(self):
        return self.obj.db.adorns or {}

    @adorns.setter
    def adorns(self, value):
        self.obj.db.adorns = value

    @property
    def materials(self):
        return self.obj.db.materials or {}

    @materials.setter
    def materials(self, value):
        self.obj.db.materials = value

    def get_quality_appearance(self):
        """
        :type self: ObjectDB
        :return str:
        """
        if self.quality_level < 0:
            return ""
        from commands.base_commands.crafting import QUALITY_LEVELS

        qual = min(self.quality_level, 11)
        qual = QUALITY_LEVELS.get(qual, "average")
        return "\nIts level of craftsmanship is %s." % qual

    @property
    def recipe(self):
        """
        Gets the crafting recipe used to create us if one exists.

        :type self: ObjectDB
        Returns:
            The crafting recipe used to create this object.
        """
        if self.obj.db.recipe:
            from world.dominion.models import CraftingRecipe

            try:
                recipe = CraftingRecipe.objects.get(id=self.obj.db.recipe)
                return recipe
            except CraftingRecipe.DoesNotExist:
                pass

    @property
    def translation(self):
        return self.obj.db.translation or {}

    @translation.setter
    def translation(self, value):
        self.obj.db.translation = value

    @recipe.setter
    def recipe(self, value):
        self.obj.db.recipe = value

    @property
    def resultsdict(self):
        return self.recipe.resultsdict

    @property
    def quality_level(self):
        return self.obj.db.quality_level or 0

    @quality_level.setter
    def quality_level(self, value):
        self.obj.db.quality_level = value

    @property
    def crafted_by(self):
        return self.obj.db.crafted_by

    @crafted_by.setter
    def crafted_by(self, value):
        self.obj.db.crafted_by = value

    @property
    def signed_by(self):
        return self.obj.db.signed_by

    @signed_by.setter
    def signed_by(self, value):
        self.obj.db.signed_by = value

    @property
    def origin_description(self):
        if self.obj.db.found_shardhaven:
            return "\nIt was found in %s." % self.obj.db.found_shardhaven
        return None

    def add_adorn(self, material, quantity):
        """
        Adds an adornment to this crafted object.

        Args:
            material: The crafting material type that we're adding
            quantity: How much we're adding
        """
        adorns = dict(self.obj.db.adorns or {})
        amt = adorns.get(material.id, 0)
        adorns[material.id] = amt + quantity
        self.adorns = adorns

    def get_refine_attempts_for_character(self, crafter):
        refine_attempts = crafter.db.refine_attempts or {}
        return refine_attempts.get(self.obj.id, 0)

    def set_refine_attempts_for_character(self, crafter, attempts):
        refine_attempts = dict(crafter.db.refine_attempts or {})
        refine_attempts[self.obj.id] = attempts
        crafter.db.refine_attempts = refine_attempts


class ConsumableCraftHandler(CraftHandler):
    def get_quality_appearance(self):
        if self.charges >= 0:
            msg = "\nIt has %s uses remaining." % self.charges
        else:
            msg = "\nIt has infinite uses."
        msg += " It can be used with the {wuse{n command."
        return msg

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
        return self.quality_level

    @charges.setter
    def charges(self, val):
        self.quality_level = val


class WearableCraftHandler(CraftHandler):
    @property
    def worn_time(self):
        return self.obj.db.worn_time or 0

    @worn_time.setter
    def worn_time(self, value):
        self.obj.db.worn_time = value

    @property
    def currently_worn(self):
        return self.obj.db.currently_worn

    @currently_worn.setter
    def currently_worn(self, value):
        self.obj.db.currently_worn = value


class MaskCraftHandler(WearableCraftHandler):
    @property
    def mask_desc(self):
        return self.obj.db.maskdesc

    @mask_desc.setter
    def mask_desc(self, value):
        self.obj.db.maskdesc = value
