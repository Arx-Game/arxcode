#
# File that determines what each URL points to. This uses _Python_ regular
# expressions, not Perl's.
#
# See:
# http://diveintopython.org/regular_expressions/street_addresses.html#re.matching.2.3
#

from django.urls import re_path
from world.dominion import views


urlpatterns = [
    re_path(r"^cal/$", views.event_calendar, name="calendar"),
    re_path(r"^cal/list/$", views.RPEventListView.as_view(), name="list_events"),
    re_path(r"^cal/create/$", views.RPEventCreateView.as_view(), name="create_event"),
    re_path(
        r"^cal/detail/(?P<pk>\d+)/$",
        views.RPEventDetailView.as_view(),
        name="display_event",
    ),
    re_path(r"^cal/comment/(?P<pk>\d+)/$", views.event_comment, name="event_comment"),
    re_path(
        r"^taskstories/list/$",
        views.AssignedTaskListView.as_view(),
        name="list_task_stories",
    ),
    re_path(
        r"^crisis/(?P<pk>\d+)/$",
        views.CrisisDetailView.as_view(),
        name="display_crisis",
    ),
    re_path(r"^map/map.png$", views.map_image, name="map_image"),
    re_path(r"^map/$", views.map_wrapper, name="map"),
    re_path(r"^fealties/chart.png$", views.fealty_chart, name="fealties"),
    re_path(
        r"^fealties/chart_full.png$", views.fealty_chart_full, name="fealties_full"
    ),
]
