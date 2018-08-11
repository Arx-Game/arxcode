# -*- coding: utf-8 -*-
"""Admin models for Fashion"""
from __future__ import unicode_literals

from django.contrib import admin

from .models import FashionSnapshot


class SnapshotAdmin(admin.ModelAdmin):
    """Snapshot admin class"""
    list_display = ('id', 'fashion_model', 'fashion_item_raw_name', 'org', 'fame', 'designer')
    list_select_related = True
    raw_id_fields = ('fashion_item', 'fashion_model', 'org', 'designer')
    readonly_fields = ('item_worth',)
    search_fields = ('id', 'fashion_model__player__username', 'org__name', 'fashion_item__db_key',
                     'designer__player__username')

    @staticmethod
    def fashion_item_raw_name(obj):
        """Strips ansi from string display"""
        return obj.fashion_item and obj.fashion_item.key

    @staticmethod
    def item_worth(obj):
        """Gets the value of the item used in the calculation"""
        return obj.item_worth

admin.site.register(FashionSnapshot, SnapshotAdmin)
