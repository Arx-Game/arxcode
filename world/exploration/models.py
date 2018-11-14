from typeclasses.scripts.combat import combat_settings
from world.stats_and_skills import do_dice_check
from evennia.utils.idmapper.models import SharedMemoryModel
from evennia.utils import create
from django.db import models
from . import builder
from server.utils.arx_utils import inform_staff
import random
from typeclasses.npcs import npc_types


class Monster(SharedMemoryModel):

    MOOKS = 0
    BOSS = 1

    MONSTER_TYPES = (
        (MOOKS, 'Mooks'),
        (BOSS, 'Boss'),
    )

    MOOK_TYPECLASS = "world.exploration.npcs.MookMonsterNpc"
    BOSS_TYPECLASS = "world.exploration.npcs.BossMonsterNpc"

    NPC_TYPES = (
        (npc_types.GUARD, "Guard"),
        (npc_types.THUG, "Thug"),
        (npc_types.SPY, "Spy"),
        (npc_types.CHAMPION, "Champion"),
        (npc_types.ASSISTANT, "Assistant"),
        (npc_types.ANIMAL, "Animal"),
        (npc_types.SMALL_ANIMAL, "Small Animal"),
    )

    name = models.CharField(max_length=40, blank=False, null=False)
    plural_name = models.CharField(max_length=40, blank=True, null=True)
    description = models.TextField(blank=False, null=False)
    spawn_message = models.TextField(blank=True, null=True)
    difficulty = models.PositiveSmallIntegerField(default=5, blank=False, null=False)
    npc_type = models.PositiveSmallIntegerField(choices=MONSTER_TYPES, default=0)
    npc_template = models.PositiveSmallIntegerField(choices=NPC_TYPES, default=0)
    habitats = models.ManyToManyField('ShardhavenType', related_name='denizens')
    minimum_quantity = models.PositiveSmallIntegerField(default=1,
                                                        help_text='Minimum number of Mooks to spawn (mooks only)')
    maximum_quantity = models.PositiveSmallIntegerField(default=10,
                                                        help_text='Maximum number of Mooks to spawn (mooks only)')
    boss_rating = models.PositiveSmallIntegerField(default=1, help_text='Boss rating (boss only)')
    threat_rating = models.PositiveSmallIntegerField(default=1, help_text='The threat rating for this monster')
    mirror = models.BooleanField(default=False,
                                 help_text='Should this monster mirror the stats of a player in the party?')

    weight_no_drop = models.PositiveSmallIntegerField(default=10,
                                                      help_text='The weight value to use for No Drop in drop '
                                                                'calculations.')

    instances = models.ManyToManyField('objects.ObjectDB', related_name='monsters')

    def create_instance(self, location):
        result = None
        for obj in self.instances.all():
            if obj.location is None:
                result = obj
                continue

        quantity = 1
        mob_name = self.name
        if self.npc_type == self.MOOKS:
            quantity = random.randint(self.minimum_quantity, self.maximum_quantity)
            if quantity > 1:
                mob_name = self.plural_name or self.name

        if not result:
            if self.npc_type == self.MOOKS:
                result = create.create_object(key=mob_name, typeclass=self.MOOK_TYPECLASS)
            elif self.npc_type == self.BOSS:
                result = create.create_object(key=mob_name, typeclass=self.BOSS_TYPECLASS)
            self.instances.add(result)

        result.setup_npc(self.npc_template, self.threat_rating, quantity, sing_name=self.name,
                         plural_name=self.plural_name or self.name)
        result.name = mob_name
        result.db.monster_id = self.id

        if self.spawn_message:
            location.msg_contents(self.spawn_message)
        result.location = location
        return result

    def handle_loot_drop(self, obj, location):
        values = {
            0: None
        }
        current_value = self.weight_no_drop
        for loot in self.drops.all():
            values[current_value] = loot.material
            current_value += loot.weight

        picker = random.randint(0, current_value)
        last_value = 0
        result = None
        for key in sorted(values.keys()):
            if key >= picker:
                result = values[last_value]
                continue
            last_value = key

        if not result:
            result = values[values.keys()[-1]]

        if result:
            location.msg_contents("The {} dropped {}!".format(obj.key, result.name))
            final_loot = result.create_instance()
            final_loot.location = location


class MonsterDrops(SharedMemoryModel):

    monster = models.ForeignKey(Monster, related_name='drops')
    material = models.ForeignKey('magic.AlchemicalMaterial', related_name='monsters')
    weight = models.PositiveSmallIntegerField(default=10, blank=False, null=False)


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
    difficulty_rating = models.PositiveSmallIntegerField(default=4)

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
    clue = models.ForeignKey("character.Clue", related_name='related_shardhavens')
    required = models.BooleanField(default=False)


class ShardhavenMoodFragment(SharedMemoryModel):

    shardhaven_type = models.ForeignKey(ShardhavenType, related_name='+')
    text = models.TextField(blank=False, null=False)


class ShardhavenObstacle(SharedMemoryModel):

    PASS_CHECK = 0
    HAS_CLUE = 1
    HAS_ALL_CLUES = 2

    OBSTACLE_TYPES = (
        (PASS_CHECK, "Pass a Dice Check"),
        (HAS_CLUE, "Possess Any Associated Clue"),
        (HAS_ALL_CLUES, "Possess All Associated Clues")
    )

    INDIVIDUAL = 0
    EVERY_TIME = 1
    ANYONE = 2

    OBSTACLE_PASS_TYPES = (
        (INDIVIDUAL, "Everyone must pass once"),
        (EVERY_TIME, "Everyone must pass every time"),
        (ANYONE, "If anyone passes, that's enough"),
    )

    haven_types = models.ManyToManyField(ShardhavenType, related_name='+', blank=True)
    obstacle_type = models.PositiveSmallIntegerField(choices=OBSTACLE_TYPES)
    description = models.TextField(blank=False, null=False)
    pass_type = models.PositiveSmallIntegerField(choices=OBSTACLE_PASS_TYPES, default=INDIVIDUAL,
                                                 verbose_name="Requirements")

    def msg(self, *args, **kwargs):
        """
        Keep the attack code happy.
        """
        pass

    def handle_dice_check(self, calling_object, args):

        if self.rolls.count() == 0:
            return True, False

        if not args:
            calling_object.msg(self.description)
            calling_object.msg("|/You have the following options:")
            counter = 1
            for roll in self.rolls.all():
                calling_object.msg("{}: [{}+{}] {}".format(counter, roll.stat, roll.skill, roll.description))
                counter += 1
            calling_object.msg("|/Enter the direction followed by the number you choose, such as 'south 1'.")
            return False, False

        try:
            choice = int(args)
        except ValueError:
            calling_object.msg("Please provide a number from 1 to {}".format(self.rolls.count()))
            return False, False

        roll = self.rolls.all()[choice - 1]
        result = do_dice_check(caller=calling_object, stat=roll.stat, skill=roll.skill, difficulty=roll.difficulty)
        if result >= roll.target:
            if roll.personal_success_msg:
                calling_object.msg(roll.personal_success_msg)

            message = roll.success_msg.replace("{name}", calling_object.key)
            calling_object.location.msg_contents(message)
            return True, roll.override
        else:
            if roll.personal_failure_msg:
                calling_object.msg(roll.personal_failure_msg)
            message = roll.failure_msg.replace("{name}", calling_object.key)
            calling_object.location.msg_contents(message)
            if roll.damage_amt:
                from typeclasses.scripts.combat.attacks import Attack
                attack = Attack(targets=[calling_object], affect_real_dmg=True, damage=roll.damage_amt,
                                use_mitigation=roll.damage_mit,
                                can_kill=True, private=True, story=roll.damage_reason, inflictor=self)
                try:
                    attack.execute()
                except combat_settings.CombatError as err:
                    inform_staff("{} broke combat failing an obstacle check in a Shardhaven: {}"
                                 .format(calling_object.name, str(err)))
            return False, False

    def handle_clue_check(self, calling_object, require_all):

        calling_object.msg(self.description + "|/")

        for clue in self.clues.all():
            if require_all:
                if clue.clue not in calling_object.roster.discovered_clues:
                    calling_object.msg("You lack the knowledge to pass this obstacle.")
                    return False, False
            else:
                if clue.clue in calling_object.roster.discovered_clues:
                    calling_object.msg("Your knowledge of \"{}\" allows you to pass.".format(clue.clue.name))
                    return True, False

        if not require_all:
            calling_object.msg("You lack the knowledge to pass this obstacle.")
            return False, False

        return True, False

    def handle_obstacle(self, calling_object, args=None):
        if self.obstacle_type == ShardhavenObstacle.PASS_CHECK:
            return self.handle_dice_check(calling_object, args)
        elif self.obstacle_type == ShardhavenObstacle.HAS_CLUE:
            return self.handle_clue_check(calling_object, False)
        elif self.obstacle_type == ShardhavenObstacle.HAS_ALL_CLUES:
            return self.handle_clue_check(calling_object, True)
        else:
            return True, False


class ShardhavenObstacleRoll(SharedMemoryModel):

    obstacle = models.ForeignKey(ShardhavenObstacle, related_name='rolls', blank=True, null=True)

    stat = models.CharField(max_length=40, blank=False, null=False)
    skill = models.CharField(max_length=40, blank=False, null=False)
    difficulty = models.PositiveSmallIntegerField(blank=False, null=False)
    target = models.PositiveSmallIntegerField(blank=False, null=False)

    override = models.BooleanField(default=False, verbose_name="Override on Success",
                                   help_text="Should succeeding on this roll make the obstacle open to everyone else?")

    description = models.TextField(blank=False, null=False, verbose_name="Description Shown of this Challenge")
    success_msg = models.TextField(blank=False, null=False, verbose_name="Message to room on Success")
    personal_success_msg = models.TextField(blank=True, null=True, verbose_name="Message to character on Success")
    failure_msg = models.TextField(blank=False, null=False, verbose_name="Message to room on Failure")
    personal_failure_msg = models.TextField(blank=True, null=True, verbose_name="Message to character on Failure")
    damage_amt = models.PositiveSmallIntegerField(blank=True, null=True,
                                                  verbose_name="Amount to damage a character by on failure")
    damage_mit = models.BooleanField(default=True, verbose_name="If damage is applied, should armor mitigate it?")
    damage_reason = models.CharField(blank=True, null=True, max_length=255,
                                     verbose_name="Short description of damage, for the damage system.")


class ShardhavenObstacleClue(SharedMemoryModel):

    obstacle = models.ForeignKey(ShardhavenObstacle, related_name='clues', blank=False, null=False)
    clue = models.ForeignKey('character.Clue', blank=False, null=False)


class ShardhavenLayoutExit(SharedMemoryModel):
    """
    This class represents a single exit between two ShardhavenLayoutSquares
    """

    layout = models.ForeignKey('ShardhavenLayout', related_name='exits')

    room_west = models.ForeignKey('ShardhavenLayoutSquare', related_name='exit_east', null=True, blank=True)
    room_east = models.ForeignKey('ShardhavenLayoutSquare', related_name='exit_west', null=True, blank=True)
    room_north = models.ForeignKey('ShardhavenLayoutSquare', related_name='exit_south', null=True, blank=True)
    room_south = models.ForeignKey('ShardhavenLayoutSquare', related_name='exit_north', null=True, blank=True)

    obstacle = models.ForeignKey(ShardhavenObstacle, related_name='+', null=True, blank=True)
    passed_by = models.ManyToManyField('objects.ObjectDB', blank=True)

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
            new_exit = create.create_object("typeclasses.exits.ShardhavenInstanceExit",
                                            key="North <N>",
                                            location=self.room_south.room,
                                            aliases=["north", "n"],
                                            destination=self.room_north.room)
            new_exit.db.haven_exit_id = self.id
            new_exit = create.create_object("typeclasses.exits.ShardhavenInstanceExit",
                                            key="South <S>",
                                            location=self.room_north.room,
                                            aliases=["south", "s"],
                                            destination=self.room_south.room)
            new_exit.db.haven_exit_id = self.id
        if self.room_east and self.room_east.room\
                and self.room_west and self.room_west.room:
            new_exit = create.create_object("typeclasses.exits.ShardhavenInstanceExit",
                                            key="East <E>",
                                            location=self.room_west.room,
                                            aliases=["east", "e"],
                                            destination=self.room_east.room)
            new_exit.db.haven_exit_id = self.id
            new_exit = create.create_object("typeclasses.exits.ShardhavenInstanceExit",
                                            key="West <W>",
                                            location=self.room_east.room,
                                            aliases=["west", "w"],
                                            destination=self.room_west.room)
            new_exit.db.haven_exit_id = self.id


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

        room = create.create_object(typeclass='world.exploration.rooms.ShardhavenRoom',
                                    key=namestring)
        room.db.haven_id = self.layout.haven.id

        final_description = self.tile.description

        fragments = ShardhavenMoodFragment.objects.filter(shardhaven_type=self.layout.haven_type)
        fragments = [fragment.text for fragment in fragments]
        random.shuffle(fragments)

        while "{}" in final_description:
            final_description = final_description.replace("{}", fragments.pop(), 1)

        room.db.raw_desc = final_description
        room.db.desc = final_description

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
        from world.dominion.models import PlotRoom
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

        obstacles = ShardhavenObstacle.objects.filter(haven_types__pk=layout.haven_type.id).all()

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

                        if random.randint(1,100) > 60:
                            obstacle = random.choice(obstacles)
                            room_exit.obstacle = obstacle

                        room_exit.save()
                    if east and not ShardhavenLayoutExit.objects.filter(room_west=room).count():
                        room_exit = ShardhavenLayoutExit(layout=layout)
                        room_exit.room_east = east
                        room_exit.room_west = room

                        if random.randint(1, 100) > 60:
                            obstacle = random.choice(obstacles)
                            room_exit.obstacle = obstacle

                        room_exit.save()
                    if north and not ShardhavenLayoutExit.objects.filter(room_south=room).count():
                        room_exit = ShardhavenLayoutExit(layout=layout)
                        room_exit.room_north = north
                        room_exit.room_south = room

                        if random.randint(1, 100) > 60:
                            obstacle = random.choice(obstacles)
                            room_exit.obstacle = obstacle

                        room_exit.save()
                    if south and not ShardhavenLayoutExit.objects.filter(room_north=room).count():
                        room_exit = ShardhavenLayoutExit(layout=layout)
                        room_exit.room_north = room
                        room_exit.room_south = south

                        if random.randint(1,100) > 60:
                            obstacle = random.choice(obstacles)
                            room_exit.obstacle = obstacle

                        room_exit.save()

        layout.save()

        # TODO: Create exit events

        # TODO: Create room events

        return layout
