from world.magic.models import *
from server.utils.test_utils import ArxTest
from evennia.utils import create
from world.crafting.models import CraftingRecipe
from world.traits.models import Trait

_PENDING_MAGIC_NOTIFY = []


def override_roll_magic(self, difficulty):
    return 10


def override_notify_magic(text):
    global _PENDING_MAGIC_NOTIFY
    _PENDING_MAGIC_NOTIFY.append(text)


def override_check_perceive_magic(text, strength=10):
    global _PENDING_MAGIC_NOTIFY
    _PENDING_MAGIC_NOTIFY.append(text)


def override_msg(text, **kwargs):
    global _PENDING_MAGIC_NOTIFY
    if isinstance(text, tuple):
        text = text[0]
    _PENDING_MAGIC_NOTIFY.append(text)


def pending_magic_text():
    global _PENDING_MAGIC_NOTIFY
    result = "\n".join(_PENDING_MAGIC_NOTIFY)
    _PENDING_MAGIC_NOTIFY = []
    return result


class ArxMagicTest(ArxTest):
    def setUp(self):
        super(ArxMagicTest, self).setUp()
        self.alignment = Alignment.objects.create(
            name="Test", adjective="spectacular", alter_caster=False
        )
        # travis keeps a copy of the Primal alignment created from migrations. Why? Because fuck you, that's why
        self.primal, _ = Alignment.objects.get_or_create(name="Primal")
        self.affinity = Affinity.objects.create(name="Light")
        self.recipe = CraftingRecipe.objects.create(
            name="alaricite tester", desc="A test recipe."
        )
        self.test_object = create.create_object(
            typeclass="typeclasses.objects.Object", key="Test Object", nohome=True
        )
        self.test_object.item_data.recipe = self.recipe.id
        self.test_object.db.alignment = self.alignment.id
        self.test_object.db.affinity = self.affinity.id
        self.test_object.item_data.quality_level = 10
        self.test_object.db.quantity = 1

        self.practitioner = Practitioner.objects.create(
            character=self.char2,
            potential=100,
            anima=100,
            sigil_desc="a test pattern atop static",
        )
        self.practitioner.notify_magic = override_notify_magic
        self.practitioner.check_perceive_magic = override_check_perceive_magic
        self.practitioner.roll_magic = override_roll_magic

        self.char2.msg = override_msg
        Trait.objects.get_or_create(
            name="mana", trait_type=Trait.STAT, category=Trait.MAGIC
        )
        self.char2.traits.set_stat_value("mana", 5)
        Trait.objects.get_or_create(
            name="intellect", trait_type=Trait.STAT, category=Trait.MENTAL
        )
        self.char2.traits.set_stat_value("intellect", 5)
        Trait.objects.get_or_create(
            name="occult", trait_type=Trait.SKILL, category=Trait.GENERAL
        )
        self.char2.traits.skills = {"occult": 5}
        self.node = SkillNode.objects.create(name="Test Node")
        self.effect = Effect.objects.create(
            name="Test Effect",
            target_type=Effect.TARGET_TYPE_EITHER,
            coded_effect=Effect.CODED_SIGHT,
        )
        self.spell = Spell.objects.create(
            name="Test Spell",
            node=self.node,
            base_difficulty=10,
            base_cost=10,
            auto_discover=True,
            required_resonance=10,
        )
        self.spell_effect = SpellEffect.objects.create(
            spell=self.spell, effect=self.effect, primary=True
        )

    def tearDown(self):
        self.test_object.delete()
        self.recipe.delete()
        self.spell.delete()
        self.effect.delete()
        self.node.delete()
        self.practitioner.delete()
        self.alignment.delete()
        self.affinity.delete()
        super(ArxMagicTest, self).tearDown()
