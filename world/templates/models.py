"""
App that handles the creation, management and assignment of Templates, which are wrappers around
any arbitrary text into a format that can be injected into any 'desc' in order to do the following:

1) Reduce database bloat by making the text 'loadable' via markup.
2) Allowing users to manage their own templates and, because it uses markup, study won't let them steal templates.
3) Allows for sharing of templates and attribution (or not as desired)

"""

from django.db import models
from evennia.typeclasses.models import SharedMemoryModel
from server.utils.arx_utils import CachedProperty
from .exceptions import AlreadySignedError
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

    PRIVATE = "PR"
    RESTRICTED = "RS"
    OPEN = "OP"
    ACCESS_LEVELS = ((PRIVATE, "PRIVATE"), (RESTRICTED, "RESTRICTED"), (OPEN, "OPEN"))

    owner = models.ForeignKey(
        "character.PlayerAccount",
        related_name="templates",
        db_index=True,
        on_delete=models.CASCADE,
    )
    desc = models.TextField()

    access_level = models.CharField(
        max_length=2, choices=ACCESS_LEVELS, default=PRIVATE
    )

    attribution = models.CharField(max_length=60)
    apply_attribution = models.BooleanField(default=False)

    title = models.CharField(max_length=255)

    applied_to = models.ManyToManyField("objects.ObjectDB", blank=True)

    grantees = models.ManyToManyField(
        "character.RosterEntry", through="TemplateGrantee", blank=True
    )

    objects = TemplateManager()

    def save(self, *args, **kwargs):
        super(Template, self).save(args, kwargs)
        for obj in self.applied_to.all():
            obj.ndb.cached_template_desc = None

    def __str__(self):
        return self.title

    def is_accessible_by(self, char):
        return (
            self.owner == char.roster.current_account
            or self.access_level == "OP"
            or self.grantees.filter(templategrantee__grantee=char.roster)
        )

    def in_use(self):
        return self.applied_to.count() > 0

    def markup(self):
        return "[[TEMPLATE_%s]]" % self.id

    def access(self, accessing_obj, access_type="template", default=True):
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

    template = models.ForeignKey("Template", on_delete=models.CASCADE)
    grantee = models.ForeignKey("character.RosterEntry", on_delete=models.CASCADE)


class WrittenWork(SharedMemoryModel):
    """
    This specifically describes an in-game document that can exist as copies
    in books. A WrittenWork may frequently be a chapter or only a single work
    contained inside a book (a Readable typeclass), which may be by different
    authors.
    """

    owner = models.ForeignKey(
        "character.PlayerAccount",
        related_name="written_works",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )
    author = models.ForeignKey(
        "objects.ObjectDB",
        related_name="authored_works",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )
    title = models.CharField(max_length=255)
    colored_title = models.TextField(blank=True)
    body = models.TextField()
    books = models.ManyToManyField(
        "objects.ObjectDB",
        related_name="contained_written_works",
        through="BookChapter",
    )
    language = models.CharField(blank=True, max_length=255)

    class Meta:
        verbose_name_plural = "Written Works"

    def __str__(self):
        return self.title

    @property
    def pretty_title(self):
        return self.colored_title or self.title


class BookChapter(SharedMemoryModel):
    written_work = models.ForeignKey("WrittenWork", on_delete=models.CASCADE)
    objectdb = models.ForeignKey(
        "objects.ObjectDB", related_name="book_chapters", on_delete=models.CASCADE
    )
    number = models.PositiveSmallIntegerField(default=1)
    signers = models.ManyToManyField(
        "objects.ObjectDB", related_name="signed_chapters", through="ChapterSignature"
    )

    class Meta:
        verbose_name_plural = "Book Chapters"
        unique_together = (
            ("objectdb", "written_work"),
            ("objectdb", "number"),
        )
        ordering = ("number",)

    def __str__(self):
        return f"Chapter {self.number}: {self.written_work}"

    @CachedProperty
    def cached_signatures(self):
        return self.signatures.all()

    def add_signature(self, signer):
        if signer in self.signers.all():
            raise AlreadySignedError("You have already signed this document.")
        self.signatures.create(signer=signer)
        del self.cached_signatures

    def get_chapter_text(self):
        msg = self.written_work.body
        if self.cached_signatures:
            msg += "\n" + ", ".join(ob.signer.db_key for ob in self.cached_signatures)
        return msg


class ChapterSignature(SharedMemoryModel):
    """
    Making a through model because probably will add the ability to forge
    signatures or sign as an alias at some point.
    """

    book_chapter = models.ForeignKey(
        "BookChapter", related_name="signatures", on_delete=models.CASCADE
    )
    signer = models.ForeignKey(
        "objects.ObjectDB", related_name="signatures", on_delete=models.CASCADE
    )
