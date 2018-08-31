"""

Admin commands

"""
from django.conf import settings
from django.db.models import Q

from evennia.server.sessionhandler import SESSIONS
from evennia.utils import evtable
from evennia.accounts.models import AccountDB
from evennia.objects.models import ObjectDB
from evennia.server.models import ServerConfig
from evennia.typeclasses.tags import Tag
from evennia.scripts.models import ScriptDB

from server.utils import prettytable
from server.utils.arx_utils import inform_staff, broadcast, create_gemit_and_post, ArxCommand, ArxPlayerCommand
from server.utils.exceptions import CommandError
from web.character.models import Clue
from world.dominion.models import Organization, RPEvent, Propriety, AssetOwner
from typeclasses.characters import Character

PERMISSION_HIERARCHY = [p.lower() for p in settings.PERMISSION_HIERARCHY]


class CmdHome(ArxCommand):
    """
    home

    Usage:
      home

    Teleports you to your home location.
    """

    key = "home"
    locks = "cmd:all()"
    help_category = "Travel"

    def func(self):
        """Implement the command"""
        caller = self.caller
        home = caller.home
        room = caller.location
        cscript = room.ndb.combat_manager
        guards = caller.db.assigned_guards or []
        if not caller.check_permstring("builders"):
            if cscript:
                caller.msg("You cannot use home to leave a room where a combat is occurring.")
                return
            if 'private' in room.tags.all():
                if len([ob for ob in room.contents if ob.player]) > 1:
                    caller.msg("You cannot use home to leave a private room if you are not alone.")
                    return
        if not home:
            caller.msg("You have no home!")
        elif home == caller.location:
            caller.msg("You are already home!")
        elif not caller.conscious:
            caller.msg("You must be conscious to go home.")
        else:
            mapping = {'secret': True}
            caller.move_to(home, mapping=mapping)
            caller.msg("There's no place like home ...")
            for guard in guards:
                if guard.location:
                    if 'stationary_guard' not in guard.tags.all():
                        guard.summon()
                else:
                    guard.db.docked = home
            caller.messages.messenger_notification(force=True)


class CmdGemit(ArxPlayerCommand):
    """
    @gemit

    Usage:
      @gemit/norecord <message>
      @gemit/startepisode <name>[/episode synopsis]=<message>
      @gemit <message>
      @gemit/orgs <org>[, <org2>,...]=<message>

    Announces a message to all connected players.
    Unlike @wall, this command will only send the text,
    without "soandso shouts:" attached. It will also be logged to
    all actively running events. Text will be sent in green by
    default. The org switch messages online members, informs offline
    members, and makes an org bboard post.
    """
    key = "@gemit"
    locks = "cmd:perm(gemit) or perm(Wizards)"
    help_category = "GMing"

    # noinspection PyAttributeOutsideInit
    def func(self):
        """Implements command"""
        try:
            if not self.args:
                raise CommandError("Usage: @gemit <message>")
            elif "norecord" in self.switches:
                self.msg("Announcing to all connected players ...")
                if not self.args.startswith("{") and not self.args.startswith("|"):
                    self.args = "|g" + self.args
                broadcast(self.args, format_announcement=False)
                return
            elif "startepisode" in self.switches:
                msg = self.rhs
                lhslist = self.lhs.split("/")
                episode_name = lhslist[0]
                synopsis = ""
                if len(lhslist) > 1:
                    synopsis = lhslist[1]
                if not episode_name or not msg:
                    raise CommandError("You must give a name & message for the new episode.")
                create_gemit_and_post(msg, self.caller, episode_name, synopsis)
            else:
                orgs_list = None
                if "orgs" in self.switches:
                    if not self.lhs or not self.rhs:
                        raise CommandError("Specify at least one org and the message.")
                    orgs_list = []
                    msg = self.rhs
                    for arg in self.lhslist:
                        try:
                            org = Organization.objects.get(name__iexact=arg)
                        except Organization.DoesNotExist:
                            raise CommandError("No organization named '%s' was found." % arg)
                        else:
                            orgs_list.append(org)
                else:
                    msg = self.lhs
                create_gemit_and_post(msg, self.caller, orgs_list=orgs_list)
        except CommandError as err:
            self.caller.msg(err)


class CmdWall(ArxCommand):
    """
    @wall

    Usage:
      @wall <message>

    Shouts a message to all connected players.
    This command should be used to send OOC broadcasts,
    while @gemit is used for IC global messages.
    """
    key = "@wall"
    locks = "cmd:perm(wall) or perm(Wizards)"
    help_category = "Admin"

    def func(self):
        """Implements command"""
        if not self.args:
            self.caller.msg("Usage: @wall <message>")
            return
        message = "%s shouts \"%s\"" % (self.caller.name, self.args)
        self.msg("Announcing to all connected players ...")
        SESSIONS.announce_all(message)


class CmdResurrect(ArxCommand):
    """
    @resurrect

    Usage:
        @resurrect <character>

    Resurrects a dead character. It will target either a character
    in your own location, or with an * before the name, it will
    resurrect the primary character of a player of the given name.
    """
    key = "@resurrect"
    locks = "cmd:perm(resurrect) or perm(Wizards)"
    help_category = "GMing"

    def func(self):
        """Implements command"""
        args = self.args
        caller = self.caller
        if not args:
            caller.msg("Rez who?")
            return
        obj = caller.search(args, location=caller.location)
        if args.startswith("*"):
            # We're looking for a player
            args = args[1:]
            obj = caller.player.search(args)
            # found a player, get the character
            if obj:
                obj = obj.db.char_ob
        if not obj or not hasattr(obj, 'resurrect'):
            caller.msg("No character found by that name.")
            return
        obj.resurrect()
        caller.msg("%s resurrected." % obj.key)


class CmdKill(ArxCommand):
    """
    @kill

    Usage:
        @kill <character>

    Kills a character. It will target either a character
    in your own location, or with an * before the name, it will
    resurrect the primary character of a player of the given name.
    """
    key = "@kill"
    locks = "cmd:perm(kill) or perm(Wizards)"
    help_category = "GMing"

    def func(self):
        """Implements command"""
        args = self.args
        caller = self.caller
        if not args:
            caller.msg("Kill who?")
            return
        obj = caller.search(args, location=caller.location)
        if args.startswith("*"):
            # We're looking for a player
            args = args[1:]
            obj = caller.player.search(args)
            # found a player, get the character
            if obj:
                obj = obj.db.char_ob
        if not obj:
            caller.msg("No character found by that name.")
            return
        obj.death_process()
        caller.msg("%s has been murdered." % obj.key)


class CmdForce(ArxCommand):
    """
    @force

    Usage:
      @force <character>=<command>
      @force/char <player>=command

    Forces a given character to execute a command. Without the char switch,
    this will search for character objects in your room, which may be npcs
    that have no player object. With the /char switch, this searches for
    the character of a given player name, who may be anywhere.
    """
    key = "@force"
    locks = "cmd:perm(force) or perm(Builders)"
    help_category = "GMing"

    def func(self):
        """Implements command"""
        caller = self.caller
        if not self.lhs or not self.rhs:
            self.caller.msg("Usage: @force <character>=<command>")
            return
        if "char" in self.switches:
            player = self.caller.player.search(self.lhs)
            if not player:
                return
            char = player.db.char_ob
        else:
            char = caller.search(self.lhs)
        if not char:
            caller.msg("No character found.")
            return
        if not char.access(caller, 'edit'):
            caller.msg("You don't have 'edit' permission for %s." % char)
            return
        char.execute_cmd(self.rhs)
        caller.msg("Forced %s to execute the command '%s'." % (char, self.rhs))
        if char.player_ob:
            inform_staff("%s forced %s to execute the command '%s'." % (caller, char, self.rhs))


class CmdRestore(ArxPlayerCommand):
    """
    @restore

    Usage:
      @restore
      @restore/player <playername>
      @restore <object ID>

    Undeletes an object or player
    """
    key = "@restore"
    locks = "cmd:perm(restore) or perm(Wizards)"
    help_category = "Admin"

    def func(self):
        """Implements command"""
        caller = self.caller
        if not self.args:
            dplayers = [str(ob) for ob in AccountDB.objects.filter(is_active=False) if not ob.is_guest()]
            dobjs = ["%s (ID:%s)" % (ob.key, ob.id) for ob in ObjectDB.objects.filter(
                db_tags__db_key__iexact="deleted")]
            caller.msg("Deleted players: %s" % ", ".join(dplayers))
            caller.msg("Deleted objects: %s" % ", ".join(dobjs))
            return
        if "player" in self.switches:
            try:
                targ = AccountDB.objects.get(username__iexact=self.args)
                targ.undelete()
                caller.msg("%s restored." % targ)
                inform_staff("%s restored player: %s" % (caller, targ))
                return
            except AccountDB.DoesNotExist:
                caller.msg("No player found for %s." % self.args)
                return
        try:
            targ = ObjectDB.objects.get(id=self.args)
            if "deleted" not in str(targ.tags).split(","):
                caller.msg("%s does not appear to be deleted." % targ)
                return
            char = caller.db.char_ob
            inform_staff("%s restored item: %s" % (caller, targ))
            caller.msg("Restored %s." % targ)
            if char:
                targ.move_to(char)
                caller.msg("%s moved to your character object." % targ)
                return
            caller.msg("You do not have a character object to move %s to. Use @tel to return it to the game." % targ)
            return
        except (ObjectDB.DoesNotExist, ValueError):
            caller.msg("No object found for ID %s." % self.args)
            return


class CmdPurgeJunk(ArxPlayerCommand):
    """
    @purgejunk

    Usage:
      @purgejunk
      @purgejunk <object ID>

    Permanently removes a deleted item from the database
    """
    key = "@purgejunk"
    locks = "cmd:perm(restore) or perm(Immortals)"
    help_category = "Admin"

    def func(self):
        """Implements command"""
        caller = self.caller
        if not self.args:
            dplayers = [str(ob) for ob in AccountDB.objects.filter(is_active=False) if not ob.is_guest()]
            dobjs = ["%s (ID:%s)" % (ob.key, ob.id) for ob in ObjectDB.objects.filter(
                db_tags__db_key__iexact="deleted")]
            caller.msg("Deleted players: %s" % ", ".join(dplayers))
            caller.msg("Deleted objects: %s" % ", ".join(dobjs))
            return
        try:
            targ = ObjectDB.objects.get(id=self.args)
            if "deleted" not in str(targ.tags).split(","):
                caller.msg("%s does not appear to be deleted." % targ)
                return
            if (targ.typeclass_path == settings.BASE_CHARACTER_TYPECLASS or
                    targ.typeclass_path == settings.BASE_ROOM_TYPECLASS):
                caller.msg("Rooms or characters cannot be deleted with this command. " +
                           "Must be removed via shell script for safety.")
                return
            targ.delete()
            inform_staff("%s purged item ID %s from the database" % (caller, self.args))
            return
        except ObjectDB.DoesNotExist:
            caller.msg("No object found for ID %s." % self.args)
            return


class CmdSendVision(ArxPlayerCommand):
    """
    @sendvision

    Usage:
        @sendvision
        @sendvision/global <what they see>
        @sendvision <character>
        @sendvision <character>=<What they see>
        @sendclue <character>,<character2, etc>=<clue ID>/<message>

    With no args, list characters who have have the visions tag, or display
    all visions for a given character. Otherwise, send a vision with the
    appropriate text to a given character.
    """
    key = "sendvision"
    aliases = ["sendvisions", "sendclue"]
    locks = "cmd:perm(sendvision) or perm(Wizards)"
    help_category = "GMing"

    def func(self):
        """Implements command"""
        args = self.args
        caller = self.caller
        if not args:
            visionaries = ObjectDB.objects.filter(db_tags__db_key__iexact="visions")
            table = prettytable.PrettyTable(["{wName{n", "{wNumber of Visions{n"])
            for char in visionaries:
                table.add_row([char.key, len(char.messages.visions)])
            caller.msg("{wCharacters who have the 'visions' @tag:{n")
            caller.msg(str(table))
            return
        if "global" in self.switches:
            targlist = AccountDB.objects.filter(roster__roster__name="Active")
            rhs = self.args
        else:
            targlist = [caller.search(arg) for arg in self.lhslist if caller.search(arg)]
            rhs = self.rhs
        if not targlist:
            return
        if "sendclue" in self.cmdstring:
            try:
                rhs = self.rhs.split("/")
                clue = Clue.objects.get(id=rhs[0])
                if len(rhs) > 1:
                    msg = rhs[1]
                else:
                    msg = ""
            except Clue.DoesNotExist:
                self.msg("No clue found by that ID.")
                return
            except (ValueError, TypeError, IndexError):
                self.msg("Must provide a clue and a message.")
                return
            for targ in targlist:
                try:
                    disco = targ.roster.discover_clue(clue)
                    if msg:
                        disco.message = msg
                        disco.save()
                    targ.inform("A new clue has been sent to you. Use @clues to view it.", category="Clue Discovery")
                except AttributeError:
                    continue
            self.msg("Clues sent to: %s" % ", ".join(str(ob) for ob in targlist))
            return
        vision_object = None
        for targ in targlist:
            char = targ.db.char_ob
            if not char:
                caller.msg("No valid character for %s." % targ)
                continue
            visions = char.messages.visions
            if not rhs:
                table = evtable.EvTable("{wVisions{n", width=78)
                for vision in visions:
                    table.add_row(char.messages.disp_entry(vision))
                caller.msg(str(table))
                return
            # use the same vision object for all of them once it's created
            vision_object = char.messages.add_vision(rhs, caller, vision_object)
            msg = "{rYou have experienced a vision!{n\n%s" % rhs
            targ.send_or_queue_msg(msg)
            targ.inform("Your character has experienced a vision. Use @sheet/visions to view it.", category="Vision")
        caller.msg("Vision added to %s: %s" % (", ".join(str(ob) for ob in targlist), rhs))
        return


class CmdAskStaff(ArxPlayerCommand):
    """
    @askstaff

    Usage:
        @askstaff <message>

    Submits a question to staff channels. Unlike +request, there's no
    record of this, so it's just a heads-up to any currently active
    staff who are paying attention. If you want to submit a question
    that will get a response later, use +request.
    """
    key = "@askstaff"

    locks = "cmd:all()"
    help_category = "Admin"

    def func(self):
        """Implements command"""
        args = self.args
        caller = self.caller
        if not args:
            caller.msg("You must ask a question.")
            return
        caller.msg("Asking: %s" % args)
        inform_staff("{c%s {wasking a question:{n %s" % (caller, args))


class CmdListStaff(ArxPlayerCommand):
    """
    +staff

    Usage:
        +staff

    Lists staff that are currently online.
    """
    key = "+staff"

    locks = "cmd:all()"
    help_category = "Admin"

    def func(self):
        """Implements command"""
        caller = self.caller
        staff = AccountDB.objects.filter(db_is_connected=True, is_staff=True)
        table = evtable.EvTable("{wName{n", "{wRole{n", "{wIdle{n", width=78)
        for ob in staff:
            from .overrides import CmdWho
            if ob.tags.get("hidden_staff") or ob.db.hide_from_watch:
                continue
            timestr = CmdWho.get_idlestr(ob.idle_time)
            obname = CmdWho.format_pname(ob)
            table.add_row(obname, ob.db.staff_role or "", timestr)
        caller.msg("{wOnline staff:{n\n%s" % table)


class CmdCcolor(ArxPlayerCommand):
    """
    @ccolor

    Usage:
        @ccolor <channel>=<colorstring>

    Sets a channel you control to have the given color
    """

    key = "@ccolor"
    help_category = "Comms"
    locks = "cmd:perm(Builders)"

    def func(self):
        """Gives channel color string"""
        caller = self.caller

        if not self.lhs or not self.rhs:
            self.msg("Usage: @ccolor <channelname>=<color code>")
            return
        from evennia.commands.default.comms import find_channel
        channel = find_channel(caller, self.lhs)
        if not channel:
            self.msg("Could not find channel %s." % self.args)
            return
        if not channel.access(caller, 'control'):
            self.msg("You are not allowed to do that.")
            return
        channel.db.colorstr = self.rhs
        caller.msg("Channel will now look like this: %s[%s]{n" % (channel.db.colorstr, channel.key))
        return


class CmdAdjustReputation(ArxPlayerCommand):
    """
    @adjustreputation

    Usage:
        @adjustreputation player,player2,...=org,affection,respect
        @adjustreputation/post [<subject>/]<message to post>
        @adjustreputation/finish

    Adjusts a player's affection/respect with a given org.
    """
    key = "@adjustreputation"
    help_category = "GMing"
    locks = "cmd:perm(Wizards)"

    def display_form(self):
        """Displays form for adjusting player reputations"""
        rep_form = self.caller.ndb.reputation_form or [{}, ""]
        post_list = (rep_form[1] or "").split("/")
        if len(post_list) < 2:
            subject = "Reputation Changes"
            post = post_list[0]
        else:
            subject = post_list[0]
            post = post_list[1]

        self.msg("{wReputation Form:{n")
        for player in rep_form[0].keys():
            change_string = ", ".join("%s: Affection: %s Respect: %s" % (
                org, values[0], values[1]) for org, values in rep_form[0][player].items())
            self.msg("{wPlayer{n: %s {wChanges{n: %s" % (player, change_string))
        self.msg("{wSubject{n %s" % subject)
        self.msg("{wPost:{n %s" % post)
        self.msg("Warning - form saved in memory only. Use /finish to avoid losing it in reloads.")

    def do_finish(self):
        """Applies the changes from the finished form"""
        rep_changes, post_msg = self.caller.ndb.reputation_form or [{}, ""]
        if not rep_changes or not post_msg:
            if not rep_changes:
                self.msg("You have not defined any reputation changes yet.")
            if not post_msg:
                self.msg("You have not yet defined a post message.")
            self.display_form()
            return
        # go through each player and apply their reputation changes
        character_list = []
        for player in rep_changes:
            # change_dict is dict of {org: (affection, respect)}
            change_dict = rep_changes[player]
            for org in change_dict:
                affection, respect = change_dict[org]
                player.gain_reputation(org, affection, respect)
                inform_staff("%s has adjusted %s's reputation with %s: %s/%s" % (
                    self.caller, player, org, affection, respect))
            character_list.append(player.player.db.char_ob)
        # post changes
        from typeclasses.bulletin_board.bboard import BBoard
        board = BBoard.objects.get(db_key__iexact="vox populi")
        post_list = post_msg.split("/")
        if len(post_list) < 2:
            subject = "Reputation changes"
        else:
            subject = post_list[0]
            post_msg = post_list[1]
        post = board.bb_post(poster_obj=self.caller, msg=post_msg, subject=subject)
        post.tags.add("reputation_change")
        for character in character_list:
            post.db_receivers_objects.add(character)
        self.caller.ndb.reputation_form = None

    def add_post(self):
        """Adds the planned bulletin board post to the form"""
        rep_form = self.caller.ndb.reputation_form or [{}, ""]
        rep_form[1] = self.args
        self.display_form()

    def add_player(self):
        """Adds a player's rep adjustments to the form"""
        rep_form = self.caller.ndb.reputation_form or [{}, ""]
        try:
            player_list = [self.caller.search(arg) for arg in self.lhslist]
            # remove None results
            player_list = [ob.Dominion for ob in player_list if ob]
            if not player_list:
                return
            org, affection, respect = self.rhslist[0], int(self.rhslist[1]), int(self.rhslist[2])
            org = Organization.objects.get(name__iexact=org)
        except IndexError:
            self.msg("Need a list of players on left side, and org, affection, and respect on right side.")
            return
        except (TypeError, ValueError):
            self.msg("Affection and Respect must be numbers.")
            return
        except Organization.DoesNotExist:
            self.msg("No org found by that name.")
            return
        rep_changes = rep_form[0]
        for player in player_list:
            org_dict = {org: (affection, respect)}
            if player not in rep_changes:
                if affection or respect:
                    rep_changes[player] = org_dict
            else:  # check if we're removing an org
                if not affection and not respect:
                    # if affection and respect are 0, we're choosing to remove it
                    try:
                        del rep_changes[player][org]
                    except KeyError:
                        pass
                else:
                    rep_changes[player].update(org_dict)
        rep_form[0] = rep_changes
        self.caller.ndb.reputation_form = rep_form
        self.display_form()

    def func(self):
        """Executes the reputation adjustment command"""
        if not self.args and not self.switches:
            self.display_form()
            return
        if "finish" in self.switches:
            self.do_finish()
            return
        if "post" in self.switches:
            self.add_post()
            return
        if "cancel" in self.switches:
            self.caller.ndb.reputation_form = None
            self.msg("Cancelled.")
            return
        if not self.switches:
            self.add_player()
            return
        self.msg("Invalid switch.")


class CmdGMDisguise(ArxCommand):
    """
    Disguises an object
        Usage:
            @disguise <object>
            @disguise <object>=<new name>
            @disguise/desc object=<temp desc>
            @disguise/remove <object>
    """
    key = "@disguise"
    help_category = "GMing"
    locks = "cmd:perm(Wizards)"

    def func(self):
        """Executes the GM disguise command"""
        targ = self.caller.search(self.lhs)
        if not targ:
            return
        if not self.switches and not self.rhs:
            self.msg("%s real name is %s" % (targ.name, targ.key))
            return
        if "remove" in self.switches:
            del targ.fakename
            del targ.temp_desc
            self.msg("Removed any disguise for %s." % targ)
            return
        if not self.rhs:
            self.msg("Must provide a new name or desc.")
            return
        if "desc" in self.switches:
            targ.temp_desc = self.rhs
            self.msg("Temporary desc is now:\n%s" % self.rhs)
            return
        targ.fakename = self.rhs
        self.msg("%s will now appear as %s." % (targ.key, targ.name))


class CmdViewLog(ArxPlayerCommand):
    """
    Views a log
        Usage:
            @view_log
            @view_log/previous
            @view_log/current
            @view_log/report <player>
            @view_log/purge

    Views a log of messages sent to you from other players. @view_log with no
    arguments lists the log that will be seen by staff if you've submitted a /report.
    To view the log of recent messages, use /current. For your last session, use
    /previous. /report <player> will go through your logs for messages from the
    player and report it to staff. Using /report again will overwrist your existing
    flagged log. If you do not want to log messages sent by others, then you may
    use @settings/private_mode. GMs cannot read any messages sent to you if that mode
    is enabled, so note that they will be unable to assist you if you report harassment.
    Current logs will not survive through server restarts, though they are saved as
    your previous log after logging out. Messages between two players in the same
    private room are never logged under any circumstances.

    If you wish to wipe all current logs stored on your character, you can use the
    /purge command.
    """
    key = "@view_log"
    help_category = "Admin"
    locks = "cmd:all()"

    def view_log(self, log):
        """Views a log for a player"""
        msg = ""
        for line in log:
            def get_name(ob):
                """Formats their name"""
                if self.caller.check_permstring("builder"):
                    return ob.key
                return ob.name
            msg += "{wFrom: {c%s {wMsg:{n %s\n" % (get_name(line[0]), line[1])
        from server.utils import arx_more
        arx_more.msg(self.caller, msg)

    def view_flagged_log(self, player):
        """Views a logged flag for viewing by a player"""
        self.msg("Viewing %s's flagged log" % player)
        self.view_log(player.flagged_log)

    def view_previous_log(self, player):
        """Views the previous log for a plyaer"""
        self.msg("Viewing %s's previous log" % player)
        self.view_log(player.previous_log)

    def view_current_log(self, player):
        """Views the player's current log"""
        self.msg("Viewing %s's current log" % player)
        self.view_log(player.current_log)

    def func(self):
        """Executes the log command"""
        if "report" in self.switches:
            targ = self.caller.search(self.args)
            if not targ:
                return
            self.caller.report_player(targ)
            self.msg("Flagging that log for review.")
            inform_staff("%s has reported %s for bad behavior. Please use @view_log to check it out." % (
                self.caller, targ))
            return
        if self.caller.check_permstring("immortals"):
            targ = self.caller.search(self.args)
        else:
            targ = self.caller
        if not targ:
            return
        # staff are only permitted to view the flagged log
        if not self.switches or targ != self.caller:
            self.view_flagged_log(targ)
            return
        if "previous" in self.switches:
            self.view_previous_log(targ)
            return
        if "current" in self.switches:
            self.view_current_log(targ)
            return
        if "purge" in self.switches:
            targ.current_log = []
            targ.previous_log = []
            targ.flagged_log = []
            self.msg("All logs for %s cleared." % targ)
            return
        self.msg("Invalid switch.")


class CmdSetLanguages(ArxPlayerCommand):
    """
    @admin_languages

    Usage:
        @admin_languages
        @admin_languages/create <language>
        @admin_languages/add <character>=<language>
        @admin_languages/remove <character>=<language>
        @admin_languages/listfluent <language>

    Views and sets languages. All players are said to speak common.
    """
    key = "@admin_languages"
    help_category = "GMing"
    locks = "cmd:perm(Wizards)"

    @property
    def valid_languages(self):
        """Gets queryset of all current valid languages, which are Tags"""
        return Tag.objects.filter(db_category="languages").order_by('db_key')

    def list_valid_languages(self):
        """Lists all current valid languages"""
        self.msg("Valid languages: %s" % ", ".join(ob.db_key.title() for ob in self.valid_languages))

    def func(self):
        """Executes admin languages command"""
        if not self.args:
            self.list_valid_languages()
            return
        if "create" in self.switches:
            if Tag.objects.filter(db_key__iexact=self.args, db_category="languages"):
                self.msg("Language already exists.")
                return
            tag = Tag.objects.create(db_key=self.args.lower(), db_category="languages", db_model="objectdb")
            self.msg("Created the new language: %s" % tag.db_key)
            return
        if "listfluent" in self.switches:
            from typeclasses.characters import Character
            chars = Character.objects.filter(db_tags__db_key__iexact=self.args,
                                             db_tags__db_category="languages")
            self.msg("Characters who can speak %s: %s" % (self.args, ", ".join(str(ob) for ob in chars)))
            return
        if not self.valid_languages.filter(db_key__iexact=self.rhs):
            self.msg("%s is not a valid language." % self.rhs)
            self.list_valid_languages()
            return
        player = self.caller.search(self.lhs)
        if not player:
            return
        if "add" in self.switches:
            player.db.char_ob.languages.add_language(self.rhs)
            self.msg("Added %s to %s." % (self.rhs, player))
            return
        if "remove" in self.switches:
            player.db.char_ob.languages.remove_language(self.rhs)
            self.msg("Removed %s from %s." % (self.rhs, player))
            return


class CmdGMEvent(ArxCommand):
    """
    Creates an event at your current location

        Usage:
            @gmevent
            @gmevent/create <name>=<description>
            @gmevent/cancel
            @gmevent/start
            @gmevent/stop

    @gmevent allows you to quickly create an RPEvent and log it at
    your current location. You'll be marked as a host and GM, and it
    will log the event at your location until you use @gmevent/stop.

    Once started, you can use @cal commands to do things like change the
    roomdesc and so on with the appropriate switches, if you choose.
    """
    key = "@gmevent"
    locks = "cmd:perm(builders) or tag(story_npc)"
    help_category = "GMing"

    def func(self):
        """Executes gmevent command"""
        form = self.caller.db.gm_event_form
        if not self.switches:
            if not form:
                self.msg("You are not yet creating an event. Use /create to make one.")
                return
            self.msg("You will create an event named '%s' when you use /start." % form[0])
            self.msg("It will have the description: %s" % form[1])
            self.msg("If you wish to change anything, just use /create again. To abort, use /cancel.")
            return
        if "cancel" in self.switches:
            self.caller.attributes.remove("gm_event_form")
            self.msg("Cancelled.")
            return
        if "create" in self.switches:
            if not self.args:
                self.msg("You must provide a name for the Event.")
                return
            if RPEvent.objects.filter(name__iexact=self.args):
                self.msg("That name is already used for an event.")
                return
            self.caller.db.gm_event_form = [self.lhs, self.rhs or ""]
            self.msg("Event name will be: %s, Event Desc: %s" % (self.lhs, self.rhs))
            return
        if "start" in self.switches:
            from datetime import datetime
            if not form or len(form) < 2:
                self.msg("You have not created an event yet. Use /create then /start it.")
                return
            name, desc = form[0], form[1]
            date = datetime.now()
            loc = self.caller.location
            events = self.caller.player_ob.Dominion.events_gmd.filter(finished=False, gm_event=True, location=loc)
            if events:
                self.msg("You are already GMing an event in this room.")
                return
            dompc = self.caller.player_ob.Dominion
            event = RPEvent.objects.create(name=name, date=date, desc=desc, location=loc,
                                           public_event=False, celebration_tier=0, gm_event=True)
            event.add_host(dompc, main_host=True)
            event.add_gm(dompc)
            event_manager = ScriptDB.objects.get(db_key="Event Manager")
            event_manager.start_event(event)
            self.msg("Event started.")
            self.caller.attributes.remove("gm_event_form")
            return
        if "stop" in self.switches:
            from datetime import datetime
            now = datetime.now()
            events = self.caller.player_ob.Dominion.events_gmd.filter(finished=False, gm_event=True, date__lte=now)
            if not events:
                self.msg("You are not currently GMing any events.")
                return
            if len(events) > 1:
                try:
                    event = events.get(location=self.caller.location)
                except RPEvent.DoesNotExist:
                    self.msg("Go to the location where the event is held to stop it.")
                    return
            else:
                event = events[0]
            event_manager = ScriptDB.objects.get(db_key="Event Manager")
            event_manager.finish_event(event)
            self.msg("Event ended.")


class CmdGMNotes(ArxPlayerCommand):
    """
    Adds or views notes about a character

    Usage:
        @gmnotes
        @gmnotes/search <tagtype>
        @gmnotes/tag <character>=<type>
        @gmnotes/rmtag <character>=<type>
        @gmnotes/set <character>=<notes>
        @gmnotes/no_gming
        @gmnotes/search/all
        @gmnotes/deltag <tagtype>
    """
    key = "@gmnotes"
    aliases = ["@gmnote"]
    locks = "cmd: perm(builders)"
    help_category = "GMing"

    @property
    def tags(self):
        """Gets queryset of gmnotes, which are Tags"""
        return Tag.objects.filter(db_category="gmnotes")

    def list_all_tags(self):
        """Displays table of all tags"""
        from evennia.utils.evtable import EvTable
        from evennia.utils.utils import crop
        from server.utils import arx_more
        if not self.args and not self.switches:
            self.msg("|wTypes of Search Tags:|n %s" % ", ".join(set(ob.db_key for ob in self.tags)))
            return
        table = EvTable("{wCharacter{n", "{wType{n", "{wDesc{n", width=78, border="cells")
        chars = Character.objects.filter(db_tags__in=self.tags).distinct()
        if "all" not in self.switches:
            chars = chars.filter(roster__roster__name="Active")
        if self.args:
            chars = chars.filter(db_tags__db_key__icontains=self.args).distinct()
        for character in chars:
            desc = character.db.gm_notes or ""
            desc = crop(desc, width=40)
            table.add_row(character.key, str(character.tags.get(category="gmnotes")), desc)
        arx_more.msg(self.caller, str(table), justify_kwargs=False)

    def list_no_gming(self):
        """Displays list of Characters who haven't had a vision or been on a GM event"""
        from datetime import datetime, timedelta
        date = datetime.now() - timedelta(days=7)
        chars = Character.objects.filter(roster__player__last_login__gte=date, roster__roster__name="Active").exclude(
            receiver_object_set__db_tags__db_key__iexact="visions").exclude(
            roster__player__Dominion__events_attended__gm_event=True).exclude(
            roster__current_account__characters__player__is_staff=True).order_by('db_key')
        msg = "{wCharacters who have never received a vision, nor attended a GM event,"
        msg += " that have logged in the last seven days:{n %s" % ", ".join(ob.key for ob in chars)
        self.msg(msg)

    def view_char(self):
        """Views a character's GM notes"""
        try:
            char = Character.objects.get(db_key__iexact=self.lhs)
        except Character.DoesNotExist:
            self.list_all_tags()
            return
        self.msg("{wNotes for {c%s{n" % char)
        self.msg(char.db.gm_notes)

    def func(self):
        """Executes gmnotes command"""
        if "no_gming" in self.switches:
            self.list_no_gming()
            return
        if "deltag" in self.switches:
            try:
                tag = self.tags.get(db_key__iexact=self.args)
            except (Tag.DoesNotExist, ValueError):
                self.msg("No tag by that name.")
            else:
                affected_characters = tag.objectdb_set.all()
                if affected_characters:
                    self.msg("Characters who have lost that tag: %s" % ", ".join(ob.key for ob in affected_characters))
                tag.delete()
                self.msg("Tag deleted.")
            return
        if not self.args or "search" in self.switches:
            self.list_all_tags()
            return
        if not self.switches and not self.rhs:
            self.view_char()
            return
        player = self.caller.search(self.lhs)
        if not player:
            return
        character = player.db.char_ob
        if "tag" in self.switches:
            character.tags.add(self.rhs, category="gmnotes")
            self.msg("%s tagged with %s" % (character, self.rhs))
            return
        if "rmtag" in self.switches:
            character.tags.remove(self.rhs, category="gmnotes")
            self.msg("Removed %s from %s" % (self.rhs, character))
            return
        if "set" in self.switches:
            old = character.db.gm_notes
            if old:
                self.msg("{wOld gm notes were:{n\n%s" % old)
            character.db.gm_notes = self.rhs
            self.msg("{wNew gm notes are:{n\n%s" % self.rhs)
            return
        self.msg("invalid switch")


class CmdJournalAdminForDummies(ArxPlayerCommand):
    """
    Admins journal stuff

    Usage:
        @admin_journal <character>
        @admin_journal/convert_short_rel_to_long_rel <character>=<type>,<target>
        @admin_journal/black/convert_short_rel_to_long_rel <character>=<type>,<target>
        @admin_journal/cancel
        @admin_journal/delete <character>=<entry #>
        @admin_journal/convert_to_black <character>=<entry #>
        @admin_journal/convert_to_white <character>=<entry #>
        @admin_journal/reveal_black <character>=<entry #>
        @admin_journal/hide_black <character>=<entry #>
    """
    key = "@admin_journal"
    aliases = ["@admin_journals"]
    locks = "cmd: perm(builders)"
    help_category = "Admin"
    black_switches = ("convert_to_white", "reveal_black", "hide_black")
    conversion_switches = black_switches + ('convert_to_black',)

    def journal_index(self, character, j_list):
        """Displays table of journals for character"""
        from server.utils.prettytable import PrettyTable
        num = 1
        table = PrettyTable(["{w#{n", "{wWritten About{n", "{wDate{n", "{wPublic{n"])
        fav_tag = "pid_%s_favorite" % self.caller.id
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
                public = "{wX{n" if entry.is_public else ""
                date = character.messages.get_date_from_header(entry)
                table.add_row([str_num, name, date, public])
                num += 1
            except (AttributeError, RuntimeError, ValueError, TypeError):
                continue
        return str(table)

    def display_white(self, character):
        """Displays white journals for character"""
        self.msg("White journals for %s" % character)
        self.msg(self.journal_index(character, character.messages.white_journal))

    def display_black(self, character):
        """Displays black journals for character"""
        self.msg("Black journals for %s" % character)
        self.msg(self.journal_index(character, character.messages.black_journal))

    def func(self):
        """Executes admin journals command"""
        player = self.caller.search(self.lhs)
        if not player:
            return
        charob = player.db.char_ob
        if not self.switches:
            from commands.commands.roster import display_relationships
            display_relationships(self.caller, charob, show_hidden=True)
            self.display_white(charob)
            self.display_black(charob)
            return
        if "convert_short_rel_to_long_rel" in self.switches:
            rel_type, target = self.rhslist[0], self.rhslist[1]
            target = self.caller.search(target)
            if not target:
                return
            target = target.db.char_ob
            charob.messages.convert_short_rel_to_long_rel(target, rel_type, "black" not in self.switches)
            self.msg("{rDone.{n")
            return
        if "cancel" in self.switches:
            self.caller.ndb.confirm_msg_delete = None
            self.caller.ndb.confirm_msg_convert = None
            self.msg("{rCancelled.{n")
            return
        if "delete" in self.switches:
            if not self.caller.check_permstring("wizards"):
                self.msg("Need Wizard or higher permissions.")
                return
            journals = charob.messages.white_journal if "black" not in self.switches else charob.messages.black_journal
            entry = self.get_entry(journals)
            if not entry:
                return
            if not self.caller.ndb.confirm_msg_delete:
                self.caller.ndb.confirm_msg_delete = entry
                self.msg("{rEntry selected for deletion. To delete, repeat command. Otherwise cancel.")
                self.msg("{rSelected entry:{n %s" % entry.db_message)
                return
            if self.caller.ndb.confirm_msg_delete != entry:
                self.msg("{rEntries did not match.")
                self.msg("{rSelected originally:{n %s" % self.caller.ndb.confirm_msg_delete.db_message)
                self.msg("{rSelected this time:{n %s" % entry.db_message)
                return
            charob.messages.delete_journal(entry)
            oldtext = entry.db_message
            self.msg("{rJournal deleted:{n %s" % oldtext)
            inform_staff("%s deleted %s's journal: %s" % (self.caller, charob, oldtext))
            self.caller.ndb.confirm_msg_delete = None
            return
        if self.check_switches(self.conversion_switches):
            if self.check_switches(self.black_switches):
                journal = charob.messages.black_journal
            else:
                journal = charob.messages.white_journal
            entry = self.get_entry(journal)
            if not entry:
                return
            if not self.confirm_entry_conversion(entry):
                return
            self.msg("{rConverted.{n")
            if "convert_to_black" in self.switches:
                charob.messages.convert_to_black(entry)
                inform_staff("%s moved %s's journal to black:\n%s" % (self.caller, charob, entry.db_message))
            elif "convert_to_white" in self.switches:
                charob.messages.convert_to_white(entry)
                inform_staff("%s moved %s's journal to white:\n%s" % (self.caller, charob, entry.db_message))
            elif "reveal_black" in self.switches:
                entry.reveal_black_journal()
                inform_staff("%s made %s's black journal public:\n%s" % (self.caller, charob, entry.db_message))
            elif "hide_black" in self.switches:
                entry.hide_black_journal()
                inform_staff("%s made %s's black journal private:\n%s" % (self.caller, charob, entry.db_message))
            self.caller.ndb.confirm_msg_convert = None
            return
        self.msg("Invalid switch.")

    def get_entry(self, journal):
        """
        Gets an entry from a journal or sends an error message
        Args:
            journal: the white_journal or black_journal list of a character

        Returns:
            Msg object or None, if something is found
        """
        try:
            return journal[int(self.rhs) - 1]
        except (TypeError, ValueError, IndexError):
            self.msg("You tried to get journal %s, but there are only %s entries." % (self.rhs, len(journal)))

    def confirm_entry_conversion(self, entry):
        """
        Checks for confirmation of modifying a given Msg object
        Args:
            entry (msg): Entry we're checking

        Returns:
            True if the entry has already been confirmed, False otherwise

        """
        if not self.caller.ndb.confirm_msg_convert:
            self.caller.ndb.confirm_msg_convert = entry
            self.msg("{rEntry selected for conversion. To convert, repeat command. Otherwise cancel.")
            self.msg("{rSelected entry:{n %s" % entry.db_message)
            return False
        if self.caller.ndb.confirm_msg_convert != entry:
            self.msg("{rEntries did not match.")
            self.msg("{rSelected originally:{n %s" % self.caller.ndb.confirm_msg_convert.db_message)
            self.msg("{rSelected this time:{n %s" % entry.db_message)
            self.msg("Previous selection cleared. You can select it again, for reals this time, then confirm.")
            self.caller.ndb.confirm_msg_convert = None
            return False
        return True


class CmdTransferKeys(ArxPlayerCommand):
    """
    adds all keys one player has to another

        Usage:
            @transferkeys <source>=<target>
    """
    key = "@transferkeys"
    locks = "cmd: perm(builders)"
    help_category = "Building"

    def func(self):
        """Executes key transfer command"""
        source = self.caller.search(self.lhs)
        targ = self.caller.search(self.rhs)
        if not source or not targ:
            return
        source = source.db.char_ob
        targ = targ.db.char_ob
        s_chest_keys = source.db.chestkeylist or []
        s_chest_keys = list(s_chest_keys)
        t_chest_keys = targ.db.chestkeylist or []
        t_chest_keys = list(t_chest_keys)
        t_chest_keys.extend(s_chest_keys)
        targ.db.chestkeylist = list(set(t_chest_keys))
        s_room_keys = source.db.keylist or []
        s_room_keys = list(s_room_keys)
        t_room_keys = targ.db.keylist or []
        t_room_keys = list(t_room_keys)
        t_room_keys.extend(s_room_keys)
        targ.db.keylist = list(set(t_room_keys))
        self.msg("Keys transferred.")


class CmdAdminKey(ArxCommand):
    """
    Grants a player a key to a container or room

    Usage:
        @admin_key <character>
        @admin_key/add/room <character>=<room>
        @admin_key/add/chest <character>=<chest>
        @admin_key/rm/room <character>=<room>
        @admin_key/rm/chest <character>=<chest>
    """
    key = "@admin_key"
    aliases = ["@admin_keys"]
    locks = "cmd: perm(builders)"
    help_category = "Admin"

    def display_keys(self, pc):
        """Displays keys for pc"""
        chest_keys = pc.db.chestkeylist or []
        room_keys = pc.db.keylist or []
        self.msg("\n{c%s's {wchest keys:{n %s" % (pc, ", ".join(str(ob) for ob in chest_keys)))
        self.msg("\n{c%s's {wroom keys:{n %s" % (pc, ", ".join(str(ob) for ob in room_keys)))

    def func(self):
        """Executes admin_key command"""
        from typeclasses.rooms import ArxRoom
        from typeclasses.characters import Character
        from typeclasses.wearable.wearable import WearableContainer
        from typeclasses.containers.container import Container
        pc = self.caller.search(self.lhs, global_search=True, typeclass=Character)
        if not pc:
            return
        chest_keys = pc.db.chestkeylist or []
        room_keys = pc.db.keylist or []
        if not self.rhs:
            self.display_keys(pc)
            return
        if "room" in self.switches:
            room = self.caller.search(self.rhs, global_search=True, typeclass=ArxRoom)
            if not room:
                return
            if "add" in self.switches:
                if room not in room_keys:
                    room_keys.append(room)
                    pc.db.keylist = room_keys
                self.msg("{yAdded.")
                return
            if room in room_keys:
                room_keys.remove(room)
                pc.db.keylist = room_keys
            self.msg("{rRemoved.")
            return
        if "chest" in self.switches:
            chest = self.caller.search(self.rhs, global_search=True, typeclass=[Container, WearableContainer])
            if not chest:
                return
            if "add" in self.switches:
                if chest not in chest_keys:
                    chest_keys.append(chest)
                    pc.db.chestkeylist = chest_keys
                self.msg("{yAdded.")
                return
            if chest in chest_keys:
                chest_keys.remove(chest)
                pc.db.chestkeylist = chest_keys
            self.msg("{rRemoved.")
            return


class CmdRelocateExit(ArxCommand):
    """
    Moves an exit to a new location

    Usage:
        @relocate_exit <exit>=<new room>

    This moves an exit to a new location. While you could do so
    with @tel, this also makes the reverse exit in the room this
    exit points to now correctly point to the new room.
    """
    key = "@relocate_exit"
    locks = "cmd: perm(builders)"
    help_category = "Building"

    def func(self):
        """Executes relocate exit command"""
        from typeclasses.rooms import ArxRoom
        exit_obj = self.caller.search(self.lhs)
        if not exit_obj:
            return
        new_room = self.caller.search(self.rhs, typeclass=ArxRoom, global_search=True)
        if not new_room:
            return
        exit_obj.relocate(new_room)
        self.msg("Moved %s to %s." % (exit_obj, new_room))


class CmdAdminTitles(ArxPlayerCommand):
    """
    Adds or removes titles from a character

    Usage:
        @admin_titles <character>
        @admin_titles/add <character>=<title>
        @admin_titles/remove <character>=#
    """
    key = "@admin_titles"
    aliases = ["@admin_title"]
    locks = "cmd: perm(builders)"
    help_category = "GMing"

    def display_titles(self, targ):
        """Displays list of titles for targ"""
        titles = targ.db.titles or []
        title_list = ["{w%s){n %s" % (ob[0], ob[1]) for ob in enumerate(titles, start=1)]
        self.msg("%s's titles: %s" % (targ, "; ".join(title_list)))

    def func(self):
        """Executes admin_title command"""
        targ = self.caller.search(self.lhs)
        if not targ:
            return
        targ = targ.db.char_ob
        titles = targ.db.titles or []
        if not self.rhs:
            self.display_titles(targ)
            return
        if "add" in self.switches:
            if self.rhs not in titles:
                titles.append(self.rhs)
                targ.db.titles = titles
            self.display_titles(targ)
            return
        if "remove" in self.switches:
            try:
                titles.pop(int(self.rhs) - 1)
            except (ValueError, TypeError, IndexError):
                self.msg("Must give a number of a current title.")
            else:
                if not titles:
                    targ.attributes.remove("titles")
                else:
                    targ.db.titles = titles
            self.display_titles(targ)


class CmdAdminWrit(ArxPlayerCommand):
    """
    Sets or views a character's writs

    Usage:
        @admin_writ <character>
        @admin_writ/set <character>=<holder>,<value>,<notes>
        @admin_writ/remove <character>=<holder>
    """
    key = "@admin_writ"
    aliases = ["@admin_writs"]
    help_category = "GMing"
    locks = "cmd:perm(builders)"

    def display_writbound(self):
        """Displays writs for all characters"""
        qs = Character.objects.filter(db_tags__db_key="has_writ")
        self.msg("{wCharacters with writs:{n %s" % ", ".join(ob.key for ob in qs))

    def func(self):
        """Executes admin_writ command"""
        if not self.args:
            self.display_writbound()
            return
        targ = self.caller.search(self.lhs)
        if not targ:
            self.display_writbound()
            return
        targ = targ.db.char_ob
        writs = targ.db.writs or {}
        if not self.rhs:
            from evennia.utils.evtable import EvTable
            self.msg("{wWrits of %s{n" % targ)
            table = EvTable("{wMaster{n", "{wValue{n", "{wNotes{n", width=78, border="cells")
            for holder, writ in writs.items():
                table.add_row(holder.capitalize(), writ[0], writ[1])
            table.reformat_column(0, width=15)
            table.reformat_column(1, width=9)
            table.reformat_column(2, width=54)
            self.msg(str(table))
            return
        if "set" in self.switches or "add" in self.switches:
            try:
                holder = self.rhslist[0].lower()
                value = int(self.rhslist[1])
                if len(self.rhslist) > 2:
                    notes = ", ".join(self.rhslist[2:])
                else:
                    notes = ""
            except (IndexError, ValueError, TypeError):
                self.msg("Invalid syntax.")
                return
            writs[holder] = [value, notes]
            targ.db.writs = writs
            targ.tags.add("has_writ")
            self.msg("%s's writ to %s set to a value of %s, notes: %s" % (targ.key, holder, value, notes))
            return
        if "remove" in self.switches:
            holder = self.rhs.lower()
            try:
                del writs[holder]
            except KeyError:
                self.msg("No writ found to %s" % holder)
                return
            if not writs:
                targ.tags.remove("has_writ")
                targ.attributes.remove("writs")
            else:
                targ.db.writs = writs
            self.msg("%s's writ to %s removed." % (targ, holder))
            return
        self.msg("Invalid switch.")


class CmdAdminBreak(ArxPlayerCommand):
    """
    Sets when staff break ends

    Usage:
        @admin_break <date>
        @admin_break/toggle_allow_ocs

    Sets the end date of a break. Players are informed that staff are on break
    as long as the date is in the future. To end the break, set it to be the
    past.
    """
    key = "@admin_break"
    locks = "cmd: perm(builders)"
    help_category = "Admin"

    def func(self):
        """Executes admin_break command"""
        from datetime import datetime
        if "toggle_allow_ocs" in self.switches:
            new_value = not bool(ServerConfig.objects.conf("allow_character_creation_on_break"))
            ServerConfig.objects.conf("allow_character_creation_on_break", new_value)
            self.msg("Allowing character creation during break has been set to %s." % new_value)
            return
        if not self.args:
            self.display_break_date()
            return
        try:
            date = datetime.strptime(self.args, "%m/%d/%y %H:%M")
        except ValueError:
            self.msg("Date did not match 'mm/dd/yy hh:mm' format.")
            self.msg("You entered: %s" % self.args)
        else:
            ServerConfig.objects.conf("end_break_date", date)
            self.msg("Break date updated.")
        finally:
            self.display_break_date()

    def display_break_date(self):
        """Displays the current end date of the break"""
        date = ServerConfig.objects.conf("end_break_date")
        display = date.strftime("%m/%d/%y %H:%M") if date else "No time set"
        self.msg("Current end date is: %s." % display)


class CmdSetServerConfig(ArxPlayerCommand):
    """
    Manages different configuration values

    Usage:
        @setconfig
        @setconfig <key>=<value>
        @setconfig/del <key>

    Sets configuration values for the server, such as a global MOTD,
    income modifier for Dominion, etc.
    """
    key = "setconfig"
    help_category = "Admin"
    locks = "cmd: perm(wizards)"
    shorthand_to_real_keys = {"motd": "MESSAGE_OF_THE_DAY", "income": "GLOBAL_INCOME_MOD"}
    valid_keys = shorthand_to_real_keys.keys()

    def get_help(self, caller, cmdset):
        """Modifies help string"""
        ret = super(CmdSetServerConfig, self).get_help(caller, cmdset)
        ret += "\nValid keys: " + ", ".join(self.valid_keys)
        return ret

    def func(self):
        """Executes cmd"""
        if not self.args:
            return self.list_config_values()
        if "del" in self.switches or "delete" in self.switches:
            ServerConfig.objects.conf(key=self.shorthand_to_real_keys[self.lhs], delete=True)
            return self.list_config_values()
        self.set_server_config_value()

    def validate_income_value(self, value, quiet=False):
        """Validates the global income modifier value"""
        try:
            return float(value)
        except (TypeError, ValueError):
            if not quiet:
                self.msg("Cannot convert to number. Using Default income value.")
            from world.dominion.models import DEFAULT_GLOBAL_INCOME_MOD
            return DEFAULT_GLOBAL_INCOME_MOD

    def list_config_values(self):
        """Prints table of config values"""
        from evennia.utils.evtable import EvTable
        table = EvTable("key", "value", width=78)
        for key in self.valid_keys:
            val = ServerConfig.objects.conf(key=self.shorthand_to_real_keys[key])
            if key == "income":
                val = self.validate_income_value(self.rhs, quiet=True)
            table.add_row(key, val)
        self.msg(str(table))

    def set_server_config_value(self):
        """Sets our configuration values. validates them if necessary"""
        key = self.lhs.lower()
        real_key = self.shorthand_to_real_keys[key]
        if key not in self.valid_keys:
            self.msg("Not a valid key: %s" % ", ".join(self.valid_keys))
            return
        if not self.rhs:
            ServerConfig.objects.conf(key=real_key, delete=True)
        else:
            val = self.rhs
            if key == "income":
                val = self.validate_income_value(self.rhs)
            if key == "motd":
                broadcast("|yServer Message of the Day:|n %s" % val)
            ServerConfig.objects.conf(key=real_key, value=val)
        self.list_config_values()


class CmdAdminPropriety(ArxPlayerCommand):
    """
    Adds or removes propriety mods from several characters

    Usage:
        admin_propriety [<tag>]
        admin_propriety/create <tag name>=<value>
        admin_propriety/add <tag>=<char, org, char2, char3, org2, etc>
        admin_propriety/remove <tag>=<char, org, char2, char3, org2, etc>
    """
    key = "admin_propriety"
    locks = "cmd: perm(builders)"
    help_category = "Admin"

    def func(self):
        """Executes admin_propriety command"""
        try:
            if not self.switches and not self.args:
                return self.list_tags()
            if not self.switches:
                return self.list_tag()
            if "create" in self.switches:
                return self.create_tag()
            if "add" in self.switches or "remove" in self.switches:
                return self.tag_or_untag_owner()
            raise CommandError("Invalid switch.")
        except CommandError as err:
            self.msg(err)

    def list_tags(self):
        """Lists tags with their values"""
        tags = Propriety.objects.values_list('name', 'percentage')
        self.msg("|wPropriety Tags:|n %s" % ", ".join("%s(%s)" % (tag[0], tag[1]) for tag in tags))

    def list_tag(self):
        """Lists characters with a given tag"""
        tag = self.get_tag()
        self.msg("Entities with %s tag: %s" % (tag, ", ".join(str(ob) for ob in tag.owners.all())))

    def get_tag(self):
        """Gets a given propriety tag"""
        try:
            return Propriety.objects.get(name__iexact=self.lhs)
        except Propriety.DoesNotExist:
            raise CommandError("Could not find a propriety tag by that name.")

    def create_tag(self):
        """Creates a new propriety tag"""
        if Propriety.objects.filter(name__iexact=self.lhs).exists():
            raise CommandError("Already a tag by the name %s." % self.lhs)
        try:
            value = int(self.rhs)
        except (ValueError, TypeError):
            raise CommandError("Must provide a value for the tag.")
        Propriety.objects.create(name=self.lhs, percentage=value)
        self.msg("Created tag %s with a percentage modifier of %s." % (self.lhs, value))

    def tag_or_untag_owner(self):
        """Adds or removes propriety tags"""
        tag = self.get_tag()
        query = Q()
        for name in self.rhslist:
            query |= Q(player__player__username__iexact=name) | Q(organization_owner__name__iexact=name)
        owners = list(AssetOwner.objects.filter(query))
        if not owners:
            raise CommandError("No assetowners found by those names.")
        if "add" in self.switches:
            tag.owners.add(*owners)
            self.msg("Added to %s: %s" % (tag, ", ".join(str(ob) for ob in owners)))
        else:
            tag.owners.remove(*owners)
            self.msg("Removed from %s: %s" % (tag, ", ".join(str(ob) for ob in owners)))
