"""
Base settings that we'll inherit from
"""
from evennia.settings_default import *

# see documentation on python-decouple. tldr: create a settings.ini file at repo root, config() draws from that.
from decouple import config, Csv

######################################################################
# Evennia base server config
######################################################################

# CHANGES: replace ADDITIONAL ANSI MAPPINGS WITH the following:
from evennia.contrib import color_markups

COLOR_ANSI_EXTRA_MAP = (
    color_markups.CURLY_COLOR_ANSI_EXTRA_MAP + color_markups.MUX_COLOR_ANSI_EXTRA_MAP
)
COLOR_XTERM256_EXTRA_FG = (
    color_markups.CURLY_COLOR_XTERM256_EXTRA_FG
    + color_markups.MUX_COLOR_XTERM256_EXTRA_FG
)
COLOR_XTERM256_EXTRA_BG = (
    color_markups.CURLY_COLOR_XTERM256_EXTRA_BG
    + color_markups.MUX_COLOR_XTERM256_EXTRA_BG
)
COLOR_XTERM256_EXTRA_GFG = (
    color_markups.CURLY_COLOR_XTERM256_EXTRA_GFG
    + color_markups.MUX_COLOR_XTERM256_EXTRA_GFG
)
COLOR_XTERM256_EXTRA_GBG = (
    color_markups.CURLY_COLOR_XTERM256_EXTRA_GBG
    + color_markups.MUX_COLOR_XTERM256_EXTRA_GBG
)
COLOR_ANSI_BRIGHT_BG_EXTRA_MAP = (
    color_markups.CURLY_COLOR_ANSI_XTERM256_BRIGHT_BG_EXTRA_MAP
    + color_markups.MUX_COLOR_ANSI_XTERM256_BRIGHT_BG_EXTRA_MAP
)
PERMISSION_HIERARCHY = [
    "Guest",  # note-only used if GUEST_ENABLED=True
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
    "Owner",
]
SERVERNAME = config("SERVERNAME", default="Arx")
VERBOSE_GAME_NAME = config("VERBOSE_GAME_NAME", default="") or SERVERNAME
GAME_SLOGAN = config("GAME_SLOGAN", default="Season Two: Heroes and Other Fables")
TIME_ZONE = config("TIME_ZONE", default="America/New_York")
USE_TZ = config("USE_TZ", default=False, cast=bool)
TELNET_PORTS = config("TELNET_PORTS", default="3000", cast=Csv(cast=int))
IDMAPPER_CACHE_MAXSIZE = config("IDMAPPER_CACHE_MAXSIZE", default=4000, cast=int)
EVENNIA_ADMIN = config("EVENNIA_ADMIN", default=False, cast=bool)
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
IN_GAME_ERRORS = config("IN_GAME_ERRORS", default=False, cast=bool)
IDLE_TIMEOUT = config("IDLE_TIMEOUT", default=-1, cast=int)
MAX_CHAR_LIMIT = config("MAX_CHAR_LIMIT", default=8000, cast=int)
DEBUG = config("DEBUG", default=False, cast=bool)
CHANNEL_COMMAND_CLASS = "commands.base_commands.channels.ArxChannelCommand"
BASE_ROOM_TYPECLASS = "typeclasses.rooms.ArxRoom"
BASE_SCRIPT_TYPECLASS = "typeclasses.scripts.scripts.Script"
BASE_GUEST_TYPECLASS = "typeclasses.guest.Guest"
# Important: set this to the ID of whatever room you want to have as a default for things to show up in
DEFAULT_HOME = config("DEFAULT_HOME", default="#13")
MULTISESSION_MODE = 1
COMMAND_DEFAULT_MSG_ALL_SESSIONS = True
ADDITIONAL_ANSI_MAPPINGS = [
    (r"%r", "\r\n"),
]
COMMAND_DEFAULT_ARG_REGEX = r"^[ /]+.*$|$"
LOCKWARNING_LOG_FILE = ""
PUBLIC_CHANNEL_NAME = config("PUBLIC_CHANNEL_NAME", default="Public")
GUEST_CHANNEL_NAME = config("GUEST_CHANNEL_NAME", default="Guest")
STAFF_INFO_CHANNEL_NAME = config("STAFF_INFO_CHANNEL_NAME", default="staffinfo")
PLAYER_HELPER_CHANNEL_NAME = config("PLAYER_HELPER_CHANNEL_NAME", default="Guides")
DEFAULT_CHANNELS = [
    {
        "key": PUBLIC_CHANNEL_NAME,
        "aliases": "pub",
        "desc": "Public discussion",
        "locks": "control: perm(Wizards);listen:all();send:all()",
    },
    {
        "key": "MUDinfo",
        "aliases": "",
        "desc": "Connection log",
        "locks": "control:perm(Immortals);listen:perm(Wizards);send:false()",
    },
    {
        "key": GUEST_CHANNEL_NAME,
        "aliases": "",
        "desc": "Guest channel",
        "locks": "control:perm(Immortals);listen:all();send:all()",
    },
    {
        "key": "Staff",
        "aliases": "",
        "desc": "Staff channel",
        "locks": "control:perm(Immortals);listen:perm(Builder);send:perm(Builder)",
    },
    {
        "key": STAFF_INFO_CHANNEL_NAME,
        "aliases": "",
        "desc": "Messages for staff",
        "locks": "control:perm(Immortals);listen:perm(Builder);send:perm(Builder)",
    },
    {
        "key": PLAYER_HELPER_CHANNEL_NAME,
        "aliases": "",
        "desc": "Channel for player volunteers",
        "locks": "control:perm(Immortals);listen:perm(helper);send:perm(helper)",
    },
]

DATABASES = {
    "default": {
        "ENGINE": config("DBMS", default="django.db.backends.sqlite3"),
        "NAME": os.path.join(GAME_DIR, "server", "evennia.db3"),
        "USER": "",
        "PASSWORD": "",
        "HOST": "",
        "PORT": "",
        "OPTIONS": {"timeout": 25},
    }
}

TEMPLATES[0]["OPTIONS"]["context_processors"] += [
    "web.character.context_processors.consts"
]
TEMPLATES[0]["OPTIONS"]["debug"] = DEBUG

# Global and Evennia-specific apps. This ties everything together so we can
# refer to app models and perform DB syncs.
INSTALLED_APPS += (
    "world.dominion",
    "world.msgs",
    "world.conditions.apps.ConditionsConfig",
    "world.fashion.apps.FashionConfig",
    "world.petitions.apps.PetitionsConfig",
    "web.character",
    "web.news",
    "web.helpdesk",
    "web.help_topics",
    "cloudinary",
    "django.contrib.humanize",
    "bootstrapform",
    "crispy_forms",
    "world.weather",
    "world.templates.apps.TemplateConfig",
    "world.exploration",
    "web.admintools",
    "world.magic",
    "world.quests.apps.QuestsConfig",
    "world.stat_checks.apps.StatChecksConfig",
    "world.prayer.apps.PrayerConfig",
    "world.traits.apps.TraitsConfig",
    "evennia_extensions.object_extensions.apps.ObjectExtensionsConfig",
    "world.game_constants.apps.GameConstantsConfig",
    "world.crafting.apps.CraftingConfig",
    "evennia_extensions.character_extensions.apps.CharacterExtensionsConfig",
)

CRISPY_TEMPLATE_PACK = "bootstrap3"
DATA_UPLOAD_MAX_NUMBER_FIELDS = 3000

######################################################################
# Game Time setup
######################################################################
TIME_FACTOR = config("TIME_FACTOR", cast=float, default=2.0)
INVESTIGATION_PROGRESS_RATE = config(
    "INVESTIGATION_PROGRESS_RATE", cast=float, default=1.0
)
INVESTIGATION_DIFFICULTY_MOD = config(
    "INVESTIGATION_DIFFICULTY_MOD", default=5, cast=int
)

######################################################################
# Magic setup
######################################################################
MAGIC_CONDITION_MODULES = ("world.magic.conditionals",)

######################################################################
# Helpdesk settings
######################################################################
HELPDESK_CREATE_TICKET_HIDE_ASSIGNED_TO = config(
    "HELPDESK_CREATE_TICKET_HIDE_ASSIGNED_TO", default=True, cast=bool
)

# Queue.id for our Requests. Should normally be 1, but can be changed if you move queues around
REQUEST_QUEUE_SLUG = config("REQUEST_QUEUE_SLUG", default="Request")
BUG_QUEUE_SLUG = config("BUG_QUEUE_SLUG", default="Bugs")

######################################################################
# Dominion settings
######################################################################
BATTLE_LOG = os.path.join(LOG_DIR, "battle.log")
DOMINION_LOG = os.path.join(LOG_DIR, "dominion.log")
LOG_FORMAT = "%(asctime)s: %(message)s"
DATE_FORMAT = "%m/%d/%Y %I:%M:%S"
GLOBAL_DOMAIN_INCOME_MOD = config("GLOBAL_DOMAIN_INCOME_MOD", cast=float, default=0.75)

SECRET_KEY = config("SECRET_KEY", default="PLEASEREPLACEME12345")
HOST_BLOCKER_API_KEY = config("HOST_BLOCKER_API_KEY", default="SOME_KEY")
import cloudinary

cloudinary.config(
    cloud_name=config("CLOUDINARY_NAME", default="SOME_NAME"),
    api_key=config("CLOUDINARY_API_KEY", default="SOME_KEY"),
    api_secret=config("CLOUDINARY_API_SECRET", default="SOME_KEY"),
)

EMAIL_BACKEND = config(
    "EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend"
)
EMAIL_HOST = config("EMAIL_HOST", default="localhost")
EMAIL_PORT = config("EMAIL_PORT", cast=int, default=25)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="")
ADMIN_NAME = config("ADMIN_NAME", default="")
ADMIN_EMAIL = config("ADMIN_EMAIL", default="")
if ADMIN_NAME and ADMIN_EMAIL:
    ADMINS = (ADMIN_NAME, ADMIN_EMAIL)
else:
    ADMINS = []
GAME_INDEX_ENABLED = config("SEND_GAME_INDEX", cast=bool, default=False)
ISSUES_URL = config("ISSUES_URL", default="")
# Evennia's base settings screw up current account creation
AUTH_PASSWORD_VALIDATORS = []
MIDDLEWARE = [
    "django.middleware.common.CommonMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",  # 1.4?
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.admindocs.middleware.XViewMiddleware",
    "django.contrib.flatpages.middleware.FlatpageFallbackMiddleware",
    "web.middleware.auth.SharedLoginMiddleware",
]
SHELL_PLUS_PRINT_SQL = config("SHELL_PLUS_PRINT_SQL", cast=bool, default=False)
