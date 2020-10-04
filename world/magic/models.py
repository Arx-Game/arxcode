from evennia.utils.idmapper.models import SharedMemoryModel
from evennia.utils.create import create_object
from django.db import models
from server.utils.picker import WeightedPicker
from evennia.utils import logger
from evennia.utils.ansi import strip_ansi
from evennia.utils.evtable import EvTable
from world.roll import Roll
from server.utils.arx_utils import commafy, inform_staff, classproperty
from datetime import datetime, timedelta
import math
import json


class Alignment(SharedMemoryModel):

    name = models.CharField(max_length=20, blank=False, null=False, unique=True)
    alter_caster = models.BooleanField(default=False)
    adjective = models.CharField(
        max_length=20, blank=False, null=False, default="colorful"
    )

    _PRIMAL = None
    _ABYSSAL = None
    _ELYSIAN = None

    def __str__(self):
        return self.name

    @staticmethod
    def by_id(id_num):
        try:
            result = Alignment.objects.get(id=id_num)
            return result
        except Alignment.DoesNotExist:
            pass

        return None

    @classproperty
    def PRIMAL(cls):
        if cls._PRIMAL:
            return cls._PRIMAL

        try:
            cls._PRIMAL = Alignment.objects.get(name__iexact="primal")
            return cls._PRIMAL
        except Alignment.DoesNotExist:
            return None

    @classproperty
    def ABYSSAL(cls):
        if cls._ABYSSAL:
            return cls._ABYSSAL

        try:
            cls._ABYSSAL = Alignment.objects.get(name__iexact="abyssal")
            return cls._ABYSSAL
        except Alignment.DoesNotExist:
            return None

    @classproperty
    def ELYSIAN(cls):
        if cls._ELYSIAN:
            return cls._ELYSIAN

        try:
            cls._ELYSIAN = Alignment.objects.get(name__iexact="elysian")
            return cls._ELYSIAN
        except Alignment.DoesNotExist:
            return None


class Affinity(SharedMemoryModel):

    name = models.CharField(max_length=20, blank=False, null=False)
    description = models.TextField(blank=True, null=True)
    opposed = models.ForeignKey(
        "self", blank=True, null=True, related_name="+", on_delete=models.SET_NULL
    )
    rank1_desc = models.CharField(max_length=255, default="spark")
    rank2_desc = models.CharField(max_length=255, default="glimmer")
    rank3_desc = models.CharField(max_length=255, default="glow")
    rank4_desc = models.CharField(max_length=255, default="light")
    rank5_desc = models.CharField(max_length=255, default="brilliance")

    class Meta:
        """Define Django meta options"""

        verbose_name_plural = "Affinities"

    def __str__(self):
        return self.name

    @staticmethod
    def by_id(id_num):
        try:
            result = Affinity.objects.get(id=id_num)
            return result
        except Affinity.DoesNotExist:
            pass

        return None

    def description_for_value(self, resonance):
        if resonance <= 10:
            return self.rank1_desc
        elif 11 <= resonance <= 100:
            return self.rank2_desc
        elif 101 <= resonance <= 1000:
            return self.rank3_desc
        elif 1001 <= resonance <= 10000:
            return self.rank4_desc
        elif 10001 <= resonance:
            return self.rank5_desc


class AlchemicalMaterial(SharedMemoryModel):

    name = models.CharField(max_length=40, blank=False, null=False)
    plural_name = models.CharField(max_length=40, blank=True, null=True)
    alignment = models.ForeignKey(
        Alignment, blank=True, null=True, related_name="+", on_delete=models.SET_NULL
    )
    affinity = models.ForeignKey(
        Affinity,
        blank=True,
        null=True,
        related_name="materials",
        on_delete=models.SET_NULL,
    )
    description = models.TextField(blank=True, null=True)

    def create_instance(self, quantity):

        name_string = self.name
        if quantity > 2:
            name_string = "{} {}".format(quantity, self.plural_name or self.name)

        result = create_object(
            key=name_string, typeclass="world.magic.materials.MagicMaterial"
        )
        result.db.desc = self.description
        result.db.alchemical_material = self.id

        quality_picker = WeightedPicker()
        quality_picker.add_option(6, 30)
        quality_picker.add_option(7, 30)
        quality_picker.add_option(8, 10)
        quality_picker.add_option(9, 5)
        quality_picker.add_option(10, 1)

        result.db.quality_level = quality_picker.pick()
        result.db.quantity = quantity
        return result

    def __str__(self):
        return self.name


class Effect(SharedMemoryModel):

    TARGET_TYPE_NONE = 0
    TARGET_TYPE_SELF = 1
    TARGET_TYPE_CHARACTER = 2
    TARGET_TYPE_OBJECT = 3
    TARGET_TYPE_EITHER = 4
    TARGET_TYPE_CLUE = 5
    TARGET_TYPE_LOCATION = 6
    TARGET_TYPE_AGENT = 7

    TARGET_TYPES = (
        (TARGET_TYPE_NONE, "None"),
        (TARGET_TYPE_SELF, "Self"),
        (TARGET_TYPE_CHARACTER, "Character"),
        (TARGET_TYPE_OBJECT, "Object"),
        (TARGET_TYPE_EITHER, "Player or Object"),
        (TARGET_TYPE_CLUE, "Clue"),
        (TARGET_TYPE_LOCATION, "Location"),
        (TARGET_TYPE_AGENT, "Retainer"),
    )

    CODED_SIGHT = 0
    CODED_ADD_CLUE = 1
    CODED_ADD_TOTAL = 2
    CODED_INFUSE = 3
    CODED_ABSORB = 4
    CODED_ATTUNE = 5
    CODED_BOOST = 6
    CODED_WARD = 7
    CODED_DAMAGE = 8
    CODED_HEAL = 9
    CODED_EMIT = 10
    CODED_MAP = 11
    CODED_APPLY_COMBAT_CONDITION = 12
    CODED_REMOVE_COMBAT_CONDITION = 13
    CODED_APPLY_COMBAT_EFFECT = 14
    CODED_REMOVE_COMBAT_EFFECT = 15
    CODED_SET_WEATHER = 16
    CODED_ANIMA_RITUAL = 17

    CODED_EFFECTS = (
        (CODED_SIGHT, "Sight"),
        (CODED_ADD_CLUE, "Add Clue to Collection"),
        (CODED_ADD_TOTAL, "Add Successes to A Global Tally"),
        (CODED_INFUSE, "Add to Primum Value of Object"),
        (CODED_ABSORB, "Absorb Primum from an Object"),
        (CODED_ATTUNE, "Attune to Object, Player, or Agent"),
        (CODED_BOOST, "Boost a Stat"),
        (CODED_WARD, "Ward a Location"),
        (CODED_HEAL, "Heal a Character"),
        (CODED_EMIT, "Simply Emits Flavor Text"),
        (CODED_MAP, "Temporarily Reveal an Exploration Map"),
        (CODED_APPLY_COMBAT_CONDITION, "Apply a Combat Condition"),
        (CODED_REMOVE_COMBAT_CONDITION, "Remove a Combat Condition"),
        (CODED_APPLY_COMBAT_EFFECT, "Apply a Combat Effect"),
        (CODED_REMOVE_COMBAT_EFFECT, "Remove a Combat Effect"),
        (CODED_SET_WEATHER, "Change the Weather"),
        (CODED_ANIMA_RITUAL, "Anima Ritual"),
    )

    name = models.CharField(max_length=20, blank=False, null=False)
    description = models.TextField(blank=True, null=True)
    target_type = models.PositiveSmallIntegerField(
        default=TARGET_TYPE_NONE, choices=TARGET_TYPES
    )
    weave_usable = models.BooleanField(default=True)
    coded_effect = models.PositiveSmallIntegerField(
        default=CODED_SIGHT, choices=CODED_EFFECTS
    )
    coded_params = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Parameters specific to the coded effect type.",
    )
    base_difficulty = models.PositiveSmallIntegerField(default=70)
    base_cost = models.PositiveSmallIntegerField(default=500)
    required_favor = models.PositiveIntegerField(
        default=0, help_text="A base amount of favor required to " "weave this effect."
    )
    affinity = models.ForeignKey(
        Affinity, blank=True, null=True, related_name="+", on_delete=models.SET_NULL
    )
    antagonistic = models.BooleanField(
        default=False, help_text="Is this effect harmful to the target?"
    )
    want_opposed = models.BooleanField(
        default=False,
        help_text="Is this effect more effective when used on an opposed affinity? "
        "(If not, it will be more effective when used on the same affinity.)",
    )
    conditions = models.CharField(max_length=255, blank=True, null=True)
    strength = models.PositiveSmallIntegerField(default=10, blank=False, null=False)
    success_msg = models.TextField(blank=True, null=True)

    CODED_EFFECT_HANDLERS = {}

    def __str__(self):
        return self.name

    @classmethod
    def register_effect_handler(cls, effect_type, handler):
        cls.CODED_EFFECT_HANDLERS[effect_type] = handler

    @property
    def effect_handler_class(self):
        if self.coded_effect not in self.__class__.CODED_EFFECT_HANDLERS:
            return None

        return self.__class__.CODED_EFFECT_HANDLERS[self.coded_effect]

    def parse_target_obj(self, practitioner, target_string):
        if self.target_type == Effect.TARGET_TYPE_SELF:
            return practitioner.character, True
        if self.target_type == Effect.TARGET_TYPE_LOCATION:
            return practitioner.character.location, True
        if self.target_type in [
            Effect.TARGET_TYPE_CHARACTER,
            Effect.TARGET_TYPE_OBJECT,
            Effect.TARGET_TYPE_EITHER,
        ]:
            results = practitioner.character.search(
                target_string,
                global_search=False,
                quiet=True,
                location=practitioner.character.location,
            )
            final_results = []
            for obj in results:
                is_character = obj.has_account or (
                    hasattr(obj, "is_character") and obj.is_character
                )
                if self.target_type == Effect.TARGET_TYPE_OBJECT:
                    if not is_character:
                        final_results.append(obj)
                elif self.target_type == Effect.TARGET_TYPE_CHARACTER:
                    if is_character:
                        final_results.append(obj)
                elif self.target_type == Effect.TARGET_TYPE_EITHER:
                    final_results.append(obj)

            if len(final_results) == 1:
                return final_results[0], True

            return None, False

        return None, True


class PractitionerAlignment(SharedMemoryModel):

    practitioner = models.ForeignKey(
        "Practitioner",
        null=False,
        blank=False,
        related_name="alignments",
        on_delete=models.CASCADE,
    )
    alignment = models.ForeignKey(
        Alignment, null=False, blank=False, on_delete=models.CASCADE
    )
    value = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("practitioner", "alignment")

    def __str__(self):
        return "{}'s {} level".format(self.practitioner, self.alignment)


class PractitionerFavor(SharedMemoryModel):

    practitioner = models.ForeignKey(
        "Practitioner",
        blank=False,
        null=False,
        related_name="favored_by",
        on_delete=models.CASCADE,
    )
    alignment = models.ForeignKey(
        Alignment,
        blank=False,
        null=False,
        related_name="favored",
        on_delete=models.CASCADE,
    )
    value = models.PositiveIntegerField(default=0)
    gm_notes = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ("practitioner", "alignment")


class Practitioner(SharedMemoryModel):

    character = models.OneToOneField(
        "objects.ObjectDB",
        blank=False,
        null=False,
        related_name="practitioner_record",
        on_delete=models.CASCADE,
    )
    potential = models.PositiveIntegerField(default=1)
    anima = models.PositiveIntegerField(default=1)
    unspent_resonance = models.FloatField(default=0.0)
    raw_alignment = models.ForeignKey(
        Alignment, blank=True, null=True, related_name="+", on_delete=models.SET_NULL
    )
    raw_affinity = models.ForeignKey(
        Affinity, blank=True, null=True, related_name="+", on_delete=models.SET_NULL
    )
    stat = models.CharField(max_length=40, default="intellect")
    skill = models.CharField(max_length=40, default="occult")
    language = models.CharField(
        max_length=20,
        default="Arvani",
        help_text="The language in which this practitioner casts.",
    )
    verb = models.CharField(
        max_length=20,
        default="chants",
        help_text="The verb (chants, sings, etc.) to describe "
        "this practitioner's casting style.",
    )
    gesture = models.CharField(
        max_length=255,
        default="gestures expansively and energetically",
        help_text="Short descriptive fragment of how this practitioner casts.",
    )
    sigil_desc = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="What this person's magic looks for description as a signature "
        "(on wards and workings).",
    )
    sigil_emit = models.TextField(
        blank=True,
        null=True,
        help_text="The emit that's shown to mage-sight when this practitioner works magic.",
    )
    magic_desc_short = models.CharField(
        max_length=1024,
        blank=True,
        null=True,
        help_text="A short description of someone's magic, to be included in a "
        "generated sentence",
    )
    magic_desc = models.TextField(
        blank=True,
        null=True,
        help_text="Additional text someone might see if they soulgaze this practitioner "
        "with high successes.",
    )
    nodes = models.ManyToManyField("SkillNode", through="SkillNodeResonance")
    spells = models.ManyToManyField("Spell", through="PractitionerSpell")
    effects = models.ManyToManyField("Effect", through="PractitionerEffect")

    def __str__(self):
        return self.character.name

    @staticmethod
    def practitioner_for_character(obj):
        try:
            practitioner = Practitioner.objects.get(character=obj)
            return practitioner
        except (
            Practitioner.DoesNotExist,
            Practitioner.MultipleObjectsReturned,
            TypeError,
        ):
            return None

    @staticmethod
    def by_id(id_num):
        try:
            practitioner = Practitioner.objects.get(id=id_num)
            return practitioner
        except (Practitioner.DoesNotExist, Practitioner.MultipleObjectsReturned):
            return None

    @property
    def best_affinity(self):
        affinities = {}
        nodes = SkillNodeResonance.objects.filter(practitioner=self)
        for node in nodes:
            if node.node.affinity:
                old_value = (
                    affinities[node.node.affinity]
                    if node.node.affinity in affinities
                    else 0
                )
                affinities[node.node.affinity] = old_value + node.resonance

        result = None
        max_value = 0
        for affinity, value in affinities.items():
            if value > max_value:
                result = affinity
                max_value = value

        return result

    @property
    def alignment(self):
        if self.raw_alignment:
            return self.raw_alignment

        alignments = PractitionerAlignment.objects.filter(practitioner=self).order_by(
            "-value"
        )
        if alignments.count() > 0:
            return alignments[0].alignment

        return Alignment.PRIMAL

    @property
    def affinity(self):
        if self.raw_affinity:
            return self.raw_affinity

        return self.best_affinity

    def resonance_record_for_node(self, node):
        try:
            resonance_node = SkillNodeResonance.objects.get(
                practitioner=self, node=node
            )
        except (
            SkillNodeResonance.DoesNotExist,
            SkillNodeResonance.MultipleObjectsReturned,
        ):
            return None

        return resonance_node

    def resonance_for_node(self, node):
        value = 0
        resonance_record = self.resonance_record_for_node(node)
        if resonance_record:
            value = resonance_record.resonance

        if node.parent_node:
            value += self.resonance_for_node(node.parent_node) / 10

        return value

    def knows_spell(self, spell):
        return spell in self.spells.all()

    def knows_node(self, node):
        return node in self.nodes.all()

    def knows_effect(self, effect):
        return effect in self.effects.all()

    def can_learn_spell(self, spell):
        return self.knows_node(spell.node)

    def can_learn_effect(self, effect):
        for node in effect.nodes.all():
            if self.knows_node(node):
                return True

        return False

    def add_resonance_to_node(self, node, amount):
        try:
            resonance_node = SkillNodeResonance.objects.get(
                practitioner=self, node=node
            )
        except (
            SkillNodeResonance.DoesNotExist,
            SkillNodeResonance.MultipleObjectsReturned,
        ):
            return

        before = resonance_node.resonance
        after = min(self.potential, resonance_node.raw_resonance + amount)
        if after == self.potential:
            self.send_inform(
                "You feel that you've reached the limit of your ability to learn |y%s|n until "
                "you improve as a practitioner." % node.name
            )
        resonance_node.raw_resonance = after
        resonance_node.save()

        if before != after:
            explanation_string = "Discovered by improving {}.".format(node.name)
            child_nodes = node.child_nodes.filter(
                auto_discover=True, required_resonance__lte=after
            ).exclude(id__in=self.nodes.all())
            if child_nodes.count():
                for child_node in child_nodes.all():
                    self.open_node(
                        child_node,
                        SkillNodeResonance.LEARN_DISCOVERED,
                        explanation=explanation_string,
                    )

            spells = node.spells.filter(
                auto_discover=True, required_resonance__lte=after
            ).exclude(id__in=self.spells.all())
            if spells.count():
                for spell in spells.all():
                    self.learn_spell(
                        spell,
                        PractitionerSpell.LEARN_DISCOVERED,
                        explanation=explanation_string,
                    )

            effects = node.effect_records.filter(
                auto_discover=True, required_resonance__lte=after
            ).exclude(effect__in=self.effects.all())
            if effects.count():
                for effect in effects.all():
                    self.learn_effect(
                        effect,
                        PractitionerEffect.LEARN_DISCOVERED,
                        explanation=explanation_string,
                    )

            conditions = node.conditions.filter(
                auto_discover=True, required_resonance__lte=after
            )
            if conditions.count():
                for condition in conditions.all():
                    self.gain_condition(
                        condition, explanation="Gained by improving %s." % node.name
                    )

        if node.parent_node:
            self.add_resonance_to_node(node.parent_node, amount / 20)

    def gain_condition(self, condition, explanation=None):
        conditions = self.conditions.filter(condition=condition)
        if conditions.count() > 0:
            return

        PractitionerCondition.objects.create(
            practitioner=self, condition=condition, gm_notes=explanation
        )
        inform_staff(
            "|y%s|n just gained the |y%s|n condition: %s"
            % (self, condition, explanation)
        )

    def apply_alignment(self, align, amount):
        try:
            practalign = PractitionerAlignment.objects.get(
                practitioner=self, alignment=align
            )
        except PractitionerAlignment.DoesNotExist:
            practalign = PractitionerAlignment.objects.create(
                practitioner=self, alignment=align
            )

        practalign.value = practalign.value + amount
        practalign.save()

    def send_inform(self, text):
        self.character.dompc.player.inform(text, category="Magic", append=True)

    def open_node(self, node, reason, explanation=None):
        if self.knows_node(node):
            return None

        result = SkillNodeResonance.objects.create(
            practitioner=self,
            node=node,
            learned_by=reason,
            learned_on=datetime.now(),
            learned_notes=explanation,
        )

        inform_string = "just unlocked node |y{}|n in the magic tree by {}".format(
            node.name, SkillNodeResonance.reason_string(reason)
        )
        if explanation:
            inform_string += ": " + explanation
        else:
            inform_string += "."

        inform_staff("|y" + self.character.name + "|n " + inform_string)
        self.send_inform("You " + inform_string)

        return result

    def learn_spell(self, spell, reason, explanation=None):
        if self.knows_spell(spell):
            return

        PractitionerSpell.objects.create(
            practitioner=self,
            spell=spell,
            learned_by=reason,
            learned_on=datetime.now(),
            learned_notes=explanation,
        )

        inform_string = "just learned spell |y{}|n by {}".format(
            spell.name, PractitionerSpell.reason_string(reason)
        )
        if explanation:
            inform_string += ": " + explanation
        else:
            inform_string += "."

        inform_staff("|y" + self.character.name + "|n " + inform_string)
        self.send_inform("You " + inform_string)

    def teach_node(self, node, teacher):
        resonance_record = self.resonance_record_for_node(node)
        if not resonance_record:
            resonance_record = self.open_node(
                node,
                SkillNodeResonance.LEARN_TAUGHT,
                "Taught by " + teacher.character.name,
            )

        resonance_record.add_teacher(teacher)

    def learn_effect(self, effect, reason, explanation=None):
        if self.knows_effect(effect):
            return

        PractitionerEffect.objects.create(
            practitioner=self,
            effect=effect,
            learned_by=reason,
            learned_on=datetime.now(),
            learned_notes=explanation,
        )

        inform_string = "just learned effect |y{}|n by {}".format(
            effect.name, PractitionerEffect.reason_string(reason)
        )
        if explanation:
            inform_string += ": " + explanation
        else:
            inform_string += "."

        inform_staff("|y" + self.character.name + "|n " + inform_string)
        self.send_inform("You " + inform_string)

    def resonance_for_main_school(self):
        nodes = SkillNodeResonance.objects.filter(
            practitioner=self, node__parent_node__isnull=True
        ).order_by("-raw_resonance")

        if nodes.count() == 0:
            # Are you even a mage?
            return 0

        return self.resonance_for_node(nodes[0])

    def resonance_for_affinity(self, affinity):
        nodes = SkillNodeResonance.objects.filter(
            practitioner=self, node__affinity=affinity, node__affinity_default=True
        ).order_by("-raw_resonance")

        if nodes.count() > 0:
            return self.resonance_for_node(nodes[0].node)

        return 0

    def roll_magic(self, difficulty):
        stat_list = ["mana", self.stat]
        roll = Roll(
            self.character,
            stat_list=stat_list,
            skill=self.skill,
            average_stat_list=True,
            difficulty=difficulty,
            quiet=True,
        )
        return roll.roll()

    def notify_magic(self, magic_string):
        self.character.msg(magic_string, options={"is_magic": True, "is_pose": True})

    def check_perceive_magic(self, magic_string, strength=10):
        difficulty = 50 - (strength / 10)
        if self.roll_magic(difficulty) >= 0:
            self.notify_magic(magic_string)

    @property
    def magic_state(self):
        value = math.trunc(self.anima / (self.potential / 10.0))

        if value == 0:
            return "You feel so exhausted that you're close to dead!"
        elif 1 <= value <= 3:
            return "You feel exhausted."
        elif 4 <= value <= 6:
            return "You feel fairly normal."
        elif 7 <= value <= 9:
            return "You feel fairly energetic."
        else:
            return "You feel downright great!"

    @property
    def casting_emit(self):
        return "{} {} in {} and {}!".format(
            self.character.name,
            self.verb.lower(),
            self.language.capitalize(),
            self.gesture,
        )

    def emit_casting_gestures(self, location, tool=None):
        if tool:
            casting_string = "Using {}, {} {} in %s and {}!".format(
                self.character.name, self.tool.obj.name, self.verb.lower(), self.gesture
            )
        else:
            casting_string = "{} {} in %s and {}!".format(
                self.character.name, self.verb.lower(), self.gesture
            )

        for obj in location.contents:
            if self.language.lower() == "arvani" or obj.tags.get(
                self.language, "languages"
            ):
                language_string = self.language.capitalize()
            else:
                language_string = "a foreign tongue"

            obj.msg(
                casting_string % language_string,
                from_obj=self.character,
                options={"is_pose": True},
            )

    def emit_sigil(self, location, strength=10):
        if self.sigil_emit:
            sigil_string = self.sigil_emit
        else:
            sigil_string = "As {} works magic, the effect spreading out from them resembles {}.".format(
                self.character.name, self.sigil_desc
            )
        location.msg_contents_magic(sigil_string, strength=strength)

    @property
    def magic_description(self):
        return self.magic_desc_short

    @property
    def magic_description_advanced(self):
        return self.magic_desc

    def favor_for_alignment(self, align):
        try:
            favor = PractitionerFavor.objects.get(practitioner=self, alignment=align)
            return favor.value
        except (
            PractitionerFavor.DoesNotExist,
            PractitionerFavor.MultipleObjectsReturned,
        ):
            pass

        return 0

    @property
    def favor(self):
        abyssal = self.favor_for_alignment(Alignment.ABYSSAL)
        elysian = self.favor_for_alignment(Alignment.ELYSIAN)
        return max(abyssal, elysian)

    @property
    def eyes_open(self):
        return (
            self.node_resonances.filter(
                node__eyes_open=True, raw_resonance__gte=0
            ).count()
            > 0
        )

    def at_magic_exposure(self, alignment=None, affinity=None, strength=10):
        conditions = None
        if affinity:
            conditions = self.conditions.filter(
                condition_alignment=alignment, condition__affinity=affinity
            )

        if not conditions or conditions.count() == 0:
            conditions = self.conditions.filter(
                condition__alignment=alignment, condition__affinity=None
            )

        if conditions.count() == 0:
            return

        for condition in conditions.all():
            condition.condition.apply_to_practitioner(self, strength=strength)

    @property
    def anima_rituals(self):
        from django.db.models import Q

        return (
            self.workings.filter(
                Q(spell__effects__coded_effect=Effect.CODED_ANIMA_RITUAL)
                | Q(weave_effect__coded_effect=Effect.CODED_ANIMA_RITUAL)
            )
            .distinct()
            .count()
        )

    @property
    def anima_rituals_this_week(self):
        from .advancement import MagicAdvancementScript

        script = MagicAdvancementScript.objects.first()
        try:
            last_week = script.db.run_date - timedelta(days=7)
        except AttributeError:
            last_week = datetime.now() - timedelta(days=7)
        return self.anima_rituals.filter(finalized_at__gte=last_week)


class PractitionerEffect(SharedMemoryModel):

    LEARN_FIAT = 0
    LEARN_TAUGHT = 1
    LEARN_DISCOVERED = 2

    LEARN_TYPES = (
        (LEARN_FIAT, "Staff Fiat"),
        (LEARN_TAUGHT, "Teaching"),
        (LEARN_DISCOVERED, "Discovery"),
    )

    practitioner = models.ForeignKey(
        Practitioner,
        default=False,
        null=False,
        related_name="effect_discoveries",
        on_delete=models.CASCADE,
    )
    effect = models.ForeignKey(
        Effect,
        default=False,
        null=False,
        related_name="known_by",
        on_delete=models.CASCADE,
    )
    learned_by = models.PositiveSmallIntegerField(
        default=LEARN_FIAT, choices=LEARN_TYPES, blank=False, null=False
    )
    learned_on = models.DateField(blank=True, null=True)
    learned_notes = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        unique_together = ("practitioner", "effect")

    def __str__(self):
        return "{}'s knowledge of {}".format(self.practitioner, self.effect)

    @classmethod
    def reason_string(cls, reason):
        for values in cls.LEARN_TYPES:
            if values[0] == reason:
                return values[1].lower()

        return None


class SkillNode(SharedMemoryModel):

    name = models.CharField(max_length=40, blank=False, null=False)
    description = models.TextField(blank=True, null=True)
    parent_node = models.ForeignKey(
        "self",
        blank=True,
        null=True,
        related_name="child_nodes",
        on_delete=models.CASCADE,
    )
    eyes_open = models.BooleanField(
        default=False,
        help_text="If set, then having this node open means "
        "someone's eyes are opened.",
    )
    auto_discover = models.BooleanField(default=False)
    discovered_by_revelations = models.ManyToManyField(
        "character.Revelation",
        blank=True,
        related_name="nodes",
        help_text="If we discover these revelations, the node is "
        "automatically discovered.",
    )
    required_resonance = models.PositiveSmallIntegerField(default=10)
    affinity = models.ForeignKey(
        Affinity, blank=True, null=True, related_name="nodes", on_delete=models.SET_NULL
    )
    affinity_default = models.BooleanField(
        default=False,
        help_text="Does this node function as the default for this "
        "affinity in its tree?",
    )
    related_effects = models.ManyToManyField(
        Effect, through="SkillNodeEffect", related_name="nodes"
    )

    def __str__(self):
        return self.name


class SkillNodeEffect(SharedMemoryModel):

    node = models.ForeignKey(
        SkillNode,
        blank=False,
        null=False,
        related_name="effect_records",
        on_delete=models.CASCADE,
    )
    effect = models.ForeignKey(
        Effect,
        blank=False,
        null=False,
        related_name="node_records",
        on_delete=models.CASCADE,
    )
    auto_discover = models.BooleanField(default=False)
    required_resonance = models.PositiveSmallIntegerField(default=0)

    class Meta:
        unique_together = ("node", "effect")


class SkillNodeResonance(SharedMemoryModel):

    LEARN_FIAT = 0
    LEARN_TAUGHT = 1
    LEARN_DISCOVERED = 2

    LEARN_TYPES = (
        (LEARN_FIAT, "Staff Fiat"),
        (LEARN_TAUGHT, "Teaching"),
        (LEARN_DISCOVERED, "Discovery"),
    )

    practitioner = models.ForeignKey(
        Practitioner,
        default=False,
        null=False,
        related_name="node_resonances",
        on_delete=models.CASCADE,
    )
    node = models.ForeignKey(
        SkillNode,
        default=False,
        null=False,
        related_name="known_by",
        on_delete=models.CASCADE,
    )
    raw_resonance = models.FloatField(default=0.0)
    learned_by = models.PositiveSmallIntegerField(
        default=LEARN_FIAT, choices=LEARN_TYPES, blank=False, null=False
    )
    learned_on = models.DateField(blank=True, null=True)
    learned_notes = models.CharField(max_length=255, blank=True, null=True)
    teaching_multiplier = models.PositiveSmallIntegerField(blank=True, null=True)
    taught_by = models.CharField(max_length=40, blank=True, null=True)
    taught_on = models.DateTimeField(blank=True, null=True)
    practicing = models.BooleanField(default=False)

    class Meta:
        unique_together = ("practitioner", "node")

    def __str__(self):
        return "{}'s {} resonance".format(self.practitioner, self.node)

    @classmethod
    def reason_string(cls, reason):
        for values in cls.LEARN_TYPES:
            if values[0] == reason:
                return values[1].lower()

        return None

    @property
    def resonance(self):
        return math.trunc(self.raw_resonance)

    def add_teacher(self, teacher):
        teacher_resonance = teacher.resonance_for_node(self.node)
        self.taught_by = teacher.character.name
        self.teaching_multiplier = math.trunc(teacher_resonance ** (1 / 10.0))
        self.taught_on = datetime.now()


class Condition(SharedMemoryModel):

    name = models.CharField(max_length=40)
    alignment = models.ForeignKey(Alignment, on_delete=models.CASCADE)
    affinity = models.ForeignKey(
        Affinity, blank=True, null=True, on_delete=models.SET_NULL
    )
    description = models.TextField(blank=True, null=True)
    node = models.ForeignKey(
        SkillNode, related_name="conditions", on_delete=models.CASCADE
    )
    auto_discover = models.BooleanField(default=False)
    required_resonance = models.PositiveSmallIntegerField(
        blank=True,
        null=True,
        help_text="If auto_discover is set, the Condition will "
        "automatically be gained when you have this much "
        "resonance in the associated node.",
    )
    roll_stat = models.CharField(
        max_length=20,
        default="Will",
        help_text="The stat to roll to avoid this condition.",
    )
    roll_skill = models.CharField(
        max_length=25,
        default="Occult",
        help_text="The skill to roll to avoid this condition.",
    )
    roll_base_difficulty = models.PositiveSmallIntegerField(
        default=30,
        help_text="The base difficulty, which will be modified by "
        "effect strength and resonance of the attached "
        "node.",
    )
    positive_condition = models.BooleanField(
        default=False,
        help_text="If true, then succeeding the roll triggers this "
        "Condition; if false, failing does.",
    )
    effects = models.ManyToManyField(Effect, related_name="+")
    emit_room = models.TextField(blank=True, null=True)
    emit_self = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name

    @property
    def effects_list(self):
        names = []
        for effect in self.effects.all():
            names.append(effect.name)
        return commafy(names)

    def apply_to_practitioner(self, practitioner, strength=10):

        resonance = practitioner.resonance_for_node(self.node)
        if self.positive_condition:
            difficulty = self.roll_base_difficulty - ((strength + resonance) / 10)
        else:
            difficulty = self.roll_base_difficulty + ((strength - resonance) / 10)

        roll = Roll(
            practitioner.character,
            stat=self.roll_stat,
            skill=self.roll_skill,
            difficulty=difficulty,
            quiet=True,
        )
        successes = roll.roll()

        if self.positive_condition:
            should_execute = successes >= 0
        else:
            should_execute = successes < 0

        if should_execute:
            self.execute(practitioner, strength=strength, successes=abs(successes))

    def execute(self, practitioner, strength=10, successes=0):

        if self.emit_self:
            practitioner.character.msg_magic(self.emit_self, mundane=True)

        if self.emit_room:
            text = self.emit_room.replace("{name}", str(practitioner))
            practitioner.character.location.msg_contents_magic(text, mundane=True)

        for effect in self.effects.all():
            effect_class = effect.effect_handler_class
            if effect_class:
                handler = effect_class(
                    lead=practitioner,
                    participants=[practitioner],
                    target_string="me",
                    target_obj=practitioner.character,
                    parameters=effect.coded_params,
                    conditions=effect.conditions,
                    strength=strength,
                    alignment=self.alignment,
                    successes=successes,
                    quiet=False,
                    affinity=effect.affinity or self.affinity,
                )
                handler.calculate()
                handler.perform()
            else:
                logger.log_err(
                    "Condition %s's effect %s has no coded handler!"
                    % (self, self.effect)
                )


class PractitionerCondition(SharedMemoryModel):

    practitioner = models.ForeignKey(
        Practitioner, related_name="conditions", on_delete=models.CASCADE
    )
    condition = models.ForeignKey(
        Condition, related_name="afflicted", on_delete=models.CASCADE
    )
    gm_notes = models.TextField(null=True, blank=True)

    class Meta:
        unique_together = ("practitioner", "condition")

    def __str__(self):
        return "%s's %s condition" % (self.practitioner, self.condition)


class Spell(SharedMemoryModel):

    name = models.CharField(max_length=40, blank=False, null=False)
    description = models.TextField(blank=True, null=True)
    node = models.ForeignKey(
        SkillNode,
        blank=False,
        null=False,
        related_name="spells",
        on_delete=models.CASCADE,
    )
    effects = models.ManyToManyField(Effect, through="SpellEffect", related_name="+")
    alignment = models.ForeignKey(
        Alignment, blank=True, null=True, related_name="+", on_delete=models.SET_NULL
    )
    affinity = models.ForeignKey(
        Affinity, blank=True, null=True, related_name="+", on_delete=models.SET_NULL
    )
    auto_discover = models.BooleanField(default=False)
    discovered_by_clues = models.ManyToManyField(
        "character.Clue",
        blank=True,
        related_name="spells",
        help_text="If we discover any of these clues, the spell is "
        "automatically learned.",
    )
    required_resonance = models.PositiveSmallIntegerField(default=1)
    required_favor = models.PositiveIntegerField(
        default=0,
        help_text="A base amount of favor required with Abyssal or "
        "Elysian to cast this spell.",
    )
    base_difficulty = models.PositiveSmallIntegerField(default=50)
    base_cost = models.PositiveSmallIntegerField(default=50)
    extra_primum = models.PositiveSmallIntegerField(
        default=100,
        help_text="What percentage of a player's anima can "
        "they pull from external sources for this "
        "spell?  100% means they can pull exactly "
        "as much as their maximum anima.",
    )
    success_msg = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name

    def get_spell_success_msg(self, practitioner):
        try:
            return (
                self.known_by.get(practitioner=practitioner).success_msg
                or self.success_msg
            )
        except PractitionerSpell.DoesNotExist:
            return self.success_msg


class SpellEffect(SharedMemoryModel):

    spell = models.ForeignKey(
        Spell,
        blank=False,
        null=False,
        related_name="spell_effects",
        on_delete=models.CASCADE,
    )
    effect = models.ForeignKey(
        Effect, blank=False, null=False, related_name="+", on_delete=models.CASCADE
    )
    primary = models.BooleanField(default=False)

    class Meta:
        unique_together = ("spell", "effect")


class PractitionerSpell(SharedMemoryModel):

    LEARN_FIAT = 0
    LEARN_TAUGHT = 1
    LEARN_DISCOVERED = 2

    LEARN_TYPES = (
        (LEARN_FIAT, "Staff Fiat"),
        (LEARN_TAUGHT, "Teaching"),
        (LEARN_DISCOVERED, "Discovery"),
    )

    practitioner = models.ForeignKey(
        Practitioner,
        blank=False,
        null=False,
        related_name="spell_discoveries",
        on_delete=models.CASCADE,
    )
    spell = models.ForeignKey(
        Spell,
        blank=False,
        null=False,
        related_name="known_by",
        on_delete=models.CASCADE,
    )
    learned_by = models.PositiveSmallIntegerField(
        default=LEARN_FIAT, choices=LEARN_TYPES, blank=False, null=False
    )
    learned_on = models.DateField(blank=False, null=False)
    learned_notes = models.CharField(max_length=255, blank=True, null=True)
    success_msg = models.TextField(
        blank=True, help_text="Custom message for our version of the spell"
    )

    class Meta:
        unique_together = ("practitioner", "spell")

    @classmethod
    def reason_string(cls, reason):
        for values in cls.LEARN_TYPES:
            if values[0] == reason:
                return values[1].lower()

        return None


class Attunement(SharedMemoryModel):

    practitioner = models.ForeignKey(
        Practitioner,
        blank=False,
        null=False,
        related_name="attunements",
        on_delete=models.CASCADE,
    )
    obj = models.ForeignKey(
        "objects.ObjectDB",
        blank=False,
        null=False,
        related_name="attuned_by",
        on_delete=models.CASCADE,
    )
    raw_attunement_level = models.FloatField(default=0.0)

    def __str__(self):
        return "{}'s attunement to {}".format(
            self.practitioner, strip_ansi(self.obj.name)
        )

    @property
    def attunement_level(self):
        return math.trunc(self.raw_attunement_level)


class FamiliarAttunement(SharedMemoryModel):

    practitioner = models.ForeignKey(
        Practitioner,
        blank=False,
        null=False,
        related_name="familiars",
        on_delete=models.CASCADE,
    )
    familiar = models.ForeignKey(
        "dominion.Agent",
        blank=False,
        null=False,
        related_name="bondmates",
        on_delete=models.CASCADE,
    )
    raw_attunement_level = models.FloatField(default=0.0)

    def __str__(self):
        return "{}'s familiar bond with {}".format(
            self.practitioner, strip_ansi(self.familiar.name)
        )

    @property
    def attunement_level(self):
        return math.trunc(self.raw_attunement_level)


class ClueCollection(SharedMemoryModel):

    name = models.CharField(max_length=80, blank=False, null=False)
    gm_notes = models.TextField(blank=True, null=True)
    clues = models.ManyToManyField("character.Clue", related_name="magic_collections")


class MagicBucket(SharedMemoryModel):

    name = models.CharField(max_length=80, blank=False, null=False)
    gm_notes = models.TextField(blank=True, null=True)
    value = models.PositiveIntegerField(default=0)


class WorkingParticipant(SharedMemoryModel):

    practitioner = models.ForeignKey(
        Practitioner,
        blank=False,
        null=False,
        related_name="+",
        on_delete=models.CASCADE,
    )
    working = models.ForeignKey(
        "Working",
        blank=False,
        null=False,
        related_name="participant_records",
        on_delete=models.CASCADE,
    )
    accepted = models.BooleanField(default=False)
    tool = models.ForeignKey(
        Attunement, blank=True, null=True, related_name="+", on_delete=models.SET_NULL
    )
    familiar = models.ForeignKey(
        FamiliarAttunement,
        blank=True,
        null=True,
        related_name="+",
        on_delete=models.SET_NULL,
    )
    drained = models.ManyToManyField("objects.ObjectDB", related_name="+")

    def __str__(self):
        result = str(self.practitioner)
        additional = None

        if self.tool:
            additional = "using " + strip_ansi(self.tool.obj.name)

        if self.familiar:
            if not additional:
                additional = ""
            else:
                additional += ", "

            additional += "working with " + self.familiar.familiar.name

        if additional:
            result += " (" + additional + ")"

        return result

    def has_drain(self, obj):
        return obj in self.drained.all()

    def add_drain(self, obj):
        if obj in self.drained.all():
            return

        self.drained.add(obj)
        self.save()

    def remove_drain(self, obj):
        if obj not in self.drained.all():
            return

        self.drained.remove(obj)
        self.save()


class Working(SharedMemoryModel):

    QUIET_NONE = 0
    QUIET_MUNDANE = 1
    QUIET_TOTAL = 2

    QUIET_TYPES = (
        (QUIET_NONE, "None"),
        (QUIET_MUNDANE, "Mundane"),
        (QUIET_TOTAL, "Total"),
    )

    lead = models.ForeignKey(
        Practitioner,
        related_name="workings",
        blank=False,
        null=False,
        on_delete=models.CASCADE,
    )
    practitioners = models.ManyToManyField(
        Practitioner, through="WorkingParticipant", related_name="assisted_workings"
    )
    template = models.BooleanField(default=False)
    template_name = models.CharField(max_length=40, blank=True, null=True)
    quiet_level = models.PositiveSmallIntegerField(
        default=QUIET_NONE, choices=QUIET_TYPES
    )
    intent = models.TextField(blank=True, null=True)
    spell = models.ForeignKey(Spell, blank=True, null=True, on_delete=models.CASCADE)
    weave_effect = models.ForeignKey(
        Effect, blank=True, null=True, related_name="+", on_delete=models.SET_NULL
    )
    weave_alignment = models.ForeignKey(
        Alignment, blank=True, null=True, related_name="+", on_delete=models.SET_NULL
    )
    weave_affinity = models.ForeignKey(
        Affinity, blank=True, null=True, related_name="+", on_delete=models.SET_NULL
    )
    target_string = models.CharField(max_length=60, blank=True, null=True)
    econ = models.PositiveSmallIntegerField(blank=True, default=0)
    gm_cost = models.PositiveIntegerField(blank=True, default=0)
    gm_difficulty = models.PositiveSmallIntegerField(blank=True, default=0)
    gm_strength = models.PositiveSmallIntegerField(
        blank=True,
        default=0,
        help_text="The base 'strength' of this magic, when it's a " "GM'd working.",
    )
    primum_at_perform = models.PositiveSmallIntegerField(blank=True, default=0)
    total_successes = models.PositiveSmallIntegerField(blank=True, default=0)
    total_favor = models.PositiveIntegerField(blank=True, default=0)
    effects_result = models.TextField(blank=True, null=True)
    effects_description = models.TextField(blank=True, null=True)
    consequence_result = models.TextField(blank=True, null=True)
    consequence_description = models.TextField(blank=True, null=True)
    calculated = models.BooleanField(default=False)
    finalized = models.BooleanField(default=False)
    finalized_at = models.DateTimeField(blank=True, null=True)

    REGISTERED_CONSEQUENCES = {}

    def __init__(self, *args, **kwargs):
        super(Working, self).__init__(*args, **kwargs)
        self.performed = False
        self.cached_target_obj = None
        self.cached_consequence = None
        self.cached_effect_handlers = None

    @classmethod
    def register_consequence(cls, danger_level, consequence, weight=10):
        consequences = []
        if danger_level in cls.REGISTERED_CONSEQUENCES:
            consequences = cls.REGISTERED_CONSEQUENCES[danger_level]
        consequences.append((consequence, weight))
        cls.REGISTERED_CONSEQUENCES[danger_level] = consequences

    @classmethod
    def random_consequence(cls, danger_level):
        if danger_level not in cls.REGISTERED_CONSEQUENCES:
            return None

        consequences = cls.REGISTERED_CONSEQUENCES[danger_level]
        picker = WeightedPicker()
        for consequence_tuple in consequences:
            picker.add_option(consequence_tuple[0], consequence_tuple[1])

        return picker.pick()

    @property
    def consequence_handler(self):
        if not self.cached_consequence and self.consequence_result:
            from world.magic.consequences import MagicConsequence

            self.cached_consequence = MagicConsequence.loads(self.consequence_result)

        return self.cached_consequence

    @property
    def effect_handlers(self):
        if not self.cached_effect_handlers and self.effects_result:
            from world.magic.effects import CodedEffect

            result = []
            serialized_array = json.loads(self.effects_result)
            for entry in serialized_array:
                handler = CodedEffect.loads(entry)
                if handler:
                    result.append(handler)
            self.cached_effect_handlers = result

        return self.cached_effect_handlers

    @property
    def participants(self):
        records = self.participant_records.filter(accepted=True)
        return [r.practitioner for r in records.all()]

    @property
    def drained(self):
        result = []
        records = self.participant_records.filter(accepted=True)
        for record in records:
            result += record.drained.all()

        return result

    @property
    def short_description(self):
        if self.intent:
            return "'{}'".format(self.intent)
        elif self.spell:
            return "cast the spell '{}'".format(self.spell.name)
        elif self.weave_effect:
            if self.weave_alignment:
                return "weave with the {} effect '{}'".format(
                    self.weave_alignment.name, self.weave_effect.name
                )
            else:
                return "weave with the effect '{}'".format(self.weave_effect.name)
        else:
            return "unknown"

    def add_practitioner(self, practitioner, tool=None, familiar=None, accepted=False):
        if practitioner in self.participants:
            return

        WorkingParticipant.objects.create(
            practitioner=practitioner,
            working=self,
            tool=tool,
            familiar=familiar,
            accepted=accepted,
        )

    def update_practitioner(
        self, practitioner, tool=None, familiar=None, clear_empty=False
    ):
        try:
            record = WorkingParticipant.objects.get(
                working=self, practitioner=practitioner
            )
            if tool or clear_empty:
                record.tool = tool
            if familiar or clear_empty:
                record.familiar = familiar
            record.save()
        except WorkingParticipant.DoesNotExist:
            raise ValueError("That participant isn't part of this working.")

    def accept_practitioner(self, practitioner):

        try:
            record = WorkingParticipant.objects.get(
                working=self, practitioner=practitioner
            )
            record.accepted = True
            record.save()
        except WorkingParticipant.DoesNotExist:
            raise ValueError("That participant isn't part of this working.")

    def decline_practitioner(self, practitioner):

        try:
            record = WorkingParticipant.objects.get(
                working=self, practitioner=practitioner
            )
            record.delete()
        except WorkingParticipant.DoesNotExist:
            raise ValueError("That participant isn't part of this working.")

    def practitioner_record(self, practitioner):
        try:
            record = WorkingParticipant.objects.get(
                working=self, practitioner=practitioner
            )
            return record
        except WorkingParticipant.DoesNotExist:
            return None

    @property
    def favor_cost(self):
        if self.weave_effect:
            return self.weave_effect.required_favor

        if self.spell:
            return self.spell.required_favor

        return 0

    @property
    def available_favor(self):
        if self.total_favor:
            return self.total_favor

        if self.lead:
            self.total_favor = self.lead.favor
            self.save()
            return self.lead.favor

        return 0

    @property
    def attunements(self):
        result = []

        for record in self.participant_records.all():
            if record.tool:
                result.append(record.tool)

        return result

    @property
    def familiars(self):
        result = []

        for record in self.participant_records.all():
            if record.familiar:
                result.append(record.familiar)

        return result

    @property
    def effects(self):
        if self.spell:
            return self.spell.effects.all()

        if self.weave_effect:
            return [self.weave_effect]

        return []

    @property
    def spell_success_msg(self):
        if self.spell:
            return self.spell.get_spell_success_msg(self.lead)
        return ""

    @property
    def primary_effect(self):
        if self.weave_effect:
            return self.weave_effect

        if self.spell:
            primary = self.spell.spell_effects.filter(primary=True)
            if primary.count() > 0:
                return primary.all()[0].effect

        return None

    @property
    def target_obj(self):
        if self.cached_target_obj:
            return self.cached_target_obj

        primary = self.primary_effect
        if not primary:
            return None

        result = primary.parse_target_obj(self.lead, self.target_string)
        if result[1]:
            self.cached_target_obj = result[0]

        return self.cached_target_obj

    @property
    def affinity(self):
        if self.spell is not None:
            return self.spell.affinity
        elif self.weave_affinity is not None:
            return self.weave_affinity

        return None

    @property
    def alignment(self):
        if self.spell is not None:
            return self.spell.alignment or Alignment.PRIMAL
        elif self.weave_alignment is not None:
            return self.weave_alignment or Alignment.PRIMAL

        return Alignment.PRIMAL

    @property
    def strength(self):
        """
        This is an overall strength of a working, used for triggering responses, such as being
        detected by sensitives and the like.
        """
        if len(self.effects) == 0:
            return self.gm_strength

        total_effect_strength = 0
        for effect in self.effects:
            total_effect_strength += effect.strength

        average_strength = total_effect_strength / len(self.effects)

        return max(10, int(average_strength * max(1.0, self.base_cost / 10.0)))

    def effect_handler(self, effect, quiet=False, target_string=None):
        """
        Gets an instance of the effect handler class for a given effect. The effect handler class will
        be what actually causes the game effects of a given working when we finalize().
        """
        effect_class = effect.effect_handler_class
        if not effect_class:
            return None

        if not target_string:
            target_string = self.target_string

        result = effect.parse_target_obj(self.lead, target_string)
        target_obj = None
        if result[1]:
            target_obj = result[0]

        return effect_class(
            lead=self.lead,
            participants=self.participants,
            target_string=target_string,
            target_obj=target_obj,
            parameters=effect.coded_params,
            conditions=effect.conditions,
            strength=effect.strength,
            alignment=self.alignment,
            successes=self.total_successes,
            quiet=quiet,
            affinity=effect.affinity or self.affinity,
        )

    def validation_error(self, target_string=None, gm_override=False):
        if not gm_override and len(self.effects) == 0:
            return (
                "This working does not target a spell or weaving effect. This is fine if you're attaching "
                "it to an action, but means it cannot be performed by 'perform'."
            )

        if gm_override:
            if not self.difficulty:
                return "This working does not have a difficulty set, and cannot yet be performed."
            if not self.cost:
                return "This working does not yet have a cost set, and cannot yet be performed."
            if not self.gm_strength:
                return "This working does not yet have a strength set, and cannot yet be performed."

        for effect in self.effects:
            effect_handler = self.effect_handler(effect, target_string=target_string)
            if not effect_handler:
                return (
                    "The effect that this working targets has not been implemented yet!  "
                    "Please whine to staff to get on it."
                )

            other_errors = effect_handler.check_for_other_errors()
            if other_errors:
                return other_errors

            if not effect_handler.valid_target():
                return "Your target '{}' is not valid for the magical effect you've chosen.".format(
                    self.target_string
                )

            if not effect_handler.valid_parameters():
                return (
                    "Something has gone horribly wrong and the system is misconfigured. "
                    "Talk to staff and tell them what you tried to do!"
                )

            if effect_handler.requires_combat and not self.lead.character.combat.state:
                return "This effect can only be used when you are in combat."

        return None

    # noinspection PyMethodMayBeStatic
    def object_affinity(self, obj):
        practitioner = Practitioner.practitioner_for_character(obj)
        if practitioner:
            return practitioner.affinity

        if obj.db.affinity_id:
            try:
                affinity = Affinity.objects.get(id=obj.db.affinity_id)
            except (Affinity.DoesNotExist, Affinity.MultipleObjectsReturned):
                return None
            return affinity
        elif obj.db.alchemical_material:
            try:
                material = AlchemicalMaterial.objects.get(id=obj.db.alchemical_material)
            except (
                AlchemicalMaterial.DoesNotExist,
                AlchemicalMaterial.MultipleObjectsReturned,
            ):
                return None
            return material.affinity

        return None

    # noinspection PyMethodMayBeStatic
    def object_primum(self, obj):
        practitioner = Practitioner.practitioner_for_character(obj)
        if practitioner:
            return practitioner.anima

        if obj.db.primum:
            return obj.db.primum

        return 0

    def resonance_for_practitioner(self, practitioner):
        if self.spell is not None:
            result = practitioner.resonance_for_node(self.spell.node)
            if result == 0 and self.affinity:
                # Default to half our resonance for the affinity.
                result = practitioner.resonance_for_affinity(self.affinity) / 2
            return max(result, 1)

        if self.affinity is not None:
            return practitioner.resonance_for_affinity(self.affinity)

        # What are we even doing?
        return 1

    @property
    def base_cost(self):
        """Base cost is used for determining the strength of an effect before discounts"""
        if self.gm_cost:
            return self.gm_cost

        if self.spell is not None:
            return self.spell.base_cost
        elif self.weave_effect is not None:
            return self.weave_effect.base_cost
        else:
            return 0

    @property
    def cost(self):
        """
        Total cost in primum of the working. Increasing Resonance makes it cheaper, doing difficult things makes it
        more expensive.
        """
        if self.gm_cost:
            return self.gm_cost

        total_resonance = 0
        for participant in self.participants:
            total_resonance += self.resonance_for_practitioner(participant) / 25.0

        for tool in self.attunements:
            total_resonance += tool.attunement_level ** (1 / 25.0)

        for familiar in self.familiars:
            total_resonance += familiar.attunement_level ** (1 / 25.0)

        final_cost = self.base_cost / (1 + total_resonance)

        if self.quiet_level == Working.QUIET_MUNDANE:
            final_cost *= 1.5
        elif self.quiet_level == Working.QUIET_TOTAL:
            final_cost *= 2.0

        # Round any fractional values up
        if math.trunc(final_cost) != final_cost:
            final_cost = math.trunc(final_cost) + 1

        return final_cost

    @property
    def difficulty(self):
        if self.gm_difficulty:
            return self.gm_difficulty

        if self.spell is not None:
            base_diff = self.spell.base_difficulty
        elif self.weave_effect is not None:
            base_diff = self.weave_effect.base_difficulty
        else:
            return None

        if self.target_obj:
            target_affinity = self.object_affinity(self.target_obj)
            if target_affinity and self.affinity:
                if self.effect.want_opposed:
                    if target_affinity == self.affinity.opposed:
                        base_diff -= 5
                    elif target_affinity == self.affinity:
                        base_diff += 5
                else:
                    if target_affinity == self.affinity.opposed:
                        base_diff += 5
                    elif target_affinity == self.affinity:
                        base_diff -= 5

            if self.primary_effect.antagonistic:
                target_practitioner = Practitioner.practitioner_for_character(
                    self.target_obj
                )
                if target_practitioner:
                    target_resonance = self.resonance_for_practitioner(
                        target_practitioner
                    )
                    working_resonance = 0
                    for participant in self.participants:
                        working_resonance += self.resonance_for_practitioner(
                            participant
                        )

                    # The target is more powerful than the practitioners.
                    # This may hurt.
                    if target_resonance > working_resonance:
                        base_diff += target_resonance - working_resonance

        return base_diff

    @property
    def available_primum(self):
        return self.calculate_available_primum(draft=False)

    def calculate_available_primum(self, draft=False):
        if self.primum_at_perform:
            return self.primum_at_perform

        base_potential = 0
        available_primum = 0
        external_primum = 0
        if self.econ:
            external_primum += self.econ / 100

        if draft:
            # We include even those who haven't accepted yet.
            for record in self.participant_records.all():
                base_potential += record.practitioner.potential
                available_primum += record.practitioner.anima
                for obj in record.drained.all():
                    external_primum += self.object_primum(obj)
        else:
            for practitioner in self.participants:
                base_potential += practitioner.potential
                available_primum += practitioner.anima
            for drain in self.drained:
                external_primum += self.object_primum(drain)

        if self.spell:
            external_potential = base_potential * (self.spell.extra_primum / 100.0)
        else:
            external_potential = base_potential * 2

        external_primum = int(min(external_primum, external_potential))

        return available_primum + external_primum

    @property
    def successes(self):
        if not self.template and self.total_successes:
            return self.total_successes

        total_successes = 0
        difficulty = self.difficulty
        for practitioner in self.participants:
            total_successes += practitioner.roll_magic(difficulty)

        if not self.template:
            self.total_successes = total_successes
            self.save()

        return total_successes

    @property
    def danger_level(self):
        return self.calculate_danger_level(draft=False)

    @staticmethod
    def danger_level_string(danger_level=0):
        danger_description = "relatively safe"
        if danger_level == 1:
            danger_description = "somewhat risky, and you might be badly injured"
        elif danger_level == 2:
            danger_description = "very risky, with a chance of life-altering effects"
        elif danger_level == 3:
            danger_description = "extremely risky, with a high chance of death"
        elif danger_level == 4:
            danger_description = "suicidally risky"

        return danger_description

    def calculate_danger_level(self, draft=False):
        """
        Our danger scale is as follows:
        0  - Safe(-ish)
        1  - A little risky
        2  - High risk of non-fatal consequences
        3  - Risk of fatal consequences
        4+ - Suicidal
        """
        if not self.cost:
            return None

        difference = self.cost - self.calculate_available_primum(draft=draft)
        if difference <= 0:
            return 0

        # Our danger scale is the rounded 10-root of the difference between
        # cost and available primum.
        result = round(abs(difference) ** (1.0 / 10))

        # If we're Invoking/Beseeching, our danger goes down by one level
        if self.favor_cost > 0:
            result -= 1

        return max(0, result)

    # noinspection PyMethodMayBeStatic
    def drain(self, obj, amount):
        obj.drain_primum(amount)

    def pay_cost(self):
        effective_cost = min(self.cost, self.available_primum)

        base_potential = 0
        for practitioner in self.participants:
            base_potential += practitioner.potential

        if self.spell:
            external_potential = round(
                base_potential * (self.spell.extra_primum / 100.0)
            )
        else:
            external_potential = base_potential

        external_payment = 0

        if self.econ:
            external_payment += self.econ / 100

        if external_payment < external_potential:
            for drain_me in self.drained:
                remaining = external_potential - external_payment
                to_drain = min(drain_me.primum, remaining)
                self.drain(drain_me, to_drain)
                external_payment += to_drain

        remaining = effective_cost - external_payment
        per_practitioner = int(round(remaining / len(self.participants)))
        for practitioner in self.participants:
            to_drain = min(practitioner.anima, per_practitioner)
            practitioner.anima -= to_drain
            remaining -= to_drain

        # Someone didn't have enough primum, spread out what's left
        # across anyone who still has primum available
        if remaining > 0:
            for practitioner in self.participants:
                to_drain = min(practitioner.anima, remaining)
                practitioner.anima -= to_drain
                remaining -= to_drain

        for practitioner in self.participants:
            practitioner.save()

    @property
    def successes_to_beat(self):
        danger_level = self.danger_level
        result = self.difficulty
        if danger_level != 0:
            result *= danger_level * 3

        return result

    @property
    def has_pending(self):
        return self.participant_records.filter(accepted=False).count() > 0

    def perform(self, unsafe=False, gm_override=False):
        """
        The initial casting of the working. All the effects are calculated, but are not put into practice
        yet. That happens during the 'finalize' step. If the casting is not valid (bad target, didn't
        provide confirmation of wanting to do something that could be dangerous/potentially lethal, etc)
        then we return False and abort.
        """
        if self.performed:
            return False

        if not gm_override:
            error = self.validation_error()
            if error is not None:
                self.lead.character.msg(error)
                return False

        danger_level = self.danger_level
        if danger_level > 0 and not unsafe:
            danger_description = Working.danger_level_string(danger_level)

            self.lead.character.msg(
                "You sense that this working would be {} at this time.  "
                "If you still wish to attempt it, use the /unsafe switch.".format(
                    danger_description
                )
            )
            return False

        successes = self.successes
        if not self.template:
            self.performed = True
            self.finalized = False
            self.primum_at_perform = self.available_primum

        if self.available_favor >= self.favor_cost:
            if successes >= 1:
                effect_results = []
                effect_descriptions = []
                spell_msg = self.spell_success_msg
                if spell_msg:
                    effect_descriptions.append(spell_msg)
                for effect in self.effects:
                    effect_handler = self.effect_handler(effect, quiet=gm_override)
                    effect_handler.perform()
                    effect_results.append(str(effect_handler))
                    effect_descriptions.append(effect_handler.results_string())

                self.effects_result = json.dumps(effect_results)
                self.effects_description = " ".join(effect_descriptions)

        missed_by = self.successes_to_beat - successes
        if missed_by > 0:
            danger_level = self.danger_level
            consequence_handler_class = Working.random_consequence(danger_level)
            if consequence_handler_class:
                consequence_handler = consequence_handler_class(
                    participants=self.participants,
                    danger_level=danger_level,
                    success_diff=missed_by,
                    alignment=self.alignment,
                    affinity=self.affinity,
                )
                consequence_handler.calculate()
                self.consequence_result = str(consequence_handler)
                self.consequence_description = consequence_handler.results_string()

        self.calculated = True
        self.save()
        return True

    def finalize(self, gm_override=False):
        if not self.performed:
            return

        if self.finalized:
            return

        if not gm_override:
            location = self.lead.character.location
            for practitioner in self.participants:
                if self.quiet_level < Working.QUIET_MUNDANE:
                    practitioner.emit_casting_gestures(location)
                if self.quiet_level < Working.QUIET_TOTAL:
                    practitioner.emit_sigil(location, strength=self.strength)

        self.pay_cost()

        if self.alignment:
            for participant in self.participants:
                participant.apply_alignment(self.alignment, self.strength)

        if self.effect_handlers:
            for effect_instance in self.effect_handlers:
                effect_instance.finalize()

        if self.consequence_handler:
            self.consequence_handler.finalize()

        self.finalized = True
        self.finalized_at = datetime.now()
        self.save()

        if not gm_override:
            for obj in self.lead.character.location.contents:
                if hasattr(obj, "at_magic_exposure"):
                    obj.at_magic_exposure(
                        alignment=self.alignment,
                        affinity=self.affinity,
                        strength=self.strength,
                    )

    @property
    def participant_string(self):
        participant_names = [str(record) for record in self.participant_records.all()]
        return commafy(participant_names)

    @property
    def draft_participant_string(self):
        names = []
        for part in self.participant_records.all():
            if part.accepted:
                names.append(str(part.practitioner))
            else:
                names.append(str(part.practitioner) + "|r*|n")
        return commafy(names)

    def __str__(self):
        if self.template:
            return str(self.lead) + "'s template to " + self.short_description

        if self.calculated:
            partstring = self.participant_string
        else:
            partstring = strip_ansi(self.draft_participant_string)

        return partstring + " performing " + self.short_description

    def description_string(self):

        table = EvTable(border=None, width=78)
        table.add_column(width=20)
        table.add_column()

        table.add_row("ID: ", self.id)
        if not self.template:
            table.add_row("Participants: ", self.participant_string)
            table.add_row("Lead: ", self.lead.character.name)
        else:
            table.add_row("Practitioner: ", self.participant_string)
            table.add_row("Templated as: ", str(self.template_name))

        if self.alignment:
            table.add_row("Alignment: ", str(self.alignment.name))
        if self.affinity:
            table.add_row("Affinity: ", str(self.affinity.name))

        if self.quiet_level != Working.QUIET_NONE:
            if self.quiet_level == Working.QUIET_MUNDANE:
                table.add_row("Quiet: ", "Mundane Perception")
            elif self.quiet_level == Working.QUIET_TOTAL:
                table.add_row("Quiet: ", "Mundane and Magical Perception")

        if self.spell:
            table.add_row("Type: ", "Casting")
            table.add_row("Spell: ", str(self.spell.name))
        elif self.weave_effect:
            table.add_row("Type: ", "Weaving")
            table.add_row("Effect: ", str(self.weave_effect.name))
        else:
            table.add_row("Type: ", "GM'd Weaving or Ritual")
            table.add_row("GM Difficulty:", str(self.gm_difficulty))
            table.add_row("GM Cost:", str(self.gm_cost))
            table.add_row("GM Strength:", str(self.gm_strength))

        if not self.template:
            table.add_row("Calculated:", "yes" if self.calculated else "no")
            table.add_row("Performed: ", "yes" if self.finalized else "no")
            table.add_row("Available Primum: ", self.available_primum)
            table.add_row("Cost: ", self.cost)
            if self.cost:
                table.add_row(
                    "Danger Level: ", self.danger_level_string(self.danger_level)
                )
            else:
                table.add_row(
                    "Danger Level: ", "Not yet calculated; set gm_cost first."
                )

        if self.performed:
            table.add_row("Successes: ", self.successes)
            if self.effects_description:
                table.add_row("Result: ", self.effects_description)
            if self.consequence_description:
                table.add_row("Consequence: ", self.consequence_description)

        return str(table)

    def performable_copy(self, target=None):

        new_working = Working.objects.create(
            lead=self.lead,
            template=False,
            quiet_level=self.quiet_level,
            intent=self.intent,
            spell=self.spell,
            weave_effect=self.weave_effect,
            weave_alignment=self.weave_alignment,
            weave_affinity=self.weave_affinity,
            target_string=target or self.target_string,
            gm_cost=self.gm_cost,
            gm_difficulty=self.gm_difficulty,
        )

        for record in self.participant_records.all():
            new_working.add_practitioner(
                record.practitioner,
                tool=record.tool,
                familiar=record.familiar,
                accepted=True,
            )

        return new_working
