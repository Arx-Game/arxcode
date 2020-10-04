from django.contrib import admin
from world.stat_checks.models import NaturalRollType, RollResult, StatWeight, DifficultyRating, DamageRating


class NaturalRollTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "value", "value_type", "result_shift")
    list_filter = ("value_type",)
    ordering = ("value_type", "value")


class RollResultadmin(admin.ModelAdmin):
    list_display = ("name", "value", "template")
    ordering = ("value",)


class StatWeightAdmin(admin.ModelAdmin):
    list_display = ("level", "weight", "stat_type")
    list_filter = ("stat_type",)
    ordering = ("stat_type", "level")


class DifficultyRatingAdmin(admin.ModelAdmin):
    list_display = ("name", "value")
    ordering = ("value",)


class DamageRatingAdmin(admin.ModelAdmin):
    list_display = ("name", "value", "max_value", "armor_cap")
    ordering = ("value",)


admin.site.register(NaturalRollType, NaturalRollTypeAdmin)
admin.site.register(RollResult, RollResultadmin)
admin.site.register(StatWeight, StatWeightAdmin)
admin.site.register(DifficultyRating, DifficultyRatingAdmin)
admin.site.register(DamageRating, DamageRatingAdmin)
