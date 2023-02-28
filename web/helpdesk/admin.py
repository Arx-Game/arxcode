from django.contrib import admin
from web.helpdesk.models import Queue, Ticket, KBCategory, KBItem, FollowUp


class QueueAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "email_address", "locale")


class FollowupInline(admin.StackedInline):
    model = FollowUp
    extra = 0
    readonly_fields = ("user",)


class TicketAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "status",
        "assigned_to",
        "submitting_player",
        "queue",
    )
    date_hierarchy = "db_date_created"
    list_filter = ("status", "queue", "priority")
    search_fields = (
        "id",
        "title",
        "assigned_to__username",
        "submitting_player__username",
        "description",
        "resolution",
    )
    raw_id_fields = ("assigned_to", "submitting_player", "submitting_room")
    inlines = (FollowupInline,)


class KBItemAdmin(admin.ModelAdmin):
    search_fields = ("title", "question", "answer")
    list_display = (
        "category",
        "title",
        "last_updated",
    )
    list_display_links = ("title",)
    list_filter = ("category",)
    filter_horizontal = ("search_tags",)


class KBCategoryAdmin(admin.ModelAdmin):
    search_fields = ("title", "slug", "description")
    list_display = ("title", "description", "parent")
    filter_horizontal = ("search_tags",)


admin.site.register(Ticket, TicketAdmin)
admin.site.register(Queue, QueueAdmin)
admin.site.register(KBCategory, KBCategoryAdmin)
admin.site.register(KBItem, KBItemAdmin)
