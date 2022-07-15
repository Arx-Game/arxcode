from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel


class Prayer(SharedMemoryModel):
    """Prayer to an invocable entity"""

    text = models.TextField("Body of the prayer")
    db_date_created = models.DateTimeField(auto_now_add=True)
    entity = models.ForeignKey(
        "InvocableEntity", on_delete=models.PROTECT, related_name="prayers"
    )
    character = models.ForeignKey(
        "objects.ObjectDB", on_delete=models.PROTECT, related_name="prayers"
    )

    @property
    def status(self):
        if self.is_answered:
            return "Answered"
        return "Unanswered"

    @property
    def is_answered(self):
        return hasattr(self, "answer") and self.answer

    def get_prayer_display(self):
        msg = f"|wPrayer to {self.entity}:|n {self.text}\n"
        if self.is_answered:
            msg += f"|wAnswer:|n {self.answer.get_prayer_answer_display()}\n"
        return msg


class InvocableEntity(SharedMemoryModel):
    """Gods and other entities people can beseech"""

    name = models.CharField(unique=True, max_length=80)
    public = models.BooleanField(default=True)
    character = models.ForeignKey(
        "objects.ObjectDB",
        null=True,
        on_delete=models.SET_NULL,
        blank=True,
        help_text="An in-game character object for this deity/being that can be invoked/worshipped",
    )

    class Meta:
        verbose_name_plural = "Invocable Entities"

    def __str__(self):
        return self.name

    @classmethod
    def get_public_names(cls):
        return ", ".join(
            cls.objects.filter(public=True)
            .order_by("name")
            .values_list("name", flat=True)
        )


class EntityAlias(SharedMemoryModel):
    """Aliases for invocable entities"""

    alias = models.CharField(unique=True, max_length=80)
    entity = models.ForeignKey(
        "InvocableEntity", on_delete=models.CASCADE, blank=True, related_name="aliases"
    )

    class Meta:
        verbose_name_plural = "Entity Aliases"


class PrayerAnswer(SharedMemoryModel):
    """Answer for a prayer"""

    prayer = models.OneToOneField(
        "Prayer", on_delete=models.PROTECT, related_name="answer"
    )
    sign = models.TextField(blank=True)
    gm_notes = models.TextField(blank=True)
    vision = models.ForeignKey(
        "character.Clue", on_delete=models.SET_NULL, null=True, blank=True
    )
    manifestation = models.ForeignKey(
        "dominion.RPEvent", on_delete=models.SET_NULL, null=True, blank=True
    )
    miracle = models.ForeignKey(
        "character.Episode", null=True, blank=True, on_delete=models.SET_NULL
    )
    db_date_created = models.DateTimeField(auto_now_add=True)

    def get_prayer_answer_display(self):
        if self.sign:
            return f"Sign: {self.sign}\n"
        if self.vision:
            return f"Vision: {self.vision} (#{self.vision_id})\n"
        if self.manifestation:
            return f"Manifestation: {self.manifestation} (#{self.manifestation_id})\n"
        if self.miracle:
            return f"Miracle: {self.miracle}"
        return "GM forgot to fill out details, make a request"


class Religion(SharedMemoryModel):
    """The different religions PCs or NPCs can have"""

    name = models.CharField(
        blank=True, unique=True, null=True, max_length=25, db_index=True
    )

    def __str__(self):
        return self.name or "Not Known"
