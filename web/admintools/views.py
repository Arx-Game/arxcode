from django.db.models import Q
from django.http import Http404
from django.shortcuts import render
from web.character.models import Revelation, Clue
from web.helpdesk.models import KBCategory, KBItem
from world.dominion.models import PlotAction


def admin_search(request):

    if not request.user.is_staff:
        raise Http404

    search_term = request.GET.get("search_term")
    if not search_term:
        return render(request, 'admintools/search.html', {'page_title': 'Admin Search Tool'})

    lore_qs = Revelation.objects.filter(Q(name__icontains=search_term) | Q(desc__icontains=search_term) |
                                        Q(gm_notes__icontains=search_term))

    clue_qs = Clue.objects.filter(Q(name__icontains=search_term) | Q(desc__icontains=search_term) |
                                  Q(gm_notes__icontains=search_term) | Q(search_tags__name__icontains=search_term))
    clue_qs = clue_qs.distinct()

    crisis_qs = PlotAction.objects.filter(Q(actions__icontains=search_term) |
                                          Q(assisting_actions__actions__icontains=search_term) |
                                          Q(story__icontains=search_term))
    crisis_qs = crisis_qs.distinct()

    search_tag_query = Q(search_tags__name__iexact=search_term)
    categories = KBCategory.objects.filter(Q(title__icontains=search_term) | Q(description__icontains=search_term) |
                                           search_tag_query).distinct()
    entries = KBItem.objects.filter(Q(title__icontains=search_term) | Q(question__icontains=search_term) |
                                    Q(answer__icontains=search_term) | search_tag_query).distinct()

    context = {
        'page_title': 'Admin Search Tool',
        'lore': lore_qs,
        'clues': clue_qs,
        'crisis_actions': crisis_qs,
        'entries': entries,
        'categories': categories,
    }
    return render(request, 'admintools/search_results.html', context)
