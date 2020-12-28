"""
Notifier.py

Contains classes for various forms of notifying players, PC GMs, staff, and
so on.  The purpose of these classes is to reduce code for sending messages
to specific subsets of the game.  (e.g. - send only to staff in a given room)

USAGE (example code):

# This code will send "Hello, world!" then 'msg' to all player GMs
# and staff GMs in the given room.
gm_notifier = RoomNotifier(caller, room=caller.location, to_gm=True, to_staff=True)
gm_notifier.notify("Hello, world!")
gm_notifier.notify(msg)
"""
from typing import List, Dict

from typeclasses.rooms import ArxRoom


class NotifyError(Exception):
    pass


class Notifier:
    """
    Base class for sending notifications to the game.
    This class is meant to be derived from and its ('private') code
    utilized in derived classes (to lower code duplication).
    """

    def __init__(
        self,
        caller,
        to_caller=False,
        to_player=False,
        to_gm=False,
        to_staff=False,
    ):
        self.caller = caller
        self.to_player = to_player
        self.to_caller = to_caller
        self.to_gm = to_gm
        self.to_staff = to_staff

        self.receiver_set = set()

    def notify(self, msg: str, options: dict = None):
        """Notifies each receiver of msg with the given options, if any."""
        for rcvr in self.receiver_set:
            rcvr.msg(msg, options)

    @property
    def receivers(self) -> set:
        return self.receiver_set

    @property
    def receiver_names(self) -> List[str]:
        return [str(player) for player in self.receiver_set]

    def _generate_receivers(self):
        pass

    def _filter_players(self) -> set:
        """Returns all non-gm, non-staff players in receiver_set."""
        player_set = {
            char for char in self.receiver_set if not char.check_staff_or_gm()
        }
        return player_set

    def _filter_gms(self) -> set:
        """Returns all player GMs in receiver_set."""
        gm_set = {
            char
            for char in self.receiver_set
            if char.check_staff_or_gm() and not char.check_permstring("builder")
        }
        return gm_set

    def _filter_staff(self) -> set:
        """Returns all staff in receiver_set."""
        staff_set = {
            char for char in self.receiver_set if char.check_permstring("builder")
        }
        return staff_set

    def _filter_receivers(self) -> set:
        """Returns all receivers designated by the given receiver flags."""
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
    """
    Notifier for sending to everyone in a room, filtered by
    the to_ flags.
    """

    def __init__(
        self,
        caller,
        room: ArxRoom,
        to_caller=False,
        to_player=False,
        to_gm=False,
        to_staff=False,
    ):
        super().__init__(caller, to_caller, to_player, to_gm, to_staff)
        self.room = room

        self._generate_receivers()

    def _generate_receivers(self):
        self.receiver_set = self._get_room_characters()
        self.receiver_set = self._filter_receivers()

    def _get_room_characters(self) -> set:
        """
        Generates the source receiver list from all characters
        in the given room.
        """
        room_set = {char for char in self.room.contents if char.is_character}

        # Include the caller in this notification if they aren't already.
        if self.to_caller:
            room_set.add(self.caller)

        return room_set


class ListNotifier(Notifier):
    """
    Notifier for sending only to the passed in list of receivers, filtered
    by the delivery flags.
    """

    def __init__(
        self,
        caller,
        receivers: List[str],
        to_caller=False,
        to_player=False,
        to_gm=False,
        to_staff=False,
    ):
        super().__init__(caller, to_caller, to_player, to_gm, to_staff)
        self.receiver_list = receivers or []

        self._generate_receivers()

    def _generate_receivers(self):
        self.receiver_set = self._get_list_characters()
        self.receiver_set = self._filter_receivers()

    def _get_list_characters(self) -> set:
        """Generates the source receiver list from passed in receivers."""
        list_set = set()
        for name in self.receiver_list:
            receiver = self.caller.search(name, use_nicks=True)
            if receiver:
                list_set.add(receiver)

        # Include the caller in this notification if they aren't already.
        if self.to_caller:
            list_set.add(self.caller)

        return list_set
