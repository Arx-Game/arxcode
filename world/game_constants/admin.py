from django.contrib import admin
from world.game_constants.models import IntegerGameConstant


class IntegerGameConstantAdmin(admin.ModelAdmin):
    list_display = ("id", "value")
    # we'll only set ID/create new values in a migration. ID should only be set in version control
    readonly_fields = ("id",)


admin.site.register(IntegerGameConstant, IntegerGameConstantAdmin)
