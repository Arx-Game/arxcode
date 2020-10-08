"""
This is a very simple news application, with most of the expected features
like news-categories/topics and searchable archives.

"""

from django.views.generic import ListView
from django.shortcuts import get_object_or_404, render
from django.conf import settings
from django.http import HttpResponseRedirect
from django import forms
from django.db.models import Q

from .models import NewsEntry

# The sidebar text to be included as a variable on each page. There's got to
# be a better, cleaner way to include this on every page.
sidebar = """
    <p class='doNotDisplay doNotPrint'>This page&rsquo;s menu:</p>
    <ul id='side-bar'>
      <li><a href='/news/archive'>News Archive</a></li>
      <li><a href='/news/search'>Search News</a></li>
    </ul>
"""


class SearchForm(forms.Form):
    """
    Class to represent a news search form under Django's newforms. This is used
    to validate the input on the search_form view, as well as the search_results
    view when we're picking the query out of GET. This makes searching safe
    via the search form or by directly inputing values via GET key pairs.
    """

    search_terms = forms.CharField(max_length=100, min_length=3, required=True)


def show_news(request, entry_id):
    """
    Show an individual news entry. Display some basic information along with
    the title and content.
    """
    news_entry = get_object_or_404(NewsEntry, id=entry_id)

    pagevars = {
        "page_title": "News Entry",
        "news_entry": news_entry,
        "sidebar": sidebar,
    }

    return render(request, "news/show_entry.html", pagevars, content_type="text/html")


def news_archive(request):
    """
    Shows an archive of news entries.

    TODO: Expand this a bit to allow filtering by month/year.
    """
    news_entries = NewsEntry.objects.all().order_by("-date_posted")
    # TODO: Move this to either settings.py or the SQL configuration.
    entries_per_page = 15

    pagevars = {
        "page_title": "News Archive",
        "browse_url": "/news/archive",
        "sidebar": sidebar,
    }
    view = ListView.as_view(queryset=news_entries)
    return view(
        request,
        template_name="news/archive.html",
        extra_context=pagevars,
        paginate_by=entries_per_page,
    )


def search_form(request):
    """
    Render the news search form. Don't handle much validation at all. If the
    user enters a search term that meets the minimum, send them on their way
    to the results page.
    """
    if request.method == "GET":
        # A GET request was sent to the search page, load the value and
        # validate it.
        form = SearchForm(request.GET)
        if form.is_valid():
            # If the input is good, send them to the results page with the
            # query attached in GET variables.
            return HttpResponseRedirect(
                "/news/search/results/?search_terms="
                + form.cleaned_data["search_terms"]
            )
    else:
        # Brand new search, nothing has been sent just yet.
        form = SearchForm()

    pagevars = {
        "page_title": "Search News",
        "search_form": form,
        "debug": settings.DEBUG,
        "sidebar": sidebar,
    }

    return render(request, "news/search_form.html", pagevars, content_type="text/html")


def search_results(request):
    """
    Shows an archive of news entries. Use the generic news browsing template.
    """
    # TODO: Move this to either settings.py or the SQL configuration.
    entries_per_page = 15

    # Load the form values from GET to validate against.
    form = SearchForm(request.GET)
    # You have to call is_valid() or cleaned_data won't be populated.
    valid_search = form.is_valid()
    # This is the safe data that we can pass to queries without huge worry of
    # badStuff(tm).
    cleaned_get = form.cleaned_data

    # Perform searches that match the title and contents.
    # TODO: Allow the user to specify what to match against and in what
    # topics/categories.
    news_entries = NewsEntry.objects.filter(
        Q(title__contains=cleaned_get["search_terms"])
        | Q(body__contains=cleaned_get["search_terms"])
    )

    pagevars = {
        "game_name": settings.SERVERNAME,
        "page_title": "Search Results",
        "searchtext": cleaned_get["search_terms"],
        "browse_url": "/news/search/results",
        "sidebar": sidebar,
    }
    view = ListView.as_view(queryset=news_entries)
    return view(
        request,
        news_entries,
        template_name="news/archive.html",
        extra_context=pagevars,
        paginate_by=entries_per_page,
    )
