from abc import ABC, abstractmethod

from django.core.exceptions import ObjectDoesNotExist


class StorageWrapper(ABC):
    """
    This descriptor provides a way to wrap the storage for a given
    property. attr_name specifies the name of the attribute on the storage
    object you're going to write to, while call_save specifies whether you
    need to call a save() method in the storage object after setting the value.
    validator_func allows you to have a callable that can transform/validate
    the provided value you're trying to save: while this isn't necessary for
    many basic django fields as they perform their own validation before saving,
    it can allow for queries with different arguments for setting a foreign key,
    for example. attr_name only needs to be specified if the descriptor uses
    a different name than the field.
    """

    def __init__(self, attr_name=None, call_save=True, validator_func=None):
        self.attr_name = attr_name
        self.call_save = call_save
        self.validator_func = validator_func

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
        if self.validator_func:
            value = self.validator_func(value)
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
