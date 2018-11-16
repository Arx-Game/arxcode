"""
Comsystem command module.

Comm commands are OOC commands and intended to be made available to
the Player at all times (they go into the PlayerCmdSet). So we
make sure to homogenize self.caller to always be the player object
for easy handling.

"""
from evennia.utils import create
from commands.base import ArxCommand
from evennia.objects.models import ObjectDB

MAP_TYPECLASS = "typeclasses.map.Map"



class CmdMap(ArxCommand):
    """
    @map - look at a map of area, if available

    Usage:
       @map

    Brings up a map of the area, if it's available.
    """

    key = "@map"
    aliases = ["+map", "map"]
    help_category = "Travel"
    locks = "cmd:all()"

    def func(self):
        "Implement the command"
        caller = self.caller
        room = caller.location
        map = room.db.map
        if not map:
            caller.msg("There is no map available at your current location.")
            return
        caller.msg("Map of {c%s{n." % map.key)
        from typeclasses.map import _CALLER_ICON
        caller.msg("Your location displayed as %s." % _CALLER_ICON)
        directions = caller.ndb.waypoint
        caller.msg(map.draw_map(room, destination=directions))



class CmdMapCreate(ArxCommand):
    """
    @mapcreate
    Usage:
     @mapcreate <mapname>

    Creates a new map.
    """

    key = "@mapcreate"
    locks = "cmd:perm(Wizards)"
    help_category = "Travel"

    def func(self):
        "Implement the command"

        caller = self.caller
        typeclass = MAP_TYPECLASS
        if not self.args:
            maps = ObjectDB.objects.filter(db_typeclass_path=typeclass)
            caller.msg("Maps: %s" % ", ".join(map.key for map in maps))
            return

        try:
            name = self.lhs

        except (ValueError, KeyError, AttributeError):
            caller.msg("Usage @mapcreate <mapname>")
            return     
        
        if ObjectDB.objects.filter(db_typeclass_path=typeclass, db_key__iexact=name):
            caller.msg("There already exists a map by that name.")
            return
        description = "A map."
        # Create and set the map up
        lockstring = "view:all();delete:perm(Immortals);edit:id(%s)" % caller.id
        new_map = create.create_object(typeclass, name, location=caller,
                                         home = "#4", permissions=None,
                                         locks=lockstring, aliases=None, destination=None,
                                         report_to=None, nohome=False)
        new_map.desc = description
        self.msg("Created map %s." % new_map.key)
        new_map.save()

class CmdMapRoom(ArxCommand):
    """
    @maproom
    Usage:
     @maproom <map name>=x,y,icons
     @maproom/clear <map name>=x,y

    Adds the room you're presently in to the map of the given name,
    giving it the x and y coordinates provided and the icon provided.
    For example, to add your current room called Silver Spire to the
    'Silverlands' map, where the Silver Spire is at (5,18):
        @maproom silverlands=5,18,SS
    To have it appear as 'SS' for its map square. Map icons should
    generally be two characters long.
    """

    key = "@maproom"
    locks = "cmd:perm(Wizards)"
    help_category = "Travel"

    def func(self):
        "Implement the command"

        caller = self.caller
        try:
            x,y = int(self.rhslist[0]), int(self.rhslist[1])
            if 'clear' not in self.switches:
                icons = self.rhslist[2]
            map = ObjectDB.objects.get(db_typeclass_path=MAP_TYPECLASS,
                                       db_key__iexact=self.lhs)
        except (KeyError, AttributeError, TypeError, ValueError):
            caller.msg("Usage error. Example of correct usage:")
            caller.msg("@maproom crownward=5,3,C7")
            return
        except ObjectDB.DoesNotExist:
            caller.msg("No map found for %s." % self.lhs)
            return
        if 'clear' in self.switches:
            map.db.rooms[(x,y)] = None
            caller.msg("Location (%s, %s) will be a blank space." % (x, y))
            return
        # set up room
        room = caller.location
        room.db.map_icon = icons
        room.db.x_coord = x
        room.db.y_coord = y
        map.add_room(room)
        caller.msg("Added %s at (%s, %s)." % (room, x, y))
        return
        
