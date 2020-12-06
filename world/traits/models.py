from django.db import models
from django.utils.functional import cached_property
from evennia.utils.idmapper.models import SharedMemoryModel
from server.utils.abstract_models import NameIntegerLookupModel, NameLookupModel

from typing import List
from random import choice


class Trait(NameLookupModel):
    """
    This describes a trait that a character can have and any metadata
    associated with it.
    """

    PHYSICAL = "physical"
    SOCIAL = "social"
    MENTAL = "mental"
    MAGIC = "magic"
    COMBAT = "combat"
    GENERAL = "general"
    CRAFTING = "crafting"

    STAT, SKILL, ABILITY, OTHER = range(4)
    TRAIT_TYPE_CHOICES = (
        (STAT, "stat"),
        (SKILL, "skill"),
        (ABILITY, "ability"),
        (OTHER, "other"),
    )
    trait_type = models.PositiveSmallIntegerField(
        default=OTHER, choices=TRAIT_TYPE_CHOICES
    )
    category = models.CharField(
        max_length=80,
        help_text="A category for this type of trait, like 'physical' stats, etc",
    )

    def __str__(self):
        return self.name

    @classmethod
    def get_valid_stat_names(cls, category=None):
        if category:
            return cls.get_valid_trait_names_by_category_and_type(category, cls.STAT)
        return cls.get_valid_trait_names_by_type(cls.STAT)

    @classmethod
    def get_valid_skill_names(cls, category=None):
        if category:
            return cls.get_valid_trait_names_by_category_and_type(category, cls.SKILL)
        return cls.get_valid_trait_names_by_type(cls.SKILL)

    @classmethod
    def get_valid_ability_names(cls, category=None):
        if category:
            return cls.get_valid_trait_names_by_category_and_type(category, cls.ABILITY)
        return cls.get_valid_trait_names_by_type(cls.ABILITY)

    @classmethod
    def get_valid_other_names(cls, category=None):
        if category:
            return cls.get_valid_trait_names_by_category_and_type(category, cls.OTHER)
        return cls.get_valid_trait_names_by_type(cls.OTHER)

    @classmethod
    def get_valid_trait_names_by_type(cls, trait_type: int) -> List[str]:
        return [
            ob.name.lower()
            for ob in cls.get_all_instances()
            if ob.trait_type == trait_type
        ]

    @classmethod
    def get_valid_trait_names_by_category_and_type(
        cls, category: str, trait_type: int
    ) -> List[str]:
        return [
            ob.name.lower()
            for ob in cls.get_all_instances()
            if ob.category == category and ob.trait_type == trait_type
        ]

    @classmethod
    def get_random_physical_stat(cls):
        physical_stats = [
            ob
            for ob in cls.get_all_instances()
            if ob.category == cls.PHYSICAL and ob.trait_type == cls.STAT
        ]
        return choice(physical_stats)


class CharacterTraitValue(SharedMemoryModel):
    """
    A permanent value that a character has for a trait.
    """

    character = models.ForeignKey(
        "objects.ObjectDB", on_delete=models.CASCADE, related_name="trait_values"
    )
    trait = models.ForeignKey("Trait", on_delete=models.CASCADE)
    value = models.SmallIntegerField(default=0)

    class Meta:
        unique_together = ("character", "trait")

    @cached_property
    def name(self):
        if not self.trait_id:
            return ""
        return self.trait.name

    def __str__(self):
        if self.character_id and self.trait_id:
            return f"{self.character.db_key}'s {self.trait.name}"
        return "Unknown character and trait"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # if we're a character, add the trait to our traitshandler
        try:
            self.character.traits.add_trait_value_to_cache(self)
        except AttributeError:
            pass
