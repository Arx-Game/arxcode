
"""
This file contains the generic, assorted views that don't fall under one of
the other applications. Views are django's way of processing e.g. html
templates on the fly.

"""
from django.shortcuts import render
from django.conf import settings

from evennia.objects.models import ObjectDB
from evennia.accounts.models import AccountDB
from web.news.models import NewsEntry
from web.character.models import Chapter
from world.dominion.models import RPEvent

_BASE_CHAR_TYPECLASS = settings.BASE_CHARACTER_TYPECLASS


def page_index(request):
    """
    Main root page.
    """
    # Some misc. configurable stuff.
    # TODO: Move this to either SQL or settings.py based configuration.
    fpage_player_limit = 4
    fpage_news_entries = 2

    # A QuerySet of recent news entries.
    news_entries = NewsEntry.objects.all().order_by('-date_posted')[:fpage_news_entries]
    # A QuerySet of the most recently connected players.
    recent_users = [ob for ob in AccountDB.objects.get_recently_connected_accounts() if hasattr(ob, 'roster') and
                    ob.roster.roster.name == "Active"][:fpage_player_limit]
    nplyrs_conn_recent = len(recent_users) or "none"
    nplyrs = AccountDB.objects.filter(roster__roster__name="Active").count() or "none"
    nplyrs_reg_recent = len(AccountDB.objects.get_recently_created_accounts()) or "none"
    nsess = len(AccountDB.objects.get_connected_accounts()) or "noone"

    nobjs = ObjectDB.objects.all().count()
    nrooms = ObjectDB.objects.filter(db_location__isnull=True).exclude(db_typeclass_path=_BASE_CHAR_TYPECLASS).count()
    nexits = ObjectDB.objects.filter(db_location__isnull=False, db_destination__isnull=False).count()
    nchars = ObjectDB.objects.filter(db_typeclass_path=_BASE_CHAR_TYPECLASS).count()
    nothers = nobjs - nrooms - nchars - nexits

    try:
        chapter = Chapter.objects.latest('start_date')
    except Chapter.DoesNotExist:
        chapter = None
    events = RPEvent.objects.filter(finished=False, public_event=True).order_by('date')[:3]

    pagevars = {
        "page_title": "After the Reckoning",
        "news_entries": news_entries,
        "players_connected_recent": recent_users,
        "num_players_connected": nsess or "noone",
        "num_players_registered": nplyrs or "no",
        "num_players_connected_recent": nplyrs_conn_recent or "no",
        "num_players_registered_recent": nplyrs_reg_recent or "noone",
        "num_rooms": nrooms or "none",
        "num_exits": nexits or "no",
        "num_objects": nobjs or "none",
        "num_characters": nchars or "no",
        "num_others": nothers or "no",
        "chapter": chapter,
        "events": events,
        "game_slogan": settings.GAME_SLOGAN,
        "user": request.user,
        "webclient_enabled": settings.WEBCLIENT_ENABLED
    }

    return render(request, 'index.html', pagevars, content_type="text/html")


def webclient(request):
    """
    Webclient page template loading.

    """
    # disable autologin until it's fixed in devel
    session = request.session
    session.flush()
    session.save()
    from evennia.web.webclient.views import webclient
    return webclient(request)
