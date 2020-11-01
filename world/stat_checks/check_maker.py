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
        self.receivers = receivers or []
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
        Sends a private roll result message to specific players as well as
        all staff at self.character's location.
        """
        self_list = (
            "me",
            "self",
            str(self.character).lower(),
            str(self.character.key).lower(),
        )

        # Build the list of who is seeing the roll, and the lists of names
        # for the msg of who is seeing the roll.  Staff names are highlighted
        # and last in the lists to draw attention to the fact it was successfully
        # shared with a GM.  The names are also sorted because my left brain
        # insisted that it's more organized this way.
        receiver_list = [
            ob for ob in set(self.receivers) if ob.name.lower() not in self_list
        ]
        staff_receiver_names = [
            "|c%s|n" % (ob.name)
            for ob in set(self.receivers)
            if ob.check_permstring("Builders")
        ]
        pc_receiver_names = [
            ob.name for ob in set(self.receivers) if not ob.check_permstring("Builders")
        ]

        all_receiver_names = sorted(pc_receiver_names) + sorted(staff_receiver_names)

        # Am I the only (non-staff) recipient?
        if len(receiver_list) == 0:
            receiver_suffix = "(Shared with: self-only)"
        else:
            receiver_suffix = "(Shared with: %s)" % (", ").join(all_receiver_names)

        # Now that we know who is getting it, build the private message string.
        private_msg = f"|w[Private Roll]|n {self.roll_message} {receiver_suffix}"

        # Always sent to yourself.
        self.character.msg(private_msg, options={"roll": True})

        # If caller doesn't have a location, we're done; there's no one
        # else to hear it!
        if not self.character.location:
            return

        # Otherwise, send result to all staff in location.
        staff_list = [
            gm
            for gm in self.character.location.contents
            if gm.check_permstring("Builders")
        ]
        for staff in staff_list:
            # If this GM is the caller or a private receiver, skip them.
            # They were or will be notified.
            if staff == self.character or staff in receiver_list:
                continue
            staff.msg(private_msg, options={"roll": True})

        # Send result message to receiver list, if any.
        for receiver in receiver_list:
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
    def __init__(self, roll1, roll2, caller, target):
        self.roll1 = roll1
        self.roll2 = roll2
        self.caller = caller
        self.target = target

    def announce(self):
        self.roll1.execute()
        self.roll2.execute()
        rolls = sorted(
            [self.roll1, self.roll2], key=lambda x: x.result_value, reverse=True
        )
        if check_rolls_tied(self.roll1, self.roll2):
            result = "*** The rolls are |ctied|n. ***"
        else:
            result = f"*** |c{rolls[0].character}|n is the winner. ***"
        msg = f"\n|w*** {self.caller} has called for an opposing check with {self.target}. ***|n\n"
        msg += f"{self.roll1.roll_message}\n{self.roll2.roll_message}\n{result}"
        self.caller.msg_location_or_contents(msg, options={"roll": True})
