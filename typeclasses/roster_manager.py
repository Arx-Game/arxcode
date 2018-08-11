"""
Although not ideal, the easiest implementation of a roster
is as a physical object that can manage lists of players
and their current state. Object will either be carried
around by an administrator, or moved off the map with location=None
and only used via dbrefs/object find. It can be identified by
typeclass and/or a unique attribute to identify it
"""

#from src.comms import Msg, TempMsg, bboardDB
from typeclasses.objects import Object
from datetime import datetime
from evennia.objects.models import ObjectDB


class RosterManager(Object):
    """
    Class to store and manage the roster
    """               

    def at_object_creation(self):
        """
        Run at RosterManager creation.
        """
        self.db.active_roster = {}
        self.db.available_roster = {}
        self.db.unavailable_roster = {}
        self.db.incomplete_roster = {}
        self.db.is_roster_manager = True
        self.db.apps_manager = None

    def at_init(self):
        """
        This is always called whenever this bboard is initiated --
        that is, whenever it its typeclass is cached from memory. This
        happens on-demand first time the bboard is used or activated
        in some way after being created but also after each server
        restart or reload.
        """
        if not self.db.apps_manager:
            apps_manager = ObjectDB.objects.get_objs_with_attr("apps_manager")
            apps_manager = [ob for ob in apps_manager if ob.is_apps_manager()]
            if not apps_manager:
                self.location.msg("DEBUG: Rostermanager: Apps Manager object not found.")
                return
            if len(apps_manager) > 1:
                self.location.msg("DEBUG: Rostermanager: Warning. More than one Apps Manager object found.")
                self.db.apps_manager = apps_manager[0]
            

    def get_all_active_characters(self):
        """
        Returns all characters currently on the roster as a sorted list of names.
        """
        return sorted(self.db.active_roster.keys())

    def get_all_available_characters(self):
        """
        Returns all characters currently on the roster as a sorted list of names.
        """
        return sorted(self.db.available_roster.keys())

    def get_all_unavailable_characters(self):
        """
        Returns all characters currently on the roster as a sorted list of names.
        """
        return sorted(self.db.unavailable_roster.keys())

    def get_all_incomplete_characters(self):
        """
        Returns all characters currently on the roster as a sorted list of names.
        """
        return sorted(self.db.incomplete_roster.keys())

    def get_character(self, key):
        """
        Checks for a current character on the roster. If present,
        returns it.
        """
        key = key.lower()
        if key in self.db.active_roster:
            return self.db.active_roster[key]['charob']
        
        if key in self.db.available_roster:
            return self.db.available_roster[key]['charob']
        
        if key in self.db.unavailable_roster:
            return self.db.unavailable_roster[key]['charob']
        
        if key in self.db.incomplete_roster:
            return self.db.incomplete_roster[key]['charob']

    def find_roster_with_key(self, key):
        "Helper function to return the first roster that has a key match."
        key = key.lower()
        if key in self.db.active_roster:
            return self.db.active_roster
        
        if key in self.db.available_roster:
            return self.db.available_roster
        
        if key in self.db.unavailable_roster:
            return self.db.unavailable_roster
        
        if key in self.db.incomplete_roster:
            return self.db.incomplete_roster
        
    def get_roster_entry(self, key):
        """
        Returns the roster entry for a given character key name.
        """
        key = key.lower()
        roster = self.find_roster_with_key(key)
        if roster:
            return roster[key]

    def identify_roster(self, roster):
        """
        Returns the attribute name of a given roster.
        """
        if not roster:
            return
        if set(roster.keys()) == set(self.db.active_roster.keys()):
            return "active_roster"
        if set(roster.keys()) == set(self.db.available_roster.keys()):
            return "available_roster"
        if set(roster.keys()) == set(self.db.unavailable_roster.keys()):
            return "unavailable_roster"
        if set(roster.keys()) == set(self.db.incomplete_roster.keys()):
            return "incomplete_roster"

    def rename_entry(self, key, new_name):
        """
        Renames first entry found to a new entry in same roster.
        """
        key = key.lower()
        new_name = new_name.lower()
        roster = self.find_roster_with_key(key)
        attr = self.identify_roster(roster)
        #print "Roster is: %s" % roster
        #print "Unavail is: %s" % self.db.unavailable_roster
        #print "Equality is: %s" % str(roster == self.db.unavailable_roster)
        #print "attr is: %s" % attr
        if not attr:
            raise Exception("Roster was not identifiable.")
        if roster:
            entry = roster.pop(key)
            roster[new_name] = entry
            self.attributes.add(attr, roster)
            return entry

    def add_character(self, charobj, pobj, type = "active", roster_notes="First Added"):
        """
        Adds a new character to the roster. The character and
        player objects must both be passed, and will be checked to
        be sure they correspond.
        """
        if charobj not in pobj.db._playable_characters:
            return
        key = charobj.key.lower()
        if type == "active":
            roster = self.db.active_roster
        elif type == "available":
            roster = self.db.available_roster
        elif type == "unavailable":
            roster = self.db.unavailable_roster
        elif type == "incomplete":
            roster = self.db.incomplete_roster
        else:
            return False
        if key in roster:
            return False
        date = datetime.today().strftime("%x %X")
        email = pobj.email
        roster[key] = {'charob': charobj,
                       'playerob': pobj,
                       'date_added': date,
                       'notes': roster_notes,
                       'current_email': email,
                       'prev_emails': [] }
        return True

    def remove_character(self, key):
        """
        Remove a character from a given roster type by their key.lower
        Returns False if character isn't found. Returns the roster
        object if found.
        """
        key = key.lower()
        roster = self.find_roster_with_key(key)
        entry = None
        if roster:
            entry = roster.pop(key, None)
        return entry
        

    def mark_active(self, key, roster_notes="", new_email=None):
        """
        Checks for charcter in available/unavailable/incomplete rosters,
        and if found will add them with any notes and new player
        """
        key = key.lower()
        #first check to see if character already active
        if key in self.db.active_roster:
            return False
        pc = self.db.available_roster.pop(key, None)
        if not pc:
            pc = self.db.unavailable_roster.pop(key, None)
        if not pc:
            pc = self.db.incomplete_roster.pop(key, None)
        if not pc:
            #not found in any of our non-active rosters
            return False
        #add additional notes and set who the new player of the active character is
        if new_email:
            if not pc['prev_emails']:
                pc['prev_emails'] = []
            pc['prev_emails'].append(pc['current_email'])
            pc['current_email'] = new_email
        #roster_notes is expected to be a string of format "month/day : notes \n"
        if roster_notes:
            pc['notes'] += roster_notes
        # try to avoid caching errors by not changing attribute in-place
        roster = self.db.active_roster
        roster[key] = pc
        self.db.active_roster = roster
        return True
        
    def search_by_filters(self, list_of_filters, roster_type = "active",
                          concept="None", fealty="None", social_rank = "None",
                          family="None"):
        """
        Looks through the active characters and returns all who match
        the filters specified. Filters include: male, female, young, adult,
        mature, elder, married, single, concept, social_class, fealty, and family.
        If concept, fealty, social_class, or family are passed, it expects for the
        corresponding varaibles to be defined.
        """
        match_set = set()
        char_list = []
        roster = self.db.active_roster
        if roster_type == "available":
            roster = self.db.available_roster
        if roster_type == "unavailable":
            roster = self.db.unavailable_roster
        if roster_type == "incomplete":
            roster = self.db.incomplete_roster
        char_list = [value['charob'] for value in roster.values()]
        match_set = set(char_list)
        if not char_list:
            return
        for filter in list_of_filters:
            if filter == "male":
                for char in char_list:
                    if char.db.gender.lower() != "male":
                        match_set.discard(char)

            if filter == "female":
                for char in char_list:
                    if char.db.gender.lower() != "female":
                        match_set.discard(char)

            if filter == "young":
                for char in char_list:
                    if char.db.age > 20:
                        match_set.discard(char)

            if filter == "adult":
                for char in char_list:
                    if  char.db.age >= 40 or char.db.age < 21:
                        match_set.discard(char)

            if filter == "mature":
                for char in char_list:
                    if char.db.age < 40 or char.db.age >= 60:
                        match_set.discard(char)

            if filter == "elder":
                for char in char_list:
                    if char.db.age < 60:
                        match_set.discard(char)

            if filter == "concept":
                for char in char_list:
                    if concept.lower() not in char.db.concept.lower():
                        match_set.discard(char)

            if filter == "fealty":
                for char in char_list:
                    if fealty.lower() not in char.db.fealty.lower():
                        match_set.discard(char)

            if filter == "social rank":
                for char in char_list:
                    try:
                        if int(social_rank) != int(char.db.social_rank):
                            match_set.discard(char)
                    except:
                        match_set.discard(char)

            if filter == "married":
                for char in char_list:
                    if char.db.marital_status.lower() != "married":
                        match_set.discard(char)

            if filter == "single":
                for char in char_list:
                    if char.db.marital_status.lower() != "unmarried":
                        match_set.discard(char)

            if filter == "family":
                for char in char_list:
                    if family.lower() not in char.db.family.lower():
                        match_set.discard(char)

        return match_set

    def is_roster_manager(self):
        """
        Identifier method. All managers from object typeclass
        will have some version of this for object searches.
        """
        return True
        
    def add_entry(self, entry, type):
        """
        Adds a roster entry to the given roster.
        """
        if not entry or not type:
            return False
        type = type.strip().lower()
        key = entry['charob'].key.lower()
        if type == "active":
            self.db.active_roster[key] = entry
            return True
        if type == "available":
            self.db.available_roster[key] = entry
            return True
        if type == "unavailable":
            self.db.unavailable_roster[key] = entry
            return True
        if type == "incomplete":
            self.db.incomplete_roster[key] = entry
            return True
        return False

    def convert(self):
        from src.web.character.models import Roster
        active = Roster.objects.get(name="Active")
        avail = Roster.objects.get(name="Available")
        unavail = Roster.objects.get(name="Unavailable")
        incom = Roster.objects.get(name="Incomplete")
        targ_rosters = (active, avail, unavail, incom)
        source_rosters = (self.db.active_roster, self.db.available_roster, self.db.unavailable_roster, self.db.incomplete_roster)
        for num in range(len(source_rosters)):
            source = source_rosters[num]
            targ = targ_rosters[num]
            entries = [ob for ob in source.values() if 'charob' in ob and 'playerob' in ob]
            for entry in entries:
                char = entry['charob']
                player = entry['playerob']
                targ.entries.create(character=char.dbobj, player=player.dbobj)
                                
