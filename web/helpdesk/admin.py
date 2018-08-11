from django.contrib import admin
from .models import Queue, Ticket, FollowUp, PreSetReply, KBCategory
from .models import EscalationExclusion, EmailTemplate, KBItem
from .models import TicketChange, Attachment, IgnoreEmail
from .models import CustomField

class QueueAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'email_address', 'locale')

class TicketAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'status', 'assigned_to', 'submitting_player', 'queue')
    date_hierarchy = 'db_date_created'
    list_filter = ('status', 'queue', 'priority')
    search_fields = ('id', 'title', 'assigned_to__username', 'submitting_player__username', 'description',
                     'resolution')
    raw_id_fields = ('assigned_to', 'submitting_player', 'submitting_room')

class TicketChangeInline(admin.StackedInline):
    model = TicketChange

class AttachmentInline(admin.StackedInline):
    model = Attachment

class FollowUpAdmin(admin.ModelAdmin):
    inlines = [TicketChangeInline, AttachmentInline]

class KBItemAdmin(admin.ModelAdmin):
    search_fields = ('title', 'question', 'answer')
    list_display = ('category', 'title', 'last_updated',)
    list_display_links = ('title',)
    list_filter = ('category',)
   
class CustomFieldAdmin(admin.ModelAdmin):
    list_display = ('name', 'label', 'data_type')

class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ('template_name', 'heading', 'locale')
    list_filter = ('locale', )

admin.site.register(Ticket, TicketAdmin)
admin.site.register(Queue, QueueAdmin)
# admin.site.register(FollowUp, FollowUpAdmin)
# admin.site.register(PreSetReply)
# admin.site.register(EscalationExclusion)
# admin.site.register(EmailTemplate, EmailTemplateAdmin)
admin.site.register(KBCategory)
admin.site.register(KBItem, KBItemAdmin)
# admin.site.register(IgnoreEmail)
# admin.site.register(CustomField, CustomFieldAdmin)
