#
# File that determines what each URL points to. This uses _Python_ regular
# expressions, not Perl's.
#
# See:
# http://diveintopython.org/regular_expressions/street_addresses.html#re.matching.2.3
#

from django.urls import re_path
from web.character import views

urlpatterns = [
    re_path(r"^active/$", views.ActiveRosterListView.as_view(), name="active_roster"),
    re_path(
        r"^available/$",
        views.AvailableRosterListView.as_view(),
        name="available_roster",
    ),
    re_path(
        r"^incomplete/$",
        views.IncompleteRosterListView.as_view(),
        name="incomplete_roster",
    ),
    re_path(
        r"^unavailable/$",
        views.UnavailableRosterListView.as_view(),
        name="unavailable_roster",
    ),
    re_path(
        r"^inactive/$", views.InactiveRosterListView.as_view(), name="inactive_roster"
    ),
    re_path(r"^gone/$", views.GoneRosterListView.as_view(), name="gone_roster"),
    re_path(r"^story/$", views.ChapterListView.as_view(), name="current_story"),
    re_path(r"^story/episodes/(?P<ep_id>\d+)/$", views.episode, name="episode"),
    re_path(r"^sheet/(?P<object_id>\d+)/$", views.sheet, name="sheet"),
    re_path(r"^sheet/(?P<object_id>\d+)/comment$", views.comment, name="comment"),
    re_path(r"^sheet/(?P<object_id>\d+)/upload$", views.upload, name="upload"),
    re_path(
        r"^sheet/(?P<object_id>\d+)/upload/complete$",
        views.direct_upload_complete,
        name="direct_upload_complete",
    ),
    re_path(r"^sheet/(?P<object_id>\d+)/gallery$", views.gallery, name="gallery"),
    re_path(
        r"^sheet/(?P<object_id>\d+)/gallery/select_portrait$",
        views.select_portrait,
        name="select_portrait",
    ),
    re_path(
        r"^sheet/(?P<object_id>\d+)/gallery/edit_photo$",
        views.edit_photo,
        name="edit_photo",
    ),
    re_path(
        r"^sheet/(?P<object_id>\d+)/gallery/delete_photo$",
        views.delete_photo,
        name="delete_photo",
    ),
    re_path(
        r"^sheet/(?P<object_id>\d+)/story$",
        views.ActionListView.as_view(),
        name="character_story",
    ),
    re_path(
        r"^sheet/(?P<object_id>\d+)/scenes$",
        views.FlashbackListView.as_view(),
        name="list_flashbacks",
    ),
    re_path(
        r"^sheet/(?P<object_id>\d+)/scenes/create$",
        views.FlashbackCreateView.as_view(),
        name="create_flashback",
    ),
    re_path(
        r"^sheet/(?P<object_id>\d+)/scenes/(?P<flashback_id>\d+)/$",
        views.FlashbackAddPostView.as_view(),
        name="flashback_post",
    ),
    re_path(
        r"^sheet/(?P<object_id>\d+)/clues/$",
        views.KnownCluesView.as_view(),
        name="list_clues",
    ),
    re_path(
        r"^sheet/(?P<object_id>\d+)/actions/$",
        views.NewActionListView.as_view(),
        name="list_actions",
    ),
    re_path(
        r"^sheet/(?P<object_id>\d+)/actions/(?P<action_id>\d+)/$",
        views.new_action_view,
        name="view_action",
    ),
    re_path(
        r"^sheet/(?P<object_id>\d+)/actions/(?P<action_id>\d+)/edit$",
        views.edit_action,
        name="edit_action",
    ),
    re_path(r"^api/$", views.character_list, name="character_list"),
]
