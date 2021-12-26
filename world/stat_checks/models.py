from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.forms import ValidationError
from server.utils.arx_utils import CachedProperty
from evennia.utils.idmapper.models import SharedMemoryModel
from jinja2 import Environment, BaseLoader
from typing import Union, List, TYPE_CHECKING, Dict
from random import randint

from server.utils.abstract_models import NameLookupModel, NameIntegerLookupModel

from world.stat_checks.constants import (
    NONE,
    DEATH,
    UNCONSCIOUSNESS,
    CAUSE_SERIOUS_WOUND,
    CAUSE_PERMANENT_WOUND,
    HEAL,
    HEAL_AND_CURE_WOUND,
    HEAL_UNCON_HEALTH,
    AUTO_WAKE,
    ATTACK_SYSTEM,
)


if TYPE_CHECKING:
    from typeclasses.characters import Character


class DifficultyRating(NameIntegerLookupModel):
    """Lookup table for difficulty ratings for stat checks, mapping names
    to minimum values for that range.

    Deprecated - moving to having a DifficultyTable which is chosen for a given
    check based on the roller CheckRank vs the Target CheckRank.
    """

    @classmethod
    def get_average_difficulty(cls) -> "DifficultyRating":
        instances = cls.get_all_instances()
        return instances[int(len(instances) / 2)]


class StatWeight(SharedMemoryModel):
    """Lookup table for the weights attached to different stat/skill/knack levels"""

    _cache_set = False
    (
        SKILL,
        STAT,
        ABILITY,
        KNACK,
        ONLY_STAT,
        HEALTH_STA,
        HEALTH_BOSS,
        MISC,
        TRAIT,
        ONLY_TRAIT,
    ) = range(10)
    STAT_CHOICES = (
        (SKILL, "skill"),
        (STAT, "stat"),
        (ABILITY, "ability"),
        (KNACK, "knack"),
        (ONLY_STAT, "stat with no skill"),
        # if more things start to play into health probably change to FK to traits
        (HEALTH_STA, "health for stamina"),
        (HEALTH_BOSS, "health for boss rating"),
        (MISC, "miscellaneous values (armor class, etc)"),
        (TRAIT, "trait in new check system"),
        (ONLY_TRAIT, "trait as a lone value in new check system"),
    )
    stat_type = models.PositiveSmallIntegerField(choices=STAT_CHOICES, default=SKILL)
    level = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="minimum level of stat for this weight",
        help_text="Set the level for the minimum rating in the stat for this "
        "weight to be used. With the default of 0 and no other weights set for "
        "this type, all levels of the type of stat (stat, skill, etc) will add "
        "a linear amount rather than curving.",
    )
    weight = models.SmallIntegerField(
        default=1,
        verbose_name="weight for this level of the stat",
        help_text="This is the multiplier for how much to add to a roll for a stat/skill "
        "of at least this level, until it encounters a higher level value you assign. "
        "For example, a StatWeight(stat_type=STAT, level=0, weight=1) would give +1 for "
        "each level of the stat. If you added a StatWeight(stat_type=STAT, level=6, "
        "weight=10), then if they have a stat of 7 they would get 5 + 20.",
    )

    @classmethod
    def get_all_instances(cls):
        if cls._cache_set:
            return cls.get_all_cached_instances()
        # performs the query and populates the SharedMemoryModel cache
        values = list(cls.objects.all())
        cls._cache_set = True
        return values

    @classmethod
    def get_weighted_value_for_stat(
        cls, level: int, only_stat: bool, new_check: bool = False
    ) -> int:
        if new_check:
            stat_type = cls.ONLY_TRAIT if only_stat else cls.TRAIT
        else:
            stat_type = cls.ONLY_STAT if only_stat else cls.STAT
        return cls.get_weighted_value_for_type(level, stat_type)

    @classmethod
    def get_weighted_value_for_skill(cls, level: int, new_check: bool = False) -> int:
        stat_type = cls.TRAIT if new_check else cls.SKILL
        return cls.get_weighted_value_for_type(level, stat_type)

    @classmethod
    def get_weighted_value_for_ability(cls, level: int, new_check: bool = False) -> int:
        stat_type = cls.TRAIT if new_check else cls.ABILITY
        return cls.get_weighted_value_for_type(level, stat_type)

    @classmethod
    def get_weighted_value_for_knack(cls, level: int) -> int:
        return cls.get_weighted_value_for_type(level, cls.KNACK)

    @classmethod
    def get_health_value_for_stamina(cls, level: int) -> int:
        return cls.get_weighted_value_for_type(
            level, cls.HEALTH_STA, require_matches=True
        )

    @classmethod
    def get_health_value_for_boss_rating(cls, level: int) -> int:
        return cls.get_weighted_value_for_type(level, cls.HEALTH_BOSS)

    @classmethod
    def get_weighted_value_for_type(
        cls, level: int, stat_type: int, require_matches=False
    ) -> int:
        """
        Given a type of stat and the level we have in that stat, get the total amount that
        should be added to rolls for that level. For example, if we have a strength of 3,
        what does that modify rolls by? 3? 20? Over NINE THOUSAND? This gets our weights
        that are applicable and aggregates them.
        """
        weights = sorted(cls.get_all_instances(), key=lambda x: x.level)
        matches = [
            ob for ob in weights if ob.stat_type == stat_type and ob.level <= level
        ]
        if require_matches and not matches:
            raise StatWeight.DoesNotExist(
                f"No match found for stat_type: {stat_type} level: {level}. "
                f"Available cached instances: {cls.get_all_instances()}."
            )
        total = 0
        for stat_weight in matches:
            # determine how many times this stat_weight should apply
            index = matches.index(stat_weight)
            # if we're the last match in the stat weights that applies to this level:
            if (index + 1) == len(matches):
                # number of levels this weight affects is the difference between the PC's stat level and the level + 1
                # e.g: if a stat_weight affects all stats 4 and higher, and the PC has a level of 5, they get 2*weight
                num_levels = (level - stat_weight.level) + 1
                total += num_levels * stat_weight.weight
            else:  # get the number of times to apply between this and our next match
                next_weight = matches[index + 1]
                num_levels = next_weight.level - stat_weight.level
                total += num_levels * stat_weight.weight

        return total

    def __str__(self):
        return (
            f"{self.get_stat_type_display()}: level: {self.level} weight: {self.weight}"
        )


class NaturalRollType(NameIntegerLookupModel):
    """
    Deprecated - moving to a system where outcomes are determined by getting a difficulty
    table and all outcomes being a natural roll upon that table. Crits/botches will be
    high/low outcomes on the table.
    """

    LOWER_BOUND, UPPER_BOUND = range(2)
    BOUNDARY_CHOICES = ((LOWER_BOUND, "lower bound"), (UPPER_BOUND, "upper bound"))
    value_type = models.PositiveSmallIntegerField(
        "The type of boundary for value",
        choices=BOUNDARY_CHOICES,
        default=LOWER_BOUND,
        help_text="If this is a lower bound, then rolls higher than value are"
        " of this type. If it's an upper bound, then rolls lower than it "
        "are of this type. It finds the closest boundary for the roll. So "
        "for example, you could have 'crit' of value 95, and then a higher "
        "crit called 'super crit' with a lower bound of 98, for 98-100 rolls.",
    )
    result_shift = models.SmallIntegerField(
        default=0,
        help_text="The number of levels to shift the result by, whether up "
        "or down. 1 for a crit would shift the result up by 1, such that "
        "a normal success turns into the level above normal. Use negative"
        " numbers for a botch/fumble (which should have an upper bound "
        "value type).",
    )

    @property
    def is_crit(self):
        return self.value_type == self.LOWER_BOUND

    @property
    def is_botch(self):
        return self.value_type == self.UPPER_BOUND

    @classmethod
    def get_roll_type(cls, roll: int) -> Union[None, "NaturalRollType"]:
        """
        Returns an instance of a crit, botch, or nothing depending if their roll falls within
        any of our bounds
        """
        # instances will be in order of worst botch to highest crit
        instances = sorted(cls.get_all_instances(), key=lambda x: x.value)
        # check if roll was high enough to be a crit, get highest value it passed
        crits = [
            ob
            for ob in instances
            if ob.value_type == cls.LOWER_BOUND and roll >= ob.value
        ]
        if crits:
            return crits[-1]
        # check if roll was low enough to be a botch. Get lowest botch it passed
        botches = [
            ob
            for ob in instances
            if ob.value_type == cls.UPPER_BOUND and roll <= ob.value
        ]
        if botches:
            return botches[0]


class RollResult(NameIntegerLookupModel):
    """Lookup table for results of rolls, whether success or failure."""

    template = models.TextField(
        help_text="A jinja2 template string that will be output with "
        "the message for this result. 'character' is the context variable "
        "for the roller: eg: '{{character}} fumbles.'"
    )

    @property
    def is_success(self):
        return self.value >= 0

    @classmethod
    def get_instance_for_roll(
        cls, roll: int, natural_roll_type: Union["NaturalRollType", None] = None
    ):
        instances = sorted(cls.get_all_instances(), key=lambda x: x.value)
        if not instances:
            raise ValueError(
                "No ResultMessage objects have yet been defined in the database."
            )
        # get index of the result that most closely corresponds to our roll, then shift by result_shift if any
        # find highest result the roll is higher than, or return our lowest value
        closest = max(
            [ob for ob in instances if ob.value <= roll],
            key=lambda x: x.value,
            default=instances[0],
        )
        # if we don't have a crit/botch, just return the closest result
        if not natural_roll_type:
            return closest
        index = instances.index(closest)
        index += natural_roll_type.result_shift
        # this means they botched so badly they would have gotten below the worst botch. Press F to pay respects
        if index < 0:
            return instances[0]
        # they critted so well that they would have gotten above the top result. Trumpets sound and peasants cheer
        if index >= len(instances):
            return instances[-1]
        # they got within the acceptable range of screwing up or being awesome
        return instances[index]

    def render(self, **data):
        return Environment(loader=BaseLoader()).from_string(self.template).render(data)


class DamageRating(NameIntegerLookupModel):
    """Mapping of how much damage harm does, mapping severity to damage amount"""

    value = models.SmallIntegerField("minimum damage")
    max_value = models.SmallIntegerField("maximum damage")
    armor_percentage = models.SmallIntegerField(
        "mitigation percentage",
        help_text="Percentage of armor that is used to reduce damage from max damage "
        "to minimum damage. 100 means they get full value of mitigation, 0 nothing.",
        default=100,
    )

    def do_damage(self, character):
        # roll damage
        damage = randint(self.value, self.max_value)
        # apply mitigation
        damage = self.mitigate_damage(character, damage)
        character.take_damage(damage, quiet=False)

    def mitigate_damage(self, character, damage) -> int:
        # resists aren't affected by armor reduction
        resists = character.traits.armor_class
        # reduce damage by mitigation (not including resists) that's reduced by multiplier
        damage -= (character.armor - resists) * (self.armor_percentage / 100.0)
        # can only take down to minimum damage value this way
        if damage < self.value:
            damage = self.value
        # resists allow damage to go below min value
        damage -= resists
        if damage < 0:
            damage = 0
        return int(damage)


class StatCheck(NameLookupModel):
    """
    Stores data on how a type of check is made. It points to a DiceSystem which
    defines what combination of stats and skills are rolled. It then has
    descriptions of different outcomes that correspond to results of the roll.
    """

    # the system used by this stat check
    dice_system = models.ForeignKey(
        "StatCombination",
        on_delete=models.PROTECT,
        related_name="stat_checks",
    )
    description = models.TextField(blank=True)
    public = models.BooleanField(default=True)
    category = models.CharField(blank=True, max_length=50, default="general")

    @CachedProperty
    def cached_difficulty_rules(self):
        return list(self.difficulty_rules.all())

    @CachedProperty
    def cached_outcomes(self):
        return list(self.outcomes.all())

    def get_value_for_traits(self, character) -> int:
        return self.dice_system.get_value_for_stat_combinations(character)

    def get_value_for_difficulty_rating(self, character, **kwargs) -> int:
        return self.get_difficulty_rating(character, **kwargs).value

    def get_difficulty_rating(self, character, **kwargs):
        # get rules for checking the situation
        for rule in self.triggers:
            if rule.situation.character_should_trigger(character, **kwargs):
                return rule.difficulty
        # if we only have a single difficulty, return that
        if len(self.cached_difficulty_rules) == 1:
            return self.cached_difficulty_rules[0].difficulty
        # return normal difficulty as default
        return DifficultyRating.get_average_difficulty()

    @property
    def triggers(self):
        rules = [rule for rule in self.cached_difficulty_rules if rule.situation]
        rules.sort(key=lambda x: x.situation.value, reverse=True)
        return rules

    def get_stats_list(self, character) -> List[str]:
        return self.dice_system.get_stats_list(character)

    def get_skills_list(self, character) -> List[str]:
        return self.dice_system.get_skills_list(character)

    def should_trigger(self, character, **kwargs):
        for rule in self.triggers:
            if rule.situation.character_should_trigger(character, **kwargs):
                return True
        return False

    def get_outcome_for_result(self, result):
        """This examines out different outcomes and compares it to the provided result.
        It tries to return the closest match of an outcome to the result we're looking for.
        If there's a direct match, it'll provide that outcome. Otherwise, it'll try to find
        the outcome with a result that's just below our given result. If there's no such
        outcome, that means all outcomes are greater than the result we have, so we grab
        the lowest of the ones remaining.
        """
        if not self.cached_outcomes:
            return
        # get direct match
        try:
            return [
                outcome for outcome in self.cached_outcomes if outcome.result == result
            ][0]
        except IndexError:
            pass
        # get first outcome that is greater than the result we're looking for
        for outcome in self.cached_outcomes:
            if result.value < outcome.result.value:
                return outcome
        # all remaining outcomes are worse than the result we're looking for, get the highest
        try:
            return [
                outcome
                for outcome in self.cached_outcomes
                if outcome.result.value < result.value
            ][-1]
        except IndexError:
            pass

    def get_difficulty_table_for_roller(
        self, character: "Character", target_rank: "CheckRank"
    ) -> "DifficultyTable":
        totals = character.traits.get_totals_for_check(self)
        value = sum(totals.values())
        return CheckRank.get_table_for_value(value, target_rank)


class StatCombination(SharedMemoryModel):
    """
    A StatCombination is a way to capture the nested structure of different
    stat/skill combinations of arbitrary complexity.
    """

    SUM, USE_HIGHEST, USE_LOWEST = range(3)
    COMBINATION_CHOICES = (
        (SUM, "Add Values Together"),
        (USE_HIGHEST, "Use the Highest Value"),
        (USE_LOWEST, "Use the Lowest Value"),
    )
    DYNAMIC_SYSTEM_CHOICES = (
        (NONE, "Not a dynamic system"),
        (ATTACK_SYSTEM, "Character Attack System"),
    )
    combined_into = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="child_combinations",
        null=True,
        blank=True,
    )
    combination_type = models.PositiveSmallIntegerField(
        choices=COMBINATION_CHOICES, default=SUM
    )
    traits = models.ManyToManyField(
        "traits.Trait", through="TraitsInCombination", related_name="stat_combinations"
    )
    flat_value = models.SmallIntegerField(
        null=True, help_text="If defined, this value is also used.", blank=True
    )
    random_ceiling = models.SmallIntegerField(
        null=True,
        help_text="If defined, value is random between flat value and this ceiling.",
        blank=True,
    )
    dynamic_system = models.PositiveSmallIntegerField(
        choices=DYNAMIC_SYSTEM_CHOICES,
        default=NONE,
    )

    def clean(self):
        cleaned_data = super().clean()
        flat_value = cleaned_data.get("flat_value")
        random_ceiling = cleaned_data.get("random_ceiling")
        if random_ceiling and flat_value:
            if random_ceiling <= flat_value:
                raise ValidationError(
                    "random_ceiling must be greater than flat_value if they are defined."
                )

    @CachedProperty
    def should_be_stat_only(self):
        """Checks the tree to see if we should use the weight for having a stat alone"""
        if self.combined_into:
            return self.combined_into.should_be_stat_only
        if self.combination_type == self.SUM:
            return (
                len(self.cached_traits_in_combination)
                + len(self.cached_child_combinations)
                <= 1
            )
        return True

    @CachedProperty
    def cached_traits_in_combination(self):
        return list(self.trait_combination_values.all())

    @CachedProperty
    def cached_child_combinations(self):
        return list(self.child_combinations.all())

    @CachedProperty
    def cached_stat_checks(self):
        return list(self.stat_checks.all())

    def get_value_for_stat_combinations(
        self,
        character: "Character",
        new_check: bool = False,
    ) -> int:
        values = []
        if self.dynamic_system == ATTACK_SYSTEM:
            # add total to character from values
            values.append(character.combat.get_total_for_attack_check())
        for trait in self.cached_traits_in_combination:
            values.append(trait.get_roll_value_for_character(character, new_check))
        for combination in self.cached_child_combinations:
            values.append(
                combination.get_value_for_stat_combinations(character, new_check)
            )
        # see if we have a flat value to add, which may be random
        if self.random_ceiling is not None:
            values.append(randint(self.flat_value or 0, self.random_ceiling))
        elif self.flat_value is not None:
            values.append(self.flat_value)
        if self.combination_type == self.SUM:
            return sum(values)
        if self.combination_type == self.USE_HIGHEST:
            return max(values)
        if self.combination_type == self.USE_LOWEST:
            return min(values)
        raise ValueError(f"Using undefined combination type: {self.combination_type}")

    def get_all_traits(self):
        traits = []
        for trait in self.cached_traits_in_combination:
            traits.append(trait.trait)
        for child in self.cached_child_combinations:
            traits.extend(child.get_all_traits())
        return traits

    def get_stats_list(self, character) -> List[str]:
        extra_stats = []
        if self.dynamic_system == ATTACK_SYSTEM:
            extra_stats = [character.combat.get_system_for_current_attack().attack_stat]
        return [
            trait.name.lower()
            for trait in self.get_all_traits()
            if trait.trait_type == trait.STAT
        ] + extra_stats

    def get_skills_list(self, character) -> List[str]:
        extra_skills = []
        if self.dynamic_system == ATTACK_SYSTEM:
            extra_skills = [
                character.combat.get_system_for_current_attack().attack_skill
            ]
        return [
            trait.name.lower()
            for trait in self.get_all_traits()
            if trait.trait_type == trait.SKILL
        ] + extra_skills

    def __str__(self):
        return self.display_system_for_character()

    def display_system_for_character(self, character=None):
        children = self.cached_child_combinations + self.cached_traits_in_combination
        if self.dynamic_system == ATTACK_SYSTEM:
            if character:
                children += (
                    character.combat.get_system_for_current_attack().all_traits()
                )
            else:
                children.append(self.get_dynamic_system_display())
        child_strings = sorted([str(ob) for ob in children])
        base = f"{self.get_combination_type_display()}: [{', '.join(child_strings)}]"
        if self.random_ceiling:
            base += f" + ({self.flat_value or 0} to {self.random_ceiling})"
        elif self.flat_value:
            base += f" + {self.flat_value}"
        return base


class TraitsInCombination(SharedMemoryModel):
    """
    This represents traits that are used in a stat combination for a check.
    The trait can have a multiplier/divisor attached to it to allow for weighting
    its value. The stat combination then determines how these values are used -
    whether added together, using the highest, etc. For example, to have an average
    of stats used for a roll, the StatCombination's combination_type would be SUM,
    and you would set the value_divisor for each trait to be the number of traits
    in the combination.
    """

    trait = models.ForeignKey(
        "traits.Trait",
        on_delete=models.CASCADE,
        related_name="trait_combination_values",
    )
    stat_combination = models.ForeignKey(
        "StatCombination",
        on_delete=models.CASCADE,
        related_name="trait_combination_values",
    )
    value_multiplier = models.PositiveSmallIntegerField(
        default=1, help_text="This is to make a value count more."
    )
    value_divisor = models.PositiveSmallIntegerField(
        default=1, help_text="This can be used to average values in a combination."
    )

    class Meta:
        unique_together = ("stat_combination", "trait")

    def __str__(self):
        base = str(self.trait)
        if self.value_multiplier != 1:
            base += f"* {self.value_multiplier}"
        if self.value_divisor != 1:
            base += f"/ {self.value_divisor}"
        return base

    @property
    def should_be_stat_only(self):
        return self.stat_combination.should_be_stat_only

    def get_roll_value_for_character(self, character, new_check=False) -> int:
        base_value = character.traits.get_value_by_trait(self.trait)
        # if it's a trait type we have weights for, we'll return that
        if self.trait.trait_type == self.trait.STAT:
            base_value = StatWeight.get_weighted_value_for_stat(
                base_value, self.should_be_stat_only, new_check
            )
        if self.trait.trait_type == self.trait.SKILL:
            base_value = StatWeight.get_weighted_value_for_skill(
                base_value, new_check=new_check
            )
        if self.trait.trait_type == self.trait.ABILITY:
            base_value = StatWeight.get_weighted_value_for_ability(
                base_value, new_check=new_check
            )
        base_value *= self.value_multiplier
        if self.value_divisor:
            base_value /= self.value_divisor
        # it's an 'other' trait, it'll be unweighted
        return int(base_value)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        try:
            del self.stat_combination.cached_traits_in_combination
        except AttributeError:
            pass


class StatCheckOutcome(SharedMemoryModel):
    """Provides a way to have a description of what happens for a given result"""

    EFFECT_CHOICES = (
        (NONE, "none"),
        (DEATH, "death"),
        (UNCONSCIOUSNESS, "unconsciousness"),
        (CAUSE_SERIOUS_WOUND, "serious wound"),
        (CAUSE_PERMANENT_WOUND, "permanent wound"),
        (HEAL, "healing"),
        (HEAL_AND_CURE_WOUND, "healing and cure a wound"),
        (HEAL_UNCON_HEALTH, "regain below-0% health"),
        (AUTO_WAKE, "recover from unconsciousness"),
    )

    stat_check = models.ForeignKey(
        "StatCheck", related_name="outcomes", on_delete=models.CASCADE
    )
    result = models.ForeignKey(
        "RollResult", related_name="outcomes", on_delete=models.PROTECT
    )
    description = models.TextField(
        help_text="A description for players/GMs of what this given result "
        "means in game"
    )

    effect = models.PositiveSmallIntegerField(
        default=NONE,
        help_text="A coded effect that you want to have trigger.",
        choices=EFFECT_CHOICES,
    )

    stat_combination = models.ForeignKey(
        "StatCombination",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="stat_check_outcomes",
        help_text="If defined, this stat combination is used to calculate a value for the effect.",
    )

    def __str__(self):
        val = f"Outcome of {self.result} for {self.stat_check}"
        if self.effect != NONE:
            val += f", Effect: {self.get_effect_display()}"
        return val

    def get_value(self, character):
        if not self.stat_combination:
            return 0
        return self.stat_combination.get_value_for_stat_combinations(character)

    class Meta:
        unique_together = ("stat_check", "result")
        ordering = ("result__value",)


class CheckDifficultyRule(SharedMemoryModel):
    """Maps different difficulties to a stat check with reasons why"""

    stat_check = models.ForeignKey(
        "StatCheck", related_name="difficulty_rules", on_delete=models.CASCADE
    )
    difficulty = models.ForeignKey(
        "DifficultyRating", related_name="difficulty_rules", on_delete=models.CASCADE
    )
    description = models.TextField(
        blank=True,
        help_text="Description for GMs of when this difficulty rating applies.",
    )

    situation = models.ForeignKey(
        "CheckCondition",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        help_text="Allows you to define a specific circumstance of when this difficulty "
        "rating should apply, usually in automated checks.",
    )

    def __str__(self):
        return f"Rule for {self.stat_check}: {self.difficulty}"


class CheckCondition(SharedMemoryModel):
    """
    A circumstance for either calling for a check or for mapping to a specific difficulty
    for a check. This will determine things like at what percent health a death save is called for,
    or an unconsciousness check, or a check for a permanent wound from a large single attack, or
    the difficulty for these checks by an associated CheckDifficultyRule.
    """

    MISSING_PERCENT_HEALTH, PERCENT_HEALTH_INFLICTED, HEALTH_BELOW_100 = range(3)
    CONDITION_CHOICES = (
        (MISSING_PERCENT_HEALTH, "Percentage of health missing"),
        (PERCENT_HEALTH_INFLICTED, "Percent health inflicted by attack"),
        (HEALTH_BELOW_100, "Flat value of health below 100"),
    )
    condition_type = models.PositiveSmallIntegerField(
        choices=CONDITION_CHOICES, default=MISSING_PERCENT_HEALTH
    )
    value = models.SmallIntegerField(default=0)

    class Meta:
        unique_together = ("condition_type", "value")

    def character_should_trigger(self, character, **kwargs):
        if self.condition_type == self.MISSING_PERCENT_HEALTH:
            return character.get_damage_percentage() >= self.value
        elif self.condition_type == self.PERCENT_HEALTH_INFLICTED:
            percent_damage = kwargs.get("percent_damage", 0)
            return percent_damage >= self.value
        elif self.condition_type == self.HEALTH_BELOW_100:
            return (100 - character.current_hp) >= self.value

        raise ValueError(
            f"Invalid condition_type set in this CheckCondition: {self.condition_type}"
        )

    def __str__(self):
        return f"{self.get_condition_type_display()}: {self.value}"


class CheckRank(NameIntegerLookupModel):
    """
    Given some total value for stats, skills, and other modifiers for a check,
    we determine a rank that someone will use when making the check as a
    measure of their relative power. Ranks are them compared to one another to
    get a chart that determines the outcomes of a roll.
    """

    id = models.SmallIntegerField(
        primary_key=True, help_text="The rank number itself (rank 1, rank 2, etc)."
    )
    description = models.TextField()
    value = models.SmallIntegerField("minimum check value for this rank", unique=True)

    def __str__(self):
        return self.name

    def __add__(self, other):
        return self.id + other.id

    def __sub__(self, other):
        return self.id - other.id

    @classmethod
    def get_base_rank_for_value(cls, value: int) -> "CheckRank":
        instances = sorted(cls.get_all_instances(), key=lambda x: x.value)
        if not instances:
            raise ValueError(
                "No CheckRank objects have yet been defined in the database."
            )
        # get highest rank that our value is over
        closest = max(
            [ob for ob in instances if ob.value <= value],
            key=lambda x: x.value,
            default=instances[0],
        )
        return closest

    @classmethod
    def get_chance_of_higher_rank(cls, value: int) -> int:
        """Given a rank, gives the percentage chance that we get a higher rank than this one"""
        closest = cls.get_base_rank_for_value(value)
        # if we're exactly at the value, we have no chance of getting higher
        progress = value - closest.value
        if progress <= 0:
            return 0
        try:
            next_value = cls.objects.get(id=closest.id + 1)
        except cls.DoesNotExist:
            return 0
        distance = next_value.value - closest.value
        # get their percentage chance of getting the next rank
        chance = (progress / distance) * 100
        return int(chance)

    @classmethod
    def get_table_for_value(cls, value, target_rank):
        rank = cls.get_base_rank_for_value(value)
        chance = cls.get_chance_of_higher_rank(value)
        if randint(1, 100) <= chance:
            try:
                rank = cls.objects.get(id=rank.id + 1)
            except cls.DoesNotExist:
                pass
        return DifficultyTable.get_difficulty_for_rank_range(rank, target_rank)


class DifficultyTable(NameIntegerLookupModel):
    """
    A DifficultyTable is a chart chosen by its value, which represents the
    difference between a roller's CheckRank and their target CheckRank. For
    example, if a roller has a CR of 5 and their target was 2, we would use
    the DifficultyTable with a value of 3, which might report it's an 'easy'
    roll. They then make a random() roll on this table, and that maps to
    different RollResults, with the closest being returned.
    """

    roll_results = models.ManyToManyField(
        "RollResult",
        through="DifficultyTableResultRange",
        related_name="difficulty_tables",
    )

    @classmethod
    def get_difficulty_for_rank_range(
        cls, roller_rank: "CheckRank", target_rank: "CheckRank"
    ) -> "DifficultyTable":
        # the higher the better for the roller
        value = roller_rank.id - target_rank.id
        instances = sorted(cls.get_all_instances(), key=lambda x: x.value)
        if not instances:
            raise ValueError(
                "No DifficultyTable objects have yet been defined in the database."
            )
        # get highest rank that our value is over
        closest = max(
            [ob for ob in instances if ob.value <= value],
            key=lambda x: x.value,
            default=instances[0],
        )
        return closest

    @CachedProperty
    def cached_ranges(self) -> List["DifficultyTableResultRange"]:
        return list(self.result_ranges.all().order_by("value"))

    @property
    def ranges_dict(self) -> Dict[int, "RollResult"]:
        return {
            difficulty_range.value: difficulty_range.result
            for difficulty_range in self.cached_ranges
        }

    def get_result_for_roll(self) -> "RollResult":
        roll = randint(1, 100)
        instances = self.cached_ranges
        if not instances:
            raise ValueError(f"No results found for {self}.")
        closest: DifficultyTableResultRange = max(
            [ob for ob in instances if ob.value <= roll],
            key=lambda x: x.value,
            default=instances[0],
        )
        return closest.result

    def display_table_values(self):
        values = "\n".join(
            f"  [Min Roll: |c{key}|n Result: |c{value}|n]"
            for key, value in self.ranges_dict.items()
        )
        return f"|wValues:|n\n{values}"


class DifficultyTableResultRange(SharedMemoryModel):
    difficulty_table = models.ForeignKey(
        "DifficultyTable", related_name="result_ranges", on_delete=models.CASCADE
    )
    result = models.ForeignKey(
        "RollResult", related_name="result_ranges", on_delete=models.CASCADE
    )
    value = models.IntegerField(
        default=1, validators=[MaxValueValidator(100), MinValueValidator(1)]
    )

    class Meta:
        unique_together = (
            ("difficulty_table", "result"),
            ("difficulty_table", "value"),
        )
        verbose_name_plural = "Difficulty Table Result Ranges"

    def __str__(self):
        return f"{self.value} - {self.result}"
