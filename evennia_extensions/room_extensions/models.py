from django.db import models

from evennia.utils.idmapper.models import SharedMemoryModel


class RoomDescriptions(SharedMemoryModel):
    """
    Adds descriptions specific to rooms. It holds both seasonal descriptions and
    room moods.
    """

    spring_description = models.TextField(blank=True)
    summer_description = models.TextField(blank=True)
    autumn_description = models.TextField(blank=True)
    winter_description = models.TextField(blank=True)
    room_mood = models.TextField(blank=True)
    mood_set_at = models.DateTimeField(blank=True, null=True)
    mood_set_by = models.ForeignKey(
        "objects.ObjectDB",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="set_moods",
    )
    room = models.OneToOneField(
        to="objects.ObjectDB",
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="room_descriptions",
    )

    class Meta:
        verbose_name_plural = "Room Extra Descriptions"

    def save(self, *args, **kwargs):
        """Clears out room.ndb.cached_template_desc after save if it is truthy."""
        super().save(*args, **kwargs)
        try:
            if self.room.ndb.cached_template_desc:
                del self.room.ndb.cached_template_desc
        except AttributeError:
            pass


class RoomDetail(SharedMemoryModel):
    """
    Stores a detail for a room. This is something that can be seen with the look
    command if they specify its name, returning its description.
    """

    name = models.CharField(blank=True, max_length=255)
    description = models.TextField(blank=True)
    room = models.ForeignKey(
        to="objects.ObjectDB",
        on_delete=models.CASCADE,
        related_name="room_details",
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name_plural = "Room Details"
        unique_together = ("name", "room")
