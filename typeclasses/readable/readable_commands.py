from commands.base import ArxCommand
from evennia.utils.ansi import parse_ansi
from server.utils.arx_utils import sub_old_ansi
from typeclasses.readable.exceptions import ChapterNotFoundError, AddChapterError
from world.templates.exceptions import AlreadySignedError
from server.utils import arx_more
from world.templates.models import WrittenWork
from evennia.commands.cmdset import CmdSet
from evennia.utils.evtable import EvTable


class WriteCmdSet(CmdSet):
    key = "WriteCmd"
    priority = 0
    duplicates = True

    def at_cmdset_creation(self):
        """Init the cmdset"""
        self.add(CmdWrite())
        self.add(CmdRead())


class SignCmdSet(CmdSet):
    key = "SignCmd"
    priority = 0
    duplicates = True

    def at_cmdset_creation(self):
        self.add(CmdSign())


class CmdSign(ArxCommand):
    """
    Signs a document

    Usage:
        sign <chapter>

    Places your signature on a document.
    """

    key = "sign"
    locks = "cmd:all()"

    def func(self):
        try:
            caller = self.caller
            obj = self.obj
            chapter = obj.get_chapter(self.args)
            chapter.add_signature(self.caller)
            caller.msg("You sign your name on %s." % obj.name)
        except (ChapterNotFoundError, AlreadySignedError) as err:
            self.msg(err)


class CmdWrite(ArxCommand):
    """
    Write a story that can be recorded on a scroll/book/letter.

    Usage:
        write[/body] <story>
        write/title <title>
        write/proof
        write/language <language>
        write/finish
        write/listworks [<story ID>]
        write/record <book>=<new book name>
        write/add <book name>=<story ID>,<chapter number>

    Writes stories that you can then add as chapters to a book object,
    which can then be read with the 'read' command.
    To write a story, use write/title to name the story, 'write' to add
    the story's content, and then write/finish to create it. To set
    the language of the story to be something other than the default,
    use write/language to specify it.

    To add stories to a book, first name the book with write/record,
    then add chapters with write/add. For example, to rename 'a scroll'
    to 'Furen's Book of Wisdom', use 'write/record Furen's Book of Wisdom'.
    Once a book has chapters added to it, its name may no longer be
    changed.
    """

    key = "write"
    locks = "cmd:all()"
    story_switches = ("title", "proof", "language", "finish", "body")
    book_switches = ("record", "add")
    work_switches = ("listworks",)

    @property
    def draft(self):
        if self.caller.ndb.story_draft is None:
            self.caller.ndb.story_draft = WrittenWork()
        return self.caller.ndb.story_draft

    def display(self):
        msg = f"|wTitle:|n {self.draft.colored_title}\n"
        lang_string = ""
        if self.draft.language:
            lang_string = f" |w(Written in |c{self.draft.language.capitalize()}|w)|n"
        msg += f"|wBody{lang_string}:|n\n{self.draft.body}"
        return msg

    def func(self):
        """Look for object in inventory that matches args to wear"""
        try:
            if not self.switches or self.check_switches(self.story_switches):
                return self.do_story_switches()
            if self.check_switches(self.book_switches):
                return self.do_book_switches()
            if self.check_switches(self.work_switches):
                return self.do_work_switches()
            raise self.error_class("Unrecognized syntax for write.")
        except (self.error_class, AddChapterError) as err:
            self.msg(err)

    def do_story_switches(self):
        if not self.args and not self.switches:
            self.switches.append("proof")
        if not self.switches or "body" in self.switches:
            self.draft.body = self.args
        if "title" in self.switches:
            title = sub_old_ansi(self.args)
            raw_title = parse_ansi(title, strip_ansi=True)
            if WrittenWork.objects.filter(title__iexact=raw_title).exists():
                raise self.error_class(
                    "Sorry, a written work already exists with that title. "
                    "Try adding a number, (eg: 'Part II')."
                )
            self.draft.colored_title = title
            self.draft.title = raw_title
        if "language" in self.switches:
            lhs = self.lhs.lower()
            if lhs and lhs not in self.caller.languages.known_languages:
                self.msg("You cannot speak that language.")
                return
            self.draft.language = lhs
        if "finish" in self.switches:
            title = self.draft.title
            colored_title = self.draft.colored_title
            body = self.draft.body
            lang = self.draft.language or ""
            if not title:
                raise self.error_class("Still needs a title set.")
            if not body:
                raise self.error_class("Still needs a body set.")
            story = self.caller.authored_works.create(
                title=title, body=body, language=lang, colored_title=colored_title
            )
            self.msg(
                f"You have created '{story}' (#{story.id}). Use |cwrite/add|n "
                f"to add it as a chapter to a book."
            )
            del self.caller.ndb.story_draft
            return
        # "proof" switch and others fall down to here, to display progress
        self.msg(self.display(), options={"box": True})

    def do_book_switches(self):
        obj = self.search(self.lhs)
        if not obj:
            return
        try:
            is_named = obj.has_been_named
        except AttributeError:
            raise self.error_class(f"{obj} is not a book.")
        if "record" in self.switches:
            if is_named:
                raise self.error_class(f"'{obj}' has already been named.")
            obj.set_book_name(self.caller, self.rhs)
            self.msg(f"You have set the book's name to {self.rhs}.")
            return
        if "add" in self.switches:
            try:
                work_id, chapter_num = int(self.rhslist[0]), int(self.rhslist[1])
            except (ValueError, TypeError):
                raise self.error_class(
                    "Enter the ID of one of your authored works "
                    "and the chapter number to add."
                )
            work = self.get_work(work_id)
            obj.add_chapter(work, chapter_num)
            obj.cmdset.delete_default()
            obj.cmdset.add_default(SignCmdSet, permanent=True)
            self.msg(f"You have added {work} as Chapter {chapter_num}.")

    def get_work(self, work_id):
        try:
            return self.caller.authored_works.get(id=work_id)
        except (WrittenWork.DoesNotExist, TypeError, ValueError):
            raise self.error_class("You have not written a work by that ID.")

    def do_work_switches(self):
        """List all the works written by the character"""
        if self.args:
            work = self.get_work(self.args)
            self.msg(str(work.body))
            return
        table = EvTable("|wID|n", "|wTitle|n", width=78)
        qs = self.caller.authored_works.all()
        for work in qs:
            table.add_row(work.id, work.pretty_title)
        self.msg(str(table))


class CmdRead(ArxCommand):
    """
    Reads a document

    Usage:
        read <book>=<chapter>

    Reads a chapter from a document.
    """

    key = "read"
    locks = "cmd:all()"

    def func(self):
        try:
            book = self.search(self.lhs)
            if not book:
                return
            try:
                chapter = book.get_chapter(self.rhs)
            except AttributeError:
                raise ChapterNotFoundError(f"{book} is not a book.")
            if (
                chapter.written_work.language
                and chapter.written_work.language.lower()
                not in self.caller.languages.known_languages
            ):
                raise ChapterNotFoundError(
                    "That chapter is written in a language you don't understand."
                )
            arx_more.msg(self.caller, chapter.get_chapter_text())
        except ChapterNotFoundError as err:
            self.msg(err)
