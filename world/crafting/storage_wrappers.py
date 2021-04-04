"""
Will contain different descriptors used by the data handlers for crafting.
Each descriptor handles setting data/getting for a field in some storage object,
typically a django model.
"""
from evennia_extensions.object_extensions.storage_wrappers import StorageWrapper


class CraftingRecordWrapper(StorageWrapper):
    """Managed attribute for getting/retrieving data about object crafting record."""

    def get_storage(self, instance):
        return instance.obj.crafting_record

    def create_new_storage(self, instance):
        from world.crafting.models import CraftingRecord

        # will be saved after
        return CraftingRecord(objectdb=instance.obj)


class MaterialTypeWrapper(StorageWrapper):
    def get_storage(self, instance):
        return instance.obj.material_composition

    def create_new_storage(self, instance):
        from world.crafting.models import MaterialComposition

        return MaterialComposition(objectdb=instance.obj)


class EquippedStatusWrapper(StorageWrapper):
    def get_storage(self, instance):
        return instance.obj.equipped_status

    def create_new_storage(self, instance):
        from world.crafting.models import EquippedStatus

        return EquippedStatus(objectdb=instance.obj)


class ArmorOverrideWrapper(StorageWrapper):
    def get_storage(self, instance):
        return instance.obj.armor_override

    def create_new_storage(self, instance):
        from world.crafting.models import ArmorOverride

        return ArmorOverride(objectdb=instance.obj)


class MaskedDescriptionWrapper(StorageWrapper):
    def get_storage(self, instance):
        return instance.obj.masked_description

    def create_new_storage(self, instance):
        from world.crafting.models import MaskedDescription

        return MaskedDescription(objectdb=instance.obj)


class PlaceSpotsOverrideWrapper(StorageWrapper):
    def get_storage(self, instance):
        return instance.obj.place_spots_override

    def create_new_storage(self, instance):
        from world.crafting.models import PlaceSpotsOverride

        return PlaceSpotsOverride(objectdb=instance.obj)


class WeaponOverrideWrapper(StorageWrapper):
    def get_storage(self, instance):
        return instance.obj.weapon_override

    def create_new_storage(self, instance):
        from world.crafting.models import WeaponOverride

        return WeaponOverride(objectdb=instance.obj)
