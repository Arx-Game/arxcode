"""
Various constants for crafting. Mostly this will be constants that hold typeclass paths for the instances
we create for different recipes.
"""

SMALL_WPN = "typeclasses.wearable.wieldable.Wieldable"
MEDIUM_WPN = "typeclasses.wearable.wieldable.Wieldable"
HUGE_WPN = "typeclasses.wearable.wieldable.Wieldable"
BOW = "typeclasses.wearable.wieldable.RangedWeapon"
DECORATIVE_WIELD = "typeclasses.wearable.decorative_weapon.DecorativeWieldable"
WEAR = "typeclasses.wearable.wearable.Wearable"
PLACE = "typeclasses.places.places.Place"
BOOK = "typeclasses.readable.readable.Readable"
CONTAINER = "typeclasses.containers.container.Container"
WEARABLE_CONTAINER = "typeclasses.wearable.wearable.WearableContainer"
BAUBLE = "typeclasses.bauble.Bauble"
PERFUME = "typeclasses.consumable.perfume.Perfume"
MASK = "typeclasses.disguises.disguises.Mask"

TYPE_CHOICES = (
    ()
)

QUALITY_LEVELS = {
    0: '{rawful{n',
    1: '{mmediocre{n',
    2: '{caverage{n',
    3: '{cabove average{n',
    4: '{ygood{n',
    5: '{yvery good{n',
    6: '{gexcellent{n',
    7: '{gexceptional{n',
    8: '{gsuperb{n',
    9: '{454perfect{n',
    10: '{553divine{n',
    11: '|355transcendent|n'
    }

ANY, INNER, OUTER, WIELDED, WIELDED_BOTH_HANDS = range(5)
LAYERS = (ANY, INNER, OUTER)
DEFAULT_LAYER = OUTER
