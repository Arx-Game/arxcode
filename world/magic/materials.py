from typeclasses.bauble import Bauble


class MagicMaterial(Bauble):
    @property
    def type_description(self):
        return "alchemical material"
