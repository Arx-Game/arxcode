from random import randint

from world.conditions.modifiers_handlers import ModifierHandler
from world.stat_checks.models import (
    DifficultyRating,
    RollResult,
    StatWeight,
    NaturalRollType,
)


TIE_THRESHOLD = 5


def check_rolls_tied(roll1, roll2, tie_value=TIE_THRESHOLD):
    if roll1.roll_result != roll2.roll_result:
        return False
    return abs(roll1.result_value - roll2.result_value) < tie_value


class SimpleRoll:
    def __init__(
        self,
        character=None,
        stat=None,
        skill=None,
        rating: DifficultyRating = None,
        receivers: list = None,
    ):
        self.character = character
        self.receivers = receivers
        self.stat = stat
        self.skill = skill
        self.result_value = None
        self.result_message = None
        self.room = character and character.location
        self.rating = rating
        self.raw_roll = None
        self.roll_result = None
        self.natural_roll_type = None

    def execute(self):
        """Does the actual roll"""
        self.raw_roll = randint(1, 100)
        val = self.get_roll_value_for_stat()
        val += self.get_roll_value_for_skill()
        val += self.get_roll_value_for_knack()
        val -= self.rating.value
        val += self.raw_roll
        self.result_value = val
        # we use our raw roll and modified toll to determine if our roll is special
        self.natural_roll_type = self.check_for_crit_or_botch()
        self.roll_result = RollResult.get_instance_for_roll(
            val, natural_roll_type=self.natural_roll_type
        )
        self.result_message = self.roll_result.render(**self.get_context())

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
            "result": self.roll_result,
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
        Sends the roll result message to players as well as all staff
        at self.character's location.
        """
        self_list = (
            "me",
            "self",
            str(self.character).lower(),
            str(self.character.key).lower(),
        )

        # Adjust receiver list; this is who actually will receive it besides staff and the caller.
        receiver_list = self.receivers.copy()
        for name in self.receivers:
            receiver = self.character.search(name.strip(), use_nicks=True)

            # If not found, is the caller, or is a GM, remove from the list of receivers.
            # (Staff doesn't need to get it twice, and the caller always will.)
            if (
                not receiver
                or receiver.check_permstring("Builders")
                or name.lower() in self_list
            ):
                receiver_list.remove(name)

        # Is this message meant just for me, or am I now the only recipient?
        self_only = False
        if len(receiver_list) == 0:
            receiver_list.append("self-only")
            self_only = True

        # Now that we know who's getting it, build the private message string.
        receiver_suffix = "(Shared with: %s)" % (", ").join(receiver_list)
        private_msg = f"|w[Private Roll]|n {self.roll_message} {receiver_suffix}"

        # Always sent to yourself.
        self.character.msg(private_msg, options={"roll": True})

        # Send result message to all staff in location.
        staff_list = [
            gm
            for gm in self.character.location.contents
            if gm.check_permstring("Builders")
        ]
        for gm in staff_list:
            # If this GM is also the caller, skip me!  I've seen it already!
            if gm.name.lower() in self_list:
                continue
            gm.msg(private_msg, options={"roll": True})

        # If sending only to caller, we're done.
        if self_only:
            return

        # Send result message to receiver list.
        for name in receiver_list:
            receiver = self.character.search(name.strip(), use_nicks=True)
            if receiver:
                receiver.msg(private_msg, options={"roll": True})

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


class BaseCheckMaker:
    roll_class = SimpleRoll

    def __init__(self, character, **kwargs):
        self.character = character
        self.kwargs = kwargs

    @classmethod
    def perform_check_for_character(cls, character, **kwargs):
        check = cls(character, **kwargs)
        check.make_check_and_announce()

    def make_check_and_announce(self):
        roll = self.roll_class(character=self.character, **self.kwargs)
        roll.execute()
        roll.announce_to_room()


class PrivateCheckMaker:
    roll_class = SimpleRoll

    def __init__(self, character, **kwargs):
        self.character = character
        self.kwargs = kwargs

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
        self.raw_rolls = sorted(rolls, key=lambda x: x.result_value, reverse=True)
        # list of lists of rolls. multiple rolls in a list indicates a tie
        self.results = []

    def rank_results(self):
        for roll in self.raw_rolls:
            is_tie = False
            if self.results:
                last_results = self.results[-1]
                if last_results and check_rolls_tied(
                    last_results[0], roll, self.tie_threshold
                ):
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

    def __init__(self, characters, caller, prefix_string="", **kwargs):
        self.characters = list(characters)
        self.caller = caller
        self.kwargs = kwargs
        self.prefix_string = prefix_string

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
    def __init__(self, roll1, roll2, caller):
        self.roll1 = roll1
        self.roll2 = roll2
        self.caller = caller

    def announce(self):
        self.roll1.execute()
        self.roll2.execute()
        rolls = sorted(
            [self.roll1, self.roll2], key=lambda x: x.result_value, reverse=True
        )
        if check_rolls_tied(self.roll1, self.roll2):
            result = "The rolls are tied."
        else:
            result = f"{rolls[0].character} is the winner."
        msg = f"{self.caller} has called for an opposing check. "
        msg += f"{self.roll1.roll_message} {self.roll2.roll_message}\n{result}"
        self.caller.msg_location_or_contents(msg, options={"roll": True})
