# -*- coding: utf-8 -*-
"""
Tests for fashion app
"""
from __future__ import unicode_literals
from server.utils.test_utils import ArxCommandTest, TestEquipmentMixins
from world.fashion import fashion_commands
from mock import patch, Mock


class FashionCommandTests(TestEquipmentMixins, ArxCommandTest):
    @patch("world.dominion.models.get_week")
    @patch("world.stats_and_skills.do_dice_check")
    def test_outfit_cmd(self, mock_dice_check, mock_get_week):
        mock_get_week.return_value = 1
        fake_dt = self.fake_datetime
        self.mask1.db.quality_level = 11
        to_be_worn = [
            self.top2,
            self.catsuit1,
            self.purse1,
            self.sword1,
            self.hairpins1,
            self.mask1,
        ]
        self.setup_cmd(fashion_commands.CmdFashionOutfit, self.char2)
        self.call_cmd(
            "",
            "No outfits to display! Try creating one, or 'outfits/archives' instead.",
        )
        self.call_cmd(
            "Friendly Shadows",
            "'Friendly Shadows' not found in your collection of outfits.",
        )
        self.call_cmd("/create", "Cannot create your shiny new outfit without a name.")
        self.call_cmd(
            "/create Friendly Shadows",
            "Emperor Testaccount2's New Clothes? Put something on " "and try again.",
        )
        self.knife1.wield(self.char2)
        for item in to_be_worn:
            item.wear(self.char2)
        to_be_removed = to_be_worn[1:] + [self.knife1]
        with patch("django.utils.timezone.now", Mock(return_value=fake_dt)):
            self.call_cmd(
                "/create Friendly Shadows",
                "Created [Friendly Shadows] weapons: Lickyknife1 and Sword1\n"
                "attire: Top2, Slinkity1, Purse1, Hairpins1, and A Fox Mask",
            )
            for item in to_be_removed:
                item.remove(self.char2)
            self.call_cmd(
                "/create Unfriendly Shadows",
                "Created [Unfriendly Shadows]\nattire: Top2",
            )
        outfit1 = fashion_commands.get_caller_outfit_from_args(
            self.caller, "Friendly Shadows"
        )
        outfit2 = fashion_commands.get_caller_outfit_from_args(
            self.caller, "Unfriendly Shadows"
        )
        self.call_cmd(
            "/create Friendly Shadows",
            "You own an outfit named 'Friendly Shadows' already.",
        )
        self.call_cmd(
            "",
            "Created    Outfit             Appraisal/Buzz \n"
            "1978/08/27 Friendly Shadows   27,290         "
            "1978/08/27 Unfriendly Shadows 500",
        )
        self.call_cmd(
            "/archive", "No archived outfits to display! Try regular 'outfits' instead."
        )
        self.call_cmd(
            "/archive friendly Shadows",
            "Friendly Shadows is added to your outfit archives.",
        )
        self.assertTrue(outfit1.archived)
        self.call_cmd(
            "",
            "Created    Outfit             Appraisal/Buzz \n"
            "1978/08/27 Unfriendly Shadows 500",
        )
        self.call_cmd(
            "/archive friendly shadows",
            "Friendly Shadows is restored from your outfit archives.",
        )
        self.assertFalse(outfit1.archived)
        # Modeling outfit2 means outfit1's appraisal goes down, since they have one item overlapping.
        self.roster_entry2.action_points = 200
        with patch("django.utils.timezone.now", Mock(return_value=fake_dt)):
            mock_dice_check.return_value = 0
            outfit2.model_outfit_for_fashion(self.org)
        self.assertTrue(self.top2.modeled_by)
        self.call_cmd(
            "",
            "Created    Outfit             Appraisal/Buzz \n"
            "1978/08/27 Friendly Shadows   26,790         "
            "1978/08/27 Unfriendly Shadows little",
        )
        self.call_cmd(
            "Unfriendly shadows",
            "Unfriendly Shadows Slot  Location \n"
            "Top2               chest Char2    "
            "\nModeled by Testaccount2 for Orgtest, generating little buzz on "
            "1978/08/27.",
        )
        self.call_cmd("/delete", "Requires an outfit's name.")
        top2_snapshot = self.top2.fashion_snapshots.first()
        self.assertEqual(self.top2.ndb.snapshots_cache, [top2_snapshot])
        self.call_cmd("/delete Friendly shadows", "Deleting Friendly Shadows.")  # :'(
        self.assertEqual(self.top2.ndb.snapshots_cache, None)
        outfit2.owner_character.msg = Mock()
        self.top2.softdelete()
        outfit2.owner_character.msg.assert_called_with(
            "Nothing remains of the outfit formerly known as " "'Unfriendly Shadows'."
        )
        self.assertFalse(self.char2.dompc.fashion_outfits.all().exists())

    @patch("world.dominion.models.get_week")
    @patch("world.stats_and_skills.do_dice_check")
    def test_model_cmd(self, mock_dice_check, mock_get_week):
        mock_get_week.return_value = 1
        fake_dt = self.fake_datetime
        self.obj1.location, self.top1.location = self.char1, self.char1
        self.mask1.db.quality_level = 11
        ap_cost = self.top1.fashion_ap_cost
        self.setup_cmd(fashion_commands.CmdFashionModel, self.char1)
        self.call_cmd("catsuit", "Please specify <item>=<organization>")
        self.call_cmd(
            "catsuit=Shadow Striders",
            "Could not find 'catsuit'.|Could not find public org 'Shadow Striders'.",
        )
        self.call_cmd("Obj=Orgtest", "Obj is not an item you can model for fashion.")
        self.call_cmd(
            "Top1=Orgtest",
            "Top1 was wrought by no mortal hand, and from it no mortal fame can be "
            "earned.",
        )
        self.top1.db.recipe = 1
        self.top1.db.crafted_by = self.char1
        self.call_cmd(
            "Top1=Orgtest",
            "Top1 was wrought by no mortal hand, and from it no mortal fame can be "
            "earned.",
        )
        self.top1.db.crafted_by = self.char2
        self.call_cmd(
            "Top1=Orgtest", "Please wear Top1 before trying to model it as fashion."
        )
        self.top1.wear(self.char1)
        self.roster_entry.action_points = 0
        self.call_cmd(
            "Top1=Orgtest",
            "It costs %s AP to model Top1; you do not have enough energy." % ap_cost,
        )
        self.roster_entry.action_points = 100
        mock_dice_check.return_value = 100
        self.org.assets.inform_owner = Mock()
        self.account2.assets.inform_owner = Mock()  # the designer's assetowner
        with patch("django.utils.timezone.now", Mock(return_value=fake_dt)):
            self.call_cmd(
                "Top1=Orgtest",
                "[Fashion] When Testaccount models 'Top1' on behalf of Orgtest, it gains "
                "modest attention from admiring onlookers.|For modeling Top1 you earn "
                "1,000 fame. Your prestige is now 1,005.",
            )
        self.assertEqual(self.roster_entry.action_points, 100 - ap_cost)
        self.org.assets.inform_owner.assert_called_with(
            "{315500{n fame awarded from Testaccount modeling Top1.",
            append=True,
            category="fashion",
        )
        self.account2.assets.inform_owner.assert_called_with(
            "{315250{n fame awarded from Testaccount modeling " "Top1.",
            append=True,
            category="fashion",
        )
        self.assertEqual(
            self.top1.modeled_by,
            "Modeled by {315Testaccount{n for {125Orgtest{n, generating "
            "{355modest{n buzz on 1978/08/27.",
        )
        # test "model/outfit":
        self.top1.remove(self.char1)
        self.top1.location = self.char2
        self.roster_entry2.action_points = 0
        self.caller = self.char2
        to_be_worn = [
            self.top1,
            self.catsuit1,
            self.purse1,
            self.sword1,
            self.hairpins1,
            self.mask1,
        ]
        self.knife1.wield(self.char2)
        for item in to_be_worn:
            item.wear(self.char2)
        outfit1 = self.create_ze_outfit("Friendly Shadows")
        self.mask1.remove(self.char2)
        self.assertFalse(outfit1.is_equipped)
        self.call_cmd(
            "/outfit Friendly Shadows=Orgtest",
            "Outfit must be equipped before trying to model it.",
        )
        self.mask1.wear(self.char2)
        self.assertTrue(outfit1.is_equipped)
        self.call_cmd(
            "/outfit Friendly Shadows=Orgtest",
            "Pieces of this outfit cannot be modeled:\n"
            "- Top1 has already been used to model fashion.\n"
            "Repeat command to model the 6 remaining item(s).",
        )
        self.call_cmd(
            "/outfit Friendly Shadows=Orgtest",
            "It costs %d AP to model Friendly Shadows; you do not "
            "have enough energy." % (ap_cost * 6),
        )
        self.roster_entry2.action_points = 200
        outfit1.owner.player.ndb.outfit_model_prompt = str(outfit1)
        with patch("django.utils.timezone.now", Mock(return_value=fake_dt)):
            self.call_cmd(
                "/outfit Friendly Shadows=Orgtest",
                "[Fashion] With talented modeling, Testaccount2 displays "
                "'Friendly Shadows' around Arx, garnering flattering "
                "conversation and murmurs throughout the city about the "
                "fine choices made by Orgtest for sponsoring someone "
                "with such exceptional taste.|For modeling Friendly "
                "Shadows you earn 72,016 fame. Your prestige is now "
                "90,269.",
            )

        self.assertEqual(self.roster_entry2.action_points, 200 - (ap_cost * 6))
        self.assertTrue(outfit1.modeled)
        self.assertTrue(self.hairpins1.modeled_by)
        self.assertEqual(self.hairpins1.fashion_snapshots.first().outfit, outfit1)
        # this tests if hairpins carries the "buzz message" from the entire outfit:
        self.assertEqual(
            self.hairpins1.modeled_by,
            "Modeled by {315Testaccount2{n for {125Orgtest{n, generating "
            "{542exceptional{n buzz on 1978/08/27!",
        )
        self.assertEqual(
            outfit1.model_info,
            "Modeled by {315Testaccount2{n for {125Orgtest{n, generating "
            "{542exceptional{n buzz on 1978/08/27!",
        )
        self.call_cmd(
            "/outfit Friendly Shadows=Orgtest",
            "Friendly Shadows has already been modeled.",
        )
        for item in to_be_worn:
            item.remove(self.char2)
        outfit2 = self.create_ze_outfit("Friendliest")  # only knife1 remains wielded
        self.call_cmd(
            "/outfit Friendliest=Orgtest",
            "Pieces of this outfit cannot be modeled:\n"
            "- Lickyknife1 has already been used to model fashion.\n"
            "No valid items remain! Try modeling a different outfit.",
        )
        self.assertFalse(outfit2.modeled)
        with patch.object(fashion_commands, "datetime") as mock_datetime:
            from evennia.server.models import ServerConfig

            ServerConfig.objects.conf("MAX_FASHION_PER_WEEK", value=3)
            from datetime import timedelta

            mock_datetime.now = Mock(return_value=fake_dt)
            self.call_cmd(
                "/outfit Friendliest=Orgtest",
                "You may only model up to 3 items a week before the public tires of you.",
            )
            mock_datetime.now = Mock(return_value=fake_dt + timedelta(days=8))
            self.call_cmd(
                "/outfit Friendliest=Orgtest",
                "Pieces of this outfit cannot be modeled:\n- Lickyknife1 has already been used to model "
                "fashion.\nNo valid items remain! Try modeling a different outfit.",
            )
        # test leaderboards:

        self.call_cmd(
            "",
            "Fashion Model   Fame Items Avg Item Fame \n"
            " TestAccount2 72,016     6        12,002"
            "   TestAccount  1,000     1         1,000",
        )
        self.call_cmd(
            "/designer",
            "Designer   Fame Items Avg Item Fame \n"
            "TestAccount2 18,253     7         2,607",
        )
        self.call_cmd(
            "/designer Testaccount2",
            "Testaccount2 Model   Fame Items Avg Item Fame \n"
            "      TestAccount2 18,003     6         3,000"
            "        TestAccount    250     1           250",
        )
        self.call_cmd(
            "/orgs",
            "Organization   Fame Items Avg Item Fame \n"
            "     Orgtest 36,508     7         5,215",
        )
        self.call_cmd(
            "/org Orgtest",
            "Orgtest Model   Fame Items Avg Item Fame \n"
            " TestAccount2 36,008     6         6,001"
            "   TestAccount    500     1           500",
        )

    def test_refund_cmd(self):
        from world.fashion.models import FashionSnapshot

        self.setup_cmd(fashion_commands.CmdAdminFashion, self.char1)
        snapshot = FashionSnapshot.objects.create(
            fashion_model=self.dompc2,
            designer=self.dompc2,
            fame=50000,
            org=self.org,
            fashion_item=self.top1,
        )
        snapshot.apply_fame()
        self.assertEqual(self.dompc2.assets.fame, 62500)
        self.call_cmd(
            "/delete 1", "Snapshot #1 fame/ap has been reversed. Deleting it."
        )
        self.assertEqual(self.dompc2.assets.fame, 0)
