"""
A script I ran when I wanted to correct what I saw as an abuse case with too many investigation assistants
for players and wanted to introduce a bottleneck of requiring xp transfers to retainers. Something I meant
to do for a long time until the problem had grown so large I couldn't ignore anymore, but that also meant
that it was too large to address by hand, so had to do things programatically. So the solution here, after
instituting a required xp investment for investigation assistants, was to allow everyone to keep one
investigation assistant unchanged, with that being the one with the highest investigation ability. For every
retainer an owner had past that, I would refund the resources spent in raising their investigation skill and
investigation_assistant ability. I decided not to wipe XP on hand because glancing over the database, the ones
with the most XP on hand didn't belong to those who had been abusing it - it tended to be with players who had
fewer retainers, and had never got around to spending resources on them to use up the xp.
"""
from collections import defaultdict
from typeclasses.npcs.npc import Retainer
from typeclasses.npcs.npc_types import ANIMAL
from world.stats_and_skills import cost_at_rank


def refund_investigation_skill(skills_dict):
    """
    Gets the amount of resources for investigation skill refund
    Args:
        skills_dict: dictionary of our skills

    Returns:
        The amount of resources to refund them.
    """
    return abs(cost_at_rank("investigation", skills_dict.get("investigation", 0), 0))


def refund_assistant_ability(abilities_dict):
    """
    Gets the amount of resources for investigation_assistant ability refund
    Args:
        abilities_dict: dictionary of our abilities

    Returns:
        The amount of resources to refund them.
    """
    return 50 * abilities_dict.get("investigation_assistant", 0)


def refund_owners():
    """
    Script for refunding all investigation retainers. So a particular problem that we'll try to avoid here is
    Evennia Attributes are usually cached. But if the pickled attribute is a collection of some kind, they are
    not cached and any access to it will represent a query. So what we'll tend to do is for every retainer we'll
    look at, we'll store tuples representing the object, their skills dict, and their abilities dict
    """
    qs = Retainer.objects.filter(agentob__agent_class__type__lt=ANIMAL)
    investigators = [ob for ob in qs if (ob.db.skills and ob.db.skills.get("investigation", 0)) or
                     (ob.db.abilities and ob.db.abilities.get("investigation_assistant", 0))]
    owners_to_retainers = defaultdict(list)
    for ob in investigators:
        tup = [ob, dict(ob.db.skills or {}), dict(ob.db.abilities or {})]
        owners_to_retainers[ob.owner].append(tup)
    for owner, tuplist in owners_to_retainers.items():
        if len(tuplist) <= 1:
            continue
        else:
            tuplist = sorted(tuplist,
                             key=lambda x: x[1].get("investigation", 0) + x[2].get("investigation_assistant", 0),
                             reverse=True)[1:]
            resources = 0
            for tup in tuplist:
                skills = tup[1]
                abilities = tup[2]
                instance_resources = refund_investigation_skill(skills)
                instance_resources += refund_assistant_ability(abilities)
                retainer = tup[0]
                print("Gave %s %s resources for resetting retainer %s." % (owner, instance_resources, retainer.id))
                skills["investigation"] = 0
                abilities["investigation_assistant"] = 0
                retainer.db.skills = skills
                retainer.db.abilities = abilities
                resources += instance_resources
            print("%s got %s total resources." % (owner, resources))
            owner.social += resources
            owner.save()
