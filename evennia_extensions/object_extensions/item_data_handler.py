"""
This serves as an abstraction layer to hide away details of storing and
retrieving data associated with a given in-game object. It'll have all
the attributes defined as properties that a given Typeclass will need,
routing the getter/setters of those properties to the underlying models
where the data is stored.
"""
from evennia_extensions.object_extensions.storage_wrappers import (
    DimensionsWrapper,
    PermanenceWrapper,
)
from server.utils.arx_utils import CachedProperty


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

    @CachedProperty
    def translation(self):
        """
        Returns cached dict of our translated text
        """
        return {ob.language: ob.description for ob in self.obj.translations.all()}

    def add_translation(self, language, description):
        """
        Adds a translated text to this crafted object
        Args:
            language (str): The name of the language
            description (str): The translated text
        """
        # get or create will prevent an exact duplicate from occurring
        self.obj.translations.get_or_create(language=language, description=description)
        # clear the cache
        del self.translation
