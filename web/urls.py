"""
Url definition file to redistribute incoming URL requests to django
views. Search the Django documentation for "URL dispatcher" for more
help.

"""
from django.conf.urls import url, include
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.views.generic import RedirectView
from django.views.static import serve


def include_app(url_path, namespace):
    return include((url_path, namespace), namespace=namespace)


urlpatterns = [
    # User Authentication
    url(r'^accounts/login',  auth_views.LoginView.as_view(template_name="login.html"), name='login'),
    url(r'^accounts/logout', auth_views.LogoutView.as_view(), name="logout"),

    # Front page
    url(r'^', include('web.website.urls')),
    # News stuff
    url(r'^news/', include('web.news.urls')),

    # Admin interface
    url(r'^admin/doc/', include('django.contrib.admindocs.urls')),
    url(r'^admin/', admin.site.urls),

    url(r'^webclient/', include_app('web.website.webclient_urls', "webclient")),

    # favicon
    url(r'^favicon\.ico$', RedirectView.as_view(url='/static/images/favicon.ico', permanent=False)),

    url(r'^character/', include_app('web.character.urls', 'character')),

    url(r'^topics/', include_app('web.help_topics.urls', namespace='help_topics')),

    url(r'^dom/', include_app('world.dominion.urls', namespace='dominion')),

    url(r'^comms/', include_app('world.msgs.urls', namespace='msgs')),

    url(r'^static/(?P<path>.*)$', serve, {'document_root': settings.STATIC_ROOT}),

    url(r'^support/', include('web.helpdesk.urls')),

    url(r'^admintools/', include_app('web.admintools.urls', namespace='admintools')),

    url(r'^explore/', include_app('world.exploration.urls', namespace='exploration')),
]

# This sets up the server if the user want to run the Django
# test server (this should normally not be needed).
if settings.SERVE_MEDIA:
    urlpatterns += [
        (r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
        
    ]

if settings.DEBUG:
    try:
        # noinspection PyPackageRequirements
        import debug_toolbar
    except ImportError:
        debug_toolbar = None
    if debug_toolbar:
        urlpatterns += [
            url(r'^__debug__/', include(debug_toolbar.urls)),
        ]

handler500 = 'web.website.views.arx_500_view'
