from commands.base import ArxCommand
from . import builder
from .loot import LootGenerator
from models import Shardhaven, ShardhavenLayout, GeneratedLootFragment, Monster
from evennia.commands.cmdset import CmdSet
from evennia.utils import create
from server.conf import settings
import random


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
            except Monster.DoesNotExist, Monster.MultipleObjectsReturned:
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

            self.msg("The entrance to {} is #{}.".format(haven.name, haven.entrance.room.id))
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

    This command is unavailable while you're in a shardhaven!
    """

    key = "home"
    locks = "cmd:all()"

    def func(self):
        self.caller.msg("|/|wYou are far from home, and do not know the way back!|n")
        self.caller.msg("(You cannot use the 'home' command while in a shardhaven.)|/")


class CmdExplorationMap(ArxCommand):

    key = "map"
    locks = "cmd:all()"

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
        map = haven.layout.map_for(self.caller)
        self.msg(map)
        self.msg("|/Key:|/  |w*|n - Your location|/  |w$|n - Entrance|/")


class CmdExplorationRoomCommands(CmdSet):

    # We want to override the CharacterCmdSet's 'home' command.
    priority = 200

    def at_cmdset_creation(self):
        self.add(CmdExplorationHome)
        self.add(CmdExplorationMap)
