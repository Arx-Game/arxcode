from django.urls import re_path
from web.website.views import webclient

urlpatterns = [re_path(r"^$", webclient, name="index")]
