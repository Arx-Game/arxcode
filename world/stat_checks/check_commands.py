from commands.base import ArxCommand
from world.stat_checks.models import DifficultyRating, DamageRating
from world.traits.models import Trait
from world.stat_checks.check_maker import (
    BaseCheckMaker,
    PrivateCheckMaker,
    SpoofCheckMaker,
    ContestedCheckMaker,
    SimpleRoll,
    OpposingRolls,
)


class CmdStatCheck(ArxCommand):
    """
    CmdStatCheck is a replacement for the previous CmdDiceCheck command.
    """

    key = "check"
    aliases = ["roll"]
    locks = "cmd:all()"

    def get_help(self, caller, cmdset):
        msg = """
    Usage:
        @check stat + skill at <difficulty rating>[=<player1>,<player2>,etc.]
        @check/contest name1,name2,name3,etc=stat (+ skill) at <rating>
        @check/contest/here stat (+ skill) at <difficulty rating>
        @check/vs stat (+ skill) vs stat(+skill)=<target name>

    Normal check is at a difficulty rating. Rating must be one of 
    {difficulty_ratings}.
    
    check/contest allows a GM to have everyone selected to make a check,
    listing the results in order of results. check/contest/here is 
    shorthand to check everyone in a room aside from the GM.
    """
        ratings = ", ".join(str(ob) for ob in DifficultyRating.get_all_instances())
        return msg.format(difficulty_ratings=ratings)

    def func(self):
        try:
            if "contest" in self.switches:
                return self.do_contested_check()
            if "vs" in self.switches:
                return self.do_opposing_checks()
            if self.rhs:
                return self.do_private_check()
            return self.do_normal_check()
        except self.error_class as err:
            self.msg(err)

    def do_normal_check(self):
        stat, skill, rating = self.get_check_values_from_args(
            self.args, "Usage: stat [+ skill] at <difficulty rating>"
        )
        BaseCheckMaker.perform_check_for_character(
            self.caller, stat=stat, skill=skill, rating=rating
        )

    def do_private_check(self):
        stat, skill, rating = self.get_check_values_from_args(
            self.lhs,
            "Usage: stat [+ skill] at <difficulty rating>[=<player1>,<player2>,etc.]",
        )
        PrivateCheckMaker.perform_check_for_character(
            self.caller, stat=stat, skill=skill, rating=rating, receivers=self.rhslist
        )

    def get_check_values_from_args(self, args, syntax):
        try:
            stats_string, rating_string = args.split(" at ")
        except (TypeError, ValueError):
            raise self.error_class(syntax)
        stat, skill = self.get_stat_and_skill_from_args(stats_string)
        rating_string = rating_string.strip()
        rating = DifficultyRating.get_instance_by_name(rating_string)
        if not rating:
            raise self.error_class(
                f"'{rating_string}' is not a valid difficulty rating."
            )
        return stat, skill, rating

    def get_stat_and_skill_from_args(self, stats_string):
        skill = None
        try:
            stat, skill = stats_string.split("+")
            stat = stat.strip().lower()
            skill = skill.strip().lower()
        except (TypeError, ValueError):
            stat = stats_string.strip().lower()
        if stat not in Trait.get_valid_stat_names():
            raise self.error_class(f"{stat} is not a valid stat name.")
        if skill and skill not in Trait.get_valid_skill_names():
            raise self.error_class(f"{skill} is not a valid skill name.")
        return stat, skill

    def do_contested_check(self):
        if not self.caller.check_staff_or_gm():
            raise self.error_class("You are not GMing an event in this room.")
        characters = []
        if "here" in self.switches:
            characters = [
                ob
                for ob in self.caller.location.contents
                if ob.is_character and ob != self.caller
            ]
            stat, skill, rating = self.get_check_values_from_args(
                self.args, "Usage: stat [+ skill] at <difficulty rating>"
            )
        else:
            if not self.rhs:
                raise self.error_class(
                    "You must specify the names of characters for the contest."
                )
            for name in self.lhslist:
                character = self.search(name)
                if not character:
                    return
                characters.append(character)
            stat, skill, rating = self.get_check_values_from_args(
                self.rhs, "Usage: stat [+ skill] at <difficulty rating>"
            )
        prefix = f"{self.caller} has called for a check of {SimpleRoll.get_check_string(stat, skill, rating)}."
        ContestedCheckMaker.perform_contested_check(
            characters, self.caller, prefix, stat=stat, skill=skill, rating=rating
        )

    def do_opposing_checks(self):
        if not self.rhs:
            raise self.error_class("You must provide a target.")
        target = self.search(self.rhs)
        if not target:
            return
        if not target.is_character:
            raise self.error_class("That is not a character.")
        check_strings = self.lhs.split(" vs ")
        if len(check_strings) != 2:
            raise self.error_class("Must provide two checks.")
        args = [(self.caller, check_strings[0]), (target, check_strings[1])]
        # use first difficulty value as the rating both checks share
        rating = DifficultyRating.get_all_cached_instances()[0]
        rolls = []
        for arg in args:
            stat, skill = self.get_stat_and_skill_from_args(arg[1])
            rolls.append(
                SimpleRoll(character=arg[0], stat=stat, skill=skill, rating=rating)
            )
        OpposingRolls(rolls[0], rolls[1], self.caller, target).announce()


class CmdHarm(ArxCommand):
    """
    CmdHarm is a new replacement for the older, deprecated harm command.
    """

    key = "harm"
    locks = "cmd:all()"
    help_category = "GMing"

    def get_help(self, caller, cmdset):
        msg = """
        Causes damage to a character during a story

        Usage: harm <character>=<damage rating>[,<damage type>]

        The harm command is used to inflict damage on a character during a
        story, usually as the result of a failed roll. Damage is determined
        by the rating of the damage you select.

        Ratings: {damage_ratings}
        """
        ratings = ", ".join(str(ob) for ob in DamageRating.get_all_instances())
        return msg.format(damage_ratings=ratings)

    def func(self):
        try:
            return self.do_harm()
        except self.error_class as err:
            self.msg(err)

    def do_harm(self):
        damage = ""
        target = self.caller.search(self.lhs)
        if not target:
            return
        if self.rhslist:
            damage = DamageRating.get_instance_by_name(self.rhslist[0])
        if not damage:
            raise self.error_class("No damage rating found by that name.")
        if target != self.caller and not self.caller.check_staff_or_gm():
            raise self.error_class("You may only harm others if GMing an event.")
        self.msg(f"Inflicting {damage} on {target}.")
        damage.do_damage(target)


class CmdSpoofCheck(ArxCommand):

    key = "@gmcheck"
    locks = "cmd:all()"

    STAT_LIMIT = 20
    SKILL_LIMIT = 20

    def get_help(self, caller, cmdset):
        ratings = ", ".join(str(obj) for obj in DifficultyRating.get_all_instances())
        msg = f"""
    @gmcheck

    Usage:
        @gmcheck <stat>/<value> [+ <skill>/<value>] at <difficulty>[=<npc name>]
        @gmcheck/crit <same as above>
        @gmcheck/flub <same as above>

    Performs a stat + skill at difficulty check with specified values.  Intended
    for GMs to make rolls for NPCs that don't necessarily exist as characters
    in-game.
    
    The /crit switch allows the roll to crit or botch.
    The /flub switch intentionally fails the roll.

    NPC name allows for a GM to optionally assign an NPC name to their roll.

    Difficulty ratings are as follows: {ratings}
    """
        return msg

    def func(self):
        try:
            self.do_spoof_roll()
        except self.error_class as err:
            self.msg(err)

    def do_spoof_roll(self):
        args = self.lhs if self.rhs else self.args
        syntax_error = (
            "Usage: <stat>/<value> [+ <skill>/<value>] at difficulty=<npc name>"
        )

        # Split string at ' at '
        args, diff_rating = self._extract_difficulty(args, syntax_error)

        # Split string at '+', if possible, and strip.
        stat_str, skill_str = self._extract_stat_skill_string(args, syntax_error)

        # Get Stat value
        stat, stat_value = self._get_values(stat_str)
        if stat and stat not in Trait.get_valid_stat_names():
            raise self.error_class(f"{stat} is not a valid stat name.")

        if stat_value < 1 or stat_value > self.STAT_LIMIT:
            raise self.error_class(f"Stats must be between 1 and {self.STAT_LIMIT}.")

        # Get skill value, if applicable (None if not)
        skill = None
        skill_value = None
        if skill_str:
            skill, skill_value = self._get_values(skill_str)
            if skill and skill not in Trait.get_valid_skill_names():
                raise self.error_class(f"{skill} is not a valid skill name.")

            if skill_value < 1 or skill_value > self.SKILL_LIMIT:
                raise self.error_class(
                    f"Skills must be between 1 and {self.SKILL_LIMIT}."
                )

        # Will be None if not self.rhs, which is what we want.
        npc_name = self.rhs

        can_crit = "crit" in self.switches
        is_flub = "flub" in self.switches

        SpoofCheckMaker.perform_check_for_character(
            self.caller,
            stat=stat,
            stat_value=stat_value,
            skill=skill,
            skill_value=skill_value,
            rating=diff_rating,
            npc_name=npc_name,
            can_crit=can_crit,
            is_flub=is_flub,
        )

    def _extract_difficulty(self, args: str, syntax: str) -> (str, DifficultyRating):
        try:
            lhs, rhs, *remainder = args.split(" at ")
        except ValueError:
            raise self.error_class(syntax)
        else:
            if remainder:
                raise self.error_class(syntax)

        rhs = rhs.strip().lower()
        difficulty = DifficultyRating.get_instance_by_name(rhs)
        if not difficulty:
            raise self.error_class(f"{rhs} is not a valid difficulty rating.")

        return lhs, difficulty

    def _extract_stat_skill_string(self, args: str, syntax: str) -> (str, str):
        # If syntax error on stat only
        if args.count("+") == 0 and args.count("/") != 1:
            raise self.error_class(syntax)
        # If syntax error on stat+skill
        elif args.count("+") == 1 and args.count("/") != 2:
            raise self.error_class(syntax)

        try:
            stat_str, skill_str, *remainder = args.split("+")
        except ValueError:
            stat_str = args
            skill_str = None
        else:
            if remainder:
                raise self.error_class(syntax)

        stat_str = stat_str.strip().lower()
        if skill_str:
            skill_str = skill_str.strip().lower()

        return stat_str, skill_str

    def _get_values(self, args: str) -> (str, int):
        try:
            lhs, rhs = args.split("/")
        except ValueError:
            raise self.error_class('Specify "name/value" for stats and skills.')

        if not rhs.isdigit():
            raise self.error_class("Stat/skill values must be a number.")

        return lhs, int(rhs)
