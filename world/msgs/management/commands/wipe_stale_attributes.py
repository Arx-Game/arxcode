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
    attr_names = ["stealth", "sense_difficulty", "is_wieldable"]

    print(
        f"Deleting stale attributes: {Attribute.objects.filter(db_key__in=attr_names).delete()}"
    )
