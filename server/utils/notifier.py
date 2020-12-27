"""
Notifier.py

Contains class for various forms of notifying players, PC GMs, staff, and
so on.  The purpose of this class is to reduce code for sending messages
to specific subsets of the game.  (e.g. - send only to staff in a given room)

Notify options:
- players: sends the msg to all non-staff, non-gm'ing players
- gm: sends the msg only to player GMs
- staff: sends the msg only to staff

- room: sends the msg only to characters in the provided room
- global: sends the msg to characters regardless of location
- private: sends the msg only to the provided receiver names


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

        self.to_players = send_to.get("player", False)
        self.to_gms = send_to.get("gm", False)
        self.to_staff = send_to.get("staff", False)

        self.source = source

        # Get the source players
        if self.source == NotifySource.ROOM:
            self._do_room_generate()
        elif self.source == NotifySource.LIST:
            self._do_list_generate()

        player_set = set()
        gm_set = set()
        staff_set = set()

        # If we're sending to PCs that aren't GMs, get them.
        if self.to_players:
            player_set = self._filter_players()

        # Same for players that are GM'ing.
        if self.to_gms:
            gm_set = self._filter_gms()

        # And lastly, staff.
        if self.to_staff:
            staff_set = self._filter_staff()

        self.receiver_set = player_set | gm_set | staff_set

    def notify(self, msg: str):
        for rcvr in self.receiver_set:
            rcvr.msg(msg, self.options)

    @property
    def receivers(self) -> set:
        return self.receiver_set

    @property
    def receiver_names(self) -> list:
        return sorted([str(player) for player in self.receiver_set])

    def _do_room_generate(self):
        """Generates the receiver list for a room notification."""
        self.receiver_set = {char for char in self.room.contents if char.is_character}

    def _do_list_generate(self):
        """Generates the receiver list for a private notificiation."""
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
