"""
Handler for Journals
"""

from world.msgs.handler_mixins.msg_utils import get_initial_queryset, lazy_import_from_str
from world.msgs.handler_mixins.handler_base import MsgHandlerBase
from world.msgs.managers import (
    WHITE_TAG,
    BLACK_TAG,
    RELATIONSHIP_TAG,
    q_search_text_body,
    q_receiver_character_name,
)

from server.utils.arx_utils import get_date, create_arx_message


class JournalHandler(MsgHandlerBase):
    def __init__(self, obj=None):
        """
        We'll be doing a series of delayed calls to set up the various
        attributes in the MessageHandler, since we can't have ObjectDB
        refer to Msg during the loading-up process.
        """
        super(JournalHandler, self).__init__(obj)
        # White Journal entries that obj has written
        self._white_journal = None
        # Black Journal entries that obj has written
        self._black_journal = None
        # Relationships obj has written in their White Journal
        self._white_relationships = None
        # Relationships obj has written in their Black Journal
        self._black_relationships = None

    @property
    def white_journal(self):
        if self._white_journal is None:
            self.build_whitejournal()
        return self._white_journal

    @white_journal.setter
    def white_journal(self, value):
        self._white_journal = value

    @property
    def black_journal(self):
        if self._black_journal is None:
            self.build_blackjournal()
        return self._black_journal

    @black_journal.setter
    def black_journal(self, value):
        self._black_journal = value

    @property
    def white_relationships(self):
        if self._white_relationships is None:
            self.build_relationshipdict(True)
        return self._white_relationships

    @white_relationships.setter
    def white_relationships(self, value):
        self._white_relationships = value

    @property
    def black_relationships(self):
        if self._black_relationships is None:
            self.build_relationshipdict(False)
        return self._black_relationships

    @black_relationships.setter
    def black_relationships(self, value):
        self._black_relationships = value

    def build_relationshipdict(self, white=True):
        """
        Builds a dictionary of names of people we have relationships with to a list
        of relationship Msgs we've made about that character.
        """
        rels = get_initial_queryset("Journal").relationships().written_by(self.obj)
        if white:
            rels = rels.white()
        else:
            rels = rels.black()
        relsdict = {}
        for rel in rels:
            if rel.db_receivers_objects.all():
                name = rel.db_receivers_objects.all()[0].key.lower()
                relslist = relsdict.get(name, [])
                relslist.append(rel)
                relsdict[name] = relslist
        if white:
            self._white_relationships = relsdict
        else:
            self._black_relationships = relsdict
        return relsdict

    def build_whitejournal(self):
        """
        Returns a list of all 'white journal' entries our character has written.
        """
        self._white_journal = list(
            get_initial_queryset("Journal").written_by(self.obj).white()
        )
        return self._white_journal

    def build_blackjournal(self):
        """
        Returns a list of all 'black journal' entries our character has written.
        """
        self._black_journal = list(
            get_initial_queryset("Journal").written_by(self.obj).black()
        )
        return self._black_journal

    def add_to_journals(self, msg, white=True):
        """adds message to our journal"""
        if not white:
            msg.add_black_locks()
            if msg not in self.black_journal:
                self.black_journal.insert(0, msg)
        else:
            if msg not in self.white_journal:
                self.white_journal.insert(0, msg)
        return msg

    def add_journal(self, msg, white=True, date=""):
        """creates a new journal message and returns it"""
        cls = lazy_import_from_str("Journal")
        if not date:
            date = get_date()
        header = self.create_date_header(date)
        j_tag = WHITE_TAG if white else BLACK_TAG
        msg = create_arx_message(
            self.obj,
            msg,
            receivers=self.obj.player_ob,
            header=header,
            cls=cls,
            tags=j_tag,
        )
        msg = self.add_to_journals(msg, white)
        # journals made this week, for xp purposes
        self.num_journals += 1
        return msg

    def add_event_journal(self, event, msg, white=True, date=""):
        """Creates a new journal about event and returns it"""
        msg = self.add_journal(msg, white, date)
        tagkey = event.name.lower()
        category = "event"
        data = str(event.id)
        msg.tags.add(tagkey, category=category, data=data)
        return msg

    def add_relationship(self, msg, targ, white=True, date=""):
        """creates a relationship and adds relationship to our journal"""
        cls = lazy_import_from_str("Journal")
        if not date:
            date = get_date()
        header = self.create_date_header(date)
        name = targ.key.lower()
        receivers = [targ, self.obj.player_ob]
        tags = (WHITE_TAG if white else BLACK_TAG, RELATIONSHIP_TAG)
        msg = create_arx_message(
            self.obj, msg, receivers=receivers, header=header, cls=cls, tags=tags
        )
        msg = self.add_to_journals(msg, white)
        rels = self.white_relationships if white else self.black_relationships
        relslist = rels.get(name, [])
        if msg not in relslist:
            relslist.insert(0, msg)
        rels[name] = relslist
        # number of relationship updates this week, for xp purposes
        self.num_rel_updates += 1
        return msg

    def search_journal(self, text):
        """
        Returns all matches for text in character's journal
        """
        Journal = lazy_import_from_str("Journal")
        matches = (
            Journal.white_journals.written_by(self.obj)
            .filter(q_receiver_character_name(text) | q_search_text_body(text))
            .distinct()
        )

        return list(matches)

    def size(self, white=True):
        if white:
            return len(self.white_journal)
        else:
            return len(self.black_journal)

    @property
    def num_journals(self):
        return self.obj.db.num_journals or 0

    @num_journals.setter
    def num_journals(self, val):
        self.obj.db.num_journals = val

    @property
    def num_rel_updates(self):
        return self.obj.db.num_rel_updates or 0

    @num_rel_updates.setter
    def num_rel_updates(self, val):
        self.obj.db.num_rel_updates = val

    def convert_short_rel_to_long_rel(self, character, rel_key, white=True):
        """
        Converts a short relationship held in our self.obj to a
        long relationship instead.
        :type character: ObjectDB
        :type rel_key: str
        :type white: bool
        """
        entry_list = self.obj.db.relationship_short[rel_key]
        found_entry = None
        for entry in entry_list:
            if entry[0].lower() == character.key.lower():
                found_entry = entry
                break
        entry_list.remove(found_entry)
        if not entry_list:
            del self.obj.db.relationship_short[rel_key]
        else:
            self.obj.db.relationship_short[rel_key] = entry_list
        msg = found_entry[1]
        self.add_relationship(msg, character, white=white)

    def delete_journal(self, msg):
        if msg in self.white_journal:
            self.white_journal.remove(msg)
        if msg in self.black_journal:
            self.black_journal.remove(msg)
        for rel_list in self.white_relationships.values():
            if msg in rel_list:
                rel_list.remove(msg)
        for rel_list in self.black_relationships.values():
            if msg in rel_list:
                rel_list.remove(msg)
        msg.delete()

    def convert_to_black(self, msg):
        """
        Converts a given white journal to a black journal
        Args:
            msg: The msg to convert
        """
        self.white_journal.remove(msg)
        msg.convert_to_black()
        self.add_to_journals(msg, white=False)

    def convert_to_white(self, msg):
        """
        Converts a black journal to a white journal
        Args:
            msg: The msg to convert
        """
        self.black_journal.remove(msg)
        msg.convert_to_white()
        self.add_to_journals(msg)

    def disp_entry_by_num(self, num=1, white=True, caller=None):
        if white:
            journal = self.white_journal
            jname = "white journal"
        else:
            journal = self.black_journal
            jname = "black reflection"
        msg = "Message {w#%s{n for {c%s{n's %s:\n" % (num, self.obj, jname)
        num -= 1
        entry = journal[num]
        if caller and not white:
            if not entry.access(caller, "read"):
                return False
        # noinspection PyBroadException
        try:
            subjects = entry.db_receivers_objects.all()
            if subjects:
                msg += "Written about: {c%s{n\n" % ", ".join(ob.key for ob in subjects)
            msg += self.disp_entry(entry)
            # mark the player as having read this
            if caller:
                if caller.player_ob:
                    caller = caller.player_ob
                entry.receivers = caller
        except Exception:  # Catch possible database errors, or bad formatting, etc
            import traceback

            traceback.print_exc()
            msg = "Error in retrieving journal. It may have been deleted and the server has not yet synchronized."
        return msg
