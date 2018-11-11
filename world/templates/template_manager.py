"""
Django manager for the Template model.
"""

from django.db import models
from django.db.models import Q


class TemplateManager(models.Manager):
    def accessible_by(self, char):
        return self.get_queryset().filter(Q(owner=char.roster.current_account) | Q(templategrantee__grantee=char.roster) | Q(access_level="OP")).distinct()

    def in_list(self, ids):
        return self.get_queryset().filter(id__in=ids).distinct()

