from world.dominion.models import PlotRoom, Clue
from evennia.utils.idmapper.models import SharedMemoryModel
from evennia.utils import create
from django.db import models
from server.conf import settings
from . import builder
import random


class ShardhavenType(SharedMemoryModel):
    """
    This model is to bind together Shardhavens and plotroom tilesets, as well as
    eventually the types of monsters and treasures that one finds there.  This is
    simply a model so we can easily add new types without having to update Choice
    fields in Shardhaven, Plotroom, and others.
    """
    name = models.CharField(blank=False, null=False, max_length=32, db_index=True)
    description = models.TextField(max_length=2048)

    def __str__(self):
        return self.name


class Shardhaven(SharedMemoryModel):
    """
    This model represents an actual Shardhaven.  Right now, it's just meant to
    be used for storing the Shardhavens we create so we can easily refer back to them
    later.  Down the road, it will be used for the exploration system.
    """
    name = models.CharField(blank=False, null=False, max_length=78, db_index=True)
    description = models.TextField(max_length=4096)
    location = models.ForeignKey('dominion.MapLocation', related_name='shardhavens', blank=True, null=True)
    haven_type = models.ForeignKey('ShardhavenType', related_name='havens', blank=False, null=False)
    required_clue_value = models.IntegerField(default=0)
    discovered_by = models.ManyToManyField('dominion.PlayerOrNpc', blank=True, related_name="discovered_shardhavens",
                                           through="ShardhavenDiscovery")

    def __str__(self):
        return self.name or "Unnamed Shardhaven (#%d)" % self.id


class ShardhavenDiscovery(SharedMemoryModel):
    """
    This model maps a player's discovery of a shardhaven
    """
    class Meta:
        verbose_name_plural = "Shardhaven Discoveries"

    TYPE_UNKNOWN = 0
    TYPE_EXPLORATION = 1
    TYPE_CLUES = 2
    TYPE_STAFF = 3

    CHOICES_TYPES = (
        (TYPE_UNKNOWN, 'Unknown'),
        (TYPE_EXPLORATION, 'Exploration'),
        (TYPE_CLUES, 'Clues'),
        (TYPE_STAFF, 'Staff Ex Machina')
    )

    player = models.ForeignKey('dominion.PlayerOrNpc', related_name='shardhaven_discoveries')
    shardhaven = models.ForeignKey(Shardhaven, related_name='+')
    discovered_on = models.DateTimeField(blank=True, null=True)
    discovery_method = models.PositiveSmallIntegerField(choices=CHOICES_TYPES, default=TYPE_UNKNOWN)


class ShardhavenClue(SharedMemoryModel):
    """
    This model shows clues that might be used for a shardhaven,
    knowledge about it or hints that it exists.
    """
    shardhaven = models.ForeignKey(Shardhaven, related_name='related_clues')
    clue = models.ForeignKey(Clue, related_name='related_shardhavens')
    required = models.BooleanField(default=False)


class ShardhavenLayoutExit(SharedMemoryModel):
    """
    This class represents a single exit between two ShardhavenLayoutSquares
    """

    layout = models.ForeignKey('ShardhavenLayout', related_name='exits')

    room_west = models.ForeignKey('ShardhavenLayoutSquare', related_name='exit_east', null=True, blank=True)
    room_east = models.ForeignKey('ShardhavenLayoutSquare', related_name='exit_west', null=True, blank=True)
    room_north = models.ForeignKey('ShardhavenLayoutSquare', related_name='exit_south', null=True, blank=True)
    room_south = models.ForeignKey('ShardhavenLayoutSquare', related_name='exit_north', null=True, blank=True)

    # TODO: Add optional ShardhavenEvent reference.

    def __str__(self):
        string = str(self.layout) + " Exit: "
        if self.room_west is not None:
            string += "(%d,%d)" % (self.room_west.x_coord, self.room_west.y_coord)
        if self.room_east is not None:
            string += "(%d,%d)" % (self.room_east.x_coord, self.room_east.y_coord)
        if self.room_north is not None:
            string += "(%d,%d)" % (self.room_north.x_coord, self.room_north.y_coord)
        if self.room_south is not None:
            string += "(%d,%d)" % (self.room_south.x_coord, self.room_south.y_coord)
        return string

    def __repr__(self):
        return str(self)

    def __unicode__(self):
        return unicode(str(self))

    def create_exits(self):
        if self.room_south and self.room_south.room\
                and self.room_north and self.room_north.room:
            create.create_object(settings.BASE_EXIT_TYPECLASS,
                                 key="North <N>",
                                 location=self.room_south.room,
                                 aliases=["north", "n"],
                                 destination=self.room_north.room)
            create.create_object(settings.BASE_EXIT_TYPECLASS,
                                 key="South <S>",
                                 location=self.room_north.room,
                                 aliases=["south", "s"],
                                 destination=self.room_south.room)
        if self.room_east and self.room_east.room\
                and self.room_west and self.room_west.room:
            create.create_object(settings.BASE_EXIT_TYPECLASS,
                                 key="East <E>",
                                 location=self.room_west.room,
                                 aliases=["east", "e"],
                                 destination=self.room_east.room)
            create.create_object(settings.BASE_EXIT_TYPECLASS,
                                 key="West <W>",
                                 location=self.room_east.room,
                                 aliases=["west", "w"],
                                 destination=self.room_west.room)


class ShardhavenLayoutSquare(SharedMemoryModel):
    """
    This class represents a single 'tile' of a ShardhavenLayout.  When the ShardhavenLayout is
    no longer in use, all these tiles should be removed.
    """
    layout = models.ForeignKey('ShardhavenLayout', related_name='rooms')
    x_coord = models.PositiveSmallIntegerField()
    y_coord = models.PositiveSmallIntegerField()

    # We use '+' for the related name because Django will then not create a reverse relationship.
    # We don't need such, and it would just be excessive.
    tile = models.ForeignKey('dominion.PlotRoom', related_name='+')

    room = models.OneToOneField('objects.ObjectDB', related_name='shardhaven_room', blank=True, null=True)

    # TODO: Add optional ShardhavenEvent reference

    def __str__(self):
        return "{} ({},{})".format(self.layout, self.x_coord, self.y_coord)

    def __repr__(self):
        return str(self)

    def __unicode__(self):
        return unicode(str(self))

    def create_room(self):
        if self.room:
            return self.room

        namestring = "|yOutside Arx - "
        namestring += self.layout.haven.name + " - "
        namestring += self.tile.name + "|n"

        room = create.create_object(typeclass='typeclasses.rooms.ArxRoom',
                                    key=namestring)
        room.db.raw_desc = self.tile.description
        room.db.desc = self.tile.description

        self.room = room
        return room

    def destroy_room(self):
        if self.room:
            self.room.softdelete()
            self.room = None
            self.save()


class ShardhavenLayout(SharedMemoryModel):

    width = models.PositiveSmallIntegerField(default=5)
    height = models.PositiveSmallIntegerField(default=4)
    haven = models.ForeignKey(Shardhaven, related_name='layouts', null=True,
                              blank=True)
    haven_type = models.ForeignKey(ShardhavenType, related_name='+')

    entrance_x = models.PositiveSmallIntegerField(default=0)
    entrance_y = models.PositiveSmallIntegerField(default=0)

    matrix = None

    def __repr__(self):
        return self.haven.name + " Layout"

    def __str__(self):
        return self.__repr__()

    def __unicode__(self):
        return unicode(str(self))

    def cache_room_matrix(self):
        self.matrix = [[None for y in range(self.height)] for x in range(self.width)]

        for room in self.rooms.all():
            self.matrix[room.x_coord][room.y_coord] = room

    def save_rooms(self):
        for room in self.rooms.all():
            room.save()
        for room_exit in self.exits.all():
            room_exit.save()

    def destroy_instanciation(self):
        for room in self.rooms.all():
            room.destroy_room()

    @property
    def ascii(self):
        self.cache_room_matrix()
        string = ""
        for y in range(self.height):
            for x in range(self.width):
                if x == self.entrance_x and y == self.entrance_y:
                    string += "|w*|n"
                elif self.matrix[x][y] is None:
                    string += "|[B|B#|n"
                else:
                    string += " "
            string += "|n\n"

        return string

    def instanciate(self):
        for room in self.rooms.all():
            room.create_room()
        for room_exit in self.exits.all():
            room_exit.create_exits()

        self.cache_room_matrix()
        return self.matrix[self.entrance_x][self.entrance_y].room.id

    @classmethod
    def new_haven(cls, haven, width=9, height=9):
        if haven is None or not isinstance(haven, Shardhaven):
            raise ValueError("Must provide a shardhaven!")

        maze = builder.Builder(x_dim=width, y_dim=height)
        maze.build()

        plotrooms = PlotRoom.objects.filter(shardhaven_type=haven.haven_type)

        if plotrooms.count() == 0:
            raise ValueError("No valid rooms for that shardhaven type!")

        # Fetch all our plotrooms so we can pick them randomly
        plotrooms = list(plotrooms)

        layout = ShardhavenLayout(haven=haven, haven_type=haven.haven_type, width=width, height=height,
                                  entrance_x=maze.x_start, entrance_y=maze.y_start)
        layout.save()

        bulk_rooms = []
        for x in range(width):
            for y in range(height):
                if not maze.grid[x][y].wall:
                    room = ShardhavenLayoutSquare(layout=layout, tile=random.choice(plotrooms), x_coord=x, y_coord=y)
                    bulk_rooms.append(room)

        ShardhavenLayoutSquare.objects.bulk_create(bulk_rooms)
        layout.cache_room_matrix()

        for x in range(width):
            for y in range(height):
                room = layout.matrix[x][y]
                if room is not None:
                    west = layout.matrix[x - 1][y]
                    east = layout.matrix[x + 1][y]
                    north = layout.matrix[x][y - 1]
                    south = layout.matrix[x][y + 1]

                    # Why do our related-fields not populate properly?
                    # Aaargh.
                    if west and not ShardhavenLayoutExit.objects.filter(room_east=room).count():
                        room_exit = ShardhavenLayoutExit(layout=layout)
                        room_exit.room_east = room
                        room_exit.room_west = west
                        room_exit.save()
                    if east and not ShardhavenLayoutExit.objects.filter(room_west=room).count():
                        room_exit = ShardhavenLayoutExit(layout=layout)
                        room_exit.room_east = east
                        room_exit.room_west = room
                        room_exit.save()
                    if north and not ShardhavenLayoutExit.objects.filter(room_south=room).count():
                        room_exit = ShardhavenLayoutExit(layout=layout)
                        room_exit.room_north = north
                        room_exit.room_south = room
                        room_exit.save()
                    if south and not ShardhavenLayoutExit.objects.filter(room_north=room).count():
                        room_exit = ShardhavenLayoutExit(layout=layout)
                        room_exit.room_north = room
                        room_exit.room_south = south
                        room_exit.save()

        layout.save()

        # TODO: Create exit events

        # TODO: Create room events

        return layout
