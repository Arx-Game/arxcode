from world.magic.models import *
from .conditional_parser import ConditionalHandler
from world.dominion.models import CraftingRecipe
from world.weather.models import WeatherType, WeatherEmit
from evennia.server.models import ServerConfig
from .test_utils import ArxMagicTest, pending_magic_text
from server.utils.test_utils import ArxTest
from mock import patch, Mock, PropertyMock


class TestMagicConditions(ArxTest):
    def setUp(self):
        super(TestMagicConditions, self).setUp()
        self.weather1 = WeatherType.objects.create(
            name="MagicTest1", gm_notes="Test weather"
        )
        self.emit1 = WeatherEmit.objects.create(
            weather=self.weather1, text="MagicTest1 weather happens."
        )
        self.weather2 = WeatherType.objects.create(
            name="MagicTest2", gm_notes="Test weather"
        )
        self.emit2 = WeatherEmit.objects.create(
            weather=self.weather2, text="MagicTest2 weather happens."
        )
        ServerConfig.objects.conf("weather_type_current", value=self.weather1.id)

    def test_weather_condition(self):
        handler = ConditionalHandler(
            "require:weather(MagicTest1);prohibit:weather(MagicTest2)"
        )
        self.assertTrue(handler.check(None, None, "require", default=True))
        self.assertFalse(handler.check(None, None, "prohibit", default=False))
        handler = ConditionalHandler(
            "require:weather(MagicTest2);prohibit:weather(MagicTest1)"
        )
        self.assertFalse(handler.check(None, None, "require", default=True))
        self.assertTrue(handler.check(None, None, "prohibit", default=False))


class TestMagicSystem(ArxMagicTest):
    def test_object_mixins(self):
        self.assertEqual(self.test_object.alignment, self.alignment)
        self.assertEqual(self.test_object.affinity, self.affinity)
        self.assertEqual(self.test_object.potential, 200)
        self.assertEqual(self.test_object.primum, 200)
        self.assertEqual(self.test_object.magic_description, "A spectacular glow.")
        self.test_object.drain_primum(190)
        self.assertEqual(self.test_object.primum, 10)
        self.assertEqual(
            self.test_object.magic_description,
            "Once a spectacular glow, now only a spark.",
        )
        self.test_object.db.magic_desc_short = "this object was used for testing"
        self.assertEqual(
            self.test_object.magic_description,
            "Once a spectacular glow, now only a spark, this "
            "object was used for testing.",
        )
        self.test_object.db.magic_desc_override = "This is a glowing test object!"
        self.assertEqual(
            self.test_object.magic_description, "This is a glowing test object!"
        )

    def test_working(self):
        self.assertEqual(self.practitioner.anima, 100)
        self.assertFalse(self.practitioner.knows_node(self.node))
        self.assertFalse(self.practitioner.knows_spell(self.spell))
        self.practitioner.open_node(
            self.node,
            SkillNodeResonance.LEARN_FIAT,
            explanation="Learned by test fiat.",
        )
        self.assertTrue(self.practitioner.knows_node(self.node))
        self.assertEqual(self.practitioner.resonance_for_node(self.node), 0)
        self.practitioner.add_resonance_to_node(self.node, 10)
        self.assertEqual(self.practitioner.resonance_for_node(self.node), 10)
        self.assertTrue(self.practitioner.knows_spell(self.spell))
        self.test_object.location = self.practitioner.character.location
        working = Working.objects.create(
            lead=self.practitioner,
            spell=self.spell,
            target_string=self.test_object.name,
        )
        working.add_practitioner(self.practitioner, accepted=True)
        with patch(
            "world.magic.models.Working.successes",
            new_callable=PropertyMock(return_value=10),
        ) as fake_successes:
            self.assertEqual(working.validation_error(), None)
            from evennia.utils.ansi import strip_ansi

            with patch("typeclasses.scripts.combat.attacks.Attack"):
                working.perform(unsafe=False)
                working.finalize()
            self.assertEqual(
                strip_ansi(working.description_string()),
                " ID:                 1                                                        \n"
                " Participants:       Char2                                                    \n"
                " Lead:               Char2                                                    \n"
                " Alignment:          Primal                                                   \n"
                " Type:               Casting                                                  \n"
                " Spell:              Test Spell                                               \n"
                " Calculated:         yes                                                      \n"
                " Performed:          yes                                                      \n"
                " Available Primum:   100                                                      \n"
                " Cost:               8                                                        \n"
                " Danger Level:       relatively safe                                          \n"
                " Successes:          10                                                       \n"
                " Result:             Participants perceive: A spectacular glow.               ",
            )
        self.assertEqual(
            pending_magic_text(),
            "Char2 chants in Arvani and gestures expansively and energetically!\n"
            "As Char2 works magic, the effect spreading out from them resembles a test "
            "pattern atop static.\n"
            "Gazing at Test Object, you perceive: A spectacular glow.",
        )
        self.assertEqual(self.practitioner.anima, 92)
