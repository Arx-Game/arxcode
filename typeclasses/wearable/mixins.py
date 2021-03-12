from server.utils.arx_utils import lowercase_kwargs, list_to_string
from typeclasses.exceptions import EquipError


class UseEquipmentMixins(object):
    """
    Behaviors related to donning equipment.
    """

    def equip_or_remove(self, verb, item_list=None):
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
        if (
            cscript
            and cscript.ndb.phase != 1
            and cscript.check_character_is_combatant(self)
        ):
            from typeclasses.scripts.combat.combat_settings import CombatError

            raise CombatError(
                "Equipment changes are only allowed in combat's setup phase."
            )
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
            equipment = [ob for ob in self.equipment if not ob.is_equipped]
            from operator import attrgetter

            return sorted(equipment, key=attrgetter("slot_limit", "db_key"))
        else:  # Equipment to be removed
            return [ob for ob in self.equipment if ob.is_equipped]

    def undress(self):
        """A character method to take it aaaaall off. Does not handle exceptions!"""
        self.equip_or_remove("remove")

    @lowercase_kwargs(
        "target_tags", "stat_list", "skill_list", "ability_list", default_append=""
    )
    def get_total_modifier(
        self,
        check_type,
        target_tags=None,
        stat_list=None,
        skill_list=None,
        ability_list=None,
    ):
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
        return (
            RollModifier.objects.filter(
                object_id__in=all_objects or [],
                check__in=check_types or [],
                user_tag__in=user_tags or [],
                target_tag__in=target_tags or [],
                stat__in=stat_list or [],
                skill__in=skill_list or [],
                ability__in=ability_list or [],
            ).aggregate(Sum("value"))["value__sum"]
            or 0
        )

    @property
    def armor_resilience(self):
        """Determines how hard it is to penetrate our armor"""
        value = self.db.armor_resilience or 15
        for ob in self.worn:
            value += ob.armor_resilience
        return int(value)

    @property
    def armor(self):
        """
        Returns armor value of all items the character is wearing plus any
        armor in their attributes.
        """
        armor = self.traits.armor_class
        for ob in self.worn:
            try:
                ob_armor = ob.armor or 0
            except AttributeError:
                ob_armor = 0
            armor += ob_armor
        return int(round(armor))

    @armor.setter
    def armor(self, value):
        self.traits.set_other_value("armor_class", value)

    @property
    def armor_penalties(self):
        penalty = 0
        for ob in self.worn:
            try:
                penalty += ob.penalty
            except (AttributeError, ValueError, TypeError):
                pass
        return penalty

    def get_fakeweapon(self):
        return self.db.fakeweapon

    @property
    def weapondata(self):
        wpndict = dict(self.get_fakeweapon() or {})
        wpn = self.weapon
        if wpn:
            wpndict["attack_skill"] = wpn.item_data.attack_skill
            wpndict["attack_stat"] = wpn.item_data.attack_stat
            wpndict["damage_stat"] = wpn.item_data.damage_stat
            wpndict["weapon_damage"] = wpn.damage_bonus
            wpndict["attack_type"] = wpn.item_data.attack_type
            wpndict["can_be_parried"] = wpn.item_data.can_be_parried
            wpndict["can_be_blocked"] = wpn.item_data.can_be_blocked
            wpndict["can_be_dodged"] = wpn.item_data.can_be_dodged
            wpndict["can_parry"] = wpn.item_data.can_parry or False
            wpndict["can_riposte"] = (
                wpn.item_data.can_parry or wpn.item_data.can_riposte or False
            )
            wpndict["reach"] = wpn.db.weapon_reach or 1
            wpndict["minimum_range"] = wpn.db.minimum_range or 0
            try:
                wpndict["difficulty_mod"] = wpn.difficulty_mod or 0
            except AttributeError:
                wpndict["difficulty_mod"] = wpn.item_data.difficulty_mod
            try:
                wpndict["flat_damage"] = wpn.flat_damage or 0
            except AttributeError:
                wpndict["flat_damage"] = wpn.db.flat_damage_bonus or 0
            wpndict["modifier_tags"] = wpn.modifier_tags
        boss_rating = self.boss_rating
        if boss_rating:
            wpndict["weapon_damage"] = wpndict.get("weapon_damage", 1) + boss_rating
            wpndict["flat_damage"] = wpndict.get("flat_damage", 0) + boss_rating * 10
        return wpndict

    @property
    def weapon(self):
        return self.db.weapon

    @weapon.setter
    def weapon(self, value):
        self.db.weapon = value

    @property
    def weapons_hidden(self):
        """Returns True if we have a hidden weapon, false otherwise"""
        try:
            return self.weapondata["hidden_weapon"]
        except (AttributeError, KeyError):
            return False
        return True

    @property
    def equipment(self):
        """Returns list of items in inventory capable of being worn/wielded."""
        return [ob for ob in self.contents if hasattr(ob, "wear")]

    @property
    def worn(self):
        """Returns list of items worn as attire."""
        worn = [ob for ob in self.equipment if ob.decorative and ob.is_worn]
        return sorted(worn, key=lambda x: x.item_data.worn_time)

    @property
    def sheathed(self):
        """Returns list of worn non-decorative weapons."""
        return [ob for ob in self.equipment if not ob.decorative and ob.is_worn]

    @property
    def wielded(self):
        """Returns list of weapons currently being wielded."""
        return [ob for ob in self.equipment if hasattr(ob, "wield") and ob.is_wielded]

    @property
    def is_naked(self):
        """Confirms a character has no worn, sheathed, or wielded items."""
        return not any([self.worn, self.sheathed, self.wielded])
