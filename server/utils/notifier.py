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
from typing import List, Dict, Union


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
        **to_flags,
    ):
        self.caller = caller
        self.to_flags = to_flags

        self.receiver_set = set()

    def notify(self, msg: str, options: Union[Dict, None] = None):
        """Notifies each receiver of msg with the given options, if any."""
        for rcvr in self.receiver_set:
            rcvr.msg(msg, options)

    @property
    def receivers(self) -> set:
        return self.receiver_set

    @property
    def receiver_names(self) -> List[str]:
        return [str(player) for player in self.receiver_set]

    def generate(self):
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

    def _filter_receivers(self):
        """Returns all receivers designated by the given receiver flags."""
        player_set = set()
        gm_set = set()
        staff_set = set()

        if self.to_flags.get("to_player", False):
            player_set = self._filter_players()

        if self.to_flags.get("to_gm", False):
            gm_set = self._filter_gms()

        if self.to_flags.get("to_staff", False):
            staff_set = self._filter_staff()

        self.receiver_set = player_set | gm_set | staff_set


class RoomNotifier(Notifier):
    """
    Notifier for sending to everyone in a room, filtered by
    the to_ flags.
    """

    def __init__(
        self,
        caller,
        room,
        **to_flags,
    ):
        super().__init__(caller, **to_flags)
        self.room = room

    def generate(self):
        self._get_room_characters()
        self._filter_receivers()

    def _get_room_characters(self):
        """
        Generates the source receiver list from all characters
        in the given room.
        """
        if self.room:
            self.receiver_set = {
                char for char in self.room.contents if char.is_character
            }


class ListNotifier(Notifier):
    """
    Notifier for sending only to the passed in list of receivers,
    then filtered by the to_flags.

    NOTE: The caller is not notified when using ListNotifier.  Use
    SelfListNotifier to get this behavior.
    """

    def __init__(self, caller, receivers: List[str] = None, **to_flags):
        super().__init__(caller, **to_flags)

        self.receiver_list = receivers or []

    def generate(self):
        self._get_list_characters()
        self._filter_receivers()

    def _get_list_characters(self):
        for name in self.receiver_list:
            receiver = self.caller.search(name, use_nicks=True)
            if receiver:
                self.receiver_set.add(receiver)


class SelfListNotifier(ListNotifier):
    """
    Notifier for sending only to the passed in list of receivers and
    the caller, then filtered by the to_flags.
    """

    def __init__(
        self,
        caller,
        receivers: List[str],
        **to_flags,
    ):
        super().__init__(caller, receivers, **to_flags)

    def generate(self):
        self._get_list_characters()
        self._filter_receivers()

    def _get_list_characters(self) -> set:
        """Generates the source receiver list from passed in receivers."""
        super()._get_list_characters()

        # Caller always sees their notifications in this notifier if
        # they're part of the to_flags set.
        self.receiver_set.add(self.caller)
