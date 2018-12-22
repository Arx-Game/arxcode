"""
Messagehandler

This handler takes either a AccountDB or ObjectDB object and
processes the Msg objects they have in their related sets.
Msg() objects will be distinguished in how they function based
on their header field, which we'll parse and process here. The
header field will be a list of key:value pairs, separated by
semicolons.
"""

from .handler_mixins import messengerhandler, journalhandler, msg_utils
from web.character.models import Clue


class MessageHandler(messengerhandler.MessengerHandler, journalhandler.JournalHandler):
    """Handler for most messages"""
    def __init__(self, obj=None):
        """
        We'll be doing a series of delayed calls to set up the various
        attributes in the MessageHandler, since we can't have ObjectDB
        refer to Msg during the loading-up process.
        """
        # the ObjectDB instance
        super(MessageHandler, self).__init__(obj)
        # comments that obj has received about it
        self._rumors = None
        self._gossip = None
        self._visions = None
        self._secrets = None

    @property
    def rumors(self):
        if self._rumors is None:
            self.build_rumorslist()
        return self._rumors

    @property
    def gossip(self):
        if self._gossip is None:
            self.build_gossiplist()
        return self._gossip

    @property
    def visions(self):
        """Visions received by the character"""
        if self._visions is None:
            self.build_visionslist()
        return self._visions

    @property
    def secrets(self):
        """Secrets written for the character"""
        if self._secrets is None:
            self.build_secretslist()
        return self._secrets

    # ---------------------------------------------------------
    # Setup/building methods
    # ---------------------------------------------------------

    def build_rumorslist(self):
        """
        Returns a list of all rumor entries which we've heard (marked as a receiver for)
        """
        self._rumors = list(msg_utils.get_initial_queryset("Rumor").about_character(self.obj))
        return self._rumors

    def build_gossiplist(self):
        """
        Returns a list of all gossip entries we've heard (marked as a receiver for)
        """
        if self.obj.player_ob:
            self._gossip = list(msg_utils.get_initial_queryset("Rumor").all_read_by(self.obj.player_ob))
        else:
            self._gossip = self.build_rumorslist()

    def build_visionslist(self):
        """
        Returns a list of all visions this character has received. Does not include visions shared with them.
        """

        # only visions that have been sent directly to us, not ones shared with us
        self._visions = list(self.obj.roster.clue_discoveries.filter(clue__clue_type=Clue.VISION,
                                                                     discovery_method__in=("original receiver",
                                                                                           "Prior Knowledge")))
        return self._visions

    def build_secretslist(self):
        """
        Returns a list of all secrets the character has had written by GMs. Does not include ones
        shared with them.
        """
        self._secrets = list(self.obj.secrets)
        return self._secrets

    # --------------------------------------------------------------
    # API/access methods
    # --------------------------------------------------------------

    def add_vision(self, msg, sender, name, vision_obj=None):
        """adds a vision sent by a god or whatever"""
        from web.character.models import Clue
        if not vision_obj:
            vision_obj = Clue(desc=msg, name=name, rating=25, author=sender.roster, clue_type=Clue.VISION)
            vision_obj.save()
        if vision_obj not in self.obj.roster.clues.all():
            self.obj.roster.discover_clue(vision_obj, message=msg, method="original receiver")
        self._visions = None  # clear cache
        return vision_obj

    # ---------------------------------------------------------------------
    # Display methods
    # ---------------------------------------------------------------------

    @property
    def num_flashbacks(self):
        """Flashbacks written by the player"""
        return self.obj.db.num_flashbacks or 0

    @num_flashbacks.setter
    def num_flashbacks(self, val):
        self.obj.db.num_flashbacks = val

    @property
    def num_weekly_journals(self):
        """Number of journal-type things that count for xp"""
        return self.num_journals + self.num_rel_updates + self.num_flashbacks

    def reset_journal_count(self):
        """Resetting our count of things which count for xp"""
        self.num_journals = 0
        self.num_rel_updates = 0
        self.num_flashbacks = 0

    def get_secret_display(self, secret_number, show_gm_notes=False):
        """
        Gets the display of a given secret
        Args:
            secret_number(int): ID of the clue (not clue discovery)
            show_gm_notes(bool): Whether to show gm notes

        Returns:
            String display of the given clue, or an error message.
        """
        return self.get_clue_display("secrets", secret_number, show_gm_notes)

    def get_vision_display(self, vision_number, show_gm_notes=False):
        """
        Gets the display of a given vision
        Args:
            vision_number(int): ID of the clue (not clue discovery)
            show_gm_notes(bool): Whether to show gm notes

        Returns:
            String display of the given clue, or an error message.
        """
        return self.get_clue_display("visions", vision_number, show_gm_notes)

    def get_clue_display(self, attr, clue_number, show_gm_notes=False):
        """
        Gets the display of a clue of the given attr type and clue_number
        Args:
            attr(str): secrets or visions, the attribute we're fetching
            clue_number: A key for a dict of clue IDs. string or int
            show_gm_notes(bool): Whether to show gm notes

        Returns:
            ClueDiscovery.display of the given clue_number.
        """

        try:
            return self.get_clue_by_id(clue_number, attr).display(show_gm_notes=show_gm_notes)
        except (KeyError, ValueError, TypeError):
            msg = "You must provide a valid ID number.\n"
            return msg + self.display_clue_table(attr)

    def get_clue_by_id(self, clue_number, attr="secrets"):
        """
        Gets a clue discovery from one of our cached lists by the name of the attribute
        Args:
            clue_number: ID of the clue (not the clue discovery object)
            attr: The name of the attribute (secrets, visions, etc)

        Returns:
            A clue discovery object corresponding to the clue ID.
        Raises:
            KeyError if clue_number isn't found, ValueError/TypeError if clue_number isn't a number
        """
        discos = {ob.clue.id: ob for ob in getattr(self, attr)}
        return discos[int(clue_number)]

    def get_secrets_list_display(self):
        return self.display_clue_table("secrets")

    def get_vision_list_display(self):
        return self.display_clue_table("visions")

    def display_clue_table(self, attr):
        """
        Returns a string of a PrettyTable of clues
        Args:
            attr(str): secrets or visions, the attribute we're fetching

        Returns:
            A string of a PrettyTable for those ClueDiscoveries
        """
        from server.utils.prettytable import PrettyTable
        table = PrettyTable(["{w#", "{wName", "{wDate:"])
        for ob in getattr(self, attr):
            name = ob.name
            if len(name) > 35:
                name = name[:32] + "..."
            table.add_row([ob.clue.id, name, ob.date.strftime("%x")])
        return str(table)
