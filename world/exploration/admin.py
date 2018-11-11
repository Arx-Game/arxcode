from django.contrib import admin
from .models import *
from world.dominion.admin import RegionFilter


class ShardhavenClueInline(admin.TabularInline):
    """Inline for Clues about Shardhavens"""
    model = ShardhavenClue
    raw_id_fields = ('clue',)
    extra = 0


class ShardhavenDiscoveryInline(admin.TabularInline):
    """Inline for players knowing about Shardhaven locations"""
    model = ShardhavenDiscovery
    raw_id_fields = ('player',)
    extra = 0


class ShardhavenTypeFilter(admin.SimpleListFilter):
    """List filter for plot rooms, letting us see what regions they're in"""
    title = "Type"
    parameter_name = "haven_type"

    def lookups(self, request, model_admin):
        """Get lookup names derived from Regions"""
        haven_types = ShardhavenType.objects.all().order_by('name')
        result = []
        for haven_type in haven_types:
            result.append((haven_type.id, haven_type.name))
        return result

    def queryset(self, request, queryset):
        """Filter queryset by Region selection"""
        if not self.value():
            return queryset

        try:
            haven_id = int(self.value())
            haven_type = ShardhavenType.objects.get(id=haven_id)
        except (ValueError, ShardhavenType.DoesNotExist):
            haven_type = None

        if not haven_type:
            return queryset

        return self.finish_queryset_by_region(queryset, haven_type)

    # noinspection PyMethodMayBeStatic
    def finish_queryset_by_region(self, queryset, region):
        """Finishes modifying the queryset. Overridden in subclasses"""
        return queryset.filter(haven_type=haven_type)


class ShardhavenLayoutTypeFilter(ShardhavenTypeFilter):
    """List filter for plot rooms, letting us see what regions they're in"""

    # noinspection PyMethodMayBeStatic
    def finish_queryset_by_region(self, queryset, region):
        """Finishes modifying the queryset. Overridden in subclasses"""
        return queryset.filter(layout__haven_type=haven_type)


class ShardhavenAdmin(admin.ModelAdmin):
    """Admin for shardhavens, Arx's very own abyssal-corrupted dungeons. Happy adventuring!"""
    list_display = ('id', 'name', 'location', 'haven_type')
    search_fields = ('name', 'description')
    inlines = (ShardhavenClueInline, )
    list_filter = (ShardhavenTypeFilter, RegionFilter,)


class ShardhavenTypeAdmin(admin.ModelAdmin):
    """Admin for specifying types of Shardhavens"""
    list_display = ('id', 'name', 'description')
    search_fields = ('name',)
    ordering = ('id',)


class ShardhavenDiscoveryAdmin(admin.ModelAdmin):
    """Non-inline admin for Shardhaven discoveries"""
    list_display = ('id', 'player', 'shardhaven')
    raw_id_fields = ('player', 'shardhaven')
    search_fields = ('player__name', 'shardhaven__name')


class ShardhavenMoodFragmentAdmin(admin.ModelAdmin):

    list_display = ('id', 'shardhaven_type', 'text')
    list_filter = (ShardhavenTypeFilter,)


class ShardhavenLayoutAdmin(admin.ModelAdmin):

    list_display = ('id', 'haven', 'width', 'height')
    list_display_links = ('id', )
    ordering = ("id",)
    search_fields = ('haven__name',)
    list_filter = (ShardhavenTypeFilter,)


class ShardhavenLayoutSquareAdmin(admin.ModelAdmin):

    list_display = ('id', 'layout', 'x_coord', 'y_coord')
    list_filter = (ShardhavenLayoutTypeFilter,)
    search_fields = ('layout__haven__name',)


class ShardhavenLayoutExitAdmin(admin.ModelAdmin):
    pass


admin.site.register(Shardhaven, ShardhavenAdmin)
admin.site.register(ShardhavenType, ShardhavenTypeAdmin)
admin.site.register(ShardhavenMoodFragment, ShardhavenMoodFragmentAdmin)
admin.site.register(ShardhavenDiscovery, ShardhavenDiscoveryAdmin)
admin.site.register(ShardhavenLayout, ShardhavenLayoutAdmin)
admin.site.register(ShardhavenLayoutSquare, ShardhavenLayoutSquareAdmin)
admin.site.register(ShardhavenLayoutExit, ShardhavenLayoutExitAdmin)
