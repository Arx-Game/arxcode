# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from mock import Mock

from server.utils.test_utils import ArxCommandTest
from world.petitions import petitions_commands


class TestPetitionCommands(ArxCommandTest):
    def test_cmd_broker(self):
        from world.petitions.models import BrokeredSale
        from world.dominion.models import CraftingMaterialType
        from web.character.models import PlayerAccount
        mat = CraftingMaterialType.objects.create(name="testium", value=5000)
        sale = BrokeredSale.objects.create(owner=self.dompc2, sale_type=BrokeredSale.ACTION_POINTS, amount=50, price=5)
        self.setup_cmd(petitions_commands.CmdBroker, self.char1)
        self.call_cmd("", 'ID Seller       Type          Price Amount \n'
                          '1  Testaccount2 Action Points 5     50')
        self.call_cmd("/buy 2", "Could not find a sale on the broker by the ID 2.")
        self.call_cmd("/buy 1", "You must provide a positive number as the amount.")
        self.call_cmd("/buy 1=-5", "You must provide a positive number as the amount.")
        self.call_cmd("/buy 1=100", "You can't buy from an alt.")
        self.roster_entry.current_account = PlayerAccount.objects.create(email="foo@foo.net")
        self.roster_entry.save()
        self.call_cmd("/buy 1=100", "You want to buy 100, but there is only 50 for sale.")
        self.call_cmd("/buy 1=25", "You cannot afford to pay 125 when you only have 0.0 silver.")
        self.char1.currency += 20000
        self.call_cmd("/buy 1=25", 'You have bought 25 Action Points from Testaccount2 for 125 silver.')
        self.assertEqual(self.roster_entry.action_points, 125)
        self.assertEqual(sale.amount, 25)
        self.call_cmd("/buy 1=10", "You have bought 10 Action Points from Testaccount2 for 50 silver.")
        self.assertEqual(self.roster_entry.action_points, 135)
        self.assertEqual(sale.amount, 15)
        sale2 = BrokeredSale.objects.create(owner=self.dompc2, sale_type=BrokeredSale.ECONOMIC, amount=50, price=5)
        sale3 = BrokeredSale.objects.create(owner=self.dompc2, sale_type=BrokeredSale.CRAFTING_MATERIALS, amount=50,
                                            price=5, crafting_material_type=mat)
        self.call_cmd("/buy 2=5", "You have bought 5 Economic Resources from Testaccount2 for 25 silver.")
        self.call_cmd("/buy 3=10", "You have bought 10 testium from Testaccount2 for 50 silver.")
        self.assertEqual(self.char1.currency, 19750)
        self.assertEqual(self.char2.currency, 250)
        self.assertEqual(self.assetowner.economic, 5)
        self.assertEqual(self.assetowner.materials.get(type=mat).amount, 10)
        self.call_cmd("/sell asdf", 'You must ask for both an amount and a price.')
        self.call_cmd("/sell foo=5", 'You must ask for both an amount and a price.')
        self.call_cmd("/sell ap=10,-20", "You must provide a positive number as the price.")
        self.call_cmd("/sell ap=10,100", "Action Points must be a factor of 3,"
                                         " since it's divided by 3 when put on sale.")
        self.call_cmd("/sell ap=12,100", "Created a new sale of 4 Action Points for 100 silver.")
        self.call_cmd("/sell ap=6,100", "Added 2 to the existing sale of Action Points for 100 silver.")
        self.call_cmd("/sell ap=600,500", "You do not have enough action points to put on sale.")
        self.call_cmd("/sell military=1, 1000", "You do not have enough military resources to put on sale.")
        self.call_cmd("/sell economic=1,1000", "Created a new sale of 1 Economic Resources for 1000 silver.")
        self.call_cmd("/sell economic=2,500", "Created a new sale of 2 Economic Resources for 500 silver.")
        self.call_cmd("/sell asdf=2,500", "Could not find a material by the name 'asdf'.")
        self.call_cmd("/sell testium=1,500", "Created a new sale of 1 testium for 500 silver.")
        mat.acquisition_modifiers = "nosell"
        mat.save()
        self.call_cmd("/sell testium=2,500", "You can't put contraband on the broker! "
                                             "Seriously, how are you still alive?")
        self.call_cmd("/buy 5=500", "You can't buy from yourself. Cancel it instead.")
        self.call_cmd("/cancel 1", "You can only cancel your own sales.")
        self.assertEqual(self.assetowner.economic, 2)
        self.call_cmd("/cancel 5", "You have cancelled the sale.")
        self.assertEqual(self.assetowner.economic, 3)
        self.call_cmd("/search ap", 'ID Seller       Type          Price Amount \n'
                                    '1  Testaccount2 Action Points 5     15     '
                                    '4  Testaccount  Action Points 100   6')
        self.call_cmd("/search testaccount2", 'ID Seller       Type               Price Amount \n'
                                              '1  Testaccount2 Action Points      5     15     '
                                              '2  Testaccount2 Economic Resources 5     45     '
                                              '3  Testaccount2 testium            5     40')
        self.call_cmd("/search resources", 'ID Seller       Type               Price Amount \n'
                                           '2  Testaccount2 Economic Resources 5     45     '
                                           '6  Testaccount  Economic Resources 500   2')
        self.call_cmd("/search materials", 'ID Seller       Type    Price Amount \n'
                                           '3  Testaccount2 testium 5     40     '
                                           '7  Testaccount  testium 500   1')
        sale8 = BrokeredSale.objects.create(owner=self.dompc, sale_type=BrokeredSale.CRAFTING_MATERIALS,
                                            crafting_material_type=mat, amount=2, price=50)
        self.call_cmd("/reprice 3=200", "You can only change the price of your own sales.")
        self.call_cmd("/reprice 8=-50", "You must provide a positive number as the price.")
        self.call_cmd("/reprice 8=50", "The new price must be different from the current price.")
        self.call_cmd("/reprice 8=500", "You have changed the price to 500.")
        self.assertEqual(sale8.pk, None)
        sale7 = BrokeredSale.objects.get(id=7)
        self.assertEqual(sale7.amount, 3)

    def test_cmd_petition(self):
        from world.petitions.models import Petition, PetitionParticipation
        from world.dominion.models import Organization
        self.setup_cmd(petitions_commands.CmdPetition, self.char1)
        self.call_cmd("", 'ID Owner Topic Org On')
        self.call_cmd("asdf", "No organization by the name asdf.")
        self.call_cmd("1", "No petition by that ID number.")
        pet = Petition.objects.create(topic="test", description="testing")
        part = PetitionParticipation.objects.create(petition=pet, dompc=self.dompc, is_owner=True)
        self.call_cmd("1", 'ID: 1  Topic: test\nOwner: Testaccount\nDescription: testing\n\nSignups:')
        part.dompc = self.dompc2
        part.save()
        self.call_cmd("/close 1", "You are not allowed to do that.")
        org = Organization.objects.create(name='test org')
        pet.organization = org
        pet.save()
        self.call_cmd("1", 'You are not allowed to access that petition.')
        self.call_cmd("test org", "You do not have access to view petitions for test org.")
        self.call_cmd("/assign 1=testaccount", "You are not allowed to access that petition.")
        org.members.create(player=self.dompc, rank=1)
        org.locks.add("admin_petition:rank(2);view_petition:rank(10)")
        self.call_cmd("test org", 'ID Owner        Topic Org      On \n1  Testaccount2 test  test org')
        self.call_cmd("", 'ID Owner        Topic Org      On \n1  Testaccount2 test  test org')
        self.call_cmd("/assign 1=testaccount2", 'You can only assign members of your organization.')
        self.call_cmd("/assign 1=testaccount", "You have assigned Testaccount to the petition.")
        self.call_cmd("/assign 1=testaccount", 'You have already signed up for this.')
        self.call_cmd("/remove 1=testaccount2", "You can only remove members of your organization.")
        self.call_cmd("/remove 1=testaccount", "You have removed Testaccount from the petition.")
        self.call_cmd("/remove 1=testaccount", "You are not signed up for that petition.")
        self.assertFalse(pet.closed)
        self.call_cmd("/close 1", "You have closed the petition.")
        self.assertTrue(pet.closed)
        self.call_cmd("/reopen 1", "You have reopened the petition.")
        self.assertFalse(pet.closed)
        self.call_cmd("/submit", "You must create a form first.")
        self.call_cmd("/create", 'Petition Being Created:\nTopic: None\nDescription: None')
        self.call_cmd("/create", 'Petition Being Created:\nTopic: None\nDescription: None\n|'
                                 'You already are creating a petition.')
        self.call_cmd("/submit", 'Please correct the following errors:\n'
                                 'topic: This field is required.\n'
                                 'description: This field is required.')
        self.call_cmd("/org foo", "No organization by that name.")
        self.call_cmd("/org test org", 'Petition Being Created:\nTopic: None\nDescription: None\nOrganization: test org')
        self.call_cmd("/org", 'Petition Being Created:\nTopic: None\nDescription: None\n')
        self.call_cmd("/topic test", 'Petition Being Created:\nTopic: test\nDescription: None\n')
        self.call_cmd("/desc testing", 'Petition Being Created:\nTopic: test\nDescription: testing\n')
        self.call_cmd("/submit", "Successfully created petition 2.")
        self.assertEqual(self.char.db.petition_form, None)
        self.char.db.petition_form = {'topic': 'test2', 'description': 'testing2', 'organization': org.id}
        org.inform = Mock()
        self.call_cmd("/submit", "Successfully created petition 3.")
        self.call_cmd("/search testing2=test org", 'ID Owner       Topic Org      On \n3  Testaccount test2 test org')
        self.call_cmd("/search test2", 'ID Owner       Topic Org      On \n3  Testaccount test2 test org')
        self.call_cmd("/search asdfadsf", "ID Owner Topic Org On")
        org.inform.assert_called_with('A new petition has been made by Testaccount.', category='Petitions')
