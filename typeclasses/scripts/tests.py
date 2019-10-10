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

    def add_factors(self, owner, vault, lifestyle, charm, composure, command, skills):
        "set values for vault, upkeep, and social_clout attributes."
        owner.vault = vault
        owner.save()
        owner.dompc.lifestyle_rating = lifestyle
        owner.dompc.save()
        owner.player.char_ob.db.charm = charm or 1
        owner.player.char_ob.db.composure = composure or 1
        owner.player.char_ob.db.command = command or 1
        owner.player.char_ob.db.skills = skills or {}

    def test_income_update(self):
        # char1 thru char5 exist
        self.add_factors(self.assetowner2, 1000, 2, charm=5, skills={'seduction': 5, 'streetwise': 2})  #sly
        self.add_factors(self.assetowner3, 2000, 3, charm=6, skills={'propaganda': 4, 'haggling': 6})  #vanity
        self.add_factors(self.assetowner4, 3000, 4, command=3, skills={'diplomacy': 3, 'etiquette': 4})  #galv
        self.add_factors(self.assetowner5, 10, 1, composure=4, skills={'manipulation': 3, 'intimidation': 5})  #may
        new_trans = AccountTransaction.objects.create
        new_trans(receiver=self.assetowner3,
                  sender=self.assetowner2,
                  category="Blackmail",
                  weekly_amount=10)
        new_trans(receiver=self.assetowner5,
                  sender=self.assetowner4,
                  category="Blush",
                  weekly_amount=33)
        new_trans(receiver=None,
                  sender=self.assetowner2,
                  category="Debt",
                  weekly_amount=75)
        event1 = create_script(WeeklyEvents)
        event1.do_dominion_events()
