from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel
from jinja2 import Environment, BaseLoader
from typing import Union


class NameIntegerLookupModel(SharedMemoryModel):
    """
    This abstract class will primarily be used for small lookup tables that can be queried once and
    then stored in memory.
    """

    _cache_set = False
    _name_to_id_map = dict()
    name = models.CharField(unique=True, max_length=150)
    value = models.SmallIntegerField(
        verbose_name="minimum value for this difficulty range/rating", unique=True
    )

    class Meta:
        abstract = True

    @classmethod
    def cache_instance(cls, instance, new=False):
        """Override of cache instance with pk cast to lowercase to be case insensitive"""
        super().cache_instance(instance, new)
        cls._name_to_id_map[instance.name] = instance.id

    @classmethod
    def get_all_instances(cls):
        if cls._cache_set:
            return sorted(cls.get_all_cached_instances(), key=lambda x: x.value)
        # performs the query and populates the SharedMemoryModel cache
        values = list(cls.objects.all().order_by("value"))
        cls._cache_set = True
        cls._name_to_id_map = {
            instance.name.lower(): instance.id for instance in values
        }
        return values

    def __str__(self):
        return self.name

    @classmethod
    def get_instance_by_name(cls, name):
        cls.get_all_instances()
        pk = cls._name_to_id_map.get(name.lower())
        return cls.get_cached_instance(pk)

    def save(self, *args, **kwargs):
        ret = super().save(*args, **kwargs)
        # store the new name to pk mapping
        type(self)._name_to_id_map[self.name.lower()] = self.id
        return ret


class DifficultyRating(NameIntegerLookupModel):
    """Lookup table for difficulty ratings for stat checks, mapping names
    to minimum values for that range."""

    pass


class StatWeight(SharedMemoryModel):
    """Lookup table for the weights attached to different stat/skill/knack levels"""

    _cache_set = False
    SKILL, STAT, ABILITY, KNACK, ONLY_STAT, HEALTH_STA, HEALTH_BOSS = range(7)
    STAT_CHOICES = (
        (SKILL, "skill"),
        (STAT, "stat"),
        (ABILITY, "ability"),
        (KNACK, "knack"),
        (ONLY_STAT, "stat with no skill"),
        (HEALTH_STA, "health for stamina"),
        (HEALTH_BOSS, "health for boss rating"),
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
    def get_weighted_value_for_stat(cls, level: int, only_stat: bool) -> int:
        stat_type = cls.ONLY_STAT if only_stat else cls.STAT
        return cls.get_weighted_value_for_type(level, stat_type)

    @classmethod
    def get_weighted_value_for_skill(cls, level: int) -> int:
        return cls.get_weighted_value_for_type(level, cls.SKILL)

    @classmethod
    def get_weighted_value_for_knack(cls, level: int) -> int:
        return cls.get_weighted_value_for_type(level, cls.KNACK)

    @classmethod
    def get_health_value_for_stamina(cls, level: int) -> int:
        return cls.get_weighted_value_for_type(level, cls.HEALTH_STA)

    @classmethod
    def get_weighted_value_for_type(cls, level: int, stat_type: int) -> int:
        """
        Given a type of stat and the level we have in that stat, get the total amount that
        should be added to rolls for that level. For example, if we have a strength of 3,
        what does that modify rolls by? 3? 20? Over NINE THOUSAND? This gets our weights
        that are applicable and aggregates them.
        """
        weights = sorted(cls.get_all_instances(), key=lambda x: x.level, reverse=True)
        matches = [
            ob for ob in weights if ob.stat_type == stat_type and ob.level <= level
        ]
        total = 0
        for stat_weight in matches:
            # number of levels this weight affects is the difference between the PC's stat level and the level + 1
            # e.g: if a stat_weight affects all stats 4 and higher, and the PC has a level of 5, they get 2*weight
            num_levels = (level - stat_weight.level) + 1
            total += num_levels * stat_weight.weight
            # reduce our level so that the weights aren't counted multiple times
            # e.g: so if we have +1 for levels 1-3 and +2 for 4-5, we don't get +3 for levels 4 and 5
            level = stat_weight.level
        return total


class NaturalRollType(NameIntegerLookupModel):
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
    armor_cap = models.SmallIntegerField(
        help_text="Percent of damage armor can prevent. 100 means armor can completely"
        " negate the attack."
    )

    def do_damage(self, character):
        pass
