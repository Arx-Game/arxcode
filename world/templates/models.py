"""
App that handles the creation, management and assignment of Templates, which are wrappers around
any arbitrary text into a format that can be injected into any 'desc' in order to do the following:

1) Reduce database bloat by making the text 'loadable' via markup.
2) Allowing users to manage their own templates and, because it uses markup, study won't let them steal templates.
3) Allows for sharing of templates and attribution (or not as desired)

"""

from django.db import models
from evennia.typeclasses.models import SharedMemoryModel
from .template_manager import TemplateManager


class Template(SharedMemoryModel):
    """
    A model for storing raw text data (ASCII) in a manageable format. Each
    Template will be owned by an individual player account.

    There are certain design implications as it regards templates:

        1) They are immutable upon creation. (This will prevent weird issues
           when markup is parsed in validly created templates.)
        2) Use of templates MUST be parsed on ingest, for the same reasons as
           above.
        3) Templates will, by default be private.
    """

    PRIVATE = 'PR'
    RESTRICTED = 'RS'
    OPEN = 'OP'
    ACCESS_LEVELS = (
        (PRIVATE, 'PRIVATE'),
        (RESTRICTED, 'RESTRICTED'),
        (OPEN, 'OPEN')
    )

    owner = models.ForeignKey('character.PlayerAccount', related_name='templates', db_index=True)
    desc = models.TextField()

    access_level = models.CharField(max_length=2, choices=ACCESS_LEVELS, default=PRIVATE)

    attribution = models.CharField(max_length=60)
    apply_attribution = models.BooleanField(default=False)

    title = models.CharField(max_length=255)

    applied_to = models.ManyToManyField('objects.ObjectDB', blank=True)

    grantees = models.ManyToManyField('character.RosterEntry', through="TemplateGrantee", blank=True)

    objects = TemplateManager()

    def save(self, *args, **kwargs):
        super(Template, self).save(args, kwargs)
        for obj in self.applied_to.all():
            obj.ndb.cached_template_desc = None

    def __unicode__(self):
        return self.title

    def is_accessible_by(self, char):
        return self.owner == char.roster.current_account \
               or self.access_level == 'OP' \
               or self.grantees.filter(templategrantee__grantee=char.roster)

    def markup(self):
        return "[[TEMPLATE_%s]]" % self.id

    def access(self, accessing_obj, access_type='template', default=True):
        """
        Determines if another object has permission to access.
        accessing_obj - object trying to access this one
        access_type - type of access sought
        default - what to return if no lock of access_type was found
        """
        return self.locks.check(accessing_obj, access_type=access_type, default=default)


class TemplateGrantee(SharedMemoryModel):
    """
    Bridge table between templates and grantees. Will likely hold
    additional metadata about the grantee status, as the feature
    expands.
    """
    template = models.ForeignKey('Template')
    grantee = models.ForeignKey('character.RosterEntry')




