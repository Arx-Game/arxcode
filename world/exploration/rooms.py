from typeclasses.rooms import ArxRoom
from .models import Shardhaven, ShardhavenLayoutSquare
from .scripts import SpawnMobScript
from .loot import LootGenerator
import random
from server.utils.picker import WeightedPicker

class ShardhavenRoom(ArxRoom):

    @property
    def shardhaven(self):
        try:
            haven = Shardhaven.objects.get(pk=self.db.haven_id)
            return haven
        except Shardhaven.DoesNotExist, Shardhaven.MultipleObjectsReturned:
            return None
        
    @property
    def shardhaven_square(self):
        try:
            haven_square = ShardhavenLayoutSquare.objects.get(pk=self.db.haven_square_id)
            return haven_square
        except ShardhavenLayoutSquare.DoesNotExist, ShardhavenLayoutSquare.MultipleObjectsReturned:
            return None

    def at_init(self):
        from exploration_commands import CmdExplorationRoomCommands
        self.cmdset.add(CmdExplorationRoomCommands())

        super(ShardhavenRoom, self).at_init()

    def at_object_receive(self, obj, source_location):
        if not obj.is_typeclass('typeclasses.characters.Character'):
            return

        haven = self.shardhaven
        if not haven:
            return

        entrance_square = haven.entrance
        if entrance_square is not None and entrance_square.room == self:
            return

        if not obj.has_player or not (hasattr(obj, 'is_character') and obj.is_character):
            return

        if obj.is_typeclass("world.exploration.npcs.BossMonsterNpc")\
                or obj.is_typeclass("world.explorations.npcs.MookMonsterNpc"):
            return

        if obj.check_permstring("builders"):
            return

        haven_square = self.shardhaven_square
        recent = False
        if haven_square is not None:
            recent = haven_square.visited_recently
            haven_square.visit(obj)

        characters = []
        for testobj in self.contents:
            if testobj != obj and (testobj.has_player or (hasattr(testobj, 'is_character') and testobj.is_character)) \
                    and not testobj.check_permstring("builders"):
                characters.append(testobj)

        player_characters = []
        for testobj in characters:
            if not testobj.is_typeclass("world.exploration.npcs.BossMonsterNpc") \
                    and not testobj.is_typeclass("world.exploration.npcs.MookMonsterNpc"):
                player_characters.append(testobj)

        picker = WeightedPicker()
        if recent:
            weight_none = haven.weight_no_monster_backtrack
        else:
            weight_none = haven.weight_no_monster

        if len(player_characters) > 0:
            weight_none *= 4

        picker.add_option(None, weight_none)
        picker.add_option("mook", haven.weight_mook_monster)
        picker.add_option("boss", haven.weight_boss_monster)

        monster = picker.pick()

        if monster:
            self.ndb.last_monster_type = monster
            obj.scripts.add(SpawnMobScript)

        if len(characters) > 0:
            return

        picker = WeightedPicker()
        if recent:
            picker.add_option(None, haven.weight_no_treasure_backtrack)
        else:
            picker.add_option(None, haven.weight_no_treasure)

        picker.add_option("trinket", haven.weight_trinket)
        picker.add_option("weapon", haven.weight_weapon)

        treasure = picker.pick()

        if treasure:
            if treasure == "trinket":
                trinket = LootGenerator.create_trinket(haven)
                trinket.location = self
            elif treasure == "weapon":
                weapon_types = (
                    LootGenerator.WPN_BOW,
                    LootGenerator.WPN_SMALL,
                    LootGenerator.WPN_MEDIUM,
                    LootGenerator.WPN_HUGE
                )
                weapon = LootGenerator.create_weapon(haven, random.choice(weapon_types))
                weapon.location = self

        if self.ndb.combat_manager:
            obj.msg("Your party is already in combat! Joining the fight.")
            obj.msg(self.ndb.combat_manager.add_combatant(obj, obj))

    def at_object_leave(self, obj, target_location):
        if obj.has_player or (hasattr(obj, 'is_character') and obj.is_character):
            mobs = []
            characters = []
            for testobj in self.contents:
                if testobj.has_player or (hasattr(testobj, 'is_character') and testobj.is_character):
                    if testobj.is_typeclass('world.exploration.npcs.BossMonsterNpc') \
                            or testobj.is_typeclass('world.exploration.npcs.MookMonsterNpc'):
                        mobs.append(testobj)
                    elif testobj != obj:
                        characters.append(testobj)

            if len(characters) == 0:
                for mob in mobs:
                    mob.location = None

    def softdelete(self):
        self.reset()
        super(ShardhavenRoom, self).softdelete()

    def reset(self):
        try:
            city_center = ArxRoom.objects.get(id=13)
        except ArxRoom.DoesNotExist, ArxRoom.MultipleObjectsReturned:
            city_center = None

        for testobj in self.contents:
            if testobj.has_player or (hasattr(testobj, 'is_character') and testobj.is_character):
                if testobj.is_typeclass('world.exploration.npcs.BossMonsterNpc') \
                        or testobj.is_typeclass('world.exploration.npcs.MookMonsterNpc'):
                    testobj.location = None
                else:
                    testobj.location = city_center
            elif testobj.is_typeclass('world.exploration.loot.Trinket') \
                    or testobj.is_typeclass('world.exploration.loot.AncientWeapon') \
                    or testobj.is_typeclass('world.magic.materials.MagicMaterial'):
                testobj.softdelete()
            elif not testobj.is_typeclass('typeclasses.exits.ShardhavenInstanceExit') \
                    or testobj.is_typeclass('typeclasses.exits.Exit'):
                # Someone dropped something in the shardhaven.  Let's not destroy it.
                testobj.location = None
