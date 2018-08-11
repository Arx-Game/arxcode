"""
Channel

The channel class represents the out-of-character chat-room usable by
Players in-game. It is mostly overloaded to change its appearance, but
channels can be used to implement many different forms of message
distribution systems.

Note that sending data to channels are handled via the CMD_CHANNEL
syscommand (see evennia.syscmds). The sending should normally not need
to be modified.

"""

from evennia import DefaultChannel
from evennia.utils.utils import lazy_property


# noinspection PyUnusedLocal
class Channel(DefaultChannel):
    """
    Working methods:
        at_channel_creation() - called once, when the channel is created
        has_connection(player) - check if the given player listens to this channel
        connect(player) - connect player to this channel
        disconnect(player) - disconnect player from channel
        access(access_obj, access_type='listen', default=False) - check the
                    access on this channel (default access_type is listen)
        delete() - delete this channel
        message_transform(msg, emit=False, prefix=True,
                          sender_strings=None, external=False) - called by
                          the comm system and triggers the hooks below
        msg(msgobj, header=None, senders=None, sender_strings=None,
            keep_log=None, online=False, emit=False, external=False) - main
                send method, builds and sends a new message to channel.
        tempmsg(msg, header=None, senders=None) - wrapper for sending non-persistent
                messages.
        distribute_message(msg, online=False) - send a message to all
                connected players on channel, optionally sending only
                to players that are currently online (optimized for very large sends)

    Useful hooks:
        channel_prefix(msg, emit=False) - how the channel should be
                  prefixed when returning to user. Returns a string
        format_senders(senders) - should return how to display multiple
                senders to a channel
        pose_transform(msg, sender_string) - should detect if the
                sender is posing, and if so, modify the string
        format_external(msg, senders, emit=False) - format messages sent
                from outside the game, like from IRC
        format_message(msg, emit=False) - format the message body before
                displaying it to the user. 'emit' generally means that the
                message should not be displayed with the sender's name.

        pre_join_channel(joiner) - if returning False, abort join
        post_join_channel(joiner) - called right after successful join
        pre_leave_channel(leaver) - if returning False, abort leave
        post_leave_channel(leaver) - called right after successful leave
        pre_send_message(msg) - runs just before a message is sent to channel
        post_send_message(msg) - called just after message was sent to channel

    """
    @lazy_property
    def org_channel(self):
        from world.dominion.models import Organization
        try:
            return self.org
        except Organization.DoesNotExist:
            return None
    
    @property
    def mutelist(self):
        """We cache mutelist here because retrieving a SaverList from Attribute is very expensive"""
        if self.ndb.mute_list is None:
            # get a copy so cached isn't a SaverList with direct database connection
            self.ndb.mute_list = list(self.db.mute_list or [])
        return self.ndb.mute_list

    @property
    def non_muted_subs(self):
        subs = self.subscriptions.all()
        listening = [ob for ob in subs if ob.is_connected and ob not in self.mutelist]
        return listening

    @staticmethod
    def format_wholist(listening):
        if listening:
            listening = sorted(listening, key=lambda x: x.key.capitalize())
            string = ", ".join([player.key.capitalize() for player in listening])
        else:
            string = "<None>"
        return string

    @property
    def complete_wholist(self):
        """
        For Staff
        """
        return self.format_wholist(self.non_muted_subs)

    @property
    def wholist(self):
        # check if we have an org
        who_list = self.non_muted_subs
        org = self.org_channel
        if org and org.secret:
            # check if list members are players who are non-secret members of the org
            non_secret = [ob.player.player for ob in org.active_members.filter(secret=False)]
            who_list = [ob for ob in who_list if ob in non_secret or ob.check_permstring("builders")]
        # pass final list to format_wholist and return it
        return self.format_wholist(who_list)

    def temp_mute(self, caller):
        """
        Temporarily mutes a channel for caller.
        Turned back on when caller disconnects.
        """
        temp_mute_list = caller.db.temp_mute_list or []
        if self in temp_mute_list:
            return
        temp_mute_list.append(self)
        caller.db.temp_mute_list = temp_mute_list
        self.mute(caller)
        caller.msg("%s will be muted until the end of this session." % self)

    def mute(self, subscriber):
        """
        Adds an entity to the list of muted subscribers.
        A muted subscriber will no longer see channel messages,
        but may use channel commands.
        """
        mutelist = self.mutelist
        if subscriber not in mutelist:
            mutelist.append(subscriber)
            self.db.mute_list = mutelist
            # invalidate cache
            self.ndb.mute_list = None
            return True

    def unmute(self, subscriber):
        """
        Removes an entity to the list of muted subscribers.
        A muted subscriber will no longer see channel messages,
        but may use channel commands.
        """
        mutelist = self.mutelist
        if subscriber in mutelist:
            mutelist.remove(subscriber)
            self.db.mute_list = mutelist
            # invalidate cache
            self.ndb.mute_list = None
            return True

    def clear_mute(self):
        self.db.mute_list = []
        self.ndb.mute_list = None
        
    def delete_chan_message(self, message):
        """
        When given a message object, if the message has other
        receivers, just remove the channels inside the message so
        that the other receivers don't lose the message. Otherwise,
        delete it completely.
        """
        if self not in message.channels:
            return
        if message.receivers:
            # remove the channel from the message, but leave msg
            # intact for other receivers
            del message.channels
            return
        message.delete()

    def channel_prefix(self, msg=None, emit=False):
        """
        How the channel should prefix itself for users. Return a string.
        """
        # use color if defined
        if self.db.colorstr:
            return '%s[%s]{n ' % (self.db.colorstr, self.key)
        # else default is whether it's private or not
        if self.locks.get('listen').strip() != "listen:all()":
            return '{y[%s]{n ' % self.key
        return '{w[%s]{n ' % self.key

    # noinspection PyMethodMayBeStatic
    def pose_transform(self, msg, sender_string):
        """
        Detects if the sender is posing, and modifies the message accordingly.
        """
        pose = False
        message = msg.message
        message_start = message.lstrip()
        if message_start.startswith((':', ';')):
            pose = True
            message = message[1:]
            if not message.startswith((':', "'", ',')):
                if not message.startswith(' '):
                    message = ' ' + message
        sender_string = "{c%s{n" % sender_string
        if pose:
            return '%s%s' % (sender_string, message)
        else:
            return '%s: %s' % (sender_string, message)

    def tempmsg(self, message, header=None, senders=None):
        """
        A wrapper for sending non-persistent messages. Note that this will
        still be a persistent message if the channel's logging is turned on.
        By default, channel logging is False, so a temp message being captured
        should only happen by intent.
        """
        self.msg(message, senders=senders, header=header, keep_log=False)
