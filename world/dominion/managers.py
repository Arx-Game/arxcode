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
    def viewable_by_player(self, player):
        if not player or not player.is_authenticated():
            return self.filter(public=True)
        if player.check_permstring("builders") or player.is_staff:
            qs = self.all()
        else:
            qs = self.filter(Q(public=True) | Q(required_clue__discoveries__in=player.roster.finished_clues))
        return qs
