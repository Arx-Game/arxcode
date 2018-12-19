"""
Commands for rumormills.
"""

from evennia import CmdSet
from commands.base import ArxCommand
from evennia.utils import evtable
from server.utils.arx_utils import get_week, time_now
from world.stats_and_skills import do_dice_check
from world.dominion.models import AssignedTask
from server.utils import arx_more

RUMOR_LIFETIME = 30


class RumorCmdSet(CmdSet):
    """CmdSet for a market."""
    key = "RumorCmdSet"
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
        self.add(CmdGossip())
        self.add(CmdRumor())


class CmdGossip(ArxCommand):
    """
    gossip
    Usage:
        gossip
        gossip/story <#>
        gossip/investigate <#>
        gossip/start <message>
        gossip/spread <#>
        gossip/squelch <#>

    Check gossip in this location. To see rumors about a specific character,
    use 'rumors'. gossip/spread will allow you to spread to a new room any
    gossip that you've heard this session. 'squelch' attempts to get rid of
    gossip at a particular location by intimidating non-player characters.

    Use gossip/story to read about a story that's been circulating around
    in recent weeks.
    """
    key = "gossip"
    locks = "cmd:all()"
    help_category = "Rumormill"

    @staticmethod
    def investigate(rumor, caller, diff):
        result = do_dice_check(caller, stat="perception", skill="investigation", difficulty=diff)
        if result > 0:
            senders = rumor.db_sender_objects.all()
            return senders

    @staticmethod
    def intimidate(caller, diff):
        result = do_dice_check(caller, stat="command", skill="intimidation", difficulty=diff)
        if result > 0:
            return True
        return False

    def disp_rumors(self, caller, rumors, add_heard=True):
        table = evtable.EvTable("{w#{n", "{w%s{n" % self.key.capitalize(),
                                border="cells", width=78, align="l", justify=True)
        x = 0
        heard_rumors = caller.ndb.heard_rumors or []
        week = get_week()
        for rumor in rumors:
            now = time_now()
            if (now - rumor.db_date_created).days > RUMOR_LIFETIME:
                continue
            x += 1
            table.add_row(x, rumor.db_message)
            if add_heard and rumor not in heard_rumors:
                heard_rumors.append(rumor)
        if add_heard:
            caller.ndb.heard_rumors = heard_rumors
        msg = "{w%s{n" % self.key.capitalize().center(78)
        msg += "\n"
        msg += str(table)
        stories = AssignedTask.objects.filter(finished=True, week__gte=week-3, observer_text__isnull=False)
        if stories:
            msg += "\n"
            msg += "{wOther Rumors{n".center(78)
            msg += "\n"
            table = evtable.EvTable("{wRumored Story #{n", "{wWeek{n", border="cells", width=78)
            for story in stories:
                table.add_row(story.id, story.week)
            msg += str(table)
        return arx_more.msg(caller, msg, justify_kwargs=False)
    
    def get_room_rumors(self):
        loc = self.caller.location
        return getattr(loc.messages, self.key)

    def func(self):
        """Execute command."""
        self.msg("Currently disabled.")
        return
        # caller = self.caller
        # loc = caller.location
        # rumors = self.get_room_rumors()
        # if not self.args:
        #     msg = self.disp_rumors(caller, rumors)
        #     caller.msg(msg)
        #     return
        # if "start" in self.switches:
        #     rumor = create_message(caller, self.lhs, receivers=(loc, caller))
        #     rumor.tags.add(self.key, category="msg")
        #     if rumor not in loc.messages.gossip:
        #         loc.messages.gossip.append(rumor)
        #     heard = caller.ndb.heard_rumors or []
        #     heard.append(rumor)
        #     caller.ndb.heard_rumors = heard
        #     caller.msg("You have started the rumor: %s" % self.lhs)
        #     return
        # if "story" in self.switches or not self.switches:
        #     week = get_week()
        #     stories = AssignedTask.objects.filter(finished=True, week__gte=week-3, observer_text__isnull=False)
        #     try:
        #         story = stories.get(id=int(self.args))
        #     except AssignedTask.DoesNotExist:
        #         caller.msg("No story for that number.")
        #         return
        #     except (ValueError, TypeError):
        #         caller.msg("Story must be a number.")
        #         return
        #     caller.msg(story.story, options={'box': True})
        #     return
        # if "investigate" in self.switches:
        #     try:
        #         num = int(self.lhs)
        #     except ValueError:
        #         caller.msg("Must give a number of the rumor.")
        #         return
        #     if num < 1 or num > len(rumors):
        #         caller.msg("Must give a number between 1 and %s." % len(rumors))
        #         return
        #     num -= 1
        #     rumor = rumors[num]
        #     if rumor.db_receivers_objects.filter(id=caller.id):
        #         caller.msg("You have already attempted to investigate this rumor.")
        #         return
        #     header = loc.messages.parse_header(rumor)
        #     difficulty = header.get("difficulty", 15)
        #     rumor.db_receivers_objects.add(caller)
        #     origin = self.investigate(rumor, caller, difficulty)
        #     if origin:
        #         senders = ", ".join(ob.key for ob in origin if not ob.check_permstring("builders"))
        #         if senders:
        #             caller.msg("Your investigation was a success. " +
        #                        "You figured out that the rumor was started by: %s." % senders)
        #             return
        #     caller.msg("You weren't able to learn anything about this.")
        #     return
        # if "squelch" in self.switches:
        #     if not rumors:
        #         caller.msg("No rumors here to squelch.")
        #         return
        #     try:
        #         rumor = rumors[int(self.args) - 1]
        #     except (TypeError, ValueError, IndexError):
        #         caller.msg("Must input a number between 1 and %s." % len(rumors))
        #         return
        #     caller.location.msg_contents("%s attempts to intimidate people here into stop spreading rumors." %
        #                                  caller.name)
        #     if self.intimidate(caller, 15):
        #         rumor.db_receivers_objects.remove(caller.location)
        #         caller.msg("People here will 'forget' this rumor existed.")
        #         return
        #     caller.msg("Your attempt to intimidate the people talking here may not have been effective.")
        #     return
        # if "spread" in self.switches:
        #     rumors = caller.ndb.heard_rumors or []
        #     if not self.args:
        #         caller.msg("Rumors you've heard:")
        #         caller.msg(self.disp_rumors(caller, rumors, add_heard=False))
        #         return
        #     if not rumors:
        #         caller.msg("You have heard no rumors recently to repeat.")
        #         return
        #     try:
        #         rumor = rumors[int(self.args)]
        #         rumor.db_receivers_objects.add(loc)
        #         rumor.db_sender_objects.add(caller)
        #         caller.msg("Rumor added to this location.")
        #         return
        #     except (ValueError, IndexError):
        #         caller.msg("You must select a rumor by number, between 0 and %s." % (len(caller.ndb.heard_rumors)-1))
        #         if rumors:
        #             caller.msg(self.disp_rumors(caller, rumors, add_heard=False))
        #         return


class CmdRumor(CmdGossip):
    """
    rumors
    Usage:
        rumors
        rumors/story <#>
        rumors/investigate <#>
        rumors/start <character>=<message>
        rumors/spread <#>
        rumors/squelch <#>

    Check rumors about different characters that are being repeated in
    this location. Use rumors/story to read stories that have been
    circulating about in rumors in recent weeks.
    """
    key = "rumors"
    aliases = ["rumor"]
    locks = "cmd:all()"
    help_category = "Rumormill"

    def disp_rumors(self, caller, rumors, add_heard=True):
        table = evtable.EvTable("{w#{n", "{wTopic{n", "{w%s{n" % self.key.capitalize(),
                                border="cells", width=78, align="l", justify=True)
        x = 0
        week = get_week()
        heard_rumors = caller.ndb.heard_rumors or []
        for rumor in rumors:
            x += 1
            player = rumor.db_receivers_players.all()
            if not player:
                continue
            player = player[0].key.capitalize()[:12]
            table.add_row(x, player, rumor.db_message)
            if add_heard and rumor not in heard_rumors:
                heard_rumors.append(rumor)
        table.reformat_column(0, width=5)
        table.reformat_column(1, width=12)
        table.reformat_column(2, width=61)
        if add_heard:
            caller.ndb.heard_rumors = heard_rumors
        msg = "{w%s{n" % self.key.capitalize().center(78)
        msg += "\n"
        msg += str(table)
        stories = AssignedTask.objects.filter(finished=True, week__gte=week-3, observer_text__isnull=False)
        if stories:
            msg += "\n"
            msg += "{wOther Rumors{n".center(78)
            msg += "\n"
            table = evtable.EvTable("{wRumored Story #{n", "{wWeek{n", border="cells", width=78)
            for story in stories:
                table.add_row(story.id, story.week)
            msg += str(table)
        return arx_more.msg(caller, msg, justify_kwargs=False)
    
    def func(self):
        self.msg("Currently disabled.")
        return
        # caller = self.caller
        # loc = caller.location
        # if "start" in self.switches:
        #     if not self.rhs:
        #         caller.msg("Syntax: rumors/start <character>=<message>")
        #         return
        #     player = caller.player.search(self.lhs)
        #     if not player:
        #         return
        #     if not player.char_ob:
        #         caller.msg("They have no character.")
        #         return
        #     rumor = create_message(caller, self.rhs, receivers=(loc, caller, player))
        #     rumor.tags.add(self.key, category="msg")
        #     if rumor not in loc.messages.rumors:
        #         loc.messages.rumors.append(rumor)
        #     caller.msg("You have started the rumor: %s" % self.lhs)
        #     return
        # super(CmdRumor, self).func()
        # return
