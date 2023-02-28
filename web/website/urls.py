"""
This structures the (simple) structure of the
webpage 'application'.
"""

from django.urls import re_path
from web.website.views import page_index

urlpatterns = [
    re_path(r"^$", page_index),
]
