"""
Arx implementation of EvMore pager

"""
from builtins import object, range

from django.conf import settings
from evennia.commands.command import Command
from evennia.commands.cmdset import CmdSet
from evennia.commands import cmdhandler
from evennia.utils.utils import justify

_CMD_NOMATCH = cmdhandler.CMD_NOMATCH
_CMD_NOINPUT = cmdhandler.CMD_NOINPUT

# we need to use NAWS for this
_SCREEN_WIDTH = settings.CLIENT_DEFAULT_WIDTH
_SCREEN_HEIGHT = settings.CLIENT_DEFAULT_HEIGHT

# text

_DISPLAY = """{text}
(|wmore|n [{pageno}/{pagemax}] |wn|next|||wb|nack|||wt|nop|||we|nnd|||wq|nuit)"""


def find_newline_seperator(text):
    seps = ("\n", "|/", "{/", "%r")
    index = -1
    for sep in seps:
        index = text.find(sep)
        if index != -1:
            return index + len(sep)
    return index


class CmdMore(Command):
    """
    Manipulate the text paging
    """

    key = _CMD_NOINPUT
    aliases = [
        "quit",
        "q",
        "abort",
        "a",
        "next",
        "n",
        "back",
        "b",
        "top",
        "t",
        "end",
        "e",
    ]
    auto_help = False

    def func(self):
        """
        Implement the command
        """
        caller = self.caller
        more = caller.ndb._more
        if not more and hasattr(self.caller, "player"):
            caller = caller.player
            more = caller.ndb._more
        if not more:
            caller.cmdset.remove("more_commands")
            return

        cmd = self.cmdstring

        if cmd in ("abort", "a", "q", "quit", "abort"):
            more.page_quit()
        elif cmd in ("back", "b"):
            more.page_back()
        elif cmd in ("top", "t"):
            more.page_top()
        elif cmd in ("end", "e"):
            more.page_end()
        else:
            # return or n, next
            more.page_next()


class CmdMoreLook(Command):
    """
    Override look to display window and prevent OOCLook from firing
    """

    key = "look"
    aliases = ["l"]
    auto_help = False

    def func(self):
        """
        Implement the command
        """
        caller = self.caller
        more = caller.ndb._more
        if not more and hasattr(self.caller, "player"):
            caller = caller.player
            more = caller.ndb._more
        if not more:
            caller.cmdset.remove("more_commands")
            return
        more.display()


class CmdSetMore(CmdSet):
    """
    Stores the more command
    """

    key = "more_commands"
    priority = 110

    def at_cmdset_creation(self):
        self.add(CmdMore())
        self.add(CmdMoreLook())


class EvMore(object):
    """
    The main pager object
    """

    def __init__(
        self,
        caller,
        text,
        always_page=False,
        session=None,
        justify_kwargs=None,
        **kwargs
    ):
        """
        Initialization of the text handler.

        Args:
            caller (Object or Player): Entity reading the text.
            text (str): The text to put under paging.
            always_page (bool, optional): If `False`, the
                pager will only kick in if `text` is too big
                to fit the screen.
            session (Session, optional): If given, this session will be used
                to determine the screen width and will receive all output.
            justify_kwargs (dict, bool or None, optional): If given, this should
                be valid keyword arguments to the utils.justify() function. If False,
                no justification will be done.
            kwargs (any, optional): These will be passed on
                to the `caller.msg` method.

        """
        self._caller = caller
        self._kwargs = kwargs
        self._pages = []
        self._npages = []
        self._npos = []
        self._exit_msg = "Exited |wmore|n pager."
        if not session:
            # if not supplied, use the first session to
            # determine screen size
            sessions = caller.sessions.get()
            if not sessions:
                return
            session = sessions[0]
        self._session = session
        text = caller.strip_ascii_from_tags(text)

        # set up individual pages for different sessions
        height = max(
            4, session.protocol_flags.get("SCREENHEIGHT", {0: _SCREEN_HEIGHT})[0] - 4
        )
        width = session.protocol_flags.get("SCREENWIDTH", {0: _SCREEN_WIDTH})[0]

        pages_by_char = kwargs.pop("pages_by_char", False)
        if pages_by_char:
            PAGE_LENGTH = 3000
            MARGIN = 1000
            while len(text) > PAGE_LENGTH:
                index = find_newline_seperator(text[PAGE_LENGTH : PAGE_LENGTH + MARGIN])
                sep = PAGE_LENGTH + index
                self._pages.append(text[:sep])
                text = "\n" + text[sep:]
            self._pages.append(text)
        else:
            if justify_kwargs is False:
                # no justification. Simple division by line
                lines = text.split("\n")
            else:
                # we must break very long lines into multiple ones
                justify_kwargs = justify_kwargs or {}
                width = justify_kwargs.get("width", width)
                justify_kwargs["width"] = width
                justify_kwargs["align"] = justify_kwargs.get("align", "l")
                justify_kwargs["indent"] = justify_kwargs.get("indent", 0)

                lines = justify(text, **justify_kwargs).split("\n")

            # always limit number of chars to 10 000 per page
            height = min(10000 // width, height)
            self._pages = [
                "\n".join(lines[i : i + height]) for i in range(0, len(lines), height)
            ]
        self._npages = len(self._pages)
        self._npos = 0
        if self._npages <= 1 and not always_page:
            # no need for paging; just pass-through.
            caller.msg(text=text, **kwargs)
        else:
            # go into paging mode
            # first pass on the msg kwargs
            caller.ndb._more = self
            caller.cmdset.add(CmdSetMore)

            # goto top of the text
            self.page_top()

    def display(self):
        """
        Pretty-print the page.
        """
        pos = self._pos
        text = self._pages[pos]
        page = _DISPLAY.format(text=text, pageno=pos + 1, pagemax=self._npages)
        if not page or not text:
            self.page_quit()
        # check for wrong session
        self._caller.msg(text=page, **self._kwargs)

    def page_top(self):
        """
        Display the top page
        """
        self._pos = 0
        self.display()

    def page_end(self):
        """
        Display the bottom page.
        """
        self._pos = self._npages - 1
        self.display()

    def page_next(self):
        """
        Scroll the text to the next page. Quit if already at the end
        of the page.
        """
        if self._pos >= self._npages - 1:
            # exit if we are already at the end
            self.page_quit()
        else:
            self._pos += 1
            self.display()

    def page_back(self):
        """
        Scroll the text back up, at the most to the top.
        """
        self._pos = max(0, self._pos - 1)
        self.display()

    def page_quit(self):
        """
        Quit the pager
        """
        del self._caller.ndb._more
        self._caller.msg(text=self._exit_msg, **self._kwargs)
        self._caller.cmdset.remove(CmdSetMore)


def msg(
    caller, text="", always_page=False, session=None, justify_kwargs=None, **kwargs
):
    """
    More-supported version of msg, mimicking the normal msg method.

    Args:
        caller (Object or Player): Entity reading the text.
        text (str): The text to put under paging.
        always_page (bool, optional): If `False`, the
            pager will only kick in if `text` is too big
            to fit the screen.
        session (Session, optional): If given, this session will be used
            to determine the screen width and will receive all output.
        justify_kwargs (dict, bool or None, optional): If given, this should
            be valid keyword arguments to the utils.justify() function. If False,
            no justification will be done.
        kwargs (any, optional): These will be passed on
            to the `caller.msg` method.

    """
    EvMore(
        caller,
        text,
        always_page=always_page,
        session=session,
        justify_kwargs=justify_kwargs,
        **kwargs
    )
