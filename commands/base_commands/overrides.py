"""
General Character commands usually available to all characters
"""
import time

from django.conf import settings

from evennia.server.sessionhandler import SESSIONS
from evennia.commands.default.comms import (CmdCdestroy, CmdChannelCreate, CmdChannels, find_channel,
                                            CmdClock, CmdCBoot, CmdCdesc, CmdAllCom, CmdCWho)
from evennia.commands.default.general import CmdSay
from evennia.comms.models import ChannelDB
from evennia.commands.default.system import CmdReload, CmdScripts
from evennia.commands.cmdhandler import get_and_merge_cmdsets
# noinspection PyProtectedMember
from evennia.commands.default.building import (CmdExamine, CmdLock, CmdDestroy, ObjManipCommand, CmdTag,
                                               CmdSetAttribute, _convert_from_string)
from evennia.commands.default.syscommands import CMD_NOMATCH
from evennia.utils import utils, evtable, create
from evennia.utils.utils import (make_iter, crop, time_format, variable_from_module,
                                 inherits_from, list_to_string)

from server.utils import arx_utils, prettytable
from server.utils.exceptions import CommandError
from commands.base import ArxCommand, ArxPlayerCommand
from world.dominion.models import CraftingMaterials


AT_SEARCH_RESULT = variable_from_module(*settings.SEARCH_AT_RESULT.rsplit('.', 1))
_DEFAULT_WIDTH = settings.CLIENT_DEFAULT_WIDTH


def args_are_currency(args):
    """
    Check if args to a given command match the expression of coins. Must be a number
    followed by 'silver' and/or 'coins', then nothing after.
    """
    units = ("pieces", "coins", "coin", "piece", "silver")
    if not args:
        return False
    if not any(unit for unit in units if unit in args):
        return False
    arglist = args.split()
    if len(arglist) < 2:
        return False
    try:
        float(arglist[0])
    except ValueError:
        return False
    if len(arglist) == 2 and not (arglist[1] == "silver" or arglist[1] in units):
        return False
    if len(arglist) == 3 and (arglist[1] != "silver" or arglist[2] not in units):
        return False
    if len(arglist) > 3:
        return False
    return True


def money_from_args(args, fromobj):
    """
    Checks whether fromobj has enough money for transaction

        Args:
            args (str): String we parse values from
            fromobj (ObjectDB): Object we're getting money from

        Returns:
            vals (tuple): (Value we're trying to get and available money)
    """
    allcoins = ("coins", "coin", "silver", "money", "pieces", "all")
    currency = fromobj.db.currency or 0
    currency = float(currency)
    currency = round(currency, 2)
    if args in allcoins:
        val = currency
    else:
        arglist = args.split()
        val = float(arglist[0])
        val = round(val, 2)
    vals = (val, currency)
    return vals


def check_volume(obj, char, quiet=False):
    """Helper function to check if a character has enough volune to carry an item"""
    vol = obj.db.volume or 1
    v_max = char.db.max_volume or 100
    if char.volume + vol > v_max:
        if not quiet:
            char.msg("You can't carry %s." % obj)
        return False
    return True


class CmdInventory(ArxCommand):
    """
    inventory

    Usage:
      inventory
      inv
      i

    Shows your inventory.
    """
    key = "inventory"
    aliases = ["inv", "i"]
    locks = "cmd:all()"
    perm_for_switches = "Builders"

    def get_help(self, caller, cmdset):
        """Returns custom helpfile"""
        if not caller.check_permstring(self.perm_for_switches):
            return self.__doc__
        help_string = """
        inventory

        Usage :
            inventory
            inv
            inv/view <character>

        Shows character's inventory.
        """
        return help_string

    def func(self):
        """check inventory"""
        show_other = self.caller.check_permstring(self.perm_for_switches) and 'view' in self.switches
        if not show_other:
            basemsg = "You are"
            char = self.caller
            player = char.player
        else:
            player = self.caller.player.search(self.args)
            if not player:
                return
            char = player.char_ob
            if not char:
                self.caller.msg("No character found.")
                return
            basemsg = "%s is" % char.key
        items = char.return_contents(self.caller, detailed=True, show_ids=show_other)
        if not items:
            string = "%s not carrying anything." % basemsg
        else:
            volume = "Volume:{n %s/%s" % (char.volume, char.db.max_volume or 100)
            string = "{w%s carrying (%s{w):%s" % (basemsg, volume, items)
        xp = char.db.xp or 0
        ap = 0
        max_ap = 0
        ap_regen = 0
        try:
            # correct possible synchronization errors
            if char.roster.action_points != char.player_ob.roster.action_points or char.ndb.stale_ap:
                char.roster.refresh_from_db(fields=("action_points",))
                char.player_ob.roster.refresh_from_db(fields=("action_points",))
                char.ndb.stale_ap = False
            ap = char.player_ob.roster.action_points
            ap_regen = char.player_ob.roster.action_point_regen
            max_ap = char.player_ob.roster.max_action_points
        except AttributeError:
            pass
        msg = "\n{w%s currently %s {c%s {wxp and {c%s{w ap.\n" % ("You" if not show_other else char.key,
                                                                  "have" if not show_other else 'has',
                                                                  xp, ap)
        msg += "{wMaximum AP:{n %s  {wWeekly AP Gain:{n %s\n" % (max_ap, ap_regen)
        msg += string
        if hasattr(player, 'Dominion') and hasattr(player.Dominion, 'assets'):
            vault = player.Dominion.assets.vault
            msg += "\n{{wBank Account:{{n {:>11,} silver coins".format(vault)
            assets = player.Dominion.assets
            econ = player.Dominion.assets.economic
            soc = player.Dominion.assets.social
            mil = player.Dominion.assets.military
            msg += "\n{{wPrestige:{{n      {:>10,}  {{wResources         {{wSocial Clout:{{n {}".format(assets.prestige,
                                                                                             char.social_clout)
            msg += "\n{{w||__ Legend:{{n    {:>10,}  {{wEconomic:{{n {:>5,}".format(assets.total_legend, econ)
            msg += "\n{{w||__ Fame:{{n      {:>10,}  {{wMilitary:{{n {:>5,}".format(assets.fame, mil)
            msg += "\n{{w||__ Grandeur:{{n  {:>10,}  {{wSocial:{{n   {:>5,}".format(assets.grandeur, soc)
            msg += "\n{{w||__ Propriety:{{n {:>10,}".format(assets.propriety)
            mats = player.Dominion.assets.materials.filter(amount__gte=1)
            msg += "\n{wMaterials:{n %s" % ", ".join(str(ob) for ob in mats)
        self.msg(msg)


class CmdGet(ArxCommand):
    """
    get

    Usage:
      get <obj or all>
      get <x silver>
      get <obj or all> from <obj>
      get/outfit <outfit name> [from <obj>]

    Picks up an object from your location and puts it in
    your inventory. (See 'help outfit' on outfit creation.)
    """
    key = "get"
    aliases = ["grab", "take"]
    locks = "cmd:all()"

    def func(self):
        """implements the command."""
        try:
            fromobj, loc = self.get_location_from_args()
            oblist, moved = self.get_oblist_from_args(loc)
            for obj in oblist:
                if not check_volume(obj, self.caller):
                    return
                if self.caller == obj:
                    continue
                if self.caller == obj.location:
                    self.caller.msg("You already hold {}.".format(obj))
                    continue
                if not obj.at_before_move(destination=self.caller, caller=self.caller):
                    continue
                moved.append(obj)
                obj.move_to(self.caller, quiet=True)
                # calling hook method
                obj.at_get(self.caller)
            if not moved:
                raise CommandError("You didn't get anything.")
            self.print_success_message(fromobj, moved)
        except CommandError as err:
            self.caller.msg(err)

    def get_location_from_args(self):
        """
        Splits user input if a container is specified.
            Returns:
                container_obj: a container object, or None
                loc: a container object, or caller's location
        """
        if not self.args:
            raise CommandError("What will you {}?".format(self.cmdstring))
        container_obj = None
        argslist = self.args.split(" from ", 1)
        if len(argslist) == 2:
            container_obj = self.caller.search(argslist[1])
            # noinspection PyAttributeOutsideInit
            if not container_obj:
                raise CommandError("Could not get anything.")
            elif not (container_obj.db.container or container_obj.dead):
                raise CommandError("That is not a container.")
            elif container_obj.db.locked and not self.caller.check_permstring("builders"):
                raise CommandError("You'll have to unlock {} first.".format(container_obj))
            self.args = argslist[0]
        loc = container_obj or self.caller.location
        return container_obj, loc

    def get_oblist_from_args(self, loc):
        """
        Records money moved and returns a list of objects to be gotten.
        """
        oblist, moved = [], []
        if self.args == "all":
            oblist = [ob for ob in loc.contents if ob != self.caller]
            val = self.get_money(loc)
            if val:
                moved.append("%d silver" % val)
        elif self.check_switches(("outfit", "outfits")):
            oblist = self.get_oblist_from_outfit(loc)
        elif args_are_currency(self.args):
            val = self.get_money(loc)
            if val:
                moved.append("%d silver" % val)
        else:
            obj = self.caller.search(self.args, location=loc, use_nicks=True, quiet=True)
            if not obj or len(make_iter(obj)) > 1:
                AT_SEARCH_RESULT(obj, self.caller, self.args, False)
            else:
                oblist = make_iter(obj)
        return oblist, moved

    def get_oblist_from_outfit(self, loc):
        """Creates a list of objects or raises FashionError if no outfit found."""
        from world.fashion.exceptions import FashionError
        from world.fashion.fashion_commands import get_caller_outfit_from_args
        try:
            outfit = get_caller_outfit_from_args(self.caller, self.args)
        except FashionError as err:
            raise CommandError(err)
        return [ob for ob in outfit.fashion_items.all() if ob.location == loc]

    def get_money(self, fromobj):
        """Gets silver, which isn't an actual object per se"""
        val, currency = money_from_args(self.args, fromobj)
        if val > currency:
            raise CommandError("Not enough money. You tried to {verb} {val}, but can only {verb} {currency}.".format(
                               verb=self.cmdstring, val=val, currency=currency))
        fromobj.pay_money(val, self.caller)
        return val

    def print_success_message(self, fromobj, moved):
        """Sends caller and location messages."""
        moved_names = list_to_string(moved)
        if fromobj:
            moved_names += " from {}".format(fromobj.name)
        caller_msg = "You {} {}.".format(self.cmdstring, moved_names)
        loc_msg = "{} {}s {}.".format(self.caller.name, self.cmdstring, moved_names)
        self.caller.msg(caller_msg)
        self.caller.location.msg_contents(loc_msg, exclude=self.caller)


class CmdDrop(ArxCommand):
    """
    drop

    Usage:
      drop <obj>

    Lets you drop an object from your inventory into the
    location you are currently in.
    """

    key = "drop"
    aliases = ["put"]
    locks = "cmd:all()"

    def func(self):
        """Implement command"""

        caller = self.caller
        obj = None
        oblist = []
        if not self.args:
            caller.msg("Drop what?")
            return
        if self.args.lower() == "all":
            oblist = [ob for ob in caller.contents if ob not in caller.worn]
            if not oblist:
                caller.msg("You have nothing to drop.")
                return
        if args_are_currency(self.args):
            arglist = self.args.split()
            try:
                val = round(float(arglist[0]), 2)
            except ValueError:
                val = round(float(caller.db.currency or 0), 2)
            currency = round(float(caller.db.currency or 0), 2)
            if val > currency:
                caller.msg("You don't have enough money.")
                return
            caller.pay_money(val, caller.location)
            caller.msg("You drop %s coins." % val)
            caller.location.msg_contents("%s drops coins worth %s silver." % (caller, val), exclude=caller)
            return
        if not obj and not oblist:
            # Because the DROP command by definition looks for items
            # in inventory, call the search function using location = caller
            results = caller.search(self.args, location=caller, quiet=True)

            # now we send it into the error handler (this will output consistent
            # error messages if there are problems).
            obj = AT_SEARCH_RESULT(results, caller, self.args, False,
                                   nofound_string="You don't carry %s." % self.args,
                                   multimatch_string="You carry more than one %s:" % self.args)
            if not obj:
                return
            else:
                oblist = [obj]
        oblist = [ob for ob in oblist if ob.at_before_move(caller.location, caller=caller)]
        if not oblist:
            return
        obnames = ", ".join(ob.name for ob in oblist)
        caller.msg("You drop %s." % obnames)
        caller.location.msg_contents("%s drops %s." % (caller.name, obnames), exclude=caller)
        for obj in oblist:
            obj.move_to(caller.location, quiet=True)
            # Call the object script's at_drop() method.
            obj.at_drop(caller)


class CmdGive(ArxCommand):
    """
    give away things

    Usage:
      give <inventory obj> = <target>
      give <inventory obj> to <target>
      give <amount> silver to <target>
      give/mats <type>,<amount> to <target>
      give/resource <type>,<amount> to <target>

    Gives an items from your inventory to another character,
    placing it in their inventory. give/resource does not require
    you to be in the same room.
    """
    key = "give"
    locks = "cmd:all()"

    # noinspection PyAttributeOutsideInit
    def func(self):
        """Implement give"""

        caller = self.caller
        to_give = None
        if not self.args:
            caller.msg("Usage: give <inventory object> = <target>")
            return
        if not self.rhs:
            arglist = self.args.split(" to ")
            if len(arglist) < 2:
                caller.msg("Usage: give <inventory object> to <target>")
                return
            self.lhs, self.rhs = arglist[0], arglist[1]
        if "resource" in self.switches:
            player = caller.player.search(self.rhs)
            if not player:
                return
            target = player.char_ob
        else:
            target = caller.search(self.rhs)
        if not target:
            return
        if target == caller:
            caller.msg("You cannot give things to yourself.")
            return
        if not target.player_ob:
            self.msg("You cannot give anything to them. Use 'put' instead.")
            return
        if "mats" in self.switches:
            lhslist = self.lhs.split(",")
            try:
                mat = caller.player_ob.Dominion.assets.materials.get(type__name__iexact=lhslist[0])
                amount = int(lhslist[1])
                if amount < 1:
                    raise ValueError
            except (IndexError, ValueError):
                caller.msg("Invalid syntax.")
                return
            except CraftingMaterials.DoesNotExist:
                caller.msg("No materials by that name.")
                return
            if mat.amount < amount:
                caller.msg("Not enough materials.")
                return
            try:
                tmat = target.player_ob.Dominion.assets.materials.get(type=mat.type)
            except CraftingMaterials.DoesNotExist:
                tmat = target.player_ob.Dominion.assets.materials.create(type=mat.type)
            mat.amount -= amount
            tmat.amount += amount
            mat.save()
            tmat.save()
            caller.msg("You give %s %s to %s." % (amount, mat.type, target))
            target.msg("%s gives %s %s to you." % (caller, amount, mat.type))
            return
        if "resource" in self.switches:
            rtypes = ("economic", "social", "military")
            lhslist = self.lhs.split(",")
            try:
                rtype = lhslist[0].lower()
                amount = int(lhslist[1])
                if amount < 1:
                    raise ValueError
            except (IndexError, ValueError):
                caller.msg("Invalid syntax.")
                return
            if rtype not in rtypes:
                caller.msg("Type must be in %s." % ", ".join(rtypes))
                return
            cres = getattr(caller.player_ob.Dominion.assets, rtype)
            if cres < amount:
                caller.msg("You do not have enough %s resources." % rtype)
                return
            tres = getattr(target.player_ob.Dominion.assets, rtype)
            cres -= amount
            tres += amount
            setattr(target.player_ob.Dominion.assets, rtype, tres)
            setattr(caller.player_ob.Dominion.assets, rtype, cres)
            target.player_ob.Dominion.assets.save()
            caller.player_ob.Dominion.assets.save()
            caller.msg("You give %s %s resources to %s." % (amount, rtype, target))
            target.player_ob.inform("%s has given %s %s resources to you." % (caller, amount, rtype),
                                    category="Resources")
            return
        if args_are_currency(self.lhs):
            arglist = self.lhs.split()
            val = round(float(arglist[0]), 2)
            if val <= 0:
                self.msg("Amount must be positive.")
                return
            currency = round(float(caller.db.currency or 0), 2)
            if val > currency:
                caller.msg("You do not have that much money to give.")
                return
            caller.pay_money(val, target)
            caller.msg("You give coins worth %s silver pieces to %s." % (val, target))
            target.msg("%s has given you coins worth %s silver pieces." % (caller, val))
            return
        # if we didn't find a match in currency that we're giving
        if not to_give:
            to_give = caller.search(self.lhs)
        if not (to_give and target):
            return
        if target == caller:
            caller.msg("You keep %s to yourself." % to_give.key)
            to_give.at_get(caller)
            return
        if not to_give.location == caller:
            caller.msg("You are not holding %s." % to_give.key)
            return
        if not check_volume(to_give, target, quiet=True):
            caller.msg("%s can't hold %s." % (target.name, to_give.name))
            return
        if not to_give.at_before_move(target, caller=caller):
            return
        # give object
        to_give.move_to(target, quiet=True)
        caller.msg("You give %s to %s." % (to_give.key, target))
        target.msg("%s gives you %s." % (caller, to_give.key))
        to_give.at_get(target)


class CmdEmit(ArxCommand):
    """
    @emit

    Usage:
      @emit[/switches] [<obj>, <obj>, ... =] <message>
      @remit           [<obj>, <obj>, ... =] <message>
      @pemit           [<obj>, <obj>, ... =] <message>

    Switches:
      room : limit emits to rooms only (default)
      players : limit emits to players only
      contents : send to the contents of matched objects too

    Emits a message to the selected objects or to
    your immediate surroundings. If the object is a room,
    send to its contents. @remit and @pemit are just
    limited forms of @emit, for sending to rooms and
    to players respectively.
    """
    key = "@emit"
    aliases = ["@pemit", "@remit", "\\\\"]
    locks = "cmd:all()"
    help_category = "Social"
    perm_for_switches = "Builders"
    arg_regex = None

    def get_help(self, caller, cmdset):
        """Returns custom help file based on caller"""
        if caller.check_permstring(self.perm_for_switches):
            return self.__doc__
        help_string = """
        @emit

        Usage :
            @emit <message>

        Emits a message to your immediate surroundings. This command is
        used to provide more flexibility than the structure of poses, but
        please remember to indicate your character's name.
        """
        return help_string

    def func(self):
        """Implement the command"""

        caller = self.caller
        if caller.check_permstring(self.perm_for_switches):
            args = self.args
        else:
            args = self.raw.lstrip(" ")

        if not args:
            string = "Usage: "
            string += "\n@emit[/switches] [<obj>, <obj>, ... =] <message>"
            string += "\n@remit           [<obj>, <obj>, ... =] <message>"
            string += "\n@pemit           [<obj>, <obj>, ... =] <message>"
            caller.msg(string)
            return

        rooms_only = 'rooms' in self.switches
        players_only = 'players' in self.switches
        send_to_contents = 'contents' in self.switches
        perm = self.perm_for_switches
        normal_emit = False

        # we check which command was used to force the switches
        if (self.cmdstring == '@remit' or self.cmdstring == '@pemit') and not caller.check_permstring(perm):
            caller.msg("Those options are restricted to GMs only.")
            return
        self.caller.posecount += 1
        if self.cmdstring == '@remit':
            rooms_only = True
            send_to_contents = True
        elif self.cmdstring == '@pemit':
            players_only = True

        if not caller.check_permstring(perm):
            rooms_only = False
            players_only = False

        if not self.rhs or not caller.check_permstring(perm):
            message = args
            normal_emit = True
            objnames = []
            do_global = False
        else:
            do_global = True
            message = self.rhs
            if caller.check_permstring(perm):
                objnames = self.lhslist
            else:
                objnames = [x.key for x in caller.location.contents if x.player]
        if do_global:
            do_global = caller.check_permstring(perm)
        # normal emits by players are just sent to the room
        if normal_emit:
            gms = [ob for ob in caller.location.contents if ob.check_permstring('builders')]
            non_gms = [ob for ob in caller.location.contents if "emit_label" in ob.tags.all() and ob.player]
            gm_msg = "{w[{c%s{w]{n %s" % (caller.name, message)
            caller.location.msg_contents(gm_msg, from_obj=caller, options={'is_pose': True}, gm_msg=True)
            for ob in non_gms:
                ob.msg(gm_msg, from_obj=caller, options={'is_pose': True})
            caller.location.msg_contents(message, exclude=gms + non_gms, from_obj=caller, options={'is_pose': True})
            return
        # send to all objects
        for objname in objnames:
            if players_only:
                obj = caller.player.search(objname)
                if obj:
                    obj = obj.character
            else:
                obj = caller.search(objname, global_search=do_global)
            if not obj:
                caller.msg("Could not find %s." % objname)
                continue
            if rooms_only and obj.location:
                caller.msg("%s is not a room. Ignored." % objname)
                continue
            if players_only and not obj.player:
                caller.msg("%s has no active player. Ignored." % objname)
                continue
            if obj.access(caller, 'tell'):
                if obj.check_permstring(perm):
                    bmessage = "{w[Emit by: {c%s{w]{n %s" % (caller.name, message)
                    obj.msg(bmessage, options={'is_pose': True})
                else:
                    obj.msg(message, options={'is_pose': True})
                if send_to_contents and hasattr(obj, "msg_contents"):
                    obj.msg_contents(message, from_obj=caller, kwargs={'options': {'is_pose': True}})
                    caller.msg("Emitted to %s and contents:\n%s" % (objname, message))
                elif caller.check_permstring(perm):
                    caller.msg("Emitted to %s:\n%s" % (objname, message))
            else:
                caller.msg("You are not allowed to emit to %s." % objname)


class CmdPose(ArxCommand):
    """
    pose - strike a pose

    Usage:
      pose <pose text>
      pose's <pose text>
      pose/history
      pose/history <search term>

    Example:
      pose is standing by the wall, smiling.
       -> others will see:
      Tom is standing by the wall, smiling.

    Describe an action being taken. The pose text will
    automatically begin with your name. Following pose with an apostrophe,
    comma, or colon will not put a space between your name and the character.
    Ex: 'pose, text' is 'Yourname, text'. Similarly, using the ; alias will
    not append a space after your name. Ex: ';'s adverb' is 'Name's adverb'.

    Pose history displays a recent history of poses received from other characters
    after your most recent pose. Once you pose, the history is wiped.
    """
    key = "pose"
    aliases = [":", "emote", ";"]
    locks = "cmd:all()"
    help_category = "Social"
    arg_regex = None

    # noinspection PyAttributeOutsideInit
    def parse(self):
        """
        Custom parse the cases where the emote
        starts with some special letter, such
        as 's, at which we don't want to separate
        the caller's name and the emote with a
        space.
        """
        super(CmdPose, self).parse()
        args = self.args
        if (args and not args[0] in ["'", ",", ":"]) and not self.cmdstring.startswith(";"):
            args = " %s" % args.lstrip(" ")
        self.args = args

    def func(self):
        """Hook function"""
        if "history" in self.switches:
            pose_history = self.caller.ndb.pose_history or []
            if self.args:
                args = self.args.lower().strip()
                pose_history = [ob for ob in pose_history if args in str(ob[0]).lower() or args in str(ob[1]).lower()]
            msg = "\n".join("{c%s{n: %s" % (ob[0], ob[1].lstrip()) for ob in pose_history)
            self.msg("Recent poses received:")
            self.msg(msg)
            return
        if not self.args:
            msg = "What do you want to do?"
            self.caller.msg(msg)
        else:
            self.caller.location.msg_action(self.caller, self.args, options={'is_pose': True})
            self.caller.posecount += 1


class CmdArxSay(CmdSay):
    """Override of CmdSay"""
    __doc__ = CmdSay.__doc__
    arg_regex = None

    # noinspection PyAttributeOutsideInit
    def parse(self):
        """Make sure cmdstring 'say' has a space, other aliases don't"""
        super(CmdArxSay, self).parse()
        if self.cmdstring == "say":
            self.args = " %s" % self.args.lstrip()

    def func(self):
        """Replacement for CmdSay's func"""
        if not self.raw:
            self.msg("Say what?")
            return
        options = {'is_pose': True}
        speech = self.raw.lstrip(" ")
        # calling the speech hook on the location
        speech = self.caller.location.at_say(speech)
        # Feedback for the object doing the talking.
        langstring = ""
        current = self.caller.languages.current_language
        if current and current.lower() != "arvani":
            langstring = " in %s" % current.capitalize()
            options.update({'language': current, 'msg_content': speech})
        self.caller.msg('You say%s, "%s{n"' % (langstring, speech), from_obj=self.caller, options=options)
        # Build the string to emit to neighbors.
        pre_name_emit_string = ' says%s, "%s{n"' % (langstring, speech)
        self.caller.location.msg_action(self.caller, pre_name_emit_string, exclude=[self.caller], options=options)
        self.caller.posecount += 1


# Changed to display room dbref number rather than room name
class CmdWho(ArxPlayerCommand):
    """
    who

    Usage:
      who [<filter>]
      doing [<filter>]
      who/sparse [<filter>]
      doing/sparse [<filter>]
      who/active
      who/watch
      who/org <organization>

    Shows who is currently online. Doing is an alias that limits info
    also for those with all permissions. Players who are currently
    looking for scenes show up with the (LRP) flag, which can be
    toggled with the @settings command. If a filter is supplied, it
    will match names that start with it.
    """

    key = "who"
    aliases = ["doing", "+who"]
    locks = "cmd:all()"

    @staticmethod
    def format_pname(player, lname=False, sparse=False):
        """
        Returns name of player with flags
        """
        base = player.name.capitalize()
        if lname and not sparse:
            char = player.char_ob
            if char:
                base = char.db.longname or base
        if player.db.afk:
            base += " {w(AFK){n"
        if player.db.lookingforrp:
            base += " {w(LRP){n"
        if player.is_staff:
            base += " {c(Staff){n"
        return base

    def check_filters(self, pname, base, fealty=""):
        """
        If we have no filters or the name starts with the
        filter or matches a flag, we return True. Otherwise
        we return False.
        """
        if "org" in self.switches:
            return True
        if not self.args:
            return True
        if self.args.lower() == "afk":
            return "(AFK)" in pname
        if self.args.lower() == "lrp":
            return "(LRP)" in pname
        if self.args.lower() == "staff":
            return "(Staff)" in pname
        if self.args.lower() == fealty.lower():
            return True
        return base.lower().startswith(self.args.lower())

    @staticmethod
    def get_idlestr(idle_time):
        """Returns a string that vaguely says how idle someone is"""
        if idle_time < 1200:
            return "No"
        if idle_time < 3600:
            return "Idle-"
        if idle_time < 86400:
            return "Idle"
        return "Idle+"

    def func(self):
        """
        Get all connected players by polling session.
        """
        player = self.caller
        session_list = [ob for ob in SESSIONS.get_sessions() if ob.account and ob.account.show_online(player)]
        session_list = sorted(session_list, key=lambda o: o.account.key.lower())
        sparse = "sparse" in self.switches
        watch_list = player.db.watching or []
        if self.cmdstring == "doing":
            show_session_data = False
        else:
            show_session_data = player.check_permstring("Immortals") or player.check_permstring("Wizards")
        total_players = len(set(ob.account for ob in session_list))
        number_displayed = 0
        already_counted = []
        public_members = []
        if "org" in self.switches:
            from world.dominion.models import Organization
            try:
                org = Organization.objects.get(name__iexact=self.args)
                if org.secret:
                    raise Organization.DoesNotExist
            except Organization.DoesNotExist:
                self.msg("Organization not found.")
                return
            public_members = [ob.player.player for ob in org.members.filter(deguilded=False, secret=False)]
        if show_session_data:
            table = prettytable.PrettyTable(["{wPlayer Name",
                                             "{wOn for",
                                             "{wIdle",
                                             "{wRoom",
                                             "{wClient",
                                             "{wHost"])
            for session in session_list:
                pc = session.get_account()
                if pc in already_counted:
                    continue
                if not session.logged_in:
                    already_counted.append(pc)
                    continue
                delta_cmd = pc.idle_time
                if "active" in self.switches and delta_cmd > 1200:
                    already_counted.append(pc)
                    continue
                if "org" in self.switches and pc not in public_members:
                    continue
                delta_conn = time.time() - session.conn_time
                plr_pobject = session.get_puppet()
                plr_pobject = plr_pobject or pc
                base = str(session.get_account())
                pname = self.format_pname(session.get_account())
                char = pc.char_ob
                if "watch" in self.switches and char not in watch_list:
                    already_counted.append(pc)
                    continue
                if not char or not char.db.fealty:
                    fealty = "---"
                else:
                    fealty = char.db.fealty
                if not self.check_filters(pname, base, fealty):
                    already_counted.append(pc)
                    continue
                pname = crop(pname, width=18)
                if session.protocol_key == "websocket" or "ajax" in session.protocol_key:
                    client_name = "Webclient"
                else:
                    # Get a sane client name to display.
                    client_name = session.protocol_flags.get('CLIENTNAME')
                    if not client_name:
                        client_name = session.protocol_flags.get('TERM')
                    if client_name and client_name.upper().endswith("-256COLOR"):
                        client_name = client_name[:-9]

                if client_name is None:
                    client_name = "Unknown"

                client_name = client_name.capitalize()

                table.add_row([pname,
                               time_format(delta_conn)[:6],
                               time_format(delta_cmd, 1),
                               hasattr(plr_pobject, "location") and plr_pobject.location and plr_pobject.location.dbref
                               or "None",
                               client_name[:9],
                               isinstance(session.address, tuple) and session.address[0] or session.address])
                already_counted.append(pc)
                number_displayed += 1
        else:
            if not sparse:
                table = prettytable.PrettyTable(["{wPlayer name", "{wFealty", "{wIdle"])
            else:
                table = prettytable.PrettyTable(["{wPlayer name", "{wIdle"])

            for session in session_list:
                pc = session.get_account()
                if pc in already_counted:
                    continue
                if not session.logged_in:
                    already_counted.append(pc)
                    continue
                if "org" in self.switches and pc not in public_members:
                    continue
                delta_cmd = pc.idle_time
                if "active" in self.switches and delta_cmd > 1200:
                    already_counted.append(pc)
                    continue
                if not pc.db.hide_from_watch:
                    base = str(pc)
                    pname = self.format_pname(pc, lname=True, sparse=sparse)
                    char = pc.char_ob
                    if "watch" in self.switches and char not in watch_list:
                        already_counted.append(pc)
                        continue
                    if not char or not char.db.fealty:
                        fealty = "---"
                    else:
                        fealty = char.db.fealty
                    if not self.check_filters(pname, base, fealty):
                        already_counted.append(pc)
                        continue
                    idlestr = self.get_idlestr(delta_cmd)
                    if sparse:
                        width = 30
                    else:
                        width = 55
                    pname = crop(pname, width=width)
                    if not sparse:
                        table.add_row([pname,
                                       fealty,
                                       idlestr])
                    else:
                        table.add_row([pname, idlestr])
                    already_counted.append(pc)
                    number_displayed += 1
                else:
                    already_counted.append(pc)
        is_one = number_displayed == 1
        if number_displayed == total_players:
            string = "{wPlayers:{n\n%s\n%s unique account%s logged in." % (table, "One" if is_one else number_displayed,
                                                                           "" if is_one else "s")
        else:
            string = "{wPlayers:{n\n%s\nShowing %s out of %s unique account%s logged in." % (
                table, "1" if is_one else number_displayed, total_players, "" if total_players == 1 else "s")
        self.msg(string)


class CmdArxSetAttribute(CmdSetAttribute):
    """Override of cmdSetAttribute"""
    __doc__ = CmdSetAttribute.__doc__

    def func(self):
        """Implement the set attribute - a limited form of @py."""

        caller = self.caller
        if not self.args:
            caller.msg("Usage: @set obj/attr = value. Use empty value to clear.")
            return

        # get values prepared by the parser
        value = self.rhs
        objname = self.lhs_objattr[0]['name']
        attrs = self.lhs_objattr[0]['attrs']

        obj = self.search_for_obj(objname)
        if not obj:
            return

        if not self.check_obj(obj):
            return

        result = []
        if "edit" in self.switches:
            # edit in the line editor
            if len(attrs) > 1:
                caller.msg("The Line editor can only be applied "
                           "to one attribute at a time.")
                return
            self.edit_handler(obj, attrs[0])
            return
        if not value:
            if self.rhs is None:
                # no = means we inspect the attribute(s)
                if not attrs:
                    attrs = [attr.key for attr in obj.attributes.all()]
                for attr in attrs:
                    if not self.check_attr(obj, attr):
                        continue
                    result.append(self.view_attr(obj, attr))
                # we view it without parsing markup.
                self.caller.msg("".join(result).strip(), options={"raw": True})
                return
            else:
                # deleting the attribute(s)
                for attr in attrs:
                    if not self.check_attr(obj, attr):
                        continue
                    result.append(self.rm_attr(obj, attr))
        else:
            # setting attribute(s). Make sure to convert to real Python type before saving.
            for attr in attrs:
                if not self.check_attr(obj, attr):
                    continue
                value = _convert_from_string(self, value)
                result.append(self.set_attr(obj, attr, value))
        # send feedback
        msg = "".join(result).strip('\n')
        caller.msg(msg)
        arx_utils.inform_staff("Building command by %s: %s" % (caller, msg))


class CmdDig(ObjManipCommand):
    """
    build new rooms and connect them to the current location
    Usage:
      @dig[/switches] roomname[;alias;alias...][:typeclass]
            [= exit_to_there[;alias][:typeclass]]
               [, exit_to_here[;alias][:typeclass]]
    Switches:
       tel or teleport - move yourself to the new room
    Examples:
       @dig kitchen = north;n, south;s
       @dig house:myrooms.MyHouseTypeclass
       @dig sheer cliff;cliff;sheer = climb up, climb down
    This command is a convenient way to build rooms quickly; it creates the
    new room and you can optionally set up exits back and forth between your
    current room and the new one. You can add as many aliases as you
    like to the name of the room and the exits in question; an example
    would be 'north;no;n'.
    """
    key = "@dig"
    locks = "cmd:perm(dig) or perm(Builders)"
    help_category = "Building"

    def func(self):
        """Do the digging. Inherits variables from ObjManipCommand.parse()"""

        caller = self.caller

        if not self.lhs:
            string = "Usage: @dig[/teleport] roomname[;alias;alias...][:parent] [= exit_there"
            string += "[;alias;alias..][:parent]] "
            string += "[, exit_back_here[;alias;alias..][:parent]]"
            caller.msg(string)
            return

        room = self.lhs_objs[0]

        if not room["name"]:
            caller.msg("You must supply a new room name.")
            return
        location = caller.location

        # Create the new room
        typeclass = room['option']
        if not typeclass:
            typeclass = settings.BASE_ROOM_TYPECLASS

        # create room
        lockstring = "control:id(%s) or perm(Immortals); delete:id(%s) or perm(Wizards); edit:id(%s) or perm(Wizards)"
        lockstring = lockstring % (caller.dbref, caller.dbref, caller.dbref)

        new_room = create.create_object(typeclass, room["name"],
                                        aliases=room["aliases"],
                                        report_to=caller)
        new_room.locks.add(lockstring)
        alias_string = ""
        if new_room.aliases.all():
            alias_string = " (%s)" % ", ".join(new_room.aliases.all())
        room_string = "Created room %s(%s)%s of type %s." % (new_room, new_room.dbref, alias_string, typeclass)

        # create exit to room

        exit_to_string = ""
        exit_back_string = ""

        if self.rhs_objs:
            to_exit = self.rhs_objs[0]
            if not to_exit["name"]:
                exit_to_string = \
                    "\nNo exit created to new room."
            elif not location:
                exit_to_string = \
                  "\nYou cannot create an exit from a None-location."
            else:
                # Build the exit to the new room from the current one
                typeclass = to_exit["option"]
                if not typeclass:
                    typeclass = settings.BASE_EXIT_TYPECLASS

                new_to_exit = create.create_object(typeclass, to_exit["name"],
                                                   location,
                                                   aliases=to_exit["aliases"],
                                                   locks=lockstring,
                                                   destination=new_room,
                                                   report_to=caller)
                alias_string = ""
                if new_to_exit.aliases.all():
                    alias_string = " (%s)" % ", ".join(new_to_exit.aliases.all())
                exit_to_string = "\nCreated Exit from %s to %s: %s(%s)%s."
                exit_to_string = exit_to_string % (location.name,
                                                   new_room.name,
                                                   new_to_exit,
                                                   new_to_exit.dbref,
                                                   alias_string)

        # Create exit back from new room

        if len(self.rhs_objs) > 1:
            # Building the exit back to the current room
            back_exit = self.rhs_objs[1]
            if not back_exit["name"]:
                exit_back_string = \
                    "\nNo back exit created."
            elif not location:
                exit_back_string = \
                   "\nYou cannot create an exit back to a None-location."
            else:
                typeclass = back_exit["option"]
                if not typeclass:
                    typeclass = settings.BASE_EXIT_TYPECLASS
                new_back_exit = create.create_object(typeclass,
                                                     back_exit["name"],
                                                     new_room,
                                                     aliases=back_exit["aliases"],
                                                     locks=lockstring,
                                                     destination=location,
                                                     report_to=caller)
                alias_string = ""
                if new_back_exit.aliases.all():
                    alias_string = " (%s)" % ", ".join(new_back_exit.aliases.all())
                exit_back_string = "\nCreated Exit back from %s to %s: %s(%s)%s."
                exit_back_string = exit_back_string % (new_room.name,
                                                       location.name,
                                                       new_back_exit,
                                                       new_back_exit.dbref,
                                                       alias_string)
        caller.msg("%s%s%s" % (room_string, exit_to_string, exit_back_string))
        if new_room and ('teleport' in self.switches or "tel" in self.switches):
            caller.move_to(new_room)
        # use property to set colored name attribute and strip ansi markup from key
        new_room.name = new_room.name
        return new_room


class CmdTeleport(ArxCommand):
    """
    teleport object to another location

    Usage:
      @tel/switch [<object> =] <target location>
      @go <target player>

    Examples:
      @tel Limbo
      @tel/quiet box Limbo
      @tel/tonone box
      @tel/grab Bob
      @tel/goto Bob
      @go Bob

    Switches:
      quiet  - don't echo leave/arrive messages to the source/target
               locations for the move.
      intoexit - if target is an exit, teleport INTO
                 the exit object instead of to its destination
      tonone - if set, teleport the object to a None-location. If this
               switch is set, <target location> is ignored.
               Note that the only way to retrieve
               an object from a None location is by direct #dbref
               reference.
      grab - if set, summons the character by that player's name to your location
      goto - if set, goes to the location of that player's character

    Teleports an object somewhere. If no object is given, you yourself
    is teleported to the target location. @go is an alias for @tel/goto.     """
    key = "@tel"
    aliases = "@teleport, @go"
    locks = "cmd:perm(teleport) or perm(Builders)"
    help_category = "Building"

    def func(self):
        """Performs the teleport"""

        caller = self.caller
        args = self.args
        lhs, rhs = self.lhs, self.rhs
        switches = self.switches

        # setting switches
        tel_quietly = "quiet" in switches
        to_none = "tonone" in switches
        get_char = "grab" in switches or "goto" in switches or self.cmdstring == "@go"

        if to_none:
            # teleporting to None
            if not args:
                obj_to_teleport = caller
                caller.msg("Teleported to None-location.")
                if caller.location and not tel_quietly:
                    caller.location.msg_contents("%s teleported into nothingness." % caller, exclude=caller)
            else:
                obj_to_teleport = caller.search(lhs, global_search=True)
                if not obj_to_teleport:
                    caller.msg("Did not find object to teleport.")
                    return
                if not obj_to_teleport.access(caller, 'delete'):
                    caller.msg("Access denied.")
                    return
                caller.msg("Teleported %s -> None-location." % obj_to_teleport)
                if obj_to_teleport.location and not tel_quietly:
                    obj_to_teleport.location.msg_contents("%s teleported %s into nothingness."
                                                          % (caller, obj_to_teleport),
                                                          exclude=caller)
            if obj_to_teleport.location:
                obj_to_teleport.location.at_object_leave(obj_to_teleport, None)
                obj_to_teleport.location = None
            if obj_to_teleport != caller and not caller.check_permstring("immortals"):
                string = "%s teleported to None-location." % obj_to_teleport
                arx_utils.inform_staff("Building command by %s: %s" % (caller, string))
            return

        # not teleporting to None location
        if not args and not to_none:
            caller.msg("Usage: teleport[/switches] [<obj> =] <target_loc>|home")
            return

        if rhs:
            obj_to_teleport = caller.search(lhs, global_search=True)
            destination = caller.search(rhs, global_search=True)
        else:
            if not get_char:
                obj_to_teleport = caller
                destination = caller.search(lhs, global_search=True)
            else:
                player = caller.search_account(lhs)
                destination = None
                if 'goto' in switches or self.cmdstring == "@go":
                    obj_to_teleport = caller
                    if player and player.character:
                        destination = player.character.location
                else:
                    obj_to_teleport = player.character
                    destination = caller.location
        if not obj_to_teleport:
            caller.msg("Did not find object to teleport.")
            return

        if not destination:
            caller.msg("Destination not found.")
            return
        if obj_to_teleport == destination:
            caller.msg("You can't teleport an object inside of itself!")
            return
        obj_location = obj_to_teleport.location
        if obj_location and obj_location == destination:
            caller.msg("%s is already at %s." % (obj_to_teleport, destination))
            return
        use_destination = True
        if "intoexit" in self.switches:
            use_destination = False
        # try the teleport
        if obj_location:
            obj_location.at_object_leave(obj_to_teleport, destination)
        if obj_to_teleport.move_to(destination, quiet=tel_quietly,
                                   emit_to_obj=caller,
                                   use_destination=use_destination):
            if obj_to_teleport == caller:
                caller.msg("Teleported to %s." % destination)
            else:
                string = "Teleported %s -> %s." % (obj_to_teleport, destination)
                caller.msg(string)
                arx_utils.inform_staff("Building command by %s: %s" % (caller, string))


newlock = "cmd: perm(Builders)"


class CmdArxCdestroy(CmdCdestroy):
    """Override of Evennia's Channel Destroy command. Different default lock"""
    __doc__ = CmdCdestroy.__doc__
    locks = newlock


class CmdArxChannelCreate(CmdChannelCreate):
    """Override of Evennia's channel create command. Different default lock."""
    __doc__ = CmdChannelCreate.__doc__
    locks = newlock


class CmdArxClock(CmdClock):
    """Override of Evennia's channel create command. Different default lock."""
    __doc__ = CmdClock.__doc__
    locks = newlock


class CmdArxCBoot(CmdCBoot):
    """Override of Evennia's channel boot command. Different default lock."""
    __doc__ = CmdCBoot.__doc__
    locks = newlock


class CmdArxCdesc(CmdCdesc):
    """Override of Evennia's channel desc command. Different default lock."""
    __doc__ = CmdCdesc.__doc__
    locks = newlock


class CmdArxAllCom(CmdAllCom):
    """Override of Evennia's allcom command"""
    __doc__ = CmdAllCom.__doc__

    def func(self):
        """
        Different from CmdAllCom in that we'll do muting rather than deleting subscriptions. Arx added muting in order
        to allow people to suppress a channel while still keeping the channel command, so they could simply do
        <channel command> on to reconnect.
        """
        from evennia.comms.models import ChannelDB
        caller = self.caller
        if self.args not in ("on", "off"):
            return super(CmdArxAllCom, self).func()
        if self.args == "on":
            # get names of all channels available to listen to
            # and activate them all
            channels = [chan for chan in ChannelDB.objects.get_all_channels()
                        if chan.access(caller, 'listen')]
            for channel in channels:
                unmuted = channel.unmute(caller)
                if unmuted:
                    self.msg("You unmute channel %s." % channel)
                else:
                    caller.execute_cmd("addcom %s" % channel.key)
            return
        channels = ChannelDB.objects.get_subscriptions(caller)
        for channel in channels:
            if channel.mute(caller):
                self.msg("You mute channel %s." % channel)


class CmdArxChannels(CmdChannels):
    """
    list all channels available to you

    Usage:
      @channels
      @clist
      comlist

    Lists all channels available to you, whether you listen to them or not.
    Use 'comlist' to only view your current channel subscriptions.
    Use addcom/delcom to join and leave channels
    """
    key = "@channels"
    aliases = ["@clist", "channels", "comlist", "chanlist", "channellist", "all channels"]
    help_category = "Comms"
    locks = "cmd: not pperm(channel_banned)"

    # this is used by the COMMAND_DEFAULT_CLASS parent
    player_caller = True

    def func(self):
        """Implement function"""

        caller = self.caller

        # all channels we have available to listen to
        channels = [chan for chan in ChannelDB.objects.get_all_channels()
                    if chan.access(caller, 'listen')]
        if not channels:
            self.msg("No channels available.")
            return
        # all channel we are already subscribed to
        subs = ChannelDB.objects.get_subscriptions(caller)

        if self.cmdstring == "comlist":
            # just display the subscribed channels with no extra info
            comtable = evtable.EvTable("{wchannel{n", "{wmy aliases{n", "{wdescription{n", align="l",
                                       maxwidth=_DEFAULT_WIDTH, border="cells")
            for chan in subs:
                clower = chan.key.lower()
                nicks = caller.nicks.get(category="channel", return_obj=True)
                comtable.add_row(*["%s%s" % (chan.key, chan.aliases.all() and
                                             "(%s)" % ",".join(chan.aliases.all()) or ""),
                                   "%s" % ",".join(nick.db_key for nick in make_iter(nicks)
                                                   if nick and nick.value[3].lower() == clower),
                                   chan.db.desc])
            self.msg("\n{wChannel subscriptions{n (use {w@channels{n to list all, "
                     "{waddcom{n/{wdelcom{n to sub/unsub):{n\n%s" % comtable)
        else:
            # full listing (of channels caller is able to listen to)
            comtable = evtable.EvTable("{wsub{n", "{wchannel{n", "{wmy aliases{n", "{wdescription{n",
                                       maxwidth=_DEFAULT_WIDTH, border="cells")
            for chan in channels:
                clower = chan.key.lower()
                nicks = caller.nicks.get(category="channel", return_obj=True)
                nicks = nicks or []
                if chan not in subs:
                    substatus = "{rNo{n"
                elif caller in chan.mutelist:
                    substatus = "{rMuted{n"
                else:
                    substatus = "{gYes{n"
                comtable.add_row(*[substatus, "%s%s" % (chan.key, chan.aliases.all() and
                                                        "(%s)" % ",".join(chan.aliases.all()) or ""),
                                   "%s" % ",".join(nick.db_key for nick in make_iter(nicks)
                                                   if nick.value[3].lower() == clower),
                                   chan.db.desc])
            comtable.reformat_column(0, width=9)
            comtable.reformat_column(3, width=14)
            self.msg("\n{wAvailable channels{n (use {wcomlist{n,{waddcom{n and "
                     "{wdelcom{n to manage subscriptions):\n%s" % comtable)


class CmdArxCWho(CmdCWho):
    """Override of Evennia's channel who command to reflect hiding some names based on permissions."""
    __doc__ = CmdCWho.__doc__

    def func(self):
        """implement function"""

        if not self.args:
            string = "Usage: @cwho <channel>"
            self.msg(string)
            return

        channel = find_channel(self.caller, self.lhs)
        if not channel:
            return
        if not channel.access(self.caller, "listen"):
            string = "You can't access this channel."
            self.msg(string)
            return
        string = "\n|CChannel subscriptions|n"
        if self.caller.check_permstring("builders"):
            wholist = channel.complete_wholist
        else:
            wholist = channel.wholist
        string += "\n|w%s:|n\n  %s" % (channel.key, wholist)
        self.msg(string.strip())


class CmdArxLock(CmdLock):
    """Override of Evennia's lock command. Different default lock."""
    __doc__ = CmdLock.__doc__
    aliases = ["@locks", "locks"]


class CmdArxTag(CmdTag):
    """Arx's version of the @tag command"""
    __doc__ = CmdTag.__doc__

    def display_tags(self):
        """Display of tags with some excluded. Staff wants to see only notable ones."""
        from evennia.typeclasses.tags import Tag
        qs = Tag.objects.filter(db_tagtype=None, db_category=None, db_data=None).exclude(
            db_key__icontains="barracks").exclude(db_key__icontains="owned_room").exclude(db_key__icontains="_favorite")
        string = list_to_string([ob.db_key for ob in qs])
        self.msg("Types of tags (excluding custom ones for individuals, or those with categories): %s" % string)

    def func(self):
        """Override of CmdTags to have different display"""
        if not self.args:
            return self.display_tags()
        super(CmdArxTag, self).func()


# noinspection PyAttributeOutsideInit
class CmdArxExamine(CmdExamine):
    """
    get detailed information about an object

    Usage:
      examine [<object>[/attrname]]
      examine [*<player>[/attrname]]
      examine/char <character name>

    Switch:
      player - examine a Player (same as adding *)
      object - examine an Object (useful when OOC)

    The examine command shows detailed game info about an
    object and optionally a specific attribute on it.
    If object is not specified, the current location is examined.

    Append a * before the search string to examine a player.

    """

    def func(self):
        """Process command"""
        caller = self.caller

        def get_cmdset_callback(cmdset):
            """
            We make use of the cmdhandeler.get_and_merge_cmdsets below. This
            is an asynchronous function, returning a Twisted deferred.
            So in order to properly use this we need use this callback;
            it is called with the result of get_and_merge_cmdsets, whenever
            that function finishes. Taking the resulting cmdset, we continue
            to format and output the result.
            """
            string = self.format_output(obj, cmdset)
            self.msg(string.strip())

        if not self.args:
            # If no arguments are provided, examine the invoker's location.
            if hasattr(caller, "location"):
                obj = caller.location
                if not obj.access(caller, 'examine'):
                    # If we don't have special info access, just look at the object instead.
                    self.msg(caller.at_look(obj))
                    return
                # using callback for printing result whenever function returns.
                get_and_merge_cmdsets(obj, self.session, self.player, obj, "object").addCallback(get_cmdset_callback)
            else:
                self.msg("You need to supply a target to examine.")
            return

        # we have given a specific target object
        for objdef in self.lhs_objattr:

            obj = None
            obj_name = objdef['name']
            obj_attrs = objdef['attrs']

            self.player_mode = (inherits_from(caller, "evennia.accounts.accounts.DefaultAccount") or
                                "player" in self.switches or obj_name.startswith('*'))
            if self.player_mode or "char" in self.switches:
                try:
                    obj = caller.search_account(obj_name.lstrip('*'))
                    if "char" in self.switches and obj:
                        obj = obj.char_ob
                except AttributeError:
                    # this means we are calling examine from a player object
                    obj = caller.search(obj_name.lstrip('*'))
            else:
                obj = caller.search(obj_name)
            if not obj:
                continue

            if not obj.access(caller, 'examine'):
                # If we don't have special info access, just look
                # at the object instead.
                self.msg(caller.at_look(obj))
                continue

            if obj_attrs:
                for attrname in obj_attrs:
                    # we are only interested in specific attributes
                    caller.msg(self.format_attributes(obj, attrname, crop=False))
            else:
                if obj.sessions.count():
                    mergemode = "session"
                elif self.player_mode:
                    mergemode = "account"
                else:
                    mergemode = "object"
                # using callback to print results whenever function returns.
                get_and_merge_cmdsets(obj, self.session, self.account, obj, mergemode, self.raw_string
                                      ).addCallback(get_cmdset_callback)


class CmdArxDestroy(CmdDestroy):
    """
        permanently delete objects

        Usage:
           @destroy[/switches] [obj, obj2, obj3, [dbref-dbref], ...]

        switches:
           override - The @destroy command will usually avoid accidentally
                      destroying player objects. This switch overrides this safety.
        examples:
           @destroy house, roof, door, 44-78
           @destroy 5-10, flower, 45

        Destroys one or many objects. If dbrefs are used, a range to delete can be
        given, e.g. 4-10. Also the end points will be deleted.
        """

    key = "@destroy"
    aliases = ["@delete", "@del"]
    locks = "cmd:perm(destroy) or perm(Builders)"
    help_category = "Building"

    def func(self):
        """Implements the command."""

        caller = self.caller

        if not self.args or not self.lhslist:
            caller.msg("Usage: @destroy[/switches] [obj, obj2, obj3, [dbref-dbref],...]")
            return ""

        # noinspection PyUnusedLocal
        def delobj(obj_name, byref=False):
            """helper function for deleting a single object"""
            ret_string = ""
            obj = caller.search(obj_name)
            if not obj:
                self.caller.msg(" (Objects to destroy must either be local or specified with a unique #dbref.)")
                return ""
            obj_name = obj.name
            if not (obj.access(caller, "control") or obj.access(caller, 'delete')):
                return "\nYou don't have permission to delete %s." % obj_name
            if obj.player and 'override' not in self.switches:
                return "\nObject %s is controlled by an active player. Use /override to delete anyway." % obj_name
            if obj.dbid == int(settings.DEFAULT_HOME.lstrip("#")):
                return "\nYou are trying to delete |c%s|n, which is set as DEFAULT_HOME. " \
                       "Re-point settings.DEFAULT_HOME to another " \
                       "object before continuing." % obj_name

            had_exits = hasattr(obj, "exits") and obj.exits
            had_objs = hasattr(obj, "contents") and any(obj for obj in obj.contents
                                                        if not (hasattr(obj, "exits") and obj not in obj.exits))
            # do the deletion
            okay = obj.softdelete()
            # if not okay:
            #     ret_string += "\nERROR: %s not deleted, probably because delete() returned False." % obj_name
            # else:
            #     ret_string += "\n%s was destroyed." % obj_name
            #     if had_exits:
            #         ret_string += " Exits to and from %s were destroyed as well." % obj_name
            #     if had_objs:
            #         ret_string += " Objects inside %s were moved to their homes." % obj_name
            ret_string += "Object has been soft deleted. You can use @restore to bring it back, or @purgejunk to "
            ret_string += "destroy it for good. It will be permanently deleted in 30 days."
            return ret_string

        string = ""
        for objname in self.lhslist:
            if '-' in objname:
                # might be a range of dbrefs
                dmin, dmax = [utils.dbref(part, reqhash=False)
                              for part in objname.split('-', 1)]
                if dmin and dmax:
                    for dbref in range(int(dmin), int(dmax + 1)):
                        string += delobj("#" + str(dbref), True)
                else:
                    string += delobj(objname)
            else:
                string += delobj(objname, True)
        if string:
            caller.msg(string.strip())


class CmdArxReload(CmdReload):
    """Override of @reload to stop us if combat is active"""
    __doc__ = CmdReload.__doc__ + "\n\nUse /override to force a reload when a combat is active."

    # noinspection PyBroadException
    def func(self):
        """Check if we're overriding/forcing it, otherwise reload is stopped if there's a combat."""
        if "override" in self.switches or "force" in self.switches:
            super(CmdArxReload, self).func()
            return
        from typeclasses.scripts.combat.combat_script import CombatManager
        if CombatManager.objects.all():
            self.msg("{rThere is a combat active. You must use @reload/override or @reload/force to do a @reload.{n")
            return
        try:
            super(CmdArxReload, self).func()
        except Exception:
            import traceback
            traceback.print_exc()


class CmdArxScripts(CmdScripts):
    """Override of Scripts"""
    __doc__ = CmdScripts.__doc__

    # noinspection PyProtectedMember
    def list_scripts(self):
        """Takes a list of scripts and formats the output."""
        from evennia.scripts.models import ScriptDB
        from django.db.models import Q
        from evennia.utils.evtable import EvTable
        if self.args and self.args.isdigit():
            scripts = ScriptDB.objects.filter(Q(id=self.args) | Q(db_obj__id=self.args) | Q(db_account__id=self.args))
        else:
            scripts = ScriptDB.objects.filter(Q(db_key__icontains=self.args) | Q(db_obj__db_key__iexact=self.args) |
                                              Q(db_account__username__iexact=self.args))
        if not scripts:
            self.msg("<No scripts>")
            return

        table = EvTable("{wdbref{n", "{wobj{n", "{wkey{n", "{wintval{n", "{wnext{n",
                        "{wtypeclass{n",
                        align='r', border="cells", width=78)
        for script in scripts:
            nextrep = script.time_until_next_repeat()
            if nextrep is None:
                nextrep = "PAUS" if script.db._paused_time else "--"
            else:
                nextrep = "%ss" % nextrep

            def script_obj_str():
                """Prettyprint script key/id"""
                if script.obj:
                    return "%s(#%s)" % (crop(script.obj.key, width=10), script.obj.id)
                return "<Global>"

            table.add_row(script.id,
                          script_obj_str(),
                          script.key,
                          script.interval if script.interval > 0 else "--",
                          nextrep,
                          script.typeclass_path.rsplit('.', 1)[-1])
        self.msg("%s" % table)

    def func(self):
        """Override of CmdScripts"""
        if self.switches:
            super(CmdArxScripts, self).func()
            return
        self.list_scripts()


class SystemNoMatch(ArxCommand):
    """
    No command was found matching the given input.
    """
    key = CMD_NOMATCH
    locks = "cmd:all()"

    def func(self):
        """
        This is given the failed raw string as input.
        """
        from evennia.utils.utils import string_suggestions, list_to_string
        msg = "Command '%s' is not available." % self.raw
        cmdset = self.cmdset
        cmdset.make_unique(self.caller)
        all_cmds = [cmd for cmd in cmdset if cmd.auto_help and cmd.access(self.caller)]
        names = []
        for cmd in all_cmds:
            # noinspection PyProtectedMember
            names.extend(cmd._keyaliases)
        suggestions = string_suggestions(self.raw, set(names), cutoff=0.7)
        if suggestions:
            msg += " Maybe you meant %s?" % list_to_string(suggestions, 'or', addquote=True)
        else:
            msg += " Type \"help\" for help."
        self.msg(msg)
