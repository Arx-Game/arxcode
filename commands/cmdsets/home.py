"""
Commands for home spaces/rooms.
"""

from evennia import CmdSet
from commands.base import ArxCommand
from django.conf import settings
from world.dominion.models import LIFESTYLES
from django.db.models import Q
from evennia.objects.models import ObjectDB
from world.dominion.models import AssetOwner, Organization, CraftingRecipe
from commands.base_commands.crafting import CmdCraft
from commands.base_commands.overrides import CmdDig
from server.utils.prettytable import PrettyTable
from server.utils.arx_utils import inform_staff, raw
from evennia.utils import utils
from evennia.utils.evtable import EvTable
from typeclasses.characters import Character
import re
# error return function, needed by Extended Look command
AT_SEARCH_RESULT = utils.variable_from_module(*settings.SEARCH_AT_RESULT.rsplit('.', 1))

DESC_COST = 0


class HomeCmdSet(CmdSet):
    """CmdSet for a home spaces."""
    key = "HomeCmdSet"
    priority = 101
    duplicates = False
    no_exits = False
    no_objs = False

    def at_cmdset_creation(self):
        """
        This is the only method defined in a cmdset, called during
        its creation. It should populate the set with command instances.

        Note that it can also take other cmdsets as arguments, which will
        be used by the character default cmdset to add all of these onto
        the internal cmdset stack. They will then be able to removed or
        replaced as needed.
        """
        self.add(CmdManageHome())


class CmdManageHome(ArxCommand):
    """
    +home
    Usage:
        +home
        +home/lock
        +home/unlock
        +home/key <character>
        +home/passmsg <message people see when entering>
        +home/lockmsg <message those who can't enter see>
        +home/rmkey <character>
        +home/lifestyle <rating>

    Controls your home. /passmsg is for use of the 'pass' command to
    go through a locked door. /lockmsg is for those who are denied
    entry. /lifestyle is to control how much silver you spend per
    week and earn prestige.
    """
    key = "+home"
    # aliases = ["@home"]
    locks = "cmd:all()"
    help_category = "Home"

    def display_lifestyles(self):
        """Displays table of Dominion lifestyles with the character's current selection"""
        caller = self.caller
        table = PrettyTable(["{wRating{n", "{wCost{n", "{wPrestige{n"])
        caller.msg("{wLifestyles:{n")
        for rating in LIFESTYLES:
            num = str(rating)
            if caller.player_ob.Dominion.lifestyle_rating == rating:
                num += '{w*{n'
            table.add_row([num, LIFESTYLES[rating][0], LIFESTYLES[rating][1]])
        caller.msg(str(table), options={'box': True})
    
    def func(self):
        """Execute command."""
        caller = self.caller
        loc = caller.location
        entrances = loc.entrances
        owners = loc.db.owners or []
        keylist = loc.db.keylist or []
        if caller not in owners and not caller.check_permstring("builders"):
            caller.msg("You are not the owner of this room.")
            return
        if not self.args and not self.switches:
            locked = "{rlocked{n" if loc.db.locked else "{wunlocked{n"
            caller.msg("Your home is currently %s." % locked)
            caller.msg("{wOwners:{n %s" % ", ".join(str(ob) for ob in owners))
            caller.msg("{wCharacters who have keys:{n %s" % ", ".join(str(ob) for ob in keylist))
            entrance = entrances[0]
            entmsg = entrance.db.success_traverse or ""
            errmsg = entrance.db.err_traverse or ""
            caller.msg("{wMessage upon passing through locked door:{n %s" % entmsg)
            caller.msg("{wMessage upon being denied access:{n %s" % errmsg)
            return
        if "unlock" in self.switches:
            # we only show as locked if -all- entrances are locked
            for ent in entrances:
                ent.unlock_exit()
            loc.db.locked = False
            caller.msg("Your house is now unlocked.")
            return
        if "lock" in self.switches:
            loc.db.locked = True
            caller.msg("Your house is now locked.")
            for ent in entrances:
                ent.lock_exit()
            return
        if "lifestyle" in self.switches and not self.args:
            # list lifestyles
            self.display_lifestyles()
            return
        if not self.args:
            caller.msg("You must provide an argument to the command.")
            return
        if "lockmsg" in self.switches:
            for r_exit in entrances:
                r_exit.db.err_traverse = self.args
            caller.msg("{wThe message those who can't enter now see is{n: %s" % self.args)
            return
        if "passmsg" in self.switches:
            for r_exit in entrances:
                r_exit.db.success_traverse = self.args
            caller.msg("{wThe message those who enter will now see is{n: %s" % self.args)
            return
        if "lifestyle" in self.switches or "lifestyles" in self.switches:
            if caller not in owners:
                caller.msg("You may only set the lifestyle rating for an owner.")
                return
            try:
                LIFESTYLES[int(self.args)]
            except (KeyError, TypeError, ValueError):
                caller.msg("%s is not a valid lifestyle." % self.args)
                self.display_lifestyles()
                return
            caller.player_ob.Dominion.lifestyle_rating = int(self.args)
            caller.player_ob.Dominion.save()
            caller.msg("Your lifestyle rating has been set to %s." % self.args)
            return
        player = caller.player.search(self.lhs)
        if not player:
            return
        char = player.char_ob
        if not char:
            caller.msg("No character found.")
            return
        keys = char.db.keylist or []
        if "key" in self.switches:          
            if loc in keys and char in keylist:
                caller.msg("They already have a key to here.")
                return
            if loc not in keys:
                keys.append(loc)
                char.db.keylist = keys
            if char not in keylist:
                keylist.append(char)
                loc.db.keylist = keylist
            char.msg("{c%s{w has granted you a key to %s." % (caller, loc))
            caller.msg("{wYou have granted {c%s{w a key.{n" % char)
            return
        if "rmkey" in self.switches:
            if loc not in keys and char not in keylist:
                caller.msg("They don't have a key to here.")
                return
            if loc in keys:
                keys.remove(loc)
                char.db.keylist = keys
            if char in keylist:
                keylist.remove(char)
                loc.db.keylist = keylist
            char.msg("{c%s{w has removed your access to %s." % (caller, loc))
            caller.msg("{wYou have removed {c%s{w's key.{n" % char)
            return


class CmdAllowBuilding(ArxCommand):
    """
    @allowbuilding

    Usage:
        @allowbuilding
        @allowbuilding all[=<cost>]
        @allowbuilding <name>[,<name2>,...][=<cost>]
        @allowbuilding/clear

    Flags your current room as permitting characters to build there.
    The name provided can either be a character or organization name.
    Cost is 100 economic resources unless specified otherwise. Max
    rooms that anyone can build off here is set by the 'expansion_cap'
    attribute, defaults to 1 if not defined. Tracked separately for
    each org/player, so any number of people could build 1 room off
    a room with expansion_cap of 1 in a room, as long as they are
    permitted to do so.
    """
    key = "@allowbuilding"
    locks = "cmd:perm(Builders)"
    help_category = "Building"

    def func(self):
        """Execute command."""
        caller = self.caller
        loc = caller.location
        permits = loc.db.permitted_builders or {}
        if not self.args and not self.switches:
            table = PrettyTable(["Name", "Cost"])
            for permit_id in permits:
                if permit_id == "all":
                    owner = "all"
                else:
                    owner = AssetOwner.objects.get(id=permit_id)
                cost = permits[permit_id]
                table.add_row([str(owner), cost])
            caller.msg(str(table))
            return
        if "clear" in self.switches:
            loc.db.permitted_builders = {}
            caller.msg("Perms wiped.")
            return
        cost = self.rhs and int(self.rhs) or 100
        for name in self.lhslist:
            if name == "all":
                permits["all"] = cost
                continue
            try:
                owner = AssetOwner.objects.get(Q(organization_owner__name__iexact=name)
                                               | Q(player__player__username__iexact=name))
            except AssetOwner.DoesNotExist:
                caller.msg("No owner by name of %s." % name)
                continue
            permits[owner.id] = cost
        loc.db.permitted_builders = permits
        caller.msg("Perms set.")
        return


class CmdBuildRoom(CmdDig):
    """
    +buildroom - build and connect new rooms to the current one

    Usage:
      +buildroom roomname=exit_to_there[;alias], exit_to_here[;alias]

      +buildroom/org orgname/roomname=[exits]

    Examples:
       +buildroom kitchen = north;n, south;s
       +buildroom sheer cliff= climb up, climb down
       +buildroom/org velenosa/dungeon=door;d, out;o

    This command is a convenient way to build rooms quickly; it creates the
    new room and you can optionally set up exits back and forth between your
    current room and the new one. You can add as many aliases as you
    like to the name of the room and the exits in question; an example
    would be 'north;no;n'.
    """
    key = "+buildroom"
    locks = "cmd:all()"
    help_category = "Home"
    help_entry_tags = ["housing"]

    # noinspection PyAttributeOutsideInit
    def func(self):
        """Do the digging. Inherits variables from ObjManipCommand.parse()"""

        caller = self.caller
        loc = caller.location

        # lots of checks and shit here
        permits = loc.db.permitted_builders or {}
        if not permits:
            caller.msg("No one is currently allowed to build a house from here.")
            return
        expansions = loc.db.expansions or {}
        max_expansions = loc.db.expansion_cap or 20
        assets = None
        # base cost = 1000
        dompc = caller.player_ob.Dominion

        if "org" in self.switches:
            # max_rooms = 100
            try:
                largs = self.lhs.split("/")
                orgname = largs[0]
                roomname = largs[1]
            except IndexError:
                caller.msg("Please specify orgname/roomname.")
                return

            try:
                org = Organization.objects.get(Q(name__iexact=orgname) &
                                               Q(members__player=dompc) &
                                               Q(members__deguilded=False))
                if not org.access(caller, 'build'):
                    caller.msg("You are not permitted to build for this org.")
                    return
                self.lhs = roomname
                self.lhslist = [roomname]
                self.args = "%s=%s" % (self.lhs, self.rhs)
                # fix args for CmdDig
                self.parse()
                assets = org.assets
                cost = permits[assets.id]
            except KeyError:
                if "all" not in permits:
                    caller.msg("That org is not permitted to build here.")
                    return
                cost = permits["all"]
            except Organization.DoesNotExist:
                caller.msg("No org by that name: %s." % orgname)
                return
        else:
            # max_rooms = 3
            assets = dompc.assets
            if assets.id in permits:
                cost = permits[assets.id]
            else:
                if "all" not in permits:
                    caller.msg("You are not allowed to build here.")
                    return
                cost = permits["all"]
        try:
            if expansions.get(assets.id, 0) >= max_expansions:
                caller.msg("You have built as many rooms from this space as you are allowed.")
                return
        except (AttributeError, TypeError, ValueError):
            caller.msg("{rError logged.{n")
            inform_staff("Room %s has an invalid expansions attribute." % loc.id)
            return
        if not self.lhs:
            caller.msg("The cost for you to build from this room is %s." % cost)
            return
        if cost > assets.economic:
            noun = "you" if dompc.assets == assets else str(assets)
            caller.msg("It would cost %s %s to build here, but only have %s." % (noun, cost, assets.economic))
            if noun != "you":
                caller.msg("Deposit resources into the account of %s." % noun)
            return
        tagname = "%s_owned_room" % str(assets)
        # because who fucking cares
        # if tagname not in loc.tags.all() and (
        # ObjectDB.objects.filter(Q(db_typeclass_path=settings.BASE_ROOM_TYPECLASS)
        #                                                               & Q(db_tags__db_key__iexact=tagname)
        #                                                               ).count() > max_rooms):
        #     caller.msg("You have as many rooms as you are allowed.")
        #     return
        if not self.rhs or len(self.rhslist) < 2:
            caller.msg("You must specify an exit and return exit for the new room.")
            return

        if not re.findall('^[\-\w\'{\[,%;|# ]+$', self.lhs) or not re.findall('^[\-\w\'{\[,%;|<># ]+$', self.rhs):
            caller.msg("Invalid characters entered for names or exits.")
            return
        new_room = CmdDig.func(self)
        if not new_room:
            return
        assets.economic -= cost
        assets.save()
        # do setup shit for new room here
        new_room.db.room_owner = assets.id
        new_room.tags.add("player_made_room")
        new_room.tags.add(tagname)
        new_room.tags.add("private")
        new_room.db.expansion_cap = 20
        new_room.db.expansions = {}
        new_room.db.cost_increase_per_expansion = 25
        cost_increase = loc.db.cost_increase_per_expansion or 0
        new_room.db.permitted_builders = {assets.id: cost + cost_increase}
        new_room.db.x_coord = loc.db.x_coord
        new_room.db.y_coord = loc.db.y_coord
        my_expansions = expansions.get(assets.id, 0) + 1
        expansions[assets.id] = my_expansions
        loc.db.expansions = expansions
        new_room.name = new_room.name  # this will setup .db.colored_name and strip ansi from key
        if cost_increase and assets.id in permits:
            permits[assets.id] += cost_increase
            loc.db.permitted_builders = permits


class CmdManageRoom(ArxCommand):
    """
    +manageroom

    Usage:
        +manageroom
        +manageroom/name <name>
        +manageroom/desc <description>
        +manageroom/springdesc <description>
        +manageroom/summerdesc <description>
        +manageroom/falldesc <description>
        +manageroom/winterdesc <description>
        +manageroom/exitname <exit>=<new name>
        +manageroom/addhome <owner>
        +manageroom/confirmhome <owner>
        +manageroom/rmhome <owner>
        +manageroom/addshop <owner>
        +manageroom/confirmshop <owner>
        +manageroom/rmshop <owner>
        +manageroom/toggleprivate
        +manageroom/setbarracks
        +manageroom/addbouncer <character>
        +manageroom/rmbouncer <character>
        +manageroom/adddecorator <character>
        +manageroom/rmdecorator <character>
        +manageroom/ban <character>
        +manageroom/unban <character>
        +manageroom/boot <character>=<exit>

    Flags your current room as permitting characters to build there.
    Cost is 100 economic resources unless specified otherwise.

    To set a seasonal description for your room, use /springdesc, /summerdesc,
    etc. /desc will always be shown as a fallback otherwise.

    You can also embed special time markers in your room description, like this:

        ```
        <night>In the darkness, the forest looks foreboding.</night>.
        <morning>Birds are chirping and whatnot.</morning>
        <afternoon>Birds are no longer chirping.</morning>
        <evening>THEY WILL NEVER CHIRP AGAIN.</evening>
        ```

    Text marked this way will only display when the server is truly at the given
    timeslot. The available times are night, morning, afternoon and evening.

    Note that `@detail`, seasons and time-of-day slots only work on rooms in this
    version of the `@desc` command.

    Owners can appoint characters to be decorators or bouncers, to allow them to
    use commands while not owners.
    
    The ban switch prevents characters from being able to enter the room. The boot
    switch removes characters from the room. Bouncers are able to use ban and boot.
    Decorators are permitted to use the desc switches.
    """
    key = "+manageroom"
    locks = "cmd:all()"
    help_category = "Home"
    desc_switches = ("desc", "winterdesc", "springdesc", "summerdesc", "falldesc")
    bouncer_switches = ("ban", "unban", "boot")
    personnel_switches = ("addbouncer", "rmbouncer", "adddecorator", "rmdecorator")
    help_entry_tags = ["housing"]
    
    def check_perms(self):
        """Checks the permissions for the room"""
        caller = self.caller
        loc = caller.location
        if not self.switches or set(self.switches) & set(self.bouncer_switches):
            if caller in loc.bouncers:
                return True
        if not self.switches or set(self.switches) & set(self.desc_switches):
            if caller in loc.decorators:
                return True
        try:
            owner = AssetOwner.objects.get(id=loc.db.room_owner)
        except AssetOwner.DoesNotExist:
            caller.msg("No owner is defined here.")
            return
        org = owner.organization_owner
        if not org and not (owner == caller.player_ob.Dominion.assets
                            or ('confirmhome' in self.switches or
                                'confirmshop' in self.switches)):
            caller.msg("You are not the owner here.")
            return
        if org and not (org.access(caller, 'build') or ('confirmhome' in self.switches or
                                                        'confirmshop' in self.switches)):
            caller.msg("You do not have permission to build here.")
            return
        return True

    def func(self):
        """Execute command."""
        caller = self.caller
        loc = caller.location
        if not self.check_perms():
            return
        if not self.switches:
            # display who has a home here, who has a shop here
            owners = loc.db.owners or []
            caller.msg("{wHome Owners:{n %s" % ", ".join(str(ob) for ob in owners))
            shops = loc.db.shopowner
            caller.msg("{wShop Owners:{n %s" % shops)
            self.msg("{wBouncers:{n %s" % ", ".join(str(ob) for ob in loc.bouncers))
            self.msg("{wDecorators:{n %s" % ", ".join(str(ob) for ob in loc.decorators))
            self.msg("{wBanned:{n %s" % ", ".join(str(ob) for ob in loc.banlist))
            return
        if "name" in self.switches:
            loc.name = self.args or loc.name
            caller.msg("Room name changed to %s." % loc)
            return
        if "exitname" in self.switches:
            if not self.rhs:
                caller.msg("Invalid usage.")
                return
            rhslist = self.rhs.split(";")
            rhs = rhslist[0]
            aliases = rhslist[1:]
            exit_object = caller.search(self.lhs)
            if not exit_object:
                return
            old = str(exit_object)
            if exit_object.typeclass_path != settings.BASE_EXIT_TYPECLASS:
                caller.msg("That is not an exit.")
                return
            exit_object.name = rhs
            exit_object.save()
            exit_object.aliases.clear()
            for alias in aliases:
                exit_object.aliases.add(alias)
            if exit_object.destination:
                exit_object.flush_from_cache()
            caller.msg("%s changed to %s." % (old, exit_object))
            return
        if (set(self.switches) & set(self.personnel_switches)) or (set(self.switches) & set(self.bouncer_switches)):
            targ = self.caller.player.search(self.lhs)
            if not targ:
                return
            targ = targ.char_ob
            if "addbouncer" in self.switches:
                loc.add_bouncer(targ)
                self.msg("%s is now a bouncer." % targ)
                return
            if "rmbouncer" in self.switches:
                loc.remove_bouncer(targ)
                self.msg("%s is no longer a bouncer." % targ)
                return
            if "adddecorator" in self.switches:
                loc.add_decorator(targ)
                self.msg("%s is now a decorator." % targ)
                return
            if "rmdecorator" in self.switches:
                loc.remove_decorator(targ)
                self.msg("%s is no longer a decorator." % targ)
                return
            if "unban" in self.switches:
                loc.unban_character(targ)
                self.msg("%s is no longer banned from entering." % targ)
                return
            if "ban" in self.switches:
                loc.ban_character(targ)
                self.msg("%s is now prevented from entering." % targ)
                return
            if "boot" in self.switches:
                from typeclasses.exits import Exit
                exit_obj = self.caller.search(self.rhs, typeclass=Exit)
                if not exit_obj:
                    return
                if not exit_obj.can_traverse(targ):
                    self.msg("They cannot move through that exit.")
                    return
                if targ.location != self.caller.location:
                    self.msg("They aren't here.")
                    return
                exit_obj.at_traverse(targ, exit_obj.destination)
                self.msg("You have kicked out %s." % targ)
                targ.msg("You have been kicked out by %s." % self.caller)
                return
        try:
            owner = AssetOwner.objects.get(id=loc.db.room_owner)
        except AssetOwner.DoesNotExist:
            caller.msg("No owner is defined here.")
            return
        if set(self.switches) & set(self.desc_switches):
            if "player_made_room" not in loc.tags.all():
                self.msg("You cannot change the description to a room that was made by a GM.")
                return
            if loc.desc:
                cost = loc.db.desc_cost or DESC_COST
            else:
                cost = 0
            if loc.ndb.confirm_desc_change != self.args:
                caller.msg("Your room's current %s is:" % self.switches[0])
                if "desc" in self.switches:
                    caller.msg(loc.desc)
                elif "springdesc" in self.switches:
                    caller.msg(loc.db.spring_desc)
                elif "summerdesc" in self.switches:
                    caller.msg(loc.db.summer_desc)
                elif "winterdesc" in self.switches:
                    caller.msg(loc.db.winter_desc)
                elif "falldesc" in self.switches:
                    caller.msg(loc.db.autumn_desc)
                caller.msg("{wCost of changing desc:{n %s economic resources" % cost)
                if self.args:
                    caller.msg("New desc:")
                    caller.msg(self.args)
                    caller.msg("{wTo confirm this, use the command again.{n")
                    caller.msg("{wChanging this desc will prompt you again for a confirmation.{n")
                    loc.ndb.confirm_desc_change = self.args
                return
            if cost:
                if cost > owner.economic:
                    caller.msg("It would cost %s to re-desc the room, and you have %s." % (cost, owner.economic))
                    return
                owner.economic -= cost
                owner.save()
            if "desc" in self.switches:
                loc.desc = self.args
                if not loc.db.raw_desc:
                    loc.db.raw_desc = self.args
                if not loc.db.general_desc:
                    loc.db.general_desc = self.args
            elif "winterdesc" in self.switches:
                loc.db.winter_desc = self.args
            elif "summerdesc" in self.switches:
                loc.db.summer_desc = self.args
            elif "springdesc" in self.switches:
                loc.db.spring_desc = self.args
            elif "falldesc" in self.switches:
                loc.db.autumn_desc = self.args
            loc.ndb.confirm_desc_change = None
            # force raw_desc to update and parse our descs
            loc.ndb.last_season = None
            loc.ndb.last_timeslot = None
            caller.msg("%s changed to:" % self.switches[0])
            caller.msg(self.args)
            return
        if "confirmhome" in self.switches:
            if caller.db.homeproposal != loc:
                caller.msg("You don't have an active invitation to accept here. Have them reissue it.")
                return
            caller.attributes.remove("homeproposal")
            loc.setup_home(caller)
            caller.msg("You have set up your home here.")
            return
        if "confirmshop" in self.switches:
            if caller.db.shopproposal != loc:
                caller.msg("You don't have an active invitation to accept here. Have them reissue it.")
                return
            caller.attributes.remove("shopproposal")
            loc.setup_shop(caller)
            caller.msg("You have set up a shop here.")
            return
        if "toggleprivate" in self.switches:
            if "private" in loc.tags.all():
                loc.tags.remove("private")
                caller.msg("Room no longer private.")
                return
            loc.tags.add("private")
            caller.msg("Room is now private.")
            return
        if "setbarracks" in self.switches:
            tagname = str(owner) + "_barracks"
            other_barracks = ObjectDB.objects.filter(db_tags__db_key=tagname)
            for obj in other_barracks:
                obj.tags.remove(tagname)
            loc.tags.add(tagname)
            self.msg("%s set to %s's barracks." % (loc, owner))
            return
        player = caller.player.search(self.args)
        if not player:
            return
        char = player.char_ob
        if not char:
            caller.msg("No char.")
            return
        if "addhome" in self.switches or "addshop" in self.switches:
            noun = "home" if "addhome" in self.switches else "shop" 
            if noun == "home":
                char.db.homeproposal = loc
            else:
                char.db.shopproposal = loc
                if loc.db.shopowner:
                    caller.msg("You must shut down the current shop here before adding another.")
                    return
            msg = "%s has offered you a %s. To accept it, go to %s" % (caller, noun, loc.key)
            msg += " and use {w+manageroom/confirm%s{n." % noun
            player.send_or_queue_msg(msg)
            caller.msg("You have offered %s this room as a %s." % (char, noun))
            return
        if "rmhome" in self.switches:
            loc.remove_homeowner(char)
            player.send_or_queue_msg("Your home at %s has been removed." % loc)
            return
        if "rmshop" in self.switches:
            loc.del_shop()
            player.send_or_queue_msg("Your shop at %s has been removed." % loc)
            return


class CmdManageShop(ArxCommand):
    """
    +manageshop

    Usage:
        +manageshop
        +manageshop/sellitem <object>=<price>
        +manageshop/rmitem <object id>
        +manageshop/all <markup percentage>
        +manageshop/refinecost <percentage>
        +manageshop/addrecipe <recipe name>=<markup percentage>
        +manageshop/rmrecipe <recipe name>
        +manageshop/addblacklist <player or org name>
        +manageshop/rmblacklist <player or org name>
        +manageshop/orgdiscount <org name>=<percentage>
        +manageshop/chardiscount <character>=<percentage>
        +manageshop/adddesign <key>=<code>
        +manageshop/rmdesign <key>

    Sets prices for your shop. Note that if you use 'all', that will
    be used for any recipe you don't explicitly set a price for.
    """
    key = "+manageshop"
    locks = "cmd:all()"
    help_category = "Home"
    help_entry_tags = ["shops"]

    def list_prices(self):
        """Lists a table of prices for the shop owner"""
        loc = self.caller.location
        prices = loc.db.crafting_prices or {}
        msg = "{wCrafting Prices{n\n"
        table = PrettyTable(["{wName{n", "{wPrice Markup Percentage{n"])
        for price in prices:
            if price == "removed":
                continue
            if price == "all" or price == "refine":
                name = price
            else:
                name = (CraftingRecipe.objects.get(id=price)).name
            table.add_row([name, "%s%%" % prices[price]])
        msg += str(table)
        msg += "\n{wItem Prices{n\n"
        table = EvTable("{wID{n", "{wName{n", "{wPrice{n", width=78, border="cells")
        prices = loc.db.item_prices or {}
        for price in prices:
            obj = ObjectDB.objects.get(id=price)
            table.add_row(price, str(obj), prices[price])
        msg += str(table)
        return msg

    def list_designs(self):
        """Lists designs the shop owner has created for crafting templates"""
        designs = self.caller.location.db.template_designs or {}
        self.msg("{wTemplate designs:{n %s" % ", ".join(designs.keys()))

    def func(self):
        """Execute command."""
        caller = self.caller
        loc = caller.location
        if caller != loc.db.shopowner:
            caller.msg("You are not the shop's owner.")
            return
        if not self.args:
            caller.msg(self.list_prices())
            org_discounts = (loc.db.discounts or {}).items()
            char_discounts = (loc.db.char_discounts or {}).items()
            # replace char with char.key in char_discounts list
            char_discounts = [(ob[0].key, ob[1]) for ob in char_discounts]
            discounts = ", ".join(("%s: %s%%" % (ob, val) for ob, val in (org_discounts + char_discounts)))
            caller.msg("{wDiscounts{n: %s" % discounts)
            blacklist = []
            if loc.db.blacklist:
                # if ob doesn't have a key, it becomes a string (because corporations aren't ppl)
                blacklist = [getattr(ob, 'key', str(ob)) for ob in loc.db.blacklist]
            caller.msg("{wBlacklist{n: %s" % ", ".join(blacklist))
            self.list_designs()
            return
        if "sellitem" in self.switches:
            try:
                price = int(self.rhs)
                if price < 0:
                    raise ValueError
            except (TypeError, ValueError):
                caller.msg("Price must be a positive number.")
                return
            results = caller.search(self.lhs, location=caller, quiet=True)
            obj = AT_SEARCH_RESULT(results, caller, self.lhs, False,
                                   nofound_string="You don't carry %s." % self.lhs,
                                   multimatch_string="You carry more than one %s:" % self.lhs)
            if not obj:
                return
            obj.at_drop(caller)
            obj.location = None
            loc.db.item_prices[obj.id] = price
            obj.tags.add("for_sale")
            obj.db.sale_location = loc
            caller.msg("You put %s for sale for %s silver." % (obj, price))
            return
        if "rmitem" in self.switches:
            try:
                num = int(self.args)
                if num not in loc.db.item_prices:
                    caller.msg("No item by that ID being sold.")
                    return
                obj = ObjectDB.objects.get(id=num)
            except ObjectDB.DoesNotExist:
                caller.msg("No object by that ID exists.")
                return
            except (ValueError, TypeError):
                caller.msg("You have to specify the ID # of an item you're trying to remove.")
                return
            obj.move_to(caller)
            obj.tags.remove("for_sale")
            obj.attributes.remove("sale_location")
            del loc.db.item_prices[obj.id]
            caller.msg("You have removed %s from your sale list." % obj)
            return
        if "all" in self.switches or "refinecost" in self.switches:
            try:
                cost = int(self.args)
                if cost < 0:
                    raise ValueError
            except ValueError:
                caller.msg("Cost must be a non-negative number.")
                return
            if "all" in self.switches:
                loc.db.crafting_prices['all'] = cost
                caller.msg("Cost for non-specified recipes set to %s percent markup." % cost)
            else:
                loc.db.crafting_prices['refine'] = cost
                caller.msg("Cost for refining set to %s percent markup." % cost)
            return
        if "addrecipe" in self.switches:
            prices = loc.db.crafting_prices or {}
            try:
                recipe = caller.player_ob.Dominion.assets.recipes.get(name__iexact=self.lhs)
                cost = int(self.rhs)
                if cost < 0:
                    raise ValueError
            except (TypeError, ValueError):
                caller.msg("Cost must be a positive number.")
                return
            except (CraftingRecipe.DoesNotExist, CraftingRecipe.MultipleObjectsReturned):
                caller.msg("Could not retrieve a recipe by that name.")
                return
            prices[recipe.id] = cost
            caller.msg("Price for %s set to %s." % (recipe.name, cost))
            removedlist = prices.get("removed", [])
            if recipe.id in removedlist:
                removedlist.remove(recipe.id)
            prices['removed'] = removedlist
            loc.db.crafting_prices = prices
            return
        if "rmrecipe" in self.switches:
            arg = None
            prices = loc.db.crafting_prices or {}
            try:
                recipe = None
                if self.lhs.lower() == "all":
                    arg = "all"
                elif self.lhs.lower() == "refining":
                    arg = "refining"
                else:
                    recipe = caller.player_ob.Dominion.assets.recipes.get(name__iexact=self.lhs)
                    arg = recipe.id
                del prices[arg]
                caller.msg("Price for %s has been removed." % recipe.name if recipe else arg)
            except KeyError:
                removedlist = prices.get("removed", [])
                if arg in removedlist:
                    caller.msg("You had no price listed for that recipe.")
                else:
                    try:
                        removedlist.append(int(arg))
                        prices["removed"] = removedlist
                    except ValueError:
                        caller.msg("Must be an ID.")
            except CraftingRecipe.DoesNotExist:
                caller.msg("No recipe found by that name.")
            finally:
                loc.db.crafting_prices = prices
                return
        if "adddesign" in self.switches:
            designs = loc.db.template_designs or {}
            try:
                if not self.rhs:
                    self.msg("Design for %s: %s" % (self.lhs, designs[self.lhs]))
                    return
            except KeyError:
                self.list_designs()
                return
            designs[self.lhs] = self.rhs
            self.msg("Raw Design for %s is now: %s" % (self.lhs, raw(self.rhs)))
            self.msg("Design for %s appears as: %s" % (self.lhs, self.rhs))
            loc.db.template_designs = designs
            return
        if "rmdesign" in self.switches:
            designs = loc.db.template_designs or {}
            try:
                del designs[self.lhs]
                self.msg("Design deleted.")
            except KeyError:
                self.msg("No design by that name.")
                self.list_designs()
            loc.db.template_designs = designs
            return
        if "addblacklist" in self.switches or "rmblacklist" in self.switches:
            blacklist = loc.db.blacklist or []
            try:
                targ = caller.player.search(self.args, nofound_string="No player by that name. Checking organizations.")
                org = False
                if not targ:
                    org = True
                    targ = Organization.objects.get(name__iexact=self.args)
                else:
                    targ = targ.char_ob
                if "addblacklist" in self.switches:
                    if org:
                        if targ.name in blacklist:
                            caller.msg("They are already in the blacklist.")
                            return
                        blacklist.append(targ.name)
                    else:
                        if targ in blacklist:
                            caller.msg("They are already in the blacklist.")
                            return
                        blacklist.append(targ)
                    caller.msg("%s added to blacklist." % getattr(targ, 'key', targ))
                else:
                    if org:
                        if targ.name not in blacklist:
                            caller.msg("They are not in the blacklist.")
                            return
                        blacklist.remove(targ.name)
                    else:
                        if targ not in blacklist:
                            caller.msg("They are not in the blacklist.")
                            return
                        blacklist.remove(targ)
                    caller.msg("%s removed from blacklist." % getattr(targ, 'key', targ))
            except Organization.DoesNotExist:
                caller.msg("No valid target found by that name.")
            loc.db.blacklist = blacklist
            return
        if "orgdiscount" in self.switches:
            try:
                org = Organization.objects.get(name__iexact=self.lhs)
                discount = int(self.rhs)
                if discount > 100:
                    raise ValueError
                if discount == 0:
                    loc.db.discounts.pop(org.name, 0)
                    self.msg("Removed discount for %s." % org)
                    return
                loc.db.discounts[org.name] = discount
                caller.msg("%s given a discount of %s percent." % (org, discount))
                return
            except (TypeError, ValueError):
                caller.msg("Discount must be a number, max of 100.")
                return
            except Organization.DoesNotExist:
                caller.msg("No organization by that name found.")
                return
        if "chardiscount" in self.switches:
            if loc.db.char_discounts is None:
                loc.db.char_discounts = {}
            try:
                character = Character.objects.get(db_key__iexact=self.lhs)
                discount = int(self.rhs)
                if discount > 100:
                    raise ValueError
                if discount == 0:
                    loc.db.char_discounts.pop(character, 0)
                    self.msg("Removed discount for %s." % character.key)
                    return
                loc.db.char_discounts[character] = discount
                caller.msg("%s given a discount of %s percent." % (character.key, discount))
                return
            except (TypeError, ValueError):
                caller.msg("Discount must be a number, max of 100.")
                return
            except Character.DoesNotExist:
                caller.msg("No character found by that name.")
                return
        caller.msg("Invalid switch.")


class CmdBuyFromShop(CmdCraft):
    """
    +shop

    Usage:
        +shop
        +shop/filter <word in item name>
        +shop/buy <item number>
        +shop/look <item number>
        +shop/viewdesigns [<key>]
        +shop/name <name>
        +shop/desc <description>
        +shop/altdesc <description>
        +shop/adorn <material type>=<amount>
        +shop/translated_text <language>=<text>
        +shop/finish [<additional silver to invest>,<AP to invest>]
        +shop/abandon
        +shop/changename <object>=<new name>
        +shop/refine <object>[=<additional silver to spend>,AP to spend>]
        +shop/addadorn <object>=<material type>,<amount>
        +shop/craft

    Allows you to buy objects from a shop. +shop/craft allows you to use a 
    crafter's skill to create an item. Similarly, +shop/refine lets you use a 
    crafter's skill to attempt to improve a crafted object. Check 'help craft' 
    for an explanation of switches, all of which can be used with +shop. Costs 
    and materials are covered by you. +shop/viewdesigns lets you see the 
    crafter's pre-made descriptions that you can copy for items you create.
    """
    key = "+shop"
    aliases = ["@shop", "shop"]
    locks = "cmd:all()"
    help_category = "Home"

    def get_discount(self):
        """Returns our percentage discount"""
        loc = self.caller.location
        char_discounts = loc.db.char_discounts or {}
        discount = 0.0
        discounts = loc.db.discounts or {}
        if self.caller in char_discounts:
            return char_discounts[self.caller]
        for org in self.caller.player_ob.Dominion.current_orgs:
            odiscount = discounts.get(org.name, 0.0)
            if odiscount and not discount:
                discount = odiscount
            if odiscount and discount and odiscount > discount:
                discount = odiscount
        return discount

    def get_refine_price(self, base):
        """Price of refining"""
        loc = self.caller.location
        price = 0
        prices = loc.db.crafting_prices or {}
        if "refine" in prices:
            price = (base * prices["refine"]) / 100.0
        elif "all" in prices:
            price = (base * prices["all"]) / 100.0
        if price == 0:
            return price
        if price > 0:
            price -= (price * self.get_discount() / 100.0)
            if price < 0:
                return 0
            return price
        raise ValueError

    def get_recipe_price(self, recipe):
        """Price for crafting a recipe"""
        loc = self.caller.location
        base = recipe.value
        price = 0
        crafting_prices = loc.db.crafting_prices or {}
        if recipe.id in crafting_prices:
            price = (base * crafting_prices[recipe.id]) / 100.0
        elif "all" in crafting_prices:
            price = (base * crafting_prices["all"]) / 100.0
        if price is not None:
            price -= (price * self.get_discount() / 100.0)
            if price < 0:
                return 0
            return price
        # no price defined
        raise ValueError

    def list_prices(self):
        """List prices of everything"""
        loc = self.caller.location
        prices = loc.db.crafting_prices or {}
        msg = "{wCrafting Prices{n\n"
        table = PrettyTable(["{wName{n", "{wCraft Price{n", "{wRefine Price{n"])
        recipes = loc.db.shopowner.player_ob.Dominion.assets.recipes.all().order_by('name')
        # This try/except block corrects 'removed' lists that are corrupted by
        # non-integers, because that was a thing once upon a time. 
        try:
            removed = prices.get("removed", [])
            recipes = recipes.exclude(id__in=removed)
        except ValueError:
            removed = [ob for ob in removed if isinstance(ob, int)]
            prices['removed'] = removed
            recipes = recipes.exclude(id__in=removed)
        recipes = self.filter_shop_qs(recipes, "name")
        for recipe in recipes:
            try:
                refineprice = str(self.get_refine_price(recipe.value))
                table.add_row([recipe.name, str(recipe.additional_cost + self.get_recipe_price(recipe)),
                               refineprice])
            except (ValueError, TypeError):
                self.msg("{rError: Recipe %s does not have a price defined.{n" % recipe.name)
        if recipes:
            msg += str(table)
        msg += "\n{wItem Prices{n\n"
        table = EvTable("{wID{n", "{wName{n", "{wPrice{n", width=78, border="cells")
        prices = loc.db.item_prices or {}
        sale_items = ObjectDB.objects.filter(id__in=prices.keys())
        sale_items = self.filter_shop_qs(sale_items, "db_key")
        for item in sale_items:
            table.add_row(item.id, item.name, prices[item.id])
        if sale_items:
            msg += str(table)
        designs = self.filter_shop_dict(loc.db.template_designs or {})
        if designs:
            msg += "\n{wNames of designs:{n %s" % ", ".join(designs.keys())
        if not recipes and not sale_items and not designs:
            msg = "Nothing found."
        return msg
        
    def filter_shop_qs(self, shop_qs, field_name):
        """Returns filtered queryset if a filter word exists"""
        if "filter" in self.switches and self.args:
            filter_query = {"%s__icontains" % field_name: self.args}
            shop_qs = shop_qs.filter(**filter_query)
        return shop_qs
    
    def filter_shop_dict(self, shop_dict):
        """Returns filtered dict if a filter word exists"""
        if "filter" in self.switches and self.args:
            shop_dict = {name: value for name, value in shop_dict.items() if self.args.lower() in name.lower()}
        return shop_dict

    def pay_owner(self, price, msg):
        """Pay money to the other and send an inform of the sale"""
        loc = self.caller.location
        loc.db.shopowner.pay_money(-price)
        assets = loc.db.shopowner.player_ob.assets
        if price >= assets.min_silver_for_inform:
            assets.inform(msg, category="shop", append=True)

    def buy_item(self, item):
        """Buy an item from inventory - pay the owner and get the item"""
        loc = self.caller.location
        price = loc.db.item_prices[item.id]
        price -= price * (self.get_discount() / 100.0)
        self.caller.pay_money(price)
        self.pay_owner(price, "%s has bought %s for %s." % (self.caller, item, price))
        item.move_to(self.caller)
        item.tags.remove("for_sale")
        item.attributes.remove("sale_location")
        del loc.db.item_prices[item.id]
        if hasattr(item, "rmkey"):
            if item.rmkey(loc.db.shopowner):
                item.grantkey(self.caller)
                self.caller.msg("Good deal! The owner gave you a key for %s." % item)
                return
            self.caller.msg("Shady deal? The owner didn't have a key for %s to give you." % item)

    def check_blacklist(self):
        """See if we're allowed to buy"""
        caller = self.caller
        loc = caller.location
        blacklist = loc.db.blacklist or []
        if caller in blacklist:
            return True
        for org in caller.player_ob.Dominion.current_orgs:
            if org.name in blacklist:
                return True
        return False

    def func(self):
        """Execute command."""
        caller = self.caller
        loc = caller.location
        self.crafter = loc.db.shopowner
        if not self.crafter:
            self.msg("No shop owner is defined.")
            return
        if self.check_blacklist():
            caller.msg("You are not permitted to buy from this shop.")
            return
        if self.crafter.roster.roster.name == "Gone":
            self.msg("The shop owner is dead.")
            return
        if "filter" in self.switches or (not self.switches and not self.args):
            caller.msg(self.list_prices())
            project = caller.db.crafting_project
            if project:
                caller.msg(self.display_project(project))
            return
        if "viewdesigns" in self.switches:
            designs = loc.db.template_designs or {}
            if not self.args:
                self.msg("Names of designs: %s" % ", ".join(designs.keys()))
                return
            try:
                design = designs[self.args]
                self.msg("{wDesign's appearance:{n\n%s" % design)
                self.msg("\n{wRaw code of design:{n\n%s" % raw(design))
            except KeyError:
                self.msg("No design found by that name.")
                self.msg("Names of designs: %s" % ", ".join(designs.keys()))
            return
        if "buy" in self.switches:
            try:
                num = int(self.args)
                price = loc.db.item_prices[num]
                obj = ObjectDB.objects.get(id=num)
            except (TypeError, ValueError, KeyError):
                caller.msg("You must supply the ID number of an item being sold.")
                return
            if price > caller.db.currency:
                caller.msg("You cannot afford it.")
                return
            self.buy_item(obj)
            return
        if "look" in self.switches:
            try:
                num = int(self.args)
                obj = ObjectDB.objects.get(id=num, id__in=loc.db.item_prices.keys())
            except (TypeError, ValueError):
                self.msg("Please provide a number of an item.")
                return
            except ObjectDB.DoesNotExist:
                caller.msg("No item found by that number.")
                return
            caller.msg(obj.return_appearance(caller))
            return
        if set(self.switches) & set(self.crafting_switches + ("craft",)):
            return CmdCraft.func(self)
        caller.msg("Invalid switch.")


class ShopCmdSet(CmdSet):
    """CmdSet for shop spaces."""
    key = "ShopCmdSet"
    priority = 101
    duplicates = False
    no_exits = False
    no_objs = False

    def at_cmdset_creation(self):
        """
        This is the only method defined in a cmdset, called during
        its creation. It should populate the set with command instances.

        Note that it can also take other cmdsets as arguments, which will
        be used by the character default cmdset to add all of these onto
        the internal cmdset stack. They will then be able to removed or
        replaced as needed.
        """
        self.add(CmdManageShop())
        self.add(CmdBuyFromShop())
