from django.db.models import Q, Manager


class OrganizationManager(Manager):
    def get_public_org(self, org_name, caller):
        org = None
        try:
            try:
                name_or_id = Q(id=int(org_name))
            except (ValueError, TypeError):
                name_or_id = Q(name__iexact=org_name)
            org = self.get(name_or_id & Q(secret=False))
        except (self.model.DoesNotExist):
            caller.msg("Could not find public org '%s'." % org_name)
        except self.model.MultipleObjectsReturned:
            orgs = self.filter(Q(name__iexact=org_name) & Q(secret=False))
            caller.msg("Too many options: %s" % ", ".join(ob for ob in orgs))
        return org


class CrisisManager(Manager):
    """Methods for accessing different Plot collections or viewing groups of Plots."""

    def viewable_by_player(self, player):
        if not player or not player.is_authenticated():
            return self.filter(public=True)
        if player.check_permstring("builders") or player.is_staff:
            qs = self.all()
        else:
            from .models import PCPlotInvolvement
            crises = Q(usage=self.model.CRISIS)
            # crisis is viewable if it's public, or they have the required clue
            crises &= Q(Q(public=True) | Q(required_clue__in=player.roster.clues.all()))
            plots = Q(usage__in=[self.model.PLAYER_RUN_PLOT, self.model.GM_PLOT])
            # plots are viewable only if they're a member
            plots &= Q(dompc_involvement__activity_status__lte=PCPlotInvolvement.INVITED)
            plots &= Q(dompc_involvement__dompc__player=player)
            qs = self.filter(crises | plots).distinct()
        return qs

    def view_plots_table(self, old=False, only_open_tickets=False, only_recruiting=False):
        """Returns an EvTable chock full of spicy Plots."""
        from evennia.utils.evtable import EvTable
        qs = self.filter(resolved=old).exclude(Q(usage=self.model.CRISIS) | Q(parent_plot__isnull=False)).distinct()
        if only_open_tickets:
            from web.helpdesk.models import Ticket
            qs = qs.filter(tickets__status=Ticket.OPEN_STATUS)
        if only_recruiting:
            from .models import PCPlotInvolvement
            qs = qs.filter(Q(dompc_involvement__activity_status=PCPlotInvolvement.ACTIVE)
                           & Q(dompc_involvement__admin_status__gte=PCPlotInvolvement.RECRUITER)
                           & ~Q(dompc_involvement__recruiter_story="")).distinct()
        alt_header = "Resolved " if old else ""
        table = EvTable("|w#|n", "|w%sPlot (owner)|n" % alt_header, "|wSummary|n", width=78, border="cells")
        for plot in qs:
            def get_plot_name_and_owner(plotmato):
                owner = (" (%s)" % plotmato.first_owner) if plotmato.first_owner else ""
                return "%s%s" % (str(plotmato), owner)

            def add_subplots_rows(subplot, color_num):
                sub_name = get_plot_name_and_owner(subplot)
                table.add_row("|%s35%s|n" % (color_num, subplot.id), sub_name, subplot.headline)
                color_num += 1
                if color_num > 5:
                    color_num = 0
                for subplotmato in subplot.subplots.filter(resolved=old):
                    add_subplots_rows(subplotmato, color_num)

            plot_name = get_plot_name_and_owner(plot)
            table.add_row(plot.id, plot_name, plot.headline)
            for subploterino in plot.subplots.filter(resolved=old):
                add_subplots_rows(subploterino, color_num=0)
        table.reformat_column(0, width=7)
        table.reformat_column(1, width=25)
        table.reformat_column(2, width=46)
        return table


class LandManager(Manager):
    def land_by_coord(self, x, y):
        qs = self.filter(Q(x_coord=x) & Q(y_coord=y))
        return qs
