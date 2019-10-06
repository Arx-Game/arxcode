"""
Tests for scripts.
"""
from mock import patch, Mock
from evennia import create_script
from server.utils.test_utils import ArxCommandTest
from world.dominion.models import AccountTransaction
from typeclasses.scripts.weekly_events import WeeklyEvents


class TestWeeklyEventScript(ArxCommandTest):
    num_additional_characters = 3

    def add_lifestyle_and_vault(self, owner, vault, lifestyle):
        owner.vault = vault
        owner.save()
        owner.dompc.lifestyle_rating = lifestyle
        owner.dompc.save()

    def test_income_update(self):
        #Char1 thru Char5 exist; Sly is always Char2. Vanity is Char3 <3
        n_trans = AccountTransaction.objects.create
        n_trans(receiver=self.assetowner3,
                sender=self.assetowner2,
                category="Blackmail",
                weekly_amount=10)
        n_trans(receiver=self.assetowner5,
                sender=self.assetowner4,
                category="Sugar Daddy",
                weekly_amount=33)
        n_trans(receiver=None,
                sender=self.assetowner2,
                category="Debt",
                weekly_amount=75)
        self.add_lifestyle_and_vault(self.assetowner2, 1000, 2)
        self.add_lifestyle_and_vault(self.assetowner3, 2000, 3)
        self.add_lifestyle_and_vault(self.assetowner4, 3000, 4)
        self.add_lifestyle_and_vault(self.assetowner5, 10, 1)
        event1 = create_script(WeeklyEvents)
        event1.do_dominion_events()



