# -*- coding: utf-8 -*-
"""
Admin classes for Conditions app
"""
from __future__ import unicode_literals

from django.contrib import admin

from .models import (
    RollModifier,
    EffectTrigger,
    Wound,
    CharacterHealthStatus,
    RecoveryRunner,
    TreatmentAttempt,
)


class RollModifierAdmin(admin.ModelAdmin):
    """Admin class for RollModifier"""

    list_display = ("id", "object", "name", "stat", "skill", "value", "check")
    search_fields = ("id", "object__db_key")
    list_filter = ("check", "modifier_type")
    save_as = True
    raw_id_fields = ("object",)


class EffectTriggerAdmin(admin.ModelAdmin):
    """Admin class for EffectTrigger"""

    list_display = ("id", "object", "trigger_event", "conditional_check", "room_msg")
    search_fields = ("id", "object__db_key")
    list_filter = ("trigger_event", "conditional_check")
    save_as = True
    raw_id_fields = ("object",)


class CharacterWoundsInline(admin.TabularInline):
    model = Wound
    extra = 0


class TreatmentAttemptInline(admin.TabularInline):
    model = TreatmentAttempt
    extra = 0
    raw_id_fields = ("healer",)


class CharacterHealthStatusAdmin(admin.ModelAdmin):
    """Admin class for Health Status"""

    list_display = (
        "character_id",
        "character_name",
        "damage",
        "consciousness",
        "is_dead",
    )
    inlines = (CharacterWoundsInline, TreatmentAttemptInline)
    raw_id_fields = ("character",)
    # these are read-only until/unless we change django-admin behavior to do all the necessary stuff on changes
    readonly_fields = ("consciousness", "is_dead")
    list_filter = ("consciousness", "is_dead")
    search_fields = ("character__db_key__iexact",)


class RecoveryRunnerAdmin(admin.ModelAdmin):
    list_display = (
        "script",
        "recovery_last_run",
        "revive_last_run",
        "recovery_interval",
        "revive_interval",
    )


# Register your models here.
admin.site.register(RollModifier, RollModifierAdmin)
admin.site.register(EffectTrigger, EffectTriggerAdmin)
admin.site.register(CharacterHealthStatus, CharacterHealthStatusAdmin)
admin.site.register(RecoveryRunner)
