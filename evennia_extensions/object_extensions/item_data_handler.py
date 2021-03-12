"""
This serves as an abstraction layer to hide away details of storing and
retrieving data associated with a given in-game object. It'll have all
the attributes defined as properties that a given Typeclass will need,
routing the getter/setters of those properties to the underlying models
where the data is stored.
"""
from abc import ABC, abstractmethod
from django.core.exceptions import ObjectDoesNotExist


class StorageWrapper(ABC):
    """
    This descriptor provides a way to wrap the storage for a given
    property.
    """

    def __init__(self, attr_name=None, call_save=True):
        self.attr_name = attr_name
        self.call_save = call_save

    def __set_name__(self, owner, name):
        if not self.attr_name:
            self.attr_name = name

    @abstractmethod
    def get_storage(self, instance):
        pass

    @abstractmethod
    def create_new_storage(self, instance):
        pass

    def get_storage_value_or_default(self, instance):
        """
        This tries to get a value from the storage object for our descriptor's instance.
        If it retrieves a value that is not None, it returns that. On a None, it returns
        the hardcoded default for the typeclass. If storage doesn't exist, it'll try to
        return the typeclass default, or create the storage object and return its field
        default if there is not default attr specified on the typeclass.
        """
        try:
            val = getattr(self.get_storage(instance), self.attr_name)
            if val is None:
                return self.get_typeclass_default(instance)
            return val
        except ObjectDoesNotExist:
            return self.get_typeclass_default_or_create_storage(instance)

    def get_typeclass_default(self, instance):
        """Gets the hardcoded default that's a property/attribute of the typeclass.
        This will raise AttributeError if the default doesn't exist.
        """
        default_attr = f"default_{self.attr_name}"
        return getattr(instance.obj, default_attr)

    def get_typeclass_default_or_create_storage(self, instance):
        """
        We'll try to get a default value for the attribute on the typeclass.
        If no default_ value is defined for the field in the typeclass,
        we'll create new storage and get the default value for the newly created
        model instance field.
        """
        try:
            return self.get_typeclass_default(instance)
        except AttributeError:
            return getattr(self.create_new_storage(instance), self.attr_name)

    def __get__(self, instance, cls=None):
        if not instance:
            return self
        return self.get_storage_value_or_default(instance)

    def __set__(self, instance, value):
        try:
            storage = self.get_storage(instance)
        except ObjectDoesNotExist:
            storage = self.create_new_storage(instance)
        setattr(storage, self.attr_name, value)
        if self.call_save:
            storage.save()


class DimensionsWrapper(StorageWrapper):
    """Managed attribute for getting/retrieving data about object dimensions."""

    def get_storage(self, instance):
        return instance.obj.dimensions

    def create_new_storage(self, instance):
        from evennia_extensions.object_extensions.models import Dimensions

        return Dimensions.objects.create(objectdb=instance.obj)


class PermanenceWrapper(StorageWrapper):
    """Managed attribute for getting/retrieving data about object permanence"""

    def get_storage(self, instance):
        return instance.obj.permanence

    def create_new_storage(self, instance):
        from evennia_extensions.object_extensions.models import Permanence

        return Permanence.objects.create(objectdb=instance.obj)


class ItemDataHandler:
    def __init__(self, obj):
        self.obj = obj

    size = DimensionsWrapper()
    weight = DimensionsWrapper()
    capacity = DimensionsWrapper()
    quantity = DimensionsWrapper()

    @property
    def total_size(self):
        return self.size * self.quantity

    put_time = PermanenceWrapper()
    deleted_time = PermanenceWrapper()

    # properties that will be overridden, but we want sensible defaults
    currently_worn = False
    sheathed_by = None
