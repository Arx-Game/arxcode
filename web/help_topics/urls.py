#
# File that determines what each URL points to. This uses _Python_ regular
# expressions, not Perl's.
#
# See:
# http://diveintopython.org/regular_expressions/street_addresses.html#re.matching.2.3
#

from django.conf.urls import url
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
    url(r"^recipes/", list_recipes, name="list_recipes"),
    url(r"^org/(?P<object_id>[\w\s]+)/$", display_org, name="display_org"),
    url(r"^commands/(?P<cmd_key>[\+@\_\w\s]+)/$", command_help, name="command_help"),
    url(r"^commands/$", list_commands, name="list_commands"),
    url(r"^(?P<object_key>[\w\s]+)/$", topic, name="topic"),
    url(r"^$", list_topics, name="list_topics"),
    url(r"^lore/(?P<object_id>[\w\s]+)/$", lore_categories, name="lore"),
]
