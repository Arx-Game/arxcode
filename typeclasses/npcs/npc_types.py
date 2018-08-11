import copy
from world.stats_and_skills import (PHYSICAL_STATS, MENTAL_STATS, SOCIAL_STATS,
                                    COMBAT_SKILLS, GENERAL_SKILLS, SOCIAL_SKILLS)

GUARD = 0
THUG = 1
SPY = 2
ASSISTANT = 3
CHAMPION = 4
ANIMAL = 5
SMALL_ANIMAL = 6

npc_templates = {
    "guard": GUARD,
    "thug": THUG,
    "spy": SPY,
    "champion": CHAMPION,
    "assistant": ASSISTANT,
    "animal": ANIMAL,
    "small animal": SMALL_ANIMAL
    }

COMBAT_TYPES = (GUARD, THUG, CHAMPION, ANIMAL)

guard_stats = {
    'strength': 3, 'stamina': 3, 'dexterity': 3,
    'charm': 1, 'command': 1, 'composure': 1,
    'intellect': 2, 'perception': 2, 'wits': 2,
    'mana': 1, 'luck': 1, 'willpower': 1,
    }
spy_stats = {
    'strength': 1, 'stamina': 1, 'dexterity': 1,
    'charm': 3, 'command': 3, 'composure': 3,
    'intellect': 2, 'perception': 2, 'wits': 2,
    'mana': 1, 'luck': 1, 'willpower': 1,
    }
assistant_stats = {
    'strength': 1, 'stamina': 1, 'dexterity': 1,
    'charm': 2, 'command': 2, 'composure': 2,
    'intellect': 3, 'perception': 3, 'wits': 3,
    'mana': 1, 'luck': 1, 'willpower': 1,
    }
animal_stats = {
    'strength': 3, 'stamina': 3, 'dexterity': 3,
    'charm': 1, 'command': 1, 'composure': 1,
    'intellect': 1, 'perception': 3, 'wits': 2,
    'mana': 1, 'luck': 1, 'willpower': 1,
    }
small_animal_stats = animal_stats.copy()
small_animal_stats.update({'strength': 1, 'stamina': 1})
unknown_stats = {
    'strength': 2, 'stamina': 2, 'dexterity': 2,
    'charm': 1, 'command': 1, 'composure': 1,
    'intellect': 2, 'perception': 2, 'wits': 2,
    'mana': 1, 'luck': 1, 'willpower': 1,
    }

npc_stats = {
    GUARD: guard_stats,
    THUG: guard_stats,
    SPY: spy_stats,
    ASSISTANT: assistant_stats,
    CHAMPION: guard_stats,
    ANIMAL: animal_stats,
    SMALL_ANIMAL: small_animal_stats,
    }
primary_stats = {
    GUARD: PHYSICAL_STATS,
    THUG: PHYSICAL_STATS,
    SPY: SOCIAL_STATS,
    ASSISTANT: MENTAL_STATS,
    CHAMPION: PHYSICAL_STATS,
    ANIMAL: PHYSICAL_STATS,
    SMALL_ANIMAL: PHYSICAL_STATS,
    }

guard_skills = dict([(key, 0) for key in COMBAT_SKILLS])
guard_skills.update({"riding": 0, "leadership": 0, "war": 0})
spy_skills = dict([(key, 0) for key in SOCIAL_SKILLS])
spy_skills.update({"streetwise": 0, "investigation": 0})
assistant_skills = dict([(key, 0) for key in GENERAL_SKILLS])
assistant_skills.update({"etiquette": 0, "diplomacy": 0})
animal_skills = {"athletics": 1, "brawl": 1, "dodge": 1, "stealth": 0,
                 "survival": 2, "legerdemain": 0, "performance": 0}
small_animal_skills = animal_skills.copy()
small_animal_skills.update({"stealth": 1, "brawl": 0})

npc_skills = {
    GUARD: guard_skills,
    THUG: guard_skills,
    SPY: spy_skills,
    ASSISTANT: assistant_skills,
    CHAMPION: guard_skills,
    ANIMAL: animal_skills,
    SMALL_ANIMAL: small_animal_skills,
    }

guard_weapon = {
    'attack_skill': 'medium wpn',
    'attack_stat': 'dexterity',
    'damage_stat': 'strength',
    'weapon_damage': 1,
    'attack_type': 'melee',
    'can_be_parried': True,
    'can_be_blocked': True,
    'can_be_dodged': True,
    'can_parry': True,
    'can_riposte': True,
    'reach': 1,
    'minimum_range': 0,
    }

animal_weapon = {
    'attack_skill': 'brawl',
    'attack_stat': 'dexterity',
    'damage_stat': 'strength',
    'weapon_damage': 2,
    'attack_type': 'melee',
    'can_be_parried': True,
    'can_be_blocked': True,
    'can_be_dodged': True,
    'can_parry': True,
    'can_riposte': True,
    'reach': 1,
    'minimum_range': 0,
    }

small_animal_weapon = animal_weapon.copy()
small_animal_weapon.update({'weapon_damage': 1})

npc_weapons = {
    GUARD: guard_weapon,
    THUG: guard_weapon,
    SPY: guard_weapon,
    ASSISTANT: guard_weapon,
    CHAMPION: guard_weapon,
    ANIMAL: animal_weapon,
    SMALL_ANIMAL: small_animal_weapon,
    }

# all armor values are (base, scaling)
guard_armor = (0, 10)
npc_armor = {
    GUARD: guard_armor,
    THUG: guard_armor,
    }
guard_hp = (0, 10)
npc_hp = {
    GUARD: guard_hp,
    THUG: guard_hp,
    }


npc_descs = {
    GUARD: "A group of guards.",
    THUG: "A group of thugs.",
    SPY: "A group of spies.",
    ASSISTANT: "A loyal assistant.",
    CHAMPION: "A loyal champion.",
    ANIMAL: "A faithful animal companion.",
    SMALL_ANIMAL: "A small faithful animal companion."
    }

npc_plural_names = {
    GUARD: "guards",
    THUG: "thugs",
    SPY: "spies",
    }

npc_singular_names = {
    GUARD: "guard",
    THUG: "thug",
    SPY: "spy",
    CHAMPION: "champion",
    ASSISTANT: "assistant",
    ANIMAL: "animal",
    SMALL_ANIMAL: "small animal",
    }


def get_npc_stats(n_type):
    return copy.deepcopy(npc_stats.get(n_type, unknown_stats))


def get_npc_skills(n_type):
    return copy.deepcopy(npc_skills.get(n_type, {}))


def get_npc_desc(n_type):
    return npc_descs.get(n_type, "Unknown description")


def get_npc_plural_name(n_type):
    return npc_plural_names.get(n_type, "unknown agents")


def get_npc_singular_name(n_type):
    return npc_singular_names.get(n_type, "unknown agent")


def get_npc_type(name):
    name = name.lower()
    for n_key, val in npc_plural_names.items():
        if val == name:
            return n_key
    for n_key, val in npc_singular_names.items():
        if val == name:
            return n_key
    return npc_templates[name]


def get_npc_weapon(n_type, quality):
    weapon = copy.deepcopy(npc_weapons.get(n_type, guard_weapon))
    weapon['weapon_damage'] += quality
    return weapon


def get_armor_bonus(n_type, quality):
    base, scale = npc_armor.get(n_type, guard_armor)
    return base + (scale * quality)


def get_hp_bonus(n_type, quality):
    base, scale = npc_hp.get(n_type, guard_hp)
    return base + (scale * quality)


def generate_default_name_and_desc(n_type, quality, org):
    """
    Returns a two-tuple of name, desc based on the
    org name, the quality level of the agent, and
    the n_type.
    """
    name = org.name
    desc = "Some guy"
    tname = get_npc_plural_name(n_type)
    if quality == 0:
        name += " untrained %s" % tname
        desc = "Completely untrained %s. Farmers and the like." % tname
    if quality == 1:
        name += " novice %s" % tname
        desc = "Untested and barely trained %s." % tname
    if quality == 2:
        name += " trained %s" % tname
        desc = "%s who have at least received some training." % tname.capitalize()
    if quality == 3:
        name += " veteran %s" % tname
        desc = "%s who have seen combat before." % tname.capitalize()
    if quality == 4:
        name += " skilled veteran %s" % tname
        desc = "%s who have seen combat, and proven to be very good at it." % tname.capitalize()
    if quality == 5:
        name += " elite %s" % tname
        desc = "Highly skilled %s. Most probably would have name-recognition for their skill." % tname
    return name, desc


def get_npc_stat_cap(atype, stat):
    if atype == SMALL_ANIMAL and stat in PHYSICAL_STATS:
        return 2
    return 5


def check_passive_guard(atype):
    passives = (SMALL_ANIMAL, ASSISTANT)
    if atype in passives:
        return True
    return False

INNATE_ABILITIES = {
    ASSISTANT: ('investigation_assistant', 'discreet_messenger', 'custom_messenger'),
    SPY: ('investigation_assistant', 'custom_messenger', 'discreet_messenger'),
    SMALL_ANIMAL: ('custom_messenger',),
}

ABILITY_COSTS = {
    'investigation_assistant': (50, 'social'), 'discreet_messenger': (25, 'social'),
    'custom_messenger': (25, 'social'),
}


def get_innate_abilities(a_type):
    """Gets abilities that each atype has available to buy at level 0"""
    abilities = INNATE_ABILITIES.get(a_type, ())
    return abilities