"""
The Conditions app is about status effects and modifiers. This can be anything from holy blessings or
enchantments to mundane diseases or using tools that give bonuses to a particular task.
"""
# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models

from evennia.utils.idmapper.models import SharedMemoryModel


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
        (ANY, "Any"), (ATTACK, "Attack"), (DAMAGE, "Damage"), (DEFENSE, "Defense"), (HEAL, "Heal"),
        (STEALTH, "Stealth"), (ANY_COMBAT, "Any Combat"), (PERCEPTION, "Perception"), (CRAFTING, "Crafting"),
        (INVESTIGATION, "Investigation"), (CASTING, "Casting"), (CHANNELING, "Channeling"), (WEAVING, "Weaving"),
        (BESEECHING, "Beseeching"), (ANY_PHYSICAL, "Any Physical"), (ANY_MENTAL, "Any Mental"),
        (ANY_SOCIAL, "Any Social"), (ANY_MYSTICAL, "Any Mystical")
    )
    MODIFIER, KNACK = range(2)
    MOD_CHOICES = ((MODIFIER, "Modifier"), (KNACK, "Knack"))
    object = models.ForeignKey("objects.ObjectDB", db_index=True, related_name="modifiers", on_delete=models.CASCADE)
    value = models.IntegerField(default=0)
    # tag required by the user for this modifier to take effect. if '', then it's for any user
    user_tag = models.CharField(blank=True, max_length=80, help_text="Only applies if user has a tag by this name.")
    # tag required by the target for this modifier to take effect. if '', then it's for any target
    target_tag = models.CharField(blank=True, max_length=80, help_text="Only applies if target has a tag by this name.")
    # type of roll/check this modifier applies to
    check = models.PositiveSmallIntegerField(choices=CHECK_CHOICES, default=ANY)
    # restricting modifier to specific stat/skill/ability
    stat = models.CharField(blank=True, max_length=40, help_text="Only applies for checks with this stat.")
    skill = models.CharField(blank=True, max_length=40, help_text="Only applies for checks with this skill.")
    ability = models.CharField(blank=True, max_length=40, help_text="Only applies for checks with this ability.")
    modifier_type = models.PositiveSmallIntegerField(choices=MOD_CHOICES, default=MODIFIER)
    name = models.CharField(blank=True, max_length=80, db_index=True, help_text="Name of the modifier, for knacks")
    description = models.TextField(blank=True, help_text="Description of why/how the modifier works")

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
        msg += "|wStat:|n {} |wSkill:|n {} |wValue:|n {}\n".format(self.stat, self.skill, self.value)
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
        (ON_BEING_HEALED, "On Being Healed")
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
        (CHANGE_AMOUNT, "Change Amount")
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
        (DAY, "Only Day")
    )
    object = models.ForeignKey("objects.ObjectDB", on_delete=models.CASCADE, related_name="triggers",
                                                                            help_text="The object this trigger is on. "
                                                                                      "For example, a room checking "
                                                                                      "others entering it.")
    priority = models.PositiveSmallIntegerField(default=0, help_text="Only highest priority triggers are executed.")
    trigger_event = models.PositiveSmallIntegerField(choices=EVENT_CHOICES, default=ON_OTHER_ENTRY)
    conditional_check = models.PositiveSmallIntegerField(choices=CONDITIONAL_CHECK_CHOICES, default=PRESTIGE_RANK)
    min_value = models.IntegerField(null=True, blank=True, help_text="Minimum value for trigger. Leave blank for "
                                                                     "tag names.")
    max_value = models.IntegerField(null=True, blank=True, help_text="Max value for trigger. Leave blank for tag "
                                                                     "names.")
    text_value = models.CharField(null=True, max_length=200, blank=True, help_text="Names of orgs, tags, etc. Leave "
                                                                                   "blank if not applicable.")
    required_time = models.PositiveSmallIntegerField(choices=TIME_OF_DAY_CHOICES, default=ANY_TIME,
                                                     help_text="Time of day when the trigger works, if any.")
    negated_check = models.BooleanField(default=False, help_text="Whether this trigger applies to all objects that do "
                                                                 "not meet the trigger check.")
    room_msg = models.TextField(blank=True, help_text="If the trigger is on a room, send this message to everyone in "
                                                      "the room. If it's on a character, send it to their location.")
    target_msg = models.TextField(blank=True, help_text="Private message sent to the target who triggered this.")
    additional_effects = models.TextField(blank=True, help_text="Parsed string of function_name: args, kwargs.")

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
                member = target.player_ob.Dominion.memberships.filter(deguilded=False,
                                                                      organization__name__iexact=self.text_value
                                                                      ).first()
                if not member or member.rank > self.max_value or member.rank < self.min_value:
                    triggered = False
        elif self.conditional_check == self.CURRENT_HEALTH_PERCENTAGE:
            try:
                health = target.get_health_percentage() * 100
                if health > self.max_value or health < self.min_value:
                    triggered = False
            except (AttributeError, ValueError, TypeError):
                triggered = False
        elif self.conditional_check == self.CHANGE_AMOUNT:
            if self.max_value < change_amount < self.min_value:
                triggered = False
        if (triggered and not self.negated_check) or (self.negated_check and not triggered):
            return self.do_trigger_results(target)
        return False

    @classmethod
    def cache_prestige_rankings(cls):
        """Creates a list of all the active Characters ranked by their prestige order. caches it in the class."""
        from world.dominion.models import AssetOwner
        qs = list(AssetOwner.objects.filter(player__player__roster__roster__name="Active"))
        cls._cached_prestige_rankings = sorted(qs, key=lambda x: x.prestige, reverse=True)

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
