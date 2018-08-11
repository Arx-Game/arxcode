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
        self.call_cmd("/targetmod char2=10,abyssal,any combat",
                      "You have added a modifier to Char2: "
                      "Modifier on Char2 of +10 against abyssal for Any Combat checks.")
        self.call_cmd("char2", "Modifiers on Char2: Modifier on Char2 of +10 against abyssal for Any Combat checks")
        self.call_cmd("/usermod here=10,divine,defense",
                      "You have added a modifier to Room: Modifier on Room of +10 for divine for Defense checks.")
        self.call_cmd("/search asdf", "Modifiers for/against asdf: ")
        self.call_cmd("/search divine", "Modifiers for/against divine: "
                                        "Modifier on Room of +10 for divine for Defense checks")


class TestTriggers(ArxTest):
    def setUp(self):
        super(TestTriggers, self).setUp()
        self.trigger1 = EffectTrigger.objects.create(object=self.room2, priority=2, room_msg="trigger1 fire")
        self.trigger2 = EffectTrigger.objects.create(object=self.room2, priority=1, room_msg="trigger2 fire")
        self.trigger3 = EffectTrigger.objects.create(object=self.room2, priority=1, room_msg="trigger3 fire")
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
