#
# File that determines what each URL points to. This uses _Python_ regular
# expressions, not Perl's.
#
# See:
# http://diveintopython.org/regular_expressions/street_addresses.html#re.matching.2.3
#

from django.urls import re_path
from world.msgs import views


urlpatterns = [
    re_path(r"^journals/list/$", views.JournalListView.as_view(), name="list_journals"),
    re_path(
        r"^journals/list/read/$",
        views.JournalListReadView.as_view(),
        name="list_read_journals",
    ),
    re_path(r"^journals/list/api/$", views.journal_list_json, name="journal_list_json"),
    re_path(r"^boards/$", views.board_list, name="board_list"),
    re_path(r"^boards/unread$", views.post_view_unread, name="post_view_unread"),
    re_path(
        r"^boards/search$",
        views.post_list_global_search,
        name="post_list_global_search",
    ),
    re_path(r"^boards/(?P<board_id>\d+)$", views.post_list, name="post_list"),
    re_path(
        r"^boards/(?P<board_id>\d+)/view$", views.post_view_all, name="post_view_all"
    ),
    re_path(
        r"^boards/(?P<board_id>\d+)/view/unread$",
        views.post_view_unread_board,
        name="post_view_unread_board",
    ),
    re_path(
        r"^boards/(?P<board_id>\d+)/view/(?P<post_id>\d+)$",
        views.post_view,
        name="post_view",
    ),
]
