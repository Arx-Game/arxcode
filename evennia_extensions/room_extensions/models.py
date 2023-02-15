from django.core.exceptions import ValidationError
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel
from evennia_extensions.room_extensions.constants import (
    ZONE_TYPES,
    ROOM_TYPES,
)
from server.utils.abstract_models import NameLookupModel
from server.utils.arx_utils import CachedProperty


class RoomExtensionModel(SharedMemoryModel):
    """
    This will be where rooms are expanded.
    """

    objectdb = models.OneToOneField(
        "objects.ObjectDB", on_delete=models.CASCADE, primary_key=True
    )

    class Meta:
        abstract = True
