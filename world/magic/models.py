from evennia.utils.idmapper.models import SharedMemoryModel
from evennia.utils.create import create_object
from django.db import models
import random
from server.utils.picker import WeightedPicker


class Affinity(SharedMemoryModel):

    name = models.CharField(max_length=20, blank=False, null=False)
    description = models.TextField(blank=True, null=True)

    class Meta:
        """Define Django meta options"""
        verbose_name_plural = "Affinities"

    def __repr__(self):
        return str(self)

    def __str__(self):
        return self.name

    def __unicode__(self):
        return unicode(str(self))


class AlchemicalMaterial(SharedMemoryModel):

    PRIMAL = 0
    ABYSSAL = 1
    ELYSIAN = 2

    MAGIC_TYPES = (
        (PRIMAL, 'Primal'),
        (ABYSSAL, 'Abyssal'),
        (ELYSIAN, 'Elysian')
    )

    name = models.CharField(max_length=40, blank=False, null=False)
    magic_type = models.PositiveSmallIntegerField(choices=MAGIC_TYPES, default=0, blank=False, null=False)
    affinity = models.ForeignKey(Affinity, blank=True, null=True, related_name='materials')
    description = models.TextField(blank=True, null=True)

    def create_instance(self):
        result = create_object(key=self.name, typeclass="world.magic.materials.MagicMaterial")
        result.db.desc = self.description
        result.db.alchemical_material = self.id

        quality_picker = WeightedPicker()
        quality_picker.add_option(6, 30)
        quality_picker.add_option(7, 30)
        quality_picker.add_option(8, 10)
        quality_picker.add_option(9, 5)
        quality_picker.add_option(10, 1)

        result.db.quality_level = quality_picker.pick()
        return result

    def __repr__(self):
        return str(self)

    def __str__(self):
        return self.name

    def __unicode__(self):
        return unicode(str(self))
