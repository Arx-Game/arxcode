from typeclasses.npcs.npc import Npc, MultiNpc
from .models import Monster


class MonsterMixin(object):

    @property
    def room_monsters(self):
        if not self.location:
            return []

        monsters = []
        for testobj in self.location.contents:
            if testobj.is_typeclass("world.exploration.npcs.MookMonster") \
                    or testobj.is_typeclass("world.exploration.npcs.BossMonster"):
                monsters.append(testobj)

        return monsters

    def end_combat(self):
        cscript = self.location.ndb.combat_manager
        if not cscript:
            return

        for testobj in self.location.contents:
            if testobj.has_player or (hasattr(testobj, 'is_character') and testobj.is_character):
                if cscript.check_character_is_combatant(testobj):
                    testobj.execute_cmd("+end_combat")

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
        if len(self.room_monsters) == 0:
            self.end_combat()

        self.monster_loot_spawn()
        self.location = None


class MookMonsterNpc(MultiNpc, MonsterMixin):

    def multideath(self, num, death=False):
        super(MookMonsterNpc, self).multideath(num, death=death)
        if self.db.num_living == 0:
            if len(self.room_monsters) == 0:
                self.end_combat()
            self.monster_loot_spawn()
            self.location = None
