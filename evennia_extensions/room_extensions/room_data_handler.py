"""
Similar to the character_data_handler, this is a subclass of item_data_handler
that stores data specific to rooms. It has properties that wrap various models
to allow for the @set command to be used to set the values of those models.
"""
from evennia_extensions.object_extensions.item_data_handler import ItemDataHandler
from evennia_extensions.room_extensions.storage_wrappers import RoomDescriptionWrapper
from evennia_extensions.object_extensions.validators import get_character


class RoomDataHandler(ItemDataHandler):
    """Adds data such as seasonal descriptions and room moods to rooms."""

    spring_description = RoomDescriptionWrapper(allow_null=False, deleted_value="")
    summer_description = RoomDescriptionWrapper(allow_null=False, deleted_value="")
    autumn_description = RoomDescriptionWrapper(allow_null=False, deleted_value="")
    winter_description = RoomDescriptionWrapper(allow_null=False, deleted_value="")
    room_mood = RoomDescriptionWrapper(allow_null=False, deleted_value="")
    mood_set_by = RoomDescriptionWrapper(
        validator_func=get_character, default_is_none=True
    )
