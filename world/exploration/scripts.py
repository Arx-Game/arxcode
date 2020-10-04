from typeclasses.scripts.scripts import Script
from .models import Monster, Shardhaven
from server.utils.picker import WeightedPicker


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
            haven = Shardhaven.objects.get(pk=self.obj.db.haven_id)
        except (Shardhaven.DoesNotExist, Shardhaven.MultipleObjectsReturned):
            self.stop()
            return

        if self.obj.db.last_monster:
            try:
                monster = Monster.objects.get(id=self.obj.db.last_monster)
            except (Monster.DoesNotExist, Monster.MultipleObjectsReturned):
                self.stop()
                return
        else:
            monsters = Monster.objects.filter(
                habitats__in=[haven.haven_type], difficulty__lte=haven.difficulty_rating
            )

            monster_type = self.obj.ndb.last_monster_type

            if monster_type:
                if monster_type == "mook":
                    monsters = monsters.filter(npc_type=Monster.MOOKS)
                elif monster_type == "boss":
                    monsters = monsters.filter(npc_type=Monster.BOSS)

            if monsters.count() == 0:
                self.stop()
                return

            picker = WeightedPicker()
            for monster in monsters.all():
                picker.add_option(monster, monster.weight_spawn)

            monster = picker.pick()

        mob_instance = monster.create_instance(self.obj)
        self.obj.msg_contents(
            "{} attacks {}!".format(mob_instance.name, self.obj.ndb.monster_attack)
        )
        mob_instance.attack(self.obj.ndb.monster_attack, kill=True)
        mob_instance.combat.set_switch_chance(40)

        if haven.auto_combat:
            cscript = self.obj.ndb.combat_manager
            for testobj in self.obj.contents:
                if (
                    testobj.has_account
                    or (hasattr(testobj, "is_character") and testobj.is_character)
                ) and not testobj.check_permstring("builders"):
                    if not cscript.check_character_is_combatant(testobj):
                        testobj.msg(cscript.add_combatant(testobj, testobj))
                    if not testobj.is_typeclass(
                        "world.exploration.npcs.BossMonsterNpc"
                    ) and not testobj.is_typeclass(
                        "world.exploration.npcs.MookMonsterNpc"
                    ):
                        if mob_instance.combat.state:
                            mob_instance.combat.state.add_foe(testobj)

        self.stop()
