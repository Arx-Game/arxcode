"""
Evennia settings file.

The available options are found in the default settings file found
here:

/home/tehom/arx/evennia/evennia/settings_default.py

Remember:

Don't copy more from the default file than you actually intend to
change; this will make sure that you don't overload upstream updates
unnecessarily.

When changing a setting requiring a file system path (like
path/to/actual/file.py), use GAME_DIR and EVENNIA_DIR to reference
your game folder and the Evennia library folders respectively. Python
paths (path.to.module) should be given relative to the game's root
folder (typeclasses.foo) whereas paths within the Evennia library
needs to be given explicitly (evennia.foo).

"""
# from .production_settings import *

"""
Base settings that we'll inherit from
"""
from evennia.settings_default import *
# see documentation on python-decouple. tldr: create a config.env file at repo root, config() draws from that.
from decouple import config

######################################################################
# Evennia base server config
######################################################################

# CHANGES: replace ADDITIONAL ANSI MAPPINGS WITH the following:
from evennia.contrib import color_markups
COLOR_ANSI_EXTRA_MAP = color_markups.CURLY_COLOR_ANSI_EXTRA_MAP + color_markups.MUX_COLOR_ANSI_EXTRA_MAP
COLOR_XTERM256_EXTRA_FG = color_markups.CURLY_COLOR_XTERM256_EXTRA_FG + color_markups.MUX_COLOR_XTERM256_EXTRA_FG
COLOR_XTERM256_EXTRA_BG = color_markups.CURLY_COLOR_XTERM256_EXTRA_BG + color_markups.MUX_COLOR_XTERM256_EXTRA_BG
COLOR_XTERM256_EXTRA_GFG = color_markups.CURLY_COLOR_XTERM256_EXTRA_GFG + color_markups.MUX_COLOR_XTERM256_EXTRA_GFG
COLOR_XTERM256_EXTRA_GBG = color_markups.CURLY_COLOR_XTERM256_EXTRA_GBG + color_markups.MUX_COLOR_XTERM256_EXTRA_GBG
COLOR_ANSI_BRIGHT_BG_EXTRA_MAP = color_markups.CURLY_COLOR_ANSI_XTERM256_BRIGHT_BG_EXTRA_MAP + color_markups.MUX_COLOR_ANSI_XTERM256_BRIGHT_BG_EXTRA_MAP
PERMISSION_HIERARCHY = ["Guest",  # note-only used if GUEST_ENABLED=True
                        "Player",
                        "Helper",
                        "Builders",
                        "Builder",
                        "Wizards",
                        "Wizard",
                        "Admin",
                        "Immortals",
                        "Immortal",
                        "Developer",
                        ]
SERVERNAME = config("SERVERNAME", default="Arx")
GAME_SLOGAN = config("GAME_SLOGAN", default="Season Two: Heroes and Other Fables")
TIME_ZONE = 'America/New_York'
USE_TZ = False
TELNET_PORTS = [3000]
IDMAPPER_CACHE_MAXSIZE = 2000
EVENNIA_ADMIN = False
EMAIL_USE_TLS = True
IN_GAME_ERRORS = False
IDLE_TIMEOUT = -1
MAX_CHAR_LIMIT = 8000
DEBUG = False
CHANNEL_COMMAND_CLASS = "commands.base_commands.channels.ArxChannelCommand"
BASE_ROOM_TYPECLASS = "typeclasses.rooms.ArxRoom"
DEFAULT_HOME = "#13"
MULTISESSION_MODE = 1
COMMAND_DEFAULT_MSG_ALL_SESSIONS = True
ADDITIONAL_ANSI_MAPPINGS = [(r'%r', "\r\n"),]
COMMAND_DEFAULT_ARG_REGEX = r'^[ /]+.*$|$'
LOCKWARNING_LOG_FILE = ""
DEFAULT_CHANNELS = [
    {"key": "Public",
     "aliases": "pub",
     "desc": "Public discussion",
     "locks": "control: perm(Wizards);listen:all();send:all()"},
    {"key": "MUDinfo",
     "aliases": "",
     "desc": "Connection log",
     "locks": "control:perm(Immortals);listen:perm(Wizards);send:false()"}
    ]

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(GAME_DIR, 'server', 'evennia.db3'),
        'USER': '',
        'PASSWORD': '',
        'HOST': '',
        'PORT': '',
        'OPTIONS': {'timeout': 25},
        }}

TEMPLATES[0]['OPTIONS']['context_processors'] += [
    'web.character.context_processors.consts']
TEMPLATES[0]['OPTIONS']['debug'] = DEBUG

# Global and Evennia-specific apps. This ties everything together so we can
# refer to app models and perform DB syncs.
INSTALLED_APPS += ('world.dominion',
                   'world.msgs',
                   'world.conditions.apps.ConditionsConfig',
                   'world.fashion.apps.FashionConfig',
                   'world.petitions.apps.PetitionsConfig',
                   'web.character',
                   'web.news',
                   'web.helpdesk',
                   'web.help_topics',
                   'cloudinary',
                   'django.contrib.humanize',
                   'bootstrapform',
                   'crispy_forms',
                   'world.weather',
                   'world.templates.apps.TemplateConfig',
                   'world.exploration',
                   'web.admintools',
                   'world.magic',
                   )

CRISPY_TEMPLATE_PACK = 'bootstrap3'
DATA_UPLOAD_MAX_NUMBER_FIELDS = 2000

######################################################################
# Game Time setup
######################################################################
TIME_FACTOR = 2.0
INVESTIGATION_PROGRESS_RATE = config("INVESTIGATION_PROGRESS_RATE", cast=float, default=1.0)
INVESTIGATION_DIFFICULTY_MOD = 5

######################################################################
# Magic setup
######################################################################
MAGIC_CONDITION_MODULES = ("world.magic.conditionals",)

######################################################################
# Helpdesk settings
######################################################################
HELPDESK_CREATE_TICKET_HIDE_ASSIGNED_TO = True

# Queue.id for our Requests. Should normally be 1, but can be changed if you move queues around
REQUEST_QUEUE_SLUG = "Request"
BUG_QUEUE_SLUG = "Bugs"

######################################################################
# Dominion settings
######################################################################
BATTLE_LOG = os.path.join(LOG_DIR, 'battle.log')
DOMINION_LOG = os.path.join(LOG_DIR, 'dominion.log')
LOG_FORMAT = "%(asctime)s: %(message)s"
DATE_FORMAT = "%m/%d/%Y %I:%M:%S"
GLOBAL_DOMAIN_INCOME_MOD = 0.75

SECRET_KEY = config('SECRET_KEY', default="PLEASEREPLACEME12345")
HOST_BLOCKER_API_KEY = config('HOST_BLOCKER_API_KEY', default="SOME_KEY")
import cloudinary
cloudinary.config(cloud_name=config('CLOUDINARY_NAME', default="SOME_NAME"),
                  api_key=config('CLOUDINARY_API_KEY', default="SOME_KEY"),
                  api_secret=config('CLOUDINARY_API_SECRET', default="SOME_KEY"))

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST', default='localhost')
EMAIL_PORT = config('EMAIL_PORT', cast=int, default=25)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='')
ADMINS = (config('ADMIN_NAME', default=''), config('ADMIN_EMAIL', default=''))
SEND_GAME_INDEX = config('SEND_GAME_INDEX', cast=bool, default=False)
ISSUES_URL = config('ISSUES_URL', default='')

######################################################################
######################################################################
######################################################################
######################################################################
######################################################################

TELNET_PORTS = [4000]
SERVERNAME = "MyArx"
GAME_SLOGAN = "The cool game"

BASE_GUEST_TYPECLASS = 'typeclasses.guest.Guest'

try:
    from server.conf.secret_settings import *
except ImportError:
    print("secret_settings.py file not found or failed to import.")

