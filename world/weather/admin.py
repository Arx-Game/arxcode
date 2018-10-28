from django.contrib import admin
from models import WeatherEmit, WeatherType


class WeatherEmitInline(admin.StackedInline):
    model = WeatherEmit
    extra = 0
    fieldsets = [(None, {'fields': [('text')]}),
                 ('Details', {'fields': [('weather', 'intensity_min', 'intensity_max', 'weight', 'gm_notes')], 'classes': ['collapse']}),
                 ('Seasons', {'fields': [('in_summer', 'in_fall', 'in_winter', 'in_spring')], 'classes': ['collapse']}),
                 ('Times', {'fields': [('at_morning', 'at_afternoon', 'at_evening', 'at_night')], 'classes': ['collapse']})]


class WeatherTypeAdmin(admin.ModelAdmin):
    model = WeatherType
    list_display = ('id', 'name', 'gm_notes')
    extra = 0
    inlines = (WeatherEmitInline,)


admin.site.register(WeatherType, WeatherTypeAdmin)
