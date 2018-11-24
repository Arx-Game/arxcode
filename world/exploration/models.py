
from typeclasses.scripts.combat import combat_settings
from world.stats_and_skills import do_dice_check

from evennia.utils.idmapper.models import SharedMemoryModel
from evennia.utils import create
from django.db import models
from . import builder
from server.utils.arx_utils import inform_staff
import random
from typeclasses.npcs import npc_types
from server.utils.picker import WeightedPicker
import datetime


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
    weight_spawn = models.PositiveSmallIntegerField(default=10)
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
    weight_trinket = models.PositiveSmallIntegerField(default=0,
                                                      help_text='The weight value to use for Trinkets')
    weight_weapon = models.PositiveSmallIntegerField(default=0,
                                                     help_text='The weight value to use for Weapons')

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

        if self.npc_type == self.BOSS:
            result.db.boss_rating = self.boss_rating

        result.setup_npc(self.npc_template, self.threat_rating, quantity, sing_name=self.name,
                         plural_name=self.plural_name or self.name)
        result.name = mob_name
        result.db.monster_id = self.id
        result.db.desc = self.description

        if self.spawn_message:
            location.msg_contents(self.spawn_message)
        result.location = location
        return result

    def handle_loot_drop(self, obj, location):
        if location is None:
            return

        haven = None
        if hasattr(location, 'shardhaven'):
            haven = location.shardhaven

        picker = WeightedPicker()

        if self.weight_no_drop > 0:
            picker.add_option(None, self.weight_no_drop)

        if haven:
            if self.weight_trinket > 0:
                picker.add_option("trinket", self.weight_trinket)

            if self.weight_weapon > 0:
                picker.add_option("weapon", self.weight_trinket)

        for loot in self.drops.all():
            picker.add_option(loot, loot.weight)

        for crafting_loot in self.crafting_drops.all():
            picker.add_option(crafting_loot, crafting_loot.weight)

        result = picker.pick()

        if result:
            final_loot = None
            if isinstance(result, basestring):
                from .loot import LootGenerator
                if result == "weapon":
                    final_loot = LootGenerator.create_weapon(haven)
                elif result == "trinket":
                    final_loot = LootGenerator.create_trinket(haven)
            else:
                quantity = random.randint(result.min_quantity, result.max_quantity)
                final_loot = result.material.create_instance(quantity)
                if haven:
                    final_loot.db.found_shardhaven = haven.name

            if final_loot is not None:
                location.msg_contents("The {} dropped {}!".format(obj.key, final_loot.name))
                final_loot.location = location


class MonsterAlchemicalDrop(SharedMemoryModel):

    monster = models.ForeignKey(Monster, related_name='drops')
    material = models.ForeignKey('magic.AlchemicalMaterial', related_name='monsters')
    weight = models.PositiveSmallIntegerField(default=10, blank=False, null=False)
    min_quantity = models.PositiveSmallIntegerField(default=1)
    max_quantity = models.PositiveSmallIntegerField(default=1)


class MonsterCraftingDrop(SharedMemoryModel):

    monster = models.ForeignKey(Monster, related_name='crafting_drops')
    material = models.ForeignKey('dominion.CraftingMaterialType', related_name='monsters')
    weight = models.PositiveSmallIntegerField(default=10, blank=False, null=False)
    min_quantity = models.PositiveSmallIntegerField(default=1)
    max_quantity = models.PositiveSmallIntegerField(default=1)


class GeneratedLootFragment(SharedMemoryModel):

    ADJECTIVE = 0
    BAUBLE_MATERIAL = 1
    BAUBLE_TYPE = 2
    NAME_FIRST = 3
    NAME_SECOND = 4
    NAME_PRE = 5
    SMALL_WEAPON_TYPE = 6
    MEDIUM_WEAPON_TYPE = 7
    HUGE_WEAPON_TYPE = 8
    BOW_WEAPON_TYPE = 9
    WEAPON_DECORATION = 10
    WEAPON_ELEMENT = 11

    FRAGMENT_TYPES = (
        (ADJECTIVE, 'Adjective'),
        (BAUBLE_MATERIAL, 'Bauble Material'),
        (BAUBLE_TYPE, 'Type of Item'),
        (NAME_FIRST, 'Name fragment (first)'),
        (NAME_SECOND, 'Name fragment (second)'),
        (NAME_PRE, 'Name fragment (prefix)'),
        (SMALL_WEAPON_TYPE, 'Small Weapon Type'),
        (MEDIUM_WEAPON_TYPE, 'Medium Weapon Type'),
        (HUGE_WEAPON_TYPE, 'Huge Weapon Type'),
        (BOW_WEAPON_TYPE, 'Archery Weapon Type'),
        (WEAPON_DECORATION, 'Weapon Decoration'),
        (WEAPON_ELEMENT, 'Weapon Element')
    )

    fragment_type = models.PositiveSmallIntegerField(choices=FRAGMENT_TYPES, default=0)
    text = models.CharField(max_length=45)

    class Meta:
        unique_together = ('fragment_type', 'text')

    @classmethod
    def pick_random_fragment(cls, ftype):

        results = cls.objects.filter(fragment_type=ftype)
        return random.choice(results.all()).text

    @classmethod
    def generate_weapon_name(cls, material='rubicund', wpn_type=MEDIUM_WEAPON_TYPE, include_name=True):

        result = ""

        if include_name:
            if random.randint(0,100) >= 97:
                result += cls.pick_random_fragment(GeneratedLootFragment.NAME_PRE) + " "

            name_first = cls.pick_random_fragment(GeneratedLootFragment.NAME_FIRST).lower()
            name_second = cls.pick_random_fragment(GeneratedLootFragment.NAME_SECOND)
            while name_second == name_first:
                name_second = cls.pick_random_fragment(GeneratedLootFragment.NAME_SECOND)

            if name_first.endswith('s') and name_second.startswith('s'):
                name_second = name_second[1:]

            wpn_name = "{}{}".format(name_first, name_second).capitalize()
            result += wpn_name + ", "

        result += 'an ancient {} '.format(material)

        result += cls.pick_random_fragment(wpn_type)
        return result

    @classmethod
    def generate_trinket_name(cls):

        adjective = cls.pick_random_fragment(GeneratedLootFragment.ADJECTIVE)
        if adjective[:1] in ["a", "e", "i", "o", "u"]:
            result = "an {} ".format(adjective)
        else:
            result = "a {} ".format(adjective)

        result += cls.pick_random_fragment(GeneratedLootFragment.BAUBLE_MATERIAL) + " "
        result += cls.pick_random_fragment(GeneratedLootFragment.BAUBLE_TYPE)

        return result


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
    taint_level = models.PositiveSmallIntegerField(default=1, help_text='How much abyssal taint does this shardhaven '
                                                                        'have, on a scale of 1 to 10.')

    weight_no_monster = models.PositiveSmallIntegerField(default=40, verbose_name="No Spawn Weight")
    weight_no_monster_backtrack = models.PositiveSmallIntegerField(default=100,
                                                                   verbose_name="No Spawn Weight on Backtrack")
    weight_boss_monster = models.PositiveSmallIntegerField(default=5, verbose_name="Boss Spawn Weight")
    weight_mook_monster = models.PositiveSmallIntegerField(default=5, verbose_name="Mook Spawn Weight")

    weight_no_treasure = models.PositiveSmallIntegerField(default=50, verbose_name="No Treasure Weight")
    weight_no_treasure_backtrack = models.PositiveSmallIntegerField(default=50, verbose_name="No Treasure Weight on Backtrack")
    weight_trinket = models.PositiveSmallIntegerField(default=5, verbose_name="Trinket Weight")
    weight_weapon = models.PositiveSmallIntegerField(default=1, verbose_name="Weapon Weight")

    auto_combat = models.BooleanField(default=False, verbose_name="Manage Combat Automatically")

    def __str__(self):
        return self.name or "Unnamed Shardhaven (#%d)" % self.id

    @property
    def entrance(self):
        if self.layout is None:
            return None

        return self.layout.entrance


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
    taint_level = models.PositiveSmallIntegerField(default=1, help_text='This mood fragment will only appear in '
                                                                        'shardhavens with this much or more abyssal '
                                                                        'taint.')


class ShardhavenObstacle(SharedMemoryModel):

    EXIT_OBSTACLE = 0
    PUZZLE_OBSTACLE = 1

    OBSTACLE_CLASSES = (
        (EXIT_OBSTACLE, "Pass an Exit"),
        (PUZZLE_OBSTACLE, "Obtain a Treasure")
    )

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
    obstacle_class = models.PositiveSmallIntegerField(default=0, choices=OBSTACLE_CLASSES)
    obstacle_type = models.PositiveSmallIntegerField(choices=OBSTACLE_TYPES)
    short_desc = models.CharField(max_length=40, blank=True, null=True,
                                  help_text="A short description of this obstacle, like 'labyrinth of mirrors'.")
    description = models.TextField(blank=False, null=False)
    pass_type = models.PositiveSmallIntegerField(choices=OBSTACLE_PASS_TYPES, default=INDIVIDUAL,
                                                 verbose_name="Requirements")
    peekable_open = models.BooleanField(default=True,
                                        help_text="Can people see through this exit when it's been passed?")
    peekable_closed = models.BooleanField(default=False,
                                          help_text="Can people see through this exit before it's been passed?")
    clue_success = models.TextField(blank=True, null=True)

    def msg(self, *args, **kwargs):
        """
        Keep the attack code happy.
        """
        pass

    def __str__(self):
        return self.short_desc or self.description

    def __repr__(self):
        return str(self)

    def __unicode__(self):
        return unicode(str(self))

    def options_description(self, exit_obj):
        direction = "south"
        if exit_obj is not None:
            direction = exit_obj.direction_name

        result = ""
        if self.rolls.count > 0:
            result += "|/You have the following options:|/"
            counter = 1
            for roll in self.rolls.all():
                result += "|/{}: [{}+{}] {}".format(counter, roll.stat, roll.skill, roll.description)
                counter += 1
            if exit_obj:
                result += "|/|/Enter the direction followed by the number you choose, such as '{} 1'.".format(direction)
            else:
                result += "|/|/Call the puzzle command with the number you choose, such as 'puzzle/solve 1'."
        return result

    def handle_dice_check(self, calling_object, exit_obj, haven_exit, args):

        if self.rolls.count() == 0:
            return True, False, True, False

        if not args:
            calling_object.msg(self.description)
            calling_object.msg(self.options_description(exit_obj))
            return False, False, False, False

        try:
            choice = int(args)
        except ValueError:
            calling_object.msg("Please provide a number from 1 to {}".format(self.rolls.count()))
            return False, False, False, False

        if choice > self.rolls.count():
            calling_object.msg("Please provide a number from 1 to {}".format(self.rolls.count()))
            return False, False, False, False

        roll = self.rolls.all()[choice - 1]
        difficulty = roll.difficulty

        if haven_exit:
            modifier = haven_exit.diff_modifier
            difficulty -= modifier
            if modifier != 0 and haven_exit.modified_diff_reason:
                calling_object.msg("Your roll difficulty is altered because %s!" % haven_exit.modified_diff_reason)

        result = do_dice_check(caller=calling_object, stat=roll.stat, skill=roll.skill, difficulty=difficulty)
        if result >= roll.target:
            if roll.personal_success_msg:
                calling_object.msg(roll.personal_success_msg)

            message = roll.success_msg.replace("{name}", calling_object.key)
            calling_object.location.msg_contents(message)
            return True, roll.override, \
                True, roll.pass_instantly or not (self.obstacle_type != ShardhavenObstacle.ANYONE and roll.override)
        else:
            if roll.personal_failure_msg:
                calling_object.msg(roll.personal_failure_msg)
            message = roll.failure_msg.replace("{name}", calling_object.key)
            calling_object.location.msg_contents(message)
            if roll.damage_amt:
                targets = [calling_object]

                # Should we damage others in the room?
                # Note that this will also catch monsters potentially, which is by design.
                if roll.damage_splash:
                    for testobj in calling_object.location.contents:
                        if testobj != calling_object and (testobj.has_player or
                                                          (hasattr(testobj, 'is_character') and testobj.is_character))\
                                and not testobj.check_permstring("builders"):
                            targets.append(testobj)
                    random.shuffle(targets)
                    if len(targets) > 1:
                        targets = targets[:random.randint(1,len(targets) - 1)]
                        if calling_object not in targets:
                            targets.append(calling_object)

                for target in targets:
                    calling_object.location.msg_contents("{} is injured!".format(target.name))

                from typeclasses.scripts.combat.attacks import Attack
                attack = Attack(targets=targets, affect_real_dmg=True, damage=roll.damage_amt,
                                use_mitigation=roll.damage_mit,
                                can_kill=True, private=True, story=roll.damage_reason, inflictor=self)
                try:
                    attack.execute()
                except combat_settings.CombatError as err:
                    inform_staff("{} broke combat failing an obstacle check in a Shardhaven: {}"
                                 .format(calling_object.name, str(err)))
            return False, False, True, False

    def can_pass_with_clue(self, calling_object):

        require_all = self.pass_type == ShardhavenObstacle.HAS_ALL_CLUES

        clue_discoveries = calling_object.roster.clue_discoveries

        for clue in self.clues.all():
            if require_all:
                if clue_discoveries.filter(clue=clue.clue).count() == 0:
                    return False
            else:
                if clue_discoveries.filter(clue=clue.clue).count() > 0:
                    return True

        if not require_all:
            return False

        return True

    def handle_clue_check(self, calling_object, exit_obj, require_all):

        calling_object.msg(self.description + "|/")

        clue_discoveries = calling_object.roster.clue_discoveries

        for clue in self.clues.all():
            if require_all:
                if clue_discoveries.filter(clue=clue.clue).count() == 0:
                    calling_object.msg("You lack the knowledge to pass this obstacle.")

                    if self.rolls.count() > 0:
                        calling_object.msg(self.options_description(exit_obj))
                        return False, False, False, False

                    return False, False, True, False
            else:
                if clue_discoveries.filter(clue=clue.clue).count() > 0:
                    calling_object.msg("Your knowledge of \"{}\" allows you to pass.".format(clue.clue.name))
                    if self.clue_success:
                        message = self.clue_success.replace("{name}", calling_object.key)
                        calling_object.location.msg_contents(message)
                    return True, False, True, False

        if not require_all:
            calling_object.msg("You lack the knowledge to pass this obstacle.")

            if self.rolls.count() > 0:
                calling_object.msg("|/However, you have other options:|/")
                counter = 1
                for roll in self.rolls.all():
                    calling_object.msg("{}: [{}+{}] {}".format(counter, roll.stat, roll.skill, roll.description))
                    counter += 1
                if exit_obj:
                    direction = exit_obj.direction_name
                    calling_object.msg("|/|/Enter the direction followed by the number you choose, such as '{} 1'."
                                       .format(direction))
                else:
                    calling_object.msg("|/|/Call the puzzle command with the number you choose, such as 'puzzle/solve 1'.")
                return False, False, False, False

            return False, False, True, False

        if self.clue_success:
            message = self.clue_success.replace("{name}", calling_object.key)
            calling_object.location.msg_contents(message)

        return True, False, True, False

    def handle_obstacle(self, calling_object, exit_obj, haven_exit, args=None):
        if self.obstacle_type == ShardhavenObstacle.PASS_CHECK:
            return self.handle_dice_check(calling_object, exit_obj, haven_exit, args)
        elif self.obstacle_type == ShardhavenObstacle.HAS_CLUE:
            if len(args) > 0 and self.rolls.count() > 0:
                return self.handle_dice_check(calling_object, exit_obj, haven_exit, args)
            else:
                return self.handle_clue_check(calling_object, exit_obj, False)
        elif self.obstacle_type == ShardhavenObstacle.HAS_ALL_CLUES:
            if len(args) > 0 and self.rolls.count() > 0:
                return self.handle_dice_check(calling_object, exit_obj, args)
            else:
                return self.handle_clue_check(calling_object, exit_obj, True)
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
    damage_splash = models.BooleanField(default=False, verbose_name="Should damage hit others in the party too?")
    damage_reason = models.CharField(blank=True, null=True, max_length=255,
                                     verbose_name="Short description of damage, for the damage system.")
    pass_instantly = models.BooleanField(default=False,
                                         verbose_name="Should a player immediately pass through the exit on success?")


class ShardhavenObstacleClue(SharedMemoryModel):

    obstacle = models.ForeignKey(ShardhavenObstacle, related_name='clues', blank=False, null=False)
    clue = models.ForeignKey('character.Clue', blank=False, null=False)


class ShardhavenPuzzle(SharedMemoryModel):

    name = models.CharField(max_length=40, blank=True, null=True)
    haven_types = models.ManyToManyField('ShardhavenType', related_name='puzzles')
    obstacle = models.ForeignKey(ShardhavenObstacle, blank=False, null=False, related_name='puzzles')
    num_drops = models.PositiveSmallIntegerField(default=1, help_text="How many treasures should this puzzle drop?")
    weight_trinket = models.SmallIntegerField(default=0,
                                              help_text="A weight chance that this puzzle will drop a trinket.")
    weight_weapon = models.SmallIntegerField(default=0,
                                             help_text="A weight chance that this puzzle will drop a weapon.")

    @property
    def display_name(self):
        if self.obstacle.short_desc:
            return self.obstacle.short_desc

        return self.name

    def handle_loot_drop(self, location):
        if location is None:
            return

        haven = None
        if hasattr(location, 'shardhaven'):
            haven = location.shardhaven

        dropped_objects = []

        for loop in range(0, self.num_drops):
            picker = WeightedPicker()
            result = None

            if haven:
                if self.weight_trinket > 0:
                    picker.add_option("trinket", self.weight_trinket)

                if self.weight_weapon > 0:
                    picker.add_option("weapon", self.weight_trinket)

            for loot in self.alchemical_materials.all():
                picker.add_option(loot, loot.weight)

            for crafting_loot in self.crafting_materials.all():
                picker.add_option(crafting_loot, crafting_loot.weight)

            for object_loot in self.object_drops.all():
                if object_loot not in dropped_objects:
                    picker.add_option(object_loot, object_loot.weight)
                    if object_loot.guaranteed:
                        result = object_loot

            if not result:
                result = picker.pick()

            if result:
                final_loot = None
                if isinstance(result, basestring):
                    from .loot import LootGenerator
                    if result == "weapon":
                        final_loot = LootGenerator.create_weapon(haven)
                    elif result == "trinket":
                        final_loot = LootGenerator.create_trinket(haven)
                else:
                    quantity = random.randint(result.minimum_quantity, result.maximum_quantity)

                    if hasattr(result, "object"):
                        dropped_objects.append(result)
                        if result.duplicate:
                            from evennia.objects.models import ObjectDB
                            final_loot = ObjectDB.objects.copy_object(result.object, new_key=result.object.key)
                        else:
                            final_loot = result.object
                    else:
                        final_loot = result.material.create_instance(quantity)
                        if haven:
                            final_loot.db.found_shardhaven = haven.name

                if final_loot is not None:
                    location.msg_contents("The {} dropped {}!".format(self.display_name, final_loot.name))
                    final_loot.location = location


class ShardhavenPuzzleMaterial(SharedMemoryModel):

    puzzle = models.ForeignKey(ShardhavenPuzzle, blank=False, null=False, related_name='alchemical_materials')
    weight = models.SmallIntegerField(default=10, help_text="A weight chance that this puzzle will drop this material.")
    material = models.ForeignKey('magic.AlchemicalMaterial', blank=False, null=False)
    minimum_quantity = models.PositiveSmallIntegerField(default=1)
    maximum_quantity = models.PositiveSmallIntegerField(default=1)


class ShardhavenPuzzleCraftingMaterial(SharedMemoryModel):

    puzzle = models.ForeignKey(ShardhavenPuzzle, blank=False, null=False, related_name='crafting_materials')
    weight = models.SmallIntegerField(default=10, help_text="A weight chance that this puzzle will drop this material.")
    material = models.ForeignKey('dominion.CraftingMaterialType', blank=False, null=False)
    minimum_quantity = models.PositiveSmallIntegerField(default=1)
    maximum_quantity = models.PositiveSmallIntegerField(default=1)


class ShardhavenPuzzleObjectLoot(SharedMemoryModel):

    puzzle = models.ForeignKey(ShardhavenPuzzle, blank=False, null=False, related_name='object_drops')
    weight = models.SmallIntegerField(default=10, help_text="A weight chance that this puzzle will drop this object.")
    object = models.ForeignKey('objects.ObjectDB', blank=False, null=False)
    duplicate = models.BooleanField(default=False, help_text="Do we create a duplicate copy of this object to drop?")
    guaranteed = models.BooleanField(default=False, help_text="Is this object a guaranteed drop?")

    @property
    def minimum_quantity(self):
        return 1

    @property
    def maximum_quantity(self):
        return 1


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
    override = models.BooleanField(default=False)

    modified_diff_by = models.SmallIntegerField(blank=True, null=True)
    modified_diff_reason = models.CharField(max_length=80, blank=True, null=True)
    modified_diff_at = models.DateTimeField(blank=True, null=True)

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

    @property
    def obstacle_name(self):
        if not self.obstacle:
            return None

        return self.obstacle.short_desc or "obstacle"

    def can_see_past(self, character):
        if not self.obstacle:
            return True

        passed = False

        if self.override:
            passed = True
        elif self.obstacle.pass_type != ShardhavenObstacle.EVERY_TIME:
            if character in self.passed_by.all():
                passed = True
            else:
                passed = self.obstacle.obstacle_type == ShardhavenObstacle.ANYONE

        if passed:
            return self.obstacle.peekable_open
        else:
            return self.obstacle.peekable_closed

    def modify_diff(self, amount=None, reason=None):
        if amount:
            self.modified_diff_at = datetime.datetime.now()
            self.modified_diff_by = amount
            self.modified_diff_reason = reason
        else:
            self.modified_diff_at = None
            self.modified_diff_by = None
            self.modified_diff_reason = None
        self.save()

    @property
    def diff_modifier(self):
        if not self.modified_diff_by or not self.modified_diff_at:
            return 0

        delta = datetime.datetime.now() - self.modified_diff_at
        if delta.total_seconds() > 600:
            return 0

        return self.modified_diff_by

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

    name = models.CharField(blank=True, null=True, max_length=30,
                            help_text='A name to use for this square instead of the tile name.')
    description = models.TextField(blank=True, null=True, help_text='A description to use for this square instead of '
                                                                    'the generated one.')

    visitors = models.ManyToManyField('objects.ObjectDB', related_name='+')
    last_visited = models.DateTimeField(blank=True, null=True)

    puzzle = models.ForeignKey(ShardhavenPuzzle, blank=True, null=True, related_name='+')
    puzzle_solved = models.BooleanField(default=False)

    monster = models.ForeignKey(Monster, blank=True, null=True, related_name='+')
    monster_defeated = models.BooleanField(default=False)

    def __str__(self):
        return "{} ({},{})".format(self.layout, self.x_coord, self.y_coord)

    def __repr__(self):
        return str(self)

    def __unicode__(self):
        return unicode(str(self))

    def visit(self, character):
        if character not in self.visitors.all():
            self.visitors.add(character)

    def mark_emptied(self):
        self.last_visited = datetime.datetime.now()

    def has_visited(self, character):
        return character in self.visitors.all()

    @property
    def visited_recently(self):
        if not self.last_visited:
            return False

        now = datetime.datetime.now()
        delta = now - self.last_visited
        return delta.total_seconds() < 86400

    def create_room(self):
        if self.room:
            return self.room

        namestring = "|yOutside Arx - "
        namestring += self.layout.haven.name + " - "
        namestring += self.name or self.tile.name + "|n"

        room = create.create_object(typeclass='world.exploration.rooms.ShardhavenRoom',
                                    key=namestring)
        room.db.haven_id = self.layout.haven.id
        room.db.haven_square_id = self.id

        if self.description:
            final_description = self.description
        else:
            final_description = self.tile.description

        fragments = ShardhavenMoodFragment.objects.filter(shardhaven_type=self.layout.haven_type,
                                                          taint_level__lte=self.layout.haven.taint_level)
        fragments = [fragment.text for fragment in fragments]
        random.shuffle(fragments)

        while "{}" in final_description:
            final_description = final_description.replace("{}", fragments.pop(), 1)

        room.db.raw_desc = final_description
        room.db.desc = final_description

        from exploration_commands import CmdExplorationRoomCommands
        room.cmdset.add(CmdExplorationRoomCommands())

        self.room = room
        self.save()
        return room

    def destroy_room(self):
        if self.room:
            self.room.softdelete()
            self.room = None
            self.save()


class ShardhavenLayout(SharedMemoryModel):

    width = models.PositiveSmallIntegerField(default=5)
    height = models.PositiveSmallIntegerField(default=4)
    haven = models.OneToOneField(Shardhaven, related_name='layout', null=True, blank=True)
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

    @property
    def entrance(self):
        if not self.matrix:
            self.cache_room_matrix()

        return self.matrix[self.entrance_x][self.entrance_y]

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

    def delete_square(self, grid_x, grid_y):
        self.cache_room_matrix()
        room = self.matrix[grid_x][grid_y]
        if room:
            # Delete this room, and any exits leading to it.
            if room.exit_north.count():
                for room_exit in room.exit_north.all():
                    room_exit.delete()
            if room.exit_south.count():
                for room_exit in room.exit_south.all():
                    room_exit.delete()
            if room.exit_east.count():
                for room_exit in room.exit_east.all():
                    room_exit.delete()
            if room.exit_west.count():
                for room_exit in room.exit_west.all():
                    room_exit.delete()
            room.delete()
            self.cache_room_matrix()
            return True
        else:
            return False

    def create_square(self, grid_x, grid_y):
        self.cache_room_matrix()
        room = self.matrix[grid_x][grid_y]
        if not room:
            from world.dominion.models import PlotRoom
            plotrooms = list(PlotRoom.objects.filter(shardhaven_type=self.haven_type))
            room = ShardhavenLayoutSquare(layout=self, tile=random.choice(plotrooms), x_coord=grid_x, y_coord=grid_y)
            room.save()

            west = self.matrix[grid_x - 1][grid_y]
            east = self.matrix[grid_x + 1][grid_y]
            north = self.matrix[grid_x][grid_y - 1]
            south = self.matrix[grid_x][grid_y + 1]

            # Why do our related-fields not populate properly?
            # Aaargh.
            if west and not ShardhavenLayoutExit.objects.filter(room_east=room).count():
                room_exit = ShardhavenLayoutExit(layout=self)
                room_exit.room_east = room
                room_exit.room_west = west
                room_exit.save()
            if east and not ShardhavenLayoutExit.objects.filter(room_west=room).count():
                room_exit = ShardhavenLayoutExit(layout=self)
                room_exit.room_east = east
                room_exit.room_west = room
                room_exit.save()
            if north and not ShardhavenLayoutExit.objects.filter(room_south=room).count():
                room_exit = ShardhavenLayoutExit(layout=self)
                room_exit.room_north = north
                room_exit.room_south = room
                room_exit.save()
            if south and not ShardhavenLayoutExit.objects.filter(room_north=room).count():
                room_exit = ShardhavenLayoutExit(layout=self)
                room_exit.room_north = room
                room_exit.room_south = south
                room_exit.save()

            self.save()
            self.cache_room_matrix()
            return True
        else:
            return False

    @property
    def ascii(self):
        self.cache_room_matrix()
        string = ""
        for y in range(self.height):
            for x in range(self.width):
                if x == self.entrance_x and y == self.entrance_y:
                    string += "|w$|n"
                elif self.matrix[x][y] is None:
                    string += "|[B|B#|n"
                else:
                    string += " "
            string += "|n\n"

        return string

    def map_for(self, player):
        self.cache_room_matrix()
        string = ""
        for y in range(self.height):
            for x in range(self.width):
                if x == self.entrance_x and y == self.entrance_y:
                    string += "|w$|n"
                elif self.matrix[x][y] is None:
                    string += "|[B|B#|n"
                elif self.matrix[x][y].has_visited(player):
                    if self.matrix[x][y].room == player.location:
                        string += "|w*|n"
                    else:
                        string += " "
                else:
                    string += "|[B|B#|n"

            string += "|n\n"

        return string

    def instanciate(self):
        for room in self.rooms.all():
            room.create_room()
        for room_exit in self.exits.all():
            room_exit.create_exits()

        self.cache_room_matrix()
        return self.matrix[self.entrance_x][self.entrance_y].room

    def reset(self):
        for room_exit in self.exits.all():
            room_exit.passed_by.clear()
            room_exit.override = False
            room_exit.save()

        for room in self.rooms.all():
            room.visitors.clear()
            room.monster_defeated = False
            room.puzzle_solved = False
            room.last_visited = None
            room.save()
            if room.room and room.room.is_typeclass('world.exploration.rooms.ShardhavenRoom'):
                room.room.reset()

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

        x = 0
        y = 0
        while layout.matrix[x][y] is None:
            x = random.randint(0, width - 1)
            y = random.randint(0, height - 1)

        layout.entrance_x = x
        layout.entrance_y = y

        obstacles = list(ShardhavenObstacle.objects.filter(haven_types__pk=layout.haven_type.id,
                                                           obstacle_class=ShardhavenObstacle.EXIT_OBSTACLE).all())
        base_obstacles = list(obstacles)
        random.shuffle(obstacles)
        target_difficulty = 30 + max(layout.haven.difficulty_rating * 2, 5)

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

                        if random.randint(1,100) < target_difficulty:
                            if len(obstacles) == 0:
                                obstacles = list(base_obstacles)
                                random.shuffle(obstacles)

                            obstacle = obstacles.pop()
                            room_exit.obstacle = obstacle

                        room_exit.save()
                    if east and not ShardhavenLayoutExit.objects.filter(room_west=room).count():
                        room_exit = ShardhavenLayoutExit(layout=layout)
                        room_exit.room_east = east
                        room_exit.room_west = room

                        if random.randint(1, 100) < target_difficulty:
                            if len(obstacles) == 0:
                                obstacles = list(base_obstacles)
                                random.shuffle(obstacles)

                            obstacle = obstacles.pop()
                            room_exit.obstacle = obstacle

                        room_exit.save()
                    if north and not ShardhavenLayoutExit.objects.filter(room_south=room).count():
                        room_exit = ShardhavenLayoutExit(layout=layout)
                        room_exit.room_north = north
                        room_exit.room_south = room

                        if random.randint(1, 100) < target_difficulty:
                            if len(obstacles) == 0:
                                obstacles = list(base_obstacles)
                                random.shuffle(obstacles)

                            obstacle = obstacles.pop()
                            room_exit.obstacle = obstacle

                        room_exit.save()
                    if south and not ShardhavenLayoutExit.objects.filter(room_north=room).count():
                        room_exit = ShardhavenLayoutExit(layout=layout)
                        room_exit.room_north = room
                        room_exit.room_south = south

                        if random.randint(1, 100) < target_difficulty:
                            if len(obstacles) == 0:
                                obstacles = list(base_obstacles)
                                random.shuffle(obstacles)

                            obstacle = obstacles.pop()
                            room_exit.obstacle = obstacle

                        room_exit.save()

        layout.save()

        return layout
