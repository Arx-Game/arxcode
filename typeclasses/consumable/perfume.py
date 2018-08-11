"""
Perfume
"""

from .consumable import Consumable
from evennia.scripts.models import ScriptDB
from evennia.utils import create
from .appearance_script import AppearanceScript


class Perfume(Consumable):
    """
    Perfume.
    """

    def at_object_creation(self):
        """
        Run at Usable creation.
        """
        self.desc = "This is a pleasant, lingering scent."

    @property
    def scent_desc(self):
        return Consumable._desc_get(self)

    @Consumable.desc.getter
    def desc(self):
        return "A bottle that contains the following scent: %s" % Consumable._desc_get(self)

    @property
    def quality_prefix(self):
        recipe_id = self.db.recipe
        from world.dominion.models import CraftingRecipe
        try:
            recipe = CraftingRecipe.objects.get(id=recipe_id)
        except CraftingRecipe.DoesNotExist:
            return "{wUnknown Perfume{n:"
        return "{w%s{n:" % recipe.name

    @property
    def valid_typeclass_path(self):
        return "typeclasses.characters.Character"

    def check_target(self, target, caller):
        if target != caller:
            caller.msg("Only apply scents to yourself. Rude.")
            return False
        return super(Perfume, self).check_target(target, caller)

    # noinspection PyMethodMayBeStatic
    def use_on_target(self, target, caller):
        """
        We fetch or create a perfume script on the target character, and
        set it to have a copy of our scent_desc, which the character will
        then append to their description.
        """
        try:
            script = target.scriptdb_set.get(db_key="Appearance")
        except ScriptDB.DoesNotExist:
            script = create.create_script(AppearanceScript, obj=target)
        script.set_scent(self)
