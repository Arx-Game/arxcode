"""
Settings we use for production. Some of these could eventually be moved into a settings.ini file
"""
from .base_settings import *

from decouple import config, Csv

TELNET_INTERFACES = config('TELNET_INTERFACES', default='45.33.87.194', cast=Csv())
WEBSOCKET_CLIENT_INTERFACE = config('WEBSOCKET_CLIENT_INTERFACE', default='45.33.87.194')
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='.arxmush.org, .arxgame.org', cast=Csv())
WEBSERVER_PORT_EXTERNAL = config('WEBSERVER_PORT_EXTERNAL', default=8000, cast=int)
WEBSERVER_PORT_INTERNAL = config('WEBSERVER_PORT_INTERNAL', default=5001, cast=int)
WEBSERVER_PORTS = [(WEBSERVER_PORT_EXTERNAL, WEBSERVER_PORT_INTERNAL)]
WEBSOCKET_CLIENT_PORT = config('WEBSOCKET_CLIENT_PORT', default=8001, cast=int)
WEBSOCKET_CLIENT_URL = config('WEBSOCKET_CLIENT_URL', default="wss://play.arxgame.org/ws")
SSH_PORTS = config('SSH_PORTS', default='8022', cast=Csv(cast=int))
SSL_PORTS = config('SSL_PORTS', default='4001', cast=Csv(cast=int))
AMP_PORT = config('AMP_PORT', default=5000, cast=int)
SITE_HEADER = config('SITE_HEADER', default="ArxPrime Admin")
INDEX_TITLE = config('INDEX_TITLE', default="ArxPrime Admin")
CHECK_VPN = config('CHECK_VPN', default=True, cast=bool)
MAX_CHAR_LIMIT = config('MAX_CHAR_LIMIT', default=8000, cast=int)

######################################################################
# Contrib config
######################################################################
if SEND_GAME_INDEX:
    GAME_INDEX_LISTING = {
        'game_status': config("INDEX_GAME_STATUS", default='beta'),
        # Optional, comment out or remove if N/A
        'game_website': config("INDEX_GAME_WEBSITE", default='http://play.arxgame.org'),
        'short_description': config("INDEX_SHORT_DESC", default='MUX-style game in an original fantasy setting'),
        # Optional but highly recommended. Markdown is supported.
        'long_description': config("INDEX_LONG_DESC", default=(
            "Arx is a MUX-style game in an original low-fantasy setting, "
            "inspired by series such as Game of Thrones and The First Law. "
        )),
        'listing_contact': config("INDEX_CONTACT", default='brannigd@hotmail.com'),
        # At minimum, specify this or the web_client_url options. Both is fine, too.
        'telnet_hostname': config("INDEX_TELNET_HOSTNAME", default='play.arxgame.org'),
        'telnet_port': TELNET_PORTS[0],
        # At minimum, specify this or the telnet_* options. Both is fine, too.
        'web_client_url': 'https://play.arxgame.org/webclient',
    }
