"""
Dice for gambling
"""
from typeclasses.objects import Object
from cmdset_gambling import DiceCmdSet


class Dice(Object):
    """
    Class for placed objects that allow the 'tabletalk' command.
    """
    default_desc = "A set of five dice. It looks like someone could {wroll{n them."

    def at_object_creation(self):
        """
        Run at Place creation.
        """
        self.cmdset.add_default(DiceCmdSet, permanent=True)
        self.at_init()
