"""
tests for lore commands
"""
from server.utils.test_utils import ArxCommandTest
from web.helpdesk import lore_commands
from web.helpdesk.models import KBCategory, KBItem, Queue


class TestLoreCommands(ArxCommandTest):
    def setUp(self):
        super(TestLoreCommands, self).setUp()
        self.cat1 = KBCategory.objects.create(
            title="religion stuff", slug="religion", description="religion desc"
        )
        self.cat2 = KBCategory.objects.create(
            title="culture stuff", slug="culture", description="culture desc"
        )
        self.subcat1 = KBCategory.objects.create(
            title="faith stuff",
            slug="faith",
            description="faith desc",
            parent=self.cat1,
        )
        self.subcat2 = KBCategory.objects.create(
            title="god stuff", slug="gods", description="gods desc", parent=self.cat1
        )
        self.item1 = KBItem.objects.create(
            title="priests",
            question="can priests marry",
            answer="lol no",
            category=self.cat1,
        )
        self.item2 = KBItem.objects.create(
            title="archfiends", question="wat dis", answer="bad", category=self.subcat2
        )
        self.item3 = KBItem.objects.create(
            title="skald", question="who dis", answer="newgod", category=self.subcat2
        )
        self.queue = Queue.objects.create(slug="Theme", title="Theme Questions")

    def test_cmd_lore(self):
        from server.utils.helpdesk_api import resolve_ticket

        self.setup_cmd(lore_commands.CmdLoreSearch, self.account)
        default_display = "Main Categories:\n\n\nculture stuff, religion stuff"
        self.call_cmd("", default_display)
        self.call_cmd(
            "foo",
            "No matches for either a category or entry by that name in the knowledge base.",
        )
        self.call_cmd(
            "religion stuff",
            "religion stuff\nDescription: religion desc\n"
            "Subcategories: faith stuff, god stuff\nEntries: priests",
        )
        self.call_cmd(
            "skald", "skald\nCategory: god stuff\nQuestion: who dis\nAnswer: newgod"
        )
        self.call_cmd("/search dis", "Matches for 'dis':\nEntries: archfiends, skald")
        self.call_cmd("/search asfd", "No matches found for 'asfd'.")
        self.call_cmd(
            "/request sdf",
            "You must specify both a category and a "
            "title for the entry created by your question.",
        )
        self.call_cmd("/request asdf/asdf", "No category by that title.")
        self.call_cmd(
            "/request religion stuff/priests",
            "There is already an entry with that title.",
        )
        self.call_cmd(
            "/request religion stuff/gongs",
            "You must enter a question about " "lore or theme for staff to answer.",
        )
        self.call_cmd(
            "/request religion stuff/gongs=how u gong fish?",
            "You have new informs. Use @inform 1 to read them.|"
            "You have created ticket 1, asking: how u gong fish?",
        )
        ticket = self.queue.ticket_set.first()
        self.assertEqual(ticket.title, "gongs")
        item = resolve_ticket(self.account2, ticket, "rly hard")
        self.assertEqual(item.title, "gongs")
        self.assertEqual(item.category, self.cat1)
        self.assertEqual(item.question, "how u gong fish?")
        self.assertEqual(item.answer, "rly hard")
