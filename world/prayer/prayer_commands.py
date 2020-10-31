"""
You gotta pray just to make it today. Praaaaay. Praaaaaay.
"""
from django.db.models import Q

from datetime import datetime, timedelta

from commands.base import ArxCommand
from world.prayer.models import Prayer, InvocableEntity
from server.utils.prettytable import PrettyTable
from server.utils.arx_utils import inform_staff


class CmdPray(ArxCommand):
    """
    Prayer
        Usage:
            pray
            pray <deity>=<stuff>
            pray/view <prayer #>
            pray/forget <prayer #>

    A character can attempt to pray for a response 3 times per week, and have a maximum of 13 active unanswered prayers.
    Note there is no mechanical benefit to praying multiple times, and this is for a story purpose of recording
    characters' prayers and conversations with the supernatural.
    """

    key = "pray"
    locks = "cmd:all()"
    help_category = "story"
    max_unanswered_prayers = 13
    max_prayers_per_week = 3

    def func(self):
        """Where the praying happens. Amen."""
        try:
            if not self.rhs and not self.switches:
                return self.do_display()
            if "view" in self.switches:
                return self.view_prayer()
            if "forget" in self.switches:
                return self.forget_prayer()
            return self.do_pray()
        except self.error_class as err:
            self.msg(err)

    def do_display(self):
        """Whatever text you want to display to characters when they just type 'pray' here."""
        prayers = self.caller.prayers.all()
        if self.rhs:
            prayers = prayers.filter(entity__name__iexact=self.rhs)
        # list prayers
        table = PrettyTable(["{w#", "{wEntity", "|wStatus|n", "{wDate|n", "|wPrayer|n"])
        for prayer in prayers:
            table.add_row(
                [prayer.id, prayer.entity, prayer.status, prayer.db_date_created.strftime("%x"),
                 prayer.text[:30]]
            )
        self.msg(str(table))

    def do_pray(self):
        """Makes a prayer"""
        if not self.rhs:
            raise self.error_class(
                "You must specify who you are praying to and a prayer."
            )
        matches = InvocableEntity.objects.filter(
            Q(name__iexact=self.lhs) | Q(aliases__alias__iexact=self.lhs)
        )
        if not matches:
            raise self.error_class(
                f"No entity by the name {self.lhs}. Available: {InvocableEntity.get_public_names()}"
            )
        if len(matches) > 1:
            raise self.error_class(f"Too many matches for {self.lhs}.")
        entity = matches[0]
        # create prayer
        self.check_max_unanswered_prayers()
        self.check_max_prayers_this_week()
        Prayer.objects.create(character=self.caller, entity=entity, text=self.rhs)
        self.msg(f"You pray to {entity}.")
        inform_staff(f"New prayer by {self.caller} to {entity}: {self.rhs}")

    def check_max_unanswered_prayers(self):
        num = self.caller.prayers.filter(answer__isnull=True).count()
        if num > self.max_unanswered_prayers:
            raise self.error_class(
                f"You can only have {self.max_unanswered_prayers} prayers. Try forgetting some."
            )

    def check_max_prayers_this_week(self):
        last_week = datetime.now() - timedelta(days=7)
        num_prayers = self.caller.prayers.filter(db_date_created__gt=last_week).count()
        if num_prayers > self.max_prayers_per_week:
            raise self.error_class(
                f"Entities will only hear {self.max_prayers_per_week} prayers per week."
            )

    def get_prayer(self):
        try:
            return self.caller.prayers.get(id=self.lhs)
        except (Prayer.DoesNotExist, ValueError, TypeError):
            raise self.error_class("No prayer by that ID.")

    def view_prayer(self):
        prayer = self.get_prayer()
        self.msg(prayer.get_prayer_display())

    def forget_prayer(self):
        prayer = self.get_prayer()
        if prayer.is_answered:
            raise self.error_class("You cannot forget an answered prayer.")
        prayer.delete()
        self.msg("You give up hope on the prayer being answered.")


class CmdGMPray(ArxCommand):
    """
    gmpray - display recent, unanswered prayers
    gmpray <entity> - display unanswered prayers for an entity
    gmpray <player> - displays unanswered prayers for a player
    """

    key = "gmpray"
    aliases = ["gm_pray", "gmprayer", "gm_prayer"]
    locks = "cmd:perm(Wizards)"
    help_category = "GMing"

    def func(self):
        """Where prayers are answered. 'No,' says God."""
        pass
