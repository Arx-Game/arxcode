# -*- coding: utf-8 -*-
"""
Admin classes for Conditions app
"""
from __future__ import unicode_literals

from django.contrib import admin

from .models import RollModifier, EffectTrigger


class RollModifierAdmin(admin.ModelAdmin):
    """Admin class for RollModifier"""
    list_display = ('id', 'object', 'check', 'value')
    search_fields = ('id', 'object__db_key')
    list_filter = ('check',)
    save_as = True
    raw_id_fields = ('object',)


class EffectTriggerAdmin(admin.ModelAdmin):
    """Admin class for EffectTrigger"""
    list_display = ('id', 'object', 'trigger_event', 'conditional_check', 'room_msg')
    search_fields = ('id', 'object__db_key')
    list_filter = ('trigger_event', 'conditional_check')
    save_as = True
    raw_id_fields = ('object',)


# Register your models here.
admin.site.register(RollModifier, RollModifierAdmin)
admin.site.register(EffectTrigger, EffectTriggerAdmin)