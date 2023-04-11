"""
Different handlers for processing junking an item
"""
from server.utils.exceptions import CommandError

_Object = None


class BaseJunkHandler:
    """A basic handler that allows junking an item unless it's flagged as special"""

    def __init__(self, obj):
        global _Object
        if not _Object:
            from typeclasses.objects import Object as _Object
        self.obj: _Object = obj

    def junk(self, caller):
        """Checks our ability to be junked out."""

        if self.obj.location != caller:
            raise CommandError("You can only +junk objects you are holding.")
        if self.obj.contents:
            raise CommandError("It contains objects that must first be removed.")
        if not self.junkable:
            raise CommandError("This object cannot be destroyed.")
        self.do_junkout(caller)

    @property
    def junkable(self):
        """A check for this object's plot connections."""
        return not self.is_plot_related

    def do_junkout(self, caller):
        """Junks us as if we were a crafted item."""
        caller.msg("You destroy %s." % self.obj)
        self.obj.softdelete()

    @property
    def is_plot_related(self):
        if (
            "plot"
            or "heirloom"
            or "legacy" in self.obj.tags.all()
            or self.obj.search_tags.all().exists()
            or self.obj.clues.all().exists()
        ):
            return True


class RefundMaterialsJunkHandler(BaseJunkHandler):
    """A handler that can give full materials back when an object is junked"""

    def __init__(self, obj):
        super().__init__(obj)
        self.item_data = obj.item_data

    @property
    def junkable(self):
        """A check for this object's plot connections."""
        if not self.item_data.recipe:
            raise AttributeError
        return not self.is_plot_related

    def do_junkout(self, caller):
        """Attempts to salvage materials from crafted item, then junks it."""
        from world.crafting.models import CraftingMaterialType, OwnedMaterial

        def get_refund_chance():
            """Gets our chance of material refund based on a skill check"""
            from world.stats_and_skills import do_dice_check

            roll = do_dice_check(
                caller, stat="dexterity", skill="legerdemain", quiet=False
            )
            return max(roll, 1)

        def randomize_amount(amt):
            """Helper function to determine amount kept when junking"""
            from random import randint

            num_kept = 0
            for _ in range(amt):
                if randint(0, 100) <= roll:
                    num_kept += 1
            return num_kept

        pmats = caller.player.Dominion.assets.owned_materials
        mats = {}
        if self.obj.item_data.recipe:
            mats = {
                req: req.amount
                for req in self.obj.item_data.recipe.required_materials.all()
            }
        adorns = self.obj.adorned_materials.all()
        refunded = []
        roll = get_refund_chance()
        for mat in adorns:
            cmat = mat.type
            amount = mat.amount
            amount = randomize_amount(amount)
            if amount:
                try:
                    pmat = pmats.get(type=cmat)
                except OwnedMaterial.DoesNotExist:
                    pmat = pmats.create(type=cmat)
                pmat.amount += amount
                pmat.save()
                refunded.append("%s %s" % (amount, cmat.name))
        for mat in mats:
            amount = mat.amount
            amount = randomize_amount(amount)
            if amount <= 0:
                continue
            cmat = mat.type
            try:
                pmat = pmats.get(type=cmat)
            except OwnedMaterial.DoesNotExist:
                pmat = pmats.create(type=cmat)
            pmat.amount += amount
            pmat.save()
            refunded.append("%s %s" % (amount, cmat.name))
        destroy_msg = "You destroy %s." % self.obj
        if refunded:
            destroy_msg += " Salvaged materials: %s" % ", ".join(refunded)
        caller.msg(destroy_msg)
        self.obj.softdelete()
