"""
General helper functions that don't fit neatly under any given category.

They provide some useful string and conversion methods that might
be of use when designing your own game.

"""
import re
from datetime import datetime

from django.conf import settings
from evennia.commands.default.muxcommand import MuxCommand, MuxAccountCommand


def validate_name(name, formatting=True, not_player=True):
    """
    Checks if a name has only letters or apostrophes, or
    ansi formatting if flag is set
    """
    if not not_player:
        player_conflict = False
    else:
        from evennia.accounts.models import AccountDB
        player_conflict = AccountDB.objects.filter(username__iexact=name)
    if player_conflict:
        return None
    if formatting:
        return re.findall('^[\-\w\'{\[,|%=_ ]+$', name)
    return re.findall('^[\w\']+$', name)


def inform_staff(message, post=False, subject=None):
    """
    Sends a message to the 'Mudinfo' channel for staff announcements.

        Args:
            message: text message to broadcast
            post: If True, we post message. If a truthy value other than True, that's the body of the post.
            subject: Post subject.
    """
    from evennia.comms.models import ChannelDB
    try:
        wizchan = ChannelDB.objects.get(db_key__iexact="staffinfo")
        now = time_now().strftime("%H:%M")
        wizchan.tempmsg("{r[%s]:{n %s" % (now, message))
        if post:
            from typeclasses.bulletin_board.bboard import BBoard
            board = BBoard.objects.get(db_key__iexact="Jobs")
            subject = subject or "Staff Activity"
            if post is not True:
                message = post
            board.bb_post(poster_obj=None, msg=message, subject=subject, poster_name="Staff")
    except Exception as err:
        print("ERROR when attempting utils.inform_staff() : %s" % err)


def setup_log(logfile):
    """Sets up a log file"""
    import logging
    file_handle = logging.FileHandler(logfile)
    formatter = logging.Formatter(fmt=settings.LOG_FORMAT, datefmt=settings.DATE_FORMAT)
    file_handle.setFormatter(formatter)
    log = logging.getLogger()
    for handler in log.handlers:
        log.removeHandler(handler)
    log.addHandler(file_handle)
    log.setLevel(logging.DEBUG)
    return log


def get_date():
    """
    Get in-game date as a string
    format is 'M/D/YEAR AR'
    """
    from typeclasses.scripts import gametime
    time = gametime.gametime(format=True)
    month, day, year = time[1] + 1, time[3] + 1, time[0] + 1001
    day += (time[2] * 7)
    date = ("%s/%s/%s AR" % (month, day, year))
    return date


def get_week():
    """Gets the current week for dominion."""
    from evennia.scripts.models import ScriptDB
    weekly = ScriptDB.objects.get(db_key="Weekly Update")
    return weekly.db.week


def time_now(aware=False):
    """Gets naive or aware datetime."""
    if aware:
        from django.utils import timezone
        return timezone.localtime(timezone.now())
    # naive datetime
    return datetime.now()


def time_from_now(date):
    """
    Gets timedelta compared to now
    Args:
        date: Datetime object to compare to now

    Returns:
        Timedelta object of difference between date and the current time.
    """
    try:
        diff = date - time_now()
    except (TypeError, ValueError):
        diff = date - time_now(aware=True)
    return diff


def datetime_format(date):
    """
    Takes a datetime object instance (e.g. from django's DateTimeField)
    and returns a string describing how long ago that date was.
    """
    year, month, day = date.year, date.month, date.day
    hour, minute, second = date.hour, date.minute, date.second
    now = datetime.now()

    if year < now.year:
        # another year
        timestring = str(date.date())
    elif date.date() < now.date():
        # another date, same year
        # put month before day because of FREEDOM
        timestring = "%02i-%02i %02i:%02i" % (month, day, hour, minute)
    elif hour < now.hour - 1:
        # same day, more than 1 hour ago
        timestring = "%02i:%02i" % (hour, minute)
    else:
        # same day, less than 1 hour ago
        timestring = "%02i:%02i:%02i" % (hour, minute, second)
    return timestring


def sub_old_ansi(text):
    """Replacing old ansi with newer evennia markup strings"""
    if not text:
        return ""
    text = text.replace('%r', '|/')
    text = text.replace('%R', '|/')
    text = text.replace('%t', '|-')
    text = text.replace('%T', '|-')
    text = text.replace('%b', '|_')
    text = text.replace('%cr', '|r')
    text = text.replace('%cR', '|[R')
    text = text.replace('%cg', '|g')
    text = text.replace('%cG', '|[G')
    text = text.replace('%cy', '|!Y')
    text = text.replace('%cY', '|[Y')
    text = text.replace('%cb', '|!B')
    text = text.replace('%cB', '|[B')
    text = text.replace('%cm', '|!M')
    text = text.replace('%cM', '|[M')
    text = text.replace('%cc', '|!C')
    text = text.replace('%cC', '|[C')
    text = text.replace('%cw', '|!W')
    text = text.replace('%cW', '|[W')
    text = text.replace('%cx', '|!X')
    text = text.replace('%cX', '|[X')
    text = text.replace('%ch', '|h')
    text = text.replace('%cn', '|n')
    return text


def strip_ansi(text):
    """Stripping out old ansi from a string"""
    from evennia.utils.ansi import strip_ansi
    text = strip_ansi(text)
    text = text.replace('%r', '').replace('%R', '').replace('%t', '').replace('%T', '').replace('%b', '')
    text = text.replace('%cr', '').replace('%cR', '').replace('%cg', '').replace('%cG', '').replace('%cy', '')
    text = text.replace('%cY', '').replace('%cb', '').replace('%cB', '').replace('%cm', '').replace('%cM', '')
    text = text.replace('%cc', '').replace('%cC', '').replace('%cw', '').replace('%cW', '').replace('%cx', '')
    text = text.replace('%cX', '').replace('%ch', '').replace('%cn', '')
    return text


def broadcast(txt, format_announcement=True):
    """Broadcasting a message to the server"""
    from evennia.server.sessionhandler import SESSION_HANDLER
    from evennia.scripts.models import ScriptDB
    if format_announcement:
        txt = "{wServer Announcement{n: %s" % txt
    txt = sub_old_ansi(txt)
    SESSION_HANDLER.announce_all(txt)
    try:
        events = ScriptDB.objects.get(db_key="Event Manager")
        events.add_gemit(txt)
    except ScriptDB.DoesNotExist:
        pass


def raw(text):
    """
    Escape text with Arx-specific codes

        Args:
            text: the text string to escape

        Returns:
            text: Text with escaped codes

    First we transform arx-specific codes into the equivalent
    ansi codes that Evennia uses. Then we escape them all,
    returning the escaped string.
    """
    from evennia.utils.ansi import raw as evennia_raw
    if not text:
        return ""
    # get Evennia codes from the Arx-specific codes
    text = sub_old_ansi(text)
    # if any were turned into newlines, we substitute the code
    text = text.replace('\n', '|/')
    # escape all of them
    text = evennia_raw(text)
    return text


def check_break(caller=None, checking_character_creation=False):
    """
    Checks if staff are currently on break

        Args:
            caller (ObjectDB or AccountDB): object to .msg our end date
            checking_character_creation (bool): Whether we can make characters during break
    Returns:
        (bool): True if we're on our break, false otherwise

    If staff are currently on break, we send an error message to a caller
    if passed along as args, then return True.
    """
    from evennia.server.models import ServerConfig
    allow_character_creation = ServerConfig.objects.conf("allow_character_creation_on_break")
    end_date = ServerConfig.objects.conf("end_break_date")
    if checking_character_creation and allow_character_creation:
        return False
    if not end_date:
        return False
    if end_date > datetime.now():
        if caller:
            caller.msg("That is currently disabled due to staff break.")
            caller.msg("Staff are on break until %s." % end_date.strftime("%x %X"))
        return True
    return False


def delete_empty_tags():
    """Deletes any tag that isn't currently connected to any objects."""
    from evennia.typeclasses.tags import Tag
    empty = Tag.objects.filter(objectdb__isnull=True, accountdb__isnull=True, msg__isnull=True, helpentry__isnull=True,
                               scriptdb__isnull=True, channeldb__isnull=True)
    empty.delete()


def trainer_diagnostics(trainer):
    """
    Gets a string of diagnostic information
    Args:
        trainer: Character object that's doing training

    Returns:
        String of diagnostic information about trainer and its attributes.
    """
    from django.core.exceptions import ObjectDoesNotExist
    msg = "%s: id: %s" % (repr(trainer), id(trainer))

    def get_attr_value(attr_name):
        """Formatting the name of an attribute"""
        ret = ", %s: " % attr_name
        try:
            attr = trainer.db_attributes.get(db_key=attr_name)
            ret += "id: %s, value: %s" % (attr.id, attr.value)
        except (AttributeError, ObjectDoesNotExist):
            ret += "no value"
        return ret
    msg += get_attr_value("currently_training")
    msg += get_attr_value("num_trained")
    return msg


# noinspection PyProtectedMember
def post_roster_cleanup(entry):
    """
    Gets rid of past data for a roster entry from previous players.

    Args:
        entry: RosterEntry we're initializing
    """
    entry.player.nicks.clear()
    entry.character.nicks.clear()
    entry.player.attributes.remove("playtimes")
    entry.player.attributes.remove("rp_preferences")
    for character in entry.player.db.watching or []:
        watched_by = character.db.watched_by or []
        if entry.player in watched_by:
            watched_by.remove(entry.player)
    entry.player.attributes.remove("watching")
    entry.player.attributes.remove("hide_from_watch")
    entry.player.db.mails = []
    entry.player.db.readmails = set()
    entry.player.tags.remove("new_mail")
    entry.player.permissions.remove("Helper")
    disconnect_all_channels(entry.player)
    entry.character.tags.remove("given_starting_gear")
    post_roster_dompc_cleanup(entry.player)


def disconnect_all_channels(player):
    """Removes all channels from the player"""
    for channel in player.account_subscription_set.all():
        channel.disconnect(player)


def reset_to_default_channels(player):
    """
    Sets the player to only be connected to the default Info and Public channels
    Args:
        player: AccountDB object to reset
    """
    from typeclasses.channels import Channel
    disconnect_all_channels(player)
    required_channels = Channel.objects.filter(db_key__in=("Info", "Public"))
    for req_channel in required_channels:
        if not req_channel.has_connection(player):
            req_channel.connect(player)


def post_roster_dompc_cleanup(player):
    """
    Removes patron/protege relationships and sets any 'Voice' rankings to rank 3.
    """
    try:
        dompc = player.Dominion
    except AttributeError:
        return
    dompc.patron = None
    dompc.save()
    for member in dompc.memberships.filter(rank=2):
        member.rank = 3
        member.save()
    try:
        dompc.assets.debts.all().delete()
    except AttributeError:
        pass


def caller_change_field(caller, obj, field, value, field_name=None):
    """
    DRY way of changing a field and notifying a caller of the change.
    Args:
        caller: Object to msg the result
        obj: database object to have a field set and saved
        field (str or unicode): Text value to set
        value: value to set in the field
        field_name: Optional value to use for the field name
    """
    old = getattr(obj, field)
    setattr(obj, field, value)
    obj.save()
    field_name = field_name or field.capitalize()
    if len(str(value)) > 78 or len(str(old)) > 78:
        old = "\n%s\n" % old
        value = "\n%s" % value
    caller.msg("%s changed from %s to %s." % (field_name, old, value))


def create_arx_message(senderobj, message, channels=None, receivers=None, locks=None, header=None, cls=None, tags=None):
    """
    Create a new communication Msg. Msgs represent a unit of
    database-persistent communication between entites. If a proxy class is
    specified, we use that instead of Msg.
    Args:
        senderobj (Object or Player): The entity sending the Msg.
        message (str): Text with the message. Eventual headers, titles
            etc should all be included in this text string. Formatting
            will be retained.
        channels (Channel, key or list): A channel or a list of channels to
            send to. The channels may be actual channel objects or their
            unique key strings.
        receivers (Object, Player, str or list): A Player/Object to send
            to, or a list of them. May be Player objects or playernames.
        locks (str): Lock definition string.
        header (str): Mime-type or other optional information for the message
        cls: Proxy class to use for creating this message.
        tags (iterable): Tag names to attach to the new Msg to identify its type
    Notes:
        The Comm system is created very open-ended, so it's fully possible
        to let a message both go to several channels and to several
        receivers at the same time, it's up to the command definitions to
        limit this as desired.
    """
    from evennia.utils.utils import make_iter
    if not cls:
        from evennia.comms.models import Msg
        cls = Msg
    if not message:
        # we don't allow empty messages.
        return None
    new_message = cls(db_message=message)
    new_message.save()
    for sender in make_iter(senderobj):
        new_message.senders = sender
    new_message.header = header
    for channel in make_iter(channels):
        new_message.channels = channel
    for receiver in make_iter(receivers):
        new_message.receivers = receiver
    if locks:
        new_message.locks.add(locks)
    new_message.save()
    for tag in make_iter(tags):
        new_message.tags.add(tag, category="msg")
    return new_message


def cache_safe_update(queryset, **kwargs):
    """
    Does a table-wide queryset update and then iterates through and
    changes all models in memory so that they do not overwrite the
    changes upon saving themselves. Note that F() objects may behave
    very strangely and should not be used as kwargs.

    Args:
        queryset: The queryset to modify.
        **kwargs: The fields we're changing with their values.
    """
    queryset.update(**kwargs)
    for obj in queryset:
        for keyword, value in kwargs.items():
            setattr(obj, keyword, value)


class ArxCommmandMixins(object):
    """Mixin class for Arx commands"""
    def check_switches(self, switch_set):
        """Checks if the commands switches are inside switch_set"""
        return set(self.switches) & set(switch_set)


class ArxCommand(ArxCommmandMixins, MuxCommand):
    """Base command for Characters for Arx"""
    pass


class ArxPlayerCommand(ArxCommmandMixins, MuxAccountCommand):
    """Base command for Players/Accounts for Arx"""
    pass


def text_box(text):
    """Encloses characters in a cute little text box"""
    boxchars = '\n{w' + '*' * 70 + '{n\n'
    return boxchars + text + boxchars


def create_gemit_and_post(msg, caller, episode_name=None, synopsis=None, orgs_list=None):
    """Creates a new StoryEmit and an accompanying episode if specified, then broadcasts it."""
    # current story
    from web.character.models import Story, Episode, StoryEmit
    story = Story.objects.latest('start_date')
    chapter = story.current_chapter
    if episode_name:
        date = datetime.now()
        episode = Episode.objects.create(name=episode_name, date=date, chapter=chapter, synopsis=synopsis)
    else:
        episode = Episode.objects.latest('date')
    gemit = StoryEmit.objects.create(episode=episode, chapter=chapter, text=msg,
                                     sender=caller)
    if orgs_list:
        gemit.orgs.add(*orgs_list)
        caller.msg("Announcing to %s ...\n%s" % (list_to_string(orgs_list), msg))
    gemit.broadcast()
    return gemit

def broadcast_msg_and_post(msg, caller, episode_name=None):
    """Sends a message to all online sessions, then makes a post about it."""
    caller.msg("Announcing to all connected players ...")
    if not msg.startswith("{") and not msg.startswith("|"):
        msg = "|g" + msg
    # save this non-formatted version for posting to BB
    post_msg = msg
    # format msg for logs and announcement
    box_chars = '\n{w' + '*' * 70 + '{n\n'
    msg = box_chars + msg + box_chars
    broadcast(msg, format_announcement=False)
    # get board and post
    from typeclasses.bulletin_board.bboard import BBoard
    bboard = BBoard.objects.get(db_key__iexact="story updates")
    subject = "Story Update"
    if episode_name:
        subject = "Episode: %s" % episode_name
    bboard.bb_post(poster_obj=caller, msg=post_msg, subject=subject, poster_name="Story")

def dict_from_choices_field(cls, field_name, include_uppercase=True):
    """Gets a dict from a Choices tuple in a model"""
    choices_tuple = getattr(cls, field_name)
    lower_case_dict = {string.lower(): integer for integer, string in choices_tuple}
    if include_uppercase:
        upper_case_dict = {string.capitalize(): integer for integer, string in choices_tuple}
        lower_case_dict.update(upper_case_dict)
    return lower_case_dict


def passthrough_properties(field_name, *property_names):
    """
    This function is designed to be used as a class decorator that takes the name of an attribute that
    different properties of the class pass through to. For example, if we have a self.foo object,
    and our property 'bar' would return self.foo.bar, then we'd set 'foo' as the field_name,
    and 'bar' would go in the property_names list.
    Args:
        field_name: The name of the attribute of the object we pass property calls through to.
        *property_names: List of property names that we do the pass-through to.

    Returns:
        A function that acts as a decorator for the class which attaches the properties to it.
    """
    def wrapped(cls):
        """Wrapper around a class decorated with the properties"""
        for name in property_names:
            def generate_property(prop_name):
                """Helper function to generate the getter/setter functions for each property"""
                def get_func(self):
                    """Getter function for the property"""
                    parent = getattr(self, field_name)
                    return getattr(parent, prop_name)

                def set_func(self, value):
                    """Setter function for the property"""
                    parent = getattr(self, field_name)
                    setattr(parent, prop_name, value)
                setattr(cls, prop_name, property(get_func, set_func))
            generate_property(name)
        return cls
    return wrapped


def lowercase_kwargs(*kwarg_names, **defaults):
    """
    Decorator for converting given kwargs that are list of strings to lowercase, and optionally appending a
    default value.
    """
    default_append = defaults.get('default_append', None)
    from functools import wraps

    def wrapper(func):
        """The actual decorator that we'll return"""
        @wraps(func)
        def wrapped(*args, **kwargs):
            """The wrapped function"""
            for kwarg in kwarg_names:
                if kwarg in kwargs:
                    kwargs[kwarg] = kwargs[kwarg] or []
                    kwargs[kwarg] = [ob.lower() for ob in kwargs[kwarg]]
                    if default_append is not None:
                        kwargs[kwarg].append(default_append)
            return func(*args, **kwargs)
        return wrapped
    return wrapper


def fix_broken_attributes(broken_object):
    """
    Patch to fix objects broken by broken formset for Attributes in django admin, where validation errors convert
    the Attributes to unicode.
    """
    from ast import literal_eval
    from evennia.utils.dbserialize import from_pickle
    for attr in broken_object.attributes.all():
        try:
            attr.value = from_pickle(literal_eval(attr.value))
        except (ValueError, SyntaxError) as err:
            print("Error for attr %s: %s" % (attr.key, err))
            continue

def list_to_string(inlist, endsep="and", addquote=False):
    """
    This pretty-formats a list as string output, adding an optional
    alternative separator to the second to last entry.  If `addquote`
    is `True`, the outgoing strings will be surrounded by quotes.
    Args:
        inlist (list): The list to print.
        endsep (str, optional): If set, the last item separator will
            be replaced with this value. Oxford comma used for "and" and "or".
        addquote (bool, optional): This will surround all outgoing
            values with double quotes.
    Returns:
        liststr (str): The list represented as a string.
    Examples:
        ```python
         # no endsep:
            [1,2,3] -> '1, 2, 3'
         # with endsep=='and':
            [1,2,3] -> '1, 2, and 3'
         # with endsep=='that delicious':
            [7,8,9] -> '7, 8 that delicious 9'
         # with addquote and endsep
            [1,2,3] -> '"1", "2" and "3"'
        ```
    """
    if not endsep:
        endsep = ","
    elif endsep in ("and", "or") and len(inlist) > 2:
        endsep = ", " + endsep
    else:
        endsep = " " + endsep
    if not inlist:
        return ""
    if addquote:
        if len(inlist) == 1:
            return "\"%s\"" % inlist[0]
        return ", ".join("\"%s\"" % v for v in inlist[:-1]) + "%s %s" % (endsep, "\"%s\"" % inlist[-1])
    else:
        if len(inlist) == 1:
            return str(inlist[0])
        return ", ".join(str(v) for v in inlist[:-1]) + "%s %s" % (endsep, inlist[-1])
