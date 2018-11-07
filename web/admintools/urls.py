from django.conf.urls import url
from .views import admin_search

urlpatterns = [
    url(r'^search/$', admin_search, name="search")
]