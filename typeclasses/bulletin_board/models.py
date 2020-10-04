"""
Model for bulletin boards. Not quite represented by object
typeclass due to having no in-game physical representation,
and not quite easily mapped to channel or msg either.
Essentially just a list of messages for players to read and
post as they like.
"""

from datetime import datetime
from django.conf import settings
from django.db import models
from src.typeclasses.models import (
    TypedObject,
    TagHandler,
    AttributeHandler,
    AliasHandler,
)
from src.utils.idmapper.models import SharedMemoryModel
from src.locks.lockhandler import LockHandler
from src.utils import logger
from src.utils.utils import is_iter, to_str, crop, make_iter
from game.gamesrc.objects.bulletin_board import managers

__all__ = "bboardDB"

_GA = object.__getattribute__
_SA = object.__setattr__
_DA = object.__delattr__


# ------------------------------------------------------------
#
# bboard
#
# ------------------------------------------------------------


class bboardDB(TypedObject):
    """
    This is the basis of a comm bboard, only implementing
    the very basics of distributing messages.

    The bboard class defines the following properties:
      key - main name for bboard
      desc - optional description of bboard
      aliases - alternative names for the bboard
      keep_log - bool if the bboard should remember messages
      permissions - perm strings

    """

    # Database manager
    objects = managers.BBoardManager()

    # not currently set up to allow inheritance of new BBoard, can change later
    _typeclass_paths = "game.gamesrc.objects.bulletin_board.bboard.BBoard"
    _default_typeclass_path = "game.gamesrc.objects.bulletin_board.bboard.BBoard"

    def __init__(self, *args, **kwargs):
        TypedObject.__init__(self, *args, **kwargs)
        _SA(self, "tags", TagHandler(self, category_prefix="bboard_"))
        _SA(self, "aliases", AliasHandler(self, category_prefix="bboard_"))
        _SA(self, "attributes", AttributeHandler(self))

    class Meta:
        "Define Django meta options"
        verbose_name = "bboard"
        verbose_name_plural = "bboards"

    #
    # bboard class methods
    #

    def __str__(self):
        return "bboard '%s' (%s)" % (self.key, self.typeclass.db.desc)

    def delete(self):
        "Clean out all connections to this bboard and delete it."
        super(bboardDB, self).delete()

    def access(self, accessing_obj, access_type="read", default=False):
        """
        Determines if another object has permission to access.
        accessing_obj - object trying to access this one
        access_type - type of access sought
        default - what to return if no lock of access_type was found
        """
        return self.locks.check(accessing_obj, access_type=access_type, default=default)

    def post(self, pobj, msg, subject="No Subject", poster_name=None):
        if access(pobj, access_type="write", default=False):
            return self.typeclass.bb_post(pobj, msg, subject, poster_name)
        else:
            return False
        pass

    def subscribe(self, pobj):
        if access(pobj):
            return self.typeclass.subscribe_bboard(pobj)
        else:
            return False
        pass

    def has_subscriber(self, pobj):
        return self.typeclass.has_subscriber(pobj)
