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
        to_player=False,
        to_gm=False,
        to_staff=False,
        options: dict = None,
    ):
        self.caller = caller
        self.to_player = to_player
        self.to_gm = to_gm
        self.to_staff = to_staff
        self.options = options

        self.receiver_set = set()

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
        pass

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

    def _sort_receivers(self) -> set:
        player_set = set()
        gm_set = set()
        staff_set = set()

        if self.to_player:
            player_set = self._filter_players()

        if self.to_gm:
            gm_set = self._filter_gms()

        if self.to_staff:
            staff_set = self._filter_staff()

        return player_set | gm_set | staff_set


class RoomNotifier(Notifier):
    def __init__(
        self,
        caller,
        room: ArxRoom,
        to_player=False,
        to_gm=False,
        to_staff=False,
        options: dict = None,
    ):
        super().__init__(caller, to_player, to_gm, to_staff, options)
        self.room = room

        self._generate_receivers()

    def _generate_receivers(self):
        self.receiver_set = self._get_room_characters()
        self.receiver_set = self._sort_receivers()

    def _get_room_characters(self) -> set:
        room_set = {char for char in self.room.contents if char.is_character}
        return room_set


class PrivateNotifier(Notifier):
    def __init__(
        self,
        caller,
        receivers: List[str],
        to_player=False,
        to_gm=False,
        to_staff=False,
        options: dict = None,
    ):
        super().__init__(caller, to_player, to_gm, to_staff, options)
        self.receiver_list = receivers or []

        self._generate_receivers()

    def _generate_receivers(self):
        self.receiver_set = self._get_list_characters()
        self.receiver_set = self._sort_receivers()

    def _get_list_characters(self) -> set:
        """Generates the receiver list for a specific-character notificiation."""
        list_set = set()
        for name in self.receiver_list:
            receiver = self.caller.search(name, use_nicks=True)
            if receiver:
                list_set.add(receiver)

        # The caller always sees their private notifications.  set()
        # will handle the redundancy of adding caller if they're not
        # already in it.
        list_set.add(self.caller)

        return list_set