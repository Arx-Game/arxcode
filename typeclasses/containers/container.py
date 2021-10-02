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
        if (
            caller != self.obj.item_data.crafted_by
            and not caller.check_permstring("builders")
            and not caller.item_data.has_key_by_id(self.obj.id)
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
            if not self.obj.grant_key(char):
                caller.msg("They already have a key.")
                return
            caller.msg("%s has been granted a key to %s." % (char, self.obj))
            return
        if "rmkey" in self.switches:
            if not self.obj.revoke_key(char):
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

        if not obj.is_container:
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

    default_capacity = 1

    @property
    def is_container(self):
        return True

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
        self.item_data.capacity = 1
        self.at_init()

    def grant_key(self, char):
        """Grants a key to this chest for char."""
        try:
            return char.item_data.add_chest_key(self)
        except AttributeError:
            return False

    def revoke_key(self, char):
        """Removes a key to this chest from char."""
        try:
            return char.item_data.remove_key(self)
        except AttributeError:
            return False

    def return_contents(
        self,
        pobject,
        detailed=True,
        show_ids=False,
        strip_ansi=False,
        show_places=True,
        sep=", ",
    ):
        if self.display_by_line:
            return super(Container, self).return_contents(
                pobject, detailed, show_ids, strip_ansi, show_places, sep="\n         "
            )
        return super(Container, self).return_contents(
            pobject, detailed, show_ids, strip_ansi, show_places, sep
        )

    @property
    def displayable(self):
        if self.item_data.recipe:
            return self.item_data.recipe.displayable or super().displayable
        return super().displayable

    @property
    def display_by_line(self):
        if self.tags.get("display_by_line"):
            return True
        if self.item_data.recipe:
            return self.item_data.recipe.display_by_line
        return False
