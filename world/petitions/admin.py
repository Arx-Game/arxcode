# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.contrib import admin

from .models import (
    BrokeredSale,
    PurchasedAmount,
    PetitionParticipation,
    Petition,
    PetitionPost,
)


class PurchasedAmountInline(admin.TabularInline):
    """Inline for purchased amounts"""

    model = PurchasedAmount
    extra = 0
    raw_id_fields = ("buyer",)


class BrokeredSaleAdmin(admin.ModelAdmin):
    """Admin for BrokeredSale"""

    list_display = (
        "id",
        "owner",
        "sale_type",
        "crafting_material_type",
        "price",
        "amount",
    )
    list_filter = ("sale_type",)
    search_fields = ("id", "owner__player__username", "crafting_material_type__name")
    inlines = (PurchasedAmountInline,)
    raw_id_fields = (
        "owner",
        "crafting_material_type",
    )


class PetitionParticipantInline(admin.TabularInline):
    """Inline for participation in petitions"""

    model = PetitionParticipation
    extra = 0
    raw_id_fields = ("dompc",)


class PetitionPostInline(admin.TabularInline):
    """Inline for posts in petitions"""

    model = PetitionPost
    extra = 0
    raw_id_fields = ("dompc",)


class PetitionAdmin(admin.ModelAdmin):
    """Admin for petitions"""

    list_display = ("id", "topic", "description", "organization")
    search_fields = ("id", "topic", "description", "organization__name")
    raw_id_fields = ("organization",)
    inlines = (PetitionParticipantInline, PetitionPostInline)


admin.site.register(BrokeredSale, BrokeredSaleAdmin)
admin.site.register(Petition, PetitionAdmin)
