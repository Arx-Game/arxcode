"""
Base commands used for Arx
"""
from evennia.commands.default.muxcommand import MuxCommand, MuxAccountCommand
from .mixins import ArxCommmandMixin


class ArxCommand(ArxCommmandMixin, MuxCommand):
    """Base command for Characters for Arx"""
    pass


class ArxPlayerCommand(ArxCommmandMixin, MuxAccountCommand):
    """Base command for Players/Accounts for Arx"""
    pass
