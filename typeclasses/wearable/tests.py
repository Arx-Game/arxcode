# -*- coding: utf-8 -*-
"""
Tests for wearables
"""
from __future__ import unicode_literals
from server.utils.test_utils import ArxCommandTest, TestEquipmentMixins
from typeclasses.wearable.cmdset_wearable import CmdWear
from typeclasses.wearable.cmdset_wieldable import CmdWield
from mock import Mock


class EquipmentCommandTests(TestEquipmentMixins, ArxCommandTest):

    def test_wield_cmd(self):
        self.room1.msg_contents = Mock()
        self.setup_cmd(CmdWield, self.char2)
        self.call_cmd("", "What are you trying to wield?")
        fight = self.start_ze_fight()
        fight.ndb.phase = 2
        self.assertEqual(self.char2.combat.attack_skill, "brawl")
        self.call_cmd("lickyknife1", "Equipment changes are only allowed in combat's setup phase.")
        fight.ndb.phase = 1
        self.call_cmd("lickyknife1", "You brandish Lickyknife1.")
        self.room1.msg_contents.assert_called_with("Char2 wields Lickyknife1.", exclude=[self.char2])
        self.assertTrue(self.knife1.is_wielded)
        self.assertEqual(self.char2.combat.attack_skill, "small wpn")
        self.call_cmd("lickyknife1", "Could not brandish Lickyknife1 (already wielded).")
        self.hairpins1.wear(self.char2)
        self.call_cmd("hairpins1", "Could not brandish Hairpins1 (other weapon in use).")
        # Tests to "sheathe" a wielded weapon:
        self.call_cmd("lickyknife1", "You sheathe Lickyknife1.", cmdstring="sheathe")
        self.assertTrue(self.knife1.is_worn)
        self.assertTrue(self.hairpins1.is_worn)
        # Tests to "wield" a worn weapon:
        self.call_cmd("hairpins1", "You brandish Hairpins1.")
        self.room1.msg_contents.assert_called_with("Char2 wields Hairpins1.", exclude=[self.char2])
        self.assertTrue(self.hairpins1.is_wielded)
        self.assertFalse(self.hairpins1.is_worn)

    def test_wear_cmd(self):
        self.setup_cmd(CmdWear, self.char2)
        self.char2.additional_desc = "Also Sly is super hot."
        self.top_no_crafter.db.recipe = 1
        self.top_no_crafter.db.crafted_by = self.char1
        self.call_cmd("", "What are you trying to wear?")
        self.obj1.location = self.char2
        self.call_cmd("obj", "Could not put on Obj (wrong item type).")
        self.call_cmd("top1", "You don't carry 'top1'.")
        self.top_no_crafter.location = self.char2
        self.call_cmd("top1", "You put on Top1.")
        self.call_cmd("top2", "Could not put on Top2 (chest slot full).")
        self.call_cmd("slinkity1", "You put on Slinkity1.")
        self.assertTrue(self.top_no_crafter.is_worn)
        self.assertTrue(self.catsuit1.is_worn)
        self.call_cmd("a fox mask", "Could not put on A Fox Mask (needs repair).")
        self.mask1.db.quality_level = 8
        self.call_cmd("a fox mask", "You currently have a +tempdesc set, which you may want to remove "
                                    "with +tempdesc.|You put on A Fox Mask.")
        self.assertEqual(self.mask1.db.quality_level, 7)
        self.assertEqual(self.char2.fakename, "Someone wearing A Fox Mask")
        self.assertEqual(self.char2.temp_desc, "A very Slyyyy Fox...")
        self.mask1.tags.add("mirrormask")  # final test re-checks quality level
        del self.char2.additional_desc
        # test 'wear' on a wielded item:
        self.hairpins1.wield(self.char2)
        self.assertTrue(self.hairpins1.is_wielded)
        self.assertFalse(self.hairpins1.is_worn)
        self.call_cmd("hairpins1", "You put on Hairpins1.")
        self.assertFalse(self.hairpins1.is_wielded)
        self.assertTrue(self.hairpins1.is_worn)
        self.call_cmd("sword1", "You put on Sword1.")
        self.knife1.wield(self.char2)
        self.assertTrue(self.knife1.is_wielded)
        # wielded lickyknife1, sheathed sword1; top1, slinkity1, fox mask, hairpins1
        outfit1 = self.create_ze_outfit("Very Friendly Shadows")
        # Tests for cmd "remove":
        self.call_cmd("a fox mask", "A Fox Mask is no longer altering your identity or description.|"
                                    "You remove A Fox Mask.", cmdstring="remove")
        self.assertFalse(self.mask1.is_worn)
        self.assertEqual(self.char2.fakename, None)
        self.call_cmd("lickyknife1", "You remove Lickyknife1.", cmdstring="remove")
        self.assertFalse(self.knife1.is_wielded)
        self.assertEqual(self.char2.combat.attack_skill, "brawl")
        self.call_cmd("lickyknife1", "Could not remove Lickyknife1 (not equipped).", cmdstring="remove")
        outfit2 = self.create_ze_outfit("Friendly Shadows")  # top1, slinkity1, hairpins1; sheathed sword1
        self.call_cmd("Sword1", "You remove Sword1.", cmdstring="remove")
        self.assertFalse(self.sword1.is_worn)
        # Tests for "undress":
        self.knife1.wield(self.char2)
        self.assertTrue(self.knife1.is_wielded)
        self.sword1.wear(self.char2)
        self.assertTrue(self.sword1.is_worn)
        self.char2.undress()
        self.assertTrue(self.char2.is_naked)  # Using this to test 'undress' because item order is unpredictable
        self.call_cmd("", "You have nothing to remove.", cmdstring="undress")
        # Tests for cmd "wear all":
        self.caller = self.char1
        self.call_cmd("all", "You have nothing to wear.")
        self.caller = self.char2
        self.call_cmd("all", "Could not put on Top2 (chest slot full).\nYou put on A Fox Mask, Lickyknife1, "
                             "Sword1, Top1, Hairpins1, Purse1, and Slinkity1.")
        # Tests for "wear/outfit":
        # All but 1 item unequipped for test because self.contents is an unordered dict which can't be
        # predicted during the 'undress' step.
        self.char2.undress()
        self.catsuit1.wear(self.char2)
        self.call_cmd("/outfit", "What are you trying to wear?")
        self.call_cmd("/outfit unfriendly", "'unfriendly' not found in your collection of outfits.")
        self.call_cmd("/outfit friendly", "'friendly' refers to more than one outfit; please be more specific.")
        self.hairpins1.location = self.purse1
        self.call_cmd("/outfit friendly shadows", "Outfit components must be on your person and not in "
                                                  "any containers.")
        self.hairpins1.location = self.char2
        self.call_cmd("/outfit very friendly shadows", "You remove Slinkity1.|You brandish Lickyknife1.|You "
                                                       "put on Top1, Slinkity1, A Fox Mask, Hairpins1, and "
                                                       "Sword1.|Your outfit 'Very Friendly Shadows' is "
                                                       "successfully equipped.")
        self.assertTrue(outfit1.is_equipped)
        self.char2.undress()
        self.mask1.wear(self.char2)
        self.catsuit1.db.recipe = 1  # creates a slot_limit conflict
        self.call_cmd("/outfit friendly shadows", "A Fox Mask is no longer altering your identity or description.|"
                                                  "You remove A Fox Mask.|Could not put on Slinkity1 (chest slot "
                                                  "full).\nYou put on Top1, Hairpins1, and Sword1.\nYour outfit "
                                                  "'Friendly Shadows' is not equipped.")
        self.assertFalse(outfit2.is_equipped)
        # Tests for "remove/outfit":
        self.call_cmd("/outfit friendly shadows", "Could not remove Slinkity1 (not equipped).\nYou remove Sword1, "
                                                  "Top1, and Hairpins1.", cmdstring="remove")
        self.catsuit1.db.recipe = 2
        self.catsuit1.wear(self.char2)
        self.mask1.wear(self.char2)
        # the /outfit switch halts at combaterror but continues for equiperrors, so we'll combat test here too.
        fight = self.start_ze_fight()
        fight.ndb.phase = 2
        self.call_cmd("/outfit friendly shadows", "Equipment changes are only allowed in combat's setup phase.",
                      cmdstring="remove")
        fight.ndb.phase = 1
        self.call_cmd("/outfit friendly shadows", "Could not remove Sword1 (not equipped), Top1 (not equipped), "
                                                  "or Hairpins1 (not equipped).\nYou remove Slinkity1.",
                      cmdstring="remove")
        self.assertTrue(self.mask1.is_worn)
        self.assertEqual(self.mask1.db.quality_level, 7)
