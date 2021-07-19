"""
The traitshandler is an abstraction layer for getting stats/skills for a character
in which data storage is hidden. The original implementation of stats/skills were using
Evennia attributes, which resulted in extremely denormalized data. Moving them to an
abstraction layer both allows for caching and hiding data storage, allowing for ease
of refactoring.
"""
import random
from collections import defaultdict, namedtuple
from typing import Dict, List

from world.conditions.constants import SERIOUS_WOUND, PERMANENT_WOUND
from world.stats_and_skills import (
    _parent_abilities_,
    DOM_SKILLS,
)
from world.traits.exceptions import InvalidTrait
from world.traits.models import CharacterTraitValue, Trait

TraitValue = namedtuple("TraitValue", "name value")


class Traitshandler:
    """
    Handler that's instantiated with a character, which will then store the instance
    as a cached property on the character.
    """

    def __init__(self, character):
        self.character = character
        # cache has different types of traits that will return an empty object when not found
        self._cache = {
            "stat": defaultdict(CharacterTraitValue),
            "skill": defaultdict(CharacterTraitValue),
            "ability": defaultdict(CharacterTraitValue),
            "other": defaultdict(CharacterTraitValue),
        }
        self.initialized = False
        self.setup_caches()

    def setup_caches(self, reset=False):
        """Set our character's trait values in the cache, with case-insensitive keys by trait name"""
        if not reset and self.initialized:
            return
        for trait_value in self.character.trait_values.all():
            self.add_trait_value_to_cache(trait_value)
        self.initialized = True

    def get_value_by_trait(self, trait: Trait) -> int:
        name = trait.name.lower()
        trait_type = trait.get_trait_type_display()
        return self.adjust_by_wounds(self._cache[trait_type][name].value, name)

    def get_wound_count_for_trait_name(self, name, perm_only=False):
        wounds = [
            ob
            for ob in self.character.health_status.cached_wounds
            if ob.trait.name.lower() == name
        ]
        if perm_only:
            wounds = [ob for ob in wounds if ob.severity == PERMANENT_WOUND]
        return len(wounds)

    def get_total_wound_count(self):
        return len(self.character.health_status.cached_wounds)

    def add_trait_value_to_cache(self, trait_value: CharacterTraitValue):
        self._cache[trait_value.trait.get_trait_type_display()][
            trait_value.trait.name.lower()
        ] = trait_value

    def adjust_by_wounds(self, value, name, perm_only=False):
        num = self.get_wound_count_for_trait_name(name, perm_only=perm_only)
        value -= num
        if value < 0:
            return 0
        return value

    def get_skill_value(self, name: str) -> int:
        return self.adjust_by_wounds(self.skills.get(name, 0), name)

    def get_stat_value(self, name: str, raw=False) -> int:
        if raw:
            return self.stats.get(name, 0)
        return self.adjust_by_wounds(self.stats.get(name, 0), name)

    def check_stat_can_be_raised(self, name: str) -> bool:
        """Returns True if the stat can be raised (or a permanent wound erased),
        False otherwise.
        """
        return self.adjust_by_wounds(self.stats.get(name, 0), name, perm_only=True) < 5

    def set_stat_value(self, name: str, value: int):
        self.set_trait_value("stat", name, value)

    def set_skill_value(self, name: str, value: int):
        self.set_trait_value("skill", name, value)

    def get_ability_value(self, name: str) -> int:
        return self.abilities.get(name, 0)

    def set_ability_value(self, name: str, value: int):
        self.set_trait_value("ability", name, value)

    def get_other_value(self, name: str) -> int:
        return self.other.get(name, 0)

    def set_other_value(self, name: str, value: int):
        self.set_trait_value("other", name, value)

    def set_trait_value(self, trait_type: str, name: str, value: int):
        """Deletes or sets up a trait value for a character, updating our cache"""
        # if our value is 0 or lower, delete the trait value
        if value <= 0 and name in self._cache[trait_type]:
            trait_value = self._cache[trait_type].pop(name)
            if trait_value.pk:
                trait_value.delete()
        else:  # create/update our trait value to be the new value
            if name in self._cache[trait_type]:
                trait_value = self._cache[trait_type][name]
            else:
                trait = Trait.get_instance_by_name(name)
                if not trait:
                    names = ", ".join(ob.name for ob in Trait.get_all_instances())
                    raise InvalidTrait(f"No trait found by '{name}'. Valid: {names}")
                trait_value, _ = self.character.trait_values.get_or_create(trait=trait)
                self._cache[trait_type][name] = trait_value
            trait_value.value = value
            trait_value.save()

    def get_highest_skill(self, namelist: List[str]) -> TraitValue:
        """
        Gets the highest trait for list of skill names. If no matches, a ValueError is raised and we choose
        one at random.
        """
        try:
            # get the highest trait from the list of skill names
            return max(
                [
                    TraitValue(name, self.skills.get(name))
                    for name in namelist
                    if name in self.skills
                ],
                key=lambda x: x.value,
            )
        except ValueError:
            # no match, get one at random
            return TraitValue(random.choice(namelist), 0)

    # stats or other traits
    def __getattr__(self, name):
        stat_names = Trait.get_valid_stat_names()
        if name in stat_names:
            return self.get_stat_value(name)
        other_names = Trait.get_valid_other_names()
        if name in other_names:
            return self.other.get(name, 0)
        raise AttributeError(f"{name} not found in {stat_names + other_names}.")

    @property
    def skills(self) -> Dict[str, int]:
        return {
            name: char_trait.value for name, char_trait in self._cache["skill"].items()
        }

    @skills.setter
    def skills(self, skills_dict: Dict[str, int]):
        self.wipe_all_skills()
        for skill, value in skills_dict.items():
            trait = Trait.get_instance_by_name(skill)
            if not trait:
                names = ", ".join(Trait.get_valid_skill_names())
                raise InvalidTrait(f"No trait found by '{skill}'. Valid: {names}")
            self._cache["skill"][skill] = self.character.trait_values.create(
                trait=trait, value=value
            )

    @property
    def abilities(self) -> Dict[str, int]:
        return {
            name: char_trait.value
            for name, char_trait in self._cache["ability"].items()
        }

    @abilities.setter
    def abilities(self, abilities_dict: Dict[str, int]):
        self.wipe_all_abilities()
        for ability, value in abilities_dict.items():
            trait = Trait.get_instance_by_name(ability)
            self._cache["ability"][ability] = self.character.trait_values.create(
                trait=trait, value=value
            )

    @property
    def stats(self) -> Dict[str, int]:
        return {
            name: char_trait.value for name, char_trait in self._cache["stat"].items()
        }

    @property
    def other(self) -> Dict[str, int]:
        return {
            name: char_trait.value for name, char_trait in self._cache["other"].items()
        }

    def wipe_all_skills(self):
        self.character.trait_values.filter(trait__trait_type=Trait.SKILL).delete()
        self._cache["skill"] = defaultdict(CharacterTraitValue)

    def wipe_all_abilities(self):
        self.character.trait_values.filter(trait__trait_type=Trait.ABILITY).delete()
        self._cache["ability"] = defaultdict(CharacterTraitValue)

    def check_training(self, field, stype):
        trainer = self.character.db.trainer
        if not trainer:
            return False
        if stype == "stat":
            callerval = self.get_stat_value(field)
            trainerval = trainer.traits.get_stat_value(field)
            return trainerval > callerval + 1
        if stype == "skill":
            callerval = self.get_skill_value(field)
            trainerval = trainer.traits.get_skill_value(field)
            return trainerval > callerval + 1
        if stype == "ability":
            callerval = self.get_ability_value(field)
            trainerval = trainer.traits.get_ability_value(field)
            return trainerval > callerval + 1
        if stype == "dom":
            try:
                callerval = getattr(self.character.player_ob.Dominion, field)
                trainerval = getattr(trainer.player_ob.Dominion, field)
                return trainerval >= callerval + 1
            except AttributeError:
                return False

    def adjust_stat(self, field, value=1):
        if field not in Trait.get_valid_stat_names():
            raise Exception(
                "Error in adjust_stat: %s not found as a valid stat." % field
            )
        if value == 1 and self.cure_permanent_wound(field):
            return
        current = self.get_stat_value(field, raw=True)
        self.set_stat_value(field, current + value)
        self.character.db.trainer = None

    def adjust_skill(self, field, value=1):
        if field not in Trait.get_valid_skill_names():
            raise Exception(
                "Error in adjust_skill: %s not found as a valid skill." % field
            )
        current = self.get_skill_value(field)
        self.set_skill_value(field, current + value)
        self.character.db.trainer = None
        if field in Trait.get_valid_skill_names(Trait.CRAFTING):
            abilitylist = _parent_abilities_[field]
            for ability in abilitylist:
                if ability not in self.abilities:
                    self.set_ability_value(ability, 1)

    def adjust_ability(self, field, value=1):
        if field not in Trait.get_valid_ability_names():
            raise Exception(
                "Error in adjust_ability: %s not found as a valid ability." % field
            )
        current = self.get_ability_value(field)
        self.set_ability_value(field, current + value)
        self.character.db.trainer = None

    def adjust_dom(self, field, value=1):
        if field not in DOM_SKILLS:
            raise Exception(
                "Error in adjust_dom: %s not found as a valid dominion skill." % field
            )
        dompc = self.character.player_ob.Dominion
        current = getattr(dompc, field)
        setattr(dompc, field, current + value)
        dompc.clear_cached_values_in_appointments()
        dompc.assets.save()
        dompc.save()

    def mirror_physical_stats_and_skills(self, source_character):
        """
        This is a way to destructively replace the physical stats and skills of our
        character with that of a source character. Eventually we'll replace this with some template
        system where characters can either use a template permanently or temporarily and modify it
        with their own values.
        """
        for stat in Trait.get_valid_stat_names(Trait.PHYSICAL):
            val = source_character.traits.get_stat_value(stat)
            self.set_stat_value(stat, val)
        self.skills = dict(source_character.traits.skills)

    def get_total_stats(self) -> int:
        return sum(self.stats.values())

    def get_max_hp(self) -> int:
        from world.stat_checks.models import StatWeight

        base = StatWeight.get_health_value_for_stamina(self.stamina)
        bonus = self.bonus_max_hp
        hp = base + bonus
        boss = StatWeight.get_health_value_for_boss_rating(self.boss_rating)
        hp += boss
        if hp <= 0:
            raise ValueError(
                f"Max hp is negative, this should never happen. base: {base}, bonus: {bonus}, boss: {boss}"
            )
        return hp

    def create_wound(self, severity=SERIOUS_WOUND):
        from world.traits.models import Trait

        trait = Trait.get_random_physical_stat()
        self.character.health_status.wounds.create(severity=severity, trait=trait)
        del self.character.health_status.cached_wounds

    def cure_permanent_wound(self, trait_name: str) -> bool:
        """Returns True if we deleted a permanent wound, False otherwise"""
        trait = Trait.get_instance_by_name(trait_name)
        return self.character.health_status.heal_permanent_wound_for_trait(trait)

    def remove_last_skill_purchase_record(self, trait_name: str) -> int:
        trait = Trait.get_instance_by_name(trait_name)
        purchase = (
            self.character.trait_purchases.filter(trait=trait).order_by("cost").last()
        )
        if not purchase:
            raise ValueError("No purchase found")
        cost = purchase.cost
        purchase.delete()
        return cost

    def record_skill_purchase(self, trait_name: str, cost):
        trait = Trait.get_instance_by_name(trait_name)
        self.character.trait_purchases.create(trait=trait, cost=cost)
