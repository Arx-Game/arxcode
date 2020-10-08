# -*- coding: utf-8 -*-
from django.urls import reverse, NoReverseMatch
from django.test import TestCase

from web.helpdesk.tests.helpers import get_staff_user, reload_urlconf


class TestKBDisabled(TestCase):
    def setUp(self):
        from web.helpdesk import settings

        self.HELPDESK_KB_ENABLED = settings.HELPDESK_KB_ENABLED
        if self.HELPDESK_KB_ENABLED:
            settings.HELPDESK_KB_ENABLED = False
            reload_urlconf()

    def tearDown(self):
        from web.helpdesk import settings

        if self.HELPDESK_KB_ENABLED:
            settings.HELPDESK_KB_ENABLED = True
            reload_urlconf()

    def test_navigation(self):
        """Test proper rendering of navigation.html by accessing the dashboard"""
        self.client.login(username=get_staff_user().get_username(), password="password")
        try:
            response = self.client.get(reverse("helpdesk_dashboard"))
        except NoReverseMatch as e:
            if "helpdesk_kb_index" in str(e):
                self.fail(
                    "Please verify any unchecked references to helpdesk_kb_index (start with navigation.html)"
                )
            else:
                raise
        else:
            self.assertEqual(response.status_code, 200)
