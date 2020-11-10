from django.db import models

from evennia.utils.idmapper.models import SharedMemoryModel


class NameLookupModel(SharedMemoryModel):
    """
    This abstract class will primarily be used for small lookup tables that can be queried once and
    then stored in memory.
    """

    _cache_set = False
    _name_to_id_map = dict()
    name = models.CharField(unique=True, max_length=150)

    class Meta:
        abstract = True

    @classmethod
    def cache_instance(cls, instance, new=False):
        """Override of cache instance with pk cast to lowercase to be case insensitive"""
        super().cache_instance(instance, new)
        cls._name_to_id_map[instance.name] = instance.id

    @classmethod
    def cached_instance_sorting_function(cls, instance):
        return instance.name.lower()

    @classmethod
    def get_cached_instance_sorting_column(cls):
        return "name"

    @classmethod
    def get_all_instances(cls):
        if cls._cache_set:
            return sorted(
                cls.get_all_cached_instances(), key=cls.cached_instance_sorting_function
            )
        # performs the query and populates the SharedMemoryModel cache
        values = list(
            cls.objects.all().order_by(cls.get_cached_instance_sorting_column())
        )
        cls._cache_set = True
        cls._name_to_id_map = {
            instance.name.lower(): instance.id for instance in values
        }
        return values

    def __str__(self):
        return self.name

    @classmethod
    def get_instance_by_name(cls, name):
        cls.get_all_instances()
        pk = cls._name_to_id_map.get(name.lower())
        return cls.get_cached_instance(pk)

    def save(self, *args, **kwargs):
        ret = super().save(*args, **kwargs)
        # store the new name to pk mapping
        type(self)._name_to_id_map[self.name.lower()] = self.id
        return ret


class NameIntegerLookupModel(NameLookupModel):
    """Tables with name/value pairs that should be sorted by those values"""

    value = models.SmallIntegerField(
        verbose_name="minimum value for this difficulty range/rating", unique=True
    )

    class Meta:
        abstract = True

    @classmethod
    def cached_instance_sorting_function(cls, instance):
        return instance.value

    @classmethod
    def get_cached_instance_sorting_column(cls):
        return "value"
