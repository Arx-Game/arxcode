from django.urls import re_path
from web.admintools.views import admin_search

urlpatterns = [re_path(r"^search/$", admin_search, name="search")]
