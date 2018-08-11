# -*- coding: utf-8 -*-
"""
Tests for fashion app
"""
from __future__ import unicode_literals
from server.utils.test_utils import ArxCommandTest
from typeclasses.wearable.wearable import Wearable
from world.dominion.models import Organization, AssetOwner, CraftingRecipe, CraftingMaterialType
from . import fashion_commands
from mock import patch, Mock


class FashionCommandTests(ArxCommandTest):
    wearable_typeclass = Wearable

    def setUp(self):
        super(FashionCommandTests, self).setUp()
        self.org = Organization.objects.create(name="Orgtest")
        AssetOwner.objects.create(organization_owner=self.org)
        self.org.members.create(player=self.dompc)
        self.mat1 = CraftingMaterialType.objects.create(name="Mat1", value=100)
        self.recipe = CraftingRecipe.objects.create(name="Recipe1", primary_amount=5, level=6,
                                                    result="slot:chest;slot_limit:1;baseval:1;penalty:2")
        self.recipe.primary_materials.add(self.mat1)
        from evennia.utils import create
        self.obj3 = create.create_object(self.wearable_typeclass, key="Obj3", location=self.char1, home=self.room1)
        self.obj3.db.quality_level = 6

    @patch('world.dominion.models.get_week')
    @patch('world.stats_and_skills.do_dice_check')
    def test_model_cmd(self, mock_dice_check, mock_get_week):
        mock_get_week.return_value = 1
        self.setup_cmd(fashion_commands.CmdFashionModel, self.char1)
        self.call_cmd("catsuit", 'Command incorrect. Please specify <item>=<organization>')
        self.call_cmd("catsuit=Shadow Striders",
                      "Could not find 'catsuit'.|Could not find public org 'Shadow Striders'.")
        self.obj1.location = self.char1
        self.call_cmd("Obj=Orgtest", "Obj is not an item you can model for fashion.")
        self.call_cmd("Obj3=Orgtest", 'Obj3 was wrought by no mortal hand, and from it no mortal fame can be earned.')
        self.obj3.db.recipe = 1
        self.obj3.db.crafted_by = self.char1
        self.call_cmd("Obj3=Orgtest", 'Obj3 was wrought by no mortal hand, and from it no mortal fame can be earned.')
        self.obj3.db.crafted_by = self.char2
        self.call_cmd("Obj3=Orgtest", "Please wear Obj3 before trying to model it as fashion.")
        self.obj3.db.currently_worn = True
        self.roster_entry.action_points = 0
        self.call_cmd("Obj3=Orgtest", "You cannot afford the %s AP cost to model." % self.obj3.fashion_ap_cost)
        self.roster_entry.action_points = 100
        mock_dice_check.return_value = 100
        self.org.assets.inform_owner = Mock()
        self.account2.assets.inform_owner = Mock()
        # TODO: add adornments to test increase of value
        self.obj3.db.adorns = {}
        self.call_cmd("Obj3=Orgtest", 'You spend time modeling Obj3 around Arx on behalf of Orgtest and earn 1000 fame.'
                                      ' Your prestige is now 1015.')
        self.assertEqual(self.roster_entry.action_points, 100 - self.obj3.fashion_ap_cost)
        self.org.assets.inform_owner.assert_called_with("{315500{n fame awarded from Testaccount modeling Obj3.",
                                                        append=True, category='fashion')
        self.account2.assets.inform_owner.assert_called_with("{315250{n fame awarded from Testaccount modeling Obj3.",
                                                             append=True, category='fashion')
        # TODO: Other tests
        #   change recipe result with fashion_mult
        #   test the leaderboards

    def test_refund_cmd(self):
        from world.fashion.models import FashionSnapshot
        self.setup_cmd(fashion_commands.CmdAdminFashion, self.char1)
        snapshot = FashionSnapshot.objects.create(fashion_model=self.dompc2, designer=self.dompc2, fame=50000,
                                                  org=self.org, fashion_item=self.obj3)
        snapshot.apply_fame()
        self.assertEqual(self.dompc2.assets.fame, 62500)
        self.call_cmd("/delete 1", 'Snapshot #1 fame/ap has been reversed. Deleting it.')
        self.assertEqual(self.dompc2.assets.fame, 0)
