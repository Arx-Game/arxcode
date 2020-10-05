#
# This makes the news model visible in the admin web interface
# so one can add/edit/delete news items etc.
#

from django.contrib import admin
from .models import NewsTopic, NewsEntry
from evennia.accounts.models import AccountDB


class NewsTopicAdmin(admin.ModelAdmin):
    list_display = ("name", "icon")


admin.site.register(NewsTopic, NewsTopicAdmin)


class NewsEntryAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "topic", "date_posted")
    list_filter = ("topic",)
    search_fields = ["title"]

    def formfield_for_foreignkey(self, db_field, request=None, **kwargs):
        if db_field.name == "author":
            kwargs["queryset"] = AccountDB.objects.filter(is_staff=True).order_by(
                "username"
            )
        return super(NewsEntryAdmin, self).formfield_for_foreignkey(
            db_field, request, **kwargs
        )


admin.site.register(NewsEntry, NewsEntryAdmin)
