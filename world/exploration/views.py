from django.http import JsonResponse
from django.db.models import Q
from .models import Shardhaven, ShardhavenLayout, ShardhavenLayoutSquare, \
    ShardhavenLayoutExit, ShardhavenObstacle, ShardhavenPuzzle, Monster


JSON_ERROR_AUTHORIZATION = -1
JSON_ERROR_BADPARAM = -2


class JsonErrorResponse(JsonResponse):

    def __init__(self, error_string, status=500, code=None):
        result = {
            'error': error_string
        }
        if code:
            result['code'] = code
        super(JsonErrorResponse, self).__init__(result, status=status)


def get_haven_list(request):
    if not request.user.is_staff:
        return JsonErrorResponse("Not authorized!", code=JSON_ERROR_AUTHORIZATION)

    result = []
    for haven in Shardhaven.objects.all():
        haven_data = {
            'id': haven.id,
            'name': str(haven.name)
        }
        result.append(haven_data)

    return JsonResponse({'havens': result})


def get_obstacle_list(request):
    if not request.user.is_staff:
        return JsonErrorResponse("Not authorized!", code=JSON_ERROR_AUTHORIZATION)

    haven_id = None
    try:
        haven_string = request.POST.get('haven_id')
        if haven_string:
            haven_id = int(haven_string)
    except ValueError:
        pass

    if not haven_id:
        return JsonErrorResponse("No haven ID given.", status=404, code=JSON_ERROR_BADPARAM)

    try:
        haven = Shardhaven.objects.get(id=haven_id)
    except (Shardhaven.DoesNotExist, Shardhaven.MultipleObjectsReturned):
        return JsonErrorResponse("No such haven found.", status=404, code=JSON_ERROR_BADPARAM)

    obstacles = ShardhavenObstacle.objects.filter(haven_types__in=[haven.haven_type],
                                                  obstacle_class=ShardhavenObstacle.EXIT_OBSTACLE)
    result = []
    for obstacle in obstacles:
        name = obstacle.description
        if len(name) > 40:
            name = obstacle.description[:40] + "..."
        obstacle_data = {
            'id': obstacle.id,
            'name': name
        }
        result.append(obstacle_data)

    return JsonResponse({'obstacles': result})


def get_monster_list(request):
    if not request.user.is_staff:
        return JsonErrorResponse("Not authorized!", code=JSON_ERROR_AUTHORIZATION)

    haven_id = None
    try:
        haven_string = request.POST.get('haven_id')
        if haven_string:
            haven_id = int(haven_string)
    except ValueError:
        pass

    if not haven_id:
        return JsonErrorResponse("No haven ID given.", status=404, code=JSON_ERROR_BADPARAM)

    try:
        haven = Shardhaven.objects.get(id=haven_id)
    except (Shardhaven.DoesNotExist, Shardhaven.MultipleObjectsReturned):
        return JsonErrorResponse("No such haven found.", status=404, code=JSON_ERROR_BADPARAM)

    monsters = Monster.objects.filter(habitats__in=[haven.haven_type]).order_by('name')
    result = []
    for monster in monsters:
        monster_data = {
            'id': monster.id,
            'name': monster.name
        }
        result.append(monster_data)

    return JsonResponse({'monsters': result})


def get_puzzle_list(request):
    if not request.user.is_staff:
        return JsonErrorResponse("Not authorized!", code=JSON_ERROR_AUTHORIZATION)

    haven_id = None
    try:
        haven_string = request.POST.get('haven_id')
        if haven_string:
            haven_id = int(haven_string)
    except ValueError:
        pass

    if not haven_id:
        return JsonErrorResponse("No haven ID given.", status=404, code=JSON_ERROR_BADPARAM)

    try:
        haven = Shardhaven.objects.get(id=haven_id)
    except (Shardhaven.DoesNotExist, Shardhaven.MultipleObjectsReturned):
        return JsonErrorResponse("No such haven found.", status=404, code=JSON_ERROR_BADPARAM)

    puzzles = ShardhavenPuzzle.objects.filter(haven_types__in=[haven.haven_type])
    result = []
    for puzzle in puzzles:
        puzzle_data = {
            'id': puzzle.id,
            'name': puzzle.name
        }
        result.append(puzzle_data)

    return JsonResponse({'puzzles': result})


def get_haven(request):
    if not request.user.is_staff:
        return JsonErrorResponse("Not authorized!", code=JSON_ERROR_AUTHORIZATION)

    haven_id = None
    try:
        haven_string = request.POST.get('haven_id')
        if haven_string:
            haven_id = int(haven_string)
    except ValueError:
        pass

    if not haven_id:
        return JsonErrorResponse("No haven ID given.", status=404, code=JSON_ERROR_BADPARAM)

    try:
        haven = Shardhaven.objects.get(id=haven_id)
    except (Shardhaven.DoesNotExist, Shardhaven.MultipleObjectsReturned):
        return JsonErrorResponse("No such haven found.", status=404, code=JSON_ERROR_BADPARAM)

    layout = haven.layout

    if not layout:
        result = {
            'has_layout': False
        }
        return JsonResponse(result)

    layout.cache_room_matrix()
    matrix = [[None for y in range(layout.height)] for x in range(layout.width)]
    for x in range(layout.width):
        for y in range(layout.height):
            room = {
                'is_room': False
            }
            layout_room = layout.matrix[x][y]
            if layout_room is not None:
                room['is_room'] = True

                if layout_room.name:
                    room['name'] = str(layout_room.name)
                if layout_room.description:
                    room['description'] = str(layout_room.description)

                if x == layout.entrance_x and y == layout.entrance_y:
                    room['entrance'] = True
                for room_exit in layout_room.exit_north.all():
                    if room_exit.obstacle:
                        room['obstacle_north'] = room_exit.obstacle.id
                for room_exit in layout_room.exit_south.all():
                    if room_exit.obstacle:
                        room['obstacle_south'] = room_exit.obstacle.id
                for room_exit in layout_room.exit_east.all():
                    if room_exit.obstacle:
                        room['obstacle_east'] = room_exit.obstacle.id
                for room_exit in layout_room.exit_west.all():
                    if room_exit.obstacle:
                        room['obstacle_west'] = room_exit.obstacle.id

                if layout_room.puzzle:
                    room['puzzle'] = layout_room.puzzle.id
                    room['puzzle_solved'] = layout_room.puzzle_solved

                if layout_room.monster:
                    room['monster'] = layout_room.monster.id
                    room['monster_defeated'] = layout_room.monster_defeated

            matrix[x][y] = room

    result = {
        'has_layout': True,
        'x_dim': layout.width,
        'y_dim': layout.height,
        'matrix': matrix
    }
    return JsonResponse(result)


def create_room(request):
    if not request.user.is_staff:
        return JsonErrorResponse("Not authorized!", code=JSON_ERROR_AUTHORIZATION)

    haven_id = None
    try:
        haven_string = request.POST.get('haven_id')
        if haven_string:
            haven_id = int(haven_string)
    except ValueError:
        pass

    if not haven_id:
        return JsonErrorResponse("No haven ID given.", status=404, code=JSON_ERROR_BADPARAM)

    try:
        haven = Shardhaven.objects.get(id=haven_id)
    except (Shardhaven.DoesNotExist, Shardhaven.MultipleObjectsReturned):
        return JsonErrorResponse("No such haven found.", status=404, code=JSON_ERROR_BADPARAM)

    layout = haven.layout

    if not layout:
        return JsonErrorResponse("No layout for that haven.", status=404, code=JSON_ERROR_BADPARAM)

    if haven.entrance.room is not None:
        return JsonErrorResponse("You cannot add or remove rooms while a haven is instanciated.", status=500,
                                 code=JSON_ERROR_BADPARAM)

    x_string = request.POST.get('x')
    y_string = request.POST.get('y')
    if not x_string or not y_string:
        return JsonErrorResponse("Missing a required parameter.", status=500, code=JSON_ERROR_BADPARAM)

    try:
        x = int(x_string)
        y = int(y_string)
    except ValueError:
        return JsonErrorResponse("Invalid parameter.", status=500, code=JSON_ERROR_BADPARAM)

    if x == layout.entrance_x and y == layout.entrance_y:
        return JsonErrorResponse("You cannot delete the entrance.", status=500, code=JSON_ERROR_BADPARAM)

    if not layout.create_square(x, y):
        return JsonErrorResponse("Unable to delete room that doesn't exit", status=500, code=JSON_ERROR_BADPARAM)

    return JsonResponse({})


def delete_room(request):
    if not request.user.is_staff:
        return JsonErrorResponse("Not authorized!", code=JSON_ERROR_AUTHORIZATION)

    haven_id = None
    try:
        haven_string = request.POST.get('haven_id')
        if haven_string:
            haven_id = int(haven_string)
    except ValueError:
        pass

    if not haven_id:
        return JsonErrorResponse("No haven ID given.", status=404, code=JSON_ERROR_BADPARAM)

    try:
        haven = Shardhaven.objects.get(id=haven_id)
    except (Shardhaven.DoesNotExist, Shardhaven.MultipleObjectsReturned):
        return JsonErrorResponse("No such haven found.", status=404, code=JSON_ERROR_BADPARAM)

    layout = haven.layout

    if not layout:
        return JsonErrorResponse("No layout for that haven.", status=404, code=JSON_ERROR_BADPARAM)

    if haven.entrance.room is not None:
        return JsonErrorResponse("You cannot add or remove rooms while a haven is instanciated.", status=500,
                                 code=JSON_ERROR_BADPARAM)

    x_string = request.POST.get('x')
    y_string = request.POST.get('y')
    if not x_string or not y_string:
        return JsonErrorResponse("Missing a required parameter.", status=500, code=JSON_ERROR_BADPARAM)

    try:
        x = int(x_string)
        y = int(y_string)
    except ValueError:
        return JsonErrorResponse("Invalid parameter.", status=500, code=JSON_ERROR_BADPARAM)

    if x == layout.entrance_x and y == layout.entrance_y:
        return JsonErrorResponse("You cannot delete the entrance.", status=500, code=JSON_ERROR_BADPARAM)

    if not layout.delete_square(x, y):
        return JsonErrorResponse("Unable to delete room that doesn't exit", status=500, code=JSON_ERROR_BADPARAM)

    return JsonResponse({})


def obstacle_for_id(obstacle_id):
    try:
        obstacle_id = int(obstacle_id)
    except ValueError:
        return None

    try:
        obstacle = ShardhavenObstacle.objects.get(id=obstacle_id)
    except (ShardhavenObstacle.DoesNotExist, ShardhavenObstacle.MultipleObjectsReturned):
        return None

    return obstacle


def monster_for_id(monster_id):
    try:
        monster_id = int(monster_id)
    except ValueError:
        return None

    try:
        monster = Monster.objects.get(id=monster_id)
    except (Monster.DoesNotExist, Monster.MultipleObjectsReturned):
        return None

    return monster


def puzzle_for_id(puzzle_id):
    try:
        puzzle_id = int(puzzle_id)
    except ValueError:
        return None

    try:
        puzzle = ShardhavenPuzzle.objects.get(id=puzzle_id)
    except (ShardhavenPuzzle.DoesNotExist, ShardhavenPuzzle.MultipleObjectsReturned):
        return None

    return puzzle


def save_room(request):
    if not request.user.is_staff:
        return JsonErrorResponse("Not authorized!", code=JSON_ERROR_AUTHORIZATION)

    haven_id = None
    try:
        haven_string = request.POST.get('haven_id')
        if haven_string:
            haven_id = int(haven_string)
    except ValueError:
        pass

    if not haven_id:
        return JsonErrorResponse("No haven ID given.", status=404, code=JSON_ERROR_BADPARAM)

    try:
        haven = Shardhaven.objects.get(id=haven_id)
    except (Shardhaven.DoesNotExist, Shardhaven.MultipleObjectsReturned):
        return JsonErrorResponse("No such haven found.", status=404, code=JSON_ERROR_BADPARAM)

    layout = haven.layout

    if not layout:
        return JsonErrorResponse("No layout for that haven.", status=404, code=JSON_ERROR_BADPARAM)

    x_string = request.POST.get('x')
    y_string = request.POST.get('y')
    if not x_string or not y_string:
        return JsonErrorResponse("Missing a required parameter.", status=500, code=JSON_ERROR_BADPARAM)

    try:
        x = int(x_string)
        y = int(y_string)
    except ValueError:
        return JsonErrorResponse("Invalid parameter.", status=500, code=JSON_ERROR_BADPARAM)

    layout.cache_room_matrix()
    room = layout.matrix[x][y]

    obstacle_north = None
    obstacle_south = None
    obstacle_west = None
    obstacle_east = None
    monster = None
    monster_defeated = False
    puzzle = None
    puzzle_solved = False

    if request.POST.get("obstacle_north"):
        obstacle_north = obstacle_for_id(request.POST.get("obstacle_north"))
        if not obstacle_north:
            return JsonErrorResponse("Unable to set obstacle", status=500, code=JSON_ERROR_BADPARAM)

    if request.POST.get("obstacle_south"):
        obstacle_south = obstacle_for_id(request.POST.get("obstacle_south"))
        if not obstacle_south:
            return JsonErrorResponse("Unable to set obstacle", status=500, code=JSON_ERROR_BADPARAM)

    if request.POST.get("obstacle_west"):
        obstacle_west = obstacle_for_id(request.POST.get("obstacle_west"))
        if not obstacle_west:
            return JsonErrorResponse("Unable to set obstacle", status=500, code=JSON_ERROR_BADPARAM)

    if request.POST.get("obstacle_east"):
        obstacle_east = obstacle_for_id(request.POST.get("obstacle_east"))
        if not obstacle_east:
            return JsonErrorResponse("Unable to set obstacle", status=500, code=JSON_ERROR_BADPARAM)

    if request.POST.get("monster"):
        monster = monster_for_id(request.POST.get("monster"))
        if not monster:
            return JsonErrorResponse("Unable to set monster", status=500, code=JSON_ERROR_BADPARAM)
        monster_defeated = request.POST.get("monster_defeated") == "true"

    if request.POST.get("puzzle"):
        puzzle = puzzle_for_id(request.POST.get("puzzle"))
        if not puzzle:
            return JsonErrorResponse("Unable to set puzzle", status=500, code=JSON_ERROR_BADPARAM)
        puzzle_solved = request.POST.get("puzzle_solved") == "true"

    if request.POST.get("name"):
        room.name = request.POST.get("name")
    else:
        room.name = None

    if request.POST.get("description"):
        room.description = request.POST.get("description")
    else:
        room.description = None

    if request.POST.get("entrance"):
        layout.entrance_x = x
        layout.entrance_y = y

    room.puzzle = puzzle
    room.puzzle_solved = puzzle_solved
    room.monster = monster
    room.monster_defeated = monster_defeated

    room.save()
    layout.save()

    for room_exit in room.exit_north.all():
        room_exit.obstacle = obstacle_north
        room_exit.save()

    for room_exit in room.exit_south.all():
        room_exit.obstacle = obstacle_south
        room_exit.save()

    for room_exit in room.exit_west.all():
        room_exit.obstacle = obstacle_west
        room_exit.save()

    for room_exit in room.exit_east.all():
        room_exit.obstacle = obstacle_east
        room_exit.save()

    return JsonResponse({})


def shardhaven_editor_view(request):
    from django.shortcuts import render
    context = {
        'page_title': 'Shardhaven Editor',
    }
    return render(request, "exploration/shardhaven_editor.html", context)
