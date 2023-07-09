from django.contrib import admin
from evennia_extensions.room_extensions.models import RoomDescriptions


class RoomDescriptionsAdmin(admin.ModelAdmin):
    list_display = (
        "pk",
        "room",
    )
    raw_id_fields = ("room", "mood_set_by")
    search_fields = ("=pk", "room__db_key")


admin.site.register(RoomDescriptions, RoomDescriptionsAdmin)
