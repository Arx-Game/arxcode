from server.utils.arx_utils import commafy, inform_staff
from evennia.utils import logger
from world.magic.models import Alignment, Affinity, Practitioner
import json
import sys


class MagicConsequence(object):
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
        participants=None,
        danger_level=1,
        success_diff=0,
        alignment=None,
        affinity=None,
        calculated=False,
        finalized=False,
    ):

        parts = None
        if participants:
            parts = []
            for part in participants:
                if isinstance(part, int):
                    part = Practitioner.by_id(part)
                if part:
                    parts.append(part)

        self.participants = parts
        self.danger_level = danger_level
        self.success_diff = success_diff

        if alignment:
            if isinstance(alignment, int):
                alignment = Alignment.by_id(alignment)

        self.alignment = alignment

        if affinity:
            if isinstance(affinity, int):
                affinity = Affinity.by_id(affinity)

        self.affinity = affinity
        self.calculated = calculated
        self.finalized = finalized

    def calculate(self):
        if self.calculated:
            return

    def finalize(self):
        if not self.calculated:
            return

        if self.finalized:
            return

    def results_string(self):
        return None

    def __str__(self):
        return self.serialize()

    def serialize(self, result=None):
        if not result:
            result = {}

        result["__class"] = self.__class__.__name__

        if self.participants:
            parts = [part.id for part in self.participants]
            result["participants"] = parts

        if self.alignment:
            result["alignment"] = self.alignment.id

        if self.affinity:
            result["affinity"] = self.affinity.id

        result["danger_level"] = self.danger_level
        result["success_diff"] = self.success_diff
        result["calculated"] = self.calculated
        result["finalized"] = self.finalized

        return json.dumps(result)


class NoConsequence(MagicConsequence):
    """
    I wanna be... consequence free...
    """

    def results_string(self):
        return "No Consequence. (Lucky!)"


class MagicDamageConsequence(MagicConsequence):
    def __init__(self, damage=0, attack_tags=None, *args, **kwargs):
        super(MagicDamageConsequence, self).__init__(*args, **kwargs)
        self.damage = damage
        if not attack_tags:
            attack_tags = ["magical"]
        self.attack_tags = attack_tags

    def calculate(self):
        super(MagicDamageConsequence, self).calculate()
        self.damage = self.success_diff * (1.0 + (self.danger_level / 10.0))

        if self.affinity:
            self.attack_tags.append(self.affinity.name)
        if self.alignment:
            self.attack_tags.append(self.alignment.name)

    def finalize(self):
        super(MagicDamageConsequence, self).finalize()

        from typeclasses.scripts.combat import attacks, combat_settings

        victims = [participant.character for participant in self.participants]
        names = [obj.name for obj in victims]
        commafied_names = commafy(names)

        attack = attacks.Attack(
            targets=victims,
            affect_real_dmg=True,
            damage=self.damage,
            use_mitigation=False,
            can_kill=True,
            private=False,
            story="Magic has consequences!",
            attack_tags=self.attack_tags,
        )
        try:
            attack.execute()
        except combat_settings.CombatError as err:
            logger.log_err("Combat error when applying magical damage: " + str(err))
            inform_staff(
                "|rCombat Error!|n Tried to apply %d damage to %s, but got error %s"
                % (self.damage, commafied_names, str(err))
            )
        else:
            part = "was"
            if len(victims) > 1:
                part = "were"
            inform_staff(
                "|y%s|n %s harmed for %d by a failed magical working."
                % (commafied_names, part, self.damage)
            )

    def results_string(self):
        victims = [participant.character.name for participant in self.participants]
        commafied_names = commafy(victims)
        part = "was"
        if len(victims) > 1:
            part = "were"

        return "{} {} damaged for {} damage of types {}.".format(
            commafied_names, part, self.damage, self.attack_tags
        )

    def serialize(self, result=None):
        if not result:
            result = {}

        result["damage"] = self.damage
        result["attack_tags"] = self.attack_tags

        return super(MagicDamageConsequence, self).serialize(result)


def register_consequences():
    from world.magic.models import Working

    # Danger level 0: we had enough primum, but we might've still missed our target successes
    Working.register_consequence(0, NoConsequence, weight=10)
    Working.register_consequence(0, MagicDamageConsequence, weight=100)

    # Danger level 1
    Working.register_consequence(0, NoConsequence, weight=10)
    Working.register_consequence(1, MagicDamageConsequence, weight=100)

    # Danger level 2
    Working.register_consequence(0, NoConsequence, weight=10)
    Working.register_consequence(2, MagicDamageConsequence, weight=100)

    # Danger level 3
    Working.register_consequence(0, NoConsequence, weight=10)
    Working.register_consequence(3, MagicDamageConsequence, weight=100)

    # Danger level 4
    Working.register_consequence(0, NoConsequence, weight=10)
    Working.register_consequence(4, MagicDamageConsequence, weight=100)
