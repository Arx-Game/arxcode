"""
Similar to the character_data_handler, this is a subclass of item_data_handler
that stores data specific to rooms. It has properties that wrap various models
to allow for the @set command to be used to set the values of those models.
"""
from evennia_extensions.object_extensions.item_data_handler import ItemDataHandler
from evennia_extensions.room_extensions.storage_wrappers import RoomDescriptionWrapper
from evennia_extensions.object_extensions.validators import get_character
from server.utils.arx_utils import CachedProperty


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

    @CachedProperty
    def details(self):
        """Returns dict of our object's room_details"""
        return {
            detail.name: detail.description for detail in self.obj.room_details.all()
        }

    def add_detail(self, name, description):
        """
        Adds a detail to our object's room_details. We'll use update_or_create
        to override existing details with the same name.
        """
        self.obj.room_details.update_or_create(
            name=name, defaults={"description": description}
        )
        self.details[name] = description

    def remove_detail(self, name):
        """Removes a detail from our object's room_details."""
        self.obj.room_details.filter(name=name).delete()
        # clear cache
        del self.details
