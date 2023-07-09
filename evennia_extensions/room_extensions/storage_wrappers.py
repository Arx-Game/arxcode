from datetime import datetime

from evennia_extensions.object_extensions.storage_wrappers import StorageWrapper


class RoomDescriptionWrapper(StorageWrapper):
    def get_storage(self, instance):
        return instance.obj.room_descriptions

    def create_new_storage(self, instance):
        from evennia_extensions.room_extensions.models import RoomDescriptions

        return RoomDescriptions.objects.create(room=instance.obj)

    def on_pre_save(self, storage, value):
        """If our self.attr_name is room_mood, then we set the timestamp. We
        don't need to save - that's handled after this hook is called."""

        if self.attr_name == "room_mood":
            storage.room_mood_set_at = datetime.now()

    def on_pre_delete(self, storage):
        """If our self.attr_name is room_mood, then we clear the timestamp
        and our room_mood_set_by."""

        if self.attr_name == "room_mood":
            storage.room_mood_set_at = None
            storage.room_mood_set_by = None
