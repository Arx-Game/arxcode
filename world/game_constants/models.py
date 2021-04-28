from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel
from world.game_constants.managers import IntegerGameConstantQueryset


class IntegerGameConstant(SharedMemoryModel):
    id = models.CharField(primary_key=True, max_length=255)
    value = models.IntegerField()

    objects = IntegerGameConstantQueryset.as_manager()

    def __str__(self):
        return self.id
