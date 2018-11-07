from django.db.models import Q
from django.http import Http404
from django.shortcuts import render
from web.character.models import LoreTopic, Clue
from world.dominion.models import CrisisAction


def admin_search(request):

    if not request.user.is_staff:
        raise Http404

    search_term = request.GET.get("search_term")
    if not search_term:
        return render(request, 'admintools/search.html', {'page_title': 'Admin Search Tool'})

    lore_qs = LoreTopic.objects.filter(Q(name__icontains=search_term) | Q(desc__icontains=search_term))

    clue_qs = Clue.objects.filter(Q(name__icontains=search_term) | Q(desc__icontains=search_term) |
                                  Q(gm_notes__icontains=search_term) | Q(search_tags__name__icontains=search_term))
    clue_qs = clue_qs.distinct()

    crisis_qs = CrisisAction.objects.filter(Q(actions__icontains=search_term) |
                                            Q(assisting_actions__actions__icontains=search_term) |
                                            Q(story__icontains=search_term))
    crisis_qs = crisis_qs.distinct()

    context = {
        'page_title': 'Admin Search Tool',
        'lore': lore_qs,
        'clues': clue_qs,
        'crisis_actions': crisis_qs
    }
    return render(request, 'admintools/search_results.html', context)
