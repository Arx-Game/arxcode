"""
These managers handles the
"""

import itertools
from django.db import models
from django.db.models import Q
from django.contrib.contenttypes.models import ContentType
from src.typeclasses.managers import returns_typeclass_list, returns_typeclass

_GA = object.__getattribute__
_AccountDB = None
_ObjectDB = None
_bboardDB = None
_SESSIONS = None
_ExternalConnection = None
_User = None


#
# bboard manager
#


class BBoardManager(models.Manager):
    """
    This BBoardManager implements methods for searching
    and manipulating Bulletin Boards directly from the database.

    These methods will all return database objects
    (or QuerySets) directly.

    A Bulletin Board is an in-game venue for communication. Players
    can post messages and read messages posted by other players.

    Evennia-specific:
    get_all_bboards
    get_bboard
    del_bboard
    bboard_search

    """

    @returns_typeclass_list
    def get_all_bboards(self):
        """
        Returns all bboards in game.
        """
        return self.all()

    @returns_typeclass
    def get_bboard(self, bboardkey):
        """
        Return the bboard object if given its key.
        Also searches its aliases.
        """
        # first check the bboard key
        bboards = self.filter(db_key__iexact=bboardkey)
        if not bboards:
            # also check aliases
            bboards = [
                bboard for bboard in self.all() if bboardkey in bboard.aliases.all()
            ]
        if bboards:
            return bboards[0]
        return None

    def del_bboard(self, bboardkey):
        """
        Delete bboard matching bboardkey.
        """
        bboards = self.filter(db_key__iexact=bboardkey)
        if not bboards:
            # no aliases allowed for deletion.
            return False
        for bboard in bboards:
            bboard.delete()
        return None

    @returns_typeclass_list
    def bboard_search(self, ostring):
        """
        Search the bboard database for a particular bboard.

        ostring - the key or database id of the bboard.
        """
        bboards = []
        if not ostring:
            return bboards
        try:
            # try an id match first
            dbref = int(ostring.strip("#"))
            bboards = self.filter(id=dbref)
        except Exception:
            pass
        if not bboards:
            # no id match. Search on the key.
            bboards = self.filter(db_key__iexact=ostring)
        if not bboards:
            # still no match. Search by alias.
            bboards = [
                bboard
                for bboard in self.all()
                if ostring.lower() in [a.lower for a in bboard.aliases.all()]
            ]
        return bboards
