"""
Commands for the fashion app.
"""
from server.utils.arx_utils import ArxCommand
from server.utils.exceptions import FashionError
from world.dominion.models import Organization
from world.fashion.models import FashionSnapshot as Snapshot


class CmdFashionModel(ArxCommand):
    """
    Model items that can be worn or wielded to earn fame.
    Usage:
        model <item>=<organization>
    Leaderboards:
        model[/all]
        model/designers[/all] [<designer name>]
        model/orgs[/all] [<organization>]

    A fashion model tests their composure & performance to earn fame. The
    organization sponsoring the model and the item's designer accrues a portion
    of fame as well. Although masks may be modeled, doing so will reveal the
    model's identity in subsequent item labels and informs.
    Without the /all switch for leaderboards, only the Top 20 are displayed.
    """
    key = "model"
    aliases = ["models"]
    help_category = "social"
    leaderboard_switches = ("designers", "orgs", "models", "all")

    def model_item(self):
        """Models an item to earn prestige"""
        if not self.rhs:
            self.feedback_command_error("Please specify <item>=<organization>")
            return
        item = self.caller.search(self.lhs, location=self.caller)
        org = Organization.objects.get_public_org(self.rhs, self.caller)
        if not item or not org:
            return
        player = self.caller.player
        try:
            fame = item.model_for_fashion(player, org)
        except AttributeError:
            self.msg("%s is not an item you can model for fashion." % item)
        except FashionError as err:
            self.msg(err)
        else:
            msg = "You spend time modeling %s around Arx on behalf of %s and earn %d fame. " % (item, org, fame)
            msg += "Your prestige is now %d." % player.assets.prestige
            self.msg(msg)

    def view_leaderboards(self):
        """Views table of fashion leaders"""
        from django.db.models import Sum, Count, Avg, F, IntegerField
        pretty_headers = ["Fashion Model", "Fame", "Item Count", "Avg Item Fame"]  # default for top 20 models

        def get_queryset(manager, group_by_string, fame_divisor):
            """Teeny helper function for getting annotated queryset"""
            return (manager.values_list(group_by_string)
                           .annotate(total_fame=Sum(F('fame')/fame_divisor))
                           .annotate(Count('id'))
                           .annotate(avg=Avg(F('fame')/fame_divisor, output_field=IntegerField()))
                           .order_by('-total_fame'))

        if "designers" in self.switches:  # Designers by fame
            if self.args:
                designer = self.caller.player.search(self.args)
                if not designer:
                    return
                pretty_headers[0] = "%s Model" % designer
                designer = designer.Dominion
                qs = get_queryset(designer.designer_snapshots, 'fashion_model__player__username',
                                  Snapshot.DESIGNER_FAME_DIVISOR)
            else:
                pretty_headers[0] = "Designer"
                qs = get_queryset(Snapshot.objects, 'designer__player__username', Snapshot.DESIGNER_FAME_DIVISOR)
        elif "orgs" in self.switches:  # Fashionable orgs
            if self.args:
                org = Organization.objects.get_public_org(self.args, self.caller)
                if not org:
                    return
                pretty_headers[0] = "%s Model" % org
                qs = get_queryset(org.fashion_snapshots, 'fashion_model__player__username', Snapshot.ORG_FAME_DIVISOR)
            else:
                pretty_headers[0] = "Organization"
                qs = get_queryset(Snapshot.objects, 'org__name', Snapshot.ORG_FAME_DIVISOR)
        else:  # Models by fame
            qs = get_queryset(Snapshot.objects, 'fashion_model__player__username', 1)
        qs = qs[:20] if "all" not in self.switches else qs
        if not qs:
            self.msg("Nothing was found.")
            return
        from server.utils.prettytable import PrettyTable
        table = PrettyTable(pretty_headers)
        for q in qs:

            # for lowercase names, we'll capitalize them
            if q[0] == q[0].lower():
                q = list(q)
                q[0] = q[0].capitalize()
            table.add_row(q)
        self.msg(str(table))

    def func(self):
        """Execute model command"""
        if self.args and not self.switches:
            self.model_item()
        elif not self.switches or self.check_switches(self.leaderboard_switches):
            self.view_leaderboards()
        else:
            self.feedback_invalid_switch()


class CmdAdminFashion(ArxCommand):
    """
    Admin commands for modeling.
    Usage:
        @admin_fashion <item ID#>
        @admin_fashion/delete <snapshot ID#>

    Shows the #IDs of model snapshot(s) that were generated whenever the
    item was modeled. /Delete will remove all status awarded, refund AP,
    and delete the snapshot, effectively reversing the model command.
    """
    key = "@admin_fashion"
    help_category = "admin"
    locks = "cmd:perm(Wizards)"

    def display_item_snapshots(self):
        """displays snapshots"""
        from evennia.objects.models import ObjectDB
        try:
            item = ObjectDB.objects.get(id=self.args)
        except ObjectDB.DoesNotExist:
            self.msg("No object found for ID %s." % self.args)
            return
        snapshots = item.fashion_snapshots.all()
        if not snapshots:
            self.msg("No snapshots exist for %s." % item)
            return
        self.msg("%s model snapshots: %s" % (item, ", ".join(ob.id + " by " + ob.fashion_model for ob in snapshots)))

    def reverse_snapshot(self):
        """reverses snapshots"""
        try:
            snapshot = Snapshot.objects.get(id=self.args)
        except Snapshot.DoesNotExist:
            self.msg("No snapshot with ID# %s." % self.args)
            return
        snapshot.apply_fame(reverse=True)
        snapshot.fashion_model.player.pay_action_points(-snapshot.fashion_item.fashion_ap_cost)
        self.msg("Snapshot #%s fame/ap has been reversed. Deleting it." % snapshot.id)
        snapshot.delete()

    def func(self):
        """Execute command"""
        if not self.args or not self.args.isdigit():
            self.feedback_command_error("Requires an ID #.")
        elif not self.switches:
            self.display_item_snapshots()
        elif "delete" in self.switches:
            self.reverse_snapshot()
        else:
            self.feedback_invalid_switch()
