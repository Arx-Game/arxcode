"""
Script for periodically removing unwanted objects from the database.
"""
from datetime import datetime, timedelta
import traceback

from server.utils.arx_utils import inform_staff, get_week
from .scripts import Script
from .script_mixins import RunDateMixin


class DatabaseCleanup(RunDateMixin, Script):
    """
    Occasionally will wipe stale objects from database.
    """
    DAYS_BETWEEN_CLEANUP = 7

    # noinspection PyAttributeOutsideInit
    def at_script_creation(self):
        """
        Setup the script
        """
        self.key = "Database Cleanup"
        self.desc = "Removes stale objects"
        self.interval = 3600
        self.persistent = True
        self.start_delay = True
        self.attributes.add("run_date", datetime.now() + timedelta(days=7))

    def at_repeat(self):
        """
        Called every minute to update the timers.
        """
        if self.check_event():
            # check if we've been tagged to not reset next time we run
            self.do_cleanup()
            self.db.run_date += timedelta(days=self.DAYS_BETWEEN_CLEANUP)

    def do_cleanup(self):
        """Cleans up stale objects from database"""
        date = datetime.now()
        offset = timedelta(days=-30)
        date = date + offset
        try:
            self.cleanup_old_informs(date)
            self.cleanup_old_tickets(date)
            self.cleanup_django_admin_logs(date)
            self.cleanup_soft_deleted_objects()
            self.cleanup_empty_tags()
            self.cleanup_old_praises()
            self.cleanup_old_sessions(date)
        except Exception as err:
            traceback.print_exc()
            print("Error in cleanup: %s" % err)
        inform_staff("Database cleanup completed.")

    @staticmethod
    def cleanup_empty_tags():
        """Deletes stale tags"""
        from server.utils.arx_utils import delete_empty_tags
        delete_empty_tags()

    @staticmethod
    def cleanup_soft_deleted_objects():
        """Permanently deletes previously 'soft'-deleted objects"""
        try:
            from evennia.objects.models import ObjectDB
            import time
            qs = ObjectDB.objects.filter(db_tags__db_key__iexact="deleted")
            current_time = time.time()
            for ob in qs:
                # never delete a player character
                if ob.player_ob:
                    ob.undelete()
                    continue
                # never delete something in-game
                if ob.location:
                    ob.undelete()
                    continue
                deleted_time = ob.db.deleted_time
                # all checks passed, delete it for reals
                if (not deleted_time) or (current_time - deleted_time > 604800):
                    # if we're a unique retainer, wipe the agent object as well
                    if hasattr(ob, 'agentob'):
                        if ob.agentob.agent_class.unique:
                            ob.agentob.agent_class.delete()
                    ob.delete()
        except Exception as err:
            traceback.print_exc()
            print("Error in cleaning up deleted objects: %s" % err)

    @staticmethod
    def cleanup_django_admin_logs(date):
        """Deletes old django admin logs"""
        try:
            from django.contrib.admin.models import LogEntry
            qs = LogEntry.objects.filter(action_time__lte=date)
            qs.delete()
        except Exception as err:
            traceback.print_exc()
            print("Error in cleaning Django Admin Change History: %s" % err)

    @staticmethod
    def cleanup_old_tickets(date):
        """Deletes old request tickets"""
        try:
            from web.helpdesk.models import Ticket, Queue
            try:
                queue = Queue.objects.get(slug__iexact="story")
                qs = Ticket.objects.filter(status__in=(Ticket.RESOLVED_STATUS, Ticket.CLOSED_STATUS),
                                           modified__lte=date
                                           ).exclude(queue=queue)
                qs.delete()
            except Queue.DoesNotExist:
                pass
        except Exception as err:
            traceback.print_exc()
            print("Error in cleaning tickets: %s" % err)

    @staticmethod
    def cleanup_old_informs(date):
        """Deletes old informs"""
        try:
            from world.msgs.models import Inform
            qs = Inform.objects.filter(date_sent__lte=date).exclude(important=True)
            qs.delete()
        except Exception as err:
            traceback.print_exc()
            print("Error in cleaning informs: %s" % err)

    @staticmethod
    def cleanup_old_praises():
        """Clean up old praises"""
        try:
            from world.dominion.models import PraiseOrCondemn
            qs = PraiseOrCondemn.objects.filter(week__lte=get_week() - 4)
            qs.delete()
        except Exception as err:
            traceback.print_exc()
            print("Error in cleaning praises: %s" % err)

    @staticmethod
    def cleanup_old_sessions(date):
        """Cleans up stale/expired sessions"""
        try:
            from django.contrib.sessions.models import Session
            qs = Session.objects.filter(expire_date__lte=date)
            qs.delete()
        except Exception as err:
            traceback.print_exc()
            print("Error in cleaning sessions: %s" % err)
