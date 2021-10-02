from django.contrib import admin
from world.stat_checks.models import (
    NaturalRollType,
    RollResult,
    StatWeight,
    DifficultyRating,
    DamageRating,
    StatCheck,
    StatCombination,
    StatCheckOutcome,
    CheckCondition,
    CheckDifficultyRule,
    TraitsInCombination,
    CheckRank,
    DifficultyTable,
    DifficultyTableResultRange,
)


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
    list_display = ("name", "value", "max_value", "armor_percentage")
    ordering = ("value",)


class CheckDifficultyRuleInline(admin.TabularInline):
    extra = 0
    model = CheckDifficultyRule


class StatCheckOutcomeInline(admin.TabularInline):
    extra = 0
    model = StatCheckOutcome


class StatCheckAdmin(admin.ModelAdmin):
    list_display = ("name", "description")
    inlines = (CheckDifficultyRuleInline, StatCheckOutcomeInline)


class CheckConditionAdmin(admin.ModelAdmin):
    list_display = ("condition_type", "value")
    inlines = (CheckDifficultyRuleInline,)


class TraitsInCombinationInline(admin.TabularInline):
    extra = 0
    model = TraitsInCombination


class StatCombinationAdmin(admin.ModelAdmin):
    list_display = ("combination", "checks")
    inlines = (TraitsInCombinationInline,)
    readonly_fields = ("checks",)

    @staticmethod
    def combination(obj):
        return str(obj)

    @staticmethod
    def checks(obj):
        return ", ".join(str(ob) for ob in obj.cached_stat_checks)


class CheckRankAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "value")
    ordering = ("value",)


class DiffRangeInline(admin.StackedInline):
    model = DifficultyTableResultRange
    extra = 0


class DifficultyTableAdmin(admin.ModelAdmin):
    list_display = ("name",)
    inlines = (DiffRangeInline,)


admin.site.register(NaturalRollType, NaturalRollTypeAdmin)
admin.site.register(RollResult, RollResultadmin)
admin.site.register(StatWeight, StatWeightAdmin)
admin.site.register(DifficultyRating, DifficultyRatingAdmin)
admin.site.register(DamageRating, DamageRatingAdmin)
admin.site.register(StatCheck, StatCheckAdmin)
admin.site.register(CheckCondition, CheckConditionAdmin)
admin.site.register(StatCombination, StatCombinationAdmin)
admin.site.register(CheckRank, CheckRankAdmin)
admin.site.register(DifficultyTable, DifficultyTableAdmin)
