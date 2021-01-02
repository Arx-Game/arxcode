from random import randint
from functools import total_ordering

from world.conditions.modifiers_handlers import ModifierHandler
from world.stat_checks.models import (
    DifficultyRating,
    RollResult,
    StatWeight,
    NaturalRollType,
    StatCheck,
)

from server.utils.notifier import RoomNotifier, SelfListNotifier


TIE_THRESHOLD = 5


def check_rolls_tied(roll1, roll2, tie_value=TIE_THRESHOLD):
    if roll1.roll_result_object != roll2.roll_result_object:
        return False
    return abs(roll1.result_value - roll2.result_value) < tie_value


@total_ordering
class SimpleRoll:
    def __init__(
        self,
        character=None,
        stat=None,
        skill=None,
        rating: DifficultyRating = None,
        receivers: list = None,
        tie_threshold: int = TIE_THRESHOLD,
        **kwargs,
    ):
        self.character = character
        self.receivers = receivers or []
        self.stat = stat
        self.skill = skill
        self.result_value = None
        self.result_message = None
        self.room = character and character.location
        self.rating = rating
        self.raw_roll = None
        self.roll_result_object = None
        self.natural_roll_type = None
        self.tie_threshold = tie_threshold
        self.roll_kwargs = kwargs

    def __lt__(self, other: "SimpleRoll"):
        """
        We treat a roll as being less than another if the Result is lower,
        or same result is outside tie threshold for the result values.
        """
        try:
            if self.roll_result_object == other.roll_result_object:
                return (self.result_value + self.tie_threshold) < other.result_value
            return self.roll_result_object.value < other.roll_result_object.value
        except AttributeError:
            return NotImplemented

    def __eq__(self, other: "SimpleRoll"):
        """Equal if they have the same apparent result object and the """
        return (self.roll_result_object == other.roll_result_object) and abs(
            self.result_value - other.result_value
        ) <= self.tie_threshold

    def get_roll_value_for_rating(self):
        return self.rating.value

    def execute(self):
        """Does the actual roll"""
        self.raw_roll = randint(1, 100)
        val = self.get_roll_value_for_traits()
        val += self.get_roll_value_for_knack()
        val -= self.get_roll_value_for_rating()
        val += self.raw_roll
        self.result_value = val
        # we use our raw roll and modified toll to determine if our roll is special
        self.natural_roll_type = self.check_for_crit_or_botch()
        self.roll_result_object = RollResult.get_instance_for_roll(
            val, natural_roll_type=self.natural_roll_type
        )
        self.result_message = self.roll_result_object.render(**self.get_context())

    @property
    def is_success(self):
        return self.roll_result_object.is_success

    def get_roll_value_for_traits(self):
        val = self.get_roll_value_for_stat()
        val += self.get_roll_value_for_skill()
        return val

    def get_context(self) -> dict:
        crit = None
        botch = None
        if self.natural_roll_type:
            if self.natural_roll_type.is_crit:
                crit = self.natural_roll_type
            else:
                botch = self.natural_roll_type
        return {
            "character": self.character,
            "roll": self.result_value,
            "result": self.roll_result_object,
            "natural_roll_type": self.natural_roll_type,
            "crit": crit,
            "botch": botch,
        }

    @classmethod
    def get_check_string(cls, stat, skill, rating):
        roll_message = f"{stat} "
        if skill:
            roll_message += f"and {skill} "
        roll_message += f"at {rating}"
        return roll_message

    @property
    def roll_prefix(self):
        roll_message = f"{self.character} checks {self.get_check_string(self.stat, self.skill, self.rating)}"
        return roll_message

    @property
    def roll_message(self):
        return f"{self.roll_prefix}. {self.result_message}"

    def announce_to_room(self):
        self.character.msg_location_or_contents(
            self.roll_message, options={"roll": True}
        )

    def announce_to_players(self):
        """
        Sends a private roll result message to specific players as well as
        to all GMs (player and staff) at that character's location.
        """
        # Notifiers will source nothing if self.character.location is None
        # or if self.receivers is None.
        # They will have empty receiver lists, and thus not do anything.

        # SelfListNotifier will notify the caller if a player or
        # player GM, and notify every player/player-GM on the list.
        player_notifier = SelfListNotifier(
            self.character,
            receivers=self.receivers,
            to_player=True,
            to_gm=True,
        )
        # RoomNotifier will notify every staff member in the room
        staff_notifier = RoomNotifier(
            self.character,
            room=self.character.location,
            to_staff=True,
        )

        # Generate the receivers of the notifications.
        player_notifier.generate()
        staff_notifier.generate()

        # Staff names get highlighted because they're fancy
        staff_names = [f"|c{name}|n" for name in sorted(staff_notifier.receiver_names)]

        # Build list of who is receiving this private roll.  Staff are last
        receiver_names = sorted(player_notifier.receiver_names) + staff_names

        # If only the caller is here to see it, only the caller will be
        # listed for who saw it.
        if receiver_names:
            receiver_suffix = f"(Shared with: {', '.join(receiver_names)})"
        else:
            receiver_suffix = f"(Shared with: {self.character})"

        # Now that we know who is getting it, build the private message string.
        private_msg = f"|w[Private Roll]|n {self.roll_message} {receiver_suffix}"

        # Notify everyone of the roll result.
        player_notifier.notify(private_msg, options={"roll": True})
        staff_notifier.notify(private_msg, options={"roll": True})

    def get_roll_value_for_stat(self) -> int:
        """
        Looks up how much to modify our roll by based on our stat. We use a lookup table to
        determine how much each level of the stat is weighted by. Weight may be different if
        there is no skills for this roll.
        """
        if not self.stat:
            return 0
        base = self.character.traits.get_stat_value(self.stat)
        # if we don't have a skill defined, we're rolling stat alone, and the weight may be different
        only_stat = not self.skill
        return StatWeight.get_weighted_value_for_stat(base, only_stat)

    def get_roll_value_for_skill(self) -> int:
        """
        Looks up how much to modify our roll based on our skill. We use a lookup table to
        determine how much each level of the skill is weighted by.
        """
        if not self.skill:
            return 0
        base = self.character.traits.get_skill_value(self.skill)
        return StatWeight.get_weighted_value_for_skill(base)

    def get_roll_value_for_knack(self) -> int:
        """Looks up the value for the character's knacks, if any."""
        try:
            mods: ModifierHandler = self.character.mods
            base = mods.get_total_roll_modifiers([self.stat], [self.skill])
        except AttributeError:
            return 0
        return StatWeight.get_weighted_value_for_knack(base)

    def check_for_crit_or_botch(self):
        """
        Checks our lookup table with our raw roll and sees if we got a crit or botch.
        """
        return NaturalRollType.get_roll_type(self.raw_roll)


class DefinedRoll(SimpleRoll):
    """
    Roll for a pre-created check that's saved in the database, which will be used
    to populate the values for the roll.
    """

    def __init__(self, character, check: StatCheck = None, target=None, **kwargs):
        super().__init__(character, **kwargs)
        self.check = check
        # target is the value that determines difficulty rating
        self.target = target or character

    def get_roll_value_for_traits(self) -> int:
        """
        Get the value for our traits from our check
        """
        return self.check.get_value_for_traits(self.character)

    def get_roll_value_for_rating(self) -> int:
        """
        Get the value for the difficult rating from our check
        """
        if self.rating:
            return super().get_roll_value_for_rating()
        self.rating = self.check.get_difficulty_rating(self.target, **self.roll_kwargs)
        return self.rating.value

    def get_roll_value_for_knack(self) -> int:
        """Looks up the value for the character's knacks, if any."""
        # get stats and skills for our check
        try:
            mods: ModifierHandler = self.character.mods
            base = mods.get_total_roll_modifiers(
                self.check.get_stats_list(), self.check.get_skills_list()
            )
        except AttributeError:
            return 0
        return StatWeight.get_weighted_value_for_knack(base)

    @property
    def outcome(self):
        return self.check.get_outcome_for_result(self.roll_result_object)

    @property
    def roll_prefix(self):
        roll_message = f"{self.character} checks '{self.check}' at {self.rating}"
        return roll_message


class BaseCheckMaker:
    roll_class = SimpleRoll

    def __init__(self, character, roll_class=None, **kwargs):
        self.character = character
        self.kwargs = kwargs
        if roll_class:
            self.roll_class = roll_class
        self.roll = None

    @classmethod
    def perform_check_for_character(cls, character, **kwargs):
        check = cls(character, **kwargs)
        check.make_check_and_announce()

    def make_check_and_announce(self):
        self.roll = self.roll_class(character=self.character, **self.kwargs)
        self.roll.execute()
        self.roll.announce_to_room()

    @property
    def is_success(self):
        return self.roll.is_success


class PrivateCheckMaker:
    roll_class = SimpleRoll

    def __init__(self, character, roll_class=None, **kwargs):
        self.character = character
        self.kwargs = kwargs
        if roll_class:
            self.roll_class = roll_class

    @classmethod
    def perform_check_for_character(cls, character, **kwargs):
        check = cls(character, **kwargs)
        check.make_check_and_announce()

    def make_check_and_announce(self):
        roll = self.roll_class(character=self.character, **self.kwargs)
        roll.execute()
        roll.announce_to_players()


class RollResults:
    """Class for ranking the results of rolls, listing ties"""

    tie_threshold = TIE_THRESHOLD

    def __init__(self, rolls):
        self.raw_rolls = sorted(rolls, reverse=True)
        # list of lists of rolls. multiple rolls in a list indicates a tie
        self.results = []

    def rank_results(self):
        for roll in self.raw_rolls:
            is_tie = False
            if self.results:
                last_results = self.results[-1]
                if last_results and last_results[0] == roll:
                    is_tie = True
            if is_tie:
                self.results[-1].append(roll)
            else:
                self.results.append([roll])

    def get_result_string(self):
        result_msgs = []
        for result in self.results:
            if len(result) > 1:
                tie = " ".join(ob.result_message for ob in result)
                result_msgs.append(f"TIE: {tie}")
            else:
                result_msgs.append(result[0].result_message)
        return "\n".join(result_msgs)

    def rank_results_and_get_display(self):
        self.rank_results()
        return self.get_result_string()


class ContestedCheckMaker:
    roll_class = SimpleRoll

    def __init__(self, characters, caller, prefix_string="", roll_class=None, **kwargs):
        self.characters = list(characters)
        self.caller = caller
        self.kwargs = kwargs
        self.prefix_string = prefix_string
        if roll_class:
            self.roll_class = roll_class

    @classmethod
    def perform_contested_check(cls, characters, caller, prefix_string, **kwargs):
        obj = cls(characters, caller, prefix_string, **kwargs)
        obj.perform_contested_check_and_announce()

    def perform_contested_check_and_announce(self):
        rolls = []
        for character in self.characters:
            roll = self.roll_class(character=character, **self.kwargs)
            roll.execute()
            rolls.append(roll)
        results = RollResults(rolls).rank_results_and_get_display()
        roll_message = f"{self.prefix_string}\n{results}"
        self.caller.msg_location_or_contents(roll_message, options={"roll": True})


class OpposingRolls:
    def __init__(self, roll1, roll2, caller, target):
        self.roll1 = roll1
        self.roll2 = roll2
        self.caller = caller
        self.target = target

    def announce(self):
        self.roll1.execute()
        self.roll2.execute()
        rolls = sorted([self.roll1, self.roll2], reverse=True)
        if self.roll1 == self.roll2:
            result = "*** The rolls are |ctied|n. ***"
        else:
            result = f"*** |c{rolls[0].character}|n is the winner. ***"
        msg = f"\n|w*** {self.caller} has called for an opposing check with {self.target}. ***|n\n"
        msg += f"{self.roll1.roll_message}\n{self.roll2.roll_message}\n{result}"
        self.caller.msg_location_or_contents(msg, options={"roll": True})


class DefinedCheckMaker(BaseCheckMaker):
    roll_class = DefinedRoll

    @property
    def outcome(self):
        return self.roll.outcome

    @property
    def value_for_outcome(self):
        return self.outcome.get_value(self.character)
