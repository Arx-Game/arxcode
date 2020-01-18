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
from world.fashion.exceptions import FashionError
from typeclasses.exceptions import EquipError
from typeclasses.scripts.combat.combat_settings import CombatError


class FashionCommonMixins(SharedMemoryModel):
    """Abstract parent with common fashion methods"""
    class Meta:
        abstract = True

    BUZZ_TYPES = ("little", "modest", "decent", "exceptional", "momentous", "legendary", "world-shaking")
    COLOR_TYPES = ("{n", "{355", "{453", "{542", "{530", "{520", "{510")
    # Emits use this %s order: fashion model, item/outfit, org, buzz_type
    EMIT_TYPES = (
        "Despite efforts made by %s, modeling %s on behalf of %s attracts %s notice.",
        "When %s models %s on behalf of %s, it gains %s attention from admiring onlookers.",
        "%s models %s on behalf of %s, gaining a %s number of admirers and significant compliments.",
        "With talented modeling, %s displays %s around Arx, garnering flattering conversation and " +
        "murmurs throughout the city about the fine choices made by %s for sponsoring someone with such %s taste.",
        "As %s models %s around Arx, word spreads like wildfire over the city about their incredible fashion " +
        "choices, attracting attention even beyond the city and gaining %s %s acclaim as well.",
        "It's more than just fashion when %s shows off %s around Arx. Resonating with the people of Arvum, it " +
        "becomes a statement on contemporary culture and the profound effect that %s has upon it - a %s event " +
        "they'll be discussing for years to come.",
        "Across Arvum and beyond, all the world hears about %s modeling %s. History will remember the abstruse " +
        "impact that %s had upon fashion itself, on this %s occasion."
        )
    BUZZIES = list(zip(BUZZ_TYPES, COLOR_TYPES, EMIT_TYPES))

    @staticmethod
    def granulate_fame(fame):
        buzz_level = 0
        if fame <= 100:
            pass
        elif fame <= 1000:
            buzz_level = 1
        elif fame <= 10000:
            buzz_level = 2
        elif fame <= 100000:
            buzz_level = 3
        elif fame <= 1000000:
            buzz_level = 4
        elif fame <= 10000000:
            buzz_level = 5
        else:
            buzz_level = 6
        return buzz_level

    def get_buzz_word(self, fame):
        """Returns a colorized buzz term based on the amount of fame."""
        buzzy = self.BUZZIES[self.granulate_fame(fame)]
        return buzzy[1] + buzzy[0] + "{n"

    def get_model_msg(self, fashion_model, org, date, fame):
        """
        Returns a string summary about the modeling of an outfit or item,
        how much buzz it garnered, and the date it was modeled.
            Args:
                fashion_model:  PlayerOrNpc object
                org:            organization
                date:           datetime
                fame:           integer
        """
        punctuation = "." if self.granulate_fame(fame) < 3 else "!"
        msg = "Modeled by {315%s{n for {125%s{n, " % (fashion_model, org)
        msg += "generating %s buzz " % self.get_buzz_word(fame)
        msg += "on %s%s" % (date.strftime("%Y/%m/%d"), punctuation)
        return msg

    @classmethod
    def get_emit_msg(cls, fashion_model, thing, org, fame):
        """
        Returns the string a room sees when the fashionista models their item
        or outfit. Higher impacts notify staff as well.
            Args:
                fashion_model:  player/account object
                thing:          an item or an outfit
                org:            organization
                fame:           integer
        String interpolation is specific order, eg: "Despite efforts made by
        <name>, modeling <item> on behalf of <org> attracts <adjective> notice."
        Order: fashion model, item/outfit, org, buzz_type (based on fame)
        """
        buzz_level = cls.granulate_fame(fame)
        buzzy = cls.BUZZIES[buzz_level]
        color = buzzy[1]
        diva = str(fashion_model)
        thing = "'%s%s'" % (str(thing), color)
        msg = color + "[Fashion] "
        msg += buzzy[2] % (diva, thing, org, buzzy[0])
        if buzz_level > 4:
            from server.utils.arx_utils import inform_staff
            inform_staff(msg)
        return msg


class FashionOutfit(FashionCommonMixins):
    """
    A collection of wearable and wieldable items that all fit on a character
    at the same time.
    """
    FAME_CAP = 5000000
    name = models.CharField(max_length=80, db_index=True)
    owner = models.ForeignKey('dominion.PlayerOrNpc', related_name='fashion_outfits', on_delete=models.CASCADE)
    fashion_items = models.ManyToManyField('objects.ObjectDB', through='ModusOrnamenta', blank=True)
    db_date_created = models.DateTimeField(auto_now_add=True)
    archived = models.BooleanField(default=False)
    # TODO: foreignkey to @cal events!

    def __str__(self):
        return str(self.name)

    def invalidate_outfit_caches(self):
        del self.fame
        del self.model_info
        del self.list_display
        del self.modeled
        del self.weapons
        del self.apparel

    def check_existence(self):
        """Deletes this outfit if none of its items exist."""
        if not self.fashion_items.exists():
            self.owner_character.msg("Nothing remains of the outfit formerly known as '%s'." % self)
            self.delete()

    def delete(self, *args, **kwargs):
        for item in self.fashion_items.all():
            if item.pk:
                item.invalidate_snapshots_cache()
        super(FashionOutfit, self).delete(*args, **kwargs)

    def add_fashion_item(self, item, slot=None):
        """Creates the through-model for what we assume is a valid item."""
        slot = slot if slot else item.slot
        ModusOrnamenta.objects.create(fashion_outfit=self, fashion_item=item, slot=slot)

    def wear(self):
        """Tries to wear our apparel and wield our weapons. Raises EquipErrors."""
        try:
            self.owner_character.undress()
        except CombatError as err:
            raise EquipError(str(err) + "\nUndress failed. " + self.equipped_msg)
        except EquipError as err:
            pass
        wield_err, wear_err, = "", ""
        try:
            to_wield = list(self.weapons.filter(modusornamenta__slot__istartswith='primary').distinct())
            if to_wield:
                self.owner_character.equip_or_remove("wield", list(to_wield))
        except EquipError as err:
            wield_err = str(err)
        try:
            to_wear = list(self.apparel)
            sheathed = list(self.weapons.exclude(modusornamenta__slot__istartswith='primary').distinct())
            to_wear.extend(sheathed)
            if to_wear:
                self.owner_character.equip_or_remove("wear", to_wear)
        except EquipError as err:
            wear_err = str(err)
        if wield_err or wear_err:
            msg = "\n".join([ob for ob in (wield_err, wear_err, self.equipped_msg) if ob])
            raise EquipError(msg)
        else:
            self.owner_character.msg(self.equipped_msg)

    def remove(self):
        """Tries to remove all our fashion_items. Raises EquipErrors."""
        try:
            self.owner_character.equip_or_remove("remove", list(self.fashion_items.all()))
        except (CombatError, EquipError) as err:
            raise EquipError(err)

    def check_outfit_fashion_ready(self):
        """
        Checks each item for model-readiness. If any are not, an exception is
        raised showing reasons for each. User may repeat the command to model
        the remaining items, if any exist. Returns a set of valid items.
        """
        valid_items = set(self.fashion_items.all())
        skipped_items = set()
        skipped_msg = "|wPieces of this outfit cannot be modeled:|n"
        for item in valid_items:
            try:
                item.check_fashion_ready()
            except FashionError as err:
                skipped_msg += "\n- " + str(err)
                skipped_items.add(item)
        valid_items = valid_items.difference(skipped_items)
        if skipped_items and self.owner.player.ndb.outfit_model_prompt != str(self):
            skipped_msg += "\n|y"
            if valid_items:
                self.owner.player.ndb.outfit_model_prompt = str(self)
                skipped_msg += "Repeat command to model the %d remaining item(s)" % len(valid_items)
            else:
                skipped_msg += "No valid items remain! Try modeling a different outfit"
            raise FashionError(skipped_msg + ".|n")
        self.owner.player.ndb.outfit_model_prompt = None
        return valid_items

    def model_outfit_for_fashion(self, org):
        """
        Modeling Spine. If there are items in this outfit that can be modeled &
        action points are paid, then snapshots are created for each and a sum of
        all their fame is returned.
        """
        from world.fashion.mixins import FashionableMixins
        if self.modeled:
            raise FashionError("%s has already been modeled." % self)
        if not self.is_carried or not self.is_equipped:
            raise FashionError("Outfit must be equipped before trying to model it.")
        valid_items = self.check_outfit_fashion_ready()
        ap_cost = len(valid_items) * FashionableMixins.fashion_ap_cost
        if not self.owner.player.pay_action_points(ap_cost):
            raise FashionError("It costs %d AP to model %s; you do not have enough energy." % (ap_cost, self))
        outfit_fame = 0
        for item in valid_items:
            outfit_fame += item.model_for_fashion(self.owner.player, org, outfit=self)
        return min(outfit_fame, self.FAME_CAP)

    @property
    def table_display(self):
        """A non-cached table of outfit items/locations, then model-info string."""
        from server.utils.prettytable import PrettyTable
        table = PrettyTable((str(self), "Slot", "Location"))
        modi = self.modusornamenta_set.all()
        for mo in modi:
            table.add_row((str(mo.fashion_item), mo.slot or "", str(mo.fashion_item.location)))
        msg = str(table)
        if self.modeled:
            msg += "\n" + self.model_info
            # TODO: Include existing event info :)
            # TODO: Include existing fashion judge votes & comments!
        return msg

    @property
    def list_display(self):
        """A cached string simply listing outfit components & model info."""
        if not hasattr(self, '_cached_outfit_display'):
            from server.utils.arx_utils import list_to_string
            msg = "|w[|n" + str(self) + "|w]|n"
            weapons = list(self.weapons)
            apparel = list(self.apparel)
            if weapons:
                msg += " weapons: " + list_to_string(weapons)
            if apparel:
                msg += "\nattire: " + list_to_string(apparel)
            if self.modeled:
                msg += "\n" + self.model_info
                # TODO: Include existing event info :)
                # TODO: Include existing fashion judge votes & comments!
            self._cached_outfit_display = msg
        return self._cached_outfit_display

    @list_display.deleter
    def list_display(self):
        if hasattr(self, '_cached_outfit_display'):
            del self._cached_outfit_display

    @property
    def model_info(self):
        if self.modeled:
            if not hasattr(self, '_cached_model_info'):
                self._cached_model_info = self.fashion_snapshots.first().display
            return self._cached_model_info

    @model_info.deleter
    def model_info(self):
        if hasattr(self, '_cached_model_info'):
            del self._cached_model_info

    @property
    def modeled(self):
        if not hasattr(self, '_cached_model_bool'):
            self._cached_model_bool = bool(self.fashion_snapshots.exists())
        return self._cached_model_bool

    @modeled.deleter
    def modeled(self):
        if hasattr(self, '_cached_model_bool'):
            del self._cached_model_bool

    @property
    def fame(self):
        if self.modeled:
            if not hasattr(self, '_cached_fame'):
                self._cached_fame = sum([ob.fame for ob in self.fashion_snapshots.all()])
            return self._cached_fame

    @fame.deleter
    def fame(self):
        if hasattr(self, '_cached_fame'):
            del self._cached_fame

    @property
    def appraisal_or_buzz(self):
        if self.modeled:
            return self.buzz
        else:
            return self.appraisal

    @property
    def appraisal(self):
        """Returns string sum worth of outfit's unmodeled items."""
        worth = 0
        for item in self.fashion_items.all():
            if not item.modeled_by:
                worth += item.item_worth
        return str("{:,}".format(worth) or "cannot model")

    @property
    def buzz(self):
        """Returns colorized string: the term for outfit's fame impact."""
        buzz = ""
        if self.modeled:
            buzz = self.get_buzz_word(self.fame)
        return buzz

    @property
    def weapons(self):
        """
        Cached queryset of this outfit's wielded/sheathed weapons, but not
        decorative weapons.
        """
        if not hasattr(self, '_cached_weapons'):
            self._cached_weapons = self.fashion_items.filter(modusornamenta__slot__iendswith='weapon').distinct()
        return self._cached_weapons

    @weapons.deleter
    def weapons(self):
        if hasattr(self, '_cached_weapons'):
            del self._cached_weapons

    @property
    def apparel(self):
        """cached queryset of this outfit's worn items. Not sheathed weapons."""
        if not hasattr(self, '_cached_apparel'):
            self._cached_apparel = self.fashion_items.exclude(modusornamenta__slot__iendswith='weapon').distinct()
        return self._cached_apparel

    @apparel.deleter
    def apparel(self):
        if hasattr(self, '_cached_apparel'):
            del self._cached_apparel

    @property
    def is_carried(self):
        """Truthy if all outfit items are located on a character."""
        return not self.fashion_items.exclude(db_location=self.owner_character).exists()

    @property
    def is_equipped(self):
        """Truthy if all outfit items are currently equipped by owner character."""
        for item in self.fashion_items.all():
            loc = item.location if item.is_equipped else None
            if loc != self.owner_character:
                return False
        return True

    @property
    def equipped_msg(self):
        """Returns a string saying whether or not outfit is equipped."""
        indicator = "successfully" if self.is_equipped else "not"
        return "Your outfit '%s' is %s equipped." % (self, indicator)

    @property
    def owner_character(self):
        return self.owner.player.char_ob


class ModusOrnamenta(SharedMemoryModel):
    """
    The method of wearing an item in an outfit.
    """
    fashion_outfit = models.ForeignKey('FashionOutfit', on_delete=models.CASCADE)
    fashion_item = models.ForeignKey('objects.ObjectDB', on_delete=models.CASCADE)
    slot = models.CharField(max_length=80, blank=True, null=True)


class FashionSnapshot(FashionCommonMixins):
    """
    The recorded moment when a piece of gear becomes a weapon
    of the fashionpocalypse.
    """
    FAME_CAP = 1500000
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
    outfit = models.ForeignKey('FashionOutfit', related_name='fashion_snapshots',
                               on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return str(self.fashion_item) if self.fashion_item else "[Snapshot #%d]" % self.id

    @property
    def display(self):
        """The modeled info and 'buzz message' that appears on items."""
        displayed_fame = self.fame if not self.outfit else self.outfit.fame
        msg = self.get_model_msg(self.fashion_model, self.org, self.db_date_created, displayed_fame)
        return msg

    def save(self, *args, **kwargs):
        """Invalidates cache on save"""
        super(FashionSnapshot, self).save(*args, **kwargs)
        self.invalidate_fashion_caches()

    def delete(self, *args, **kwargs):
        """Invalidates cache before delete"""
        self.invalidate_fashion_caches()
        super(FashionSnapshot, self).delete(*args, **kwargs)

    def invalidate_fashion_caches(self):
        if self.outfit:
            self.outfit.invalidate_outfit_caches()
        self.fashion_item.invalidate_snapshots_cache()

    def roll_for_fame(self):
        """
        Rolls for amount of fame the item generates, minimum 2 fame. The fashion model's social clout and
        skill check of composure + performance is made exponential to be an enormous swing in the efficacy
        of fame generated: Someone whose roll+social_clout is 50 will be hundreds of times as effective
        as someone who flubs the roll.
        """
        from world.stats_and_skills import do_dice_check
        char = self.fashion_model.player.char_ob
        roll = do_dice_check(caller=char, stat="composure", skill="performance", difficulty=30)
        roll = pow(max((roll + char.social_clout * 5), 1), 1.5)
        percentage = max(roll/100.0, 0.01)
        level_mod = self.fashion_item.recipe.level/6.0
        percentage *= max(level_mod, 0.01)
        percentage *= max((self.fashion_item.quality_level/40.0), 0.01)
        percentage = max(percentage, 0.2)
        # they get either their percentage of the item's worth, their modified roll, or 4, whichever is highest
        self.fame = min(max(int(self.fashion_item.item_worth * percentage), max(int(roll), 4)), self.FAME_CAP)
        self.save()

    def apply_fame(self, reverse=False):
        """
        Awards full amount of fame to fashion model and a portion to the
        sponsoring Organization & the item's Designer.
        """
        from world.dominion.models import PrestigeCategory

        mult = -1 if reverse else 1
        model_fame = self.fame * mult
        org_fame = self.org_fame * mult
        designer_fame = self.designer_fame * mult
        self.fashion_model.assets.adjust_prestige(model_fame, PrestigeCategory.FASHION)
        self.org.assets.adjust_prestige(org_fame)
        self.designer.assets.adjust_prestige(designer_fame, PrestigeCategory.DESIGN)

    def inform_fashion_clients(self):
        """
        Informs clients when fame is earned, by using their AssetOwner method.
        """
        category = "fashion"
        msg = "fame awarded from %s modeling %s." % (self.fashion_model, self.fashion_item)
        if self.org_fame > 0:
            org_msg = "{{315{:,}{{n {}".format(self.org_fame, msg)
            self.org.assets.inform_owner(org_msg, category=category, append=True)
        if self.designer_fame > 0:
            designer_msg = "{{315{:,}{{n {}".format(self.designer_fame, msg)
            self.designer.assets.inform_owner(designer_msg, category=category, append=True)

    def reverse_snapshot(self):
        """Reverses the fame / action point effects of this snapshot"""
        from world.fashion.mixins import FashionableMixins
        self.apply_fame(reverse=True)
        self.fashion_model.player.pay_action_points(-FashionableMixins.fashion_ap_cost)

    @property
    def org_fame(self):
        """The portion of fame awarded to sponsoring org"""
        return int(self.fame/self.ORG_FAME_DIVISOR)

    @property
    def designer_fame(self):
        """The portion of fame awarded to item designer."""
        return int(self.fame/self.DESIGNER_FAME_DIVISOR)
