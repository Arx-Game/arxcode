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
