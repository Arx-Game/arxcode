"""
Tests for scripts.
"""
from mock import patch, Mock
from evennia import create_script
from server.utils.test_utils import ArxCommandTest
from world.dominion.models import AccountTransaction, LIFESTYLES
from typeclasses.scripts.weekly_events import WeeklyEvents


class TestWeeklyEventScript(ArxCommandTest):
    num_additional_characters = 3

    def add_factors(self, owner, vault, lifestyle, charm=1, composure=1, command=1, skills=None):
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

    def calculate_transaction(self, transaction, sender_vault, receiver_vault=None):
        if receiver_vault:
            self.assertEqual(transaction.receiver.vault, receiver_vault + transaction.weekly_amount)
        self.assertEqual(transaction.sender.vault, sender_vault - transaction.weekly_amount)

    def test_income_update(self):
        # char1 thru char5 exist
        vault2, vault3, vault4, vault5 = 1000, 2000, 3000, 10
        nvault2 = self.add_factors(self.assetowner2, vault2, 2, charm=5, skills={'seduction': 5, 'streetwise': 2})
        nvault3 = self.add_factors(self.assetowner3, vault3, 3, charm=6, skills={'propaganda': 4, 'haggling': 6})
        nvault4 = self.add_factors(self.assetowner4, vault4, 4, command=3, skills={'diplomacy': 3, 'etiquette': 4})
        nvault5 = self.add_factors(self.assetowner5, vault5, 1, composure=4, skills={'manipulation': 3, 'intimidation': 5})
        # post-lifestyle: nvault2=900, nvault3=1800, nvault4=2500, nvault5=10
        new_trans = AccountTransaction.objects.create
        trans1 = new_trans(receiver=self.assetowner3,  # 3 gettin paid
                           sender=self.assetowner2,
                           category="Blackmail",
                           weekly_amount=10)
        trans2 = new_trans(receiver=self.assetowner3,  # 3 gets 0 because
                           sender=self.assetowner5,  # assetowner5 cannot afford this
                           category="Lost Bet",
                           weekly_amount=3333)
        trans3 = new_trans(receiver=None,
                           sender=self.assetowner2,
                           category="Debt",
                           weekly_amount=75)
        trans4 = new_trans(receiver=self.assetowner3,  # 3 gettin paid
                           sender=self.assetowner4,
                           category="Blush",
                           weekly_amount=100)
        event1 = create_script(WeeklyEvents)
        event1.db.week = 0
        event1.do_dominion_events()
        self.calculate_transaction(trans1,
                                   nvault2 - trans3.weekly_amount,
                                   nvault3 + trans4.weekly_amount)
        # transaction 2 would fail
        self.calculate_transaction(trans3,
                                   nvault2 - trans1.weekly_amount)
        self.calculate_transaction(trans4,
                                   nvault4,
                                   nvault3 + trans1.weekly_amount)
