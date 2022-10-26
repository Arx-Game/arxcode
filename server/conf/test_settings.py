from server.conf.base_settings import *
from decouple import config, Csv

MAX_COMMAND_RATE = 1
# values to put in new settings file to maintain existing values:
TELNET_PORTS = [3050]
WEBSERVER_PORTS = [(8082, 5001)]
WEBSOCKET_CLIENT_PORT = 8083
SSH_PORTS = [8022]
SSL_PORTS = [4001]
AMP_PORT = 5000
TELNET_INTERFACES = config("TELNET_INTERFACES", default="192.168.1.209", cast=Csv())
WEBSOCKET_CLIENT_INTERFACE = config(
    "WEBSOCKET_CLIENT_INTERFACE", default="192.168.1.209"
)
INTERNAL_IPS = ("127.0.0.1",)
SITE_HEADER = "ArxTest Admin"
INDEX_TITLE = "ArxTest Admin"
IN_GAME_ERRORS = True

INSTALLED_APPS += ("test_without_migrations",)

######################################################################
# Contrib config
######################################################################

GAME_INDEX_LISTING = {}
DEBUG = True
TEMPLATES[0]["OPTIONS"]["debug"] = DEBUG
