"""
Commands for searching the lore knowledge base and for asking a question that then becomes
part of the knowledge base.
"""
from django.db.models import Q

from commands.base import ArxPlayerCommand
from web.helpdesk.models import KBItem, KBCategory, Ticket
from server.utils import helpdesk_api


SEP = "{C" + "-" * 78 + "{n"


class CmdLoreSearch(ArxPlayerCommand):
    """
    View the Lore/Theme Knowledge Base or ask a question to be added

    Usage:
        lore [<entry or category name>]
        lore/search <keyword or phrase>
        lore/request <category>/<entry title>=[question to be answered]

    The Lore/Theme Knowledge Base is a list of answers to questions
    about the setting of the game, from the perspective of things that
    characters would be expected to already know. Without arguments, the
    command will list the main KB categories. You can view a category or item
    by the title of that item or category, or do a search to try to find any
    matches of a keyword or phrase.

    If there isn't a clear answer to a question on theme, you can create a
    new theme question by issuing a lore/request about your question, which
    creates a ticket for review.
    """
    key = "lore"
    aliases = ["theme"]
    help_category = "Information"

    def func(self):
        """Executes Lore cmd"""
        try:
            if not self.args:
                return self.display_main_categories()
            if not self.switches:
                return self.display_category_or_entry()
            if "search" in self.switches:
                return self.search_knowledge_base()
            if "request" in self.switches:
                return self.create_lore_question()
            raise self.error_class("Invalid switch.")
        except self.error_class as err:
            self.msg(err)

    def display_main_categories(self):
        """Displays the main categories for no input"""
        msg = SEP + "\n|CMain Categories:|n\n" + SEP + "\n\n"
        cat_names = KBCategory.objects.filter(parent__isnull=True).values_list('title', flat=True)
        msg += "|w" + ", ".join(cat_names)
        self.msg(msg)

    def display_category_or_entry(self):
        """Display a category and/or an entry that's found"""
        category = item = None
        try:
            category = KBCategory.objects.get(title__iexact=self.args)
        except KBCategory.DoesNotExist:
            pass
        try:
            item = KBItem.objects.get(title__iexact=self.args)
        except KBItem.DoesNotExist:
            pass
        msg = ""
        if category:
            msg += category.display()
        if item:
            if msg:
                msg += "\n"
            msg += item.display()
        if not item and not category:
            raise self.error_class("No matches for either a category or entry by that name in the knowledge base.")
        self.msg(msg)

    def search_knowledge_base(self):
        """Performs a search for a term given by the player"""
        search_tag_query = Q(search_tags__name__iexact=self.args)
        categories = KBCategory.objects.filter(Q(title__icontains=self.args) | Q(description__icontains=self.args) |
                                               search_tag_query).distinct()
        entries = KBItem.objects.filter(Q(title__icontains=self.args) | Q(question__icontains=self.args) |
                                        Q(answer__icontains=self.args) | search_tag_query).distinct()
        disco_query = Q(name__icontains=self.args) | Q(desc__icontains=self.args) | search_tag_query
        try:
            clues = self.caller.roster.clues.filter(disco_query).distinct()
        except AttributeError:
            clues = []
        try:
            revelations = self.caller.roster.revelations.filter(disco_query).distinct()
        except AttributeError:
            revelations = []
        msg = ""
        if categories:
            msg += "|wCategories:|n %s\n" % ", ".join(str(ob) for ob in categories)
        if entries:
            msg += "|wEntries:|n %s\n" % ", ".join(str(ob) for ob in entries)
        if clues:
            msg += "|wClues:|n %s\n" % ", ".join(str(ob) for ob in clues)
        if revelations:
            msg += "|wRevelations:|n %s\n" % ", ".join(str(ob) for ob in revelations)
        if not msg:
            msg = "No matches found for '%s'." % self.args
        else:
            msg = ("Matches for '%s':\n" % self.args) + msg
        self.msg(msg)

    def create_lore_question(self):
        """Submits a ticket as a new theme question"""
        try:
            category, title = self.lhs.split("/")
            category = KBCategory.objects.get(title__iexact=category)
        except ValueError:
            raise self.error_class("You must specify both a category and a "
                                   "title for the entry created by your question.")
        except KBCategory.DoesNotExist:
            raise self.error_class("No category by that title.")
        if KBItem.objects.filter(title__iexact=title).exists():
            raise self.error_class("There is already an entry with that title.")
        if Ticket.objects.filter(title__iexact=title).exists():
            raise self.error_class("An entry is already proposed with that title.")
        if not self.rhs:
            raise self.error_class("You must enter a question about lore or theme for staff to answer.")
        ticket = helpdesk_api.create_ticket(self.caller, self.rhs, kb_category=category, queue_slug="Theme",
                                            optional_title=title)
        self.msg("You have created ticket %s, asking: %s" % (ticket.id, self.rhs))
