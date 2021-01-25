"""
Container objects. Bags, chests, etc.


"""
from typeclasses.objects import Object as DefaultObject
from commands.base import ArxCommand
from evennia.commands import cmdset
from typeclasses.mixins import LockMixins


# noinspection PyUnresolvedReferences
class CmdChestKey(ArxCommand):
    """
    Grants a key to this chest to a player

    Usage:
        @chestkey <player>
        @chestkey/rmkey <player>

    Grants or removes keys to containers to a player.
    """

    key = "@chestkey"
    locks = "cmd:all()"
    help_category = "containers"

    def func(self):
        """
        self.obj  #  type: Container
        :return:
        """
        caller = self.caller
        chestkeys = caller.db.chestkeylist or []
        if (
            caller != self.obj.craft_handler.crafted_by
            and not caller.check_permstring("builders")
            and self.obj not in chestkeys
        ):
            caller.msg("You cannot grant keys to %s." % self)
            return
        if not self.args:
            caller.msg("Grant a key to whom?")
            return
        player = caller.player.search(self.args)
        if not player:
            return
        char = player.char_ob
        if not char:
            return
        if not self.switches:
            if not self.obj.grantkey(char):
                caller.msg("They already have a key.")
                return
            caller.msg("%s has been granted a key to %s." % (char, self.obj))
            return
        if "rmkey" in self.switches:
            if not self.obj.rmkey(char):
                caller.msg("They don't have a key.")
                return
            caller.msg("%s has had their key to %s removed." % (char, self.obj))
            return
        caller.msg("Invalid switch.")
        return


class CmdRoot(ArxCommand):
    """
    Makes a container object immovable or removes the immovable
    quality of the container object.

    Usage:
        +root <container>
        +unroot <container>
    """

    key = "root"
    aliases = ["+root", "+unroot"]
    locks = "cmd:all()"

    def func(self):
        caller = self.caller

        loc = caller.location

        if caller not in loc.decorators:
            caller.msg("You must be a decorator in order to use this command")
            return

        verb = self.cmdstring.lstrip("+")

        obj = loc.search(self.args, location=loc)

        if not obj:
            caller.msg("That object does not exist.")
            return

        if not obj.db.container:
            caller.msg("Can only target containers!")
            return

        if verb == "unroot":
            if not obj.tags.get("rooted"):
                caller.msg("You cannot unroot %s. It is not rooted" % obj)
                return

            obj.locks.remove("get")
            obj.tags.remove("rooted")
            obj.locks.add("get:all()")

            caller.msg("Successfully unrooted %s." % obj)

        if verb == "root":
            if obj.tags.get("rooted"):
                caller.msg("You cannot root %s. It is already rooted." % obj)
                return

            obj.locks.remove("get")
            obj.tags.add("rooted")
            obj.locks.add("get:perm(Builders) or decorators()")

            caller.msg("Successfully rooted %s." % obj)

        return


# noinspection PyTypeChecker
class Container(LockMixins, DefaultObject):
    """
    Containers - bags, chests, etc. Players can have keys and can
    lock/unlock containers.
    """

    # noinspection PyMethodMayBeStatic
    def create_container_cmdset(self, contdbobj):
        """
        Helper function for creating an container command set + command.

        The command of this cmdset has the same name as the container object
        and allows the container to react when the player enter the container's name,
        triggering the movement between rooms.

        Note that containerdbobj is an ObjectDB instance. This is necessary
        for handling reloads and avoid tracebacks if this is called while
        the typeclass system is rebooting.
        """

        # create a cmdset
        container_cmdset = cmdset.CmdSet(None)
        container_cmdset.key = "_containerset"
        container_cmdset.priority = 9
        container_cmdset.duplicates = True
        # add command to cmdset
        container_cmdset.add(CmdChestKey(obj=contdbobj))
        return container_cmdset

    def at_cmdset_get(self, **kwargs):
        """
        Called when the cmdset is requested from this object, just before the
        cmdset is actually extracted. If no container-cmdset is cached, create
        it now.
        """
        if self.ndb.container_reset or not self.cmdset.has_cmdset(
            "_containerset", must_be_default=True
        ):
            # we are resetting, or no container-cmdset was set. Create one dynamically.
            self.cmdset.add_default(self.create_container_cmdset(self), permanent=False)
            self.ndb.container_reset = False

    def at_after_move(self, source_location):
        if self.tags.get("rooted"):
            self.locks.remove("get")
            self.tags.remove("rooted")
            self.locks.add("get:all()")

    def at_object_creation(self):
        """Called once, when object is first created (after basetype_setup)."""
        self.locks.add("usekey: chestkey(%s)" % self.id)
        self.db.container = True
        self.db.max_volume = 1
        self.at_init()

    def grantkey(self, char):
        """Grants a key to this chest for char."""
        chestkeys = char.db.chestkeylist or []
        if self in chestkeys:
            return False
        chestkeys.append(self)
        char.db.chestkeylist = chestkeys
        return True

    def rmkey(self, char):
        """Removes a key to this chest from char."""
        chestkeys = char.db.chestkeylist or []
        if self not in chestkeys:
            return
        chestkeys.remove(self)
        char.db.chestkeylist = chestkeys
        return True

    def return_contents(
        self,
        pobject,
        detailed=True,
        show_ids=False,
        strip_ansi=False,
        show_places=True,
        sep=", ",
    ):
        if self.tags.get("display_by_line"):
            return super(Container, self).return_contents(
                pobject, detailed, show_ids, strip_ansi, show_places, sep="\n         "
            )
        return super(Container, self).return_contents(
            pobject, detailed, show_ids, strip_ansi, show_places, sep
        )
