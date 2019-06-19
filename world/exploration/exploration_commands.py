from commands.base import ArxCommand
from . import builder
from .loot import LootGenerator
from models import Shardhaven, ShardhavenLayout, GeneratedLootFragment, Monster
from evennia.commands.cmdset import CmdSet
from evennia.utils import create
from server.conf import settings
from world.stats_and_skills import do_dice_check
import random
import time


class CmdTestMonsterBuild(ArxCommand):
    """
    This command will spawn in test monsters from the
    shardhaven tables.

    Usage:
      @mh_testbuild/spawn <monster ID>
    """

    key = "@mh_testbuild"
    locks = "cmd:perm(Admins)"

    def func(self):
        if "spawn" in self.switches:

            try:
                monster_id = int(self.lhs)
                monster = Monster.objects.get(id=monster_id)
            except ValueError:
                self.msg("You need to provide an integer value!")
                return
            except (Monster.DoesNotExist, Monster.MultipleObjectsReturned):
                self.msg("That doesn't appear to be a valid monster!")
                return

            mob = monster.create_instance(self.caller.location)
            self.msg("Spawned in " + mob.name)
            return

        self.msg("Pick a valid switch!")


class CmdTestShardhavenBuild(ArxCommand):
    """
    This command will build and print a test maze for a
    Shardhaven.

    Usage:
      @sh_testbuild/maze [width,height]
      @sh_testbuild/layout <shardhaven ID>
      @sh_testbuild/showlayout <shardhaven ID>
      @sh_testbuild/instanciate <shardhaven ID>
      @sh_testbuild/entrance <shardhaven ID>
      @sh_testbuild/reset <shardhaven ID>
      @sh_testbuild/destroy <shardhaven ID>
    """

    key = "@sh_testbuild"
    locks = "cmd:perm(Wizards)"

    def func(self):
        if "maze" in self.switches:
            x_dim = int(self.lhslist[0]) if len(self.lhslist) == 2 else 9
            y_dim = int(self.lhslist[1]) if len(self.lhslist) == 2 else 9

            maze = builder.Builder(x_dim=x_dim, y_dim=y_dim)

            maze.build()
            self.msg(str(maze))
            return

        if "layout" in self.switches:

            try:
                haven = Shardhaven.objects.get(id=int(self.lhs))
            except ValueError:
                self.msg("You need to provide an integer ID!")
                return
            except (Shardhaven.DoesNotExist, Shardhaven.MultipleObjectsReturned):
                self.msg("That doesn't appear to be an ID matching a Shardhaven!")
                return

            layouts = ShardhavenLayout.objects.filter(haven=haven)
            if layouts.count() > 0:
                self.msg("That shardhaven already has a layout generated!")
                return

            self.msg("Generating layout for " + str(haven))

            x_dim = int(self.rhslist[0]) if len(self.rhslist) == 2 else 9
            y_dim = int(self.rhslist[1]) if len(self.rhslist) == 2 else 9

            layout = ShardhavenLayout.new_haven(haven, x_dim, y_dim)
            self.msg("Layout generated!")
            self.msg(layout.ascii)

            return

        if "showlayout" in self.switches:

            try:
                haven = Shardhaven.objects.get(id=int(self.args))
            except ValueError:
                self.msg("You need to provide an integer ID!")
                return
            except (Shardhaven.DoesNotExist, Shardhaven.MultipleObjectsReturned):
                self.msg("That doesn't appear to be an ID matching a Shardhaven!")
                return

            layouts = ShardhavenLayout.objects.filter(haven=haven)
            if layouts.count() == 0:
                self.msg("That shardhaven doesn't appear to have a layout!")
                return

            self.msg("Layout for {}".format(haven.name))
            self.msg(layouts[0].ascii)
            return

        if "instanciate" in self.switches:
            try:
                haven = Shardhaven.objects.get(id=int(self.args))
            except ValueError:
                self.msg("You need to provide an integer ID!")
                return
            except (Shardhaven.DoesNotExist, Shardhaven.MultipleObjectsReturned):
                self.msg("That doesn't appear to be an ID matching a Shardhaven!")
                return

            layouts = ShardhavenLayout.objects.filter(haven=haven)
            if layouts.count() == 0:
                self.msg("That shardhaven doesn't appear to have a layout!")
                return
            layout = layouts[0]

            self.msg("Instanciating " + str(layout))
            room = layout.instanciate()
            from typeclasses.rooms import ArxRoom
            try:
                city_center = ArxRoom.objects.get(id=13)
                create.create_object(settings.BASE_EXIT_TYPECLASS,
                                     key="Back to Arx <Arx>",
                                     location=room,
                                     aliases=["arx", "back to arx", "out"],
                                     destination=city_center)
            except ArxRoom.DoesNotExist:
                pass

            self.msg("Done. The entrance is at #" + str(room.id))
            return

        if "entrance" in self.switches:

            try:
                haven = Shardhaven.objects.get(id=int(self.args))
            except ValueError:
                self.msg("You need to provide an integer ID!")
                return
            except (Shardhaven.DoesNotExist, Shardhaven.MultipleObjectsReturned):
                self.msg("That doesn't appear to be an ID matching a Shardhaven!")
                return

            layouts = ShardhavenLayout.objects.filter(haven=haven)
            if layouts.count() == 0:
                self.msg("That shardhaven doesn't appear to have a layout!")
                return
            layout = layouts[0]

            if haven.entrance.room:
                self.msg("The entrance to {} is #{}.".format(haven.name, haven.entrance.room.id))
            else:
                self.msg("{} is not presently instanciated.".format(haven.name))
            return

        if "reset" in self.switches:

            try:
                haven = Shardhaven.objects.get(id=int(self.args))
            except ValueError:
                self.msg("You need to provide an integer ID!")
                return
            except (Shardhaven.DoesNotExist, Shardhaven.MultipleObjectsReturned):
                self.msg("That doesn't appear to be an ID matching a Shardhaven!")
                return

            layouts = ShardhavenLayout.objects.filter(haven=haven)
            if layouts.count() == 0:
                self.msg("That shardhaven doesn't appear to have a layout!")
                return
            layout = layouts[0]

            self.msg("Resetting layout for " + layout.haven.name + ".")
            layout.reset()
            self.msg("Done.")
            return

        if "destroy" in self.switches:
            try:
                haven = Shardhaven.objects.get(id=int(self.args))
            except ValueError:
                self.msg("You need to provide an integer ID!")
                return
            except (Shardhaven.DoesNotExist, Shardhaven.MultipleObjectsReturned):
                self.msg("That doesn't appear to be an ID matching a Shardhaven!")
                return

            layouts = ShardhavenLayout.objects.filter(haven=haven)
            if layouts.count() == 0:
                self.msg("That shardhaven doesn't appear to have a layout!")
                return
            layout = layouts[0]

            self.msg("Destroying " + str(layout) + " instance.")
            layout.destroy_instanciation()
            return

        self.msg("Provide a valid switch!")
        return


class CmdTestLoot(ArxCommand):
    """
    This command tests the generated loot functionality.

    Usage:
        @gl_testbuild/weaponname [small||medium||huge||bow]
        @gl_testbuild/trinketname
        @gl_testbuild/weapon <shardhaven ID>
        @gl_testbuild/trinket <shardhaven ID>
    """

    key = "@gl_testbuild"
    locks = "cmd:perm(Admins)"

    def func(self):

        if "weaponname" in self.switches:
            weapon_materials = (
                'steel',
                'rubicund',
                'diamondplate',
                'alaricite'
            )

            size = GeneratedLootFragment.MEDIUM_WEAPON_TYPE

            if self.args == "small":
                size = GeneratedLootFragment.SMALL_WEAPON_TYPE
            elif self.args == "huge":
                size = GeneratedLootFragment.HUGE_WEAPON_TYPE
            elif self.args == "bow":
                size = GeneratedLootFragment.BOW_WEAPON_TYPE

            material = random.choice(weapon_materials)
            should_name = material in ['diamondplate', 'alaricite']

            name = GeneratedLootFragment.generate_weapon_name(material, wpn_type=size, include_name=should_name)
            self.msg("Generated a weapon: {}".format(name))
            return

        if "trinketname" in self.switches:

            name = GeneratedLootFragment.generate_trinket_name()
            self.msg("Generated a trinket: {}".format(name))
            return

        if "trinket" in self.switches:

            try:
                haven = Shardhaven.objects.get(pk=int(self.args))
            except (ValueError, Shardhaven.DoesNotExist):
                self.msg("Something went horribly wrong.")
                return

            trinket = LootGenerator.create_trinket(haven)
            trinket.location = self.caller.location
            self.msg("Created %s" % trinket.name)
            return

        if "weapon" in self.switches:

            weapon_types = (
                LootGenerator.WPN_SMALL,
                LootGenerator.WPN_MEDIUM,
                LootGenerator.WPN_HUGE,
                LootGenerator.WPN_BOW
            )
            weapon_type = random.choice(weapon_types)

            try:
                haven = Shardhaven.objects.get(pk=int(self.args))
            except (ValueError, Shardhaven.DoesNotExist):
                self.msg("Something went horribly wrong.")
                return

            weapon = LootGenerator.create_weapon(haven, wpn_type=weapon_type)
            weapon.location = self.caller.location
            self.msg("Created %s" % weapon.name)
            return

        self.msg("Unknown option!")


class CmdExplorationCmdSet(CmdSet):

    def at_cmdset_creation(self):
        self.add(CmdTestMonsterBuild())
        self.add(CmdTestShardhavenBuild())
        self.add(CmdTestLoot())


class CmdExplorationHome(ArxCommand):
    """
    Sends you home.

    Usage:
        home

    But this command is unavailable while you're in a shardhaven!
    """

    key = "home"
    locks = "cmd:all()"
    help_category = "Shardhavens"

    def func(self):
        self.caller.msg("|/|wYou are far from home, and do not know the way back!|n")
        self.caller.msg("(You cannot use the 'home' command while in a shardhaven.)|/")


class CmdExplorationMap(ArxCommand):
    """
    Show an automatically-generated map.

    Usage:
      map

    While in a shardhaven, your character will cleverly keep a map of where
    they've been (and where the entrance was), which you can access through
    the 'map' command.
    """

    key = "map"
    locks = "cmd:all()"
    help_category = "Shardhavens"

    def func(self):
        if not hasattr(self.caller.location, "shardhaven"):
            self.msg("You aren't in a shardhaven!  How did this happen?")
            return

        haven = self.caller.location.shardhaven
        if not haven:
            self.msg("You aren't in a shardhaven!  How did this happen?")
            return

        header = "|/{}'s map of {}|/".format(self.caller.name, haven.name).upper()
        self.msg(header)
        map_desc = haven.layout.map_for(self.caller)
        self.msg(map_desc)
        self.msg("|/Key:|/  |w*|n - Your location|/  |w$|n - Entrance|/")


class CmdExplorationSneak(ArxCommand):
    """
    Attempts to move quietly in a direction.

    Usage:
      sneak <exit>

    In a shardhaven, sometimes you want to move quietly! This command will
    attempt to do so, in hopes that monsters will not hear you and be
    attracted to your location. However, if you fail, you might make more
    noise than you intend and attract the attention of monsters you didn't
    want.

    You also cannot sneak through exits that are blocked by an obstacle.
    """

    key = "sneak"
    locks = "cmd:all()"
    help_category = "Shardhavens"

    def func(self):
        if not self.args:
            self.msg("You must provide a direction to sneak!")
            return

        exit_objs = self.caller.search(self.args, quiet=True, global_search=False,
                                       typeclass='typeclasses.exits.ShardhavenInstanceExit')
        if not exit_objs or len(exit_objs) == 0:
            self.msg("There doesn't appear to be a shardhaven exit by that name!")
            return

        if len(exit_objs) > 1:
            self.msg("That matches too many exits!")
            return

        exit_obj = exit_objs[0]

        if not exit_obj.passable(self.caller):
            self.msg("You cannot sneak that way; there's still an obstacle there you have to pass!")
            return

        roll = do_dice_check(self.caller, "dexterity", "stealth", 25, quiet=False)
        if roll < 0:
            self.caller.location.msg_contents("%s attempts to sneak %s, but makes noise as they do so!"
                                              % (self.caller.name, exit_obj.direction_name))
        elif roll > 1:
            self.caller.location.msg_contents("%s moves stealthily through %s."
                                              % (self.caller.name, exit_obj.direction_name))

        self.caller.ndb.shardhaven_sneak_value = roll
        self.caller.execute_cmd(exit_obj.direction_name)


class CmdExplorationAssist(ArxCommand):
    """
    Temporarily alter the difficulty of an obstacle.

    Usage:
      assist <direction>

    This command can only be used once every 30 minutes, but will allow
    a player to make a wits+leadership roll in order to adjust the difficulty
    of an obstacle's rolls for 10 minutes.  If you succeed on your roll, your
    leadership and cleverness will lower the difficulty and your party will
    have an easier time passing the obstacle.  If you fail, however, your
    advice is bad and it will make things more difficult.
    """

    key = "assist"
    locks = "cmd:all()"
    help_category = "Shardhavens"

    def func(self):
        if not self.args:
            self.msg("You must provide a direction to assist the party with!")
            return

        last_assist = self.caller.db.shardhaven_last_assist
        if last_assist and time.time() - last_assist < 1800:
            self.msg("You cannot assist through a direction again yet.")
            return

        exit_objs = self.caller.search(self.args, quiet=True, global_search=False,
                                       typeclass='typeclasses.exits.ShardhavenInstanceExit')
        if not exit_objs or len(exit_objs) == 0:
            self.msg("There doesn't appear to be a shardhaven exit by that name!")
            return

        if len(exit_objs) > 1:
            self.msg("That matches too many exits!")
            return

        exit_obj = exit_objs[0]
        haven_exit = exit_obj.haven_exit
        if not haven_exit:
            self.msg("Something is horribly wrong with that exit; it's not set up as a Shardhaven exit.")
            return

        if not haven_exit.obstacle:
            self.msg("There's no obstacle in that direction to assist with!")
            return

        self.caller.db.shardhaven_last_assist = time.time()
        roll = do_dice_check(self.caller, "wits", "leadership", 30, quiet=False)
        haven_exit.modify_diff(amount=roll / 2, reason="%s assisted with a leadership roll" % self.caller.name)
        self.caller.location.msg_contents("%s attempts to assist the party with the obstacle to the %s, "
                                          "adjusting the difficulty." % (self.caller.name, exit_obj.direction_name))


class CmdExplorationPuzzle(ArxCommand):
    """
    Gets information on -- or solves -- a puzzle in a Shardhaven room.

    Usage:
      puzzle
      puzzle/solve
      puzzle/solve <choice>

    The first form of this command will show information on the puzzle -- if any --
    in the current room.  The second form will attempt to solve the puzzle with
    a clue, if you have one that applies.  The third one will attempt to solve
    the puzzle with one of the roll options.
    """

    key = "puzzle"
    locks = "cmd:all()"

    def shardhaven_room(self):
        if not hasattr(self.caller.location, "shardhaven_room"):
            return None

        haven_room = self.caller.location.shardhaven_room
        return haven_room

    def puzzle_for_room(self):
        haven_room = self.shardhaven_room()
        if haven_room and haven_room.puzzle and not haven_room.puzzle_solved:
            return haven_room.puzzle

        return None

    def can_attempt(self):
        attempts = self.caller.location.db.puzzle_attempts
        if not attempts:
            return True

        if self.caller.id not in attempts:
            return True

        timestamp = attempts[self.caller.id]
        delta = time.time() - timestamp
        if delta < 180:
            from math import trunc
            self.msg("You can't attempt to solve this puzzle for {} seconds.".format(trunc(180 - delta)))
            return False

        return True

    def func(self):

        puzzle = self.puzzle_for_room()
        if not puzzle:
            self.msg("There is no puzzle here to solve!")
            return

        if "solve" in self.switches:

            if self.caller.location.ndb.combat_manager:
                cscript = self.caller.location.ndb.combat_manager
                if cscript.ndb.combatants:
                    if cscript.check_character_is_combatant(self.caller):
                        self.msg("You're in combat, and cannot attempt to solve this puzzle right now!")
                        return False

            if not self.can_attempt():
                return

            result, override_obstacle, attempted, instant = \
                puzzle.obstacle.handle_obstacle(self.caller, None, None, args=self.args)
            if result:
                puzzle.handle_loot_drop(self.caller.location)
                haven_room = self.shardhaven_room()
                haven_room.puzzle_solved = True
                haven_room.save()
            elif attempted:
                attempts = self.caller.location.db.puzzle_attempts or {}
                attempts[self.caller.id] = time.time()
                self.caller.location.db.puzzle_attempts = attempts
            return

        self.msg("|/" + puzzle.obstacle.description + "|/" + puzzle.obstacle.options_description(None) + "|/")


class CmdExplorationRoomCommands(CmdSet):

    # We want to override the CharacterCmdSet's 'home' command.
    priority = 200

    def at_cmdset_creation(self):
        self.add(CmdExplorationHome())
        self.add(CmdExplorationMap())
        self.add(CmdExplorationSneak())
        self.add(CmdExplorationAssist())
        self.add(CmdExplorationPuzzle())
