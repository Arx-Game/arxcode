"""
Module for a number of social commands that we'll add for players. Most
will be character commands, since they'll deal with the grid.
"""
import time
import random
from datetime import datetime, timedelta
from functools import reduce

from django.conf import settings
from django.db.models import Q

from server.utils.arx_utils import list_to_string
from commands.base import ArxCommand, ArxPlayerCommand
from evennia.objects.models import ObjectDB
from evennia.typeclasses.tags import Tag
from evennia.utils.evtable import EvTable
from evennia.utils.utils import make_iter
from evennia.scripts.models import ScriptDB

from commands.base_commands.roster import format_header
from commands.mixins import RewardRPToolUseMixin
from server.utils.exceptions import PayError, CommandError
from server.utils.prettytable import PrettyTable
from server.utils.arx_utils import (
    inform_staff,
    time_from_now,
    inform_guides,
    commafy,
    a_or_an,
    get_full_url,
)
from typeclasses.characters import Character
from typeclasses.rooms import ArxRoom
from web.character.models import AccountHistory, FirstContact
from world.crafting.models import (
    CraftingMaterialType,
    OwnedMaterial,
)
from world.dominion.forms import RPEventCreateForm
from world.dominion.models import (
    RPEvent,
    Agent,
    AssetOwner,
    Reputation,
    Member,
    PlotRoom,
    Organization,
    InfluenceCategory,
    PlotAction,
    PrestigeAdjustment,
    PrestigeCategory,
    PrestigeNomination,
)
from world.msgs.models import Journal, Messenger
from world.msgs.managers import reload_model_as_proxy
from world.stats_and_skills import do_dice_check

from paxforms import forms, fields
from paxforms.paxform_commands import PaxformCommand


def char_name(character_object, verbose_where=False, watch_list=None):
    """
    Formats the name of character_object
    Args:
        character_object: Character object to format the name of
        verbose_where: Whether to add room title
        watch_list: List of characters that are being watched, for highlighting

    Returns:
        String of formatted character name
    """
    watch_list = watch_list or []
    cname = character_object.name
    if character_object in watch_list:
        cname += "{c*{n"
    if character_object.player_ob and character_object.player_ob.db.lookingforrp:
        cname += "|R+|n"
    if not verbose_where:
        return cname
    if character_object.db.room_title:
        cname += "{w(%s){n" % character_object.db.room_title
    return cname


def get_char_names(charlist, caller):
    """
    Formats a string of names from list of characters
    Args:
        charlist: Character list to format
        caller: Character object to check settings/permissions

    Returns:
        String that's a list of names
    """
    watch_list = caller.db.watching or []
    verbose_where = False
    if caller.tags.get("verbose_where"):
        verbose_where = True
    return ", ".join(
        char_name(char, verbose_where, watch_list)
        for char in charlist
        if char.player
        and (not char.player.db.hide_from_watch or caller.check_permstring("builders"))
    )


class CmdHangouts(ArxCommand):
    """
    +hangouts

    Usage:
        +hangouts
        +hangouts/all

    Shows the public rooms marked as hangouts, displaying the players
    there. They are the rooms players gather in when they are seeking
    public scenes welcome to anyone.
    """

    key = "+hangouts"
    locks = "cmd:all()"
    help_category = "Travel"

    def func(self):
        """Execute command."""
        caller = self.caller
        oblist = ArxRoom.objects.filter(db_tags__db_key="hangouts")
        if "all" not in self.switches:
            oblist = oblist.filter(
                locations_set__db_typeclass_path=settings.BASE_CHARACTER_TYPECLASS
            )
        oblist = oblist.distinct()
        caller.msg(format_header("Hangouts"))
        self.msg("Players who are currently LRP have a |R+|n by their name.")
        if not oblist:
            caller.msg("No hangouts are currently occupied.")
            return
        for room in oblist:
            char_names = get_char_names(room.get_visible_characters(caller), caller)
            if char_names or "all" in self.switches:
                name = room.name
                if room.db.x_coord is not None and room.db.y_coord is not None:
                    pos = (room.db.x_coord, room.db.y_coord)
                    name = "%s %s" % (name, str(pos))
                if char_names:
                    name += ": %s" % char_names
                caller.msg(name)


class CmdWhere(ArxPlayerCommand):
    """
    +where

    Usage:
        +where
        +where [<character>,<character 2>,...]
        +where/shops [<ability>]
        +where/shops/all [<ability>]
        +where/randomscene
        +where/watch
        +where/firstimpression

    Displays a list of characters in public rooms. The /shops switch
    lets you see a list of shops. /watch filters results by characters in
    your watchlist, while /randomscene filters by characters you can claim.
    """

    key = "+where"
    locks = "cmd:all()"
    help_category = "Travel"
    randomscene_switches = ("rs", "randomscene", "randomscenes")
    firstimp_switches = ("firstimp", "firstimpression", "firstimpressions", "fi", "fp")
    filter_switches = randomscene_switches + firstimp_switches

    @staticmethod
    def get_room_str(room):
        """Returns formatted room name"""
        name = room.name
        if room.db.x_coord is not None and room.db.y_coord is not None:
            pos = (room.db.x_coord, room.db.y_coord)
            name = "%s %s" % (name, str(pos))
        return name

    def list_shops(self):
        """Sends msg of list of shops to caller"""
        rooms = ArxRoom.objects.filter(db_tags__db_key__iexact="shop").order_by(
            "db_key"
        )
        msg = "{wList of shops:{n"
        for room in rooms:
            owner = room.db.shopowner
            if self.args and owner:
                if self.args.lower() not in owner.traits.abilities:
                    continue
            name = owner.key
            if owner and not owner.roster.roster.name == "Active":
                if "all" not in self.switches:
                    continue
                name += " {w(Inactive){n"
            msg += "\n%s: %s" % (self.get_room_str(room), name)
        self.msg(msg)

    def func(self):
        """"Execute command."""
        caller = self.caller
        if "shops" in self.switches:
            self.list_shops()
            return
        characters = Character.objects.filter(Q(roster__roster__name="Active")).exclude(
            db_tags__db_key__iexact="disguised"
        )
        if self.args:
            name_list = map(lambda n: Q(db_key__iexact=n), self.lhslist)
            name_list = reduce(lambda a, b: a | b, name_list)
            characters = [
                ob.id
                for ob in characters.filter(name_list)
                if not ob.player_ob.db.hide_from_watch
            ]
        rooms = (
            ArxRoom.objects.exclude(db_tags__db_key__iexact="private")
            .filter(locations_set__in=characters)
            .distinct()
            .order_by("db_key")
        )
        if not rooms:
            self.msg("No visible characters found.")
            return
        # this blank line is now a love note to my perfect partner. <3
        msg = " {wLocations of players:\nPlayers who are currently LRP have a |R+|n by their name, "
        msg += "and players who are on your watch list have a {c*{n by their name."
        applicable_chars = []
        if self.check_switches(self.randomscene_switches):
            cmd = CmdRandomScene()
            cmd.caller = caller.char_ob
            applicable_chars = list(cmd.scenelist) + [
                ob for ob in cmd.newbies if ob not in cmd.claimlist
            ]
        elif self.check_switches(self.firstimp_switches):
            applicable_chars = [
                ob.entry.character
                for ob in AccountHistory.objects.unclaimed_impressions(caller.roster)
            ]
        for room in rooms:
            # somehow can get Character in queryset rather than ArxRoom
            if not hasattr(room, "get_visible_characters"):
                from evennia.utils.logger import log_err

                log_err(
                    "Object ID: %s is not a room despite being from ArxRoom queryset."
                    % room.id
                )
                continue
            charlist = sorted(room.get_visible_characters(caller), key=lambda x: x.name)
            charlist = [
                ob
                for ob in charlist
                if not ob.player_ob.db.hide_from_watch and not ob.is_disguised
            ]
            if self.check_switches(self.filter_switches):
                charlist = [ob for ob in charlist if ob in applicable_chars]
            elif "watch" in self.switches:
                watching = caller.db.watching or []
                matches = [ob for ob in charlist if ob in watching]
                if not matches:
                    continue
            char_names = get_char_names(charlist, caller)
            if not char_names:
                continue
            room_name = self.get_room_str(room)
            msg += "\n%s: %s" % (room_name, char_names)
        self.msg(msg)


class CmdWatch(ArxPlayerCommand):
    """
    +watch

    Usage:
        +watch
        +watch <character>
        +watch/stop <character>
        +watch/hide

    Starts watching a player, letting you know when they
    go IC or stop being IC. If +watch/hide is set, you cannot
    be watched by anyone.
    """

    key = "+watch"
    locks = "cmd:all()"
    help_category = "Social"
    max_watchlist_size = 50

    @staticmethod
    def disp_watchlist(caller):
        """Display watchlist to caller"""
        watchlist = caller.db.watching or []
        if not watchlist:
            caller.msg("Not watching anyone.")
            return
        table = []
        for ob in sorted(watchlist, key=lambda x: x.key):
            name = ob.key.capitalize()
            if ob.player_ob.is_connected and not ob.player_ob.db.hide_from_watch:
                name = "{c*%s{n" % name
            table.append(name)
        caller.msg(
            "Currently watching (online players are highlighted):\n%s"
            % ", ".join(table),
            options={"box": True},
        )
        if caller.db.hide_from_watch:
            caller.msg("You are currently in hidden mode.")
        return

    def func(self):
        """Execute command."""
        caller = self.caller
        if not self.args and not self.switches:
            self.disp_watchlist(caller)
            return
        if "hide" in self.switches:
            hide = caller.db.hide_from_watch or False
            hide = not hide
            caller.msg("Hiding set to %s." % str(hide))
            caller.db.hide_from_watch = hide
            return
        player = caller.search(self.args)
        if not player:
            return
        char = player.char_ob
        if not char:
            caller.msg("No character found.")
            return
        watchlist = caller.db.watching or []
        if "stop" in self.switches:
            if char not in watchlist:
                caller.msg("You are not watching %s." % char.key)
                return
            # stop watching them
            watchlist.remove(char)
            caller.db.watching = watchlist
            watched = char.db.watched_by or []
            if caller in watched:
                watched.remove(caller)
                char.db.watched_by = watched
            caller.msg("Stopped watching %s." % char.key)
            return
        if len(watchlist) >= self.max_watchlist_size:
            self.msg(
                "You may only have %s characters on your watchlist."
                % self.max_watchlist_size
            )
            return
        if char in watchlist:
            caller.msg("You are already watching %s." % char.key)
            return
        watched = char.db.watched_by or []
        if caller not in watched:
            watched.append(caller)
            char.db.watched_by = watched
        watchlist.append(char)
        caller.db.watching = watchlist
        caller.msg("You start watching %s." % char.key)


class CmdFinger(ArxPlayerCommand):
    """
    +finger

    Usage:
        +finger <character>
        +finger/preferences <note on RP preferences>
        +finger/playtimes <note on your playtimes>

    Displays information about a given character. To set RP hooks, use the
    +rphooks command. Use the 'preferences' or 'playtimes' switches to add
    information about your RP preferences or your playtimes to your finger
    information.
    """

    key = "+finger"
    locks = "cmd:all()"
    help_category = "Social"

    def func(self):
        """Execute command."""
        caller = self.caller
        if "preferences" in self.switches:
            if self.args:
                caller.db.rp_preferences = self.args
                self.msg("RP preferences set to: %s" % self.args)
            else:
                caller.attributes.remove("rp_preferences")
                self.msg("RP preferences removed.")
            return
        if "playtimes" in self.switches:
            if self.args:
                caller.db.playtimes = self.args
                self.msg("Note on playtimes set to: %s" % self.args)
            else:
                caller.attributes.remove("playtimes")
                self.msg("Note on playtimes removed.")
            return
        show_hidden = caller.check_permstring("builders")
        if not self.args:
            caller.msg("You must supply a character name to +finger.")
            return
        player = caller.search(self.args)
        if not player:
            return
        char = player.char_ob
        if not char:
            caller.msg("No character found.")
            return
        viewing_own_character = player == caller
        name = char.db.longname or char.key
        msg = "\n{wName:{n %s\n" % name
        titles = char.titles
        if titles:
            msg += "{wFull Titles:{n %s\n" % titles
        try:
            if char.roster.show_positions:
                positions = char.player_ob.player_positions.all()
                if positions:
                    msg += "{wOOC Positions: {n%s\n" % ", ".join(
                        str(pos) for pos in positions
                    )
        except AttributeError:
            pass
        try:
            rost = str(char.roster.roster)
            roster_status = "{n, currently"
            if rost == "Gone":
                rost = "{rGone{n"
            elif rost == "Active":
                rost = "{cActive{n"
            elif rost == "Inactive":
                rost = "{yInactive{n"
            elif rost == "Available":
                rost = "{gAvailable{n"
            else:
                raise AttributeError
            roster_status += " %s" % rost
        except AttributeError:
            roster_status = ""
        if "rostercg" in char.tags.all():
            msg += "{wRoster Character%s{n\n" % roster_status
        else:
            msg += "{wOriginal Character%s{n\n" % roster_status
        if show_hidden:
            msg += "{wCharID:{n %s, {wPlayerID:{n %s\n" % (char.id, player.id)
            msg += "{wTotal Posecount:{n %s\n" % char.total_posecount
        if char.db.obituary:
            msg += "{wObituary:{n %s\n" % char.db.obituary
        else:
            session = player.get_all_sessions() and player.get_all_sessions()[0]
            if session and player.show_online(caller):
                idle_time = time.time() - session.cmd_last_visible
                idle = "Online and is idle" if idle_time > 1200 else "Online, not idle"
                msg += "{wStatus:{n %s\n" % idle
            else:
                last_online = (
                    player.last_login
                    and player.last_login.strftime("%m-%d-%y")
                    or "Never"
                )
                msg += "{wStatus:{n Last logged in: %s\n" % last_online
        fealty = char.db.fealty or "None"
        msg += "{wFealty:{n %s\n" % fealty

        quote = char.db.quote
        if quote:
            msg += "{wQuote:{n %s\n" % quote
        msg += "{wCharacter page:{n %s\n" % get_full_url(char.get_absolute_url())
        if show_hidden or viewing_own_character:
            orgs = player.current_orgs
        else:
            orgs = player.public_orgs
        if orgs:
            org_str = ""
            apply_buffer = False
            secret_orgs = player.secret_orgs
            for org in orgs:
                s_buffer = ""
                if apply_buffer:
                    s_buffer = " " * 15

                def format_org_name(organization):
                    """Returns the formatted string of an organization name"""
                    secret_str = (
                        "" if organization not in secret_orgs else " {m(Secret){n"
                    )
                    return "%s%s" % (organization.name, secret_str)

                org_str += "%s%s: %s\n" % (
                    s_buffer,
                    format_org_name(org),
                    get_full_url(org.get_absolute_url()),
                )
                apply_buffer = True
            msg += "{wOrganizations:{n %s" % org_str
        hooks = player.tags.get(category="rp hooks")
        if hooks:
            hooks = make_iter(hooks)
            hook_descs = player.db.hook_descs or {}
            msg += "{wRP Hooks:{n\n%s\n" % "\n".join(
                "%s: %s" % (hook, hook_descs.get(hook, "")) for hook in hooks
            )
        playtimes = player.db.playtimes
        if playtimes:
            msg += "{wPlaytimes:{n %s\n" % playtimes
        prefs = player.db.rp_preferences
        if prefs:
            msg += "{wRP Preference Notes:{n %s\n" % prefs
        caller.msg(msg, options={"box": True})


# for a character writing in their White Journal or Black Reflection
class CmdJournal(ArxCommand):
    """
    journal

    Usage:
        journal [<entry number>]
        journal <character>[=<entry number>]
        journal/search <character>=<text or tags to search for>
        journal/write <text>
        journal/event <event name>=<text>
        journal/black [<entry number>]
        journal/black <character>[=<entry number>]
        journal/addblack <text>
        journal/blackevent <event name>=<text>
        journal/index <character>[=<number of entries>]
        journal/blackindex <number of entries>
        journal/all
        journal/edit <entry number>=<text>
        journal/editblack <entry number>=<text>
        journal/delete <entry number>
        journal/delblack <entry number>
        journal/markallread
        journal/favorite <character>=<entry number>
        journal/unfavorite <character>=<entry number>
        journal/dispfavorites
        journal/countweek

    Allows a character to read the White Journals of characters,
    or add to their own White Journal or Black Reflections. White
    Journals are public notes that are recorded by the scribes of
    Vellichor for all to see, while Black Reflections are sealed notes
    that are kept private until after the character is deceased and then
    only released if explicitly stated to do so in their will, along with
    the concurrence of their family and the Scholars of Vellichor.

    The edit function is only to fix typographical errors. ICly, the content
    of journals can never be altered once written. Only use it to fix
    formatting or typos.
    """

    key = "journal"
    locks = "cmd:all()"
    help_category = "Social"

    def journal_index(self, character, j_list):
        """
        Gets a formatted table of a character's journals
        Args:
            character: Character who we're getting the journals for
            j_list: list of journals

        Returns:
            String that's a formatted PrettyTable
        """
        num = 1
        table = PrettyTable(["{w#{n", "{wWritten About{n", "{wDate{n", "{wUnread?{n"])
        fav_tag = "pid_%s_favorite" % self.caller.player_ob.id
        for entry in j_list:
            try:
                event = character.messages.get_event(entry)
                name = ", ".join(ob.key for ob in entry.db_receivers_objects.all())
                if event and not name:
                    name = event.name[:25]
                if fav_tag in entry.tags.all():
                    str_num = str(num) + "{w*{n"
                else:
                    str_num = str(num)
                unread = "" if self.caller.player_ob in entry.receivers else "{wX{n"
                date = character.messages.get_date_from_header(entry)
                table.add_row([str_num, name, date, unread])
                num += 1
            except (AttributeError, RuntimeError, ValueError, TypeError):
                continue
        return str(table)

    def disp_unread_journals(self):
        """Sends a list of all journals the caller hasn't read to them"""
        caller = self.caller
        msgs = Journal.white_journals.all_unread_by(self.caller.player_ob).order_by(
            "-db_date_created"
        )
        msgs = [msg.id for msg in msgs]
        if len(msgs) > 500:
            self.msg("Truncating some matches.")
        msgs = msgs[:500]
        all_writers = (
            ObjectDB.objects.filter(
                Q(sender_object_set__in=msgs)
                & ~Q(roster__current_account=caller.roster.current_account)
            )
            .distinct()
            .order_by("db_key")
        )
        msg_list = []
        for writer in all_writers:
            count = writer.sender_object_set.filter(id__in=msgs).count()
            msg_list.append("{C%s{c(%s){n" % (writer.key, count))
        caller.msg("Writers with journals you have not read: %s" % ", ".join(msg_list))

    def disp_favorite_journals(self):
        """Sends a list of all the journals the caller has favorited"""
        caller = self.caller
        msgs = Journal.white_journals.favorites_of(caller).order_by("-db_date_created")
        msgs = [msg.id for msg in msgs]
        if len(msgs) > 500:
            self.msg("Truncating some matches.")
        msgs = msgs[:500]
        all_writers = (
            ObjectDB.objects.filter(
                Q(sender_object_set__in=msgs)
                & ~Q(roster__current_account=caller.roster.current_account)
            )
            .distinct()
            .order_by("db_key")
        )
        msglist = []
        for writer in all_writers:
            count = writer.sender_object_set.filter(id__in=msgs).count()
            if count:
                msglist.append("{C%s{c(%s){n" % (writer.key, count))
        caller.msg("Writers with journals you have favorited: %s" % ", ".join(msglist))

    def mark_all_read(self):
        """Marks the caller as having read all journals"""
        caller = self.caller
        player = caller.player_ob
        all_msgs = Journal.white_journals.all_unread_by(player)
        # we'll do a bulk create of the through-model that represents how journals are marked as read
        ReadJournalModel = Journal.db_receivers_accounts.through
        bulk_list = []
        for msg in all_msgs:
            bulk_list.append(ReadJournalModel(accountdb=player, msg=msg))
        ReadJournalModel.objects.bulk_create(bulk_list)

    def func(self):
        """Execute command."""
        caller = self.caller
        num = 1
        # if no arguments, caller's journals
        if not self.args and not self.switches:
            char = caller
            white = "black" not in self.switches
            j_name = "White Journal" if white else "Black Reflection"
            # display caller's latest white or black journal entry
            try:
                self.msg(
                    "Number of entries in your %s: %s"
                    % (j_name, char.messages.size(white))
                )
                self.msg(
                    char.messages.disp_entry_by_num(
                        num=num, white=white, caller=caller.player_ob
                    ),
                    options={"box": True},
                )
            except IndexError:
                caller.msg("No journal entries written yet.")
            self.disp_unread_journals()
            return
        if "dispfavorites" in self.switches or "favorites" in self.switches:
            self.disp_favorite_journals()
            return
        if "markallread" in self.switches:
            self.mark_all_read()
            caller.msg("All messages marked read.")
            return
        if "countweek" in self.switches:
            num = caller.messages.num_weekly_journals
            self.msg("You have written %s journals this week." % num)
            return
        # if no switches but have args, looking up journal of a character
        if (
            not self.switches
            or "black" in self.switches
            or "favorite" in self.switches
            or "unfavorite" in self.switches
        ):
            white = "black" not in self.switches
            try:
                if not self.args:
                    char = caller
                    num = 1
                else:
                    if self.lhs.isdigit():
                        num = int(self.lhs)
                        char = caller
                    else:
                        # search as a player to make it global
                        char = caller.player.search(self.lhs)
                        # get character object from player we found
                        char = char.char_ob
                        if not char:
                            raise AttributeError
                        # display their latest white journal entry of the character
                        if not self.rhs:
                            num = 1
                        else:
                            num = int(self.rhs)
                    if num < 1:
                        caller.msg("Journal entry number must be at least 1.")
                        return
                journal = (
                    char.messages.white_journal
                    if white
                    else char.messages.black_journal
                )
                if "favorite" in self.switches or "unfavorite" in self.switches:
                    try:
                        entry = journal[num - 1]
                        if "favorite" in self.switches:
                            entry.tag_favorite(caller.player_ob)
                            self.msg("Entry added to favorites.")
                        else:
                            entry.untag_favorite(caller.player_ob)
                            self.msg("Entry removed from favorites.")
                        return
                    except (IndexError, AttributeError, ValueError, TypeError):
                        self.msg("No such entry to tag as a favorite.")
                        return
                msg = char.messages.disp_entry_by_num(
                    num, white=white, caller=caller.player_ob
                )
                # if we fail access check, we have 'False' instead of a msg
                if msg is None:
                    caller.msg("Empty entry.")
                    return
                if not msg:
                    caller.msg("You do not have permission to read that.")
                    return
                caller.msg(
                    "Number of entries for {c%s{n's %s journal: %s"
                    % (char, "white" if white else "black", len(journal))
                )
                caller.msg(msg, options={"box": True})
            except AttributeError:
                caller.msg("No player found for %s." % self.lhs)
                return
            except (ValueError, TypeError):
                caller.msg("You must provide a number for an entry.")
                return
            except IndexError:
                if num == 1:
                    caller.msg("No journal entries written yet.")
                    return
                caller.msg(
                    "You must provide a number that matches one of their entries."
                )
                return
            return
        # creating a new black or white journal
        if (
            "write" in self.switches
            or "addblack" in self.switches
            or "event" in self.switches
            or "blackevent" in self.switches
        ):
            white = (
                "addblack" not in self.switches and "blackevent" not in self.switches
            )
            if not self.lhs:
                caller.msg("You cannot add a blank entry.")
                return
            if "event" in self.switches or "blackevent" in self.switches:
                if not self.rhs:
                    caller.msg("You must specify a comment for the event.")
                    return
                try:
                    event = RPEvent.objects.get(name__iexact=self.lhs)
                    entry = caller.messages.add_event_journal(
                        event, self.rhs, white=white
                    )
                except RPEvent.DoesNotExist:
                    caller.msg("Could not find an event by that name.")
                    return
            else:
                entry = caller.messages.add_journal(self.lhs, white=white)
            caller.msg(
                "New %s added:" % ("white journal" if white else "black reflection")
            )
            caller.msg(caller.messages.disp_entry(entry), options={"box": True})
            if white:
                caller.msg_watchlist(
                    "A player you are watching, {c%s{n, has updated their white journal."
                    % caller.key
                )
            return
        if "search" in self.switches:
            rhs = self.rhs
            if not rhs:
                char = caller
                rhs = self.args
            else:
                char = caller.player.search(self.lhs)
                if not char:
                    return
                char = char.char_ob
                if not char:
                    caller.msg("No character found.")
                    return
            entries = char.messages.search_journal(rhs)
            if not entries:
                caller.msg("No matches.")
                return
            journal = char.messages.white_journal
            white_matches = [
                journal.index(entry) + 1 for entry in entries if entry in journal
            ]
            caller.msg(
                "White journal matches: %s"
                % ", ".join("#%s" % str(num) for num in white_matches)
            )
        if "index" in self.switches or "blackindex" in self.switches:
            num = 20
            if not self.lhs:
                char = caller
            elif self.lhs.isdigit():
                char = caller
                num = int(self.lhs)
            else:
                try:
                    char = caller.player.search(self.lhs).char_ob
                except AttributeError:
                    caller.msg("Character not found.")
                    return
            if self.rhs:
                try:
                    num = int(self.rhs)
                except ValueError:
                    caller.msg("Number of entries must be a number.")
                    return
            if "blackindex" in self.switches:
                if char != caller and not caller.check_permstring("builders"):
                    caller.msg("You can only see your own black journals.")
                    return
                journal = char.messages.black_journal
            else:
                journal = char.messages.white_journal
            caller.msg("{wJournal Entries for {c%s{n" % char)
            caller.msg(self.journal_index(char, journal[:num]))
            return
        if "all" in self.switches:
            self.disp_unread_journals()
            return
        if (
            "edit" in self.switches
            or "editblack" in self.switches
            or "delete" in self.switches
            or "delblack" in self.switches
        ):
            journal = (
                caller.messages.white_journal
                if ("edit" in self.switches or "delete" in self.switches)
                else caller.messages.black_journal
            )
            delete = "delete" in self.switches or "delblack" in self.switches
            try:
                num = int(self.lhs)
                text = self.rhs
                if num < 1 or (not text and not delete):
                    raise ValueError
                entry = journal[num - 1]
            except (TypeError, ValueError):
                caller.msg("Must provide a journal entry number and replacement text.")
                return
            except IndexError:
                caller.msg("No entry by that number.")
                return
            now = datetime.now()
            if (now - entry.db_date_created).days > 2:
                caller.msg("It has been too long to edit that message.")
                return
            old = entry.db_message
            if "delete" in self.switches or "delblack" in self.switches:
                journal.remove(entry)
                entry.delete()
                self.msg("Entry deleted.")
            else:
                entry.db_message = self.rhs
                entry.save()
            logpath = settings.LOG_DIR + "/journal_changes.txt"
            try:
                log = open(logpath, "a+")
                msg = "*" * 78
                msg += "\nJournal Change by %s\nOld:\n%s\nNew:\n%s\n" % (
                    caller,
                    old,
                    self.rhs,
                )
                msg += "*" * 78
                msg += "\n\n"
                log.write(msg)
            except IOError:
                import traceback

                traceback.print_exc()
            caller.msg("New journal entry body is:\n%s" % self.rhs)
            inform_staff(
                "%s has %s their journal." % (caller, "deleted" if delete else "edited")
            )
            return
        caller.msg("Invalid switch.")
        return


class CmdPosebreak(ArxCommand):
    """
    +posebreak

    Usage:
        +posebreak

    Toggles on or off a linebreak between poses.
    """

    key = "+posebreak"
    locks = "cmd:all()"
    help_category = "Settings"

    def func(self):
        """Execute command."""
        caller = self.caller
        if caller.db.posebreak:
            caller.db.posebreak = False
        else:
            caller.db.posebreak = True
        caller.msg("Pose break set to %s." % caller.db.posebreak)
        return


class CmdMessenger(ArxCommand):
    """
    messenger

    Usage:
        messenger
        messenger <receiver>[,<receiver2>,...]=<message>
        messenger/receive
        messenger/deliver <receivers>|<object>[,<money>][,<mat>/<amt>]=<msg>
        messenger/money <receivers>|<amount>=<message>
        messenger/materials <receivers>|<material>/<amount>=<message>
        messenger/old <number>
        messenger/oldindex <amount to display>
        messenger/sent <number>
        messenger/sentindex <amount to display>
        messenger/delete <number>
        messenger/forward <number>=<target>[,<target 2>,..]
        messenger/preserve <number>
        messenger/draft <receiver>=<message>
        messenger/proof
        messenger/send
        messenger/discreet <retainer ID>
        messenger/custom <retainer ID>
        messenger/spoof <name for messages you send>

    Dispatches or receives in-game messengers. Messengers are an
    abstraction of any IC communication through distances - they
    can be people sent as messengers, courier ravens, whatever, as
    long as it's largely a letter being delivered personally to a
    receiving character. You can also deliver objects with the 'deliver'
    command.

    To draft a message before sending it, use the 'draft' switch, review
    your message with 'proof', and then finally send it with 'send'.

    When sending deliveries, you can specify more than one receiver. If you
    are delivering an object, it will be sent to the first receiver you list.
    Money and crafting materials are sent to each person listed, charging you
    the total. For example, 'messenger/money copper,prism|50=hi!' would cost
    a total of 100 silver.

    For turning off messenger notifications, see @settings.
    """

    key = "messenger"
    locks = "cmd:all()"
    aliases = [
        "messengers",
        "receive messenger",
        "receive messengers",
        "receive messages",
        "message",
    ]
    help_category = "Social"
    delivery_switches = ("deliver", "money", "materials", "silver")

    def disp_messenger(self, msg):
        """Displays msg to caller, reloads it as correct proxy class if necessary"""
        try:
            self.caller.messages.display_messenger(msg)
        except AttributeError:
            msg = reload_model_as_proxy(msg)
            self.caller.messages.display_messenger(msg)

    def get_mats_from_args(self, args):
        """
        Get crafting materials to send from caller
        Args:
            args (str): String we parse for materials

        Returns:
            mats (tuple): tuple of (Material's ID, amount)
        """
        try:
            lhslist = args.split("/")
            material = CraftingMaterialType.objects.get(name__iexact=lhslist[0])
            amt = int(lhslist[1])
            if amt < 1:
                raise ValueError(
                    "You must specify a positive value of a material to send."
                )
        # different errors
        except (IndexError, AttributeError, TypeError):
            self.msg("You must specify materials to send.")
        except CraftingMaterialType.DoesNotExist:
            self.msg("That is not a valid material type.")
        except OwnedMaterial.DoesNotExist:
            self.msg("You don't have any of that material.")
        except ValueError as err:
            self.msg(err)
        # succeeded, return amount. It'll be decremented when sent off later
        else:
            return material.id, amt

    def set_or_remove_retainer_ability(self, attr_name, attr_desc):
        """
        Sets or removes customization options for messengers based on our retainers, such as the ability
        to send custom messengers, or to receive them discreetly.

            Args:
                attr_name (str): name of the Attribute to check/set
                attr_desc (str): A phrase of what the attr makes retainers do, to send to players.
        """
        caller = self.caller
        handler = caller.messages
        if not self.args:
            if not getattr(handler, attr_name):
                self.msg("You are not using a retainer to %s." % attr_desc)
                return
            setattr(handler, attr_name, None)
            return
        try:
            if self.args.isdigit():
                obj = caller.player_ob.retainers.get(id=self.args).dbobj
            else:
                obj = caller.player_ob.retainers.get(
                    agent_objects__dbobj__db_key__iexact=self.args
                ).dbobj
        except (Agent.DoesNotExist, ValueError):
            self.msg("No retainer by that ID.")
        except AttributeError:
            self.msg("That agent cannot %s." % attr_desc)
        else:
            if obj.traits.get_ability_value(attr_name):
                setattr(handler, attr_name, obj)
            else:
                self.msg("%s does not have the ability to %s." % (obj, attr_desc))

    def display_messenger_status(self):
        """Displays short msg to caller of number of read and unread messengers they have."""
        caller = self.caller
        unread = caller.messages.pending_messengers
        read = caller.messages.messenger_history
        if not (read or unread):
            caller.msg(
                "You have no messengers waiting for you, and have never received any messengers."
                + " {wEver{n. At all. Not {rone{n."
            )
        if read:
            caller.msg("You have {w%s{n old messages you can re-read." % len(read))
        if unread:
            caller.msg(
                "{mYou have {w%s{m new messengers waiting to be received." % len(unread)
            )

    def check_cannot_use_messengers(self, target):
        """
        Checks if the target can receive messengers. If not, we send an error message.
        Args:
            target: Character to check

        Returns:
            True if they can't receive messengers, False if they can.
        """
        fail = False
        if self.caller.check_permstring("builders"):
            return fail
        if target.tags.get("no_messengers"):
            fail = True
        elif target.location and target.location.tags.get("no_messengers"):
            fail = True
        elif target.combat.combat and target in target.combat.combat.ndb.combatants:
            fail = True
        if fail:
            self.msg("%s cannot send or receive messengers at the moment." % target.key)
        return fail

    def func(self):
        """Execute command."""
        caller = self.caller
        # Display the number of old messages we have, and list whether
        # we have new messengers waiting
        cmdstr = getattr(self, "cmdstring", "messenger")
        if (
            cmdstr == "receive messenger"
            or cmdstr == "receive messengers"
            or cmdstr == "receive messages"
        ):
            self.switches.append("receive")
        if not self.args and not self.switches:
            self.display_messenger_status()
            return
        if "spoof" in self.switches:
            if not caller.check_permstring("builders"):
                self.msg("GM only command for now.")
                return
            caller.messages.spoofed_name = self.args
            return
        if "discreet" in self.switches or "custom" in self.switches:
            if "discreet" in self.switches:
                attr_name = "discreet_messenger"
                attr_desc = "receive messages discreetly"
            else:
                attr_name = "custom_messenger"
                attr_desc = "deliver messages for you"
            self.set_or_remove_retainer_ability(attr_name, attr_desc)
            return
        # get the first new messenger we have waiting
        if "receive" in self.switches:
            if self.check_cannot_use_messengers(self.caller):
                return
            caller.messages.receive_pending_messenger()
            return
        # display an old message
        if (
            "old" in self.switches
            or "delete" in self.switches
            or "oldindex" in self.switches
            or "preserve" in self.switches
            or "forward" in self.switches
            or "save" in self.switches
        ):
            old = caller.messages.messenger_history
            if not old:
                caller.msg(
                    "You have never received a single messenger ever. Not a single one. "
                    + "Not even a death threat. {wNothing{n."
                )
                return
            if not self.args or "oldindex" in self.switches:
                try:
                    num_disp = int(self.args)
                except (TypeError, ValueError):
                    num_disp = 30
                # display a prettytable of message number, sender, IC date
                self.display_received_table(num_disp, old)
                return
            try:
                num = int(self.lhs)
                if num < 1:
                    raise ValueError
                msg = old[num - 1]
                if "forward" in self.switches:
                    targs = self.check_valid_receivers(self.rhslist)
                    if not targs:
                        return
                    caller.messages.forward_messenger(targs, msg)
                    return
                if "delete" in self.switches:
                    caller.messages.del_messenger(msg)
                    caller.msg(
                        "You destroy all evidence that you ever received that message."
                    )
                    return
                if "preserve" in self.switches or "save" in self.switches:
                    if not caller.messages.preserve_messenger(msg):
                        return
                self.disp_messenger(msg)
                return
            except TypeError:
                caller.msg("You have %s old messages." % len(old))
                return
            except (ValueError, IndexError):
                caller.msg(
                    "You must supply a number between 1 and %s. You wrote '%s'."
                    % (len(old), self.lhs)
                )
                return
        if (
            "sent" in self.switches
            or "sentindex" in self.switches
            or "oldsent" in self.switches
        ):
            old = list(
                Messenger.objects.written_by(caller).order_by("-db_date_created")
            )
            if not old:
                caller.msg(
                    "There are no traces of old messages you sent. They may have all been destroyed."
                )
                return
            if not self.args or "sentindex" in self.switches:
                try:
                    num_disp = int(self.args)
                except (TypeError, ValueError):
                    num_disp = 20
                # display a prettytable of message number, sender, IC date
                return self.display_sent_table(num_disp, old)
            try:
                num = int(self.lhs)
                if num < 1:
                    raise ValueError
                msg = old[num - 1]
                caller.msg(
                    "\n{wMessage to:{n %s" % ", ".join(ob.key for ob in msg.receivers)
                )
                self.disp_messenger(msg)
                return
            except TypeError:
                caller.msg("You have %s old sent messages." % len(old))
                return
            except (ValueError, IndexError):
                caller.msg(
                    "You must supply a number between 1 and %s. You wrote '%s'."
                    % (len(old), self.lhs)
                )
                return
        if "proof" in self.switches:
            msg = caller.db.messenger_draft
            if not msg:
                caller.msg("You have no draft message stored.")
                return
            caller.msg("Message for: %s" % ", ".join(ob.key for ob in msg[0]))
            caller.msg(msg[1])
            return
        if "send" in self.switches:
            if self.check_cannot_use_messengers(self.caller):
                return
            caller.messages.send_draft_message()
            caller.ndb.already_previewed = None
            return
        if not self.lhs or not self.rhs:
            caller.msg("Invalid usage.")
            return
        # delivery messenger
        money = 0.0
        mats = None
        delivery = None
        if self.check_switches(self.delivery_switches):
            try:
                name_list, remainder = self.get_list_of_arguments()
                targs = self.check_valid_receivers(name_list)
                if "money" in self.switches or "silver" in self.switches:
                    money = float(remainder[0])
                elif "materials" in self.switches:
                    mats = self.get_mats_from_args(remainder[0])
                    if not mats:
                        return
                else:  # deliver
                    delivery = caller.search(remainder[0], location=caller)
                    if not delivery:
                        return
                    if len(remainder) > 1:
                        money = remainder[1]
                    if len(remainder) > 2:
                        mats = self.get_mats_from_args(remainder[2])
                money = float(money)
                if money < 0:
                    raise ValueError
            except IndexError:
                caller.msg("Must provide both a receiver and an object for a delivery.")
                caller.msg("Ex: messenger/deliver alaric,a bloody rose=Only for you.")
                return
            except (ValueError, TypeError):
                caller.msg("Money must be a number.")
                return
        # normal messenger
        elif "draft" in self.switches or not self.switches:
            targs = self.check_valid_receivers(self.lhslist)
        else:  # invalid switch
            self.msg("Unrecognized switch.")
            return
        if not targs:
            return
        if "draft" in self.switches:
            caller.messages.messenger_draft = (targs, self.rhs)
            return
        # check that we have enough money/mats for every receiver
        if not self.check_delivery_amounts(targs, delivery, money, mats):
            return
        caller.messages.create_and_send_messenger(
            self.rhs, targs, delivery, money, mats
        )
        caller.ndb.already_previewed = None

    def get_list_of_arguments(self):
        """
        Try to get different types of arguments based on user input. If a | is specified, then
        they're separating a list of receivers with the pipe. Otherwise, they're assumed to have
        one receiver, and we just use self.lhslist for the old comma separated arguments.
        Returns:
            Two lists: the first being a list of player names, the other a list of remaining
            arguments.
        """
        arglist = self.lhs.split("|")
        if len(arglist) == 1:
            return (self.lhslist[0],), self.lhslist[1:]
        else:
            return arglist[0].split(","), arglist[1].split(",")

    def check_delivery_amounts(self, receivers, delivery, money, mats):
        """
        Checks if we can deliver everything we're trying to send
        Args:
            receivers: Receivers we're sending stuff to
            delivery: Object we might be delivering, if any
            money: Silver we're sending, if any
            mats: Materials we're sending, if any

        Returns:
            True if we can send, false otherwise
        """
        num = len(receivers)
        if delivery:
            if not delivery.at_before_move(receivers[0], caller=self.caller):
                return
            if delivery.location != self.caller:
                self.msg("You do not have the delivery in your possession.")
                return
        if money:
            total = money * num
            current = self.caller.currency
            if current < total:
                self.msg(
                    "That delivery would cost %s, and you only have %s."
                    % (total, current)
                )
                return
        if mats:
            amt = mats[1] * num
            try:
                pmats = self.caller.player.Dominion.assets.owned_materials
                pmat = pmats.get(type=mats[0])
            except OwnedMaterial.DoesNotExist:
                self.msg("You don't have any of that type of material.")
                return
            if pmat.amount < amt:
                self.msg(
                    "You want to send %s, but you only have %s available."
                    % (amt, pmat.amount)
                )
                return
        return True

    def check_valid_receivers(self, name_list):
        """
        Given a list of names, check that each player given by the name_list has a character object that
        can receive messengers. Return all valid characters.
        Args:
            name_list: List of names of players to check

        Returns:
            List of character objects
        """
        targs = []
        for arg in name_list:
            targ = self.caller.player.search(arg)
            if targ:
                can_deliver = True
                character = targ.char_ob
                if not character:
                    can_deliver = False
                elif self.check_cannot_use_messengers(character):
                    continue
                elif not hasattr(targ, "roster") or not targ.roster.roster:
                    can_deliver = False
                elif targ.roster.roster.name not in ("Active", "Unavailable"):
                    can_deliver = False
                if not can_deliver:
                    self.msg("%s cannot receive messengers." % targ)
                    continue
                targs.append(character)
        if not targs:
            self.msg("No valid receivers found.")
        return targs

    def display_received_table(self, num_disp, old):
        """Sends prettytable of old received messengers to caller"""
        caller = self.caller
        msgtable = PrettyTable(
            ["{wMsg #", "{wSender", "{wIC Date", "{wOOC Date", "{wSave"]
        )
        mess_num = 1
        old = old[:num_disp]
        for mess in old:
            try:
                name = caller.messages.get_sender_name(mess)
            except AttributeError:
                mess = reload_model_as_proxy(mess)
                print(
                    "Error: Had to reload Msg ID %s as Messenger when displaying received table."
                    % mess.id
                )
                name = caller.messages.get_sender_name(mess)
            date = caller.messages.get_date_from_header(mess) or "Unknown"
            ooc_date = mess.db_date_created.strftime("%x")
            saved = "{w*{n" if mess.preserved else ""
            msgtable.add_row([mess_num, name, date, ooc_date, saved])
            mess_num += 1
        self.msg(msgtable)

    def display_sent_table(self, num_disp, old):
        """Displays table of messengers we've sent to caller"""
        msgtable = PrettyTable(["{wMsg #", "{wReceiver", "{wDate"])
        mess_num = 1
        old = old[:num_disp]
        for mess in old:
            receiver = mess.receivers
            if receiver:
                receiver = receiver[0]
                name = receiver.key
            else:
                name = "Unknown"
            try:
                date = self.caller.messages.get_date_from_header(mess) or "Unknown"
            except AttributeError:
                mess = reload_model_as_proxy(mess)
                print(
                    "Error: Had to reload Msg ID %s as Messenger when displaying sent table."
                    % mess.id
                )
                date = self.caller.messages.get_date_from_header(mess) or "Unknown"
            msgtable.add_row([mess_num, name, date])
            mess_num += 1
        self.msg(msgtable)
        return


class CmdCalendar(ArxPlayerCommand):
    """
    @cal - Creates events and displays information about them.

    Usage:
        @cal [<event number>]
        @cal/list
        @cal/old
        @cal/comments <event number>=<comment number>
    Creation:
        @cal/create [<name>]
        @cal/abort
        @cal/submit
    Creation or Editing:
        @cal/desc <description>[=<event ID>]
        @cal/date <date>[=<event ID>]
        @cal/largesse <level>[=<event ID>]
        @cal/location [<room name, otherwise room you're in>][=<event ID>]
        @cal/plotroom [<plot room ID>][=<event ID>]
        @cal/private <on or off>[=<event ID>]
        @cal/host <playername>[=<event ID>]
        @cal/gm <playername>[=<event ID>]
        @cal/invite <player or org name>[,name,...][=<event ID>]
        @cal/uninvite <player or org name>[=<event ID>]
        @cal/roomdesc <description>[=<event ID>]
        @cal/risk <risk value>[=<event ID>]
        @cal/plot <plot ID #>[=<event ID>]
    Admin:
        @cal/starteventearly <event ID>
        @cal/cancel <event ID>
        @cal/endevent <event ID>
        @cal/movehere <event ID>
    Interaction:
        @cal/join <event ID>
        @cal/sponsor <org>,<social resources>=<event ID>

    Date should be in 'MM/DD/YY HR:MN' format. /private toggles whether the
    event is public or private (defaults to public). To spend extravagant
    amounts of money in hosting an event for prestige, set the /largesse
    level. To see the valid largesse types with their costs and prestige
    values, do '@cal/largesse'. Prestige is divided among hosts present,
    or if no hosts are present goes fully to the main host. Private events
    give half prestige. All times are in EST.

    To mark an event as a player-run-plot, use /addgm to designate a
    player as the storyteller for the event. Please only use this for a
    player who is actually running an event with some form of plot that
    requires checks to influence the outcome.

    When starting an event early, you can specify '=here' to start it in
    your current room rather than its previous location. /movehere allows
    an event to be moved to the new room you occupy while in progress.

    If an event takes place off the grid, you can @cal/join the event to
    be teleported to the room, for easy gathering of the group.

    If you want to mark an event private or public so that it can be viewed
    by people who didn't attend it on the web, use /toggleprivate.
    """

    key = "@cal"
    locks = "cmd:all()"
    aliases = ["+event", "+events", "@calendar"]
    help_category = "Social"

    class CalCmdError(Exception):
        """Errors for this command"""

        pass

    display_switches = ("old", "list")
    target_event_switches = ("comments", "join", "sponsor")
    form_switches = ("create", "abort", "submit")
    attribute_switches = (
        "plotroom",
        "roomdesc",
        "host",
        "gm",
        "invite",
        "uninvite",
        "location",
        "desc",
        "date",
        "private",
        "risk",
        "plot",
        "reschedule",
        "largesse",
    )
    admin_switches = ("cancel", "starteventearly")
    in_progress_switches = ("movehere", "endevent")

    @property
    def project(self):
        return self.caller.ndb.event_creation

    @project.setter
    def project(self, val):
        self.caller.ndb.event_creation = val

    @project.deleter
    def project(self):
        self.caller.ndb.event_creation = None

    @property
    def form(self):
        """Returns the RPEventCreateForm for the caller"""
        proj = self.project
        if not proj:
            return
        return RPEventCreateForm(proj, owner=self.caller.Dominion)

    @property
    def event_manager(self):
        """Returns the script for tracking/updating events"""
        return ScriptDB.objects.get(db_key="Event Manager")

    def func(self):
        """Execute command."""
        try:
            if not self.args and (
                not self.switches or self.check_switches(self.display_switches)
            ):
                return self.do_display_switches()
            if not self.switches or self.check_switches(self.target_event_switches):
                return self.do_target_event_switches()
            if self.check_switches(self.form_switches):
                return self.do_form_switches()
            if self.check_switches(self.attribute_switches):
                return self.do_attribute_switches()
            if self.check_switches(self.in_progress_switches):
                return self.do_in_progress_switches()
            if self.check_switches(self.admin_switches):
                return self.do_admin_switches()
            raise self.CalCmdError("Invalid switch.")
        except (self.CalCmdError, PayError) as err:
            self.msg(err)

    def do_display_switches(self):
        """Displays events"""
        if not self.switches and self.project:
            self.display_project()
            return
        if self.caller.check_permstring("builders"):
            qs = RPEvent.objects.all()
        else:
            dompc = self.caller.Dominion
            qs = RPEvent.objects.filter(
                Q(public_event=True) | Q(dompcs=dompc) | Q(orgs__in=dompc.current_orgs)
            )
        if "old" in self.switches:  # display finished events
            finished = qs.filter(finished=True).distinct().order_by("-date")
            from server.utils import arx_more

            table = self.display_events(finished)
            arx_more.msg(self.caller, "{wOld events:\n%s" % table, justify_kwargs=False)
        else:  # display upcoming events
            unfinished = qs.filter(finished=False).distinct().order_by("date")
            table = self.display_events(unfinished)
            self.msg("{wUpcoming events:\n%s" % table, options={"box": True})

    @staticmethod
    def display_events(events):
        """Returns table of events"""
        table = PrettyTable(
            ["{wID{n", "{wName{n", "{wDate{n", "{wHost{n", "{wPublic{n"]
        )
        for event in events:
            host = event.main_host or "No host"
            host = str(host).capitalize()
            public = "Public" if event.public_event else "Not Public"
            table.add_row(
                [
                    event.id,
                    event.name[:25],
                    event.date.strftime("%x %H:%M"),
                    host,
                    public,
                ]
            )
        return table

    def do_target_event_switches(self):
        """Interact with events owned by other players"""
        caller = self.caller
        lhslist = self.lhs.split("/")
        if len(lhslist) > 1:
            lhs = lhslist[0]
            rhs = lhslist[1]
        else:
            lhs = self.lhs
            rhs = self.rhs
        if "sponsor" in self.switches:
            from django.core.exceptions import ObjectDoesNotExist

            event = self.get_event_from_args(self.rhs)
            try:
                org = Organization.objects.get(name__iexact=self.lhslist[0])
            except Organization.DoesNotExist:
                raise self.CalCmdError("No Organization by that name.")
            if not org.access(self.caller, "withdraw"):
                raise self.CalCmdError(
                    "You do not have permission to spend funds for %s." % org
                )
            if event.finished:
                raise self.CalCmdError("Try as you might, you cannot alter the past.")
            try:
                amount = int(self.lhslist[1])
                if amount < 1:
                    raise ValueError
            except (TypeError, ValueError):
                raise self.CalCmdError(
                    "You must provide a positive number of social resources to add."
                )
            try:
                sponsoring = event.add_sponsorship(org, amount)
            except ObjectDoesNotExist:
                raise self.CalCmdError(
                    "The organization must be invited before they can sponsor."
                )
            self.msg(
                "%s is now sponsoring %s for %d social resources."
                % (org, event, sponsoring.social)
            )
            return
        event = self.get_event_from_args(lhs)
        if "join" in self.switches:
            diff = time_from_now(event.date).total_seconds()
            if diff > 3600:
                caller.msg("You cannot join the event until closer to the start time.")
                return
            if event.plotroom is None:
                caller.msg(
                    "That event takes place on the normal grid, so you can just walk there."
                )
                return
            if event.location is None:
                caller.msg("That event has no location to join.")
                return
            caller.msg("Moving you to the event location.")
            mapping = {"secret": True}
            caller.char_ob.move_to(event.location, mapping=mapping)
        # display info on a given event
        if not rhs:
            caller.msg(event.display(), options={"box": True})
            return
        try:
            num = int(rhs)
            if num < 1:
                raise ValueError
            comments = list(
                event.comments.filter(db_tags__db_key="white_journal").order_by(
                    "-db_date_created"
                )
            )
            caller.msg(caller.char_ob.messages.disp_entry(comments[num - 1]))
            return
        except (ValueError, TypeError):
            caller.msg("Must leave a positive number for a comment.")
            return
        except IndexError:
            caller.msg("No entry by that number.")
            return

    def get_event_from_args(self, args, check_admin=False, check_host=False):
        """Gets an event by args"""
        try:
            event = RPEvent.objects.get(id=int(args))
        except (ValueError, TypeError):
            raise self.CalCmdError("Event must be a number.")
        except RPEvent.DoesNotExist:
            raise self.CalCmdError("No event found by that number.")
        if not event.can_view(self.caller):
            raise self.CalCmdError("You can't view this event.")
        if check_host and not event.can_end_or_move(self.caller):
            raise self.CalCmdError("You do not have permission to change the event.")
        if check_admin and not event.can_admin(self.caller):
            raise self.CalCmdError("Only the main host can cancel the event.")
        return event

    def do_form_switches(self):
        """Handles form switches"""
        if "abort" in self.switches:
            del self.project
            self.msg("Event creation cancelled.")
        elif "create" in self.switches:
            if not self.args:
                self.display_project()
                return
            if RPEvent.objects.filter(name__iexact=self.lhs):
                self.msg(
                    "There is already an event by that name. Choose a different name "
                    "or add a number if it's a sequel event."
                )
                return
            defaults = RPEvent()
            new = {
                "hosts": [],
                "gms": [],
                "org_invites": [],
                "invites": [],
                "name": self.lhs,
                "public_event": defaults.public_event,
                "risk": defaults.risk,
                "celebration_tier": defaults.celebration_tier,
            }
            self.project = new
            msg = (
                "|wStarting project.|n It will not be saved until you submit it. "
                "Does not persist through logout or server reload.\n%s"
                % self.form.display()
            )
            self.msg(msg, options={"box": True})
        elif "submit" in self.switches:
            form = self.form
            if not form:
                raise self.CalCmdError("You must /create a form first.")
            if not form.is_valid():
                raise self.CalCmdError(form.display_errors() + "\n" + form.display())
            event = form.save()
            self.project = None
            self.msg(
                "New event created: %s at %s."
                % (event.name, event.date.strftime("%x %X"))
            )
            inform_staff(
                "New event created by %s: %s, scheduled for %s."
                % (self.caller, event.name, event.date.strftime("%x %X"))
            )

    def do_attribute_switches(self):
        """Sets a value for the form or changes an existing event's attribute"""
        event = None
        if self.rhs:
            event = self.get_event_from_args(self.rhs, check_host=True)
        else:
            proj = self.project
            if not proj:
                raise self.CalCmdError(
                    "You must use /create first or specify an event."
                )
        if "largesse" in self.switches:
            return self.set_largesse(event)
        if "date" in self.switches or "reschedule" in self.switches:
            return self.set_date(event)
        if "location" in self.switches:
            return self.set_location(event)
        if "desc" in self.switches:
            return self.set_event_desc(event)
        if "roomdesc" in self.switches:
            return self.set_room_desc(event)
        if "plotroom" in self.switches:
            return self.set_plotroom(event)
        if "private" in self.switches:
            return self.set_private(event)
        if "host" in self.switches:
            return self.add_or_remove_host(event)
        if "gm" in self.switches:
            return self.add_or_remove_gm(event)
        if "invite" in self.switches:
            return self.invite_org_or_player(event)
        if "uninvite" in self.switches:
            return self.uninvite_org_or_player(event)
        if "action" in self.switches:
            return self.set_crisis_action(event)
        if "risk" in self.switches:
            return self.set_risk(event)

    def do_in_progress_switches(self):
        """Change event in progress"""
        event = self.get_event_from_args(self.lhs, check_host=True)
        if "movehere" in self.switches:
            loc = self.caller.char_ob.location
            self.event_manager.move_event(event, loc)
            self.msg("Event moved to your room.")
        elif "endevent" in self.switches:
            self.event_manager.finish_event(event)
            self.msg("You have ended the event.")

    def do_admin_switches(self):
        """Starts an event or cancels it"""
        if "cancel" in self.switches:
            event = self.get_event_from_args(self.lhs, check_admin=True)
            if event.id in self.event_manager.db.active_events:
                self.msg("You must /end an active event.")
                return
            cost = event.cost
            self.caller.char_ob.pay_money(-cost)
            inform_staff("%s event has been cancelled." % str(event))
            self.event_manager.cancel_event(event)
            self.msg("You have cancelled the event.")
        elif "starteventearly" in self.switches:
            event = self.get_event_from_args(self.lhs, check_host=True)
            if self.rhs and self.rhs.lower() == "here":
                loc = self.caller.char_ob.location
                if not loc:
                    self.msg("You do not currently have a location.")
                    return
                self.event_manager.start_event(event, location=loc)
            else:
                self.event_manager.start_event(event)
            self.msg("You have started the event.")

    def display_project(self):
        """Sends a string display of a project"""
        form = self.form
        if form:
            msg = "|wEvent you're creating:|n\n" + form.display()
        else:
            msg = "|wYou are not currently creating an event.|n"
        self.msg(msg, options={"box": True})

    def set_form_or_event_attribute(self, param, value, event=None):
        """Sets an attribute in an event or creation form"""
        if event:
            setattr(event, param, value)
            event.save()
        else:
            proj = self.project
            if not proj:
                raise self.CalCmdError(
                    "You must /create to start a project, or specify an event you want to change."
                )
            proj[param] = value
            self.project = proj

    def set_date(self, event=None):
        """Sets a date for an event"""
        try:
            date = datetime.strptime(self.lhs, "%m/%d/%y %H:%M")
        except ValueError:
            raise self.CalCmdError(
                "Date did not match 'mm/dd/yy hh:mm' format. You entered: %s" % self.lhs
            )
        now = datetime.now()
        if date < now:
            raise self.CalCmdError("You cannot make an event for the past.")
        if event and event.date < now:
            raise self.CalCmdError(
                "You cannot reschedule an event that's already started."
            )
        self.set_form_or_event_attribute("date", date, event)
        self.msg("Date set to %s." % date.strftime("%x %X"))
        if event:
            self.event_manager.reschedule_event(event)
        self.msg(
            "Current time is %s for comparison." % (datetime.now().strftime("%x %X"))
        )
        offset = timedelta(hours=2)
        count = RPEvent.objects.filter(
            date__lte=date + offset, date__gte=date - offset
        ).count()
        self.msg("Number of events within 2 hours of that date: %s" % count)

    def set_largesse(self, event=None):
        """Sets largesse for an event"""
        from server.utils.arx_utils import dict_from_choices_field

        largesse_types = dict_from_choices_field(
            RPEvent, "LARGESSE_CHOICES", include_uppercase=False
        )
        costs = dict(RPEvent.LARGESSE_VALUES)
        lhs = self.lhs.lower()
        if not lhs:
            table = PrettyTable(["{wLevel{n", "{wCost{n", "{wPrestige{n"])
            choices = dict(RPEvent.LARGESSE_CHOICES)
            for key in costs:
                name = choices[key]
                table.add_row([name, costs[key][0], costs[key][1]])
            self.msg(table, options={"box": True})
            return
        if lhs not in largesse_types:
            self.msg(
                "Argument needs to be in %s." % ", ".join(ob for ob in largesse_types)
            )
            return
        cel_tier = largesse_types[lhs]
        cost = costs[cel_tier][0]
        if event:
            new_cost = cost
            cost = new_cost - event.cost
        currency = self.caller.char_ob.currency
        if currency < cost:
            self.msg("That requires %s to buy. You have %s." % (cost, currency))
            return
        self.set_form_or_event_attribute("celebration_tier", cel_tier, event)
        self.msg("Largesse level set to %s for %s." % (lhs, cost))
        if event:
            self.caller.char_ob.pay_money(cost)

    def set_event_desc(self, event):
        """Sets description of an event"""
        self.set_form_or_event_attribute("desc", self.lhs, event)
        self.msg("Desc of event set to:\n%s" % self.lhs)

    def set_room_desc(self, event):
        """Sets description appended to event's location"""
        self.set_form_or_event_attribute("room_desc", self.lhs, event)
        self.msg("Room desc of event set to:\n%s" % self.lhs)

    def set_location(self, event=None):
        """Sets location for form or an event"""
        if self.lhs and self.lhs.lower() != "here":
            try:
                try:
                    room = ArxRoom.objects.get(db_key__iexact=self.lhs)
                except ArxRoom.DoesNotExist:
                    room = ArxRoom.objects.get(db_key__icontains=self.lhs)
            except (ArxRoom.DoesNotExist, ArxRoom.MultipleObjectsReturned):
                raise self.CalCmdError(
                    "Could not find a unique match for %s." % self.lhs
                )
        else:
            if not self.caller.character:
                raise self.CalCmdError(
                    "You must be in a room to mark it as the event location."
                )
            room = self.caller.character.location
        if not room:
            raise self.CalCmdError("No room found.")
        id_or_instance = room if event else room.id
        self.set_form_or_event_attribute("plotroom", None, event)
        self.set_form_or_event_attribute("location", id_or_instance, event)
        self.msg("Room set to %s." % room)

    def set_plotroom(self, event):
        """Sets the virtual 'plotroom' for an event, if any."""
        if self.lhs:
            dompc = self.caller.Dominion
            try:
                room_id = int(self.lhs)
                plotrooms = PlotRoom.objects.filter(
                    Q(id=room_id) & (Q(creator=dompc) | Q(public=True))
                )
            except ValueError:
                plotrooms = PlotRoom.objects.filter(
                    Q(name__icontains=self.lhs) & (Q(creator=dompc) | Q(public=True))
                )

            if not plotrooms:
                raise self.CalCmdError("No plotrooms found matching %s" % self.lhs)

            if len(plotrooms) > 1:
                msg = "Found multiple rooms matching %s:" % self.lhs
                for room in plotrooms:
                    msg += "  %d: %s (%s)" % (
                        room.id,
                        room.name,
                        room.get_detailed_region_name(),
                    )
                raise self.CalCmdError(msg)
            plotroom = plotrooms[0]
            id_or_instance = plotroom if event else plotroom.id
            self.set_form_or_event_attribute("location", None, event)
            self.set_form_or_event_attribute("plotroom", id_or_instance, event)
            msg = (
                "Plot room for event set to %s: %s (in %s)\nIf you wish to remove the plotroom later, "
                "use this command with no left-hand-side argument."
                % (plotroom, plotroom.ansi_name(), plotroom.get_detailed_region_name())
            )
            self.msg(msg)
        else:
            self.set_form_or_event_attribute("plotroom", None, event)
            self.msg("Plot room for event cleared.")

    def set_private(self, event):
        """Sets whether an event is private or public"""
        args = self.lhs.lower()
        if args == "on":
            public = False
        elif args == "off":
            public = True
        else:
            raise self.CalCmdError("Private must be set to either 'on' or 'off'.")
        self.set_form_or_event_attribute("public_event", public, event)
        self.msg("Event set to: %s" % ("public" if public else "private"))

    def add_or_remove_host(self, event):
        """Adds a host or changes them to a regular guest"""
        try:
            host = self.caller.search(self.lhs).Dominion
        except AttributeError:
            return
        if event:
            if host == event.main_host:
                raise self.CalCmdError("The main host cannot be removed.")
            if host in event.hosts:
                event.change_host_to_guest(host)
                msg = "Changed host to a regular guest. Use /uninvite to remove them completely."
            else:
                event.add_host(host)
                msg = "%s added to hosts." % host
        else:
            hosts = self.project["hosts"]
            if host.id in hosts:
                hosts.remove(host.id)
                if host.id not in self.project["invites"]:
                    self.project["invites"].append(host.id)
                msg = "Changed host to a regular guest. Use /uninvite to remove them completely."
            else:
                hosts.append(host.id)
                if host.id in self.project["invites"]:
                    self.project["invites"].remove(host.id)
                msg = "%s added to hosts." % host
        self.msg(msg)

    def add_or_remove_gm(self, event):
        """Adds a gm or strips gm tag from them"""
        try:
            gm = self.caller.search(self.lhs).Dominion
        except AttributeError:
            return
        add_msg = (
            "|w%s is now marked as a gm.|n\n"
            "Reminder: Please only add a GM for an event if it's a player-run plot. Tagging a "
            "social event as a PRP is strictly prohibited. If you tagged this as a PRP in error, use "
            "gm on them again to remove them."
        )
        if event:
            if gm in event.gms:
                event.untag_gm(gm)
                msg = (
                    "%s is no longer marked as a gm. Use /uninvite to remove them completely."
                    % gm
                )
            else:
                if len(event.gms) >= 2:
                    raise self.CalCmdError(
                        "Please limit yourself to one or two designated GMs."
                    )
                event.add_gm(gm)
                msg = add_msg % gm
        else:
            gms = self.project["gms"]
            if gm.id in gms:
                msg = (
                    "%s is no longer marked as a gm. Use /uninvite to remove them completely."
                    % gm
                )
                if gm.id not in self.project["invites"]:
                    self.project["invites"].append(gm.id)
            else:
                if len(gms) >= 2:
                    raise self.CalCmdError(
                        "Please limit yourself to one or two designated GMs."
                    )
                gms.append(gm.id)
                if gm.id in self.project["invites"]:
                    self.project["invites"].remove(gm.id)
                msg = add_msg % gm
        self.msg(msg)

    def invite_org_or_player(self, event):
        """Invites an organization or player to an event"""
        for arg in self.lhslist:
            org, pc = self.get_org_or_dompc(arg)
            if event:
                if org:
                    if org in event.orgs.all():
                        raise self.CalCmdError("That organization is already invited.")
                    event.invite_org(org)
                else:
                    if pc in event.dompcs.all():
                        raise self.CalCmdError("They are already invited.")
                    event.add_guest(pc)
            else:
                proj = self.project
                if not proj:
                    raise self.CalCmdError(
                        "You must use /create first or specify an event."
                    )
                if org:
                    if org.id in proj["org_invites"]:
                        raise self.CalCmdError("That organization is already invited.")
                    proj["org_invites"].append(org.id)
                else:
                    if pc.id in proj["hosts"] or pc.id in proj["gms"]:
                        raise self.CalCmdError(
                            "They are already invited to host or gm."
                        )
                    if pc.id in proj["invites"]:
                        raise self.CalCmdError("They are already invited.")
                    proj["invites"].append(pc.id)
            self.msg("{wInvited {c%s{w to attend." % (pc or org))

    def get_org_or_dompc(self, args):
        """Gets org or a dompc based on name"""
        org = None
        pc = None
        try:
            org = Organization.objects.get(name__iexact=args)
        except Organization.DoesNotExist:
            try:
                pc = self.caller.search(args).Dominion
            except AttributeError:
                raise self.CalCmdError(
                    "Could not find an organization or player by that name."
                )
        return org, pc

    def uninvite_org_or_player(self, event):
        """Removes an organization or player from an event"""
        org, pc = self.get_org_or_dompc(self.lhs)
        if event:
            if org:
                if org not in event.orgs.all():
                    raise self.CalCmdError("That organization is not invited.")
                event.remove_org(org)
            else:
                if pc not in event.dompcs.all():
                    raise self.CalCmdError("They are not invited.")
                event.remove_guest(pc)
        else:
            proj = self.project
            if org:
                if org.id not in proj["org_invites"]:
                    raise self.CalCmdError("That organization is not invited.")
                proj["org_invites"].remove(org.id)
            else:
                if pc.id in proj["hosts"] or pc.id in proj["gms"]:
                    raise self.CalCmdError("Remove them as a host or gm first.")
                if pc.id not in proj["invites"]:
                    raise self.CalCmdError("They are not invited.")
                proj["invites"].remove(pc.id)
        self.msg("{wRemoved {c%s{w's invitation." % (pc or org))

    def set_crisis_action(self, event):
        """Sets crisis actions for an event"""
        try:
            plot = self.caller.Dominion.plots_we_can_gm.get(id=self.lhs)
        except (PlotAction.DoesNotExist, ValueError, TypeError):
            raise self.CalCmdError("You can only add or remove plots you can gm.")
        if event:
            beat = event.beat
            if beat in plot.updates.all():
                event.beat = None
                event.save()
                if not beat.desc:
                    beat.delete()
                msg = "Plot removed."
            else:
                if not beat.desc:
                    beat.delete()
                event.beat = plot.updates.create()
                msg = "Plot added."
        else:
            plot_id = self.project.setdefault("plot", None)
            if plot_id == plot.id:
                self.project["plot"] = None
                msg = "Plot removed."
            else:
                self.project["plot"] = plot.id
                msg = "Plot added."
        self.msg(msg)

    def set_risk(self, event):
        """Sets risk for an rpevent"""
        if not self.caller.check_permstring("builders"):
            raise self.CalCmdError("Only GMs can set the risk of an event.")
        try:
            risk = int(self.lhs)
            if risk > 10 or risk < 0:
                raise ValueError
        except (TypeError, ValueError):
            raise self.CalCmdError("Risk must be between 0 and 10.")
        self.set_form_or_event_attribute("risk", risk, event)
        self.msg("Risk is now set to: %s" % risk)


class CmdPraise(ArxPlayerCommand):
    """
    praise

    Usage:
        praise <character>[,<num praises>][=<message>]
        praise/all <character>[=<message>]
        praise/org <org>[,<num praises>][=<message>]

    Praises a character, increasing their prestige. Your number
    of praises per week are based on your social rank and skills.
    Using praise with no arguments lists your praises. Costs 1 AP
    regardless of how many praises are used.

    Praises for orgs work a little differently. It may only be used
    for an organization sponsoring an event while you are in attendance,
    and the amount gained is based on the largesse of the event and the
    social resources spent by the organization.
    """

    key = "praise"
    locks = "cmd:all()"
    help_category = "Social"
    aliases = ["igotyoufam"]
    attr = "praises"
    verb = "praise"
    verbing = "praising"
    MIN_VALUE = 10

    class PraiseError(Exception):
        """Errors when praising"""

        pass

    def func(self):
        """Execute command."""
        try:
            if not self.lhs:
                self.msg(self.display_praises(), options={"box": True})
                return
            self.do_praise()
        except self.PraiseError as err:
            self.msg(err)

    def do_praise(self):
        """Executes a praise"""
        caller = self.caller
        # don't you dare judge us for having thought of this
        if self.cmdstring == "praise" and self.lhs.lower() == "the sun":
            caller.msg("Thank you for your jolly cooperation. Heresy averted.")
            return
        if "org" in self.switches:
            try:
                targ = Organization.objects.get(name__iexact=self.lhslist[0])
            except Organization.DoesNotExist:
                raise self.PraiseError("No organization by that name.")
            from django.core.exceptions import ObjectDoesNotExist

            try:
                base = caller.char_ob.location.event.get_sponsor_praise_value(targ)
            except (AttributeError, ObjectDoesNotExist):
                raise self.PraiseError(
                    "There is no event going on that has %s as a sponsor." % targ
                )
            targ = targ.assets
        else:
            base = 0
            targ = caller.search(self.lhslist[0])
            if not targ:
                return
            try:
                name = targ.char_ob.roster.roster.name
                if not name or name.lower() == "incomplete" or not targ.Dominion.assets:
                    raise AttributeError
            except AttributeError:
                raise self.PraiseError("No character found by '%s'." % self.lhslist[0])
            account = caller.roster.current_account
            if account == targ.roster.current_account:
                raise self.PraiseError("You cannot %s yourself." % self.verb)
            if targ.is_staff:
                raise self.PraiseError("Staff don't need your %s." % self.attr)
            targ = targ.Dominion.assets
        char = caller.char_ob
        current_used = self.current_used
        if current_used >= self.get_max_praises():
            raise self.PraiseError(
                "You have already used all your %s for the week." % self.attr
            )
        if len(self.lhslist) > 1:
            try:
                to_use = int(self.lhslist[1])
                if to_use < 1:
                    raise ValueError
                if to_use > self.get_actions_remaining():
                    raise ValueError
            except ValueError:
                raise self.PraiseError(
                    "The number of praises used must be a positive number, "
                    "and less than your max praises."
                )
        else:
            to_use = 1 if "all" not in self.switches else self.get_actions_remaining()
        current_used += to_use
        from world.dominion.models import PraiseOrCondemn
        from server.utils.arx_utils import get_week

        if not caller.pay_action_points(1):
            raise self.PraiseError(
                "You cannot muster the energy to praise someone at this time."
            )
        amount = self.do_praise_roll(base) * to_use
        praise = PraiseOrCondemn.objects.create(
            praiser=caller.Dominion,
            target=targ,
            number_used=to_use,
            message=self.rhs or "",
            week=get_week(),
            value=amount,
        )
        praise.do_prestige_adjustment()
        name = str(targ).capitalize()
        caller.msg(
            "You %s the actions of %s. You have %s %s remaining."
            % (self.verb, name, self.get_actions_remaining(), self.attr)
        )
        reasons = ": %s" % self.rhs if self.rhs else "."
        char.location.msg_contents(
            "%s is overheard %s %s%s" % (char.name, self.verbing, name, reasons),
            exclude=char,
        )

    def do_praise_roll(self, base=0):
        """(charm+propaganda at difficulty 15=x, where x >0), x* ((40*prestige mod)+# of social resources)"""
        roll = do_dice_check(self.caller.char_ob, stat="charm", skill="propaganda")
        roll *= int(self.caller.Dominion.assets.prestige_mod)
        roll += base
        return max(roll, self.MIN_VALUE)

    def get_max_praises(self):
        """Calculates how many praises character has"""
        char = self.caller.char_ob
        clout = char.social_clout
        s_rank = char.db.social_rank or 10
        return clout + ((8 - s_rank) // 2)

    @property
    def current_used(self):
        """Number of praises already used"""
        praises = self.caller.get_current_praises_and_condemns()
        return sum(ob.number_used for ob in praises)

    def get_actions_remaining(self):
        """How many praises and condemns left this week"""
        return self.get_max_praises() - self.current_used

    def display_praises(self):
        """Returns table of praises by player"""
        player = self.caller
        praises_or_condemns = player.get_current_praises_and_condemns()
        praises = praises_or_condemns.filter(value__gte=0)
        condemns = praises_or_condemns.filter(value__lt=0)
        msg = "Praises:\n"
        table = EvTable("Name", "Praises", "Value", "Message", width=78, align="r")
        for praise in praises:
            table.add_row(
                praise.target,
                praise.number_used,
                "{:,}".format(praise.value),
                praise.message,
            )
        msg += str(table)
        msg += "\nCondemns:\n"
        table = EvTable("Name", "Condemns", "Value", "Message", width=78)
        for pc in condemns:
            table.add_row(pc.capitalize(), condemns[pc][0], condemns[pc][1])
        msg += str(table)
        msg += "\nPraises or Condemns remaining: %s" % self.get_actions_remaining()
        return msg


class CmdCondemn(CmdPraise):
    """
    condemn

    Usage:
        condemn <character>[=<message>]
        condemn/all <character>[=<message>]

    Condemns a character, decreasing their prestige. Your number
    of condemns per week are based on your social rank and skills.
    Using condemn with no arguments lists your condemns.
    """

    key = "condemn"
    attr = "condemns"
    verb = "condemn"
    verbing = "condemning"
    aliases = ["throw shade"]


class CmdAFK(ArxPlayerCommand):
    """
    afk

    Usage:
        afk
        afk <message>

    Toggles on or off AFK(away from keyboard). If you provide a message,
    it will be sent to people who send you pages.
    """

    key = "afk"
    locks = "cmd:all()"
    help_category = "Social"

    def func(self):
        """Execute command."""
        caller = self.caller
        if caller.db.afk:
            caller.db.afk = ""
            caller.msg("You are no longer AFK.")
            return
        caller.db.afk = self.args or "Sorry, I am AFK(away from keyboard) right now."
        caller.msg("{wYou are now AFK with the following message{n: %s" % caller.db.afk)
        return


class CmdRoomHistory(ArxCommand):
    """
    Adds a historical note to a room

    Usage:
        +roomhistory <message>

    Tags a note into a room to indicate that something significant happened
    here in-character. This is primarily intended to allow for magically
    sensitive characters to have a mechanism for detecting a past event, far
    in the future.
    """

    key = "+roomhistory"
    locks = "cmd:all()"
    help_category = "Social"

    def func(self):
        """Execute command."""
        caller = self.caller
        if not self.args:
            caller.msg("Please enter a description for the event.")
            return
        history = caller.location.db.roomhistory or []
        history.append((caller, self.args))
        caller.location.db.roomhistory = history
        caller.location.tags.add("roomhistory")
        caller.msg(
            "Added the historical note {w'%s'{n to this room. Thank you." % self.args
        )
        inform_staff(
            "%s added the note {w'%s'{n to room %s."
            % (caller.key, self.args, caller.location)
        )
        return


class CmdRoomMood(RewardRPToolUseMixin, ArxCommand):
    """
    Temporarily adds to room description

    Usage:
        +room_mood <message>

    Changes the current 'mood' of the room, which is a few lines that can be
    set to describe things which recently happened and shows up under look.
    Lasts for 24 hours. This can be used to help with setting up a scene and
    describing what is going on for people who enter.
    """

    key = "+room_mood"
    aliases = ["+roommood", "setscene"]
    locks = "cmd:all()"
    help_category = "Social"

    def func(self):
        """Execute command."""
        caller = self.caller
        mood = caller.location.db.room_mood or (None, 0, "")
        self.msg("Old mood was: %s" % mood[2])
        if not self.args:
            caller.location.attributes.remove("room_mood")
            self.msg("Mood erased.")
            return
        mood = (caller, time.time(), self.args)
        caller.location.db.room_mood = mood
        self.caller.location.msg_contents(
            "{w(OOC)The scene set/room mood is now set to:{n %s" % mood[2]
        )
        self.mark_command_used()


class CmdSocialNotable(ArxCommand):
    """
    Who's currently being talked about around Arx?

    Usage:
      notable [name]
      notable/buzz
      notable/legend
      notable/infamous
      notable/orgs

    This command will return who's currently being talked about around Arx,
    and if possible, why.

    The first form will show it based on prestige (a combination of multiple
    factors, such as your fame, legend, grandeur, and propriety).  This list
    represents who's particularly recognizable at this moment in time.  If you
    provide a character name, it will give you a quick note about that
    particular character.

    The second form will show it just based on fame, which is transient and
    fades over time.  Fame might come from being seen at a particularly
    fashionable event, or winning a tournament, or something else that briefly
    puts you in the spotlight.  The buzz list is thus who's currently in the
    spotlight for something recent.

    The third form will show it just based on legend, which is harder to earn
    but does not fade like fame.  Legend might come from doing something
    incredibly heroic, or rediscovering an ancient weapon of note, or other
    notable acts which will be remembered by history.  The legend list is
    thus people who are still reknowned for various things they've done.

    The fourth form will show the people who are infamous, whose prestige
    has dropped into the negative numbers.

    The fifth form will show the organizations in the city that people
    are talking about, though will not say precisely why the organization
    is currently notable.

    """

    key = "notable"
    locks = "cmd:all()"

    def show_rankings(self, title, asset_owners, adjust_type, show_percent=False):
        counter = 1
        table = EvTable()
        table.add_column(width=8)
        table.add_column()
        median = AssetOwner.MEDIAN_PRESTIGE * 1.0
        for owner in asset_owners:
            if show_percent:
                percentage = round((owner.prestige / median) * 100)
                percentage -= percentage % 10
                table.add_row(
                    str(counter),
                    owner.prestige_descriptor(adjust_type),
                    str(percentage) + "%",
                )
            else:
                table.add_row(str(counter), owner.prestige_descriptor(adjust_type))
            counter += 1
        if title:
            self.msg("\n|w" + title + "|n")
        self.msg(str(table) + "\n")

    def func(self):
        adjust_type = None
        if self.args:
            try:
                target = self.character_search(self.args)
                asset = AssetOwner.objects.get(player=target.dompc)

                percentage = round(
                    (asset.prestige / (AssetOwner.MEDIAN_PRESTIGE * 1.0)) * 100
                )
                percentage -= percentage % 10
                descriptor = asset.prestige_descriptor(
                    None, include_reason=False, wants_long_reason=True
                )
                best_adjust = asset.most_notable_adjustment(adjust_type=None)

                result = "%s, is roughly %d%% as notable as the average citizen." % (
                    descriptor,
                    percentage,
                )

                if best_adjust and best_adjust.long_reason:
                    result = "%s %s" % (result, best_adjust.long_reason)

                self.msg(result)

            except CommandError as ce:
                self.msg(ce)
            except (AssetOwner.DoesNotExist, AssetOwner.MultipleObjectsReturned):
                self.msg("No such character!")
            except ValueError:
                self.msg("That character doesn't seem to be on the list!")
            return

        if "orgs" in self.switches:
            title = "Organizations Currently in the Public Eye"
            assets = (
                AssetOwner.objects.filter(organization_owner__secret=False)
                .filter(
                    organization_owner__members__player__player__roster__roster__name="Active"
                )
                .distinct()
            )
            assets = sorted(assets, key=lambda x: x.prestige, reverse=True)
        else:
            assets = list(
                AssetOwner.objects.filter(
                    player__player__roster__roster__name__in=(
                        "Active",
                        "Gone",
                        "Available",
                    )
                )
            )

            if "buzz" in self.switches:
                title = "Who's Momentarily in the News"
                adjust_type = PrestigeAdjustment.FAME
                assets = sorted(assets, key=lambda x: x.fame, reverse=True)
            elif "legend" in self.switches:
                title = "People of Legendary Renown"
                adjust_type = PrestigeAdjustment.LEGEND
                assets = sorted(assets, key=lambda x: x.total_legend, reverse=True)
            elif "infamous" in self.switches:
                title = "Those Who Society Shuns"
                assets = [asset for asset in assets if asset.prestige < 0]
                assets = sorted(assets, key=lambda x: x.prestige, reverse=False)
                if len(assets) == 0:
                    self.msg(
                        "There don't seem to be any people with negative prestige right now!"
                    )
                    return
            else:
                title = "Who's Being Talked About Right Now"
                assets = sorted(assets, key=lambda x: x.prestige, reverse=True)

        assets = assets[:20]
        self.show_rankings(
            title,
            assets,
            adjust_type,
            show_percent=self.caller.check_permstring("builders"),
        )


class PrestigeCategoryField(fields.Paxfield):
    """
    This field contains a single prestige category
    """

    def __init__(self, required=False, **kwargs):
        super(PrestigeCategoryField, self).__init__(**kwargs)
        self._required = required
        self._value = None

    # noinspection PyMethodMayBeStatic
    def _get_category(self, args):
        try:
            return PrestigeCategory.objects.get(name__iexact=args)
        except PrestigeCategory.DoesNotExist:
            return None

    def set(self, value, caller=None):

        if value is None:
            self._value = None
            return True, None

        category_obj = self._get_category(value)
        if not category_obj:
            return False, "No such prestige category '%s'" % value

        self._value = value
        return self.validate(caller=caller)

    def get(self):
        if self._value:
            return self._value
        else:
            return self.default

    def get_display_params(self):
        return "<category>"

    def validate(self, caller=None):
        if self.required and not self.get():
            return False, "Required field {} was not provided.  {}".format(
                self.full_name, self.help_text or ""
            )

        return True, None

    def webform_field(self, caller=None):
        from django.forms import CharField

        options = {"label": self.full_name}
        if self.required is not None:
            options["required"] = self.required
        return CharField(**options)


class FormNomination(forms.Paxform):

    form_key = "social_nomination"
    form_purpose = "Describes a social nomination for one or more players."
    form_description = """
    This command allows you to fill out a nomination for a prestige adjustment
    for one or more players, of a given type.
    """

    nominees = fields.CharacterListField(
        required=True,
        full_name="Nominees",
        help_text="You must provide one or more characters for this nomination.",
    )
    category = PrestigeCategoryField(
        required=True,
        full_name="Category",
        help_text="You must provide a valid prestige adjustment category.  "
        "Do 'nominate/types' to see the valid types.",
    )
    type = fields.ChoiceField(
        required=True,
        full_name="Adjustment Type",
        choices=PrestigeNomination.TYPES,
        help_text="You must define whether this nomination is " "for fame or legend.",
    )
    size = fields.ChoiceField(
        required=True,
        full_name="Adjustment Size",
        choices=PrestigeNomination.SIZES,
        help_text="You must provide a valid nomination size.",
    )
    summary = fields.TextField(
        required=False,
        max_length=40,
        full_name="Short Summary",
        help_text="This summary should be very short, and suitable for inclusion on the "
        "'notable' list.",
    )
    reason = fields.TextField(
        required=True,
        max_length=2048,
        full_name="Reason",
        help_text="The reason should be a description of what these nominees did that is so "
        "notable.",
    )

    def _get_character(self, args):
        from typeclasses.characters import Character

        try:
            return Character.objects.get(db_key__iexact=args)
        except Character.DoesNotExist:
            return self._get_character_by_id(args)

    # noinspection PyMethodMayBeStatic
    def _get_character_by_id(self, args):
        from typeclasses.characters import Character

        try:
            key = int(args)
            return Character.objects.get(pk=key)
        except (Character.DoesNotExist, ValueError):
            return None

    def submit(self, caller, values):
        character_list = [self._get_character(value) for value in values["nominees"]]
        asset_owners = [
            char_obj.player_ob.Dominion.assets for char_obj in character_list
        ]
        short_reason = None
        if "summary" in values:
            short_reason = values["summary"]

        try:
            category = PrestigeCategory.objects.get(name__iexact=values["category"])
        except PrestigeCategory.DoesNotExist:
            caller.msg(
                "Something has gone horribly wrong; your category seems to no longer be valid."
            )
            return

        nomination = PrestigeNomination.objects.create(
            nominator=caller.player_ob.Dominion,
            category=category,
            reason=short_reason,
            long_reason=values["reason"],
            adjust_type=values["type"],
            adjust_size=values["size"],
        )
        for asset_owner in asset_owners:
            nomination.nominees.add(asset_owner)
        caller.msg("Nomination submitted.")

        character_names = ["|y" + char_obj.key + "|n" for char_obj in character_list]
        verb = "was"
        if len(character_names) > 1:
            verb = "were"

        adjust_type = "fame"
        if values["type"] == PrestigeNomination.TYPE_LEGEND:
            adjust_type = "legend"

        size_name = "small"
        for size_tup in PrestigeNomination.SIZES:
            if size_tup[0] == values["size"]:
                size_name = size_tup[1].lower()

        inform_guides(
            "|wPRESTIGE:|n %s %s nominated for %s %s %s adjustment.  Do 'review_nomination %d' for details."
            % (
                commafy(character_names),
                verb,
                a_or_an(size_name),
                size_name,
                adjust_type,
                nomination.id,
            )
        )


class CmdSocialNominate(PaxformCommand):
    """
    Describes a social nomination for one or more players.

    Usage:
      nominate/create
      nominate/check
      nominate/category <category>
      nominate/nominees <character1>[,character2...]
      nominate/reason [value]
      nominate/size [Small||Medium||Large||Huge]
      nominate/summary [value]
      nominate/cancel
      nominate/submit
      nominate/types

    This command allows you to fill out a nomination for a prestige adjustment
    for one or more players, of a given type.  /create, /cancel, and /submit
    will manage the submission of this form, while /check will make sure your
    form has valid values.

    The /category, /nominees, /reason, /size, and /summary values will fill
    out the various fields of the form.

    Lastly, nominate/types will list the valid categories you can use in
    filling out a nomination.
    """

    key = "nominate"
    locks = "cmd:all()"
    form_class = FormNomination

    def func(self):
        if "types" in self.switches:
            table = EvTable("|wName|n", "|wDescription|n")
            for prestige_type in PrestigeCategory.objects.all():
                table.add_row(prestige_type.name, prestige_type.description)
            self.msg(str(table))
            return

        super(CmdSocialNominate, self).func()


class CmdSocialReview(ArxCommand):
    """
    Reviews pending social nominations.

    Usage:
      review_nomination [id]
      review_nomination/approve <id>
      review_nomination/deny <id>
    """

    key = "review_nomination"
    locks = "cmd:perm(helper)"

    # noinspection PyMethodMayBeStatic
    def pending_nomination(self, arg):
        try:
            int_arg = int(arg)
            nomination = PrestigeNomination.objects.get(id=int_arg)
            return nomination
        except (ValueError, PrestigeNomination.DoesNotExist):
            return None

    def func(self):
        if not self.args:
            pending = PrestigeNomination.objects.filter(pending=True)

            if pending.count() == 0:
                self.msg("No pending nominations.")
                return

            table = EvTable("|wID|n", "|wType|n", "|wSize|n", "|wCharacters|n")
            for nom in pending.all():
                adjust_type = "Fame"
                if nom.adjust_type == PrestigeNomination.TYPE_LEGEND:
                    adjust_type = "Legend"

                size_name = "Small"
                for size_tup in PrestigeNomination.SIZES:
                    if size_tup[0] == nom.adjust_size:
                        size_name = size_tup[1]

                names = [str(nominee) for nominee in nom.nominees.all()]
                table.add_row(nom.id, adjust_type, size_name, commafy(names))
            self.msg(table)
            return

        nom = self.pending_nomination(self.args)
        if not nom:
            self.msg("No pending nomination with that ID.")
            return

        if "approve" in self.switches:
            if self.caller.check_permstring("builders"):
                self.msg("Since you're staff, approving immediately.")
                nom.apply()
                return
            nom.approve(self.caller)
            self.msg("Your approval has been recorded.")
            return

        if "deny" in self.switches:
            if self.caller.check_permstring("builders"):
                self.msg("Since you're staff, denying immediately.")
                inform_guides(
                    "|wPRESTIGE:|n %s has manually denied nomination %d"
                    % (self.caller.name, nom.id)
                )
                nom.pending = False
                nom.approved = False
                nom.save()
                return
            nom.deny(self.caller)
            self.msg("Your denial has been recorded.")
            return

        adjust_type = "Fame"
        if nom.adjust_type == PrestigeNomination.TYPE_LEGEND:
            adjust_type = "Legend"

        size_name = "Small"
        for size_tup in PrestigeNomination.SIZES:
            if size_tup[0] == nom.adjust_size:
                size_name = size_tup[1]

        names = [str(nominee) for nominee in nom.nominees.all()]
        approved_by = [str(approver) for approver in nom.approved_by.all()]
        denied_by = [str(denier) for denier in nom.denied_by.all()]

        result = "\n|wID:|n %d\n" % nom.id
        result += "|wNominees:|n %s\n" % commafy(names)
        result += "|wNominated by:|n %s\n" % str(nom.nominator)
        result += "|wApproved by:|n %s\n" % commafy(approved_by)
        result += "|wDenied by: %s\n" % commafy(denied_by)
        result += "|wType:|n %s %s\n" % (size_name, adjust_type)
        if nom.reason:
            result += "|wSummary:|n %s\n" % nom.reason
        result += "|wReason:|n\n%s\n" % nom.long_reason
        self.msg(result)

        return


class CmdThink(ArxCommand):
    """
    Think to yourself

    Usage:
        +think <message>

    Sends a message to yourself about your thoughts. At present, this
    is really mostly for your own use in logs and the like. Eventually,
    characters with mind-reading powers may be able to see these.
    """

    key = "+think"
    locks = "cmd:all()"
    help_category = "Social"

    def func(self):
        """Execute command."""
        caller = self.caller
        caller.msg("You think: %s" % self.args)


class CmdFeel(ArxCommand):
    """
    State what your character is feeling

    Usage:
        +feel

    Sends a message to yourself about your feelings. Can possibly
    be seen by very sensitive people.
    """

    key = "+feel"
    locks = "cmd:all()"
    help_category = "Social"

    def func(self):
        """Execute command."""
        caller = self.caller
        caller.msg("You feel: %s" % self.args)


class CmdDonate(ArxCommand):
    """
    Donates money to some group

    Usage:
        +donate <group name>=<amount>
        +donate/hype <player>,<group>=<amount>
        +donate/score [<group>]

    Donates money to some group of npcs in exchange for prestige.
    """

    key = "+donate"
    locks = "cmd:all()"
    help_category = "Social"
    action_point_cost = 1

    def get_help(self, caller, cmdset):
        msg = (
            self.__doc__
            + """
    +donate/score lists donation amounts. Costs {w%s{n AP.
    """
            % (self.action_point_cost)
        )
        return msg

    @property
    def donations(self):
        """Queryset of donations by caller"""
        return self.caller.player.Dominion.assets.donations.all().order_by("amount")

    def func(self):
        """Execute command."""
        caller = self.caller
        try:
            if "score" in self.switches:
                return self.display_score()
            if not self.lhs:
                self.list_donations(caller)
                return
            group = self.get_donation_target()
            if not group:
                return
            try:
                val = int(self.rhs)
                if val > caller.db.currency:
                    raise CommandError("Not enough money.")
                if val <= 0:
                    raise ValueError
                if not caller.player.pay_action_points(self.action_point_cost):
                    raise CommandError("Not enough AP.")
                caller.pay_money(val)
                group.donate(val, self.caller)
            except (TypeError, ValueError):
                raise CommandError("Must give a positive number.")
        except CommandError as err:
            caller.msg(err)

    def list_donations(self, caller):
        """Lists donations to the caller"""
        msg = "{wDonations:{n\n"
        table = PrettyTable(["{wGroup{n", "{wTotal{n"])
        for donation in self.donations:
            table.add_row([str(donation.receiver), donation.amount])
        msg += str(table)
        caller.msg(msg)

    def get_donation_target(self):
        """Get donation object"""
        org, npc = self.get_org_or_npc_from_args()
        if not org and not npc:
            return
        if "hype" in self.switches:
            player = self.caller.player.search(self.lhslist[0])
            if not player:
                return
            donations = player.Dominion.assets.donations
        else:
            donations = self.caller.player.Dominion.assets.donations
        if org:
            return donations.get_or_create(organization=org)[0]
        return donations.get_or_create(npc_group=npc)[0]

    def get_org_or_npc_from_args(self):
        """Get a tuple of org, npc used for getting the donation object"""
        org, npc = None, None
        if "hype" in self.switches:
            if len(self.lhslist) < 2:
                raise CommandError("Usage: <player>,<group>=<amount>")
            name = self.lhslist[1]
        else:
            name = self.lhs
        try:
            org = Organization.objects.get(name__iexact=name)
            if org.secret and not self.caller.check_permstring("builders"):
                if not org.active_members.filter(player__player=self.caller.player):
                    org = None
                    raise Organization.DoesNotExist
        except Organization.DoesNotExist:
            try:
                npc = InfluenceCategory.objects.get(name__iexact=name)
            except InfluenceCategory.DoesNotExist:
                raise CommandError(
                    "Could not find an organization or npc group by the name %s." % name
                )
        return org, npc

    def display_score(self):
        """Displays score for donations"""
        if self.args:
            return self.display_score_for_group()
        return self.display_top_donor_for_each_group()

    def display_score_for_group(self):
        """Displays a list of the top 10 donors for a given group"""
        org, npc = self.get_org_or_npc_from_args()
        if org and org.secret:
            raise CommandError("Cannot display donations for secret orgs.")
        group = org or npc
        if not group:
            return
        msg = "Top donors for %s\n" % group
        table = PrettyTable(["Donor", "Amount"])
        for donation in (
            group.donations.filter(amount__gt=0).distinct().order_by("-amount")
        ):
            table.add_row([str(donation.giver), str(donation.amount)])
        msg += str(table)
        self.msg(msg)

    def display_top_donor_for_each_group(self):
        """Displays the highest donor for each group"""
        orgs = Organization.objects.filter(donations__isnull=False)
        if not self.caller.check_permstring("builders"):
            orgs = orgs.exclude(secret=True)
        orgs = list(orgs.distinct())
        npcs = list(
            InfluenceCategory.objects.filter(donations__isnull=False).distinct()
        )
        groups = orgs + npcs
        table = PrettyTable(["Group", "Top Donor", "Donor's Total Donations"])
        top_donations = []
        for group in groups:
            donation = (
                group.donations.filter(amount__gt=0)
                .order_by("-amount")
                .distinct()
                .first()
            )
            if donation:
                top_donations.append(donation)
        top_donations.sort(key=lambda x: x.amount, reverse=True)
        for donation in top_donations:
            table.add_row(
                [str(donation.receiver), str(donation.giver), str(donation.amount)]
            )
        self.msg(str(table))


class CmdRandomScene(ArxCommand):
    """
    @randomscene - Claim roleplay (RP) scenes for weekly XP.
    Usage:
        @randomscene
        @randomscene/claim <player>=<summary of the scene>
        @randomscene/validate <player>
        @randomscene/viewrequests
        @randomscene/online

    Execute the command to generate names. Once you meet and share a scene,
    use @randomscene/claim to request they validate it. If they agree, you'll
    both receive xp during the weekly script. Unanswered requests are wiped
    weekly. The /claim switch requires both of you to be in the same room.
    The claimed character will receive XP whether or not they validate.
    @randomscene/online displays only currently connected players.

    Players should only use @randomscene/claim after meaningful interaction,
    not simply being in the same room or acknowledgment in passing. If anyone
    uses @randomscene/claim on you without meaningful interaction, please do
    not @randomscene/validate the request, and please let staff know.

    A random RP command is also chosen, granting you weekly XP when used.
    Use 'help <command>' if you are unfamiliar with its use!
    """

    key = "@randomscene"
    aliases = ["@rs"]
    locks = "cmd:all()"
    help_category = "Social"
    NUM_SCENES = 3
    NUM_DAYS = 3
    DAYS_FOR_NEWBIE_CHECK = 14
    random_rp_command_keys = [
        "knock",
        "shout",
        "mutter",
        "petition",
        "goals",
        "+plots",
        "+room_mood",
        "+roomtitle",
        "+tempdesc",
        "flashback",
    ]

    @property
    def scenelist(self):
        """Randomly generated list of players we can claim"""
        return self.caller.player_ob.db.random_scenelist or []

    @property
    def claimlist(self):
        """List of people we have claimed and who have asked to claim us"""
        return list(
            set(
                list(self.caller.player_ob.db.claimed_scenelist or [])
                + list(self.requested_validation)
            )
        )

    @property
    def validatedlist(self):
        """List of players we have validated the scenes for"""
        return self.caller.player_ob.db.validated_list or []

    @property
    def requested_validation(self):
        """List of players who have requested to claim us"""
        return self.caller.player_ob.db.requested_validation or []

    @property
    def masked_validated_list(self):
        """Yet another fucking special case made necessary by fucking masks"""
        if self.caller.player_ob.db.masked_validated_list is None:
            self.caller.player_ob.db.masked_validated_list = {}
        return self.caller.player_ob.db.masked_validated_list

    @property
    def newbies(self):
        """A list of new players we want to encourage people to RP with

        Returns:
            List: valid_choices queryset filtered by new players and
                  returned as a list instead.
        """
        newness = datetime.now() - timedelta(days=self.DAYS_FOR_NEWBIE_CHECK)
        newbies = (
            self.valid_choices.filter(
                Q(roster__accounthistory__start_date__gte=newness)
                & Q(roster__accounthistory__end_date__isnull=True)
            )
            .distinct()
            .order_by("db_key")
        )
        return list(newbies)

    @property
    def gms(self):
        """A list of GMs of active events in the current space.

        Returns:
            list: list of gms for any active event in the room
        """
        loc = self.caller.location
        event = loc.event
        if not event:
            return []
        gms = [
            ob.player.char_ob
            for ob in event.gms.all()
            if ob.player and ob.player.char_ob
        ]
        return [gm for gm in gms if gm.location == loc]

    @property
    def valid_choices(self):
        """property that returns queryset of our valid Characters that could be our @rs list

        Returns:
            queryset: Queryset of Character objects

        """
        last_week = datetime.now() - timedelta(days=self.NUM_DAYS)
        return Character.objects.filter(
            Q(roster__roster__name="Active")
            & ~Q(roster__current_account=self.caller.roster.current_account)
            & Q(roster__player__last_login__isnull=False)
            & Q(
                Q(roster__player__last_login__gte=last_week)
                | Q(roster__player__db_is_connected=True)
            )
            & Q(roster__player__is_staff=False)
            & ~Q(roster__player__db_tags__db_key="staff_npc")
        ).distinct()

    @property
    def valid_scene_choices(self):
        """List of valid_choices but without newbies or those already claimed."""
        newbies = [ob.id for ob in self.newbies]
        claimlist = [ob.id for ob in self.claimlist if ob.id not in newbies]
        choices = self.valid_choices
        if newbies:
            choices = choices.exclude(id__in=newbies)
        if claimlist:
            choices = choices.exclude(id__in=claimlist)
        return list(choices)

    @property
    def num_remaining_scenes(self):
        """Number of remaining scenes for the caller"""
        options = (len(self.valid_scene_choices), self.NUM_SCENES)
        return min(options)

    @property
    def need_to_generate_lists(self):
        """Bool luv u."""
        potential = len(self.scenelist) + len(
            [ob for ob in self.claimlist if ob not in self.newbies]
        )
        return potential < self.num_remaining_scenes

    def display_lists(self):
        """Displays (and generates, if needed) the list of players we can claim and have validated."""
        for ob in self.scenelist[:]:
            try:
                ob.roster.roster.refresh_from_db()
                ob.roster.refresh_from_db()
                ob.refresh_from_db()
                if ob.roster.roster.name != "Active":
                    self.caller.player_ob.db.random_scenelist.remove(ob)
            except (AttributeError, TypeError, ValueError):
                pass
        if self.need_to_generate_lists:
            self.generate_lists()
        scenelist = self.scenelist
        claimlist = self.claimlist
        validated = self.validatedlist
        gms = self.gms
        newbies = [ob for ob in self.newbies if ob not in claimlist]
        msg = "{w@Randomscene Information for this week:{n "
        if "online" in self.switches:
            msg += "{yOnly displaying online characters.{n"
            scenelist = [ob for ob in scenelist if ob.show_online(self.caller.player)]
            newbies = [ob for ob in newbies if ob.show_online(self.caller.player)]
        if scenelist:
            msg += "\n{wRandomly generated RP partners:{n "
            msg += list_to_string([ob.key for ob in scenelist])
        if newbies:
            msg += "\n{wNew players who can be also RP'd with for credit:{n "
            msg += list_to_string([ob.key for ob in newbies])
        if gms:
            msg += "\n{wGMs for events here that can be claimed for credit:{n "
            msg += list_to_string(gms)
        if not any((scenelist, newbies, gms)):
            msg += "\n{wNo players remain to be claimed.{n"
        else:
            msg += "\n{yReminder: Please only /claim those you have interacted with significantly in a scene.{n"
        if claimlist:
            msg += "\n{wThose you have already RP'd with:{n "
            msg += list_to_string([ob.key for ob in claimlist])
        if validated:
            msg += "\n{wThose you have validated scenes for:{n "
            masked = dict(self.masked_validated_list)
            msg += list_to_string(
                [ob.key if ob not in masked else masked[ob] for ob in validated]
            )
        if not any((scenelist, newbies, gms, claimlist, validated)):
            msg = "No characters qualify for @randomscene information to be displayed."
        # random RP Tool!
        if (
            not self.caller.db.random_rp_command_this_week
            and not self.caller.db.rp_command_used
        ):
            self.generate_random_command()
        msg += (
            "\n|wRandomly chosen Roleplay Tool:|n %s"
            % self.caller.db.random_rp_command_this_week
        )
        if self.caller.db.rp_command_used:
            msg += "|y (Already used)|n"
        self.msg(msg)

    def generate_lists(self):
        """Generates our random choices of people we can claim this week."""
        scenelist = self.scenelist
        newbies = self.newbies
        claimlist = [ob for ob in self.claimlist if ob not in newbies]
        choices = self.valid_scene_choices
        num_scenes = self.NUM_SCENES - (len(claimlist) + len(scenelist))
        if num_scenes > 0:
            try:
                scenelist.extend(random.sample(choices, num_scenes))
            except ValueError:
                scenelist.extend(choices)
        scenelist = sorted(scenelist, key=lambda x: x.key.capitalize())
        self.caller.player_ob.db.random_scenelist = scenelist

    def generate_random_command(self):
        """Generates our random RP Tool of the week."""
        self.caller.db.random_rp_command_this_week = random.choice(
            self.random_rp_command_keys
        )

    def claim_scene(self):
        """Sends a request from caller to another player to validate their scene."""
        targ = self.caller.search(self.lhs)
        if not targ:
            return
        try:
            cannot_claim = bool(targ.fakename)
        except AttributeError:
            cannot_claim = True
        messagelist = list(self.scenelist) + list(self.newbies) + list(self.gms)
        err = ""
        if targ == self.caller or cannot_claim:
            err = "You cannot claim '%s'." % self.lhs
        elif not self.rhs:
            err = "You must include some summary of the scene. It may be quite short."
        elif targ in self.claimlist:
            err = "You have already claimed a scene with %s this week." % self.lhs
        elif targ not in messagelist:
            err = (
                "%s is not in your list of random scene partners this week." % self.lhs
            )
        if err:
            self.msg(err)
            return
        requests = targ.db.scene_requests or {}
        tup = (self.caller, self.rhs)
        name = self.caller.name
        from server.utils.arx_utils import strip_ansi

        name = strip_ansi(name)
        requests[name.lower()] = tup
        targ.db.scene_requests = requests
        msg = (
            "%s has submitted a RP scene that included you, for which you have received xp. "
            % name
        )
        msg += "Validating it will grant them xp."
        msg += "\n\nTheir summary of the scene was the following: %s" % self.rhs
        msg += "\nIf you ignore this request, it will be wiped in weekly maintenance."
        msg += "\nTo validate, use {w@randomscene/validate %s{n" % name
        msg += "\n{rYou are already flagged for xp, and are not penalized in any way for ignoring a request "
        msg += "from someone who did not meaningfully interact with you.{n"
        targ.player_ob.inform(msg, category="Validate")
        inform_staff(
            "%s has completed this random scene with %s: %s"
            % (self.caller.key, targ, self.rhs)
        )
        self.msg(
            "You have sent %s a request to validate your scene: %s"
            % (self.lhs, self.rhs)
        )
        our_requests = self.requested_validation
        our_requests.append(targ)
        self.caller.player_ob.db.requested_validation = our_requests
        if targ in self.scenelist:
            self.scenelist.remove(targ)

    def validate_scene(self):
        """Grants a request to validate a randomscene."""
        scene_requests = self.caller.db.scene_requests or {}
        name = self.args.lower()
        targ = scene_requests.pop(name, (None, ""))[0]
        self.caller.db.scene_requests = scene_requests
        if not targ:
            self.msg("No character by that name has sent you a request.")
            self.view_requests()
            return
        validated = self.caller.player_ob.db.validated_list or []
        claimed = targ.player_ob.db.claimed_scenelist or []
        claimed.append(self.caller)
        targ_scenelist = targ.player_ob.db.random_scenelist or []
        if self.caller in targ_scenelist:
            targ_scenelist.remove(self.caller)
            targ.player_ob.db.random_scenelist = targ_scenelist
        targ.player_ob.db.claimed_scenelist = claimed
        self.msg("Validating their scene. Both of you will receive xp for it later.")
        validated.append(targ)
        self.caller.player_ob.db.validated_list = validated
        if targ.key.lower() != name:
            self.masked_validated_list[targ] = name

    def view_requests(self):
        """Views current requests for validation."""
        requests = self.caller.db.scene_requests or {}
        table = EvTable("{wName{n", "{wSummary{n", width=78, border="cells")
        for tup in requests.values():
            table.add_row(tup[0], tup[1])
        self.msg(str(table))

    def func(self):
        """Main function for RandomScene"""
        if (not self.switches or "online" in self.switches) and not self.args:
            self.display_lists()
            return
        if "claim" in self.switches or (not self.switches and self.args):
            self.claim_scene()
            return
        if "validate" in self.switches:
            self.validate_scene()
            return
        if "viewrequests" in self.switches:
            self.view_requests()
            return
        self.msg("Invalid switch.")


class CmdCensus(ArxPlayerCommand):
    """
    Displays population of active players by fealty

    Usage:
        +census

    Lists the number of active characters in each fealty. New characters
    created receive an xp bonus for being in a less populated fealty.
    """

    key = "+census"
    locks = "cmd:all()"
    help_category = "Information"

    def func(self):
        """Displays the census information"""
        from .guest import census_of_fealty

        fealties = census_of_fealty()
        table = PrettyTable(["{wFealty{n", "{w#{n"])
        for fealty in fealties:
            table.add_row([fealty, fealties[fealty]])
        self.msg(table)


class CmdRoomTitle(RewardRPToolUseMixin, ArxCommand):
    """
    Displays what your character is currently doing in the room

    Usage:
        +roomtitle <description>

    Appends a short blurb to your character's name when they are displayed
    to the room in parentheses. Use +roomtitle with no argument to remove
    it.
    """

    key = "+roomtitle"
    aliases = ["room_title", "permapose"]
    locks = "cmd:all()"
    help_category = "Social"

    def func(self):
        """Sets or clears a roomtitle for the caller"""
        if not self.args:
            self.msg("Roomtitle cleared.")
            self.caller.attributes.remove("room_title")
            return
        self.caller.db.room_title = self.args
        self.msg("Your roomtitle set to %s {w({n%s{w){n" % (self.caller, self.args))
        self.mark_command_used()


class CmdTempDesc(RewardRPToolUseMixin, ArxCommand):
    """
    Appends a temporary description to your regular description

    Usage:
        +tempdesc <description>

    Appends a short blurb to your character's description in parentheses.
    Use +tempdesc with no argument to remove it.
    """

    key = "+tempdesc"
    locks = "cmd:all()"
    help_category = "Social"

    def func(self):
        """Sets or removes a temporary desc from the character"""
        if not self.args:
            self.msg("Temporary description cleared.")
            del self.caller.additional_desc
            return
        self.caller.additional_desc = self.args
        self.msg("Temporary desc set to: %s" % self.args)
        self.mark_command_used()


class CmdLanguages(ArxCommand):
    """
    Sets the languages you speak, and can teach to others

    Usage:
        +lang
        +lang <language>
        +lang/translate <object>
        +lang/teachme <player>=<language>
        +lang/teach <player>

    Shows what languages you know and are currently speaking. You can request
    that a player teach you a language with +lang/teachme. Translate allows you
    to read material written in other languages. Higher ranks of linguistics
    allow you to learn more languages.
    """

    key = "+lang"
    locks = "cmd:all()"
    help_category = "Social"

    def list_languages(self):
        """Lists the languages the caller can speak"""
        known = [ob.capitalize() for ob in self.caller.languages.known_languages]
        known += ["Arvani"]
        self.msg("{wYou can currently speak:{n %s" % ", ".join(known))
        self.msg(
            "You can learn %s additional languages."
            % self.caller.languages.additional_languages
        )

    def func(self):
        """Executes the language command"""
        if not self.args:
            self.msg(
                "{wYou are currently speaking:{n %s"
                % self.caller.languages.current_language.capitalize()
            )
            self.list_languages()
            return
        if "translate" in self.switches:
            obj = self.caller.search(self.args)
            if not obj:
                return
            translation = obj.item_data.translation
            matches = False
            for lang in self.caller.languages.known_languages:
                if lang in translation:
                    self.msg(
                        "You translate the following from %s:\n%s"
                        % (lang.capitalize(), translation[lang])
                    )
                    matches = True
            if not matches:
                self.msg(
                    "%s does not seem to contain any foreign tongue you can read." % obj
                )
            return
        if not self.switches:
            args = self.args.lower()
            if args == "arvani" or args == "common":
                self.caller.attributes.remove("currently_speaking")
                self.msg("{wYou are now speaking Arvani.{n")
                return
            if args not in self.caller.languages.known_languages:
                self.msg("You cannot speak %s." % self.args)
                self.list_languages()
                return
            self.caller.db.currently_speaking = args
            self.msg("{wYou are now speaking %s.{n" % self.args)
            return
        player = self.caller.player.search(self.lhs)
        if not player:
            return
        targ = player.char_ob
        if not targ:
            self.msg("Not found.")
            return
        if "teachme" in self.switches:
            if self.caller.languages.additional_languages <= 0:
                self.msg(
                    "You need a higher rank of linguistics before you can learn anything else."
                )
                return
            req = targ.ndb.language_requests or {}
            req[self.caller] = self.rhs
            targ.ndb.language_requests = req
            self.msg("You request that %s teach you %s." % (targ, self.rhs))
            targ.msg(
                "{w%s has requested that you teach them %s.{n" % (self.caller, self.rhs)
            )
            return
        if "teach" in self.switches:
            req = self.caller.ndb.language_requests or {}
            if targ not in req:
                self.msg("You do not have a request from %s." % targ)
                return
            lang = req[targ].lower()
            if lang not in self.caller.languages.known_languages:
                self.msg("You do not know %s." % lang)
                self.list_languages()
                return
            if targ.languages.max_languages <= len(targ.languages.known_languages):
                self.msg("They know as many languages as they can learn.")
                return
            targ.languages.add_language(lang)
            self.msg("You have taught %s to %s." % (lang, targ))
            targ.msg("%s has taught you %s." % (self.caller, lang))
            return


class CmdIAmHelping(ArxPlayerCommand):
    """
    Donates AP to other players at a poor conversion rate

        Usage:
            +iamhelping <player>=<AP>

    Allows you to donate AP to other players (with some restrictions) to
    represent helping them out with whatever they're up to: gathering supplies
    for a crafter, acting as a menial servant/helping their servants manage
    their affairs, discreetly having annoying npcs killed, etc. It's much more
    effective to assist directly with investigations, crisis actions, etc,
    using those respective commands. Rate of AP conversion is 3 to 1.
    """

    key = "+iamhelping"
    help_category = "Social"
    ap_conversion = 3

    def func(self):
        """Executes the +iamhelping command"""
        try:
            from evennia.server.models import ServerConfig

            if not self.args:
                self.msg("You have %s AP remaining." % self.caller.roster.action_points)
                return
            if ServerConfig.objects.conf(key="DISABLE_AP_TRANSFER"):
                raise CommandError("AP transfers are temporarily disabled.")
            targ = self.caller.search(self.lhs)
            if not targ:
                return
            try:
                val = int(self.rhs)
            except (ValueError, TypeError):
                raise CommandError("AP needs to be a number.")
            if self.caller.roster.current_account == targ.roster.current_account:
                raise CommandError("You cannot give AP to an alt.")
            receive_amt = val // self.ap_conversion
            if receive_amt < 1:
                raise CommandError("Must transfer at least %s AP." % self.ap_conversion)
            max_ap = targ.roster.max_action_points
            if targ.roster.action_points + receive_amt > max_ap:
                raise CommandError("That would put them over %s AP." % max_ap)
            if not self.caller.pay_action_points(val):
                raise CommandError("You do not have enough AP.")
            targ.pay_action_points(-receive_amt)
            self.msg(
                "Using %s of your AP, you have given %s %s AP."
                % (val, targ, receive_amt)
            )
            msg = "%s has given you %s AP." % (self.caller, receive_amt)
            targ.inform(msg, category=msg)
        except CommandError as err:
            self.msg(err)


class CmdRPHooks(ArxPlayerCommand):
    """
    Sets or searches RP hook tags

    Usage:
        +rphooks <character>
        +rphooks/search <tag>
        +rphooks/add <searchable title>[=<optional description>]
        +rphooks/rm <searchable title>
    """

    key = "+rphooks"
    help_category = "Social"
    aliases = ["rphooks"]

    def list_valid_tags(self):
        """Lists the existing tags for rp hooks"""
        tags = Tag.objects.filter(db_category="rp hooks").order_by("db_key")
        self.msg("Categories: %s" % "; ".join(tag.db_key for tag in tags))
        return

    def func(self):
        """Executes the RPHooks command"""
        if not self.switches:
            if not self.args:
                targ = self.caller
            else:
                targ = self.caller.search(self.args)
                if not targ:
                    self.list_valid_tags()
                    return
            hooks = targ.tags.get(category="rp hooks") or []
            hooks = make_iter(hooks)
            hook_descs = targ.db.hook_descs or {}
            table = EvTable("Hook", "Desc", width=78, border="cells")
            for hook in hooks:
                table.add_row(hook, hook_descs.get(hook, ""))
            table.reformat_column(0, width=20)
            table.reformat_column(1, width=58)
            self.msg(table)
            if not hooks:
                self.list_valid_tags()
            return
        if "add" in self.switches:
            title = self.lhs.lower()
            if len(title) > 25:
                self.msg("Title must be under 25 characters.")
                return
            # test characters in title
            if not self.validate_name(title):
                return
            data = self.rhs
            hook_descs = self.caller.db.hook_descs or {}
            self.caller.tags.add(title, category="rp hooks")
            if data:
                hook_descs[title] = data
                self.caller.db.hook_descs = hook_descs
            data_str = (": %s" % data) if data else ""
            self.msg("Added rphook tag: %s%s." % (title, data_str))
            return
        if "search" in self.switches:
            table = EvTable("Name", "RPHook", "Details", width=78, border="cells")
            if not self.args:
                self.list_valid_tags()
                return
            tags = Tag.objects.filter(
                db_key__icontains=self.args, db_category="rp hooks"
            )
            for tag in tags:
                for pc in tag.accountdb_set.all():
                    hook_desc = pc.db.hook_descs or {}
                    desc = hook_desc.get(tag.db_key, "")
                    table.add_row(pc, tag.db_key, desc)
            table.reformat_column(0, width=10)
            table.reformat_column(1, width=20)
            table.reformat_column(2, width=48)
            self.msg(table)
            return
        if "rm" in self.switches or "remove" in self.switches:
            args = self.args.lower()
            hook_descs = self.caller.db.hook_descs or {}
            if args in hook_descs:
                del hook_descs[args]
                if not hook_descs:
                    self.caller.attributes.remove("hook_descs")
                else:
                    self.caller.db.hook_descs = hook_descs
            tagnames = self.caller.tags.get(category="rp hooks") or []
            if args not in tagnames:
                self.msg("No rphook by that category name.")
                return
            self.caller.tags.remove(args, category="rp hooks")
            self.msg("Removed.")
            return
        self.msg("Invalid switch.")

    def validate_name(self, name):
        """Ensures that RPHooks doesn't have a name with special characters that would break it"""
        import re

        if not re.findall("^[\w',]+$", name):
            self.msg("That category name contains invalid characters.")
            return False
        return True


class CmdFirstImpression(ArxCommand):
    """
    An award for a first RP scene with another player

    Usage:
        +firstimpression[/previous] <character>
        +firstimpression <character>=<summary of the RP Scene>
        +firstimpression/list[/previous]
        +firstimpression/here
        +firstimpression/outstanding
        +firstimpression/quiet <character>=<summary>
        +firstimpression/private <character>=<summary>
        +firstimpression/all <character>=<summary>
        +firstimpression/toggleprivate <character>
        +firstimpression/share <character>[=-1, -2, etc]
        +firstimpressions/mine[/previous]
        +firstimpression/publish <character>[=-1, -2, etc]

    This allows you to claim an xp reward for the first time you
    have a scene with another player. You receive 1 xp, while the
    player you write the summary for receives 4 xp. Should they
    return the favor, you'll receive 4 and they'll receive 1. The other
    player receives an inform of the summary you write, and a prompt
    to let them know they can use the command in return. This command
    requires you to be in the same room, as a small reminder that this
    should take place after an RP scene.

    The summary should be an IC account. If it is private, it is treated
    as a black journal entry only to yourself. If it is not private, but
    marked without the 'all' switch, it is treated as a privately conferred
    note. If both players choose to share/publish it, it is treated as
    a white journal. You can choose not to send an inform of what you wrote
    if you use the /private switch, or choose not to send an inform at all
    with the /quiet switch. Using /all will mean everyone can see it. If no
    switches are used, only the receiver can see it.

    /toggleprivate and /share determines who can view the first
    impression you write. A private first impression isn't viewable
    by anyone but you and staff. /share will set the writer's consent for
    the first impression to be viewable by everyone. The receiver can then
    grant their consent for it to be a publicly viewable account by using
    the /publish command, which makes it viewable on their character sheet.

    Using the /publish, /share, or /all switch will grant the user 1 xp.
    They cannot be reversed once set.

    If you wish to /publish or /share a first impression of a character that
    was played by a previous character, you must specify a negative number.
    For example, '+firstimpression/publish bob=-1' is for the previous player
    of Bob who wrote a first impression of you.

    To see firstimpressions written by or on a previous version of your
    character, use the /previous switch.
    """

    key = "+firstimpression"
    help_category = "Social"
    aliases = ["+firstimpressions"]

    @property
    def imps_of_me(self):
        """Retrieves impressions of us, in our current incarnation"""
        return self.caller.roster.impressions_of_me

    @property
    def imps_by_me(self):
        """Retrieves impressions we have written, as our current incarnation"""
        return self.caller.roster.accounthistory_set.last().initiated_contacts.all()

    @property
    def previous_imps_by_me(self):
        """Retrieves impressions written by previous incarnations"""
        return FirstContact.objects.filter(
            from_account__in=self.caller.roster.previous_history
        )

    def list_valid(self):
        """Sends msg to caller of list of characters they can make firstimpression of"""
        contacts = AccountHistory.objects.claimed_impressions(self.caller.roster)
        if "list" in self.switches:
            if "previous" in self.switches:
                contacts = AccountHistory.objects.filter(
                    contacted_by__in=self.caller.roster.previous_history
                )
            self.msg(
                "{wCharacters you have written first impressions of:{n %s"
                % ", ".join(str(ob.entry) for ob in contacts)
            )
            return
        qs = AccountHistory.objects.unclaimed_impressions(self.caller.roster)
        if "outstanding" in self.switches:
            impressions = self.imps_of_me.filter(private=False, from_account__in=qs)
            authors_and_imps = [
                '{c%s{n: "%s"' % (ob.writer, ob.summary) for ob in impressions
            ]
            self.msg(
                "First Impressions you have not yet reciprocated: \n%s"
                % "\n".join(authors_and_imps)
            )
            return
        location = ""
        if "here" in self.switches:
            location = "at your location "
            qs = qs.filter(entry__character__db_location=self.caller.location)
        players = sorted(
            set(ob.entry.player for ob in qs), key=lambda x: x.username.capitalize()
        )
        self.msg(
            "{wPlayers %syou haven't written a first impression for yet:{n %s"
            % (location, ", ".join(str(ob) for ob in players))
        )

    def func(self):
        """Executes firstimpression command"""
        if "mine" in self.switches:
            by_str = ""
            player = None
            if self.args:
                player = self.caller.player.search(self.args)
                if not player:
                    return
                by_str = " by %s" % self.args.capitalize()
            if "previous" in self.switches:
                msg = (
                    "{wFirst impressions written on previous versions of this character%s:{n\n"
                    % by_str
                )
            else:
                msg = "{wFirst impressions written of you so far%s:{n\n" % by_str
            msg += self.caller.roster.get_impressions_str(
                player=player, previous="previous" in self.switches
            )
            self.msg(msg)
            return
        if not self.args:
            self.list_valid()
            return
        if (not self.switches or "previous" in self.switches) and not self.rhs:
            if "previous" in self.switches:
                qs = self.previous_imps_by_me
            else:
                qs = self.imps_by_me
            history = qs.filter(to_account__entry__player__username__iexact=self.args)
            if not history:
                self.msg(
                    "{wNo history found for %s. Use with no arguments to see a list of valid chars.{n"
                    % self.args
                )
                return
            self.msg("{wYour first impressions of {c%s{n:" % self.args.capitalize())

            def get_privacy_str(roster_object):
                """Formats string of roster_object with whether it's shared and/or private"""
                if roster_object.private:
                    return "{w(Private){n"
                return (
                    "{w(Shared){n" if roster_object.writer_share else "{w(Not Shared){n"
                )

            self.msg(
                "\n".join("%s %s" % (get_privacy_str(ob), ob.summary) for ob in history)
            )
            return
        targ = self.caller.player.search(self.lhs)
        if not targ:
            return
        if targ == self.caller.player:
            self.msg("You cannot record a first impression of yourself.")
            return
        hist = targ.roster.accounthistory_set.last()
        if (
            "toggleprivate" in self.switches
            or "share" in self.switches
            or "publish" in self.switches
        ):
            if self.rhs:
                try:
                    # We get previous first impressions by negative index on the queryset
                    hist = list(targ.roster.accounthistory_set.all())[int(self.rhs) - 1]
                except (ValueError, TypeError, IndexError):
                    self.msg("Couldn't find a first impression by that number")
                    return
            if "publish" in self.switches:
                try:
                    impression = self.imps_of_me.get(from_account=hist)
                except FirstContact.DoesNotExist:
                    self.msg("No impression found by them.")
                    return
                if impression.private:
                    self.msg("That impression is private.")
                    return
                if impression.receiver_share:
                    self.msg("You have already shared that.")
                    return
                impression.receiver_share = True
                impression.save()
                self.caller.adjust_xp(1)
                self.msg(
                    "You have marked %s's impression of you public, and received 1 xp."
                    % targ
                )
                return
            try:
                impression = self.imps_by_me.get(to_account=hist)
            except FirstContact.DoesNotExist:
                self.msg("No impression found of them.")
                return
            if impression.viewable_by_all:
                self.msg(
                    "It has already been shared publicly and can no longer be made private."
                )
                return
            if "toggleprivate" in self.switches:
                impression.private = not impression.private
                impression.save()
                privacy_str = "private" if impression.private else "public"
                self.msg(
                    "Your first impression of %s is now marked %s."
                    % (targ, privacy_str)
                )
                return
            if "share" in self.switches:
                if impression.private:
                    self.msg("A private impression cannot be marked viewable by all.")
                    return
                if impression.writer_share:
                    self.msg("You have already marked that as public.")
                    return
                impression.writer_share = True
                impression.save()
                self.caller.adjust_xp(1)
                self.msg(
                    "You have marked your impression as publicly viewable and gained 1 xp."
                )
                return
            return
        # check if the target has written a first impression of us. If not, we'll need to be in the same room
        received = self.imps_of_me.filter(from_account__entry__player=targ)
        if not received and targ.char_ob.location != self.caller.location:
            self.msg("Must be in the same room.")
            return
        if not self.rhs or len(self.rhs) < 10:
            self.msg("Must write a longer summary of the RP scene.")
            return
        try:
            self.imps_by_me.get(to_account=hist)
            self.msg("You have already written your first impression of them.")
            return
        except FirstContact.DoesNotExist:
            private = "private" in self.switches or "quiet" in self.switches
            writer_share = not private and "all" in self.switches
            self.caller.roster.accounthistory_set.last().initiated_contacts.create(
                to_account=hist,
                private=private,
                writer_share=writer_share,
                summary=self.rhs,
            )
            self.msg(
                "{wYou have recorded your first impression on %s:{n\n%s"
                % (targ, self.rhs)
            )
            if "quiet" not in self.switches:
                msg = (
                    "%s has written their +firstimpression on you, giving you 4 xp."
                    % self.caller.key
                )
                if not received:
                    msg += " If you want to return the favor with +firstimpression, you will gain 1 additional xp, and "
                    msg += (
                        "give them 4 in return. You are under no obligation to do so."
                    )
                if "private" not in self.switches:
                    msg += "\nSummary of the scene they gave: %s" % self.rhs
                targ.inform(msg, category="First Impression")
            inform_staff(
                "%s's first impression of %s: %s" % (self.caller.key, targ, self.rhs)
            )
            xp = 2 if writer_share else 1
            self.caller.adjust_xp(xp)
            self.msg("You have gained %s xp." % xp)
            targ.char_ob.adjust_xp(4)


# noinspection PyAttributeOutsideInit
class CmdGetInLine(ArxCommand):
    """
    Manages lines of people waiting their turn in events

    Usage:
        +line
        +line/createline[/loop] <line host 1>,<line host 2>,<etc>
        +line/loop
        +line/nextinline
        +line/getinline
        +line/dropout
        +line/dismiss

    Allows you to recognize people who are standing in a line for their turn
    to speak. To create a line, use +line/createline with the names of fellow
    hosts who may also control it. +line/loop toggles the line to repeat.
    Call the next person with +line/nextinline. To join a line that's been
    created, use +line/getinline. If you want to give up your turn, use
    +line/dropout. If you are done recognizing people, use +line/dismiss.
    """

    key = "+line"
    aliases = ["getinline", "nextinline"]
    locks = "cmd: all()"
    help_category = "Social"

    @property
    def line(self):
        """The Line object, stored as a list in the caller's location"""
        loc = self.caller.location
        if loc.ndb.event_line is None:
            loc.ndb.event_line = []
        else:  # cleanup line
            for ob in loc.ndb.event_line[:]:
                if hasattr(ob, "location") and ob.location != self.caller.location:
                    loc.ndb.event_line.remove(ob)
        return loc.ndb.event_line

    @line.setter
    def line(self, val):
        self.caller.location.ndb.event_line = val

    @property
    def hosts(self):
        """List of hosts for the line"""
        loc = self.caller.location
        if loc.ndb.event_line_hosts is None:
            loc.ndb.event_line_hosts = []
        loc.ndb.event_line_hosts = [
            ob for ob in loc.ndb.event_line_hosts if ob.location == loc
        ]
        return loc.ndb.event_line_hosts

    @hosts.setter
    def hosts(self, val):
        self.caller.location.ndb.event_line_hosts = val

    @property
    def loop(self):
        """Returns a thingy if line looping was set"""
        return self.caller.location.ndb.event_line_loop

    @loop.setter
    def loop(self, val):
        self.caller.location.ndb.event_line_loop = val

    def check_line(self):
        """Checks if we can create a line, or if one already exists."""
        if not self.hosts and not self.line:
            self.msg("There is no line here. You can create one with +line/createline.")
            return
        return True

    def display_line(self):
        """Displays current line order."""
        line = self.line
        hosts = self.hosts
        if not self.check_line():
            return
        self.msg("|wThis line is hosted by:|n %s" % ", ".join(str(ob) for ob in hosts))
        self.msg("|wCurrent line order:|n %s" % ", ".join(str(ob) for ob in line))

    def join_line(self):
        """Has caller join the line."""
        if self.caller in self.line:
            self.msg("You are already in the line.")
            return
        if not self.line and self.loop:
            self.line.append("|r*Loop Marker*|n")
        self.line.append(self.caller)
        self.caller.location.msg_contents("%s has joined the line." % self.caller)

    def next_in_line(self):
        """Gets the next person in line."""
        if not self.check_line() or not self.can_alter_line():
            return
        line = self.line
        if not line:
            self.msg("No one is next in line.")
            return
        next_guy = line.pop(0)
        from six import string_types

        is_string = isinstance(next_guy, string_types)
        if self.loop:
            self.line.append(next_guy)
            if is_string:
                next_guy = line.pop(0)
                self.line.append(next_guy)
        elif is_string:
            next_guy = line.pop(0)
        self.caller.location.msg_contents("|553Turn in line:|n %s" % next_guy)

    def drop_out(self):
        """Removes caller from the line."""
        line = self.line
        if self.caller in line:
            line.remove(self.caller)
            self.msg("You have been removed from the line.")
            return
        self.msg("You are not in the line.")
        self.display_line()

    def can_alter_line(self):
        """Returns whether they have permission to change the line"""
        hosts = self.hosts
        caller = self.caller
        if caller not in hosts and not caller.check_permstring("builders"):
            self.msg("You do not have permission to alter the line.")
            return
        return True

    def dismiss(self):
        """Gets rid of the line."""
        if not self.can_alter_line:
            return
        if self.loop:
            self.loop = None
        self.line = []
        self.hosts = []
        self.caller.location.msg_contents(
            "The line has been dismissed by %s." % self.caller
        )
        return

    def create_line(self):
        """Creates a new line here."""
        if self.hosts and self.line:
            self.msg("There is a line here already.")
            self.display_line()
            return
        self.line = []
        other_hosts = [self.caller.search(arg) for arg in self.lhslist]
        other_hosts = [ob for ob in other_hosts if ob and ob.player]
        other_hosts.append(self.caller)
        self.hosts = other_hosts
        if "loop" in self.switches:
            self.toggle_loop()
        self.display_line()

    def toggle_loop(self):
        """Toggles whether the line will automatically loop"""
        if not self.can_alter_line():
            return
        if self.loop:
            self.loop = None
        else:
            self.caller.location.ndb.event_line_loop = True
        self.msg("Line looping set to: %s" % str(bool(self.loop)))

    # noinspection PyUnresolvedReferences
    def func(self):
        """Executes the +line command"""
        # check what aliases we have used
        if self.cmdstring == "getinline":
            self.switches.append("getinline")
        if self.cmdstring == "nextinline":
            self.switches.append("nextinline")
        if "createline" in self.switches:
            self.create_line()
            return
        if not self.args and not self.switches:
            self.display_line()
            return
        if not self.check_line:
            return
        if "getinline" in self.switches:
            self.join_line()
            return
        if "nextinline" in self.switches:
            self.next_in_line()
            return
        if "dropout" in self.switches:
            self.drop_out()
            return
        if "dismiss" in self.switches:
            self.dismiss()
            return
        if "loop" in self.switches:
            self.toggle_loop()
            return


class CmdFavor(RewardRPToolUseMixin, ArxPlayerCommand):
    """
    Applies favor or disfavor from an organization to a character

    Usage:
        favor <organization>
        favor/all
        favor/set <organization>=<character>,<value>/<gossip>
        favor/remove <organization>=<character>

    The favor command allows an organization's leadership to show whether
    a character outside the organization has pleased or angered them, which
    applies 5 percent of the organization's fame + legend to the character's
    propriety per favor point. To show that someone has earned the good
    graces of your organization, the favor value should be positive. If
    someone has annoyed you, the value is negative. Positive and negative
    favor are each capped by the social modifier of the organization.

    The cost of applying favor is 200 social resources per point. This value
    is modified by the respect and affection npcs in the organization hold
    toward the character, if any. Positive values make positive favor cheaper
    and negative favor more expensive, and vice-versa.

    Favor cannot be granted to characters in the organization, unless the
    organization is a noble house and the character is of vassal rank. If a
    character joins the organization or is promoted above vassal rank, their
    favor is immediately set to 0.

    When adding favor, you must set a gossip text string that displays what
    npcs would speculate as the reason for someone being held in favor or
    disfavor by an organization.
    """

    key = "favor"
    help_category = "Social"

    def func(self):
        """Executes the favor command"""
        try:
            if not self.switches or "all" in self.switches:
                self.list_favor()
            elif "set" in self.switches or "add" in self.switches:
                self.add_favor()
            elif "remove" in self.switches:
                self.remove_favor()
            else:
                raise CommandError("Invalid switch.")
        except CommandError as err:
            self.msg(err)
        else:
            self.mark_command_used()

    def list_favor(self):
        """Lists who is in favor/disfavor for an organization"""
        if "all" in self.switches:
            favors = Reputation.objects.exclude(favor=0).order_by("-date_gossip_set")
            self.msg("Characters with favor: %s" % ", ".join(str(ob) for ob in favors))
            return
        org = self.get_organization(check_perm=False)
        favors = org.reputations.filter(Q(favor__gt=0) | Q(favor__lt=0)).order_by(
            "-favor"
        )
        msg = "{wThose Favored/Disfavored by %s{n\n" % org
        msg += "\n\n".join(
            "{c%s{w (%s):{n %s" % (ob.player, ob.favor, ob.npc_gossip) for ob in favors
        )
        self.msg(msg)

    def get_organization(self, check_perm=True):
        """Gets an organization and sees if we have permissions to set favor"""
        try:
            org = Organization.objects.get(name__iexact=self.lhs)
        except Organization.DoesNotExist:
            raise CommandError("No organization by the name '%s'." % self.lhs)
        if check_perm and not org.access(self.caller, "favor"):
            raise CommandError("You do not have permission to set favor.")
        return org

    def add_favor(self):
        """Adds favor to a character, assuming we have points to spare and can afford the cost."""
        org = self.get_organization()
        try:
            rhslist, gossip = self.rhs.split("/", 1)
            rhslist = rhslist.split(",")
        except (TypeError, ValueError, AttributeError):
            raise CommandError("You must provide a name, target, and gossip string.")
        try:
            target = self.caller.search(rhslist[0])
            amount = int(rhslist[1])
        except (IndexError, ValueError, TypeError):
            raise CommandError("You must provide both a target and an amount.")
        if not target:
            return
        if not amount:
            raise CommandError("Amount cannot be 0.")
        self.check_cap(org, amount)
        try:
            member = org.active_members.get(player=target.Dominion)
            if org.category != "noble":
                raise CommandError("Cannot set favor for a member.")
            if member.rank < 5:
                raise CommandError("Favor can only be set for vassals or non-members.")
        except Member.DoesNotExist:
            pass
        cost = self.get_cost(org, target, amount)
        if self.caller.ndb.favor_cost_confirmation != cost:
            self.caller.ndb.favor_cost_confirmation = cost
            raise CommandError("Cost will be %s. Repeat the command to confirm." % cost)
        self.caller.ndb.favor_cost_confirmation = None
        if not self.caller.pay_resources("social", cost):
            raise CommandError("You cannot afford to pay %s resources." % cost)
        self.set_target_org_favor(target, org, amount, gossip)

    def set_target_org_favor(self, target, org, amount, gossip):
        """Sets the amount of favor for target's reputation with org"""
        rep, _ = target.Dominion.reputations.get_or_create(organization=org)
        rep.favor = amount
        rep.npc_gossip = gossip
        rep.date_gossip_set = datetime.now()
        rep.save()
        self.msg("Set %s's favor in %s to %s." % (target, org, amount))
        inform_staff(
            "%s set gossip for %s's reputation with %s to: %s"
            % (self.caller, target, org, gossip)
        )

    @staticmethod
    def check_cap(org, amount):
        """Sees if we have enough points remaining"""
        from django.db.models import Sum, Q

        if amount < 0:
            query = Q(favor__lt=0)
        else:
            query = Q(favor__gt=0)
        total = abs(
            org.reputations.filter(query).aggregate(sum=Sum("favor"))["sum"] or 0
        ) + abs(amount)
        mod = org.social_modifier * 5
        if total > mod:
            noun = "favor" if amount > 0 else "disfavor"
            raise CommandError(
                "That would bring your total %s to %s, and you can only spend %s."
                % (noun, total, mod)
            )

    @staticmethod
    def get_cost(org, target, amount):
        """Gets the total cost in social resources for setting favor for target by the amount."""
        rep, _ = target.Dominion.reputations.get_or_create(organization=org)
        base = 200
        if amount > 0:
            base -= rep.respect + rep.affection
        else:
            base += rep.respect + rep.affection
        if base < 0:
            base = 0
        return base * abs(amount)

    def remove_favor(self):
        """Revokes the favor set for a character."""
        org = self.get_organization()
        target = self.caller.search(self.rhs)
        if not target:
            return
        try:
            rep = target.Dominion.reputations.get(organization=org)
        except Reputation.DoesNotExist:
            raise CommandError("They have no favor with %s." % org)
        rep.wipe_favor()
        self.msg("Favor for %s removed." % target)
