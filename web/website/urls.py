"""
This structures the (simple) structure of the
webpage 'application'.
"""

from django.conf.urls import url
from web.website.views import page_index

urlpatterns = [
    url(r"^$", page_index),
]
