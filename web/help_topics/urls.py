#
# File that determines what each URL points to. This uses _Python_ regular
# expressions, not Perl's.
#
# See:
# http://diveintopython.org/regular_expressions/street_addresses.html#re.matching.2.3
#

from django.urls import re_path
from web.help_topics.views import (
    topic,
    list_commands,
    list_topics,
    list_recipes,
    display_org,
    command_help,
    lore_categories,
)

urlpatterns = [
    re_path(r"^recipes/", list_recipes, name="list_recipes"),
    re_path(r"^org/(?P<object_id>[\w\s]+)/$", display_org, name="display_org"),
    re_path(
        r"^commands/(?P<cmd_key>[\+@\_\w\s]+)/$", command_help, name="command_help"
    ),
    re_path(r"^commands/$", list_commands, name="list_commands"),
    re_path(r"^(?P<object_key>[\w\s]+)/$", topic, name="topic"),
    re_path(r"^$", list_topics, name="list_topics"),
    re_path(r"^lore/(?P<object_id>[\w\s]+)/$", lore_categories, name="lore"),
]
