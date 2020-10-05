"""

Lockfuncs

Lock functions are functions available when defining lock strings,
which in turn limits access to various game systems.

All functions defined globally in this module are assumed to be
available for use in lockstrings to determine access. See the
Evennia documentation for more info on locks.

A lock function is always called with two arguments, accessing_obj and
accessed_obj, followed by any number of arguments. All possible
arguments should be handled with *args, **kwargs. The lock function
should handle all eventual tracebacks by logging the error and
returning False.

Lock functions in this module extend (and will overload same-named)
lock functions from evennia.locks.lockfuncs.

"""
from world.dominion.models import Organization, Member
from world.magic.models import Practitioner

# def myfalse(accessing_obj, accessed_obj, *args, **kwargs):
#    """
#    called in lockstring with myfalse().
#    A simple logger that always returns false. Prints to stdout
#    for simplicity, should use utils.logger for real operation.
#    """
#    print "%s tried to access %s. Access denied." % (accessing_obj, accessed_obj)
#    return False

# Dominion-specific lockfuncs: rank in an organization, or mere membership


# noinspection PyUnusedLocal
def rank(accessing_obj, accessed_obj, *args, **kwargs):
    """
    Use rank in an organization to see if we pass. If orgname
    is not specified, the org is assumed to be the accessed
    object. If rank is called incorrectly, we'll try to call the
    organization permission instead as a fallback.
    Usage:
        rank(value)
        rank(value, orgname)
    """
    if not args:
        return False
    if accessing_obj.player_ob:
        accessing_obj = accessing_obj.player_ob
    if hasattr(accessing_obj, "dbobj"):
        accessing_obj = accessing_obj.dbobj
    try:
        rank_num = int(args[0])
    except ValueError:
        # check if rank was called where they meant to use organization permission
        if len(args) == 1:
            return organization(accessing_obj, accessed_obj, *args, **kwargs)
        # might have called it with the wrong order. We'll try to reverse it
        args = args[::-1]
        # we'll try the same thing again now that it's reversed.
        try:
            rank_num = int(args[0])
        except (ValueError, TypeError):
            print("Malformed lock 'rank' in %s." % accessed_obj)
            return False
    if len(args) == 1:
        org_obj = accessed_obj
    else:
        try:
            org_obj = Organization.objects.get(name__iexact=args[1])
        except Organization.DoesNotExist:
            return False
    try:
        member = accessing_obj.Dominion.memberships.get(
            organization=org_obj, deguilded=False
        )
        return member.rank <= rank_num
    except (AttributeError, Member.DoesNotExist):
        return False


# noinspection PyUnusedLocal
def organization(accessing_obj, accessed_obj, *args, **kwargs):
    """
    Check if accessing_obj is a member of the Organization given
    by the name.
    Usage:
        organization(orgname)
    """
    if not args:
        return False
    # if we're accessing as a character, set it to be the player object
    # noinspection PyBroadException
    try:
        if accessing_obj.player_ob:
            accessing_obj = accessing_obj.player_ob
    except AttributeError:
        pass
    if hasattr(accessing_obj, "dbobj"):
        accessing_obj = accessing_obj.dbobj
    try:
        org_obj = Organization.objects.get(name__iexact=args[0])
    except Organization.DoesNotExist:
        return False
    try:
        accessing_obj.Dominion.memberships.get(organization=org_obj, deguilded=False)
        # if get fails we get Member.DoesNotExist exception, and won't execute return True
        return True
    except (AttributeError, Member.DoesNotExist):
        # we weren't a member of the organization
        return False


# alias for organization lockfunc
org = organization


# noinspection PyUnusedLocal
def ability(accessing_obj, accessed_obj, *args, **kwargs):
    """
    Check accessing_obj's rank in an ability to determine lock.
    Usage:
        ability(value)
        ability(ability_name, value)
    If only value is given, ability must be a property in accessed_obj
    that returns ability_name.
    """
    if not args:
        return False
    if len(args) == 1:
        if args[0] == "all":
            return True
        name = accessed_obj.ability
        val = int(args[0])
    else:
        name = args[0]
        val = int(args[1])
    if name == "all":
        from world.stats_and_skills import CRAFTING_ABILITIES

        ability_list = CRAFTING_ABILITIES
    else:
        ability_list = name.split(",")
    for ability_name in ability_list:
        ability_name = ability_name.lower().strip()
        try:
            pab = accessing_obj.traits.get_ability_value(ability_name)
        except AttributeError:
            return False
        if pab >= val:
            return True
    return False


# noinspection PyUnusedLocal
def skill(accessing_obj, accessed_obj, *args, **kwargs):
    """
    Check accessing_obj's rank in an skill to determine lock.
    Usage:
        skill(value)
        skill(ability_name, value)
    If only value is given, ability must be a property in accessed_obj
    that returns ability_name.
    """
    if not args:
        return False
    if len(args) == 1:
        if args[0] == "all":
            return True
        name = accessed_obj.skill
        val = int(args[0])
    else:
        name = args[0]
        val = int(args[1])
    if name == "all":
        from world.stats_and_skills import CRAFTING_SKILLS

        skill_list = CRAFTING_SKILLS
    else:
        skill_list = name.split(",")
    if accessing_obj.char_ob:
        accessing_obj = accessing_obj.char_ob
    for skill_name in skill_list:
        skill_name = skill_name.lower().strip()
        try:
            pab = accessing_obj.traits.get_skill_value(skill_name)
            if pab >= val:
                return True
        except AttributeError:
            return False
    return False


# noinspection PyUnusedLocal
def roomkey(accessing_obj, accessed_obj, *args, **kwargs):
    """
    A key to a room.
    """
    if not args:
        return False
    roomid = int(args[0])
    keylist = accessing_obj.db.keylist or []
    valid = [ob for ob in keylist if hasattr(ob, "tags")]
    keylist = [room.id for room in valid]
    if valid:
        accessing_obj.db.keylist = valid
    return roomid in keylist


# noinspection PyUnusedLocal
def chestkey(accessing_obj, accessed_obj, *args, **kwargs):
    """
    A key to a chest. Needs to be stored in a different attr than
    roomkey for display purposes, so separate lockfunc is required.
    """
    if not args:
        return False
    chestid = int(args[0])
    keylist = accessing_obj.db.chestkeylist or []
    valid = [ob for ob in keylist if hasattr(ob, "tags")]
    keylist = [chest.id for chest in valid]
    if valid:
        accessing_obj.db.chestkeylist = valid
    return chestid in keylist


# noinspection PyBroadException
# noinspection PyUnusedLocal
def cattr(accessing_obj, accessed_obj, *args, **kwargs):
    """
    Checks attr in the character object of the accessing_obj, which
    should be a player.
    """
    from evennia.locks.lockfuncs import attr

    try:
        if accessing_obj.player_ob:
            return attr(accessing_obj, accessed_obj, *args, **kwargs)
        char_ob = accessing_obj.char_ob
        return attr(char_ob, accessed_obj, *args, **kwargs)
    except Exception:
        return False


# noinspection PyUnusedLocal
def decorator(accessing_obj, accessed_obj, *args, **kwargs):
    """
    Checks if accessing_obj is owner/decorator of room obj
    is in, or the obj itself if it has no location.
    """
    obj = accessed_obj.location or accessed_obj
    try:
        if accessing_obj in obj.homeowners:
            return True
        return accessing_obj in obj.decorators
    except (AttributeError, ValueError, TypeError):
        return False


decorators = decorator


def practitioner(accessing_obj, accessed_obj, *args, **kwargs):
    """
    Checks if the accessing_obj has a magical Practitioner record.
    """
    mage = Practitioner.practitioner_for_character(accessing_obj)
    if not mage:
        return False

    return mage.eyes_open
