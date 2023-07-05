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
    DisplayNamesWrapper,
    ObjectDBFieldWrapper,
    DescriptionWrapper,
)
from evennia_extensions.object_extensions.validators import get_objectdb, get_room
from server.utils.arx_utils import CachedProperty


class ItemDataHandler:
    def __init__(self, obj):
        self.obj = obj

    # properties for dimensions
    size = DimensionsWrapper()
    weight = DimensionsWrapper()
    capacity = DimensionsWrapper()
    quantity = DimensionsWrapper()
    is_locked = DimensionsWrapper()
    home = ObjectDBFieldWrapper(validator_func=get_objectdb)
    location = ObjectDBFieldWrapper(validator_func=get_objectdb)
    destination = ObjectDBFieldWrapper(validator_func=get_room)

    @property
    def total_size(self):
        return self.size * self.quantity

    # properties for object existence
    put_time = PermanenceWrapper()
    deleted_time = PermanenceWrapper()
    pre_offgrid_location = PermanenceWrapper()

    # properties for object name
    false_name = DisplayNamesWrapper()
    colored_name = DisplayNamesWrapper()

    # properties that will be overridden, but we want sensible defaults
    currently_worn = False

    # properties for object description
    permanent_description = DescriptionWrapper(allow_null=False, deleted_value="")
    temporary_description = DescriptionWrapper(
        default_is_none=True, allow_null=False, deleted_value=""
    )

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
