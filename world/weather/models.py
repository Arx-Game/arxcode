from evennia.typeclasses.models import SharedMemoryModel
from django.db import models


class WeatherType(SharedMemoryModel):

    name = models.CharField('Weather Name', max_length=25)
    gm_notes = models.TextField('GM Notes', blank=True, null=True)
    automated = models.BooleanField('Automated', help_text="Should this weather ever occur automatically?",
                                    default=True)
    multiplier = models.IntegerField('Weight Multiplier', default=1,
                                     help_text='Multiply weather emit weights by this value when picking a weather; '
                                               'higher values make the weather more likely.')

    def __repr__(self):
        return self.name

    def __unicode__(self):
        return self.name

    def __str__(self):
        return self.name

    @property
    def emit_count(self):
        return self.emits.count()

    @property
    def total_weight(self):
        result = 0
        for emit in self.emits.all():
            result += emit.weight * self.multiplier
        return result


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
