"""
wieldable objects. Weapons. While worn, wieldable objects are
considered 'sheathed' unless specified otherwise
"""
from typeclasses.exceptions import EquipError
from typeclasses.wearable.cmdset_wieldable import WeaponCmdSet
from typeclasses.wearable.wearable import Wearable
from world.crafting.craft_data_handlers import WieldableDataHandler


# noinspection PyMethodMayBeStatic
# noinspection PyUnusedLocal
class Wieldable(Wearable):
    """
    Class for wieldable objects
    API: Properties are all a series of database attributes,
    for easy customization by builders using @set.
    'ready_phrase' allows a builder to set the string added to character name when
    the object is wielded. ex: @set sword/ready_phrase = "wields a large sword"
    'stealth' determines if the weapon will give an echo to the room when it is
    wielded. Poisons, magic, stealthy daggers, etc, fall into this category.
    """

    default_desc = "A weapon of some kind."
    SHEATHED_LIMIT = 6
    item_data_class = WieldableDataHandler
    default_attack_stat = "dexterity"
    default_damage_stat = "strength"
    default_can_be_blocked = True
    default_can_be_dodged = True
    default_can_be_countered = True
    default_ready_phrase = ""
    baseval_scaling_divisor = 20.0
    default_scaling = 0.2

    def at_object_creation(self):
        """
        Run at wieldable creation. The defaults are for a generic melee
        weapon.
        """
        self.cmdset.add_default(WeaponCmdSet, permanent=True)
        self.at_init()

    def softdelete(self):
        self.cease_wield()
        super(Wieldable, self).softdelete()

    @property
    def default_attack_skill(self):
        if self.item_data.recipe:
            return self.item_data.recipe.weapon_skill
        return "medium wpn"

    @property
    def default_attack_type(self):
        if self.item_data.recipe:
            return self.item_data.recipe.attack_type
        return "melee"

    @property
    def is_ranged(self):
        """This specifies whether we're a melee or ranged weapon,
        which implies some default behaviors"""
        return self.item_data.attack_type == "ranged"

    @property
    def default_can_be_parried(self):
        """By default, people cannot parry ranged weapons"""
        return not self.is_ranged

    @property
    def default_can_parry(self):
        """By default, ranged weapons can't be used to parry"""
        return not self.is_ranged

    @property
    def default_can_riposte(self):
        """By default, ranged weapons cannot riposte"""
        return not self.is_ranged

    def at_before_move(self, destination, **kwargs):
        """Checks if the object can be moved"""
        caller = kwargs.get("caller", None)
        if caller and self.is_wielded:
            caller.msg("%s is currently wielded and cannot be moved." % self)
            return False
        return super(Wieldable, self).at_before_move(destination, **kwargs)

    def at_after_move(self, source_location, **kwargs):
        """If new location is not our wielder, remove."""
        if self.is_wielded and self.location != source_location:
            self.cease_wield(source_location)
        super(Wieldable, self).at_after_move(source_location, **kwargs)

    def remove(self, wielder):
        """
        Takes off the weapon entirely, wielded or worn.
        """
        if not self.cease_wield():
            super(Wieldable, self).remove(wielder)

    def at_post_remove(self, wielder):
        """Hook called after removing succeeds."""
        return True

    def wear(self, wearer):
        """
        Puts item on the wearer.
        """
        super(Wieldable, self).wear(wearer)

    def at_pre_wear(self, wearer):
        """Hook called before wearing to cease wielding and perform checks."""
        self.cease_wield()
        super(Wieldable, self).at_pre_wear(wearer)

    def slot_check(self, wearer):
        if self.decorative:
            super(Wieldable, self).slot_check(wearer)
        else:
            sheathed = wearer.sheathed
            if len(sheathed) >= self.SHEATHED_LIMIT:
                raise EquipError("sheathed limit reached")

    def at_post_wear(self, wearer):
        """Hook called after wearing this weapon."""
        return True

    def cease_wield(self, wielder=None):
        """
        Only resets wielded traits: Not part of 'remove' because other
        reasons to cease wielding exist, such as wearing.
        """
        if self.is_wielded:
            wielder = wielder if wielder else self.location
            wielder.weapon = None
            self.is_wielded = False
            self.at_post_cease_wield(wielder)
            return True

    def at_post_cease_wield(self, wielder):
        """Hook called after cease_wield succeeds."""
        if wielder:
            wielder.combat.setup_weapon(wielder.weapondata)

    # noinspection PyAttributeOutsideInit
    def wield(self, wielder):
        """
        Puts item on the wielder.
        """
        # Assume fail exceptions are raised at_pre_wield
        self.at_pre_wield(wielder)
        self.is_wielded = True
        wielder.weapon = self
        self.at_post_wield(wielder)

    def at_pre_wield(self, wielder):
        """Hook called before wielding for any checks."""
        if self.is_wielded:
            raise EquipError("already wielded")
        if self.location != wielder:
            raise EquipError("misplaced")
        if any(wielder.wielded):
            raise EquipError("other weapon in use")
        if self.is_worn:
            self.remove(wielder)

    def at_post_wield(self, wielder):
        """Hook called after wielding succeeds."""
        if wielder:
            wielder.combat.setup_weapon(wielder.weapondata)
        self.announce_wield(wielder)

    def announce_wield(self, wielder):
        """
        Makes a list of room occupants who are aware this weapon has
        been wielded, and tells them.
        """
        exclude = [wielder]
        msg = self.item_data.ready_phrase or "wields %s" % self.name
        wielder.location.msg_contents("%s %s." % (wielder.name, msg), exclude=exclude)

    def check_fashion_ready(self):
        from world.fashion.mixins import FashionableMixins

        FashionableMixins.check_fashion_ready(self)
        if not (self.is_wielded or self.is_worn):
            from world.fashion.exceptions import FashionError

            verb = "wear" if self.decorative else "sheathe"
            raise FashionError(
                "Please wield or %s %s before trying to model it as fashion."
                % (verb, self)
            )
        return True

    @property
    def default_damage_bonus(self):
        if not self.item_data.recipe:
            return 1
        return int(
            round(
                self.modified_baseval
                + (self.quality_scaling * self.item_data.quality_level)
            )
        )

    @property
    def default_difficulty_mod(self):
        diffmod = 0
        if self.item_data.attack_skill == "huge wpn":
            diffmod += 1
        elif self.item_data.attack_skill == "archery":
            diffmod -= 10
        elif self.item_data.attack_skill == "small wpn":
            diffmod -= 1
        if not self.item_data.recipe:
            return diffmod
        diffmod -= int(round(0.2 * self.item_data.quality_level))
        return diffmod

    @property
    def default_flat_damage_bonus(self):
        if not self.item_data.recipe:
            return 0
        return (self.item_data.quality_level - 2) * 2

    @property
    def armor(self):
        return 0

    @property
    def is_wielded(self):
        return self.item_data.currently_wielded

    @is_wielded.setter
    def is_wielded(self, bull):
        self.item_data.currently_wielded = bull

    @property
    def is_equipped(self):
        """shared property just for checking worn/wielded/otherwise-used status."""
        return self.is_worn or self.is_wielded

    @property
    def decorative(self):
        """Weapons are not decorative. Unless they are."""
        return False
