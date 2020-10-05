"""
django-helpdesk - A Django powered ticket tracker for small enterprise.

(c) Copyright 2008 Jutda. All Rights Reserved. See LICENSE for details.

templatetags/admin_url.py - Very simple template tag allow linking to the
                            right auth user model urls.

{% url 'changelist'|user_admin_url %}
"""

from django import template
from django.contrib.auth import get_user_model


def user_admin_url(action):
    user = get_user_model()
    return "admin:%s_%s_%s" % (
        user._meta.app_label,
        user._meta.model_name.lower(),
        action,
    )


register = template.Library()
register.filter(user_admin_url)
