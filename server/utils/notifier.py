"""
Notifier.py

Contains class for various forms of notifying players, PC GMs, staff, and
so on.  The purpose of this class is to reduce code for sending messages
to specific subsets of the game.  (e.g. - send only to staff in a given room)

RECEIVER OPTIONS
- player: sends the msg to non-staff, non-gm'ing players
- gm: sends the msg to player GMs
- staff: sends the msg to staff

NOTE: Each of these flags can be set to True or False; they are used to
filter out subsets of the player sources.

PLAYER SOURCE OPTIONS
- room: retrieves all characters in the provided room
- list: retrieves all characters from the provided receiver names

NOTE: Player source options are mutually exclusive.


USAGE (example code):

# This code will send "Hello, world!" then 'msg' to all player GMs
# and staff GMs in the given room.
gm_notifier = Notifier(room=caller.location, rcvr_flags={"gm": True, "staff": True})
gm_notifier.notify("Hello, world!")
gm_notifier.notify(msg)
"""
from enum import Enum
from typing import List, Dict

from typeclasses.rooms import ArxRoom


class NotifyError(Exception):
    pass


class Notifier:
    def __init__(
        self,
        caller,
        room: ArxRoom = None,
        receivers: List[str] = None,
        send_to: Dict[str, bool] = None,
        source: Dict[str, bool] = None,
        options: dict = None,
    ):
        self.caller = caller
        self.room = room
        self.receiver_list = receivers or []
        self.receiver_set = set()
        self.options = options
        self.send_to = send_to or {}
        self.source = source or {}

        self._generate_receivers()

    def notify(self, msg: str):
        for rcvr in self.receiver_set:
            rcvr.msg(msg, self.options)

    @property
    def receivers(self) -> set:
        return self.receiver_set

    @property
    def receiver_names(self) -> List[str]:
        return [str(player) for player in self.receiver_set]

    def _generate_receivers(self):
        room_set = set()
        list_set = set()

        # Get the source players
        if self.source.get("room", False):
            room_set = self._get_room_characters()
        elif self.source.get("list", False):
            list_set = self._get_list_characters()

        # All the source players in one set.
        self.receiver_set = room_set | list_set

        player_set = set()
        gm_set = set()
        staff_set = set()

        # If we're sending to PCs that aren't GMs, identify them.
        if self.send_to.get("player", False):
            player_set = self._filter_players()

        # Same for players that are GM'ing.
        if self.send_to.get("gm", False):
            gm_set = self._filter_gms()

        # And now staff.
        if self.send_to.get("staff", False):
            staff_set = self._filter_staff()

        # Get all the receivers together.
        self.receiver_set = player_set | gm_set | staff_set

    def _get_room_characters(self) -> set:
        """Generates the receiver list for a room notification."""
        # If there isn't a location, there can't be any receivers.
        # self.receiver_set will still be an empty set()
        if not self.room:
            return
        room_set = {char for char in self.room.contents if char.is_character}
        return room_set

    def _get_list_characters(self) -> set:
        """Generates the receiver list for a specific-character notificiation."""
        list_set = set()
        for name in self.receiver_list:
            receiver = self.caller.search(name, use_nicks=True)
            if receiver:
                list_set.add(receiver)

        return list_set

    def _filter_players(self) -> set:
        player_set = {
            char for char in self.receiver_set if not char.check_staff_or_gm()
        }
        return player_set

    def _filter_gms(self) -> set:
        gm_set = {
            char
            for char in self.receiver_set
            if char.check_staff_or_gm() and not char.check_permstring("builder")
        }
        return gm_set

    def _filter_staff(self) -> set:
        staff_set = {
            char for char in self.receiver_set if char.check_permstring("builder")
        }
        return staff_set
