from typeclasses.objects import Object as DefaultObject
from .models import CraftingMaterialType, CraftingMaterials


class CraftingMaterialObject(DefaultObject):

    @property
    def material_type(self):
        if not self.db.material_type:
            return None
        try:
            material = CraftingMaterialType.objects.get(id=self.db.material_type)
            return material
        except (CraftingMaterialType.DoesNotExist, CraftingMaterialType.MultipleObjectsReturned):
            return None

    @property
    def type_description(self):
        material = self.material_type
        if not material:
            return "unknown crafting material"

        return "crafting material, %s" % material.name

    def store_into(self, owner):
        if not self.db.quantity:
            return

        material = self.db.material_type
        if not material:
            return

        material_records = owner.materials.filter(type=material)
        if material_records.count() == 0:
            record = CraftingMaterials(type=material, amount=self.db.quantity, owner=owner)
            record.save()
        else:
            record = material_records.all().first()
            record.amount = record.amount + self.db.quantity
            record.save()

        self.softdelete()
