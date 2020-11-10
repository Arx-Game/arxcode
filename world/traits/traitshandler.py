"""
The traitshandler is an abstraction layer for getting stats/skills for a character
in which data storage is hidden. The original implementation of stats/skills were using
Evennia attributes, which resulted in extremely denormalized data. Moving them to an
abstraction layer both allows for caching and hiding data storage, allowing for ease
of refactoring.
"""
import random
from typing import Dict, List
from world.stats_and_skills import (
    _parent_abilities_,
    DOM_SKILLS,
)
from world.traits.models import CharacterTraitValue, Trait
from world.traits.exceptions import InvalidTrait
from collections import defaultdict, namedtuple

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
        self.setup_cache()

    def setup_cache(self, reset=False):
        """Set our character's trait values in the cache, with case-insensitive keys by trait name"""
        if not reset and self.initialized:
            return
        for trait_value in self.character.trait_values.all():
            self.add_trait_value_to_cache(trait_value)
        self.initialized = True

    def add_trait_value_to_cache(self, trait_value: CharacterTraitValue):
        self._cache[trait_value.trait.get_trait_type_display()][
            trait_value.trait.name.lower()
        ] = trait_value

    def get_skill_value(self, name: str) -> int:
        return self.skills.get(name, 0)

    def get_stat_value(self, name: str) -> int:
        return self.stats.get(name, 0)

    def set_stat_value(self, name: str, value: int):
        self.set_trait_value("stat", name, value)

    def set_skill_value(self, name: str, value: int):
        self.set_trait_value("skill", name, value)

    def get_ability_value(self, name: str) -> int:
        return self.abilities.get(name, 0)

    def set_ability_value(self, name: str, value: int):
        self.set_trait_value("ability", name, value)

    def set_trait_value(self, trait_type: str, name: str, value: int):
        """Deletes or sets up a trait value for a character, updating our cache"""
        # if our value is 0 or lower, delete the trait value
        if value <= 0:
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

    # physical stats
    def __getattr__(self, name):
        names = Trait.get_valid_stat_names()
        if name in names:
            return self.stats.get(name, 0)
        raise AttributeError(f"{name} not found in {names}.")

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
        current = self.get_stat_value(field)
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
