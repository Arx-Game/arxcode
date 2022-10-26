from django.conf.urls import url
from world.exploration import views


urlpatterns = [
    url(r"^api/list$", views.get_haven_list, name="get_haven_list"),
    url(r"^api/haven$", views.get_haven, name="get_haven"),
    url(r"^api/haven/obstacles$", views.get_obstacle_list, name="get_obstacles"),
    url(r"^api/haven/room/create", views.create_room, name="create_room"),
    url(r"^api/haven/room/delete", views.delete_room, name="delete_room"),
    url(r"^api/haven/room/edit", views.save_room, name="save_room"),
    url(r"^api/haven/puzzles", views.get_puzzle_list, name="get_puzzles"),
    url(r"^api/haven/monsters", views.get_monster_list, name="get_monsters"),
    url(r"^shardhaven_editor", views.shardhaven_editor_view, name="shardhaven_editor"),
]
