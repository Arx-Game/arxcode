"""
django-helpdesk - A Django powered ticket tracker for small enterprise.

(c) Copyright 2008 Jutda. All Rights Reserved. See LICENSE for details.

views/kb.py - Public-facing knowledgebase views. The knowledgebase is a
              simple categorised question/answer system to show common
              resolutions to common problems.
"""
from django.shortcuts import render, get_object_or_404

from web.helpdesk import settings as helpdesk_settings
from web.helpdesk.models import KBCategory, KBItem


def index(request):
    category_list = KBCategory.objects.all()
    # TODO: It'd be great to have a list of most popular items here.
    return render(request, 'helpdesk/kb_index.html', {
            'kb_categories': category_list,
            'helpdesk_settings': helpdesk_settings,
        })


def category(request, slug):
    kb_category = get_object_or_404(KBCategory, slug__iexact=slug)
    items = kb_category.kb_items.all()
    return render(request, 'helpdesk/kb_category.html', {
            'category': kb_category,
            'items': items,
            'helpdesk_settings': helpdesk_settings,
        })


def item(request, item_id):
    kb_item = get_object_or_404(KBItem, pk=item_id)
    return render(request, 'helpdesk/kb_item.html', {
            'item': kb_item,
            'helpdesk_settings': helpdesk_settings,
        })
