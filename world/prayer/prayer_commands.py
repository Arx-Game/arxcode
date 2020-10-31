"""
You gotta pray just to make it today. Praaaaay. Praaaaaay.
"""
from commands.base import ArxCommand


class CmdPray(ArxCommand):
    """
    Help file to be filled out by Apostate
    """
    key = "pray"
    locks = "cmd:all()"
    help_category = "story"

    def func(self):
        """Where the praying happens. Amen."""
        pass


class CmdGMPray(ArxCommand):
    """
    Help file to also be filled out by Apostate
    """
    key = "gmpray"
    aliases = ["gm_pray", "gmprayer", "gm_prayer"]
    locks = "cmd:perm(Wizards)"
    help_category = "GMing"

    def func(self):
        """Where prayers are answered. 'No,' says God."""
        pass

