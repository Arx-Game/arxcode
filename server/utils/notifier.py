"""
Notifier.py

Contains class for various forms of notifying players, PC GMs, staff, and
so on.  The purpose of this class is to reduce code for sending messages
to specific subsets of the game.  (e.g. - send only to staff in a given room)

RECEIVER OPTIONS
- caller: sends the msg to the caller
- player: sends the msg to non-staff, non-gm'ing players
- gm: sends the msg to player GMs
- staff: sends the msg to staff

NOTE: Each of these flags can be set to True or False; they are used to
filter out subsets of the player sources.

PLAYER SOURCE OPTIONS
- room: retrieves all characters in the provided room
- private: retrieves all characters from the provided receiver names

NOTE: Player source options are mutually exclusive.


USAGE (example code):

# This code will send "Hello, world!" then 'msg' to all player GMs
# and staff GMs in the given room.
gm_notifier = Notifier(room=caller.location, rcvr_flags={"gm": True, "staff": True})
gm_notifier.notify("Hello, world!")
gm_notifier.notify(msg, options={"roll": True})
"""
from enum import Enum
from typing import List, Dict

from typeclasses.rooms import ArxRoom


class NotifyError(Exception):
    pass


class NotifySource(Enum):
    ROOM = 1
    LIST = 2


class Notifier:
    def __init__(
        self,
        caller,
        room: ArxRoom = None,
        receivers: List[str] = None,
        send_to: Dict[str, bool] = None,
        source: NotifySource = NotifySource.ROOM,
        options: dict = None,
    ):
        self.caller = caller
        self.room = room
        self.receiver_list = receivers or []
        self.receiver_set = set()
        self.options = options
        self.send_to = send_to or {}

        self.source = source

        # Get the source players
        if self.source == NotifySource.ROOM:
            self._get_room_characters()
        elif self.source == NotifySource.LIST:
            self._get_list_characters()

        player_set = set()
        gm_set = set()
        staff_set = set()

        # If we're sending to PCs that aren't GMs, get them.
        if send_to.get("player", False):
            player_set = self._filter_players()

        # Same for players that are GM'ing.
        if send_to.get("gm", False):
            gm_set = self._filter_gms()

        # And now staff.
        if send_to.get("staff", False):
            staff_set = self._filter_staff()

        # Get all the other receivers together.
        self.receiver_set = player_set | gm_set | staff_set

        # Finally, add caller if sending to caller.  set() will
        # handle the redundancy of extra callers being added.
        if send_to.get("caller", False):
            self.receiver_set.add(self.caller)

    def notify(self, msg: str):
        for rcvr in self.receiver_set:
            rcvr.msg(msg, self.options)

    @property
    def receivers(self) -> set:
        return self.receiver_set

    @property
    def receiver_names(self) -> list:
        return [str(player) for player in self.receiver_set]

    def _get_room_characters(self):
        """Generates the receiver list for a room notification."""
        # If there isn't a location, there can't be any receivers.
        # self.receiver_set will still be an empty set()
        if not self.room:
            return
        self.receiver_set = {char for char in self.room.contents if char.is_character}

    def _get_list_characters(self):
        """Generates the receiver list for a specific-character notificiation."""
        for name in self.receiver_list:
            receiver = self.caller.search(name, use_nicks=True)
            if receiver:
                self.receiver_set.add(receiver)

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
