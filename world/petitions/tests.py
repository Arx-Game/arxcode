# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from mock import Mock

from server.utils.test_utils import ArxCommandTest
from world.petitions import petitions_commands
from datetime import date


class TestPetitionCommands(ArxCommandTest):


    def test_cmd_broker(self):
        from world.petitions.models import BrokeredSale
        from world.dominion.models import CraftingMaterialType
        from web.character.models import PlayerAccount
        from evennia.server.models import ServerConfig
        mat = CraftingMaterialType.objects.create(name="testium", value=5000)
        sale = BrokeredSale.objects.create(owner=self.dompc2, sale_type=BrokeredSale.ACTION_POINTS, amount=50, price=5,
                                           broker_type=BrokeredSale.SALE)
        self.setup_cmd(petitions_commands.CmdBroker, self.char1)
        self.call_cmd("", 'ID Seller       Type          Price Amount \n'
                          '1  Testaccount2 Action Points 5     50     |\nID Buyer Type Price Amount')
        self.call_cmd("/buy 2", "You must ask for both an amount and a price.")
        self.call_cmd("/buy 1,2", "You must ask for both an amount and a price.")
        self.call_cmd("/buy ap=1,-5", "You must provide a positive number as the price.")
        self.call_cmd("/buy ap=-1,5", "You must provide a positive number as the amount.")
        self.char1.currency += 20000
        self.assertEqual(self.char2.currency, 0)
        self.call_cmd("/buy ap=1,100",
                      "You have placed an order for 1 Action Points for 100 silver each and 100 total.")
        self.call_cmd("/reprice 2=500000000", "You cannot afford to pay 499999900 when you only have 19900.0 silver.")
        self.assertEqual(self.char1.currency, 19900)
        self.call_cmd("/reprice 2=5000", "You have changed the price to 5000.")
        self.assertEqual(self.char1.currency, 15000)
        self.call_cmd("/cancel 2", "You have cancelled the purchase.")
        self.assertEqual(self.char1.currency, 20000)
        self.char1.currency -= 20000
        self.roster_entry.current_account = PlayerAccount.objects.create(email="foom@foo.net")
        self.roster_entry.save()
        self.call_cmd("/buy ap=1,100", "You cannot afford to pay 100 when you only have 0.0 silver.")
        self.char1.currency += 20000
        self.assertEqual(self.char1.currency, 20000)
        self.call_cmd("/buy ap=5,100", "You have bought 5 Action Points from Testaccount2 for 25 silver.")
        self.call_cmd("", 'ID Seller       Type          Price Amount \n1  Testaccount2 Action Points 5     45     |'
                          '\nID Buyer Type Price Amount')
        self.call_cmd("/buy ap=15,25", 'You have bought 15 Action Points from Testaccount2 for 75 silver.')
        self.assertEqual(self.char1.currency, 19900)
        self.assertEqual(self.char2.currency, 100)
        self.assertEqual(self.roster_entry.action_points, 120)
        self.assertEqual(sale.amount, 30)
        self.call_cmd("/buy ap=125,10",
                      "You have bought 30 Action Points from Testaccount2 for 150 silver.|"
                      "You have placed an order for 95 Action Points for 10 silver each and 950 total.")
        self.assertEqual(self.roster_entry.action_points, 150)
        self.assertEqual(sale.pk, None)
        self.call_cmd("/cancel 5", "You have cancelled the purchase.")
        self.char1.currency += 250
        sale2 = BrokeredSale.objects.create(owner=self.dompc2, sale_type=BrokeredSale.ECONOMIC, amount=50, price=5)
        sale3 = BrokeredSale.objects.create(owner=self.dompc2, sale_type=BrokeredSale.CRAFTING_MATERIALS, amount=50,
                                            price=5, crafting_material_type=mat)
        self.call_cmd("/buy Economic=5,100", "You have bought 5 Economic Resources from Testaccount2 for 25 silver.")
        self.call_cmd("/buy Testium=10,100", "You have bought 10 testium from Testaccount2 for 50 silver.")
        self.assertEqual(sale2.amount, 45)
        self.assertEqual(sale3.amount, 40)
        self.assertEqual(self.char1.currency, 19925)
        self.assertEqual(self.char2.currency, 325)
        self.assertEqual(self.assetowner.economic, 5)
        self.assertEqual(self.assetowner.materials.get(type=mat).amount, 10)
        self.call_cmd("/sell asdf", 'You must ask for both an amount and a price.')
        self.call_cmd("/sell foo=5", 'You must ask for both an amount and a price.')
        self.call_cmd("/sell ap=10,-20", "You must provide a positive number as the price.")
        self.call_cmd("/sell ap=10,100", "Action Points must be a factor of 3,"
                                         " since it's divided by 3 when put on sale.")
        ServerConfig.objects.conf(key="DISABLE_AP_TRANSFER", value=True)
        self.call_cmd("/sell ap=12,100", 'Action Point sales are temporarily disabled.')
        ServerConfig.objects.conf(key="DISABLE_AP_TRANSFER", delete=True)
        self.call_cmd("/sell ap=12,100", "Created a new sale of 4 Action Points for 100 silver each and 400 total.")
        self.call_cmd("/sell ap=6,100",
                      "Added 2 to the existing sale of Action Points for 100 silver each and 600 total.")
        self.call_cmd("/sell ap=600,500", "You do not have enough action points to put on sale.")
        self.call_cmd("/sell military=1, 1000", "You do not have enough military resources to put on sale.")
        self.call_cmd("/sell economic=1,1000",
                      "Created a new sale of 1 Economic Resources for 1000 silver each and 1000 total.")
        self.assertEqual(self.assetowner.economic, 4)
        self.call_cmd("/sell economic=2,500",
                      "Created a new sale of 2 Economic Resources for 500 silver each and 1000 total.")
        self.assertEqual(self.assetowner.economic, 2)
        self.call_cmd("/sell asdf=2,500", "Could not find a material by the name 'asdf'.")
        self.call_cmd("/sell testium=1,500", "Created a new sale of 1 testium for 500 silver each and 500 total.")
        mat.acquisition_modifiers = "nosell"
        mat.save()
        self.call_cmd("/sell testium=2,500", "You can't put contraband on the broker! "
                                             "Seriously, how are you still alive?")
        self.call_cmd("/cancel 6", "You can only cancel your own sales.")
        self.assertEqual(self.assetowner.economic, 2)
        self.call_cmd("", 'ID Seller       Type               Price Amount \n'
                          '6  Testaccount2 Economic Resources 5     45     '
                          '7  Testaccount2 testium            5     40     '
                          '10 Testaccount  Action Points      100   6      '
                          '11 Testaccount  Economic Resources 1000  1      '
                          '12 Testaccount  Economic Resources 500   2      '
                          '13 Testaccount  testium            500   1      |\n'
                          'ID Buyer Type Price Amount')
        self.call_cmd("/cancel 11", "You have cancelled the sale.")
        self.assertEqual(self.assetowner.economic, 3)
        self.call_cmd("/search ap", 'ID Seller      Type          Price Amount \n'
                                    '10 Testaccount Action Points 100   6      |\n'
                                    'ID Buyer Type Price Amount')
        self.call_cmd("/search testaccount2", 'ID Seller       Type               Price Amount \n'
                                              '6  Testaccount2 Economic Resources 5     45     '
                                              '7  Testaccount2 testium            5     40     |\n'
                                              'ID Buyer Type Price Amount')
        self.call_cmd("/search resources", 'ID Seller       Type               Price Amount \n'
                                           '6  Testaccount2 Economic Resources 5     45     '
                                           '12 Testaccount  Economic Resources 500   2      |\n'
                                           'ID Buyer Type Price Amount')
        self.call_cmd("/search materials", 'ID Seller       Type    Price Amount \n'
                                           '7  Testaccount2 testium 5     40     '
                                           '13 Testaccount  testium 500   1      |\n'
                                           'ID Buyer Type Price Amount')
        sale14 = BrokeredSale.objects.create(owner=self.dompc, sale_type=BrokeredSale.CRAFTING_MATERIALS,
                                             crafting_material_type=mat, amount=2, price=50)
        self.call_cmd("/reprice 6=200", "You can only change the price of your own sales.")
        self.call_cmd("/reprice 14=-50", "You must provide a positive number as the price.")
        self.call_cmd("/reprice 14=50", "The new price must be different from the current price.")
        self.call_cmd("/reprice 14=500", 'You have changed the price to 500, merging with an existing sale.')
        self.assertEqual(sale14.pk, None)
        sale7 = BrokeredSale.objects.get(id=7)
        self.assertEqual(sale7.amount, 40)
        sale15 = BrokeredSale.objects.create(owner=self.dompc2, sale_type=BrokeredSale.SOCIAL, amount=50, price=300,
                                             broker_type=BrokeredSale.PURCHASE)
        self.assetowner.social = 60
        self.call_cmd("/sell social=5,250", 'You have sold 5 Social Resources to Testaccount2 for 1500 silver.')
        self.call_cmd("/sell social=55,350",
                      'Created a new sale of 55 Social Resources for 350 silver each and 19250 total.')
        self.call_cmd("", 'ID Seller       Type               Price Amount \n'
                          '6  Testaccount2 Economic Resources 5     45     '
                          '7  Testaccount2 testium            5     40     '
                          '10 Testaccount  Action Points      100   6      '
                          '12 Testaccount  Economic Resources 500   2      '
                          '13 Testaccount  testium            500   3      '
                          '17 Testaccount  Social Resources   350   55     |\n'
                          'ID Buyer        Type             Price Amount \n'
                          '15 Testaccount2 Social Resources 300   45')
        self.call_cmd("/reprice 17=300", 'You have sold 45 Social Resources to Testaccount2 for 13500 silver.|'
                                         'You have changed the price to 300.')
        self.assertEqual(sale15.pk, None)
        self.assertEqual(self.assetowner2.social, 50)
        self.assertEqual(self.char1.currency, 34925)
        self.call_cmd("/buy military=10,500",
                      'You have placed an order for 10 Military Resources for 500 silver each and 5000 total.')
        self.assertEqual(self.char1.currency, 29925)
        self.call_cmd("/reprice 18=200", 'You have changed the price to 200.')
        self.assertEqual(self.char1.currency, 32925)
        self.call_cmd("/reprice 18=300", 'You have changed the price to 300.')
        self.assertEqual(self.char1.currency, 31925)

    def test_cmd_petition(self):

        from world.petitions.models import Petition, PetitionParticipation
        from world.dominion.models import Organization
        self.setup_cmd(petitions_commands.CmdPetition, self.char1)
        self.call_cmd("", 'Updated ID Owner Topic Org On')
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
        self.call_cmd(
            "test org",
            '\x1b[0mUpdated\x1b[0m   \x1b[0mID\x1b[0m \x1b[0mOwner\x1b[0m        \x1b[0mTopic\x1b[0m \x1b[0mOrg\x1b[0m      \x1b[0mOn\x1b[0m \n\x1b[0mU\x1b[38;5;208m' +
            date.today().strftime("%m/%d/%y") +
            '\x1b[0m 1  \x1b[0mTestaccount2\x1b[0m \x1b[0mtest\x1b[0m  \x1b[0mtest org\x1b[0m \x1b[0m\x1b[0m',
            noansi=False)
        self.call_cmd("", 'Updated   ID Owner        Topic Org      On \nU'+date.today().strftime("%m/%d/%y")+' 1  Testaccount2 test  test org')
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
        org.members.create(player=self.dompc2, rank=4, deguilded=True)
        self.dompc2.petition_settings.get_or_create()
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
        self.account2.inform = Mock()
        org.inform = Mock()
        self.call_cmd("/submit", "Successfully created petition 3.")
        self.call_cmd("/search testing2=test org", 'Updated  ID Owner       Topic Org      On \n'+date.today().strftime("%m/%d/%y")+' 3  Testaccount test2 test org')
        self.call_cmd("/search test2", 'Updated  ID Owner       Topic Org      On \n'+date.today().strftime("%m/%d/%y")+' 3  Testaccount test2 test org')
        self.call_cmd("/search asdfadsf", "Updated ID Owner Topic Org On")
        org.inform.assert_called_with('A new petition has been made by Testaccount.', category='Petitions')
        self.account2.inform.assert_not_called()

        self.caller = self.char2
        self.account2.inform = Mock()
        self.call_cmd("/ignore all", "You are no longer informed of new petitions.")

        self.caller = self.char1
        self.char.db.petition_form = {'topic': 'test2', 'description': 'testing2'}
        self.call_cmd("/submit", "Successfully created petition 4.")
        self.account2.inform.assert_not_called()

        self.caller = self.char2
        self.account2.inform = Mock()
        self.call_cmd("/ignore all", "You are now informed of new petitions.")

        self.caller = self.char1
        self.char.db.petition_form = {'topic': 'test2', 'description': 'testing2'}
        self.call_cmd("/submit", "Successfully created petition 5.")
        self.account2.inform.assert_called()

        self.caller = self.char2
        self.account2.inform = Mock()
        self.call_cmd("/ignore general", "You are no longer informed of new general petitions.")

        self.caller = self.char1
        self.char.db.petition_form = {'topic': 'test2', 'description': 'testing2'}
        self.call_cmd("/submit", "Successfully created petition 6.")
        self.account2.inform.assert_not_called()

        self.caller = self.char2
        self.account2.inform = Mock()
        self.call_cmd("/ignore general", "You are now informed of new general petitions.")

        self.caller = self.char1
        self.char.db.petition_form = {'topic': 'test2', 'description': 'testing2'}
        self.call_cmd("/submit", "Successfully created petition 7.")
        self.account2.inform.assert_called()

        self.caller = self.char1
        self.call_cmd("/ignore test org", "You are no longer informed of new test org petitions.")

        self.caller = self.char2
        self.account1.inform = Mock()
        self.char2.db.petition_form = {'topic': 'test2', 'description': 'testing2', 'organization': org.id}
        self.call_cmd("/submit", "Successfully created petition 8.")
        self.account1.inform.assert_not_called()

        self.caller = self.char1
        self.call_cmd("/ignore test org", "You are now informed of new test org petitions.")

        self.caller = self.char2
        self.account1.inform = Mock()
        self.char2.db.petition_form = {'topic': 'test2', 'description': 'testing2', 'organization': org.id}
        self.call_cmd("/submit", "Successfully created petition 9.")
        self.account1.inform.assert_called()

