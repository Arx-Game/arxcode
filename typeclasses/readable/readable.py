"""
Readable/Writable objects
"""

from typeclasses.objects import Object

from typeclasses.readable.readable_commands import WriteCmdSet, SignCmdSet
from world.crafting.junk_handlers import BaseJunkHandler


class Readable(Object):
    """
    Class for objects that can be written/named
    """

    default_desc = "Nothing has been written on this yet. '{whelp write{n'"
    junk_handler_class = BaseJunkHandler

    def at_object_creation(self):
        """
        Run at Place creation.
        """
        self.db.written = False
        self.db.can_stack = True
        self.db.do_not_format_desc = True
        self.at_init()

    def at_after_move(self, source_location, **kwargs):
        if self.item_data.quantity > 1 and not self.db.written:
            self.setup_multiname()
        location = self.location
        # if location is a character, add cmdset
        if location and location.is_character:
            if self.db.written:
                self.cmdset.add_default(SignCmdSet, permanent=True)
            else:
                self.cmdset.add_default(WriteCmdSet, permanent=True)
        else:
            self.cmdset.delete_default()

    def return_appearance(self, *args, **kwargs):
        msg = Object.return_appearance(self, *args, **kwargs)
        if self.db.signed and not self.db.can_stack:
            sigs = ", ".join(str(ob) for ob in self.db.signed)
            msg += "\nSigned by: %s" % sigs
        return msg

    # noinspection PyAttributeOutsideInit
    def setup_multiname(self):
        if self.item_data.quantity > 1:
            self.key = "%s books" % self.item_data.quantity
            self.save()
        else:
            self.key = "a book"

    def set_num(self, value):
        self.item_data.quantity = value
        self.setup_multiname()
