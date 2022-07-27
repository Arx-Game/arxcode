"""
Manager for character applications
"""
from django.conf import settings
from typeclasses.objects import Object
from datetime import datetime
from django.core.mail import send_mail
import string
import random
from evennia.objects.models import ObjectDB
import traceback


class AppsManager(Object):
    """
    Class to store and manage the roster
    """

    def at_object_creation(self):
        """
        Run at AppsManager creation.
        Pending and Closed are dictionaries that map character names
        to lists of applications.
        """
        # each app also contains a copy of the application number so that
        # the format is the same for both by_email and by_num dicts. Note
        # that apps by email is a list of apps for each email, while
        # apps_by_num is just one app per app_num key.
        self.db.apps_by_num = {}
        self.db.apps_manager = True
        self.db.num_apps = 0
        self.db.roster_manager_ref = None
        self.at_init()

    def at_init(self):
        """
        This is always called whenever this manager is initiated --
        that is, whenever it its typeclass is cached from memory. This
        happens on-demand first time the manager is used or activated
        in some way after being created but also after each server
        restart or reload.
        """
        super(AppsManager, self).at_init()
        roster_manager = ObjectDB.objects.get_objs_with_attr("is_roster_manager")
        if roster_manager:
            self.db.roster_manager_ref = roster_manager[0]

    def resend(self, app_num, caller):
        app = self.db.apps_by_num.get(app_num)
        if not app:
            caller.msg("AppManager error: No application by that number found.")
            return False
        return self.close_app(app_num, caller, app[7], app[8])

    def fix_email(self, app_num, caller, email):
        app = self.db.apps_by_num.get(app_num)
        if not app:
            caller.msg("AppManager error: No application by that number found.")
            return False
        app[2] = email
        return True

    def close_app(self, app_num, caller, gm_notes, approve=True):
        """
        Mark pending app as closed.
        app = [app_num, char_ob, email, date_submit, application_string, gm_ob, date_answer, gm_notes, approval, pending]
        """
        found_app = self.db.apps_by_num.get(app_num)
        if not found_app:
            caller.msg("AppManager error: No application by that number found.")
            return False
        found_app[5] = caller
        found_app[6] = datetime.today().strftime("%x %X")
        found_app[7] = gm_notes
        found_app[8] = approve
        found_app[9] = False  # marked as closed
        email = found_app[2]
        if not email:
            caller.msg(
                "AppManager error: No email found for player application. Approval cancelled."
            )
            return False
        if approve:
            # send approval email
            player = found_app[1].player_ob
            if not player:
                caller.msg(
                    "AppManager error: No player object found for character application."
                )
                return False
            message = (
                "Thank you for applying to play a character on %s. This email is to "
                % settings.SERVERNAME
            )
            message += (
                "inform you that your application to play %s has been approved.\n\n"
                % found_app[1].key.capitalize()
            )
            if gm_notes:
                message += "GM Notes: %s\n" % gm_notes
            newpass = "".join(
                random.choice(string.ascii_uppercase + string.digits) for _ in range(8)
            )
            # remove password set while testing
            if not player.is_superuser:
                player.set_password(newpass)
                try:
                    from commands.base_commands.roster import change_email, add_note

                    change_email(found_app[1].key, email, caller)
                    caller.msg(
                        "Updated email of %s in roster to be %s." % (player, email)
                    )
                    add_note(
                        found_app[1].key, "Application approved by %s" % caller, caller
                    )
                except Exception:
                    traceback.print_exc()
                    player.email = email
                    caller.msg(
                        "Failed to update email in roster. Please change manually with @chroster."
                    )
                player.save()
            message += (
                "A new password has been automatically generated for you: %s\n\n"
                % newpass
            )
            message += "After logging in for your first time, you may change the password to whatever you like "
            message += "with the @password command. Enjoy ArxMUSH!"
            try:
                msg_success = send_mail(
                    "ArxMUSH Character Application",
                    message,
                    "admin@arxmush.org",
                    [email],
                    fail_silently=False,
                )
            except Exception as err:
                traceback.print_exc()
                caller.msg("Exception encountered while trying to mail: %s" % err)
                return False
            if msg_success:
                caller.msg("Email successfully sent.")
                return True
            else:
                caller.msg("Email failed for unknown reason.")
                return False
        if not approve:
            message = "Thank you for applying to play a character on ArxMUSH. This email is to "
            message += (
                "inform you that unfortunately your application to play %s has been declined.\n\n"
                % found_app[1].key.capitalize()
            )
            message += "Please refer to the following message for context - it may be just that the GMs "
            message += "feel more information is needed in an application, or that they feel your take on "
            message += "a character's story might be more suited to a different character, possibly an original "
            message += "one of your own creation.\n\n"
            if not gm_notes:
                caller.msg("GM Notes are required in app denial.")
                return False
            message += "GM Notes: %s\n" % gm_notes
            try:
                msg_success = send_mail(
                    "ArxMUSH Character Application",
                    message,
                    "arxmush@gmail.com",
                    [email],
                    fail_silently=False,
                )
            except Exception as err:
                caller.msg("Exception encountered while trying to mail: %s" % err)
                return False
            if msg_success:
                caller.msg("Email successfully sent.")
                return True
            else:
                caller.msg("Email failed for unknown reason.")
                return False
        return True

    def view_app(self, ticket_num):
        """
        returns an application, unique for ticket_num
        """
        return self.db.apps_by_num.get(ticket_num)

    def view_all_apps_for_char(self, char_name):
        """
        all apps for char
        """
        char_name = char_name.lower()
        app_list = [
            app
            for app in self.db.apps_by_num.values()
            if app[1].key.lower() == char_name
        ]
        return app_list

    def view_all_apps(self):
        """
        All apps by character
        """
        return self.db.apps_by_num

    def view_apps_for_email(self, email):
        """
        apps for a specific email/player
        """
        email = email.lower()
        email = email.strip()
        apps = [app for app in self.db.apps_by_num.values() if app[2] == email]
        return apps

    def add_app(self, char_ob, email, app_string):
        """
        Application for a character
        app = [app_num, char_ob, email, date_submit, application_string, gm_ob, date_answer, gm_notes, approval, pending ]
        """
        email = email.strip()
        self.db.num_apps += 1
        app_num = self.db.num_apps
        date = datetime.today().strftime("%x %X")
        app = [
            app_num,
            char_ob,
            email,
            date,
            app_string,
            None,
            "None",
            "None",
            False,
            True,
        ]
        self.db.apps_by_num[app_num] = app

    def delete_app(self, caller, num):
        try:
            del self.db.apps_by_num[num]
            caller.msg("App %s deleted." % num)
        except (ValueError, KeyError):
            caller.msg("No app found for %s." % num)

    def is_apps_manager(self):
        """
        Identifier method. All managers from object typeclass
        will have some version of this for object searches.
        """
        return True
