from typeclasses.objects import Object as DefaultObject


class CraftingMaterialObject(DefaultObject):
    @property
    def material_info(self):
        return self.materials.first()

    @property
    def type_description(self):
        material = self.material_info
        if not material:
            return "unknown crafting material"
        return "crafting material, %s" % material.type

    def store_into(self, owner):
        material = self.material_info
        if not material:
            return

        record, _ = owner.materials.get_or_create(type=material.type)
        record.amount += material.amount
        record.save()

        self.softdelete()
