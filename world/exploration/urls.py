from django.urls import re_path
from world.exploration import views


urlpatterns = [
    re_path(r"^api/list$", views.get_haven_list, name="get_haven_list"),
    re_path(r"^api/haven$", views.get_haven, name="get_haven"),
    re_path(r"^api/haven/obstacles$", views.get_obstacle_list, name="get_obstacles"),
    re_path(r"^api/haven/room/create", views.create_room, name="create_room"),
    re_path(r"^api/haven/room/delete", views.delete_room, name="delete_room"),
    re_path(r"^api/haven/room/edit", views.save_room, name="save_room"),
    re_path(r"^api/haven/puzzles", views.get_puzzle_list, name="get_puzzles"),
    re_path(r"^api/haven/monsters", views.get_monster_list, name="get_monsters"),
    re_path(
        r"^shardhaven_editor", views.shardhaven_editor_view, name="shardhaven_editor"
    ),
]
