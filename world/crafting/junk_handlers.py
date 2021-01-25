"""
Different handlers for processing junking an item
"""
from server.utils.exceptions import CommandError


class BaseJunkHandler:
    """A basic handler that allows junking an item unless it's flagged as special"""

    def __init__(self, obj):
        self.obj = obj

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
        caller.msg("You destroy %s." % self)
        self.obj.softdelete()

    @property
    def is_plot_related(self):
        if (
            "plot" in self.obj.tags.all()
            or self.obj.search_tags.all().exists()
            or self.obj.clues.all().exists()
        ):
            return True


class RefundMaterialsJunkHandler(BaseJunkHandler):
    """A handler that can give full materials back when an object is junked"""

    def __init__(self, obj):
        super().__init__(obj)
        self.craft_handler = obj

    @property
    def junkable(self):
        """A check for this object's plot connections."""
        if not self.craft_handler.recipe:
            raise AttributeError
        return not self.is_plot_related

    def do_junkout(self, caller):
        """Attempts to salvage materials from crafted item, then junks it."""
        from world.dominion.models import CraftingMaterials, CraftingMaterialType

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

        pmats = caller.player.Dominion.assets.materials
        mats = self.craft_handler.materials
        adorns = self.craft_handler.adorns
        refunded = []
        roll = get_refund_chance()
        for mat in adorns:
            cmat = CraftingMaterialType.objects.get(id=mat)
            amount = adorns[mat]
            amount = randomize_amount(amount)
            if amount:
                try:
                    pmat = pmats.get(type=cmat)
                except CraftingMaterials.DoesNotExist:
                    pmat = pmats.create(type=cmat)
                pmat.amount += amount
                pmat.save()
                refunded.append("%s %s" % (amount, cmat.name))
        for mat in mats:
            amount = mats[mat]
            if mat in adorns:
                amount -= adorns[mat]
            amount = randomize_amount(amount)
            if amount <= 0:
                continue
            cmat = CraftingMaterialType.objects.get(id=mat)
            try:
                pmat = pmats.get(type=cmat)
            except CraftingMaterials.DoesNotExist:
                pmat = pmats.create(type=cmat)
            pmat.amount += amount
            pmat.save()
            refunded.append("%s %s" % (amount, cmat.name))
        destroy_msg = "You destroy %s." % self
        if refunded:
            destroy_msg += " Salvaged materials: %s" % ", ".join(refunded)
        caller.msg(destroy_msg)
        self.obj.softdelete()
