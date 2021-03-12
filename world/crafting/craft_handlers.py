"""
Handler for hiding implementation details of data storage for a crafted object
behind an abstraction layer
"""


def get_storage_prop(attr_name, default=None):
    """Helper function to create a property with closures of the given values we provide."""

    def get_func(self):
        return self.get_db_or_default(attr_name, default)

    def set_func(self, value):
        self.set_db_value(attr_name, value)

    return property(get_func, set_func)


class CraftHandler:
    """Encapsulates data/methods for any crafted object in game"""

    def __init__(self, obj):
        self.obj = obj

    def get_db_or_default(self, attr, default=None):
        """
        Gets a value from AttributeHolder if it exists. If not, we'll check
        for a default value as an attribute on the object, or return a default
        passed to the function.
        Args:
            attr (str): The name of the attribute
            default: The default value to be returned if the attribute doesn't exist

        Returns:
            The value of the attribute or the default
        """
        val = self.obj.attributes.get(attr)
        if val is not None:
            return val
        # default values are in the form of default_<attrname>,
        # for example: "attack_speed" -> "default_attack_speed"
        default_attr_name = f"default_{attr}"
        return getattr(self.obj, default_attr_name, default)

    def set_db_value(self, attr, value):
        self.obj.attributes.add(attr, value)

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
        if self.origin_description:
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

    adorns = get_storage_prop("adorns", {})
    materials = get_storage_prop("materials", {})

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
        recipe_pk = self.get_db_or_default("recipe")
        if recipe_pk:
            from world.dominion.models import CraftingRecipe

            try:
                recipe = CraftingRecipe.objects.get(id=recipe_pk)
                return recipe
            except CraftingRecipe.DoesNotExist:
                pass

    translation = get_storage_prop("translation", {})

    @recipe.setter
    def recipe(self, value):
        self.set_db_value("recipe", value)

    @property
    def resultsdict(self):
        return self.recipe.resultsdict

    quality_level = get_storage_prop("quality_level", 0)

    crafted_by = get_storage_prop("crafted_by")

    signed_by = get_storage_prop("signed_by")

    @property
    def origin_description(self):
        found = self.get_db_or_default("found_shardhaven")
        if found:
            return "\nIt was found in %s." % found
        return None

    def add_adorn(self, material, quantity):
        """
        Adds an adornment to this crafted object.

        Args:
            material: The crafting material type that we're adding
            quantity: How much we're adding
        """
        adorns = dict(self.adorns)
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
    worn_time = get_storage_prop("worn_time", 0)
    currently_worn = get_storage_prop("currently_worn", False)


class MaskCraftHandler(WearableCraftHandler):
    mask_desc = get_storage_prop("maskdesc")


class WieldableCraftHandler(WearableCraftHandler):
    attack_skill = get_storage_prop("attack_skill", "medium wpn")
    attack_stat = get_storage_prop("attack_stat", "dexterity")
    currently_wielded = get_storage_prop("currently_wielded", False)
    damage_stat = get_storage_prop("damage_stat", "strength")
    damage_bonus = get_storage_prop("damage_bonus", 1)
    attack_type = get_storage_prop("attack_type", "melee")
    can_be_parried = get_storage_prop("can_be_parried", True)
    can_be_blocked = get_storage_prop("can_be_blocked", True)
    can_be_dodged = get_storage_prop("can_be_dodged", True)
    can_be_countered = get_storage_prop("can_be_countered", True)
    can_parry = get_storage_prop("can_parry", True)
    can_riposte = get_storage_prop("can_riposte", True)
    difficulty_mod = get_storage_prop("difficulty_mod", 0)
