"""
wieldable objects. Weapons. While worn, wieldable objects are
considered 'sheathed' unless specified otherwise.

is_wieldable boolean is the check to see if we're a wieldable
object. is_wielded is a boolean saying our wielded state
"""
from typeclasses.exceptions import EquipError
from typeclasses.wearable.cmdset_wieldable import WeaponCmdSet
from typeclasses.wearable.wearable import Wearable


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
    is_wieldable = True
    attack_skill = "medium wpn"
    attack_stat = "dexterity"
    damage_stat = "strength"
    attack_type = "melee"
    can_be_parried = True
    can_be_blocked = True
    can_be_countered = True
    can_be_dodged = True
    can_parry = True
    can_riposte = True
    base_difficulty_mod = 0
    slot = "sheathed"

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

    def at_before_move(self, destination, **kwargs):
        """Checks if the object can be moved"""
        caller = kwargs.get('caller', None)
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

    def wear(self, wearer, layer=None):
        """
        Puts item on the wearer.
        """
        super(Wieldable, self).wear(wearer)

    def at_pre_wear(self, wearer, layer=None):
        """Hook called before wearing to cease wielding and perform checks."""
        self.cease_wield()
        super(Wieldable, self).at_pre_wear(wearer, layer=layer)

    def slot_check(self, wearer, layer):
        if self.decorative:
            super(Wieldable, self).slot_check(wearer, layer)
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
        if self.db.stealth:
            # checks for sensing a stealthed weapon being wielded. those who fail are put in exclude list
            chars = [char for char in wielder.location.contents if hasattr(char, 'sensing_check') and char != wielder]
            for char in chars:
                if char.sensing_check(self, diff=self.db.sensing_difficulty) < 1:
                    exclude.append(char)
        wielder.location.msg_contents("%s %s." % (wielder.name, self.ready_phrase), exclude=exclude)

    @property
    def ready_phrase(self):
        return self.db.ready_phrase or "wields %s" % self.name

    def calc_armor(self):
        """Sheathed/worn weapons have no armor value or other modifiers"""
        return 0, 0, 0

    def check_fashion_ready(self):
        from world.fashion.mixins import FashionableMixins
        FashionableMixins.check_fashion_ready(self)
        if not (self.is_wielded or self.is_worn):
            from world.fashion.exceptions import FashionError
            verb = "wear" if self.decorative else "sheathe"
            raise FashionError("Please wield or %s %s before trying to model it as fashion." % (verb, self))
        return True

    @property
    def base_damage(self):
        if not self.recipe or self.ignore_crafted:
            return self.db.base_damage or 0
        return int(round(self.baseval + (self.scaling * self.quality_level)))

    @base_damage.setter
    def base_damage(self, value):
        """
        Manually sets the value of our weapon, ignoring any crafting recipe we have.
        """
        self.db.base_damage = value
        self.tags.add("ignore_crafted")

    @property
    def flat_damage(self):
        flat = self.db.flat_damage_bonus or 0
        if not self.recipe or self.ignore_crafted:
            return flat
        flat += (self.quality_level - 2) * 2
        return flat

    @property
    def difficulty_mod(self):
        return self.base_difficulty_mod - int(round(0.2 * self.quality_level))

    @property
    def armor(self):
        return 0

    @property
    def is_wielded(self):
        try:
            return self.equipped_details.is_wielded
        except AttributeError:
            return False

    @is_wielded.setter
    def is_wielded(self, bull):
        if bull:
            self.tags.add("currently_wielded")
        else:
            self.tags.remove("currently_wielded")

    @property
    def is_equipped(self):
        """shared property just for checking worn/wielded/otherwise-used status."""
        return self.is_worn or self.is_wielded

    @property
    def decorative(self):
        """Weapons are not decorative. Unless they are."""
        return False


class RangedWeapon(Wieldable):
    can_be_parried = False
    can_parry = False
    can_riposte = False
    attack_type = "ranged"
    base_difficulty_mod = -10


class HugeWeapon(Wieldable):
    base_difficulty_mod = 1


class SmallWeapon(Wieldable):
    base_difficulty_mod = -1
