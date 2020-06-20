"""
General Character commands usually available to all characters
"""
from six import string_types

from django.conf import settings
from evennia.comms.models import TempMsg
from evennia.objects.models import ObjectDB
from evennia.utils import utils, evtable
from evennia.utils.utils import make_iter, variable_from_module

from server.utils import prettytable
from server.utils.arx_utils import raw, list_to_string
from commands.base import ArxCommand, ArxPlayerCommand
from commands.mixins import RewardRPToolUseMixin

AT_SEARCH_RESULT = variable_from_module(*settings.SEARCH_AT_RESULT.rsplit('.', 1))


class CmdBriefMode(ArxCommand):
    """
    brief

    Usage:
      brief

    Toggles whether to display long room descriptions
    when moving through rooms.
    """
    key = "brief"
    locks = "cmd:all()"
    help_category = "Settings"

    def func(self):
        """ Handles the toggle """
        caller = self.caller
        caller.db.briefmode = not caller.db.briefmode
        if not caller.db.briefmode:
            caller.msg("Brief mode is now off.")
        else:
            caller.msg("Brief mode is now on.")


class CmdGameSettings(ArxPlayerCommand):
    """
    @settings toggles different settings.

    Usage:
        @settings
        @settings/brief
        @settings/posebreak
        @settings/stripansinames
        @settings/no_ascii
        @settings/lrp
        @settings/afk [message]
        @settings/nomessengerpreview
        @settings/bbaltread
        @settings/ignore_messenger_notifications
        @settings/ignore_messenger_deliveries
        @settings/ignore_weather
        @settings/ignore_model_emits
        @settings/newline_on_messages
        @settings/private_mode
        @settings/ic_only
        @settings/ignore_bboard_notifications
        @settings/quote_color <color string>
        @settings/name_color <color string>
        @settings/verbose_where
        @settings/emit_label
        @settings/highlight_all_mentions
        @settings/highlight_place

    Switches: /brief suppresses room descs when moving through rooms.
    /posebreak adds a newline between poses from characters.
    /lrp flags your name in the who list as looking for scenes.
    /afk shows you are away from the keyboard with an optional message.
    /nomessengerpreview removes the echo of messengers that you send.
    /bbaltread allows you to read @bb messages on your alts.
    /ignore_messenger_notifications suppresses messenger notifications.
    /ignore_messenger_deliveries will ignore message deliveries to others.
    /ignore_weather will disable weather emits.
    /ignore_model_emits will ignore modeling result emits.
    /private_mode prevents logging any messages that are sent to you.
    /ic_only prevents you from receiving pages.
    /quote_color sets a color for dialogue inside quotations.
        See 'help @color' for usage of color codes.
    /name_color sets a color for occurances of your character's name.
        Currently name_color doesn't revert back to quote_color mid-quote.
    /verbose_where shows any roomtitle information that someone has set
        about their current activities, when using the +where command.
    /emit_label will prefix each emit with its author.
    /highlight_all_mentions enables highlighting for all mentions in channels.
    /highlight_place enables highlighting for place names in poses.
    """
    key = "@settings"
    locks = "cmd:all()"
    help_category = "Settings"
    aliases = ["lrp"]
    valid_switches = ('brief', 'posebreak', 'stripansinames', 'no_ascii', 'lrp', 'verbose_where',
                      'afk', 'nomessengerpreview', 'bbaltread', 'ignore_messenger_notifications',
                      'ignore_messenger_deliveries', 'newline_on_messages', 'private_mode',
                      'ic_only', 'ignore_bboard_notifications', 'quote_color', 'name_color',
                      'emit_label', 'ignore_weather', 'ignore_model_emits', "highlight_all_mentions",
                      'highlight_place', 'place_color')

    def func(self):
        """Executes setting command"""
        caller = self.caller
        char = caller.char_ob
        if not char:
            caller.msg("Settings have no effect without a character object.")
            return
        switches = self.switches
        if self.cmdstring == "lrp":
            switches = ["lrp"]
        if "brief" in switches:
            self.togglesetting(char, "briefmode")
            return
        if "posebreak" in switches:
            self.togglesetting(char, "posebreak")
            return
        if "stripansinames" in switches:
            self.togglesetting(char, "stripansinames")
            return
        if "no_ascii" in switches:
            self.togglesetting(caller, "no_ascii", tag=True)
            return
        if "lrp" in switches:
            self.togglesetting(caller, "lookingforrp")
            return
        if "nomessengerpreview" in switches:
            self.togglesetting(caller, "nomessengerpreview")
            return
        if "bbaltread" in switches:
            self.togglesetting(caller, "bbaltread")
            return
        if "afk" in switches:
            caller.execute_cmd("afk %s" % self.args)
            return
        if "ignore_messenger_notifications" in switches:
            self.togglesetting(caller, "ignore_messenger_notifications")
            return
        if "ignore_messenger_deliveries" in switches:
            self.togglesetting(char, "ignore_messenger_deliveries")
            return
        if "newline_on_messages" in switches:
            self.togglesetting(caller, "newline_on_messages", tag=True)
            return
        if "verbose_where" in switches:
            self.togglesetting(caller, "verbose_where", tag=True)
            return
        if "private_mode" in switches:
            self.togglesetting(caller, "private_mode", tag=True)
            return
        if "ic_only" in switches:
            self.togglesetting(caller, "IC_Only", tag=True)
            return
        if "ignore_bboard_notifications" in switches:
            self.togglesetting(caller, "no_post_notifications", tag=True)
            return
        if "quote_color" in switches:
            self.set_text_colors(char, "pose_quote_color")
            return
        if "name_color" in switches:
            self.set_text_colors(char, "name_color")
            return
        if "emit_label" in switches:
            self.togglesetting(char, "emit_label", tag=True)
            return
        if "ignore_weather" in switches:
            self.togglesetting(caller, "ignore_weather")
            return
        if "ignore_model_emits" in switches:
            self.togglesetting(char, "ignore_model_emits")
            return
        if "highlight_all_mentions" in switches:
            self.togglesetting(caller, "highlight_all_mentions")
            return
        if "highlight_place" in switches:
            self.togglesetting(caller, "highlight_place")
            return
        if "place_color" in switches:
            self.set_text_colors(char, "place_color")
            return
        caller.msg("Invalid switch. Valid switches are: %s" % ", ".join(self.valid_switches))

    def togglesetting(self, char, attr, tag=False):
        """Toggles a setting for the caller"""
        caller = self.caller
        if tag:
            if not char.tags.get(attr):
                self.msg("%s is now on." % attr)
                char.tags.add(attr)
            else:
                self.msg("%s is now off." % attr)
                char.tags.remove(attr)
                char.tags.all()  # update cache until there's a fix for that
            return
        char.attributes.add(attr, not char.attributes.get(attr))
        if not char.attributes.get(attr):
            caller.msg("%s is now off." % attr)
        else:
            caller.msg("%s is now on." % attr)

    def set_text_colors(self, char, attr):
        """Sets either pose_quote_color or name_color for the caller"""
        args = self.args
        if not args:
            char.attributes.remove(attr)
            char.msg('Cleared %s setting.' % attr)
        else:
            if not args.startswith(("|", "{")):
                args = "|%s" % args
            if attr == "pose_quote_color":
                char.db.pose_quote_color = args
                char.msg('Text in quotes will appear %s"like this."|n' % args)
            elif attr == "name_color":
                char.db.name_color = args
                char.msg('Mentions of your name will look like: %s%s|n' % (args, char.key))
            elif attr == "place_color":
                char.db.place_color = args
                char.msg("Place names will look like %sthis|n." % args)


class CmdGlance(ArxCommand):
    """
    glance

    Usage:
        glance <character>
        glance/pcs

    Lets you see some information at a character in the same
    room as you.
    """
    key = "glance"
    locks = "cmd:all()"
    help_category = "Social"

    def send_glance_str(self, char):
        """Sends the string of glancing in the room to the caller"""
        string = "\n{c%s{n\n%s\n%s" % (char.get_fancy_name(),
                                       char.return_extras(self.caller),
                                       char.get_health_appearance())
        self.msg(string)

    def func(self):
        """Executes glance command"""
        caller = self.caller
        if not self.args:
            charlist = [ob for ob in caller.location.contents if ob != caller and hasattr(ob, 'return_extras')]
            if "pcs" in self.switches:
                charlist = [ob for ob in charlist if ob.player]
        else:
            char = caller.search(self.args)
            if not char:
                return
            charlist = [char]
        if not charlist:
            self.msg("No one to glance at.")
            return
        for ob in charlist:
            try:
                self.send_glance_str(ob)
            except AttributeError:
                caller.msg("You cannot glance at that.")
                continue


class CmdShout(RewardRPToolUseMixin, ArxCommand):
    """
    shout

    Usage:
      shout <message>
      shout/loudly <MESSAGE>

    Sends a message to adjacent rooms. Shout sends a message
    to the rooms connected to your current one, while
    shout/loudly sends farther than that. Use with care!
    """
    key = "shout"
    locks = "cmd:all()"
    help_category = "Social"

    def func(self):
        """ Handles the toggle """
        caller = self.caller
        args = self.args
        switches = self.switches
        loudly = False
        if not args:
            caller.msg("Shout what?")
            return
        if switches and "loudly" in switches:
            loudly = True
        loudstr = "loudly " if loudly else ""
        from_dir = "from nearby"
        caller.msg('You shout, "%s"' % args)
        txt = '{c%s{n shouts %s%s, "%s"' % (caller.name, loudstr, from_dir, args)
        caller.location.msg_contents(txt, exclude=caller, options={'shout': True,
                                                                   'from_dir': from_dir})
        self.mark_command_used()


class CmdFollow(ArxCommand):
    """
    follow

    Usage:
        follow

    Starts following the chosen object. Use follow without
    any arguments to stop following. While following a player,
    you can follow them through locked doors they can open.

    To stop someone from following you, use 'ditch'.
    """
    key = "follow"
    locks = "cmd:all()"
    help_category = "Travel"

    def func(self):
        """ Handles followin' """
        caller = self.caller
        args = self.args
        f_targ = caller.ndb.following
        if not args and f_targ:
            caller.stop_follow()
            return
        if not args:
            caller.msg("You are not following anyone.")
            return
        f_targ = caller.search(args)
        if not f_targ:
            caller.msg("No one to follow.")
            return
        caller.follow(f_targ)


class CmdDitch(ArxCommand):
    """
    ditch

    Usage:
        ditch
        ditch <list of followers>

    Shakes off someone following you. Players can follow you through
    any locked door you have access to.
    """
    key = "ditch"
    locks = "cmd:all()"
    aliases = ["lose"]
    help_category = "Travel"

    def func(self):
        """ Handles followin' """
        caller = self.caller
        args = self.args
        followers = caller.ndb.followers
        if not followers:
            caller.msg("No one is following you.")
            return
        if args:
            matches = []
            for arg in self.lhslist:
                obj = ObjectDB.objects.object_search(arg, exact=False, candidates=caller.ndb.followers)
                if obj:
                    matches.append(obj[0])
                else:
                    AT_SEARCH_RESULT(obj, caller, arg)
            for match in matches:
                match.stop_follow()
            return
        # no args, so make everyone stop following
        if followers:
            for follower in followers:
                follower.stop_follow()
        caller.ndb.followers = []
        return


# Note that if extended_room's Extended Look is defined, this is probably not used
class CmdLook(ArxCommand):
    """
    look

    Usage:
      look
      look <obj>
      look *<player>

    Observes your location or objects in your vicinity.
    """
    key = "look"
    aliases = ["l", "ls"]
    locks = "cmd:all()"
    arg_regex = r"\s.*?|$"

    def func(self):
        """
        Handle the looking.
        """
        caller = self.caller
        args = self.args
        if args:
            # Use search to handle duplicate/nonexistent results.
            looking_at_obj = caller.search(args, use_nicks=True)
            if not looking_at_obj:
                return
        else:
            looking_at_obj = caller.location
            if not looking_at_obj:
                caller.msg("You have no location to look at!")
                return

        if not hasattr(looking_at_obj, 'return_appearance'):
            # this is likely due to us having a player instead
            looking_at_obj = looking_at_obj.character
        if not looking_at_obj.access(caller, "view"):
            caller.msg("Could not find '%s'." % args)
            return
        # get object's appearance
        caller.msg(looking_at_obj.return_appearance(caller))
        # the object's at_desc() method.
        looking_at_obj.at_desc(looker=caller)


class CmdWhisper(RewardRPToolUseMixin, ArxCommand):
    """
    whisper - send private IC message

    Usage:
      whisper[/switches] [<player>,<player>,... = <message>]
      whisper =<message> - sends whisper to last person you whispered
      whisper <name> <message>
      whisper/mutter
      whisper/list <number> - Displays list of last <number> of recent whispers

    Switch:
      last - shows who you last messaged
      list - show your last <number> of messages (default)

    Send an IC message to a character in your room. A whisper of the format
    "whisper player=Hello" will send a message in the form of "You whisper
    <player>". A whisper of the format "whisper player=:does an emote" will appear
    in the form of "Discreetly, soandso does an emote" to <player>. It's generally
    expected that for whispers during public roleplay scenes that the players
    involved should pose to the room with some small mention that they're
    communicating discreetly. For ooc messages, please use the 'page'/'tell'
    command instead. If the /mutter switch is used, some of your whisper will
    be overheard by the room. Mutter cannot be used for whisper-poses.

    If no argument is given, you will get a list of your whispers from this
    session.
    """
    key = "whisper"
    aliases = ["mutter"]
    locks = "cmd:not pperm(page_banned)"
    help_category = "Social"
    simplified_key = "mutter"

    def func(self):
        """Implement function using the Msg methods"""

        # this is a MuxCommand, which means caller will be a Character.
        caller = self.caller
        # get the messages we've sent (not to channels)
        if not caller.ndb.whispers_sent:
            caller.ndb.whispers_sent = []
        pages_we_sent = caller.ndb.whispers_sent
        # get last messages we've got
        if not caller.ndb.whispers_received:
            caller.ndb.whispers_received = []
        pages_we_got = caller.ndb.whispers_received

        if 'last' in self.switches:
            if pages_we_sent:
                recv = ",".join(str(obj) for obj in pages_we_sent[-1].receivers)
                self.msg("You last whispered {c%s{n:%s" % (recv, pages_we_sent[-1].message))
                return
            else:
                self.msg("You haven't whispered anyone yet.")
                return

        if not self.args or 'list' in self.switches:
            pages = list(pages_we_sent) + list(pages_we_got)
            pages.sort(key=lambda x: x.date_created)

            number = 5
            if self.args:
                try:
                    number = int(self.args)
                except ValueError:
                    self.msg("Usage: whisper [<player> = msg]")
                    return

            if len(pages) > number:
                lastpages = pages[-number:]
            else:
                lastpages = pages
            template = "{w%s{n {c%s{n whispered to {c%s{n: %s"
            lastpages = "\n ".join(template %
                                   (utils.datetime_format(page.date_created),
                                    ",".join(obj.name for obj in page.senders),
                                    "{n,{c ".join([obj.name for obj in page.receivers]),
                                    page.message) for page in lastpages)

            if lastpages:
                string = "Your latest whispers:\n %s" % lastpages
            else:
                string = "You haven't whispered anyone yet."
            self.msg(string)
            return
        # We are sending. Build a list of targets
        lhs = self.lhs
        rhs = self.rhs
        lhslist = self.lhslist
        if not self.rhs:
            # MMO-type whisper. 'whisper <name> <target>'
            arglist = self.args.lstrip().split(' ', 1)
            if len(arglist) < 2:
                caller.msg("The MMO-style whisper format requires both a name and a message.")
                caller.msg("To send a message to your last whispered character, use {wwhisper =<message>")
                return
            lhs = arglist[0]
            rhs = arglist[1]
            lhslist = set(arglist[0].split(","))

        if not lhs and rhs:
            # If there are no targets, then set the targets
            # to the last person we paged.
            if pages_we_sent:
                receivers = pages_we_sent[-1].receivers
            else:
                self.msg("Who do you want to whisper?")
                return
        else:
            receivers = lhslist

        recobjs = []
        for receiver in set(receivers):

            if isinstance(receiver, string_types):
                pobj = caller.search(receiver, use_nicks=True)
            elif hasattr(receiver, 'character'):
                pobj = receiver.character
            elif hasattr(receiver, 'player'):
                pobj = receiver
            else:
                self.msg("Who do you want to whisper?")
                return
            if pobj:
                if hasattr(pobj, 'has_account') and not pobj.has_account:
                    self.msg("You may only send whispers to online characters.")
                elif not pobj.location or pobj.location != caller.location:
                    self.msg("You may only whisper characters in the same room as you.")
                else:
                    recobjs.append(pobj)
        if not recobjs:
            self.msg("No one found to whisper.")
            return
        header = "{c%s{n whispers," % caller.name
        message = rhs
        mutter_text = ""
        # if message begins with a :, we assume it is a 'whisper-pose'
        if message.startswith(":"):
            message = "%s {c%s{n %s" % ("Discreetly,", caller.name, message.strip(':').strip())
            is_a_whisper_pose = True
        elif message.startswith(";"):
            message = "%s {c%s{n%s" % ("Discreetly,", caller.name, message.lstrip(';').strip())
            is_a_whisper_pose = True
        else:
            is_a_whisper_pose = False
            message = '"' + message + '"'

        # create the temporary message object
        temp_message = TempMsg(senders=caller, receivers=recobjs, message=message)

        caller.ndb.whispers_sent.append(temp_message)

        # tell the players they got a message.
        received = []
        rstrings = []
        for pobj in recobjs:
            otherobs = [ob for ob in recobjs if ob != pobj]
            if not pobj.access(caller, 'tell'):
                rstrings.append("You are not allowed to page %s." % pobj)
                continue
            if is_a_whisper_pose:
                omessage = message
                if otherobs:
                    omessage = "(Also sent to %s.) %s" % (", ".join(ob.name for ob in otherobs), message)
                pobj.msg(omessage, from_obj=caller, options={'is_pose': True})
            else:
                if otherobs:
                    myheader = header + " to {cyou{n and %s," % ", ".join("{c%s{n" % ob.name for ob in otherobs)
                else:
                    myheader = header
                pobj.msg("%s %s" % (myheader, message), from_obj=caller, options={'is_pose': True})
            if not pobj.ndb.whispers_received:
                pobj.ndb.whispers_received = []
            pobj.ndb.whispers_received.append(temp_message)
            if hasattr(pobj, 'has_account') and not pobj.has_account:
                received.append("{C%s{n" % pobj.name)
                rstrings.append("%s is offline. They will see your message if they list their pages later." %
                                received[-1])
            else:
                received.append("{c%s{n" % pobj.name)
                # afk = pobj.player_ob and pobj.player_ob.db.afk
                # if afk:
                #     pobj.msg("{wYou inform {c%s{w that you are AFK:{n %s" % (caller, afk))
                #     rstrings.append("{c%s{n is AFK: %s" % (pobj.name, afk))
        if rstrings:
            self.msg("\n".join(rstrings))
        if received:
            if is_a_whisper_pose:
                self.msg("You posed to %s: %s" % (", ".join(received), message))
            else:
                self.msg("You whispered to %s, %s" % (", ".join(received), message))
                if "mutter" in self.switches or "mutter" in self.cmdstring:
                    from random import randint
                    word_list = rhs.split()
                    chosen = []
                    num_real = 0
                    for word in word_list:
                        if randint(0, 2):
                            chosen.append(word)
                            num_real += 1
                        else:
                            chosen.append("...")
                    if num_real:
                        mutter_text = " ".join(chosen)
                if mutter_text:
                    emit_string = ' mutters, "%s{n"' % mutter_text
                    exclude = [caller] + recobjs
                    caller.location.msg_action(self.caller, emit_string, options={'is_pose': True}, exclude=exclude)
                    self.mark_command_used()
        caller.posecount += 1


class CmdPage(ArxPlayerCommand):
    """
    page - send private message

    Usage:
      page[/switches] [<player>,<player2>,... = <message>]
      page[/switches] [<player> <player2> <player3>...= <message>]
      page [<message to last paged player>]
      tell  <player> <message>
      ttell [<message to last paged player>]
      reply [<message to player who last paged us and other receivers>]
      page/list <number>
      page/noeval
      page/allow <name>
      page/block <name>
      page/reply <message>

    Switch:
      last - shows who you last messaged
      list - show your last <number> of tells/pages (default)

    Send a message to target user (if online), or to the last person
    paged if no player is given. If no argument is given, you will
    get a list of your latest messages. Note that pages are only
    saved for your current session. Sending pages to multiple receivers
    accepts the names either separated by commas or whitespaces.

    /allow toggles whether someone may page you when you use @settings/ic_only.
    /block toggles whether all pages are blocked from someone.
    """

    key = "page"
    aliases = ['tell', 'p', 'pa', 'pag', 'ttell', 'reply']
    locks = "cmd:not pperm(page_banned)"
    help_category = "Comms"
    arg_regex = r'\/|\s|$'

    def disp_allow(self):
        """Displays those we're allowing"""
        self.msg("{wPeople on allow list:{n %s" % ", ".join(str(ob) for ob in self.caller.allow_list))
        self.msg("{wPeople on block list:{n %s" % ", ".join(str(ob) for ob in self.caller.block_list))

    def func(self):
        """Implement function using the Msg methods"""

        # this is a ArxPlayerCommand, which means caller will be a Player.
        caller = self.caller
        if "allow" in self.switches or "block" in self.switches:
            if not self.args:
                self.disp_allow()
                return
            targ = caller.search(self.args)
            if not targ:
                return
            if "allow" in self.switches:
                if targ not in caller.allow_list:
                    caller.allow_list.append(targ)
                    # allowing someone removes them from the block list
                    if targ in caller.block_list:
                        caller.block_list.remove(targ)
                else:
                    caller.allow_list.remove(targ)
            if "block" in self.switches:
                if targ not in caller.block_list:
                    caller.block_list.append(targ)
                    # blocking someone removes them from the allow list
                    if targ in caller.allow_list:
                        caller.allow_list.remove(targ)
                else:
                    caller.block_list.remove(targ)
            self.disp_allow()
            return
        # get the messages we've sent (not to channels)
        if not caller.ndb.pages_sent:
            caller.ndb.pages_sent = []
        pages_we_sent = caller.ndb.pages_sent
        # get last messages we've got
        if not caller.ndb.pages_received:
            caller.ndb.pages_received = []
        pages_we_got = caller.ndb.pages_received

        if 'last' in self.switches:
            if pages_we_sent:
                recv = ",".join(str(obj) for obj in pages_we_sent[-1].receivers)
                self.msg("You last paged {c%s{n:%s" % (recv, pages_we_sent[-1].message))
                return
            else:
                self.msg("You haven't paged anyone yet.")
                return
        if 'list' in self.switches or not self.raw:
            pages = pages_we_sent + pages_we_got
            pages.sort(key=lambda x: x.date_created)

            number = 5
            if self.args:
                try:
                    number = int(self.args)
                except ValueError:
                    self.msg("Usage: tell [<player> = msg]")
                    return

            if len(pages) > number:
                lastpages = pages[-number:]
            else:
                lastpages = pages
            template = "{w%s{n {c%s{n paged to {c%s{n: %s"
            lastpages = "\n ".join(template %
                                   (utils.datetime_format(page.date_created),
                                    ",".join(obj.name for obj in page.senders),
                                    "{n,{c ".join([obj.name for obj in page.receivers]),
                                    page.message) for page in lastpages)

            if lastpages:
                string = "Your latest pages:\n %s" % lastpages
            else:
                string = "You haven't paged anyone yet."
            self.msg(string)
            return
        # if this is a 'tell' rather than a page, we use different syntax
        cmdstr = self.cmdstring.lower()
        lhs = self.lhs
        rhs = self.rhs
        lhslist = self.lhslist
        if cmdstr.startswith('tell'):
            arglist = self.args.lstrip().split(' ', 1)
            if len(arglist) < 2:
                caller.msg("The tell format requires both a name and a message.")
                return
            lhs = arglist[0]
            rhs = arglist[1]
            lhslist = set(arglist[0].split(","))
        # go through our comma separated list, also separate them by spaces
        elif lhs and rhs:
            tarlist = []
            for ob in lhslist:
                for word in ob.split():
                    tarlist.append(word)
            lhslist = tarlist

        # We are sending. Build a list of targets
        if "reply" in self.switches or cmdstr == "reply":
            if not pages_we_got:
                self.msg("You haven't received any pages.")
                return
            last_page = pages_we_got[-1]
            receivers = set(last_page.senders + last_page.receivers)
            receivers.discard(self.caller)
            rhs = self.args
        elif (not lhs and rhs) or (self.args and not rhs) or cmdstr == 'ttell':
            # If there are no targets, then set the targets
            # to the last person we paged.
            # also take format of p <message> for last receiver
            if pages_we_sent:
                receivers = pages_we_sent[-1].receivers
                # if it's a 'tt' command, they can have '=' in a message body
                if not rhs or cmdstr == 'ttell':
                    rhs = self.raw.lstrip()
            else:
                self.msg("Who do you want to page?")
                return
        else:
            receivers = lhslist

        if "noeval" in self.switches:
            rhs = raw(rhs)

        recobjs = []
        for receiver in set(receivers):
            # originally this section had this check, which always was true
            # Not entirely sure what he was trying to check for
            if isinstance(receiver, string_types):
                findpobj = caller.search(receiver)
            else:
                findpobj = receiver
            pobj = None
            if findpobj:
                # Make certain this is a player object, not a character
                if hasattr(findpobj, 'character'):
                    # players should always have is_connected, but just in case
                    if not hasattr(findpobj, 'is_connected'):
                        # only allow online tells
                        self.msg("%s is not online." % findpobj)
                        continue
                    elif findpobj.character:
                        if hasattr(findpobj.character, 'player') and not findpobj.character.player:
                            self.msg("%s is not online." % findpobj)
                        else:
                            pobj = findpobj.character
                    elif not findpobj.character:
                        # player is either OOC or offline. Find out which
                        if hasattr(findpobj, 'is_connected') and findpobj.is_connected:
                            pobj = findpobj
                        else:
                            self.msg("%s is not online." % findpobj)
                else:
                    # Offline players do not have the character attribute
                    self.msg("%s is not online." % findpobj)
                    continue
                if findpobj in caller.block_list:
                    self.msg("%s is in your block list and would not be able to reply to your page." % findpobj)
                    continue
                if caller.tags.get("chat_banned") and (
                                caller not in findpobj.allow_list or findpobj not in caller.allow_list):
                    self.msg("You cannot page if you are not in each other's allow lists.")
                    continue
                if ((findpobj.tags.get("ic_only") or caller in findpobj.block_list or findpobj.tags.get("chat_banned"))
                        and not caller.check_permstring("builders")):
                    if caller not in findpobj.allow_list:
                        self.msg("%s is IC only and cannot be sent pages." % findpobj)
                        continue
            else:
                continue
            if pobj:
                if hasattr(pobj, 'player') and pobj.player:
                    pobj = pobj.player
                recobjs.append(pobj)

        if not recobjs:
            self.msg("No one found to page.")
            return
        if len(recobjs) > 1:
            rec_names = ", ".join("{c%s{n" % str(ob) for ob in recobjs)
        else:
            rec_names = "{cyou{n"
        header = "{wPlayer{n {c%s{n {wpages %s:{n" % (caller, rec_names)
        message = rhs
        pagepose = False
        # if message begins with a :, we assume it is a 'page-pose'
        if message.startswith(":") or message.startswith(";"):
            pagepose = True
            header = "From afar,"
            if len(recobjs) > 1:
                header = "From afar to %s:" % rec_names
            if message.startswith(":"):
                message = "{c%s{n %s" % (caller, message.strip(':').strip())
            else:
                message = "{c%s{n%s" % (caller, message.strip(';').strip())

        # create the temporary message object
        temp_message = TempMsg(senders=caller, receivers=recobjs, message=message)
        caller.ndb.pages_sent.append(temp_message)

        # tell the players they got a message.
        received = []
        r_strings = []
        for pobj in recobjs:
            if not pobj.access(caller, 'msg'):
                r_strings.append("You are not allowed to page %s." % pobj)
                continue
            if "ic_only" in caller.tags.all() and pobj not in caller.allow_list:
                msg = "%s is not in your allow list, and you are IC Only. " % pobj
                msg += "Allow them to send a page, or disable the IC Only @setting."
                self.msg(msg)
                continue
            pobj.msg("%s %s" % (header, message), from_obj=caller, options={'log_msg': True})
            if not pobj.ndb.pages_received:
                pobj.ndb.pages_received = []
            pobj.ndb.pages_received.append(temp_message)
            if hasattr(pobj, 'has_account') and not pobj.has_account:
                received.append("{C%s{n" % pobj.name)
                r_strings.append("%s is offline. They will see your message if they list their pages later." %
                                 received[-1])
            else:
                received.append("{c%s{n" % pobj.name.capitalize())
            afk = pobj.db.afk
            if afk:
                pobj.msg("{wYou inform {c%s{w that you are AFK:{n %s" % (caller, afk))
                r_strings.append("{c%s{n is AFK: %s" % (pobj.name, afk))
        if r_strings:
            self.msg("\n".join(r_strings))
        if received:
            if pagepose:
                self.msg("Long distance to %s: %s" % (", ".join(received), message))
            else:
                self.msg("You paged %s with: '%s'." % (", ".join(received), message))


class CmdOOCSay(ArxCommand):
    """
    ooc

    Usage:
      ooc <message>

    Send an OOC message to your current location. For IC messages,
    use 'say' instead.
    """

    key = "ooc"
    locks = "cmd:all()"
    help_category = "Comms"

    def func(self):
        """Run the OOCsay command"""

        caller = self.caller
        speech = self.raw.lstrip()

        if not speech:
            caller.msg("No message specified. If you wish to stop being IC, use @ooc instead.")
            return

        oocpose = False
        nospace = False
        if speech.startswith(";") or speech.startswith(":"):
            oocpose = True
            if speech.startswith(";"):
                nospace = True
            speech = speech[1:]

        # calling the speech hook on the location
        speech = caller.location.at_say(speech)
        options = {"ooc_note": True, "log_msg": True}

        # Feedback for the object doing the talking.
        if not oocpose:
            caller.msg('{y(OOC){n You say: %s{n' % speech)

            # Build the string to emit to neighbors.
            emit_string = '{y(OOC){n {c%s{n says: %s{n' % (caller.name, speech)
            caller.location.msg_contents(emit_string, from_obj=caller,
                                         exclude=caller, options=options)
        else:
            if nospace:
                emit_string = '{y(OOC){n {c%s{n%s' % (caller.name, speech)
            else:
                emit_string = '{y(OOC){n {c%s{n %s' % (caller.name, speech)
            caller.location.msg_contents(emit_string, exclude=None, options=options, from_obj=caller)


# implement CmdMail. player.db.Mails is List of Mail
# each Mail is tuple of 3 strings - sender, subject, message
class CmdMail(ArxPlayerCommand):
    """
    Send and check player mail

    Usage:
      @mail          - lists all mail in player's mailbox
      @mail #        - read mail by the given number
      @mail/raw # - read mail by given number without ansi evaluation
      @mail/quick [<player>[,<player2,...]/<subject>=<message>
      @mail/org <org name>/<subject>=<message>
      @mail/delete # - deletes mail by given number

    Switches:
      delete - delete mail
      quick  - sends mail

    Examples:
      @mail/quick Tommy/Hello=Let's talk soon
      @mail/delete 5

    Accesses in-game mail. Players may send, receive,
    or delete messages.
    """
    key = "@mail"
    aliases = ["mail", "+mail"]
    locks = "cmd:all()"
    help_category = "Comms"

    def check_valid_receiver(self, pobj):
        """Checks if we can send mail to that player"""
        caller = self.caller
        if pobj in caller.block_list:
            self.msg("%s is in your block list and would not be able to reply to your mail." % pobj)
            return
        if caller.tags.get("chat_banned") and (caller not in pobj.allow_list or pobj not in caller.allow_list):
            self.msg("You cannot mail someone unless you are in each others' allow lists.")
            return
        if ((pobj.tags.get("ic_only") or caller in pobj.block_list or pobj.tags.get("chat_banned"))
                and not caller.check_permstring("builders")):
            if caller not in pobj.allow_list:
                self.msg("%s is IC only and cannot be sent mail." % pobj)
                return
        return True

    def send_mail(self):
        """Sends mail to a player or org"""
        caller = self.caller
        if not self.rhs:
            caller.msg("You cannot mail a message with no body.")
            return
        recobjs = []
        message = self.rhs
        # separate it into receivers, subject. May not have a subject
        if not self.lhs:
            caller.msg("You must have a receiver set.")
            return
        arglist = self.lhs.split("/")
        if len(arglist) < 2:
            subject = "No Subject"
        else:
            subject = arglist[1]
        if "org" in self.switches:
            from world.dominion.models import Organization
            try:
                org = Organization.objects.get(name__iexact=arglist[0])
            except Organization.DoesNotExist:
                self.msg("No org by that name.")
                return
            if org.secret:
                self.msg("Cannot mail secret orgs.")
                return
            # mail all non-secret members
            recobjs = [ob.player.player for ob in org.active_members if not ob.secret]
        else:
            receivers_raw = arglist[0]
            receivers = receivers_raw.split(",")
            for receiver in receivers:
                receiver = receiver.strip()
                pobj = caller.search(receiver, global_search=True)
                # if we got a character instead of player, get their player
                if hasattr(pobj, 'player') and pobj.player:
                    pobj = pobj.player
                # if we found a match
                if pobj:
                    if self.check_valid_receiver(pobj):
                        recobjs.append(pobj)
        self.send_mails(recobjs, message, subject)

    def send_mails(self, recobjs, message, subject):
        """Sends mail to receivers"""
        caller = self.caller
        sender = str(caller)
        if not recobjs:
            caller.msg("No players found.")
            return
        receivers = ", ".join(str(ob) for ob in recobjs)
        for pobj in recobjs:
            pobj.mail(message, subject, sender, receivers)
        caller.msg("Mail successfully sent to %s" % receivers)

    def func(self):
        """Access mail"""

        caller = self.caller
        switches = self.switches

        # mailbox is combined from Player object and his characters
        mails = caller.db.mails or []

        # error message for invalid argument
        nomatch = "You must supply a number matching a mail message."

        if not switches or "raw" in self.switches:
            # if no argument and no switches, list all mail
            caller.tags.remove("new_mail")  # mark mail as read
            if not self.args or not self.lhs:
                table = prettytable.PrettyTable(["{wMail #",
                                                 "{wSender",
                                                 "{wSubject"])
                mail_number = 0
                for mail in mails:
                    # list the mail
                    # mail is a tuple of (sender,subject,message)
                    sender = mail[0]
                    subject = mail[1]
                    mail_number += 1
                    this_number = str(mail_number)
                    if mail not in (caller.db.readmails or set()):
                        col = "{w"
                    else:
                        col = "{n"
                    table.add_row([col + str(this_number), col + str(sender), col + str(subject)])
                string = "{wMailbox:{n\n%s" % table
                caller.msg(string)
                return
            else:
                # get mail number, then display the message
                try:
                    mail_number = int(self.args)
                except ValueError:
                    caller.msg(nomatch)
                    return
                if mail_number < 1 or mail_number > len(mails):
                    caller.msg(nomatch)
                    return
                mail = mails[mail_number - 1]
                sender = mail[0]
                subject = mail[1]
                message = mail[2]
                sentdate = mail[3]
                cclist = mail[4]
                string = "{wMessage:{n %s" % mail_number + "\n"
                string += "{wSent:{n %s" % str(sentdate) + "\n"
                string += "{wTo:{n %s" % cclist + "\n"
                string += "{wSender:{n %s" % sender + "\n"
                string += "{wSubject:{n %s" % subject + "\n"
                string += "{w" + 20 * "-" + "{n\n"
                if "raw" in self.switches:
                    message = raw(message)
                string += message
                string += "\n{w" + 20 * "-" + "{n\n"
                caller.msg(string)
                read_mails = caller.db.readmails or set()
                if mail not in read_mails:
                    read_mails.add(mail)
                    caller.db.readmails = read_mails
                return
        if not self.args or not self.lhs:
            caller.msg("Usage: mail[/switches] # or mail/quick [<name>/<subject>=<message>]")
            return
        if 'delete' in switches or 'del' in self.switches:
            try:
                mail_number = int(self.args)
            except ValueError:
                caller.msg(nomatch)
                return
            if mail_number < 1 or mail_number > len(mails):
                caller.msg(nomatch)
                return
            mail = mails[mail_number - 1]
            caller.db.mails.remove(mail)
            caller.db.readmails.discard(mail)
            caller.msg("Message deleted.")
            return
        if 'quick' in switches or 'org' in switches:
            self.send_mail()
            return


class CmdDirections(ArxCommand):
    """
    @directions

    Usage:
      @directions <room name>
      @directions/off

    Gets directions to a room, or toggles it off. This will attempt to
    find a direct path between you and the room based on your current
    coordinates. If no such path exists, it will tell you the general
    heading. Please use @map to find a direct route otherwise. Your
    destination will be displayed as a red XX on the map.
    """
    key = "@directions"
    help_category = "Travel"
    locks = "cmd:all()"

    def func(self):
        """ Handles the toggle """
        caller = self.caller
        if "off" in self.switches or not self.args:
            if caller.ndb.waypoint:
                caller.ndb.waypoint = None
                caller.msg("Directions turned off.")
            else:
                caller.msg("You must give the name of a room.")
            return
        from typeclasses.rooms import ArxRoom
        room = ArxRoom.objects.filter(db_key__icontains=self.args).exclude(db_tags__db_key="unmappable")[:10]
        if len(room) > 1:
            exact = [ob for ob in room if self.args in ob.aliases.all()]
            if len(exact) == 1:
                room = exact[0]
            else:
                caller.msg("Multiple matches: %s" % ", ".join(str(ob) for ob in room))
                room = room[0]
                caller.msg("Showing directions to %s." % room)
        elif len(room) == 1:
            room = room[0]
        if not room:
            caller.msg("No matches for %s." % self.args)
            return
        caller.msg("Attempting to find where your destination is in relation to your position." +
                   " Please use {w@map{n if the directions don't have a direct exit there.")
        directions = caller.get_directions(room)
        if not directions:
            caller.msg("You can't figure out how to get there from here. "
                       "You may have to go someplace closer, like the City Center.")
            caller.ndb.waypoint = None
            return
        caller.msg("Your destination is through the %s." % directions)
        caller.ndb.waypoint = room
        return


class CmdPut(ArxCommand):
    """
    Puts an object inside a container
    Usage:
        put <object or all or x silver> in <object>
        put/outfit <outfit name> in <object>

    Places an object you hold inside an unlocked
    container. (See 'help outfit' for outfit creation.)
    """
    key = "put"
    locks = "cmd:all()"

    def func(self):
        """Executes Put command"""
        from .overrides import args_are_currency
        caller = self.caller

        args = self.args.split(" in ", 1)
        if len(args) != 2:
            caller.msg("Usage: put <name> in <name>")
            return
        dest = caller.search(args[1], use_nicks=True, quiet=True)
        if not dest:
            return AT_SEARCH_RESULT(dest, caller, args[1])
        dest = make_iter(dest)[0]
        if args_are_currency(args[0]):
            self.put_money(args[0], dest)
            return
        if self.check_switches(("outfit", "outfits")):
            from world.fashion.exceptions import FashionError
            try:
                obj_list = self.get_oblist_from_outfit(args[0])
            except FashionError as err:
                return caller.msg(err)
        elif args[0] == "all":
            obj_list = caller.contents
        else:
            obj = caller.search(args[0], location=caller)
            if not obj:
                return
            obj_list = [obj]
        obj_list = [ob for ob in obj_list if ob.at_before_move(dest, caller=caller)]
        success = []
        for obj in obj_list:
            if obj == dest:
                caller.msg("You can't put an object inside itself.")
                continue
            if not dest.db.container:
                caller.msg("That is not a container.")
                return
            if dest.db.locked and not self.caller.check_permstring("builders"):
                caller.msg("You'll have to unlock {} first.".format(dest.name))
                return
            if dest in obj.contents:
                caller.msg("You can't place an object in something it contains.")
                continue
            max_volume = dest.db.max_volume or 0
            volume = obj.db.volume or 0
            if dest.volume + volume > max_volume:
                caller.msg("No more room; {} won't fit.".format(obj))
                continue
            if not obj.access(caller, 'get'):
                caller.msg("You cannot move {}.".format(obj))
                continue
            obj.move_to(dest)
            success.append(obj)
            from time import time
            obj.db.put_time = time()
        if success:
            success_str = "%s in %s" % (list_to_string(success), dest.name)
            caller.msg("You put %s." % success_str)
            caller.location.msg_contents("%s puts %s." % (caller.name, success_str), exclude=caller)
        else:
            self.msg("Nothing moved.")

    def put_money(self, args, destination):
        """
        Puts silver in a destination object.

            Args:
                args(str): String we'll get values from
                destination (ObjectDB): What we're putting money in
        """
        from .overrides import money_from_args
        val, currency = money_from_args(args, self.caller)
        if val > currency:
            self.msg("You do not have enough money.")
            return
        self.caller.pay_money(val, destination)
        self.msg("You put %s silver in %s." % (val, destination))

    def get_oblist_from_outfit(self, args):
        """Creates a list of objects or raises FashionError if no outfit found."""
        from world.fashion.fashion_commands import get_caller_outfit_from_args
        outfit = get_caller_outfit_from_args(self.caller, args)
        obj_list = [ob for ob in outfit.fashion_items.all() if ob.location == self.caller]
        return obj_list


class CmdGradient(ArxPlayerCommand):
    """
    @gradient - displays a string formatted with color codes
    Usage:
        @gradient <xxx>,<xxx>=<string to format>
        @gradient/reverse <xxx>,<xxx>=<string to format>

    @gradient takes two color code values and a string, then outputs the
    string with it changing colors through that range. If the reverse
    switch is specified, it will reverse colors halfway through the string.
    See @color xterm256 for a list of codes.
    """
    key = "@gradient"
    locks = "cmd: all()"

    @staticmethod
    def get_step(length, diff):
        """Gets step of the gradient"""
        if diff == 0:
            return 0
        return length/diff

    def color_string(self, start, end, text):
        """Returns a colored string for the gradient"""
        current = start
        output = ""
        for x in range(len(text)):
            r, g, b = current[0], current[1], current[2]
            if x == 0:
                tag = "{{%s%s%s" % (str(r), str(g), str(b))
                output += "%s%s" % (tag, text[x])
                continue
            diff = (end[0]-current[0], end[1]-current[1], end[2]-current[2])
            previous = current
            step = (self.get_step(len(text), diff[0]), self.get_step(len(text), diff[1]), self.get_step(len(text),
                                                                                                        diff[2]))
            if step[0] and x % step[0] == 0:
                if diff[0] > 1:
                    r += 1
                elif diff[0] < 1:
                    r -= 1
            if step[1] and x % step[1] == 0:
                if diff[1] > 1:
                    g += 1
                elif diff[1] < 1:
                    g -= 1
            if step[2] and x % step[2] == 0:
                if diff[2] > 1:
                    b += 1
                elif diff[2] < 1:
                    b -= 1
            current = (r, g, b)
            if current != previous:
                # we add a tag
                tag = "{{%s%s%s" % (str(r), str(g), str(b))
                output += "%s%s" % (tag, text[x])
            else:
                output += text[x]
        return output

    def func(self):
        """Executes gradient command"""
        caller = self.caller
        try:
            start, end = self.lhslist[0], self.lhslist[1]
            start = (int(start[0]), int(start[1]), int(start[2]))
            end = (int(end[0]), int(end[1]), int(end[2]))
            text = self.rhs or "Example Text"
        except IndexError:
            caller.msg("Must specify both a start and an end, ex: @gradient 050,132")
            return
        except ValueError:
            caller.msg("Please input numbers such as 050, 134, etc. No braces.")
            return
        reverse = "reverse" in self.switches
        if not reverse:
            caller.msg(self.color_string(start, end, text))
            return
        caller.msg(self.color_string(start, end, text[:len(text)//2]))
        caller.msg(self.color_string(end, start, text[len(text)//2:]))


class CmdInform(ArxPlayerCommand):
    """
    @inform - reads messages sent to you by the game
    Usage:
        @inform
        @inform/new
        @inform <number>[=<end number>]
        @inform/del <number>[=<end number>]
        @inform/delmatches <string to match in categories>
        @inform/shopminimum <number>
        @inform/bankminimum <type>,<number>
        @inform/important <number>
        @inform/readall
        @inform/org[/other switches] <name>[/rest as above]

    Displays your informs. /shopminimum sets a minimum amount that must be paid
    before you are informed of activity in your shops.
    """
    key = "@inform"
    aliases = ["@informs"]
    locks = "cmd: all()"
    banktypes = ("resources", "materials", "silver")

    def read_inform(self, inform):
        """Reads an inform for the caller"""
        msg = "\n{wCategory:{n %s\n" % inform.category
        msg += "{w" + "-"*70 + "{n\n\n%s\n" % inform.message
        self.msg(msg, options={'box': True})
        if self.caller not in inform.read_by.all():
            inform.read_by.add(self.caller)

    def get_inform(self, inform_target, val):
        """Returns an inform from inform_target with index based on val"""
        informs = inform_target.informs.all()
        try:
            val = int(val)
            if val <= 0:
                raise ValueError
            inform = informs[val - 1]
            return inform
        except (ValueError, IndexError):
            self.msg("You must specify a number between 1 and %s." % len(informs))

    def set_attr(self, asset_owner, attr, valuestr):
        """Sets attribute for displaying minimums"""
        try:
            value = int(valuestr)
            if value <= 0:
                raise ValueError
        except (TypeError, ValueError):
            # remove attribute
            self.msg("Removing minimum.")
            setattr(asset_owner, attr, 0)
            asset_owner.save()
            return
        # set attribute with value
        setattr(asset_owner, attr, value)
        asset_owner.save()
        self.display_minimums(asset_owner)

    def display_minimums(self, asset_owner):
        """Displays minimums for informs to be sent"""
        table = evtable.EvTable("{wPurpose{n", "{wResource{n", "{wThreshold{n",  width=78, pad_width=0)
        attrs = (("min_silver_for_inform", "silver", "shop/banking"),
                 ("min_materials_for_inform", "materials", "banking"),
                 ("min_resources_for_inform", "resources", "banking"))
        for attr, res, purp in attrs:
            val = getattr(asset_owner, attr)
            table.add_row(purp, res, "{:,}".format(val))
        self.msg(str(table))

    def func(self):
        """Executes inform command"""
        inform_target = self.caller
        lhs = self.lhs
        lhslist = self.lhslist
        if "org" in self.switches:
            self.switches.remove("org")
            from world.dominion.models import Organization
            try:
                lhsargs = lhs.split("/")
                name = lhsargs[0]
                if len(lhsargs) > 1:
                    lhs = lhsargs[1]
                else:
                    lhs = ""
                lhslist = lhs.split(",")
                org = self.caller.current_orgs.get(name__iexact=name)
                if not org.access(self.caller, "informs"):
                    self.msg("You do not have permission to read informs.")
                    return
            except Organization.DoesNotExist:
                self.msg("No organization by that name.")
                return
            else:
                inform_target = org

        if "new" in self.switches:
            inform = inform_target.informs.exclude(read_by=self.caller).first()
            if not inform:
                self.msg("No unread inform found.")
                return
            self.read_inform(inform)
            return
        informs = list(inform_target.informs.all())
        if "readall" in self.switches:
            read_informs = list(self.caller.read_informs.all())
            informs = [ob for ob in informs if ob not in read_informs]
            if not informs:
                self.msg("Nothing new.")
                return
            for inform in informs:
                self.read_inform(inform)
            return
        if "shopminimum" in self.switches:
            if not self.check_permission(inform_target):
                return
            self.set_attr(inform_target.assets, "min_silver_for_inform", lhs)
            return
        if "bankminimum" in self.switches:
            if not self.check_permission(inform_target):
                return
            valuestr = None
            attr = None
            try:
                attr = lhslist[0]
                valuestr = lhslist[1]
            except IndexError:
                pass
            if attr not in self.banktypes:
                self.msg("Must be one of the following: %s" % ", ".join(self.banktypes))
                self.display_minimums(inform_target.assets)
                return
            attr = "min_%s_for_inform" % attr
            self.set_attr(inform_target.assets, attr, valuestr)
            return
        if not informs:
            self.msg("You have no messages from the game waiting for you.")
            return
        if not lhs:
            table = evtable.EvTable("{w#{n", "{wCategory{n", "{wDate{n", width=78, pad_width=0)
            x = 0
            read_informs = list(self.caller.read_informs.all())
            for info in informs:
                x += 1

                def highlight(ob_str, add_star=False):
                    """Helper function to highlight unread entries"""
                    if info in read_informs:
                        return ob_str
                    if add_star:
                        return "{w*%s{n" % ob_str
                    else:
                        return "{w%s{n" % ob_str
                num = highlight(x, add_star=True)
                cat = highlight(info.category)
                date = highlight(info.date_sent.strftime("%x %X"))
                table.add_row(num, cat, date)
            table.reformat_column(index=0, width=7)
            table.reformat_column(index=1, width=52)
            table.reformat_column(index=2, width=19)
            self.msg(table)
            return
        if "delmatches" in self.switches:
            if not self.check_permission(inform_target):
                return
            informs = inform_target.informs.filter(category__icontains=lhs)
            if informs:
                informs.delete()
                self.msg("Informs deleted.")
                return
            self.msg("No matches.")
            return
        if not self.rhs:
            inform = self.get_inform(inform_target, lhs)
            if not inform:
                return
            informs = [inform]
        else:
            try:
                vals = range(int(lhs), int(self.rhs) + 1)
                if not vals:
                    raise ValueError
            except ValueError:
                self.msg("Invalid numbers.")
                return
            informs = [self.get_inform(inform_target, val) for val in vals]
            informs = [ob for ob in informs if ob]
        if not self.switches:
            for inform in informs:
                self.read_inform(inform)
            return
        if "important" in self.switches:
            inform = self.get_inform(inform_target, lhs)
            if not inform:
                return
            self.toggle_important(inform_target, inform)
            return
        if "del" in self.switches or "delete" in self.switches:
            if not self.check_permission(inform_target):
                return
            for inform in informs:
                inform.delete()
                self.msg("Inform deleted.")
            return
        self.msg("Invalid switch.")
        return

    def check_permission(self, inform_target):
        """Checks permission for seeing transactions"""
        if inform_target == self.caller:
            return True
        if inform_target.access(self.caller, "transactions"):
            return True
        self.msg("You do not have permission to set transactions/delete informs for %s." % inform_target)
        self.msg("This is controlled by the 'transaction' permission under @org/perm.")

    def toggle_important(self, inform_target, inform):
        """Toggles the importance of an inform"""
        if not inform.important and inform_target.informs.filter(important=True).count() > 20:
            self.msg("You may only have 20 informs marked as important.")
            return
        inform.important = not inform.important
        inform.save()
        self.msg("Toggled importance for selected informs.")


class CmdKeyring(ArxCommand):
    """
    Checks keys
    Usage:
        +keyring
        +keyring/remove <chest or room>

    Checks your keys, or Removes a key.
    """
    key = "+keyring"
    locks = "cmd:all()"

    def func(self):
        """Executes keyring command"""
        caller = self.caller
        room_keys = caller.db.keylist or []
        # remove any duplicates and ensure only rooms are in keylist
        room_keys = [ob for ob in set(room_keys) if hasattr(ob, 'is_room') and ob.is_room]
        caller.db.keylist = room_keys
        chest_keys = caller.db.chestkeylist or []
        # remove any deleted objects
        chest_keys = [ob for ob in chest_keys if hasattr(ob, 'tags') and "deleted" not in ob.tags.all()]
        chest_keys = list(set(chest_keys))
        caller.db.chestkeylist = chest_keys
        if "remove" in self.switches:
            old = set(room_keys + chest_keys)
            room_keys = [ob for ob in room_keys if ob.key.lower() != self.args.lower()]
            chest_keys = [ob for ob in chest_keys if ob.key.lower() != self.args.lower()]
            caller.db.keylist = room_keys
            caller.db.chestkeylist = chest_keys
            removed = old - set(room_keys + chest_keys)
            if removed:
                self.msg("Removed %s." % ", ".join(str(ob) for ob in removed))
        key_list = list(room_keys) + list(chest_keys)
        caller.msg("Keys: %s" % ", ".join(ob.key for ob in key_list if ob))
        return


class CmdDump(ArxCommand):
    """
    Empty a container of all its objects. Great for re-sorting items or making
    a complete mess of someone's room.

    Usage:
        dump <container>

    Dump will only work if the container is unlocked.
    """
    key = "dump"
    aliases = ["empty"]
    locks = "cmd:all()"

    def func(self):
        """Executes dump command"""
        caller = self.caller

        if not self.args:
            caller.msg("Dump what?")
            return

        obj = caller.search(self.args)
        if not obj:
            return
        loc = obj.location

        # If the object being dumped is not a container or is not dead and therefore lootable then bail out
        if not (obj.db.container or obj.dead):
            caller.msg("You cannot dump %s as it is not a valid container." % obj)
            return

        # Unless the caller is a builder the locked container cannot be dumped
        if obj.db.locked and not caller.check_permstring("builders"):
            caller.msg("%s is locked. Unlock it first." % obj)
            return

        # Quietly move every object inside the container to container's location
        obj.transfer_all(loc, caller)
        caller.msg("You dump the contents of %s." % obj)
        loc.msg_contents("%s dumps %s and spills its contents all over the floor." % (caller.name, obj),
                         exclude=caller)
        return


class CmdLockObject(ArxCommand):
    """
    Locks or unlocks an exit or container

    Usage:
        lock <object>
        unlock <object>

    Locks or unlocks an object for which you have a key.
    """
    key = "+lock"
    aliases = ["lock", "unlock", "+unlock"]
    locks = "cmd:all()"

    def func(self):
        """Executes lock/unlock command"""
        caller = self.caller
        verb = self.cmdstring.lstrip("+")
        obj = caller.search(self.args)
        if not obj:
            return
        if hasattr(obj, 'lock_exit'):
            if verb == "lock":
                obj.lock_exit(caller)
            else:
                obj.unlock_exit(caller)
            return
        try:
            lock_method = getattr(obj, verb)
            lock_method(caller)
        except AttributeError:
            self.msg("You cannot %s %s." % (verb, obj))
            return


class CmdTidyUp(ArxCommand):
    """
    Removes idle characters from the room

    Usage:
        +tidy

    This removes any character who has been idle for at least
    one hour in your current room, provided that the room is
    public or a room you own.
    """
    key = "+tidy"
    aliases = ["+gohomeyouredrunk"]
    locks = "cmd:all()"

    def func(self):
        """Executes tidy command"""
        caller = self.caller
        loc = caller.location
        if "private" in loc.tags.all() and not caller.check_permstring("builders"):
            owners = loc.db.owners or []
            if caller not in owners:
                self.msg("This is a private room.")
                return
        from typeclasses.characters import Character
        # can only boot Player Characters
        chars = Character.objects.filter(db_location=loc, roster__roster__name="Active")
        found = []
        for char in chars:
            time = char.idle_time
            player = char.player
            # no sessions connected, character that somehow became headless, such as server crash
            if not player or not player.is_connected or not player.sessions.all():
                char.at_post_unpuppet(player)
                found.append(char)
                continue
            if time > 3600:
                player.unpuppet_all()
                found.append(char)
        if not found:
            self.msg("No characters were found to be idle.")
        else:
            self.msg("The following characters were removed: %s" % ", ".join(ob.name for ob in found))
