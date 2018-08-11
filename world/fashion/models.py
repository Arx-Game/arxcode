# -*- coding: utf-8 -*-
"""
The Fashion app is for letting players have a mechanical benefit for fashion. Without
a strong mechanical benefit for fashion, players who don't care about it will tend
to protest spending money on it. Fashion is the primary mechanic for organizations
gaining prestige, which influences their economic power.
"""
from __future__ import unicode_literals

from django.db import models

from evennia.utils.idmapper.models import SharedMemoryModel


class FashionSnapshot(SharedMemoryModel):
    """
    The recorded moment when a piece of gear becomes a weapon
    of the fashionpocalypse.
    """
    ORG_FAME_DIVISOR = 2
    DESIGNER_FAME_DIVISOR = 4
    db_date_created = models.DateTimeField(auto_now_add=True)
    fashion_item = models.ForeignKey('objects.ObjectDB', related_name='fashion_snapshots',
                                     on_delete=models.SET_NULL, null=True)
    fashion_model = models.ForeignKey('dominion.PlayerOrNpc', related_name='fashion_snapshots',
                                      on_delete=models.SET_NULL, null=True)
    org = models.ForeignKey('dominion.Organization', related_name='fashion_snapshots',
                            on_delete=models.SET_NULL, null=True)
    designer = models.ForeignKey('dominion.PlayerOrNpc', related_name='designer_snapshots',
                                 on_delete=models.SET_NULL, null=True)
    fame = models.IntegerField(default=0, blank=True)

    def __str__(self):
        org_msg = "for {125%s{n " % self.org if self.org else ""
        return "Modeled by {315%s{n %son %s" % (self.fashion_model, org_msg,
                                                self.db_date_created.strftime("%Y/%m/%d"))

    def save(self, *args, **kwargs):
        """Invalidates cache on save"""
        super(FashionSnapshot, self).save(*args, **kwargs)
        self.fashion_item.invalidate_snapshots_cache()

    def delete(self, *args, **kwargs):
        """Invalidates cache before delete"""
        self.fashion_item.invalidate_snapshots_cache()
        super(FashionSnapshot, self).delete(*args, **kwargs)

    def roll_for_fame(self):
        """
        Rolls for amount of fame the item generates, minimum 2 fame. The fashion model's social clout and
        skill check of composure + performance is made exponential to be an enormous swing in the efficacy
        of fame generated: Someone whose roll+social_clout is 50 will be hundreds of times as effective
        as someone who flubs the roll.
        """
        from world.stats_and_skills import do_dice_check
        char = self.fashion_model.player.character
        roll = do_dice_check(caller=char, stat="composure", skill="performance", difficulty=30)
        roll = pow(max((roll + char.social_clout * 3), 1), 1.5)
        percentage = max(roll/100.0, 0.01)
        level_mod = self.fashion_item.recipe.level/6.0
        percentage *= max(level_mod, 0.01)
        percentage *= max((self.fashion_item.quality_level/40.0), 0.01)
        # they get either their percentage of the item's worth, their modified roll, or 4, whichever is highest
        self.fame = max(int(self.item_worth * percentage), max(int(roll), 4))
        self.save()

    def apply_fame(self, reverse=False):
        """
        Awards full amount of fame to fashion model and a portion to the
        sponsoring Organization & the item's Designer.
        """
        mult = -1 if reverse else 1
        model_fame = self.fame * mult
        org_fame = self.org_fame * mult
        designer_fame = self.designer_fame * mult
        self.fashion_model.assets.adjust_prestige(model_fame, force=reverse)
        self.org.assets.adjust_prestige(org_fame, force=reverse)
        self.designer.assets.adjust_prestige(designer_fame, force=reverse)

    def inform_fashion_clients(self):
        """
        Informs clients when fame is earned, by using their AssetOwner method.
        """
        category = "fashion"
        msg = "fame awarded from %s modeling %s." % (self.fashion_model, self.fashion_item)
        if self.org_fame > 0:
            org_msg = "{315%d{n %s" % (self.org_fame, msg)
            self.org.assets.inform_owner(org_msg, category=category, append=True)
        if self.designer_fame > 0:
            designer_msg = "{315%d{n %s" % (self.designer_fame, msg)
            self.designer.assets.inform_owner(designer_msg, category=category, append=True)

    @property
    def fashion_mult_override(self):
        """Returns a recipe's overriding fashion multiplier, or None."""
        return self.fashion_item.recipe.resultsdict.get("fashion_mult", None)

    @property
    def fashion_mult(self):
        """
        Returns a multiplier for fashion fame based on its recipe's 'baseval'.
        Recipes with no baseval recieve a bonus to fame awarded. The awarded
        amount swiftly decreases if recipe armor/damage is over 2, unless admin
        overrides with "fashion_mult" in the recipe's 'result' field.
        """
        if self.fashion_mult_override is not None:
            return float(self.fashion_mult_override)
        recipe_base = self.fashion_item.recipe.baseval
        if not recipe_base:
            return 3.0
        elif recipe_base <= 2:
            return 1.0
        elif recipe_base == 3:
            return 0.5
        elif recipe_base == 4:
            return 0.25
        else:
            return 0.1

    @property
    def item_worth(self):
        """
        Recipe cost is affected by the multiplier before adornment costs are added.
        """
        item = self.fashion_item
        value = item.recipe.value * self.fashion_mult
        if item.adorns:
            adorns = dict(item.adorns)
            for material, quantity in adorns.items():
                value += material.value * quantity
        return int(value)

    @property
    def org_fame(self):
        """The portion of fame awarded to sponsoring org"""
        return int(self.fame/self.ORG_FAME_DIVISOR)

    @property
    def designer_fame(self):
        """The portion of fame awarded to item designer."""
        return int(self.fame/self.DESIGNER_FAME_DIVISOR)
