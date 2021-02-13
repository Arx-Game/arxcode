"""
The Conditions app is about status effects and modifiers. This can be anything from holy blessings or
enchantments to mundane diseases or using tools that give bonuses to a particular task.
"""
# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from datetime import datetime
import random

from django.db import models

from evennia.utils.idmapper.models import SharedMemoryModel

from world.conditions.constants import (
    SERIOUS_WOUND,
    PERMANENT_WOUND,
    CONSCIOUS,
    UNCONSCIOUS,
    ASLEEP,
    RECOVERY,
    REVIVE,
    WOUND,
)
from world.conditions.exceptions import TreatmentTooRecentError
from world.conditions.managers import HealthStatusQuerySet, TreatmentAttemptQuerySet
from server.utils.arx_utils import CachedProperty
from world.stat_checks.constants import (
    RECOVERY_CHECK,
    UNCON_SAVE,
    HEAL_AND_CURE_WOUND,
    RECOVERY_TREATMENT,
    REVIVE_TREATMENT,
    REVIVE_EFFECTS,
    AUTO_WAKE,
    HEAL,
)
from world.stat_checks.utils import get_check_maker_by_name


class RollModifier(SharedMemoryModel):
    """
    A modifier to a roll. The modifier can be attached to any ObjectDB, and based on what the object actually is
    will shape how it's used. For example, a room will grant its modifiers to those who are inside it. Armor will
    provide modifiers when worn. Weapons when wielded. Characters have their modifiers innately at all times.
    Modifiers that are caused by conditions will be the responsibility of conditions to apply or remove.
    """

    ANY = 0
    ATTACK = 1
    DAMAGE = 2
    DEFENSE = 3
    HEAL = 4
    STEALTH = 5
    ANY_COMBAT = 6
    PERCEPTION = 7
    CRAFTING = 8
    INVESTIGATION = 9
    CASTING = 10
    CHANNELING = 11
    WEAVING = 12
    BESEECHING = 13
    ANY_PHYSICAL = 14
    ANY_MENTAL = 15
    ANY_SOCIAL = 16
    ANY_MYSTICAL = 17

    CHECK_CHOICES = (
        (ANY, "Any"),
        (ATTACK, "Attack"),
        (DAMAGE, "Damage"),
        (DEFENSE, "Defense"),
        (HEAL, "Heal"),
        (STEALTH, "Stealth"),
        (ANY_COMBAT, "Any Combat"),
        (PERCEPTION, "Perception"),
        (CRAFTING, "Crafting"),
        (INVESTIGATION, "Investigation"),
        (CASTING, "Casting"),
        (CHANNELING, "Channeling"),
        (WEAVING, "Weaving"),
        (BESEECHING, "Beseeching"),
        (ANY_PHYSICAL, "Any Physical"),
        (ANY_MENTAL, "Any Mental"),
        (ANY_SOCIAL, "Any Social"),
        (ANY_MYSTICAL, "Any Mystical"),
    )
    MODIFIER, KNACK = range(2)
    MOD_CHOICES = ((MODIFIER, "Modifier"), (KNACK, "Knack"))
    object = models.ForeignKey(
        "objects.ObjectDB",
        db_index=True,
        related_name="modifiers",
        on_delete=models.CASCADE,
    )
    value = models.IntegerField(default=0)
    # tag required by the user for this modifier to take effect. if '', then it's for any user
    user_tag = models.CharField(
        blank=True,
        max_length=80,
        help_text="Only applies if user has a tag by this name.",
    )
    # tag required by the target for this modifier to take effect. if '', then it's for any target
    target_tag = models.CharField(
        blank=True,
        max_length=80,
        help_text="Only applies if target has a tag by this name.",
    )
    # type of roll/check this modifier applies to
    check = models.PositiveSmallIntegerField(choices=CHECK_CHOICES, default=ANY)
    # restricting modifier to specific stat/skill/ability
    stat = models.CharField(
        blank=True, max_length=40, help_text="Only applies for checks with this stat."
    )
    skill = models.CharField(
        blank=True, max_length=40, help_text="Only applies for checks with this skill."
    )
    ability = models.CharField(
        blank=True,
        max_length=40,
        help_text="Only applies for checks with this ability.",
    )
    modifier_type = models.PositiveSmallIntegerField(
        choices=MOD_CHOICES, default=MODIFIER
    )
    name = models.CharField(
        blank=True,
        max_length=80,
        db_index=True,
        help_text="Name of the modifier, for knacks",
    )
    description = models.TextField(
        blank=True, help_text="Description of why/how the modifier works"
    )

    @classmethod
    def get_check_type_list(cls, check_type):
        """
        Gets a list of all relevant check_types based on the given check_type
        Args:
            check_type: Matches one of our integer choices

        Returns:
            A list of the relevant check_types.
        """
        check_type_list = [check_type]
        if check_type == cls.ANY:
            return check_type_list
        check_type_list.append(cls.ANY)
        if check_type in (cls.ATTACK, cls.DEFENSE, cls.DAMAGE):
            check_type_list.extend([cls.ANY_COMBAT, cls.ANY_PHYSICAL])
        if check_type in (cls.HEAL, cls.STEALTH):
            check_type_list.append(cls.ANY_PHYSICAL)
        if check_type in (cls.PERCEPTION, cls.INVESTIGATION):
            check_type_list.append(cls.ANY_MENTAL)
        if check_type in (cls.WEAVING, cls.CHANNELING, cls.CASTING, cls.BESEECHING):
            check_type_list.append(cls.ANY_MYSTICAL)
        return check_type_list

    def __str__(self):
        sign = "-" if self.value < 0 else "+"
        msg = "Modifier on %s of %s%s" % (self.object, sign, self.value)
        if self.skill or self.stat or self.ability:
            msg += "to %s" % "/".join([self.stat, self.skill, self.ability])
        if self.user_tag:
            msg += " for %s" % self.user_tag
        if self.target_tag:
            msg += " against %s" % self.target_tag
        msg += " for %s checks" % self.get_check_display()
        return msg

    def display_knack(self):
        msg = "\n|wName:|n %s\n" % self.name
        msg += "|wStat:|n {} |wSkill:|n {} |wValue:|n {}\n".format(
            self.stat, self.skill, self.value
        )
        msg += "|wDescription:|n {}\n".format(self.description)
        return msg

    @property
    def crit_chance_bonus(self):
        """Modifiers to crit chance from a roll modifier"""
        if self.value > 0:
            return 1 + (self.value // 2)


class EffectTrigger(SharedMemoryModel):
    """
    Triggers are to have certain effects occur when another object interacts with the object the
    trigger is on. Other objects are responsible for checking for conditions in appropriate hooks
    and calling check_trigger_on_target on the appropriate object, which then handles checking for
    and processing any events that happen.
    """

    ON_OTHER_ENTRY = 0
    ON_OTHER_DEPART = 1
    ON_TAKING_DAMAGE = 2
    ON_INFLICTING_DAMAGE = 3
    ON_DEATH = 4
    ON_PICKUP = 5
    ON_USE = 6
    ON_BEING_HEALED = 7
    EVENT_CHOICES = (
        (ON_OTHER_ENTRY, "On Other Entry"),
        (ON_OTHER_DEPART, "On Other Depart"),
        (ON_TAKING_DAMAGE, "On Taking Damage"),
        (ON_INFLICTING_DAMAGE, "On Inflicting Damage"),
        (ON_DEATH, "On Dying"),
        (ON_PICKUP, "On Pickup"),
        (ON_USE, "On Use"),
        (ON_BEING_HEALED, "On Being Healed"),
    )

    PRESTIGE_RANK = 0
    PRESTIGE_VALUE = 1
    SOCIAL_RANK = 2
    TAG_NAME = 3
    ORG_NAME_AND_RANK_RANGE = 4
    CURRENT_HEALTH_PERCENTAGE = 5
    CHANGE_AMOUNT = 6
    CONDITIONAL_CHECK_CHOICES = (
        (PRESTIGE_RANK, "Prestige Rank"),
        (PRESTIGE_VALUE, "Prestige Value"),
        (SOCIAL_RANK, "Social Rank"),
        (ORG_NAME_AND_RANK_RANGE, "Org Name and Rank Range"),
        (CURRENT_HEALTH_PERCENTAGE, "Current Health %"),
        (CHANGE_AMOUNT, "Change Amount"),
    )
    ANY_TIME = 0
    MORNING = 1
    AFTERNOON = 2
    EVENING = 3
    NIGHT = 4
    DAY = 5
    TIME_OF_DAY_CHOICES = (
        (ANY_TIME, "Any Time"),
        (MORNING, "Only Morning"),
        (AFTERNOON, "Only Afternoon"),
        (EVENING, "Only Evening"),
        (NIGHT, "Only Night"),
        (DAY, "Only Day"),
    )
    object = models.ForeignKey(
        "objects.ObjectDB",
        related_name="triggers",
        on_delete=models.CASCADE,
        help_text="The object this trigger is on. For example, a room checking "
        "others entering it.",
    )
    priority = models.PositiveSmallIntegerField(
        default=0, help_text="Only highest priority triggers are executed."
    )
    trigger_event = models.PositiveSmallIntegerField(
        choices=EVENT_CHOICES, default=ON_OTHER_ENTRY
    )
    conditional_check = models.PositiveSmallIntegerField(
        choices=CONDITIONAL_CHECK_CHOICES, default=PRESTIGE_RANK
    )
    min_value = models.IntegerField(
        null=True,
        blank=True,
        help_text="Minimum value for trigger. Leave blank for " "tag names.",
    )
    max_value = models.IntegerField(
        null=True,
        blank=True,
        help_text="Max value for trigger. Leave blank for tag " "names.",
    )
    text_value = models.CharField(
        null=True,
        max_length=200,
        blank=True,
        help_text="Names of orgs, tags, etc. Leave " "blank if not applicable.",
    )
    required_time = models.PositiveSmallIntegerField(
        choices=TIME_OF_DAY_CHOICES,
        default=ANY_TIME,
        help_text="Time of day when the trigger works, if any.",
    )
    negated_check = models.BooleanField(
        default=False,
        help_text="Whether this trigger applies to all objects that do "
        "not meet the trigger check.",
    )
    room_msg = models.TextField(
        blank=True,
        help_text="If the trigger is on a room, send this message to everyone in "
        "the room. If it's on a character, send it to their location.",
    )
    target_msg = models.TextField(
        blank=True, help_text="Private message sent to the target who triggered this."
    )
    additional_effects = models.TextField(
        blank=True, help_text="Parsed string of function_name: args, kwargs."
    )

    def check_trigger_on_target(self, target, change_amount=0):
        """Checks whether target will trigger an effect. If so, we process the trigger."""
        triggered = True
        if self.required_time != self.ANY_TIME:
            # see if the current time of day doesn't match the required time
            _, time = self.object.get_room().get_time_and_season()
            req = self.required_time
            if req == self.MORNING and time != "morning":
                triggered = False
            if req == self.AFTERNOON and time != "afternoon":
                triggered = False
            if req == self.EVENING and time != "evening":
                triggered = False
            if req == self.NIGHT and time != "night":
                triggered = False
            if req == self.DAY and time not in ("morning", "afternoon", "evening"):
                triggered = False
        if self.conditional_check == self.PRESTIGE_RANK:
            # see if the target's prestige rank doesn't fall within the specified range
            try:
                owner = target.dompc.assets
            except AttributeError:
                triggered = False
            else:
                rank = None
                try:
                    rank = self._cached_prestige_rankings.index(owner)
                except (AttributeError, ValueError):
                    self.cache_prestige_rankings()
                    try:
                        rank = self._cached_prestige_rankings.index(owner)
                    except ValueError:
                        pass
                if rank is None or self.max_value < rank or rank < self.min_value:
                    triggered = False
        elif self.conditional_check == self.PRESTIGE_VALUE:
            # see if the target's prestige value doesn't fall within the range
            try:
                prest = target.player_ob.Dominion.assets.prestige
                if prest < self.min_value or prest > self.max_value:
                    triggered = False
            except (AttributeError, ValueError, TypeError):
                triggered = False
        elif self.conditional_check == self.SOCIAL_RANK:
            # see if their social rank doesn't fall within the range
            s_rank = target.db.social_rank
            if not s_rank or s_rank > self.max_value or s_rank < self.min_value:
                triggered = False
        elif self.conditional_check == self.TAG_NAME:
            # see if the target doesn't have the right tag
            if not target.tags.get(self.text_value):
                triggered = False
        elif self.conditional_check == self.ORG_NAME_AND_RANK_RANGE:
            # see if the target isn't a member of the org within the rank range specified
            if not target.player_ob:
                triggered = False
            else:
                member = target.player_ob.Dominion.memberships.filter(
                    deguilded=False, organization__name__iexact=self.text_value
                ).first()
                if (
                    not member
                    or member.rank > self.max_value
                    or member.rank < self.min_value
                ):
                    triggered = False
        elif self.conditional_check == self.CURRENT_HEALTH_PERCENTAGE:
            try:
                health = target.get_health_percentage()
                if health > self.max_value or health < self.min_value:
                    triggered = False
            except (AttributeError, ValueError, TypeError):
                triggered = False
        elif self.conditional_check == self.CHANGE_AMOUNT:
            if self.max_value < change_amount < self.min_value:
                triggered = False
        if (triggered and not self.negated_check) or (
            self.negated_check and not triggered
        ):
            return self.do_trigger_results(target)
        return False

    @classmethod
    def cache_prestige_rankings(cls):
        """Creates a list of all the active Characters ranked by their prestige order. caches it in the class."""
        from world.dominion.models import AssetOwner

        qs = list(
            AssetOwner.objects.filter(player__player__roster__roster__name="Active")
        )
        cls._cached_prestige_rankings = sorted(
            qs, key=lambda x: x.prestige, reverse=True
        )

    def do_trigger_results(self, target):
        """
        Process the results of a successful trigger
        Args:
            target: The object receiving our trigger.
        """
        if self.room_msg:
            target.msg_location_or_contents(self.room_msg)
        if self.target_msg:
            target.msg(self.target_msg)
        # TODO: Process additional_effects
        return True

    def save(self, *args, **kwargs):
        """On save, we'll refresh the cache of ou"""
        super(EffectTrigger, self).save(*args, **kwargs)
        self.object.triggerhandler.add_trigger_to_cache(self)


class Wound(SharedMemoryModel):
    """
    A wound that a character has taken. It may be serious (temporary) or
    permanent, and affects one of their traits.
    """

    SERIOUS, PERMANENT = SERIOUS_WOUND, PERMANENT_WOUND
    WOUND_TYPES = (
        (SERIOUS, "serious wound"),
        (PERMANENT, "permanent wound"),
    )
    health_status = models.ForeignKey(
        "CharacterHealthStatus", related_name="wounds", on_delete=models.CASCADE
    )
    trait = models.ForeignKey(
        "traits.Trait", related_name="wounds", on_delete=models.CASCADE
    )
    severity = models.PositiveSmallIntegerField(default=SERIOUS, choices=WOUND_TYPES)


class CharacterHealthStatus(SharedMemoryModel):
    """
    Tracks the status of a character's health - their consciousness, living/dead state,
    and damage taken. Eventually we'll change death/unconsciousness to be conditions that
    are associated with applying their cmdsets and other state changes, but for now we're
    doing that separately and this is just storage for marking that state.
    """

    CONSCIOUSNESS_CHOICES = (
        (CONSCIOUS, "conscious"),
        (ASLEEP, "asleep"),
        (UNCONSCIOUS, "unconscious"),
    )

    character = models.OneToOneField(
        "objects.ObjectDB",
        related_name="character_health_status",
        on_delete=models.CASCADE,
        primary_key=True,
    )
    damage = models.PositiveSmallIntegerField(default=0)
    consciousness = models.PositiveSmallIntegerField(
        default=CONSCIOUS, choices=CONSCIOUSNESS_CHOICES
    )
    is_dead = models.BooleanField(default=False)

    objects = HealthStatusQuerySet.as_manager()

    @property
    def character_name(self):
        return self.character.db_key

    def __str__(self):
        return self.character_name

    def full_restore(self):
        self.damage = 0
        self.consciousness = CONSCIOUS
        self.is_dead = False
        self.save()

    def set_alive(self):
        if self.is_dead:
            self.is_dead = False
            self.save()

    def set_dead(self):
        if not self.is_dead:
            self.is_dead = True
            self.save()

    def set_awake(self):
        if self.consciousness != CONSCIOUS:
            self.consciousness = CONSCIOUS
            self.save()

    def set_asleep(self):
        if self.consciousness != ASLEEP:
            self.consciousness = ASLEEP
            self.save()

    def set_unconscious(self):
        if self.consciousness != UNCONSCIOUS:
            self.consciousness = UNCONSCIOUS
            self.save()

    def reduce_damage(self, value):
        """Lowers our damage by the given value"""
        if value > 0 and self.damage > 0:
            self.damage -= value
            if self.damage < 0:
                self.damage = 0
            self.save()

    @property
    def is_conscious(self):
        return self.consciousness == CONSCIOUS

    @property
    def is_asleep(self):
        return self.consciousness == ASLEEP

    def get_highest_value_for_treatment_type(self, treatment_type):
        return (
            self.treatment_attempts.filter(treatment_type=treatment_type).aggregate(
                highest=models.Max("value", output_field=models.IntegerField(default=0))
            )["highest"]
            or 0
        )

    @CachedProperty
    def cached_highest_revive_treatment_roll(self):
        return self.get_highest_value_for_treatment_type(REVIVE)

    @CachedProperty
    def cached_highest_recovery_treatment_roll(self):
        return self.get_highest_value_for_treatment_type(RECOVERY)

    @CachedProperty
    def cached_should_heal_wound(self):
        return self.treatment_attempts.filter(
            outcome__effect=HEAL_AND_CURE_WOUND
        ).exists()

    @CachedProperty
    def cached_revive_treatments(self):
        return list(self.treatment_attempts.filter(treatment_type=REVIVE))

    def get_highest_revive_treatment(self):
        if not self.cached_revive_treatments:
            return
        return sorted(self.cached_revive_treatments, key=lambda x: x.value)[-1]

    def recovery_check(self):
        treatment_value = self.cached_highest_recovery_treatment_roll or 0
        check = get_check_maker_by_name(RECOVERY_CHECK, self.character)
        check.make_check_and_announce()
        if check.outcome.effect == HEAL:
            # get the base healing value for this character based on their roll and stats
            healing = check.value_for_outcome
            # add healing given by their best treatment
            healing += treatment_value
            self.character.change_health(healing, wake=False)
            if self.cached_should_heal_wound:
                self.heal_wound()
            # check to see if we would regain consciousness, if needed
            self.check_regain_consciousness()

    @CachedProperty
    def cached_wounds(self):
        return list(self.wounds.all())

    def get_wound_string(self):
        msg = ""
        if self.cached_wounds:
            serious = [ob for ob in self.cached_wounds if ob.severity == Wound.SERIOUS]
            permanent = [ob for ob in self.cached_wounds if ob not in serious]
            msg += f"\nWounds: Serious: {len(serious)}, Permanent: {len(permanent)}"
        return msg

    def heal_wound(self):
        """Heals a serious, but not permanent wound"""
        serious = [ob for ob in self.cached_wounds if ob.severity == Wound.SERIOUS]
        if serious:
            # get a random wound from our list of serious wounds
            wound = random.choice(serious)
            # remove from caches
            self.cached_wounds = [ob for ob in self.cached_wounds if ob != wound]
            wound.delete()

    def heal_permanent_wound_for_trait(self, trait) -> bool:
        perm = [
            ob
            for ob in self.cached_wounds
            if ob.severity == Wound.PERMANENT and ob.trait == trait
        ]
        if perm:
            perm[0].delete()
            del self.cached_wounds
            return True
        return False

    def revive_check(self):
        """The character heals"""
        treatment = self.get_highest_revive_treatment()
        if not treatment:
            return
        if treatment.outcome.effect not in REVIVE_EFFECTS:
            return
        uncon_damage = self.damage - self.character.max_hp
        if uncon_damage < 0:
            uncon_damage = 0
        value = treatment.value_for_outcome
        if uncon_damage:
            # if we rolled high enough to auto-wake, we heal all our unconscious damage
            if treatment.outcome.effect == AUTO_WAKE:
                value += uncon_damage
            else:  # otherwise, we heal between 50% to all of our uncon damage
                value += random.randint(uncon_damage // 2, uncon_damage)
        self.reduce_damage(value)
        if treatment.outcome.effect == AUTO_WAKE:
            # we wake up and we're done, no uncon save required
            self.character.wake_up()
            return
        # see if the character regains consciousness
        self.check_regain_consciousness()

    def check_regain_consciousness(self):
        """
        Makes a check to regain consciousness via the unconsciouness save if our
        character is unconscious.
        """
        # no need if they're not actually unconscious
        if self.consciousness != UNCONSCIOUS:
            return
        # If the character is below 0 health, they can't wake up
        if self.character.get_health_percentage() < 0:
            return
        check = get_check_maker_by_name(UNCON_SAVE, self.character)
        check.make_check_and_announce()
        if check.is_success:
            self.character.wake_up()

    def check_treatment_too_recent(self, healer, treatment_type, error_msg):
        """Raises a TreatmentTooRecent error"""
        if self.treatment_attempts.filter(
            treatment_type=treatment_type, healer=healer
        ).exists():
            raise TreatmentTooRecentError(error_msg)

    def add_recovery_treatment(self, healer):
        self.check_treatment_too_recent(
            healer,
            RECOVERY,
            f"{healer} has attempted to assist with their recovery too recently.",
        )
        check = get_check_maker_by_name(
            RECOVERY_TREATMENT, healer, target=self.character
        )
        check.make_check_and_announce()
        self.add_treatment_for_check(check, TreatmentAttempt.RECOVERY)

    def add_treatment_for_check(self, check, treatment_type):
        """
        Adds a treatment to the character.
        """
        self.treatment_attempts.create(
            healer=check.character,
            treatment_type=treatment_type,
            value=check.value_for_outcome,
            time_attempted=datetime.now(),
            outcome=check.outcome,
        )

    def add_revive_treatment(self, healer):
        self.check_treatment_too_recent(
            healer, REVIVE, f"{healer} has attempted to revive them too recently."
        )
        check = get_check_maker_by_name(REVIVE_TREATMENT, healer, target=self.character)
        check.make_check_and_announce()
        self.add_treatment_for_check(check, TreatmentAttempt.REVIVE)

    def at_enter_combat(self):
        """Called if the character enters combat"""
        if any(self.treatment_attempts.all().delete()):
            self.character.msg(
                "|rYour recovery treatments have been ruined by entering combat.|n"
            )


class RecoveryRunner(SharedMemoryModel):
    """
    This is a singleton - it should be a table with only a single row. It connects to a script
    that calls it at periodic intervals. It runs calls for recovery checks or revive attempts
    for the health status of characters.
    """

    script = models.OneToOneField(
        "scripts.ScriptDB",
        primary_key=True,
        on_delete=models.CASCADE,
        related_name="recovery_runner",
    )
    recovery_last_run = models.DateTimeField(
        null=True,
        help_text="When our recovery checks for all damaged characters last ran. "
        "A recovery check heals the character if successful.",
    )
    revive_last_run = models.DateTimeField(
        null=True,
        help_text="When our revive checks for unconscious characters last ran. "
        "Characters above 0 health will regain consciousness if they "
        "succeed the check.",
    )
    recovery_interval = models.PositiveSmallIntegerField(
        default=60 * 60 * 24, help_text="Number of seconds between recovery checks."
    )
    revive_interval = models.PositiveSmallIntegerField(
        default=60 * 5, help_text="Number of seconds between revive checks."
    )

    def run_recovery_checks(self):
        """Called by our script, this runs recovery checks for every damaged character"""
        # get the health status of all living characters with damage
        qs = CharacterHealthStatus.objects.get_recovery_queryset()
        for status in qs:
            status.recovery_check()
        # delete all old recovery treatments after
        TreatmentAttempt.objects.decrement_treatments(treatment_type=RECOVERY)
        TreatmentAttempt.flush_instance_cache()
        # store the date so we know when we were last run
        self.recovery_last_run = datetime.now()
        self.save()

    def run_revive_checks(self):
        """Called by our script, this runs revive checks for every unconscious character"""
        # get the health status of all unconscious characters who are alive
        qs = CharacterHealthStatus.objects.get_revive_queryset()
        for status in qs:
            status.revive_check()
        # delete all old revive treatments after
        TreatmentAttempt.objects.decrement_treatments(treatment_type=REVIVE)
        TreatmentAttempt.flush_instance_cache()
        # store the date so we know when we were last run
        self.revive_last_run = datetime.now()
        self.save()


class TreatmentAttempt(SharedMemoryModel):
    """A healing attempt by a character to another character's health status"""

    RECOVERY, REVIVE, WOUND = RECOVERY, REVIVE, WOUND
    TREATMENT_CHOICES = ((RECOVERY, "recovery"), (REVIVE, "revive"), (WOUND, "wound"))
    target = models.ForeignKey(
        "CharacterHealthStatus",
        on_delete=models.CASCADE,
        related_name="treatment_attempts",
    )
    healer = models.ForeignKey(
        "objects.ObjectDB", related_name="treatments_given", on_delete=models.CASCADE
    )
    value = models.SmallIntegerField(default=0)
    treatment_type = models.PositiveSmallIntegerField(
        default=RECOVERY, choices=TREATMENT_CHOICES
    )
    time_attempted = models.DateTimeField(null=True)
    uses_remaining = models.PositiveSmallIntegerField(default=5)
    outcome = models.ForeignKey(
        "stat_checks.StatCheckOutcome",
        null=True,
        on_delete=models.SET_NULL,
        related_name="treatment_attempts",
        help_text="If there's a specific effect for the treatment roll, "
        "we look it up in the outcome we point at. Otherwise this is null.",
    )

    objects = TreatmentAttemptQuerySet.as_manager()
