from django.conf.urls import url
from .views import webclient

urlpatterns = [url(r"^$", webclient, name="index")]
