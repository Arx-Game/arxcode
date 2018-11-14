from typeclasses.npcs.npc import Npc, MultiNpc
from .models import Monster


class MonsterMixin(object):

    def monster_loot_spawn(self):
        if self.db.monster_id:
            try:
                monster = Monster.objects.get(id=self.db.monster_id)
                monster.handle_loot_drop(self, self.location)
            except Monster.DoesNotExist, Monster.MultipleObjectsReturned:
                pass


class BossMonsterNpc(Npc, MonsterMixin):

    def death_process(self, *args, **kwargs):
        super(BossMonsterNpc, self).death_process(*args, **kwargs)
        self.monster_loot_spawn()
        self.location = None


class MookMonsterNpc(MultiNpc, MonsterMixin):

    def multideath(self, num, death=False):
        super(MookMonsterNpc, self).multideath(num, death=death)
        if self.db.num_living == 0:
            self.monster_loot_spawn()
            self.location = None
