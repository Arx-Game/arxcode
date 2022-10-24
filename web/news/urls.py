"""
This structures the url tree for the news application.
It is imported from the root handler, game.web.urls.py.
"""

from django.conf.urls import url
from web.news import views

urlpatterns = [
    url(r"^show/(?P<entry_id>\d+)/$", views.show_news),
    url(r"^archive/$", views.news_archive),
    url(r"^search/$", views.search_form),
    url(r"^search/results/$", views.search_results),
]
