from typeclasses.rooms import ArxRoom
from .models import Shardhaven
from .scripts import SpawnMobScript
import random


class ShardhavenRoom(ArxRoom):

    def at_object_receive(self, obj, source_location):
        if not obj.is_typeclass('typeclasses.characters.Character'):
            return

        try:
            haven = Shardhaven.objects.get(pk=self.db.haven_id)
        except Shardhaven.DoesNotExist, Shardhaven.MultipleObjectsReturned:
            return

        difficulty = haven.difficulty_rating
        chance = random.randint(0, 100)
        if chance > difficulty * 3:
            return

        obj.scripts.add(SpawnMobScript)

    def at_object_leave(self, obj, target_location):
        if obj.has_player or (hasattr(obj, 'is_character') and obj.is_character):
            mobs = []
            characters = []
            for testobj in self.contents:
                if testobj.has_player or (hasattr(testobj, 'is_character') and testobj.is_character):
                    if testobj.is_typeclass('world.exploration.npcs.BossMonsterNpc') or testobj.is_typeclass('world.exploration.npcs.MookMonsterNpc'):
                        mobs.append(testobj)
                    elif testobj != obj:
                        characters.append(testobj)

            if len(characters) == 0:
                for mob in mobs:
                    mob.location = None

