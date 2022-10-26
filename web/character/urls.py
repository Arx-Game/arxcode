#
# File that determines what each URL points to. This uses _Python_ regular
# expressions, not Perl's.
#
# See:
# http://diveintopython.org/regular_expressions/street_addresses.html#re.matching.2.3
#

from django.conf.urls import url
from web.character import views

urlpatterns = [
    url(r"^active/$", views.ActiveRosterListView.as_view(), name="active_roster"),
    url(
        r"^available/$",
        views.AvailableRosterListView.as_view(),
        name="available_roster",
    ),
    url(
        r"^incomplete/$",
        views.IncompleteRosterListView.as_view(),
        name="incomplete_roster",
    ),
    url(
        r"^unavailable/$",
        views.UnavailableRosterListView.as_view(),
        name="unavailable_roster",
    ),
    url(r"^inactive/$", views.InactiveRosterListView.as_view(), name="inactive_roster"),
    url(r"^gone/$", views.GoneRosterListView.as_view(), name="gone_roster"),
    url(r"^story/$", views.ChapterListView.as_view(), name="current_story"),
    url(r"^story/episodes/(?P<ep_id>\d+)/$", views.episode, name="episode"),
    url(r"^sheet/(?P<object_id>\d+)/$", views.sheet, name="sheet"),
    url(r"^sheet/(?P<object_id>\d+)/comment$", views.comment, name="comment"),
    url(r"^sheet/(?P<object_id>\d+)/upload$", views.upload, name="upload"),
    url(
        r"^sheet/(?P<object_id>\d+)/upload/complete$",
        views.direct_upload_complete,
        name="direct_upload_complete",
    ),
    url(r"^sheet/(?P<object_id>\d+)/gallery$", views.gallery, name="gallery"),
    url(
        r"^sheet/(?P<object_id>\d+)/gallery/select_portrait$",
        views.select_portrait,
        name="select_portrait",
    ),
    url(
        r"^sheet/(?P<object_id>\d+)/gallery/edit_photo$",
        views.edit_photo,
        name="edit_photo",
    ),
    url(
        r"^sheet/(?P<object_id>\d+)/gallery/delete_photo$",
        views.delete_photo,
        name="delete_photo",
    ),
    url(
        r"^sheet/(?P<object_id>\d+)/story$",
        views.ActionListView.as_view(),
        name="character_story",
    ),
    url(
        r"^sheet/(?P<object_id>\d+)/scenes$",
        views.FlashbackListView.as_view(),
        name="list_flashbacks",
    ),
    url(
        r"^sheet/(?P<object_id>\d+)/scenes/create$",
        views.FlashbackCreateView.as_view(),
        name="create_flashback",
    ),
    url(
        r"^sheet/(?P<object_id>\d+)/scenes/(?P<flashback_id>\d+)/$",
        views.FlashbackAddPostView.as_view(),
        name="flashback_post",
    ),
    url(
        r"^sheet/(?P<object_id>\d+)/clues/$",
        views.KnownCluesView.as_view(),
        name="list_clues",
    ),
    url(
        r"^sheet/(?P<object_id>\d+)/actions/$",
        views.NewActionListView.as_view(),
        name="list_actions",
    ),
    url(
        r"^sheet/(?P<object_id>\d+)/actions/(?P<action_id>\d+)/$",
        views.new_action_view,
        name="view_action",
    ),
    url(
        r"^sheet/(?P<object_id>\d+)/actions/(?P<action_id>\d+)/edit$",
        views.edit_action,
        name="edit_action",
    ),
    url(r"^api/$", views.character_list, name="character_list"),
]
