"""
Default settings for django-helpdesk.

"""

from django.conf import settings


try:
    DEFAULT_USER_SETTINGS = settings.HELPDESK_DEFAULT_SETTINGS
except:
    DEFAULT_USER_SETTINGS = None

if type(DEFAULT_USER_SETTINGS) != type(dict()):
    DEFAULT_USER_SETTINGS = {
        "use_email_as_submitter": True,
        "email_on_ticket_assign": True,
        "email_on_ticket_change": True,
        "login_view_ticketlist": True,
        "email_on_ticket_apichange": True,
        "tickets_per_page": 25,
    }


HAS_TAG_SUPPORT = False

""" generic options - visible on all pages """
# redirect to login page instead of the default homepage when users visits "/"?
HELPDESK_REDIRECT_TO_LOGIN_BY_DEFAULT = getattr(
    settings, "HELPDESK_REDIRECT_TO_LOGIN_BY_DEFAULT", False
)

# show knowledgebase links?
HELPDESK_KB_ENABLED = getattr(settings, "HELPDESK_KB_ENABLED", True)

# show extended navigation by default, to all users, irrespective of staff status?
HELPDESK_NAVIGATION_ENABLED = getattr(settings, "HELPDESK_NAVIGATION_ENABLED", False)

# show dropdown list of languages that ticket comments can be translated into?
HELPDESK_TRANSLATE_TICKET_COMMENTS = getattr(
    settings, "HELPDESK_TRANSLATE_TICKET_COMMENTS", False
)

# list of languages to offer. if set to false, all default google translate languages will be shown.
HELPDESK_TRANSLATE_TICKET_COMMENTS_LANG = getattr(
    settings, "HELPDESK_TRANSLATE_TICKET_COMMENTS_LANG", ["en", "de", "fr", "it", "ru"]
)

# show link to 'change password' on 'User Settings' page?
HELPDESK_SHOW_CHANGE_PASSWORD = getattr(
    settings, "HELPDESK_SHOW_CHANGE_PASSWORD", False
)

# allow user to override default layout for 'followups' - work in progress.
HELPDESK_FOLLOWUP_MOD = getattr(settings, "HELPDESK_FOLLOWUP_MOD", False)

# auto-subscribe user to ticket if (s)he responds to a ticket?
HELPDESK_AUTO_SUBSCRIBE_ON_TICKET_RESPONSE = getattr(
    settings, "HELPDESK_AUTO_SUBSCRIBE_ON_TICKET_RESPONSE", False
)


""" options for public pages """
# show 'view a ticket' section on public page?
HELPDESK_VIEW_A_TICKET_PUBLIC = getattr(settings, "HELPDESK_VIEW_A_TICKET_PUBLIC", True)

# show 'submit a ticket' section on public page?
HELPDESK_SUBMIT_A_TICKET_PUBLIC = getattr(
    settings, "HELPDESK_SUBMIT_A_TICKET_PUBLIC", True
)


""" options for update_ticket views """
# allow non-staff users to interact with tickets? this will also change how 'staff_member_required'
# in staff.py will be defined.
HELPDESK_ALLOW_NON_STAFF_TICKET_UPDATE = getattr(
    settings, "HELPDESK_ALLOW_NON_STAFF_TICKET_UPDATE", False
)

# show edit buttons in ticket follow ups.
HELPDESK_SHOW_EDIT_BUTTON_FOLLOW_UP = getattr(
    settings, "HELPDESK_SHOW_EDIT_BUTTON_FOLLOW_UP", True
)

# show delete buttons in ticket follow ups if user is 'superuser'
HELPDESK_SHOW_DELETE_BUTTON_SUPERUSER_FOLLOW_UP = getattr(
    settings, "HELPDESK_SHOW_DELETE_BUTTON_SUPERUSER_FOLLOW_UP", False
)

# make all updates public by default? this will hide the 'is this update public' checkbox
HELPDESK_UPDATE_PUBLIC_DEFAULT = getattr(
    settings, "HELPDESK_UPDATE_PUBLIC_DEFAULT", False
)

# only show staff users in ticket owner drop-downs
HELPDESK_STAFF_ONLY_TICKET_OWNERS = getattr(
    settings, "HELPDESK_STAFF_ONLY_TICKET_OWNERS", False
)

# only show staff users in ticket cc drop-down
HELPDESK_STAFF_ONLY_TICKET_CC = getattr(
    settings, "HELPDESK_STAFF_ONLY_TICKET_CC", False
)


# allow the subject to have a configurable template.
HELPDESK_EMAIL_SUBJECT_TEMPLATE = getattr(
    settings,
    "HELPDESK_EMAIL_SUBJECT_TEMPLATE",
    "{{ ticket.ticket }} {{ ticket.title|safe }} %(subject)s",
)


""" options for staff.create_ticket view """
# hide the 'assigned to' / 'Case owner' field from the 'create_ticket' view?
HELPDESK_CREATE_TICKET_HIDE_ASSIGNED_TO = getattr(
    settings, "HELPDESK_CREATE_TICKET_HIDE_ASSIGNED_TO", False
)


""" email options """
# default Queue email submission settings
QUEUE_EMAIL_BOX_TYPE = getattr(settings, "QUEUE_EMAIL_BOX_TYPE", None)
QUEUE_EMAIL_BOX_SSL = getattr(settings, "QUEUE_EMAIL_BOX_SSL", None)
QUEUE_EMAIL_BOX_HOST = getattr(settings, "QUEUE_EMAIL_BOX_HOST", None)
QUEUE_EMAIL_BOX_USER = getattr(settings, "QUEUE_EMAIL_BOX_USER", None)
QUEUE_EMAIL_BOX_PASSWORD = getattr(settings, "QUEUE_EMAIL_BOX_PASSWORD", None)
