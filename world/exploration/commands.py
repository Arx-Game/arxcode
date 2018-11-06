from server.utils.arx_utils import ArxCommand
from . import builder
from models import Shardhaven, ShardhavenLayout
from evennia.commands.cmdset import CmdSet


class CmdTestShardhavenBuild(ArxCommand):
    """
    This command will build and print a test maze for a
    Shardhaven.

    Usage:
      @sh_testbuild/maze [width,height]
      @sh_testbuild/layout <shardhaven ID>
      @sh_testbuild/instanciate <shardhaven layout ID>
      @sh_testbuild/destroy <shardhaven layout ID>
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
                haven = Shardhaven.objects.get(id=int(self.args))
            except ValueError:
                self.msg("You need to provide an integer ID!")
                return
            except Shardhaven.DoesNotExist, Shardhaven.MultipleObjectsReturned:
                self.msg("That doesn't appear to be an ID matching a Shardhaven!")
                return

            self.msg("Generating layout for " + str(haven))

            layout = ShardhavenLayout.new_haven(haven, 9, 9)
            self.msg("Layout generated!")
            self.msg(layout.ascii)

            return

        if "instanciate" in self.switches:
            try:
                layout = ShardhavenLayout.objects.get(id=int(self.args))
            except ValueError:
                self.msg("You need to provide an integer ID")
                return
            except ShardhavenLayout.DoesNotExist, ShardhavenLayout.MultipleObjectsReturned:
                self.msg("That doesn't appear to be an ID matching a valid shardhaven layout!")
                return

            self.msg("Instanciating " + str(layout))
            room_id = layout.instanciate()
            self.msg("The entrance is at #" + str(room_id))
            return

        if "destroy" in self.switches:
            try:
                layout = ShardhavenLayout.objects.get(id=int(self.args))
            except ValueError:
                self.msg("You need to provide an integer ID")
                return
            except ShardhavenLayout.DoesNotExist, ShardhavenLayout.MultipleObjectsReturned:
                self.msg("That doesn't appear to be an ID matching a valid shardhaven layout!")
                return

            self.msg("Destroying " + str(layout) + " instance.")
            layout.destroy_instanciation()
            return

        self.msg("Provide a valid switch!")
        return


class CmdExplorationCmdSet(CmdSet):

    def at_cmdset_creation(self):
        self.add(CmdTestShardhavenBuild())