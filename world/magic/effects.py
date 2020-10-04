from .conditional_parser import ConditionalHandler
from web.character.models import Clue
from evennia.objects.models import ObjectDB
from .models import (
    ClueCollection,
    MagicBucket,
    Effect,
    Practitioner,
    Alignment,
    Affinity,
)
from server.utils.arx_utils import inform_staff
import json
import sys


# noinspection PyMethodMayBeStatic
class CodedEffect(object):
    requires_combat = False

    @classmethod
    def load(cls, serialized_dict=None):
        if not serialized_dict:
            return None

        target_class_name = serialized_dict["__class"]
        if not target_class_name:
            return None

        target_class = getattr(sys.modules[__name__], target_class_name)
        if not target_class:
            return None

        del serialized_dict["__class"]
        return target_class(**serialized_dict)

    @classmethod
    def loads(cls, serialized_string):
        serialized_dict = json.loads(serialized_string)
        return cls.load(serialized_dict)

    def __init__(
        self,
        lead=None,
        participants=None,
        target_string=None,
        target_obj=None,
        parameters=None,
        conditions=None,
        strength=10,
        quiet=False,
        successes=0,
        performed=False,
        finalized=False,
        alignment=None,
        affinity=None,
    ):

        if isinstance(lead, int):
            self.lead = Practitioner.by_id(lead)
        else:
            self.lead = lead

        self.participants = []
        for part in participants:
            if isinstance(part, int):
                part = Practitioner.by_id(part)
            self.participants.append(part)

        if self.lead not in self.participants:
            self.participants.append(self.lead)

        if isinstance(target_obj, int):
            try:
                target_obj = ObjectDB.objects.get(id=target_obj)
            except (ObjectDB.DoesNotExist, ObjectDB.MultipleObjectsReturned):
                target_obj = None

        if isinstance(affinity, int):
            try:
                affinity = Affinity.objects.get(id=affinity)
            except (Affinity.DoesNotExist, Affinity.MultipleObjectsReturned):
                affinity = None

        if isinstance(alignment, int):
            try:
                alignment = Alignment.objects.get(id=alignment)
            except (Alignment.DoesNotExist, Alignment.MultipleObjectsReturned):
                alignment = None

        self.target_obj = target_obj
        self.target_string = target_string
        self.parameters = parameters
        self.strength = strength
        self.conditions = ConditionalHandler(conditions)
        self.quiet = quiet
        self.successes = successes
        self.performed = performed
        self.finalized = finalized
        self.affinity = affinity
        self.alignment = alignment

    def __str__(self):
        return self.serialize()

    def valid_target(self):
        return True

    def valid_parameters(self):
        return True

    def check_for_other_errors(self):
        """Returns None, or a string of any other error messages that prevent us from casting"""
        return None

    def valid_conditions(self):
        require = self.conditions.check(
            self.lead, self.target_obj, "require", default=True
        )
        prohibit = self.conditions.check(
            self.lead, self.target_obj, "prohibit", default=False
        )

        return require and not prohibit

    def msg(self, text):
        if not self.quiet:
            for practitioner in self.participants:
                practitioner.notify_magic(text)

    def msg_room(self, text, guaranteed=False, mundane=False):
        if not self.quiet:
            for obj in self.lead.location.contents:
                if hasattr(obj, "msg_magic"):
                    obj.msg_magic(
                        text,
                        strength=self.strength,
                        guaranteed=guaranteed,
                        mundane=mundane,
                    )

    def results_string(self):
        return None

    def perform(self):
        if self.performed:
            return

        self.performed = True

    def finalize(self):
        if not self.performed:
            return

        if self.finalized:
            return

        self.finalized = True

    def serialize(self, result=None):
        if not result:
            result = {}

        result["__class"] = self.__class__.__name__

        if self.lead:
            result["lead"] = self.lead.id

        result["participants"] = [part.id for part in self.participants]

        if self.target_string:
            result["target_string"] = self.target_string

        if self.target_obj:
            result["target_obj"] = self.target_obj.id

        if self.parameters:
            result["parameters"] = self.parameters

        if self.conditions:
            result["conditions"] = str(self.conditions)

        if self.affinity:
            result["affinity"] = self.affinity.id

        if self.alignment:
            result["alignment"] = self.alignment.id

        result["strength"] = self.strength
        result["quiet"] = self.quiet
        result["successes"] = self.successes
        result["performed"] = self.performed
        result["finalized"] = self.finalized

        return json.dumps(result)


class SightEffect(CodedEffect):
    def __init__(self, sight_result=None, *args, **kwargs):
        super(SightEffect, self).__init__(*args, **kwargs)
        self.sight_result = sight_result

    def valid_target(self):
        return self.target_obj is not None

    def valid_parameters(self):
        return True

    def perform(self):
        super(SightEffect, self).perform()

        text = self.target_obj.magic_description

        if self.successes > 20:
            magic_advanced = self.target_obj.magic_description_advanced
            if magic_advanced:
                text += " " + magic_advanced

        self.sight_result = text

    def finalize(self):
        super(SightEffect, self).finalize()

        self.msg(
            "Gazing at {}, you perceive: {}".format(
                self.target_obj.name, self.sight_result
            )
        )

    def results_string(self):
        if not self.performed:
            return None

        return "Participants perceive: " + self.sight_result

    def serialize(self, result=None):
        if not result:
            result = {}

        if self.sight_result:
            result["sight_result"] = self.sight_result

        return super(SightEffect, self).serialize(result)


class ClueCollectionEffect(CodedEffect):
    def __init__(self, *args, **kwargs):
        super(ClueCollectionEffect, self).__init__(*args, **kwargs)
        self.cached_clue = None
        self.cached_collection = None

    @property
    def target_collection(self):
        if self.cached_collection:
            return self.cached_collection

        collection = None
        try:
            collection_id = int(self.parameters)
            collection = ClueCollection.objects.get(id=collection_id)
        except (ValueError, ClueCollection.DoesNotExist):
            pass

        if not collection:
            try:
                collection = ClueCollection.objects.get(name__iexact=self.parameters)
            except ClueCollection.DoesNotExist:
                pass

        self.cached_collection = collection
        return collection

    @property
    def target_clue(self):
        if self.cached_clue:
            return self.cached_clue

        try:
            clue_id = int(self.target_string)
            target_clue = Clue.objects.get(id=clue_id)
        except (ValueError, Clue.DoesNotExist):
            return None

        self.cached_clue = target_clue
        return target_clue

    def valid_target(self):
        if not self.lead:
            return False

        clue = self.target_clue
        if not clue:
            return False

        if clue not in self.lead.character.roster.clues.all():
            return False

    def valid_parameters(self):
        return self.target_collection is not None

    def perform(self):
        super(ClueCollectionEffect, self).perform()

    def finalize(self):
        super(ClueCollectionEffect, self).finalize()

        clue = self.target_clue

        if clue not in self.target_collection.clues.all():
            self.target_collection.clues.add(clue)
            self.target_collection.save()

    def results_string(self):
        return "'{}' added to collection '{}'.".format(
            self.target_clue.name, self.target_collection.name
        )


class BucketEffect(CodedEffect):
    def __init__(self, final_value=None, *args, **kwargs):
        super(BucketEffect, self).__init__(*args, **kwargs)
        self.cached_bucket = None
        self.final_value = final_value

    @property
    def target_bucket(self):
        if self.cached_bucket:
            return self.cached_bucket

        split_params = self.parameters.split(",")
        left_param = split_params[0]

        try:
            bucket_id = int(left_param)
            bucket = MagicBucket.objects.get(id=bucket_id)
        except (ValueError, MagicBucket.DoesNotExist):
            bucket = None

        if not bucket:
            try:
                bucket = MagicBucket.objects.get(name__iexact=left_param)
            except MagicBucket.DoesNotExist:
                pass

        self.cached_bucket = bucket
        return bucket

    def valid_target(self):
        return True

    def valid_parameters(self):
        if self.target_bucket is None:
            return False

        split_params = self.parameters.split(",")
        if len(split_params) == 1:
            return True

        right_param = split_params[1]

        try:
            int(right_param)
        except ValueError:
            return False

        return True

    def perform(self):
        super(BucketEffect, self).perform()

        split_params = self.parameters.split(",")
        if len(split_params) == 1:
            multiplier = 1
        else:
            right_param = split_params[1]

            try:
                multiplier = int(right_param)
            except ValueError:
                raise ValueError

        self.final_value = self.successes * multiplier

    def finalize(self):
        super(BucketEffect, self).finalize()

        self.target_bucket.value = self.target_bucket.value + self.final_value

    def results_string(self):
        if not self.performed:
            return None

        return "{} added to bucket '{}'.".format(
            self.final_value, self.target_bucket.name
        )

    def serialize(self, result=None):
        if not result:
            result = {}

        if self.final_value:
            result["final_value"] = self.final_value

        return super(BucketEffect, self).serialize(result)


class DamageEffect(CodedEffect):
    requires_combat = True

    def __init__(self, *args, **kwargs):
        super(DamageEffect, self).__init__(*args, **kwargs)
        self.damage = 0
        self.real_damage = True
        self.can_kill = True
        self.use_mitigation = True
        self.targets = [self.target_obj]
        self.message = ""
        self.attack_tags = []

    def valid_target(self):
        """
        Target must be in combat for this to be valid. We already check for caster to be in combat with
        requires_combat being set to True.
        """
        try:
            return bool(self.target_obj.combat.state)
        except AttributeError:
            return False

    @property
    def combat(self):
        return self.lead.character.combat.combat

    def perform(self):
        """Rolls the damage we'll do"""
        from random import randint

        super(DamageEffect, self).perform()
        if self.parameters:
            params = self.parameters.split(",")
            if "noarmor" in params:
                self.use_mitigation = False
            if "mercy" in params:
                self.can_kill = False
            if "fake_damage" in params:
                self.real_damage = False
            if "aoe" in params:
                self.targets = list(
                    set(self.lead.character.combat.state.targets + self.targets)
                )
        self.real_damage = self.real_damage and self.combat.ndb.affect_real_damage
        self.can_kill = self.can_kill and self.real_damage
        # big range. So very minor spell of strength 10 does between 2-44 damage.
        self.damage = randint(self.strength // 4, (self.strength + 1) * 4)
        self.attack_tags = [str(ob) for ob in (self.alignment, self.affinity) if ob] + [
            "magic"
        ]

    def finalize(self):
        from typeclasses.scripts.combat.attacks import Attack

        super(DamageEffect, self).finalize()
        attack = Attack(
            targets=self.targets,
            affect_real_dmg=self.real_damage,
            damage=self.damage,
            use_mitigation=self.use_mitigation,
            attack_tags=self.attack_tags,
            can_kill=self.can_kill,
            story=self.message,
            inflictor=self.lead.character,
        )
        attack.execute()


class AnimaRitualEffect(CodedEffect):
    MIN_LENGTH = 250

    def __init__(self, *args, **kwargs):
        super(AnimaRitualEffect, self).__init__(*args, **kwargs)
        self.final_value = 0

    @property
    def story(self):
        """The story of how they're gaining understanding/changing as a person"""
        return self.target_string

    def check_for_other_errors(self):
        if len(self.story) < self.MIN_LENGTH:
            return (
                "That's too short for a story of your ritual. "
                "Please enter a story at least %s characters long." % self.MIN_LENGTH
            )

    def perform(self):
        super(AnimaRitualEffect, self).perform()
        num_rituals = self.lead.anima_rituals_this_week + 1
        self.final_value = self.strength / num_rituals
        inform_staff(
            "Anima Ritual story by %s: %s" % (self.lead.character.key, self.story)
        )

    def finalize(self):
        super(AnimaRitualEffect, self).finalize()
        self.lead.anima += self.final_value
        self.lead.save()

    def results_string(self):
        return "{} gains {} anima.".format(self.lead.character, self.final_value)


# TODO: All the other handlers, gods help me.


def register_effects():
    Effect.register_effect_handler(Effect.CODED_SIGHT, SightEffect)
    Effect.register_effect_handler(Effect.CODED_ADD_CLUE, ClueCollectionEffect)
    Effect.register_effect_handler(Effect.CODED_ADD_TOTAL, BucketEffect)
    Effect.register_effect_handler(Effect.CODED_DAMAGE, DamageEffect)
    Effect.register_effect_handler(Effect.CODED_ANIMA_RITUAL, AnimaRitualEffect)
