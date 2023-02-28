"""
This structures the url tree for the news application.
It is imported from the root handler, game.web.urls.py.
"""

from django.urls import re_path
from web.news import views

urlpatterns = [
    re_path(r"^show/(?P<entry_id>\d+)/$", views.show_news),
    re_path(r"^archive/$", views.news_archive),
    re_path(r"^search/$", views.search_form),
    re_path(r"^search/results/$", views.search_results),
]
