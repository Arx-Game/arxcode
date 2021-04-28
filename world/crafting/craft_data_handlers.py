"""
Handler for hiding implementation details of data storage for a crafted object
behind an abstraction layer
"""
from django.core.exceptions import ObjectDoesNotExist
from evennia_extensions.object_extensions.item_data_handler import ItemDataHandler
from server.utils.arx_utils import CachedProperty
from world.crafting.storage_wrappers import (
    CraftingRecordWrapper,
    MaterialTypeWrapper,
    EquippedStatusWrapper,
    ArmorOverrideWrapper,
    MaskedDescriptionWrapper,
    PlaceSpotsOverrideWrapper,
    WeaponOverrideWrapper,
)
from world.crafting.validators import get_material, get_recipe, get_character


class CraftDataHandler(ItemDataHandler):
    """Encapsulates data/methods for any crafted object in game"""

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
        return string

    @CachedProperty
    def adorn_objects(self):
        """
        Returns cached dict of our adorned materials
        """
        return {ob.type: ob.amount for ob in self.obj.adorned_materials.all()}

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

    recipe = CraftingRecordWrapper(validator_func=get_recipe)
    quality_level = CraftingRecordWrapper()
    crafted_by = CraftingRecordWrapper(validator_func=get_character)

    @property
    def origin_description(self):
        found = self.obj.db.found_shardhaven
        if found:
            return "\nIt was found in %s." % found
        return None

    def add_adorn(self, material, quantity: int):
        """
        Adds an adornment to this crafted object.

        Args:
            material (CraftingMaterialType): The crafting material type that we're adding
            quantity: How much we're adding
        """
        if isinstance(material, int):
            ob, _ = self.obj.adorned_materials.get_or_create(type_id=material)
        else:
            ob, _ = self.obj.adorned_materials.get_or_create(type=material)
        ob.amount = quantity
        ob.save()
        # clear cache
        del self.adorn_objects

    def get_refine_attempts_for_character(self, crafter):
        try:
            return self.obj.crafting_record.refine_attempts.get(
                crafter=crafter
            ).num_attempts
        except ObjectDoesNotExist:
            return 0

    def set_refine_attempts_for_character(self, crafter, attempts):
        self.obj.crafting_record.set_refine_attempts(crafter, attempts)


class ConsumableDataHandler(CraftDataHandler):
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


class WearableDataHandler(CraftDataHandler):
    worn_time = EquippedStatusWrapper()
    currently_worn = EquippedStatusWrapper()
    armor_penalty = ArmorOverrideWrapper()
    armor_resilience = ArmorOverrideWrapper()
    slot_limit = ArmorOverrideWrapper()
    slot = ArmorOverrideWrapper()


class MaskDataHandler(WearableDataHandler):
    mask_desc = MaskedDescriptionWrapper("description")


class WieldableDataHandler(WearableDataHandler):
    currently_wielded = EquippedStatusWrapper()
    ready_phrase = EquippedStatusWrapper()
    attack_skill = WeaponOverrideWrapper()
    attack_stat = WeaponOverrideWrapper()
    damage_stat = WeaponOverrideWrapper()
    damage_bonus = WeaponOverrideWrapper()
    attack_type = WeaponOverrideWrapper()
    can_be_parried = WeaponOverrideWrapper()
    can_be_blocked = WeaponOverrideWrapper()
    can_be_dodged = WeaponOverrideWrapper()
    can_be_countered = WeaponOverrideWrapper()
    can_parry = WeaponOverrideWrapper()
    can_riposte = WeaponOverrideWrapper()
    difficulty_mod = WeaponOverrideWrapper()
    flat_damage_bonus = WeaponOverrideWrapper()


class PlaceDataHandler(CraftDataHandler):
    max_spots = PlaceSpotsOverrideWrapper()

    @CachedProperty
    def occupants(self):
        return [ob.character for ob in self.obj.occupying_characters.all()]

    def add_occupant(self, character):
        if character not in self.occupants:
            self.obj.occupying_characters.create(character=character)
            del self.occupants

    def remove_occupant(self, character):
        if any(self.obj.occupying_characters.filter(character=character).delete()):
            del self.occupants


class MaterialObjectDataHandler(ItemDataHandler):
    material_type = MaterialTypeWrapper(validator_func=get_material)
