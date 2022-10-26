from django.conf.urls import url
from web.website.views import webclient

urlpatterns = [url(r"^$", webclient, name="index")]
