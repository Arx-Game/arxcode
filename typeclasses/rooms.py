"""
Extended Room

Evennia Contribution - Griatch 2012

This is an extended Room typeclass for Evennia. It is supported
by an extended Look command and an extended @desc command, also
in this module.


Features:

1) Time-changing description slots

This allows to change the full description text the room shows
depending on larger time variations. Four seasons - spring, summer,
autumn and winter are used by default). The season is calculated
on-demand (no Script or timer needed) and updates the full text block.

There is also a general description which is used as fallback if
one or more of the seasonal descriptions are not set when their
time comes.

An updated @desc command allows for setting seasonal descriptions.

The room uses the src.utils.gametime.GameTime global script. This is
started by default, but if you have deactivated it, you need to
supply your own time keeping mechanism.


2) In-description changing tags

Within each seasonal (or general) description text, you can also embed
time-of-day dependent sections. Text inside such a tag will only show
during that particular time of day. The tags looks like <timeslot> ...
</timeslot>. By default there are four timeslots per day - morning,
afternoon, evening and night.


3) Details

The Extended Room can be "detailed" with special keywords. This makes
use of a special Look command. Details are "virtual" targets to look
at, without there having to be a database object created for it. The
Details are simply stored in a dictionary on the room and if the look
command cannot find an object match for a "look <target>" command it
will also look through the available details at the current location
if applicable. An extended @desc command is used to set details.


4) Extra commands

  CmdExtendedLook - look command supporting room details
  CmdExtendedDesc - @desc command allowing to add seasonal descs and details,
                    as well as listing them
  CmdGameTime     - A simple "time" command, displaying the current
                    time and season.


Installation/testing:

1) Add CmdExtendedLook, CmdExtendedDesc and CmdGameTime to the default cmdset
   (see wiki how to do this).
2) @dig a room of type contrib.extended_room.ExtendedRoom (or make it the
   default room type)
3) Use @desc and @detail to customize the room, then play around!

"""
import time
from django.conf import settings

from evennia.contrib.extended_room import ExtendedRoom
from evennia import default_cmds
from evennia import utils
from evennia.utils.utils import lazy_property
from evennia.objects.models import ObjectDB

from commands.base import ArxCommand
from typeclasses.scripts import gametime
from typeclasses.mixins import NameMixins, ObjectMixins
from world.magic.mixins import MagicMixins
from world.msgs.messagehandler import MessageHandler

from world.weather import utils as weather_utils

# error return function, needed by Extended Look command
_AT_SEARCH_RESULT = utils.variable_from_module(
    *settings.SEARCH_AT_RESULT.rsplit(".", 1)
)

# room cmdsets
MARKETCMD = "commands.cmdsets.market.MarketCmdSet"
BANKCMD = "commands.cmdsets.bank.BankCmdSet"
RUMORCMD = "commands.cmdsets.rumor.RumorCmdSet"
HOMECMD = "commands.cmdsets.home.HomeCmdSet"
SHOPCMD = "commands.cmdsets.home.ShopCmdSet"


# implements the Extended Room

# noinspection PyUnresolvedReferences
class ArxRoom(ObjectMixins, ExtendedRoom, MagicMixins):
    """
    This room implements a more advanced look functionality depending on
    time. It also allows for "details", together with a slightly modified
    look command.
    """

    def get_time_and_season(self):
        """
        Calculate the current time and season ids.
        """
        return gametime.get_time_and_season()

    @property
    def is_room(self):
        return True

    def softdelete(self):
        for entrance in self.entrances:
            entrance.softdelete()
        super(ArxRoom, self).softdelete()

    def undelete(self, move=True):
        super(ArxRoom, self).undelete(move=move)
        for entrance in self.entrances:
            entrance.undelete(move)

    @lazy_property
    def messages(self):
        return MessageHandler(self)

    @property
    def player_characters(self):
        return [
            ob
            for ob in self.contents
            if hasattr(ob, "is_character") and ob.is_character and ob.player
        ]

    def get_visible_characters(self, pobject):
        """Returns a list of visible characters in a room."""
        return [char for char in self.player_characters if char.access(pobject, "view")]

    def return_appearance(
        self, looker, detailed=False, format_desc=True, show_contents=True
    ):
        """This is called when e.g. the look command wants to retrieve the description of this object."""
        # update desc
        ExtendedRoom.return_appearance(self, looker)
        # return updated desc plus other stuff
        return (
            ObjectMixins.return_appearance(self, looker, detailed, format_desc)
            + self.command_string()
            + self.mood_string
            + self.event_string()
            + self.extra_status_string(looker)
            + self.combat_string(looker)
        )

    def _current_event(self):
        if not self.db.current_event:
            return None
        from world.dominion.models import RPEvent

        try:
            return RPEvent.objects.get(id=self.db.current_event)
        except (RPEvent.DoesNotExist, ValueError, TypeError):
            return None

    event = property(_current_event)

    def _entrances(self):
        return ObjectDB.objects.filter(db_destination=self)

    entrances = property(_entrances)

    def combat_string(self, looker):
        try:
            if looker.combat.combat:
                return "\nYou are in combat. Use {w+cs{n to see combatstatus."
            elif self.ndb.combat_manager:
                msg = "\nThere is a combat in progress here. You can observe it with {w@spectate_combat{n, "
                msg += "or join it with {w+fight{n."
                return msg
        except AttributeError:
            pass
        return ""

    def extra_status_string(self, looker):
        return ""

    def event_string(self):
        event = self.event
        if not event:
            return ""
        msg = "\n{wCurrent Event{n: %s (for more - {w@cal %s{n)" % (
            event.name,
            event.id,
        )
        if event.celebration_tier == 0:
            largesse = "poor"
        elif event.celebration_tier == 1:
            largesse = "common"
        elif event.celebration_tier == 2:
            largesse = "refined"
        elif event.celebration_tier == 3:
            largesse = "grand"
        elif event.celebration_tier == 4:
            largesse = "extravagant"
        elif event.celebration_tier == 5:
            largesse = "legendary"
        else:
            largesse = "Undefined"
        msg += "\n{wScale of the Event:{n %s" % largesse
        msg += "\n{rEvent logging is currently turned on in this room.{n\n"
        desc = event.room_desc
        if desc:
            msg += "\n" + desc + "\n"
        return msg

    def start_event_logging(self, event):
        self.msg_contents("{rEvent logging is now on for this room.{n")
        self.tags.add("logging event")
        self.db.current_event = event.id

    def stop_event_logging(self):
        self.tags.remove("logging event")
        self.attributes.remove("current_event")
        self.msg_contents("{rEvent logging is now off for this room.{n")

    def command_string(self):
        msg = ""
        tags = self.tags.all()
        if "shop" in tags:
            msg += "\n    {wYou can {c+shop{w here.{n"
        if "bank" in tags:
            msg += "\n    {wYou can {c+bank{w here.{n"
        if "nonlethal_combat" in tags:
            msg += "\n{wCombat in this room is non-lethal."
        return msg

    @property
    def mood_string(self):
        msg = ""
        mood = self.db.room_mood
        try:
            created = mood[1]
            if time.time() - created > 86400:
                self.attributes.remove("room_mood")
            else:
                msg = "\n{wCurrent Room Mood:{n " + mood[2]
        except (IndexError, ValueError, TypeError):
            msg = ""
        return msg

    def _homeowners(self):
        return self.db.owners or []

    homeowners = property(_homeowners)

    def give_key(self, char):
        keylist = char.db.keylist or []
        if self not in keylist:
            keylist.append(self)
        char.db.keylist = keylist

    def remove_key(self, char):
        keylist = char.db.keylist or []
        if self in keylist:
            keylist.remove(self)
        char.db.keylist = keylist

    def add_homeowner(self, char, sethomespace=True):
        owners = self.db.owners or []
        if char not in owners:
            owners.append(char)
            self.give_key(char)
        self.db.owners = owners
        if sethomespace:
            char.home = self
            char.save()

    def remove_homeowner(self, char):
        owners = self.db.owners or []
        if char in owners:
            owners.remove(char)
            self.remove_key(char)
            if char.home == self:
                char.home = ObjectDB.objects.get(id=13)
                char.save()
            self.db.owners = owners
            if not owners:
                self.del_home()

    def setup_home(self, owners=None, sethomespace=True):
        owners = utils.make_iter(owners)
        for owner in owners:
            self.add_homeowner(owner, sethomespace)
        self.tags.add("home")
        for ent in self.entrances:
            ent.locks.add("usekey: perm(builders) or roomkey(%s)" % self.id)
        if "HomeCmdSet" not in [ob.key for ob in self.cmdset.all()]:
            self.cmdset.add(HOMECMD, permanent=True)
        from world.dominion.models import AssetOwner

        try:
            # add our room owner as a homeowner if they're a player
            aowner = AssetOwner.objects.get(id=self.db.room_owner)
            char = aowner.player.player.char_ob
            if char not in owners:
                self.add_homeowner(char, False)
        except (AttributeError, AssetOwner.DoesNotExist, ValueError, TypeError):
            pass

    def del_home(self):
        if self.db.owners:
            self.db.owners = []
        self.tags.remove("home")
        for ent in self.entrances:
            ent.locks.add("usekey: perm(builders)")
            ent.item_data.is_locked = False
        if "HomeCmdSet" in [ob.key for ob in self.cmdset.all()]:
            self.cmdset.delete(HOMECMD)

    def setup_shop(self, owner):
        self.db.shopowner = owner
        self.tags.add("shop")
        if "ShopCmdSet" not in [ob.key for ob in self.cmdset.all()]:
            self.cmdset.add(SHOPCMD, permanent=True)
        self.db.discounts = {}
        self.db.crafting_prices = {}
        self.db.blacklist = []
        self.db.item_prices = {}

    def return_inventory(self):
        for o_id in self.db.item_prices or {}:
            obj = ObjectDB.objects.get(id=o_id)
            obj.move_to(self.db.shopowner)

    def del_shop(self):
        self.return_inventory()
        self.tags.remove("shop")
        if "ShopCmdSet" in [ob.key for ob in self.cmdset.all()]:
            self.cmdset.delete(SHOPCMD)
        self.attributes.remove("discounts")
        self.attributes.remove("crafting_prices")
        self.attributes.remove("blacklist")
        self.attributes.remove("shopowner")

    def msg_contents(
        self, text=None, exclude=None, from_obj=None, mapping=None, **kwargs
    ):
        """
        Emits something to all objects inside an object.

        exclude is a list of objects not to send to. See self.msg() for
                more info.
        """
        if not isinstance(text, str):
            try:
                message = text[0]
            except IndexError:
                message = ""
        else:
            message = text
        eventid = self.db.current_event
        gm_only = kwargs.pop("gm_msg", False)
        options = kwargs.get("options", {})
        if gm_only:
            exclude = exclude or []
            exclude = exclude + [
                ob for ob in self.contents if not ob.check_permstring("builders")
            ]
        # if we have an event at this location, log messages
        if eventid:
            from evennia.scripts.models import ScriptDB

            try:
                event_script = ScriptDB.objects.get(db_key="Event Manager")
                ooc = options.get("ooc_note", False)
                if gm_only or ooc:
                    event_script.add_gmnote(eventid, message)
                else:
                    event_script.add_msg(eventid, message, from_obj)
            except ScriptDB.DoesNotExist:
                if from_obj:
                    from_obj.msg("Error: Event Manager not found.")
        super(ArxRoom, self).msg_contents(
            text=message, exclude=exclude, from_obj=from_obj, mapping=mapping, **kwargs
        )

    def ban_character(self, character):
        if character not in self.banlist:
            self.banlist.append(character)

    def unban_character(self, character):
        if character in self.banlist:
            self.banlist.remove(character)

    @property
    def banlist(self):
        if self.db.banlist is None:
            self.db.banlist = []
        return self.db.banlist

    def check_banned(self, character):
        return character in self.banlist

    def add_bouncer(self, character):
        if character not in self.bouncers:
            self.bouncers.append(character)

    def remove_bouncer(self, character):
        if character in self.bouncers:
            self.bouncers.remove(character)

    @property
    def bouncers(self):
        if self.db.bouncers is None:
            self.db.bouncers = []
        return self.db.bouncers

    def add_decorator(self, character):
        if character not in self.decorators:
            self.decorators.append(character)

    def remove_decorator(self, character):
        if character in self.decorators:
            self.decorators.remove(character)

    @property
    def decorators(self):
        if self.db.decorators is None:
            self.db.decorators = []
        return self.db.decorators

    @property
    def places(self):
        from typeclasses.places.places import Place

        return [ob for ob in self.contents if isinstance(ob, Place)]

    # noinspection PyMethodMayBeStatic
    # noinspection PyUnusedLocal
    def at_say(
        self,
        message,
        msg_self=None,
        msg_location=None,
        receivers=None,
        msg_receivers=None,
        **kwargs
    ):
        return message

    def msg_action(self, from_obj, no_name_emit_string, exclude=None, options=None):
        if from_obj.is_disguised:
            exclude = exclude or []
            can_see = [
                ob for ob in self.player_characters if ob.truesight and ob != from_obj
            ]
            emit_string = "%s%s" % (
                "%s {c(%s){n" % (from_obj.name, from_obj.key),
                no_name_emit_string,
            )
            for character in can_see:
                character.msg(emit_string, options=options, from_obj=from_obj)
            exclude.extend(can_see)
        emit_string = "%s%s" % (from_obj, no_name_emit_string)
        self.msg_contents(
            emit_string,
            exclude=exclude,
            from_obj=from_obj,
            options=options,
            mapping=None,
        )


class CmdExtendedLook(default_cmds.CmdLook):
    """
    look

    Usage:
      look
      look <obj>
      look <room detail>
      look *<player>

    Observes your location, details at your location or objects in your vicinity.
    """

    arg_regex = r"\/|\s|$"
    # remove 'ls' alias because it just causes collisions with exit aliases
    aliases = ["l"]

    def check_detail(self):
        caller = self.caller
        location = caller.location
        if (
            location
            and hasattr(location, "return_detail")
            and callable(location.return_detail)
        ):
            detail = location.return_detail(self.args)
            if detail:
                # we found a detail instead. Show that.
                caller.msg(detail)
                return True

    def func(self):
        """
        Handle the looking - add fallback to details.
        """
        caller = self.caller
        args = self.args
        looking_at_obj = None
        if args:
            alist = args.split("'s ")
            if len(alist) == 2:
                obj = caller.search(alist[0], use_nicks=True, quiet=True)
                if obj:
                    obj = utils.make_iter(obj)
                    looking_at_obj = caller.search(
                        alist[1], location=obj[0], use_nicks=True, quiet=True
                    )
            else:
                looking_at_obj = caller.search(args, use_nicks=True, quiet=True)
            # originally called search with invalid arg of no_error or something instead of quiet
            if not looking_at_obj:
                # no object found. Check if there is a matching
                # detail at location.
                if self.check_detail():
                    return
                # no detail found. Trigger delayed error messages
                _AT_SEARCH_RESULT(looking_at_obj, caller, args, False)
                return
            else:
                # we need to extract the match manually.
                if len(utils.make_iter(looking_at_obj)) > 1:
                    _AT_SEARCH_RESULT(looking_at_obj, caller, args, False)
                    self.check_detail()
                    return
                looking_at_obj = utils.make_iter(looking_at_obj)[0]
        else:
            looking_at_obj = caller.location
            if not looking_at_obj:
                caller.msg("You have no location to look at!")
                return

        if not hasattr(looking_at_obj, "return_appearance"):
            # this is likely due to us having a player instead
            looking_at_obj = looking_at_obj.character
        if not looking_at_obj.access(caller, "view"):
            caller.msg("Could not find '%s'." % args)
            self.check_detail()
            return
        # get object's appearance
        desc = looking_at_obj.return_appearance(caller, detailed=False)
        caller.msg(desc)
        # the object's at_desc() method.
        looking_at_obj.at_desc(looker=caller)
        self.check_detail()


class CmdStudyRawAnsi(ArxCommand):
    """
    prints raw ansi codes for a name
    Usage:
        @study <obj>[=<player to send it to>]

    Prints raw ansi.
    """

    key = "@study"
    locks = "cmd:all()"

    def func(self):
        caller = self.caller
        ob = caller.search(self.lhs)
        if not ob:
            return
        targ = caller.player
        if self.rhs:
            targ = targ.search(self.rhs)
            if not targ:
                return
        from server.utils.arx_utils import raw

        if targ != caller:
            targ.msg("%s sent you this @study on %s: " % (caller, ob))
            caller.msg("Sent to %s." % targ)
        targ.msg("Escaped name: %s" % raw(ob.name))
        targ.msg("Escaped desc: %s" % raw(ob.desc))


# Custom build commands for setting seasonal descriptions
# and detailing extended rooms.


class CmdExtendedDesc(default_cmds.CmdDesc):
    """
    @desc - describe an object or room

    Usage:
      @desc [<obj> = <description>]
      @desc/char <character>=<description>
      @desc[/switch] <description>
      @detail[/del] [<key> = <description>]
      @detail/fix <key>=<string to replace>,<new string to replace it>


    Switches for @desc:
      spring  - set description for <season> in current room
      summer
      autumn
      winter

    Switch for @detail:
      del   - delete a named detail

    Sets the "desc" attribute on an object. If an object is not given,
    describe the current room.

    The alias @detail allows to assign a "detail" (a non-object
    target for the look command) to the current room (only).

    You can also embed special time markers in your room description, like this:
      <night>In the darkness, the forest looks foreboding.</night>. Text
    marked this way will only display when the server is truly at the given
    time slot. The available times
    are night, morning, afternoon and evening.

    Note that @detail, seasons and time-of-day slots only works on rooms in this
    version of the @desc command.

    """

    aliases = ["@describe", "@detail"]

    @staticmethod
    def reset_times(obj):
        """By deleteting the caches we force a re-load."""
        obj.ndb.last_season = None
        obj.ndb.last_timeslot = None

    def func(self):
        """Define extended command"""
        caller = self.caller
        location = caller.location
        if self.cmdstring == "@detail":
            # switch to detailing mode. This operates only on current location
            if not location:
                caller.msg("No location to detail!")
                return
            if not location.access(caller, "edit"):
                caller.msg("You do not have permission to use @desc here.")
                return

            if not self.args:
                # No args given. Return all details on location
                string = "{wDetails on %s{n:\n" % location
                string += "\n".join(
                    " {w%s{n: %s" % (key, utils.crop(text))
                    for key, text in location.db.details.items()
                )
                caller.msg(string)
                return
            if self.switches and self.switches[0] in "del":
                # removing a detail.
                if self.lhs in location.db.details:
                    del location.db.details[self.lhs]
                    caller.msg("Detail %s deleted, if it existed." % self.lhs)
                self.reset_times(location)
                return
            if self.switches and self.switches[0] in "fix":
                if not self.lhs or not self.rhs:
                    caller.msg("Syntax: @detail/fix key=old,new")
                fixlist = self.rhs.split(",")
                if len(fixlist) != 2:
                    caller.msg("Syntax: @detail/fix key=old,new")
                    return
                key = self.lhs
                try:
                    location.db.details[key] = location.db.details[key].replace(
                        fixlist[0], fixlist[1]
                    )
                except (KeyError, AttributeError):
                    caller.msg("No such detail found.")
                    return
                caller.msg(
                    "Detail %s has had text changed to: %s"
                    % (key, location.db.details[key])
                )
                return
            if not self.rhs:
                # no '=' used - list content of given detail
                if self.args in location.db.details:
                    string = "{wDetail '%s' on %s:\n{n" % (self.args, location)
                    string += location.db.details[self.args]
                    caller.msg(string)
                    return
            # setting a detail
            location.db.details[self.lhs] = self.rhs
            caller.msg("{wSet Detail %s to {n'%s'." % (self.lhs, self.rhs))
            self.reset_times(location)
            return
        else:
            # we are doing a @desc call
            if not self.args:
                if location:
                    string = "{wDescriptions on %s{n:\n" % location.key
                    string += " {wspring:{n %s\n" % location.db.spring_desc
                    string += " {wsummer:{n %s\n" % location.db.summer_desc
                    string += " {wautumn:{n %s\n" % location.db.autumn_desc
                    string += " {wwinter:{n %s\n" % location.db.winter_desc
                    string += " {wgeneral:{n %s" % location.db.general_desc
                    caller.msg(string)
                    return
            if self.switches and self.switches[0] in (
                "spring",
                "summer",
                "autumn",
                "winter",
            ):
                # a seasonal switch was given
                if self.rhs:
                    caller.msg("Seasonal descs only works with rooms, not objects.")
                    return
                switch = self.switches[0]
                if not location:
                    caller.msg("No location was found!")
                    return
                if not location.access(caller, "edit"):
                    caller.msg("You do not have permission to @desc here.")
                    return
                if switch == "spring":
                    location.db.spring_desc = self.args
                elif switch == "summer":
                    location.db.summer_desc = self.args
                elif switch == "autumn":
                    location.db.autumn_desc = self.args
                elif switch == "winter":
                    location.db.winter_desc = self.args
                # clear flag to force an update
                self.reset_times(location)
                caller.msg("Seasonal description was set on %s." % location.key)
            else:
                # Not seasonal desc set, maybe this is not an extended room
                if self.rhs:
                    text = self.rhs
                    if "char" in self.switches:
                        # if we're looking for a character, find them by player
                        # so we can @desc someone not in the room
                        caller = caller.player
                    obj = caller.search(self.lhs)
                    # if we did a search as a player, get the character object
                    if obj and obj.char_ob:
                        obj = obj.char_ob
                    if not obj:
                        return
                else:
                    caller.msg(
                        "You must have both an object to describe and the description."
                    )
                    caller.msg("Format: @desc <object>=<description>")
                    return
                if not obj.access(caller, "edit"):
                    caller.msg(
                        "You do not have permission to change the @desc of %s."
                        % obj.name
                    )
                    return
                obj.desc = self.rhs  # a compatability fallback
                if utils.inherits_from(obj, ExtendedRoom):
                    # this is an extendedroom, we need to reset
                    # times and set general_desc
                    obj.db.general_desc = text
                    self.reset_times(obj)
                    caller.msg("General description was set on %s." % obj.key)
                else:
                    caller.msg("The description was set on %s." % obj.key)


# Simple command to view the current time and season
class CmdGameTime(ArxCommand):
    """
    Check the game time and weather

    Usage:
      time
      time <YYYY/mm/dd[ HH:MM]>

    Shows the current in-game time, season, and the last weather emit, in case you
    missed it or have emits turned off.  (To turn off weather emits, use the
    @settings command to toggle the 'ignore_weather' setting.)

    The second format will show what the in-game date was for a given real date
    (and optional time).
    """

    key = "time"
    locks = "cmd:all()"
    help_category = "General"
    aliases = "weather"

    # noinspection PyUnusedLocal
    def get_help(self, caller, cmdset):
        return (
            self.__doc__
            + "\nGame time moves %s times faster than real time."
            % gametime.time_factor()
        )

    def func(self):
        """Reads time info from current room"""
        if self.args:
            parsed = None
            to_parse = self.args.strip()
            try:
                parsed = time.strptime(to_parse, "%Y/%m/%d %H:%M")
            except ValueError:
                try:
                    parsed = time.strptime(to_parse, "%Y/%m/%d")
                except ValueError:
                    pass

            if not parsed:
                self.msg(
                    "Unable to understand that date!  It must be in the format "
                    "|wYYYY/mm/dd|n or |wYYYY/mm/dd HH:MM|n to be understood."
                )
                return

            parsed = time.mktime(parsed)
            game_time = gametime.realtime_to_gametime(parsed)
            if game_time is None:
                self.msg(
                    "Real date |w{}|n was before the game started!".format(to_parse)
                )
                return
            from server.utils.arx_utils import get_date

            self.msg(
                "Real date |w{}|n was about |w{}|n in game time.".format(
                    to_parse, get_date(game_time)
                )
            )
            return

        location = self.caller.location
        if not location or not hasattr(location, "get_time_and_season"):
            self.msg("No location available - you are outside time.")
        else:
            season, timeslot = location.get_time_and_season()
            prep = "a"
            if season == "autumn":
                prep = "an"
            weather = weather_utils.get_last_emit()
            self.msg(
                "It's %s %s day, in the %s.  %s" % (prep, season, timeslot, weather)
            )
            time_tuple = gametime.gametime(format=True)
            hour, minute = time_tuple[4], time_tuple[5]
            from server.utils.arx_utils import get_date

            self.msg(
                "Today's date: %s. Current time: %s:%02d" % (get_date(), hour, minute)
            )


class CmdSetGameTimescale(ArxCommand):
    """
    Sets or checks the multiplier for the current IC timescale.

    Usage:
        timescale
        timescale/set <new>

    The first form of this command will display what the current time
    factor is, the speed at which IC time runs compared to normal time.
    The second form will set a new time factor.
    """

    key = "timescale"
    locks = "cmd:perm(Wizards)"

    def func(self):
        if "set" in self.switches:
            try:
                factor = float(self.args)
                gametime.set_time_factor(factor)
                self.msg("IC time now runs at {}:1 scale.".format(factor))
            except ValueError:
                self.msg("You need to provide a number for the new time factor.")
            return

        elif "history" in self.switches:
            from datetime import datetime
            from evennia.utils.evtable import EvTable

            table = EvTable("Real Time", "Game Date", "Multiplier")
            for tdict in gametime.time_intervals():
                dt = datetime.fromtimestamp(tdict["real"])
                ic_time = gametime._format(
                    tdict["game"],
                    gametime.YEAR,
                    gametime.MONTH,
                    gametime.WEEK,
                    gametime.DAY,
                    gametime.HOUR,
                    gametime.MIN,
                )
                month, day, year = ic_time[1] + 1, ic_time[3] + 1, ic_time[0] + 1001

                real_time = dt.strftime("%m/%d/%Y %H:%M")
                ic_timestamp = "{}/{}/{} {}:{}".format(
                    month, day, year, ic_time[4], ic_time[5]
                )

                multiplier = tdict["multiplier"]

                table.add_row(real_time, ic_timestamp, multiplier)

            self.msg(table)
            return

        factor = gametime.time_factor()
        self.msg("IC time is running at {}:1 scale".format(factor))


class TempRoom(ArxRoom):
    """
    A temporary room, which will reap itself when everyone has left.
    """

    def is_empty_except(self, obj):
        """
        Returns whether or not this room is currently empty of characters save the given object.
        :return: True if the room has no characters or NPCs in it, False if someone is present.
        """
        for con in self.contents:
            if con is not obj and (
                con.has_account or (hasattr(con, "is_character") and con.is_character)
            ):
                return False
        return True

    def at_object_leave(self, obj, target_location):
        """Override of at_object_leave hook for soft-deleting this room once it's empty"""
        if obj.has_account or (hasattr(obj, "is_character") and obj.is_character):
            if self.is_empty_except(obj):
                self.softdelete()
