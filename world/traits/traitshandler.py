"""
The traitshandler is an abstraction layer for getting stats/skills for a character
in which data storage is hidden. The original implementation of stats/skills were using
Evennia attributes, which resulted in extremely denormalized data. Moving them to an
abstraction layer both allows for caching and hiding data storage, allowing for ease
of refactoring.
"""
import random
from typing import Dict, List
from world.stats_and_skills import (VALID_SKILLS, VALID_STATS, VALID_ABILITIES,
                                    CRAFTING_SKILLS, _parent_abilities_, DOM_SKILLS,
                                    PHYSICAL_STATS)


class Trait:
    """Wrapper for traits, will later be replaced by a model"""
    def __init__(self, name, value):
        self.name = name
        self.value = value


class Traitshandler:
    """
    Handler that's instantiated with a character, which will then store the instance
    as a cached property on the character.
    """
    def __init__(self, character):
        self.character = character

    def get_skill_value(self, name: str) -> int:
        return self.skills.get(name, 0)

    def get_stat_value(self, name: str) -> int:
        return self.character.attributes.get(name, 0)

    def set_stat_value(self, name: str, value: int):
        self.character.attributes.add(name, value)

    def set_skill_value(self, name: str, value: int):
        self.initialize_skills()
        if value <= 0:
            self.character.db.skills.pop(name)
        self.character.db.skills[name] = value

    def get_ability_value(self, name: str) -> int:
        return self.abilities.get(name, 0)

    def set_ability_value(self, name: str, value: int):
        self.initialize_abilities()
        if value <= 0:
            self.character.db.abilities.pop(name)
        self.character.db.abilities[name] = value

    def get_highest_skill(self, namelist: List[str]) -> Trait:
        """
        Gets the highest trait for list of skill names. If no matches, a ValueError is raised and we choose
        one at random.
        """
        try:
            # get the highest trait from the list of skill names
            return max([Trait(name, self.get_skill_value(name)) for name in namelist], key=lambda x: x.value)
        except ValueError:
            # no match, get one at random
            return Trait(random.choice(namelist), 0)

    # physical stats
    @property
    def strength(self):
        return self.character.db.strength

    @property
    def stamina(self):
        return self.character.db.stamina

    @property
    def dexterity(self):
        return self.character.db.dexterity

    # social stats
    @property
    def charm(self):
        return self.character.db.charm

    @property
    def command(self):
        return self.character.db.command

    @property
    def composure(self):
        return self.character.db.composure

    # mental stats
    @property
    def intellect(self):
        return self.character.db.intellect

    @property
    def perception(self):
        return self.character.db.perception

    @property
    def wits(self):
        return self.character.db.wits

    # special stats
    @property
    def mana(self):
        return self.character.db.mana

    @property
    def luck(self):
        return self.character.db.luck

    @property
    def willpower(self):
        return self.character.db.willpower

    @property
    def skills(self) -> Dict[str, int]:
        return dict(self.character.db.skills or {})

    @skills.setter
    def skills(self, skills_dict: Dict[str, int]):
        self.character.db.skills = skills_dict

    @property
    def abilities(self) -> Dict[str, int]:
        return dict(self.character.db.abilities or {})

    @abilities.setter
    def abilities(self, abilities_dict: Dict[str, int]):
        self.character.db.abilities = abilities_dict

    def initialize_skills(self):
        if self.character.db.skills is None:
            self.character.db.skills = {}

    def initialize_abilities(self):
        if self.character.db.abilities is None:
            self.character.db.abilities = {}

    def initialize_stats(self):
        for stat in VALID_STATS:
            if self.character.attributes.get(stat) is None:
                self.character.attributes.add(stat, 0)

    def wipe_all_skills(self):
        self.skills = {}

    def wipe_all_abilities(self):
        self.abilities = {}

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
        if field not in VALID_STATS:
            raise Exception("Error in adjust_stat: %s not found as a valid stat." % field)
        current = self.get_stat_value(field)
        self.set_stat_value(field, current + value)
        self.character.db.trainer = None

    def adjust_skill(self, field, value=1):
        if field not in VALID_SKILLS:
            raise Exception("Error in adjust_skill: %s not found as a valid skill." % field)
        current = self.get_skill_value(field)
        self.set_skill_value(field, current + value)
        self.character.db.trainer = None
        if field in CRAFTING_SKILLS:
            abilitylist = _parent_abilities_[field]
            for ability in abilitylist:
                if ability not in self.abilities:
                    self.set_ability_value(ability, 1)

    def adjust_ability(self, field, value=1):
        if field not in VALID_ABILITIES:
            raise Exception("Error in adjust_ability: %s not found as a valid ability." % field)
        current = self.get_ability_value(field)
        self.set_ability_value(field, current + value)
        self.character.db.trainer = None

    def adjust_dom(self, field, value=1):
        if field not in DOM_SKILLS:
            raise Exception("Error in adjust_dom: %s not found as a valid dominion skill." % field)
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
        for stat in PHYSICAL_STATS:
            val = source_character.traits.get_stat_value(stat)
            self.set_stat_value(stat, val)
        self.skills = dict(source_character.traits.skills)
