"""
Commands for the conditions app.
"""
from commands.base import ArxCommand
from server.utils.exceptions import PayError
from world.conditions.models import RollModifier
from world.stats_and_skills import VALID_SKILLS, VALID_STATS


class CmdModifiers(ArxCommand):
    """
    Adds modifiers to objects

    Usage:
        @modifiers <object>
        @modifiers/search <tag name>
        @modifiers/targetmod <object>=<value>,<tag name>,check
        @modifiers/usermod <object>=<value>,<tag name>,check

    Sets modifiers for the most common usages - an object providing a bonus
    against those with a particular tag (targetmod) for a given type of roll,
    or an object providing a bonus to a user if they have the given tag. For
    more complex modifiers (such as to specific skills, or combinations of
    requirements), use django admin.

    Rooms provide modifiers to those in the location, while weapons and armor
    must be wielded/worn respectively. Tags they check can be added to things
    with the @tag command using the category 'modifiers'.
    """

    key = "@modifiers"
    locks = "cmd: perm(builders)"
    help_category = "building"

    def display_mods(self):
        """Displays modifiers on target"""
        targ = self.caller.search(self.lhs)
        if not targ:
            return
        self.msg(
            "Modifiers on %s: %s"
            % (targ, ", ".join(str(ob) for ob in targ.modifiers.all()))
        )

    def add_mod(self):
        """Adds a modifier to target"""
        from server.utils.arx_utils import dict_from_choices_field

        choices = dict_from_choices_field(RollModifier, "CHECK_CHOICES")
        try:
            value = int(self.rhslist[0])
            tag_name = self.rhslist[1].lower()
            check = choices[self.rhslist[2].lower()]
        except (IndexError, AttributeError):
            self.msg("You must provide value, tag name, and the type of check.")
        except KeyError:
            self.msg("Not a valid check type: %s" % ", ".join(choices.keys()))
        else:
            targ = self.caller.search(self.lhs)
            if not targ:
                return
            if "targetmod" in self.switches:
                mod = targ.add_modifier(value, check_type=check, target_tag=tag_name)
            else:
                mod = targ.add_modifier(value, check_type=check, user_tag=tag_name)
            self.msg("You have added a modifier to %s: %s." % (targ, mod))

    def search_mods(self):
        """Searches for modifiers for/against a given tag"""
        from django.db.models import Q

        msg = "Modifiers for/against %s: " % self.args
        qs = RollModifier.objects.filter(
            Q(user_tag__iexact=self.args) | Q(target_tag__iexact=self.args)
        )
        msg += ", ".join(str(ob) for ob in qs)
        self.msg(msg)

    def func(self):
        """Executes modifiers command"""
        if not self.switches:
            return self.display_mods()
        if "targetmod" in self.switches or "usermod" in self.switches:
            return self.add_mod()
        if "search" in self.switches:
            return self.search_mods()


class CmdKnacks(ArxCommand):
    """
    Creates or displays knacks for your character

    Usage:
        @knacks
        @knacks <name>
        @knacks/create <stat>,<skill>,<knack name>=<description>
        @knacks/train <name>

    The knacks command is a way to customize what a character is really good
    at. By creating a knack, you identify a particular type of check where
    your character excels: for example, you might identify an area of Faith
    lore that your character specializes in with a intellect+theology knack,
    or a character who is an accomplished jouster might have a dexterity +
    riding knack. The description is generally meant to convey the specifics
    of your character's knack and when/why it might be applicable.

    Knacks cost {} xp to create, then {} + {}*rank to increase. Each rank in
    a knack increases the results of applicable rolls by {} and chance for a
    critical success by 1 + half your rank (rounded down).
    """

    key = "@knacks"
    aliases = ["knack"]
    locks = "cmd:all()"
    help_category = "Progression"
    new_knack_cost = 150
    base_increase_cost = 50
    cost_per_rank = 10
    bonus_per_rank = 1

    def get_help(self, caller, cmdset):
        return self.__doc__.format(
            self.new_knack_cost,
            self.base_increase_cost,
            self.cost_per_rank,
            self.bonus_per_rank,
        )

    def func(self):
        """Executes the knack command"""
        try:
            if not self.args and not self.switches:
                return self.display_knacks()
            if self.args and not self.switches:
                return self.view_knack()
            if "create" in self.switches:
                return self.create_knack()
            if "train" in self.switches:
                return self.train_knack()
            raise self.error_class("Invalid switch.")
        except (self.error_class, PayError) as err:
            self.msg(err)

    def display_knacks(self):
        """Displays our knacks"""
        self.msg(self.caller.mods.display_knacks())

    def view_knack(self):
        """Views a single knack"""
        knack = self.get_knack()
        self.msg(knack.display_knack())

    def get_knack(self):
        knack = self.caller.mods.get_knack_by_name(self.args)
        if not knack:
            raise self.error_class("No knack found by that name.")
        return knack

    def create_knack(self):
        """Attempts to create a new knack"""
        desc = self.rhs
        if not desc:
            raise self.error_class("You must provide a description.")
        try:
            stat, skill, name = (
                self.lhslist[0],
                self.lhslist[1],
                ", ".join(self.lhslist[2:]),
            )
        except IndexError:
            raise self.error_class("You must provide a stat and skill.")
        if not name:
            raise self.error_class("You must provide a name.")
        if self.caller.mods.get_knack_by_name(name):
            raise self.error_class("You already have a knack by that name.")
        stat, skill = stat.lower(), skill.lower()
        if stat not in VALID_STATS:
            raise self.error_class("{} is not a valid stat.".format(stat))
        if skill not in VALID_SKILLS:
            raise self.error_class("{} is not a valid skill.".format(skill))
        if any(
            [
                knack
                for knack in self.caller.mods.knacks
                if knack.stat == stat and knack.skill == skill
            ]
        ):
            raise self.error_class(
                "You already have a knack for that skill and stat combination."
            )
        self.caller.pay_xp(self.new_knack_cost)
        self.caller.mods.create_knack(name, stat, skill, desc)
        self.msg("You create a knack called '{}' for {}+{}.".format(name, stat, skill))

    def train_knack(self):
        knack = self.get_knack()
        new_rank = knack.value + 1
        cost = self.base_increase_cost + (self.cost_per_rank * knack.value)
        self.caller.pay_xp(cost)
        knack.value = new_rank
        knack.save()
        self.msg("You have increased {} to rank {}.".format(knack.name, new_rank))
