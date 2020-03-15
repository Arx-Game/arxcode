from server.utils.arx_utils import lowercase_kwargs, list_to_string
from typeclasses.exceptions import EquipError
from evennia.objects.objects import DefaultCharacter
from typing import Union
from typeclasses.mixins import ModifierMixin


class UseEquipmentMixins(object):
    """
    Behaviors related to donning equipment.
    """
    def check_equipment_changes_permitted(self: Union[DefaultCharacter, 'UseEquipmentMixins']):
        cscript = self.location.ndb.combat_manager
        if cscript and cscript.ndb.phase != 1 and cscript.check_character_is_combatant(self):
            from typeclasses.scripts.combat.combat_settings import CombatError
            raise CombatError("Equipment changes are only allowed in combat's setup phase.")

    def wield(self, obj):
        self.check_equipment_changes_permitted()

    def wear(self, obj, layer):
        self.check_equipment_changes_permitted()

    def remove(self, obj):
        self.check_equipment_changes_permitted()
        obj.remove()

    def undress(self):
        """A character method to take it aaaaall off. Does not handle exceptions!"""
        self.equip_or_remove("remove")

    def sheathe(self, obj):
        self.check_equipment_changes_permitted()

    def equip_or_remove(self: Union[DefaultCharacter, 'UseEquipmentMixins'], verb, item_list=None):
        """
        A list of items is worn, wielded, or removed from a character.

            Args:
                verb (str): the method to call
                item_list (list): objects we attempt to call method in

        Will try to call the method matching our verb for each list item. If no
        list is given, we build list from character contents. A message is
        crafted for success or exception (failure). Total success means results
        are messaged to self. Otherwise result is raised as an EquipError.
        """
        cscript = self.location.ndb.combat_manager
        if cscript and cscript.ndb.phase != 1 and cscript.check_character_is_combatant(self):
            from typeclasses.scripts.combat.combat_settings import CombatError
            raise CombatError("Equipment changes are only allowed in combat's setup phase.")
        if verb in ("wear", "sheathe"):
            alt = verb if verb == "sheathe" else "put on"
            verb = "wear"
        elif verb == "wield":
            alt = "brandish"
        else:
            verb, alt = "remove", "remove"
        if not item_list:
            item_list = self.get_item_list_to_equip(verb)
            if not item_list:
                raise EquipError("You have nothing to %s." % verb)
        successes, failures = [], []
        for item in item_list:
            try:
                getattr(item, verb)(self)
            except AttributeError:
                failures.append("%s |w(wrong item type)|n" % item)
            except EquipError as err:
                failures.append("%s |w(%s)|n" % (item, err))
            else:
                successes.append(str(item))
        msg = ""
        if failures:
            msg += "Could not %s %s.\n" % (alt, list_to_string(failures, endsep="or"))
        if successes:
            msg += "You %s %s." % (alt, list_to_string(successes))
        elif len(item_list) > 1:  # no successes and also multiple items attempted
            msg += "|yYou %s nothing.|n" % alt
        if failures:
            raise EquipError(msg)
        else:
            self.msg(msg)

    def get_item_list_to_equip(self, verb):
        """Builds a verb-appropriate list of items from our contents."""
        if verb == "wear":
            equipment = [ob for ob in self.equipable_items if not ob.is_equipped]
            from operator import attrgetter
            return sorted(equipment, key=attrgetter('slot', 'db_key'))
        else:  # Equipment to be removed
            return [ob for ob in self.equipable_items if ob.is_equipped]

    def get_items_in_slot_and_layer(self, slot, layer):
        return [item for item in self.equipable_items if item.slot == slot and item.layer == layer]

    def check_slot_and_layer_occupied(self, slot, layer):
        return sum([item.slot_volume for item in self.get_items_in_slot_and_layer(slot, layer)])

    @lowercase_kwargs("target_tags", "stat_list", "skill_list", "ability_list", default_append="")
    def get_total_modifier(self: Union[DefaultCharacter, 'UseEquipmentMixins', ModifierMixin],
                           check_type, target_tags=None, stat_list=None, skill_list=None, ability_list=None):
        """Gets all modifiers from their location and worn/wielded objects."""
        from django.db.models import Sum
        from world.conditions.models import RollModifier
        user_tags = self.modifier_tags or []
        user_tags.append("")
        # get modifiers from worn stuff we have and our location, if any
        all_objects = list(self.worn)
        if self.location:
            all_objects.append(self.location)
        all_objects.append(self)
        if self.weapon:
            all_objects.append(self.weapon)
        all_objects = [ob.id for ob in all_objects]
        check_types = RollModifier.get_check_type_list(check_type)
        return RollModifier.objects.filter(object_id__in=all_objects or [], check__in=check_types or [],
                                           user_tag__in=user_tags or [], target_tag__in=target_tags or [],
                                           stat__in=stat_list or [], skill__in=skill_list or [],
                                           ability__in=ability_list or []).aggregate(Sum('value'))['value__sum'] or 0

    @property
    def armor_resilience(self: Union[DefaultCharacter, 'UseEquipmentMixins']):
        """Determines how hard it is to penetrate our armor"""
        value = self.db.armor_resilience or 15
        for ob in self.worn:
            value += ob.armor_resilience
        return int(value)

    @property
    def armor(self: Union[DefaultCharacter, 'UseEquipmentMixins']):
        """
        Returns armor value of all items the character is wearing plus any
        armor in their attributes.
        """
        armor = self.db.armor_class or 0
        for ob in self.worn:
            try:
                ob_armor = ob.armor or 0
            except AttributeError:
                ob_armor = 0
            armor += ob_armor
        return int(round(armor))

    @armor.setter
    def armor(self: Union[DefaultCharacter, 'UseEquipmentMixins'], value):
        self.db.armor_class = value

    @property
    def armor_penalties(self):
        penalty = 0
        for ob in self.worn:
            try:
                penalty += ob.penalty
            except (AttributeError, ValueError, TypeError):
                pass
        return penalty

    def get_fakeweapon(self: Union[DefaultCharacter, 'UseEquipmentMixins']):
        return self.db.fakeweapon

    @property
    def weapondata(self: Union['typeclasses.characters.Character', 'UseEquipmentMixins']):
        wpndict = dict(self.get_fakeweapon() or {})
        wpn = self.weapon
        if wpn:
            wpndict['attack_skill'] = wpn.attack_skill
            wpndict['attack_stat'] = wpn.attack_stat
            wpndict['damage_stat'] = wpn.damage_stat
            wpndict['weapon_damage'] = wpn.base_damage
            wpndict['attack_type'] = wpn.attack_type
            wpndict['can_be_parried'] = wpn.can_be_parried
            wpndict['can_be_blocked'] = wpn.can_be_blocked
            wpndict['can_be_dodged'] = wpn.can_be_dodged
            wpndict['can_parry'] = wpn.can_parry
            wpndict['can_riposte'] = wpn.can_parry or wpn.can_riposte
            wpndict['difficulty_mod'] = wpn.difficulty_mod
            wpndict['flat_damage'] = wpn.flat_damage
            wpndict['modifier_tags'] = wpn.modifier_tags
        boss_rating = self.boss_rating
        if boss_rating:
            wpndict['weapon_damage'] = wpndict.get('weapon_damage', 1) + boss_rating
            wpndict['flat_damage'] = wpndict.get('flat_damage', 0) + boss_rating * 10
        return wpndict

    @property
    def weapon(self: Union[DefaultCharacter, 'UseEquipmentMixins']):
        return self.db.weapon

    @weapon.setter
    def weapon(self: Union[DefaultCharacter, 'UseEquipmentMixins'], value):
        self.db.weapon = value

    @property
    def weapons_hidden(self):
        """Returns True if we have a hidden weapon, false otherwise"""
        try:
            return self.weapondata['hidden_weapon']
        except (AttributeError, KeyError):
            return False

    @property
    def equipable_items(self: Union[DefaultCharacter, 'UseEquipmentMixins']):
        """Returns list of items in inventory capable of being worn/wielded."""
        return [ob for ob in self.contents if hasattr(ob, 'wear')]

    @property
    def equipped_items(self: Union[DefaultCharacter, 'UseEquipmentMixins']):
        return [ob for ob in self.contents if hasattr()]

    @property
    def worn(self):
        """Returns list of items worn as attire."""
        worn = [ob for ob in self.equipable_items if ob.decorative and ob.is_worn]
        return sorted(worn, key=lambda x: x.db.worn_time)

    @property
    def sheathed(self):
        """Returns list of worn non-decorative weapons."""
        return [ob for ob in self.equipable_items if not ob.decorative and ob.is_worn]

    @property
    def wielded(self):
        """Returns list of weapons currently being wielded."""
        return [ob for ob in self.equipable_items if hasattr(ob, 'wield') and ob.is_wielded]

    @property
    def is_naked(self):
        """Confirms a character has no worn, sheathed, or wielded items."""
        return not any([self.worn, self.sheathed, self.wielded])

    @property
    def used_volume(self: Union[DefaultCharacter, 'UseEquipmentMixins']):
        """The idea here is the only objects that take up carrying space are things which we aren't worn -
        it's just objects that the character is physically holding. So weapons count, but worn clothes do not.
        """
        return sum(ob.volume for ob in self.contents if not ob.is_worn)
