#
# File that determines what each URL points to. This uses _Python_ regular
# expressions, not Perl's.
#
# See:
# http://diveintopython.org/regular_expressions/street_addresses.html#re.matching.2.3
#

from django.conf.urls import url
from . import views


urlpatterns = [
    url(r'^cal/list/$', views.RPEventListView.as_view(), name="list_events"),
    url(r'^cal/create/$', views.RPEventCreateView.as_view(), name="create_event"),
    url(r'^cal/detail/(?P<pk>\d+)/$', views.RPEventDetailView.as_view(), name='display_event'),
    url(r'^cal/comment/(?P<pk>\d+)/$', views.event_comment, name='event_comment'),
    url(r'^taskstories/list/$', views.AssignedTaskListView.as_view(), name="list_task_stories"),
    url(r'^crisis/(?P<pk>\d+)/$', views.CrisisDetailView.as_view(), name="display_crisis"),
    url(r'^map/map.png$', views.map_image, name='map_image'),
    url(r'^map/$', views.map_wrapper, name='map'),
    url(r'^fealties/chart.png$', views.fealty_chart, name='fealties'),
    url(r'^fealties/chart_full.png$', views.fealty_chart_full, name='fealties_full')
]
