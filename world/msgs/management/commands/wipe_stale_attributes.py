"""
I'm slowly replacing Attributes as the primary form of data storage of the game
with real tables. Occasionally I'm finding places where the attributes aren't
being used at all but were still having rows populated, so I wanted to wipe
them without creating a one-off migration that would then need to be deleted
right after being applied to avoid slowing down tests.
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Fix permissions for proxy models."

    def handle(self, *args, **options):
        wipe_attributes()


def wipe_attributes():
    from evennia.typeclasses.attributes import Attribute

    # different attributes that we're dumping due to not being used
    attr_names = [
        "stealth",
        "sense_difficulty",
        "is_wieldable",
        "damage_bonus",
        "worn_time",
        "currently_worn",
        "currently_wielded",
        "penalty",
        "armor_resilience",
        "slot_limit",
        "slot",
        "attack_skill",
        "attack_stat",
        "damage_stat",
        "damage_bonus",
        "attack_type",
        "can_be_parried",
        "can_be_dodged",
        "can_be_countered",
        "can_parry",
        "can_riposte",
        "difficulty_mod",
        "flat_damage_bonus",
        "max_spots",
        "occupants",
        "sitting_at_table",
        "places",
        "materials",
        "wielded_by",
        "sheathed_by",
        "can_be_blocked",
        "ready_phrase",
        "destroyable",
        # for Readable
        "written",
        "can_stack",
        "do_not_format_desc",
        "author",
        "container",
        "locked",
        "docked",
        "docked_guards",
        "worn_by",
        "requested_support",
        "last_recovery_test",
        "asked_supporters",
        "administered_aid",
    ]
    for attr in attr_names:
        print(
            f"Deleted stale attribute {attr}: {Attribute.objects.filter(db_key=attr).delete()}"
        )
