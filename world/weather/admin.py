from django.contrib import admin
from models import WeatherEmit, WeatherType


class WeatherEmitInline(admin.StackedInline):
    model = WeatherEmit
    extra = 0
    fieldsets = [(None, {'fields': [('text',)]}),
                 ('Details', {'fields': [('intensity_min', 'intensity_max', 'weight', 'gm_notes')],
                              'classes': ['collapse']}),
                 ('Seasons', {'fields': [('in_summer', 'in_fall', 'in_winter', 'in_spring')],
                              'classes': ['collapse']}),
                 ('Times', {'fields': [('at_morning', 'at_afternoon', 'at_evening', 'at_night')],
                            'classes': ['collapse']})]


class WeatherTypeAdmin(admin.ModelAdmin):
    model = WeatherType
    list_display = ('id', 'name', 'gm_notes', 'emit_count', 'automated')
    ordering = ('id',)
    extra = 0
    inlines = (WeatherEmitInline,)


class WeatherEmitAdmin(admin.ModelAdmin):
    model = WeatherEmit
    list_display = ('id', 'weather', 'text', 'in_summer', 'in_fall', 'in_winter', 'in_spring')
    ordering = ('id',)
    extra = 0
    fieldsets = [(None, {'fields': [('weather', 'text')]}),
                 ('Details', {'fields': [('intensity_min', 'intensity_max', 'weight', 'gm_notes')]}),
                 ('Seasons', {'fields': [('in_summer', 'in_fall', 'in_winter', 'in_spring')]}),
                 ('Times', {'fields': [('at_morning', 'at_afternoon', 'at_evening', 'at_night')]})]
    list_filter = ('weather', 'in_summer', 'in_fall', 'in_winter', 'in_spring', 'at_morning', 'at_afternoon',
                   'at_evening', 'at_night')


admin.site.register(WeatherType, WeatherTypeAdmin)
admin.site.register(WeatherEmit, WeatherEmitAdmin)
