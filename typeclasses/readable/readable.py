"""
Readable/Writable objects
"""
from server.utils.arx_utils import CachedProperty
from typeclasses.objects import Object
from typeclasses.readable.exceptions import ChapterNotFoundError, AddChapterError

from typeclasses.readable.readable_commands import SignCmdSet
from world.crafting.junk_handlers import BaseJunkHandler


class Readable(Object):
    """
    Class for objects that can be written/named
    """

    junk_handler_class = BaseJunkHandler
    maximum_chapters = 20

    def at_object_creation(self):
        """
        Run at Place creation.
        """
        self.at_init()

    def at_after_move(self, source_location, **kwargs):
        if self.item_data.quantity > 1 and not self.written:
            self.setup_multiname()
        location = self.location
        # if location is a character, add cmdset
        if location and location.is_character:
            if self.written:
                self.cmdset.add_default(SignCmdSet, permanent=True)
        else:
            self.cmdset.delete_default()

    def return_appearance(self, *args, **kwargs):
        """Books do not use a description at all. They return their index/command help."""
        msg = self.chapter_index_display_string
        msg += f"\n{self.command_help_string}"
        return msg

    @property
    def chapter_index_display_string(self):
        if not self.written:
            return "There are no chapters added to this book yet.\n"
        msg = "Chapter Index:\n"
        for number, chapter in self.chapter_index.items():
            msg += f"({number}) {chapter.written_work.pretty_title}\n"
        return msg

    @property
    def command_help_string(self):
        msg = ""
        if self.written:
            msg += "To read a chapter from the book, use |cread <book>=<chapter>|n.\n"
        else:
            msg += "To add a chapter to the book, use |cwrite/add <book>=<story ID>,<chapter number>|n\n"
        return msg

    # noinspection PyAttributeOutsideInit
    def setup_multiname(self):
        self.key = self.generic_book_name

    @property
    def generic_book_name(self):
        if self.item_data.quantity > 1:
            return "%s books" % self.item_data.quantity
        else:
            return "book"

    @property
    def has_been_named(self):
        return self.key != self.generic_book_name

    def set_num(self, value):
        self.item_data.quantity = value
        self.setup_multiname()

    @property
    def written(self):
        return bool(self.chapter_index)

    @property
    def can_stack(self):
        return not self.written

    @CachedProperty
    def chapter_index(self):
        return {ob.number: ob for ob in self.book_chapters.all()}

    def get_chapter(self, number):
        if not number and number != 0:
            number = 1
        try:
            number = int(number)
        except (ValueError, TypeError):
            raise ChapterNotFoundError(f"Chapter index must be a number, not {number}")
        try:
            return self.chapter_index[number]
        except KeyError:
            raise ChapterNotFoundError("No chapter by that number.")

    def set_book_name(self, caller, name):
        if self.item_data.quantity > 1:
            from evennia.utils.create import create_object

            remain = self.item_data.quantity - 1
            newobj = create_object(
                typeclass="typeclasses.readable.readable.Readable",
                key="book",
                location=caller,
                home=caller,
            )
            newobj.set_num(remain)
        self.item_data.quantity = 1
        self.name = name
        self.aliases.add("book")

    def add_chapter(self, work, chapter_number):
        if work in self.chapter_index.values():
            raise AddChapterError("This work has already been added as a chapter.")
        if chapter_number in self.chapter_index.keys():
            raise AddChapterError("There is already a chapter by that number.")
        if len(self.chapter_index.values()) >= self.maximum_chapters:
            raise AddChapterError("The book has the maximum number of chapters.")
        self.book_chapters.create(number=chapter_number, written_work=work)
        # clear cache
        del self.chapter_index
