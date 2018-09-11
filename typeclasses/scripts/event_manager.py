"""
Script to handle timing for events in the game.
"""

from django.conf import settings
from .scripts import Script
from world.dominion.models import RPEvent
from twisted.internet import reactor
from evennia.server.sessionhandler import SESSIONS
from evennia.utils.ansi import parse_ansi
import traceback
from server.utils.arx_utils import time_from_now, time_now

LOGPATH = settings.LOG_DIR + "/rpevents/"
GMPATH = LOGPATH + "gm_logs/"


def delayed_start(event_id):
    # noinspection PyBroadException
    try:
        event = RPEvent.objects.get(id=event_id)
        from evennia.scripts.models import ScriptDB
        script = ScriptDB.objects.get(db_key="Event Manager")
        if event.id in script.db.cancelled:
            script.db.cancelled.remove(event.id)
            return
        script.start_event(event)
    except Exception:
        traceback.print_exc()


class EventManager(Script):
    """
    This script repeatedly saves server times so
    it can be retrieved after server downtime.
    """
    # noinspection PyAttributeOutsideInit
    def at_script_creation(self):
        """
        Setup the script
        """
        self.key = "Event Manager"
        self.desc = "Manages RP events and notifications"
        self.interval = 300
        self.persistent = True
        self.start_delay = True
        # we store everything as IDs of the event objects rather than the events themselves
        # due to serialization code not working on some django model instances
        self.db.idle_events = {}
        self.db.active_events = []
        self.db.pending_start = {}
        self.db.cancelled = []

    def at_repeat(self):
        """
        Called every 5 minutes to update the timers. If we find an upcoming event
        based on date, we'll do an announcement if it starts between 55-60 mins,
        then another announcement if it's starting under 10 minutes. If under 5
        minutes, we schedule it to start.
        """
        idles = self.db.idle_events
        actives = self.db.active_events
        for eventid in idles:
            # if the event has been idle for an hour, close it down
            if idles[eventid] >= 12:
                # noinspection PyBroadException
                try:
                    event = RPEvent.objects.get(id=eventid)
                    self.finish_event(event)
                except Exception:
                    traceback.print_exc()
                    del idles[eventid]
        # copy all active events to idle events for next check
        for eventid in actives:
            idles[eventid] = idles.get(eventid, 0) + 1
        # check for new events to announce
        upcoming = RPEvent.objects.filter(finished=False).exclude(id__in=actives)
        for event in upcoming:
            diff = time_from_now(event.date).total_seconds()
            if diff < 0:
                self.confirm_event_location(event)
                self.start_event(event)
            elif diff < 300:
                self.confirm_event_location(event)
                if event.id not in self.db.pending_start:
                    reactor.callLater(diff, delayed_start, event.id)
                    self.db.pending_start[event.id] = diff
            elif diff < 600:
                self.confirm_event_location(event)
                self.announce_upcoming_event(event, diff)
            elif 1500 < diff <= 1800:
                self.confirm_event_location(event)
                self.announce_upcoming_event(event, diff)
            elif 3300 < diff <= 3600:
                self.confirm_event_location(event)
                self.announce_upcoming_event(event, diff)

    @staticmethod
    def announce_upcoming_event(event, diff):
        mins = int(diff/60)
        secs = diff % 60
        announce_msg = "{wEvent: '%s'(#%s) will start in %s minutes and %s seconds.{n" % (event.name, event.id,
                                                                                          mins, secs)
        if event.public_event:
            SESSIONS.announce_all(announce_msg)
        else:
            event.make_announcement(announce_msg)

    @staticmethod
    def confirm_event_location(event):
        if event.location is None:
            if event.plotroom is not None:
                event.create_room()

    @staticmethod
    def get_event_location(event):
        loc = event.location
        if loc is None and event.plotroom is not None:
            event.create_room()
            loc = event.location
        if loc:
            return loc
        gms = event.gms.filter(player__db_is_connected=True)
        for gm in gms:
            loc = gm.player.char_ob.location
            if loc:
                return loc
        else:
            try:
                loc = event.main_host.player.char_ob.location
            except AttributeError:
                pass
        return loc

    # noinspection PyBroadException
    def start_event(self, event, location=None):
        # see if this was called from callLater, and if so, remove reference to it
        if event.id in self.db.pending_start:
            del self.db.pending_start[event.id]

        # if we've already started, do nothing. Can happen due to queue
        if event.id in self.db.active_events:
            return
        # announce event start
        if location:
            loc = location
        else:
            loc = self.get_event_location(event)
        if loc:  # set up event logging, tag room
            loc.start_event_logging(event)
            start_str = "%s has started at %s." % (event.name, loc.name)
            if loc != event.location:
                event.location = loc
                event.save()
        else:
            start_str = "%s has started." % event.name
        if event.public_event:
            border = "{w***********************************************************{n\n"
            start_str = border + start_str + "\n" + border
            SESSIONS.announce_all(start_str)
        elif event.location:
            try:
                event.location.msg_contents(start_str, options={'box': True})
            except Exception:
                pass
        self.db.active_events.append(event.id)
        self.db.idle_events[event.id] = 0
        now = time_now()
        if now < event.date:
            # if we were forced to start early, update our date
            event.date = now
            event.save()
        # set up log for event
        open_logs = self.ndb.open_logs or []
        open_gm_logs = self.ndb.open_gm_logs or []
        # noinspection PyBroadException
        with open(self.get_log_path(event.id), 'a+') as log:
            open_logs.append(log)
        with open(self.get_gmlog_path(event.id), 'a+') as gmlog:
            open_gm_logs.append(gmlog)
        self.ndb.open_logs = open_logs
        self.ndb.open_gm_logs = open_gm_logs

    def finish_event(self, event):
        loc = self.get_event_location(event)
        if loc:
            try:
                loc.stop_event_logging()
            except AttributeError:
                loc.db.current_event = None
                loc.msg_contents("{rEvent logging is now off for this room.{n")
                loc.tags.remove("logging event")
            end_str = "%s has ended at %s." % (event.name, loc.name)
        else:
            end_str = "%s has ended." % event.name
        if event.public_event:
            SESSIONS.announce_all(end_str)
        else:
            if loc:
                loc.msg_contents(end_str)
        event.finished = True
        event.clear_room()
        event.save()
        if event.id in self.db.active_events:
            self.db.active_events.remove(event.id)
        if event.id in self.db.idle_events:
            del self.db.idle_events[event.id]
        self.do_awards(event)
        # noinspection PyBroadException
        self.delete_event_post(event)

    def move_event(self, event, new_location):
        if event.location:
            event.location.stop_event_logging()
        event.location = new_location
        event.save()
        if event.id in self.db.active_events:
            new_location.start_event_logging(event)

    def add_msg(self, eventid, msg, sender=None):
        # reset idle timer for event
        self.db.idle_events[eventid] = 0
        event = RPEvent.objects.get(id=eventid)
        msg = parse_ansi(msg, strip_ansi=True)
        msg = "\n" + msg + "\n"
        with open(self.get_log_path(eventid), 'a+') as log:
            log.write(msg)
        try:
            dompc = sender.player.Dominion
            if dompc not in event.attended:
                event.record_attendance(dompc)
        except AttributeError:
            pass

    def add_gmnote(self, eventid, msg):
        msg = parse_ansi(msg, strip_ansi=True)
        msg = "\n" + msg + "\n"
        with open(self.get_gmlog_path(eventid), 'a+') as log:
            log.write(msg)

    def add_gemit(self, msg):
        msg = parse_ansi(msg, strip_ansi=True)
        for event_id in self.db.active_events:
            self.add_msg(event_id, msg)

    @staticmethod
    def do_awards(event):
        qualified_hosts = [ob for ob in event.hosts if ob in event.attended]
        if not qualified_hosts:
            main_host = event.main_host
            if main_host:
                qualified_hosts = [main_host]
        for host in qualified_hosts:
            if not host.player:
                continue
            # award karma
            try:
                account = host.player.roster.current_account
                account.karma += 1
                account.save()
            except (AttributeError, ValueError, TypeError):
                pass
            # award prestige
            try:
                host.assets.adjust_prestige(event.prestige/len(qualified_hosts))
            except (AttributeError, ValueError, TypeError):
                continue

    def cancel_event(self, event):
        if event.id in self.db.pending_start:
            self.db.cancelled.append(event.id)
            del self.db.pending_start[event.id]
        self.delete_event_post(event)
        event.delete()

    def reschedule_event(self, event):
        diff = time_from_now(event.date).total_seconds()
        if diff < 0:
            self.start_event(event)
            return

    @staticmethod
    def get_event_board():
        from typeclasses.bulletin_board.bboard import BBoard
        return BBoard.objects.get(db_key__iexact="events")

    def post_event(self, event, poster, post):
        board = self.get_event_board()
        board.bb_post(poster_obj=poster, msg=post, subject=event.name,
                      event=event)

    def delete_event_post(self, event):
        # noinspection PyBroadException
        try:
            board = self.get_event_board()
            post = board.posts.get(db_tags__db_key=event.tagkey,
                                   db_tags__db_data=event.tagdata)
            post.delete()
        except Exception:
            pass

    @staticmethod
    def get_log_path(eventid):
        logname = "event_log_%s.txt" % eventid
        return LOGPATH + logname

    @staticmethod
    def get_gmlog_path(eventid):
        logname = "event_log_%s.txt" % eventid
        gmlogname = "gm_%s" % logname
        return GMPATH + gmlogname
