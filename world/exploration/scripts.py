from typeclasses.scripts import Script
from .models import Monster, Shardhaven
import random


class SpawnMobScript(Script):

    def at_script_creation(self):
        """
        Setup the script
        """
        self.desc = "Spawn in monsters"
        self.interval = 1
        self.persistent = False
        self.start_delay = True

    def at_repeat(self):
        try:
            haven = Shardhaven.objects.get(pk=self.obj.location.db.haven_id)
        except Shardhaven.DoesNotExist, Shardhaven.MultipleObjectsReturned:
            self.stop()
            return

        monsters = Monster.objects.filter(habitats__in=[haven.haven_type], difficulty__lte=haven.difficulty_rating)
        if monsters.count() == 0:
            self.stop()
            return

        monster = random.choice(monsters.all())
        mob_instance = monster.create_instance(self.obj.location)
        self.obj.msg("{} attacks you!".format(mob_instance.name))
        mob_instance.attack(self.obj.name, kill=True)
        self.stop()
