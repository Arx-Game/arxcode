from django.contrib import admin
from .models import *


class AffinityAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')


class AlchemicalMaterialAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'magic_type', 'affinity')


admin.site.register(Affinity, AffinityAdmin)
admin.site.register(AlchemicalMaterial, AlchemicalMaterialAdmin)
