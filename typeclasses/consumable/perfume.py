"""
Perfume
"""

from evennia.scripts.models import ScriptDB
from evennia.utils import create
from typeclasses.consumable.consumable import Consumable
from typeclasses.consumable.appearance_script import AppearanceScript


class Perfume(Consumable):
    """
    Perfume.
    """

    default_desc = "This is a pleasant, lingering scent."

    @property
    def scent_desc(self):
        return super(Perfume, self).desc

    @property
    def desc(self):
        return "A bottle that contains the following scent: %s" % self.scent_desc

    @desc.setter
    def desc(self, value):
        self.db.desc = value

    @property
    def quality_prefix(self):
        recipe = self.item_data.recipe
        try:
            return "{w%s{n:" % recipe.name
        except AttributeError:
            return "{wUnknown Perfume{n:"

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
