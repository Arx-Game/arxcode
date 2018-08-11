"""
Managers for the Character app. The ArxRosterManager was written as a replacement for a roster manager that
originally was an ObjectDB typeclass that stored roster entries as lists/dicts in Attributes.
"""
from django.db import models


class ArxRosterManager(models.Manager):
    """
    Manager for the game's Roster. A lot of our methods will actually retrieve Character/ObjectDB instances
    for convenience.
    """
    @property
    def active(self):
        """Gets our Active roster"""
        return self.get(name="Active")
    
    @property
    def available(self):
        """Gets our Available roster"""
        return self.get(name="Available")
    
    @property
    def unavailable(self):
        """Gets our Unavailable roster"""
        return self.get(name="Unavailable")
    
    @property
    def incomplete(self):
        """Gets our Incomplete roster"""
        return self.get(name="Incomplete")

    def get_all_active_characters(self):
        """Gets a queryset of all character objects in our Active roster"""
        from evennia.objects.models import ObjectDB
        return ObjectDB.objects.select_related('roster__roster').filter(roster__roster=self.active).order_by('db_key')
    
    def get_all_available_characters(self):
        """Gets a queryset of all character objects in our Available roster"""
        from evennia.objects.models import ObjectDB
        return ObjectDB.objects.select_related('roster__roster').filter(
            roster__roster=self.available).order_by('db_key')
    
    def get_all_unavailable_characters(self):
        """Gets a queryset of all character objects in our Unavailable roster"""
        from evennia.objects.models import ObjectDB
        return ObjectDB.objects.select_related('roster__roster').filter(
            roster__roster=self.unavailable).order_by('db_key')
    
    def get_all_incomplete_characters(self):
        """Gets a queryset of all character objects in our Incomplete roster"""
        from evennia.objects.models import ObjectDB
        return ObjectDB.objects.select_related('roster__roster').filter(
            roster__roster=self.incomplete).order_by('db_key')

    @staticmethod
    def get_character(name):
        """Gets a character by name"""
        from evennia.objects.models import ObjectDB
        try:
            return ObjectDB.objects.get(db_key__iexact=name, roster__roster__isnull=False)
        except ObjectDB.DoesNotExist:
            return None

    @staticmethod
    def search_by_filters(list_of_filters, roster_type="active",
                          concept="None", fealty="None", social_rank="None",
                          family="None"):
        """
        Looks through the active characters and returns all who match
        the filters specified. Filters include: male, female, young, adult,
        mature, elder, married, single, concept, social_class, fealty, and family.
        If concept, fealty, social_class, or family are passed, it expects for the
        corresponding variables to be defined.
        """
        from evennia.objects.models import ObjectDB
        char_list = ObjectDB.objects.filter(roster__roster__name__iexact=roster_type)
        match_set = set(char_list)
        if not char_list:
            return
        for char_filter in list_of_filters:
            if char_filter == "male":
                for char in char_list:
                    if not char.db.gender or char.db.gender.lower() != "male":
                        match_set.discard(char)
            if char_filter == "female":
                for char in char_list:
                    if not char.db.gender or char.db.gender.lower() != "female":
                        match_set.discard(char)
            if char_filter == "young":
                for char in char_list:
                    if not char.db.age or char.db.age > 20:
                        match_set.discard(char)
            if char_filter == "adult":
                for char in char_list:
                    if not char.db.age or char.db.age >= 40 or char.db.age < 21:
                        match_set.discard(char)
            if char_filter == "mature":
                for char in char_list:
                    if not char.db.age or char.db.age < 40 or char.db.age >= 60:
                        match_set.discard(char)
            if char_filter == "elder":
                for char in char_list:
                    if not char.db.age or char.db.age < 60:
                        match_set.discard(char)
            if char_filter == "concept":
                for char in char_list:
                    if not char.db.concept or concept.lower() not in char.db.concept.lower():
                        match_set.discard(char)
            if char_filter == "fealty":
                for char in char_list:
                    if not char.db.fealty or fealty.lower() not in char.db.fealty.lower():
                        match_set.discard(char)
            if char_filter == "social rank":
                for char in char_list:
                    try:
                        if int(social_rank) != int(char.db.social_rank):
                            match_set.discard(char)
                    except (TypeError, ValueError, AttributeError):
                        match_set.discard(char)
            if char_filter == "married":
                for char in char_list:
                    if not char.db.marital_status or char.db.marital_status.lower() != "married":
                        match_set.discard(char)
            if char_filter == "single":
                for char in char_list:
                    if not char.db.marital_status or char.db.marital_status.lower() != "unmarried":
                        match_set.discard(char)
            if char_filter == "family":
                for char in char_list:
                    if not char.db.family or family.lower() not in char.db.family.lower():
                        match_set.discard(char)
        return match_set
        
        
class AccountHistoryManager(models.Manager):
    """
    Manager for AccountHistory. We'll use it to grab stuff related to first impressions.
    """
    def claimed_impressions(self, entry):
        """
        Gets AccountHistories that entry has written first impressions on
        
            Args:
                entry: RosterEntry object we're checking
                
            Returns:
                QuerySet of AccountHistory objects that entry has already claimed first impressions on
        """
        return self.filter(entry=entry).last().contacts.all()
    
    def unclaimed_impressions(self, entry):
        """
        Gets AccountHistory objects that are valid for entry to write first impressions on
        
            Args:
                entry: RosterEntry object we're checking
                
            Returns:
                QuerySet of AccountHistory objects that can be targeted for firstimpressions
        """
        qs = self.filter(entry__roster__name="Active", end_date__isnull=True).exclude(
            account=entry.current_account)
        qs = qs.exclude(id__in=self.claimed_impressions(entry))
        return qs.distinct()
