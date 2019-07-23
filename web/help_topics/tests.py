from django.test import TestCase
from django.test.client import Client
from django.core.urlresolvers import reverse


# Create your tests here.
class ViewTopic(TestCase):
    def setUp(self):
        from evennia.help.models import HelpEntry
        self.public_entry = HelpEntry.objects.create(db_key="Test Public")
        self.private_entry = HelpEntry.objects.create(db_key="Test Private")
        self.private_entry.locks.add("view: perm(builders)")
        self.client = Client()

    def test_view_public(self):
        response = self.client.get(reverse("help_topics:topic", args=(self.public_entry.db_key,)))
        self.assertEqual(response.status_code, 200)

    def test_view_private(self):
        from evennia.utils import create
        from typeclasses.accounts import Account
        self.account = create.create_account("TestAccount", email="test@test.com", password="testpassword",
                                             typeclass=Account)
        response = self.client.get(reverse("help_topics:topic", args=(self.private_entry.db_key,)))
        self.assertEqual(response.status_code, 403)
        logged_in_client = Client()
        logged_in_client.login(username="TestAccount", password="testpassword")
        response = logged_in_client.get(reverse("help_topics:topic", args=(self.private_entry.db_key,)))
        self.assertEqual(response.status_code, 403)
        self.account.permissions.add("builder")
        response = logged_in_client.get(reverse("help_topics:topic", args=(self.private_entry.db_key,)))
        self.assertEqual(response.status_code, 200)
