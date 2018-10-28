from evennia.typeclasses.models import SharedMemoryModel
from django.db import models


class WeatherType(SharedMemoryModel):

    name = models.CharField('Weather Name', max_length=25)
    gm_notes = models.TextField('GM Notes', blank=True, null=True)


class WeatherEmit(SharedMemoryModel):

    weather = models.ForeignKey(WeatherType, related_name='emits')

    at_night = models.BooleanField('Night', default=True)
    at_morning = models.BooleanField('Morning', default=True)
    at_afternoon = models.BooleanField('Afternoon', default=True)
    at_evening = models.BooleanField('Evening', default=True)

    in_summer = models.BooleanField('Summer', default=True)
    in_fall = models.BooleanField('Fall', default=True)
    in_winter = models.BooleanField('Winter', default=True)
    in_spring = models.BooleanField('Spring', default=True)

    intensity_min = models.PositiveSmallIntegerField('Min Intensity', default=1)
    intensity_max = models.PositiveSmallIntegerField('Max Intensity', default=10)
    weight = models.PositiveIntegerField('Weight', default=10)
    text = models.TextField('Emit', blank=False, null=False)
    gm_notes = models.TextField('GM Notes', blank=True, null=True)
