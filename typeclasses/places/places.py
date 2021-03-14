"""
Places for tabletalk
"""

from typeclasses.objects import Object
from typeclasses.places.cmdset_places import DefaultCmdSet, SittingCmdSet
from evennia.utils.utils import make_iter
from world.crafting.craft_data_handlers import PlaceDataHandler


class Place(Object):
    """
    Class for placed objects that allow the 'tabletalk' command.
    """

    item_data_class = PlaceDataHandler
    default_max_spots = 6
    default_desc = "A place for people to privately chat. Dropping it in a room will make it part of the room."
    PLACE_LOCKS = (
        "call:true();control:perm(Wizards);delete:perm(Wizards);examine:perm(Builders);"
        "get:perm(Builders) or decorators();puppet:perm(Immortals);tell:all();view:all()"
    )

    TT_SAY = 1
    TT_POSE = 2
    TT_EMIT = 3

    @property
    def default_occupants(self):
        return []

    def at_object_creation(self):
        """
        Run at Place creation.
        """
        # locks so characters cannot 'get' it
        self.locks.add(self.PLACE_LOCKS)
        self.at_init()

    def leave(self, character):
        """
        Character leaving the table.
        """
        occupants = self.item_data.occupants or []
        if character in occupants:
            occupants.remove(character)
            self.item_data.occupants = occupants
            character.cmdset.delete(SittingCmdSet)
            character.db.sitting_at_table = None
            self.location.msg_contents(
                "%s has left the %s." % (character.name, self.key), exclude=character
            )
            return

    def join(self, character):
        """
        Character joins the table
        """
        occupants = self.item_data.occupants or []
        character.cmdset.add(SittingCmdSet, permanent=True)
        character.db.sitting_at_table = self
        occupants.append(character)
        self.item_data.occupants = occupants
        self.location.msg_contents(
            "%s has joined the %s." % (character.name, self.key), exclude=character
        )

    def build_tt_msg(
        self, from_obj, to_obj, msg: str, is_ooc=False, msg_type=TT_SAY
    ) -> str:
        say_msg = '{ooc}At the {place_color}{place_name}|n, {name} says, "{msg}"'
        pose_msg = "{ooc}At the {place_color}{place_name}|n, {name}{msg}"
        emit_msg = "{ooc}{emit_label}At the {place_color}{place_name}|n, {msg}"

        ooc = "|w(OOC)|n " if is_ooc else ""
        place_name = self.key

        # If highlighting place name for rcvr.
        highlight = to_obj.player_ob.db.highlight_place
        if highlight:
            place_color = to_obj.char_ob.db.place_color or ""  # Beware of None
        else:
            place_color = ""

        if msg_type == self.TT_SAY:
            place_msg = say_msg.format(
                ooc=ooc,
                place_color=place_color,
                place_name=place_name,
                name=from_obj.name,
                msg=msg,
            )
        elif msg_type == self.TT_POSE:
            place_msg = pose_msg.format(
                ooc=ooc,
                place_color=place_color,
                place_name=place_name,
                name=from_obj.name,
                msg=msg,
            )
        elif msg_type == self.TT_EMIT:
            if to_obj.tags.get("emit_label"):
                emit_label = "{w[{c%s{w]{n " % from_obj.name
            else:
                emit_label = ""
            place_msg = emit_msg.format(
                ooc=ooc,
                emit_label=emit_label,
                place_color=place_color,
                place_name=place_name,
                msg=msg,
            )
        else:
            raise ValueError("Invalid message type in Places.build_tt_msg()")

        return place_msg

    def tt_msg(
        self,
        message,
        from_obj,
        exclude=None,
        is_ooc=False,
        msg_type=TT_SAY,
        options=None,
    ):
        """
        Send msg to characters at table. Note that if this method was simply named
        'msg' rather than tt_msg, it would be called by msg_contents in rooms, causing
        characters at the places to receive redundant messages, since they are still
        objects in the room as well.
        """
        # utils.make_iter checks to see if an object is a list, set, etc, and encloses it in a list if not
        # needed so that 'ob not in exclude' can function if we're just passed a character
        exclude = make_iter(exclude)
        for ob in self.item_data.occupants:
            if ob not in exclude:
                place_msg = self.build_tt_msg(from_obj, ob, message, is_ooc, msg_type)
                ob.msg(place_msg, from_obj=from_obj, options=options)
        from_obj.posecount += 1

    def at_after_move(self, source_location, **kwargs):
        """If new location is not our wearer, remove."""
        location = self.location
        # first, remove ourself from the source location's places, if it exists
        if (
            source_location
            and hasattr(source_location, "is_room")
            and source_location.is_room
        ):
            if source_location.db.places and self in source_location.db.places:
                source_location.db.places.remove(self)
        # if location is a room, add cmdset
        if location and location.is_room:
            places = location.db.places or []
            self.cmdset.add_default(DefaultCmdSet, permanent=True)
            places.append(self)
            location.db.places = places
        # if location not a room, remove cmdset
        else:
            self.cmdset.delete_default()
