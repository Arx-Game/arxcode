"""
Tests for Conditions app
"""
# -*- coding: utf-8 -*-
from mock import Mock

from server.utils.test_utils import ArxCommandTest, ArxTest
from . import condition_commands
from world.conditions.models import EffectTrigger


class ConditionsCommandsTests(ArxCommandTest):
    def test_modifiers_cmd(self):
        self.setup_cmd(condition_commands.CmdModifiers, self.char1)
        self.call_cmd("char2", "Modifiers on Char2: ")
        self.call_cmd(
            "/targetmod char2=10,abyssal,any combat",
            "You have added a modifier to Char2: "
            "Modifier on Char2 of +10 against abyssal for Any Combat checks.",
        )
        self.call_cmd(
            "char2",
            "Modifiers on Char2: Modifier on Char2 of +10 against abyssal for Any Combat checks",
        )
        self.call_cmd(
            "/usermod here=10,divine,defense",
            "You have added a modifier to Room: Modifier on Room of +10 for divine for Defense checks.",
        )
        self.call_cmd("/search asdf", "Modifiers for/against asdf: ")
        self.call_cmd(
            "/search divine",
            "Modifiers for/against divine: "
            "Modifier on Room of +10 for divine for Defense checks",
        )

    def test_knacks_cmd(self):
        self.setup_cmd(condition_commands.CmdKnacks, self.char1)
        self.call_cmd("", "Knacks for Char:")
        self.call_cmd("asdf", "No knack found by that name.")
        self.call_cmd("/create asdjfh", "You must provide a description.")
        self.call_cmd("/create asf=asdf", "You must provide a stat and skill.")
        self.call_cmd("/create a,b=asdf", "You must provide a name.")
        self.call_cmd("/create a,b,c=asdf", "a is not a valid stat.")
        self.call_cmd("/create strength,b,c=asdf", "b is not a valid skill.")
        self.call_cmd(
            "/create strength,brawl,hit ppl gud=real gud",
            "You tried to spend 150 xp, but only have 0 available.",
        )
        self.char1.adjust_xp(150)
        self.assertEqual(
            self.char1.mods.get_total_roll_modifiers(["charm"], ["seduction"]), 0
        )
        self.call_cmd(
            "/create charm,seduction,smirkity vixen=So slyyyyyy",
            "You spend 150 xp and have 0 remaining.|"
            "You create a knack called 'smirkity vixen' for charm+seduction.",
        )
        self.assertEqual(
            self.char1.mods.get_total_roll_modifiers(["charm"], ["seduction"]), 1
        )
        self.assertEqual(
            self.char1.mods.get_crit_modifiers(["charm"], ["seduction"]), 1
        )
        self.call_cmd(
            "",
            "Knacks for Char:\n\n"
            "Name: smirkity vixen\n"
            "Stat: charm Skill: seduction Value: 1\n"
            "Description: So slyyyyyy",
        )
        self.call_cmd(
            "smirkity vixen",
            "Name: smirkity vixen\n"
            "Stat: charm Skill: seduction Value: 1\n"
            "Description: So slyyyyyy",
        )
        self.call_cmd("/train asdf", "No knack found by that name.")
        self.call_cmd(
            "/train smirkity vixen",
            "You tried to spend 60 xp, but only have 0 available.",
        )
        self.char1.adjust_xp(60)
        self.call_cmd(
            "/train smirkity vixen",
            "You spend 60 xp and have 0 remaining.|"
            "You have increased smirkity vixen to rank 2.",
        )
        self.assertEqual(
            self.char1.mods.get_total_roll_modifiers(["charm"], ["seduction"]), 2
        )
        self.assertEqual(
            self.char1.mods.get_crit_modifiers(["charm"], ["seduction"]), 2
        )
        self.call_cmd(
            "/create charm,seduction,more smirkity=So smirk",
            "You already have a knack for that skill and stat combination.",
        )


class TestTriggers(ArxTest):
    def setUp(self):
        super(TestTriggers, self).setUp()
        self.trigger1 = EffectTrigger.objects.create(
            object=self.room2, priority=2, room_msg="trigger1 fire"
        )
        self.trigger2 = EffectTrigger.objects.create(
            object=self.room2, priority=1, room_msg="trigger2 fire"
        )
        self.trigger3 = EffectTrigger.objects.create(
            object=self.room2, priority=1, room_msg="trigger3 fire"
        )
        self.mock_triggers()

    def mock_triggers(self):
        self.trigger1.do_trigger_results = Mock(return_value=True)
        self.trigger2.do_trigger_results = Mock(return_value=True)
        self.trigger3.do_trigger_results = Mock(return_value=True)

    def test_social_rank(self):
        self.char1.db.social_rank = 3
        self.trigger1.conditional_check = EffectTrigger.SOCIAL_RANK
        self.trigger1.min_value = 2
        self.trigger1.max_value = 3
        self.trigger1.save()
        self.trigger2.conditional_check = EffectTrigger.SOCIAL_RANK
        self.trigger2.min_value = 2
        self.trigger2.max_value = 3
        self.trigger2.save()
        self.char1.move_to(self.room2)
        self.trigger1.do_trigger_results.assert_called_once()
        self.trigger2.do_trigger_results.assert_not_called()
        self.trigger1.min_value = 4
        self.trigger1.save()
        self.trigger3.conditional_check = EffectTrigger.SOCIAL_RANK
        self.trigger3.min_value = 2
        self.trigger3.max_value = 3
        self.trigger3.save()
        self.mock_triggers()
        self.char1.move_to(self.room2)
        self.trigger1.do_trigger_results.assert_not_called()
        self.trigger2.do_trigger_results.assert_called_once()
        self.trigger3.do_trigger_results.assert_called_once()
