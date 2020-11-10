"""
Template file for saving values of stats and skills.
Will add more class functionality later, with helper
functions and so on.

Stats are defined as an attribute from the name of the
stat, listed in the _valid_stats_ tuple. Skills and
abilities are held accessed in the traitshandler:
character.traits.skills and character.traits.abilities,
respectively. So while you can do
char.traits.strength, you would have to access
a skill by char.traits.get_skill_value('brawl'), for example.
"""
from .roll import Roll
from math import ceil


# tuples of allowed stats and skills

DOM_SKILLS = (
    "population",
    "income",
    "farming",
    "productivity",
    "upkeep",
    "loyalty",
    "warfare",
)
_parent_abilities_ = {
    "sewing": ["tailor"],
    "smithing": ["weaponsmith", "armorsmith", "jeweler"],
    "tanning": ["leatherworker"],
    "alchemy": ["apothecary"],
    "woodworking": ["carpenter"],
}
# Default difficulty for an 'easy' task for a person with a skill of 1
DIFF_DEFAULT = 15


# Base Costs for things:
# cost for stats are always 100, regardless of current value
NEW_STAT_COST = 100
# this multiplier is times the new rank of the skill you're going for
# so going from 2 to 3 will be 30 for non-combat, 60 for combat
NON_COMBAT_SKILL_COST_MULT = 10
COMBAT_SKILL_COST_MULT = 20
# being taught will give you a 20% discount
TEACHER_DISCOUNT = 0.8
LEGENDARY_COST = 500


def get_partial_match(args, s_type):
    from world.traits.models import Trait

    # helper function for finding partial string match of stat/skills
    if s_type == "stat":
        word_list = Trait.get_valid_stat_names()
    elif s_type == "skill":
        word_list = Trait.get_valid_skill_names()
    else:
        return
    matches = []
    for word in word_list:
        if word.startswith(args):
            matches.append(word)
    return matches


def do_dice_check(*args, **kwargs):
    """
    Sending stuff to Roll class for dice checks; assumed to already be run through get_partial_match.
    """
    roll = Roll(*args, **kwargs)
    roll.roll()
    return roll.result


def get_stat_cost(caller, stat):
    """Currently all stats cost 100, but this could change."""
    cost = NEW_STAT_COST
    if caller.traits.check_training(stat, stype="stat"):
        cost = discounted_cost(caller, cost)
    total_stats = caller.traits.get_total_stats()
    bonus_stats = total_stats - 36
    if bonus_stats > 0:
        cost *= 1 + 0.5 * bonus_stats
    return int(cost)


def cost_at_rank(skill, current_rating, new_rating):
    """Returns the total cost when given a current rating and the new rating."""
    from world.traits.models import Trait

    cost = 0
    if new_rating > current_rating:
        while current_rating < new_rating:
            current_rating += 1
            if (
                skill in Trait.get_valid_skill_names(Trait.COMBAT)
                or skill in Trait.get_valid_ability_names()
            ):
                mult = COMBAT_SKILL_COST_MULT
            else:
                mult = NON_COMBAT_SKILL_COST_MULT
            if current_rating >= 6 and skill in Trait.get_valid_skill_names():
                base = LEGENDARY_COST
                mult //= 10
            else:
                base = current_rating
            cost += base * mult
        return cost
    if new_rating < current_rating:
        while current_rating > new_rating:
            if (
                skill in Trait.get_valid_skill_names(Trait.COMBAT)
                or skill in Trait.get_valid_ability_names()
            ):
                cost -= current_rating * COMBAT_SKILL_COST_MULT
            else:
                cost -= current_rating * NON_COMBAT_SKILL_COST_MULT
            current_rating -= 1
        return cost
    return cost


def get_skill_cost_increase(caller, additional_cost=0):
    from commands.base_commands import guest

    skills = caller.traits.skills
    srank = caller.db.social_rank or 0
    age = caller.db.age or 0
    total = 0.0
    for skill in skills:
        # get total cost of each skill
        total += cost_at_rank(skill, 0, skills[skill])
    skill_xp = guest.get_total_skill_points() * 10
    bonus_by_srank = guest.XP_BONUS_BY_SRANK.get(srank, 0)
    bonus_by_age = guest.award_bonus_by_age(age)
    discounts = skill_xp + bonus_by_srank + bonus_by_age
    if total + additional_cost < discounts:  # we're free
        return -1.0
    elif total >= discounts:  # we have an xp tax
        total -= discounts
        total += additional_cost
        return total / 500.0
    else:  # we have some newbie skill points left over. Give us a discount
        initial = (discounts - total) / additional_cost * -1
        # we need to determine the tax from the remaining points over, after discount
        cost = additional_cost + (additional_cost * initial)
        tax = cost / 500.0
        return initial + tax


def get_skill_cost(
    caller, skill, adjust_value=None, check_teacher=True, unmodified=False
):
    """Uses cost at rank and factors in teacher discounts if they are allowed."""
    current_rating = caller.traits.get_skill_value(skill)
    if not adjust_value and adjust_value != 0:
        adjust_value = 1
    new_rating = current_rating + adjust_value
    # cost for a legendary skill
    base_cost = cost_at_rank(skill, current_rating, new_rating)
    if base_cost < 0:
        return base_cost
    if unmodified:
        return base_cost
    # check for freebies
    tax = get_skill_cost_increase(caller, additional_cost=base_cost)
    if tax <= -1.0:
        return 0
    # check what discount would be
    cost = base_cost
    if check_teacher:
        if caller.traits.check_training(skill, stype="skill"):
            cost = discounted_cost(caller, base_cost)
    cost += ceil(cost * tax)
    return cost


def get_dom_cost(caller, skill, adjust_value=None):
    dompc = caller.player.Dominion
    current_rating = getattr(dompc, skill)
    if not adjust_value and adjust_value != 0:
        adjust_value = 1
    new_rating = current_rating + adjust_value
    cost = cost_at_rank(skill, current_rating, new_rating)
    if cost < 0:
        return cost
    cost *= 100
    return cost


def get_ability_cost(
    caller, ability, adjust_value=None, check_teacher=True, unmodified=False
):
    """Uses cost at rank and factors in teacher discounts if they are allowed."""
    from world.traits.models import Trait

    current_rating = caller.traits.get_ability_value(ability)
    if not adjust_value and adjust_value != 0:
        adjust_value = 1
    new_rating = current_rating + adjust_value
    cost = cost_at_rank(ability, current_rating, new_rating)
    crafting_abilities = Trait.get_valid_ability_names(Trait.CRAFTING)
    if ability in crafting_abilities:
        cost /= 2
    if cost < 0:
        return cost
    if unmodified:
        return cost
    # abilities are more expensive the more we have in the same category
    if ability in crafting_abilities:
        for c_ability in crafting_abilities:
            cost += caller.traits.get_ability_value(c_ability)
    # check what discount would be
    if check_teacher:
        if caller.traits.check_training(ability, stype="ability"):
            cost = discounted_cost(caller, cost)
    return cost


def discounted_cost(caller, cost):
    discount = TEACHER_DISCOUNT
    trainer = caller.db.trainer
    teaching = trainer.traits.get_skill_value("teaching")
    discount -= 0.05 * teaching
    if 0 > discount > 1:
        raise ValueError("Error: Training Discount outside valid ranges")
    return ceil(cost * discount)


def get_dom_resource(field):
    if field in ("population", "loyalty"):
        return "social"
    if field in ("income", "farming", "upkeep", "productivity"):
        return "economic"
    if field in ("warfare",):
        return "military"
