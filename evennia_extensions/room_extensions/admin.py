from django.contrib import admin
from evennia_extensions.room_extensions.models import RoomDescriptions, RoomDetail


class RoomDescriptionsAdmin(admin.ModelAdmin):
    list_display = (
        "pk",
        "room",
    )
    raw_id_fields = ("room", "mood_set_by")
    search_fields = ("=pk", "room__db_key")


class RoomDetailAdmin(admin.ModelAdmin):
    list_display = (
        "pk",
        "room",
        "name",
    )
    raw_id_fields = ("room",)
    search_fields = ("=pk", "room__db_key", "name")


admin.site.register(RoomDescriptions, RoomDescriptionsAdmin)
admin.site.register(RoomDetail, RoomDetailAdmin)
