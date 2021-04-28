from typeclasses.objects import Object as DefaultObject


class CraftingMaterialObject(DefaultObject):
    default_material_type = None

    @property
    def material_type(self):
        return self.item_data.material_type

    @property
    def type_description(self):
        material = self.material_type
        if not material:
            return "unknown crafting material"

        return "crafting material, %s" % material.name

    def store_into(self, owner):
        if not self.item_data.quantity:
            return

        material = self.material_type
        if not material:
            return

        record, _ = owner.owned_materials.get_or_create(type=material)
        record.amount += self.item_data.quantity
        record.save()

        self.softdelete()

    @property
    def desc(self):
        msg = "Nondescript material."
        if self.material_type:
            msg = self.material_type.desc
        return msg
