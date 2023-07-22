from abc import ABC, abstractmethod

from django.core.exceptions import ObjectDoesNotExist, ValidationError


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

    def __init__(
        self,
        attr_name=None,
        call_save=True,
        validator_func=None,
        deleted_value=None,
        allow_null=True,
        default_is_none=False,
        allow_self_argument=False,
    ):
        self.attr_name = attr_name
        self.call_save = call_save
        self.validator_func = validator_func
        self.deleted_value = deleted_value
        self.allow_null = allow_null
        self.default_is_none = default_is_none
        self.allow_self_argument = allow_self_argument

    def __set_name__(self, owner, name):
        if not self.attr_name:
            self.attr_name = name

    @abstractmethod
    def get_storage(self, instance):
        pass

    @abstractmethod
    def create_new_storage(self, instance):
        pass

    def delete_attribute(self, instance):
        try:
            storage = self.get_storage(instance)
            setattr(storage, self.attr_name, self.deleted_value)
            self.on_pre_delete(storage)
            if self.call_save:
                storage.save()
        except ObjectDoesNotExist:
            pass

    def get_storage_value_or_default(self, instance):
        """
        This tries to get a value from the storage object for our descriptor's instance.
        If it retrieves a value that is not None, it returns that. On a None, it returns
        the hardcoded default for the typeclass. If storage doesn't exist, it'll try to
        return the typeclass default, raising an AttributeError if a default is not specified.
        Originally, I had it be more forgiving, but silently failing when no default was
        specified masked errors. Now it's a requirement that a default attribute must
        exist.
        """
        try:
            val = getattr(self.get_storage(instance), self.attr_name)
            if val is None:
                return self.get_typeclass_default(instance)
            return val
        except ObjectDoesNotExist:
            return self.get_typeclass_default(instance)

    def get_typeclass_default(self, instance):
        """Gets the hardcoded default that's a property/attribute of the typeclass.
        This will raise AttributeError if the default doesn't exist.
        """
        if self.default_is_none:
            return None
        default_attr = f"default_{self.attr_name}"
        return getattr(instance.obj, default_attr)

    def __get__(self, instance, cls=None):
        if not instance:
            return self
        return self.get_storage_value_or_default(instance)

    def __set__(self, instance, value):
        if self.validator_func and not (value is None and self.allow_null):
            value = self.validator_func(value)
        if not self.allow_self_argument and value == instance.obj:
            raise ValidationError(f"You cannot set {self.attr_name} to self.")
        try:
            storage = self.get_storage(instance)
        except ObjectDoesNotExist:
            storage = self.create_new_storage(instance)
        setattr(storage, self.attr_name, value)
        if self.call_save:
            self.on_pre_save(storage, value)
            storage.save()

    def __delete__(self, instance):
        self.delete_attribute(instance)

    def on_pre_save(self, storage, value):
        """Hook for any other processing before calling save on the storage object."""

    def on_pre_delete(self, storage):
        """Hook for any other processing before deleting a field on the storage object."""


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


class DisplayNamesWrapper(StorageWrapper):
    def get_storage(self, instance):
        return instance.obj.display_names

    def create_new_storage(self, instance):
        from evennia_extensions.object_extensions.models import DisplayNames

        return DisplayNames.objects.create(objectdb=instance.obj)


class ObjectDBFieldWrapper(StorageWrapper):
    """Wraps fields already present on the object for use in the set command"""

    def get_storage(self, instance):
        return instance.obj

    def create_new_storage(self, instance):
        return instance.obj


class DescriptionWrapper(StorageWrapper):
    """Managed attribute for getting/retrieving data about object descriptions"""

    def get_storage(self, instance):
        return instance.obj.descriptions

    def create_new_storage(self, instance):
        from evennia_extensions.object_extensions.models import Descriptions

        return Descriptions.objects.create(objectdb=instance.obj)
