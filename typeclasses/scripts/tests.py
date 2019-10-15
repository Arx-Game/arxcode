"""
Tests for scripts.
"""
from evennia import create_script
from server.utils.test_utils import ArxCommandTest
from world.dominion.models import AccountTransaction, LIFESTYLES
from typeclasses.scripts.weekly_events import WeeklyEvents


class TestWeeklyEventScript(ArxCommandTest):
    num_additional_characters = 3

    def add_factors(self, owner, vault, lifestyle=1, charm=1, composure=1, command=1, skills=None):
        "set values for vault, upkeep, and social_clout attributes."
        owner.vault = vault
        owner.save()
        owner.player.lifestyle_rating = lifestyle
        owner.player.save()
        owner.player.player.char_ob.db.charm = charm
        owner.player.player.char_ob.db.composure = composure
        owner.player.player.char_ob.db.command = command
        owner.player.player.char_ob.db.skills = skills or {}
        cost = LIFESTYLES.get(lifestyle, (0, 0))[0]
        return vault - cost

    def assert_tran_success(self, transaction, sender_vault, receiver_vault=None):
        if receiver_vault:
            self.assertEqual(transaction.receiver.vault, receiver_vault + transaction.weekly_amount)
        self.assertEqual(transaction.sender.vault, sender_vault - transaction.weekly_amount)

    def test_income_basic(self):
        "Tests weekly lifestyle cost and transactions between people."
        vault2, vault3, vault4, vault5 = 1000, 2000, 3000, 10
        pl2 = self.add_factors(self.assetowner2, vault2, 2, charm=5, skills={'seduction': 5, 'streetwise': 2})
        pl3 = self.add_factors(self.assetowner3, vault3, 3, charm=6, skills={'propaganda': 4, 'haggling': 6})
        pl4 = self.add_factors(self.assetowner4, vault4, 4, command=3, skills={'diplomacy': 3, 'etiquette': 4})
        pl5 = self.add_factors(self.assetowner5, vault5, composure=4, skills={'manipulation': 3, 'intimidation': 5})
        # post-lifestyle (pl) vaults: pl2=900, pl3=1800, pl4=2500, pl5=10
        # TODO: test prestige changes
        new_tran = AccountTransaction.objects.create
        tran1 = new_tran(receiver=self.assetowner3, sender=self.assetowner2,  # 3 gets paid
                         category="Blackmail", weekly_amount=10)
        tran2 = new_tran(receiver=self.assetowner3, sender=self.assetowner5,  # 5 cannot afford
                         category="Lost Bet", weekly_amount=3333)
        tran3 = new_tran(receiver=None, sender=self.assetowner2,
                         category="Debt", weekly_amount=75)
        tran4 = new_tran(receiver=self.assetowner3, sender=self.assetowner4,  # 3 gets paid
                         category="Blush", weekly_amount=100)
        event1 = create_script(WeeklyEvents)
        event1.db.week = 1
        event1.do_dominion_events()
        event1.inform_creator.create_and_send_informs()
        self.assert_tran_success(tran1, pl2 - tran3.weekly_amount, pl3 + tran4.weekly_amount)
        self.assertTrue(
            "Failed payments to you: %s -> %s. Amount: %s" % (self.assetowner5, self.assetowner3, tran2.weekly_amount)
            in self.account3.informs.last().message)
        self.assertEqual(self.assetowner5.vault, pl5)  # Same because tran2 failed
        self.assert_tran_success(tran3, pl2 - tran1.weekly_amount, receiver_vault=None)
        self.assert_tran_success(tran4, pl4, pl3 + tran1.weekly_amount)
