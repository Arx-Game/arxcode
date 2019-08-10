"""
Maps.
"""
from typeclasses.objects import Object

_CALLER_ICON = '{gXX{n'
_BLANK_SQUARE = '  '
_DEST_ICON = '{rXX{n'


class Map(Object):
    """
    A map. Redo this as a table later
    """
    default_desc = "A map that holds data about a particular grid area."
    def at_object_creation(self):
        """
        Run at Map creation.
        """
        self.db.max_x = 0
        self.db.min_x = 0
        self.db.max_y = 0
        self.db.min_y = 0
        self.db.rooms = {}
        # locks so characters cannot 'get' it
        self.locks.add("get:perm(Builders);delete:false()")
        self.at_init()

    def get_icon(self, origin_room, x, y, destination=None):
        room = self.db.rooms.get((x,y), None)
        if not room:
            return _BLANK_SQUARE
        if room == origin_room:
            return _CALLER_ICON
        if (destination and destination.db.x_coord == x
            and destination.db.y_coord == y):
            return _DEST_ICON
        return room.db.map_icon or _BLANK_SQUARE

    def draw_map(self, origin_room, destination=None):
        map = ""
        for y in range(self.db.max_y, self.db.min_y - 1, -1):
            map += "\n"
            for x in range(self.db.min_x, self.db.max_x + 1):
                if x != self.db.min_x:
                    map += "-"
                # cap size of icon at 2 characters
                icon = self.get_icon(origin_room, x, y, destination)
                # if icon is only one character, add a space
                if len(icon) < 2:
                    icon += " "
                map += icon
        return map

    def add_room(self, room):
        x = room.db.x_coord
        y = room.db.y_coord
        if x > self.db.max_x:
            self.db.max_x = x
        if x < self.db.min_x:
            self.db.min_x = x
        if y > self.db.max_y:
            self.db.max_y = y
        if y < self.db.min_y:
            self.db.min_y = y
        self.db.rooms[(x,y)] = room
        room.db.map = self
        
