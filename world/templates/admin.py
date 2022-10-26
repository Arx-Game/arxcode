from django.contrib import admin
from django.utils.safestring import mark_safe

from world.templates.models import (
    Template,
    WrittenWork,
    BookChapter,
    ChapterSignature,
)


class TemplateAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "title")
    search_fields = ("=id", "title")
    raw_id_fields = ("owner",)


class ChapterInline(admin.StackedInline):
    model = BookChapter
    extra = 0
    raw_id_fields = ("objectdb",)


class WrittenWorkAdmin(admin.ModelAdmin):
    list_display = ("id", "author", "title", "language")
    search_fields = ("title", "=author__db_key", "=id")
    raw_id_fields = ("owner", "author")
    readonly_fields = ("body_without_ansi",)
    list_filter = ("language",)
    inlines = (ChapterInline,)

    @mark_safe
    def body_without_ansi(self, obj):
        from web.help_topics.templatetags.app_filters import mush_to_html

        return mush_to_html(obj.body)

    body_without_ansi.allow_tags = True


class SignatureAdmin(admin.ModelAdmin):
    list_display = ("book_chapter_id", "signer")
    search_fields = (
        "=book_chapter__id",
        "signer__db_key",
        "book_chapter__written_work__title",
    )
    raw_id_fields = ("book_chapter", "signer")


admin.site.register(Template, TemplateAdmin)
admin.site.register(WrittenWork, WrittenWorkAdmin)
admin.site.register(ChapterSignature, SignatureAdmin)
