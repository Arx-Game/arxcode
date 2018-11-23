from typeclasses.rooms import ArxRoom
from .models import Shardhaven, ShardhavenLayoutSquare
from .scripts import SpawnMobScript
from .loot import LootGenerator
import random
from server.utils.picker import WeightedPicker
from typeclasses.mixins import ObjectMixins
from evennia.contrib.extended_room import ExtendedRoom


class ShardhavenRoom(ArxRoom):

    def extra_status_string(self, looker):
        haven_room = self.shardhaven_square
        if haven_room and haven_room.puzzle and not haven_room.puzzle_solved:
            return "|/|/|yThere is a puzzle to solve here.  Type 'puzzle' for details!|n|/"

        return ""

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

        haven_square = self.shardhaven_square
        recent = False
        if haven_square is not None:
            recent = haven_square.visited_recently
            haven_square.visit(obj)

        if obj.check_permstring("builders"):
            return

        characters = []
        for testobj in self.contents:
            if testobj != obj and (testobj.has_player or (hasattr(testobj, 'is_character') and testobj.is_character)) \
                    and not testobj.check_permstring("builders"):
                characters.append(testobj)

        player_characters = []
        monsters = []
        for testobj in characters:
            if not testobj.is_typeclass("world.exploration.npcs.BossMonsterNpc") \
                    and not testobj.is_typeclass("world.exploration.npcs.MookMonsterNpc"):
                player_characters.append(testobj)
            else:
                monsters.append(testobj)

        if obj not in player_characters:
            player_characters.append(obj)

        if haven_square.monster and not haven_square.monster_defeated and len(monsters) == 0:
            self.db.last_monster = haven_square.monster.id
            self.ndb.monster_attack = obj.name
            self.scripts.add(SpawnMobScript)
        else:
            picker = WeightedPicker()
            # Let's not roll high for EVERY single player
            # Otherwise we run the risk of a monster showing up every single room.
            if recent:
                weight_none = haven.weight_no_monster_backtrack
            else:
                weight_none = haven.weight_no_monster

            if len(monsters) > 0:
                weight_none *= 4
                if haven.auto_combat:
                    cscript = self.ndb.combat_manager
                    if cscript and not cscript.check_character_is_combatant(obj):
                        obj.msg("There is a fight in the room!")
                        obj.msg(cscript.add_combatant(obj, obj))
                        for mon in monsters:
                            if mon.combat.state:
                                mon.combat.state.add_foe(obj)

            if len(player_characters) > 1:
                # Chance of spawn in goes down after the first player.
                weight_none = weight_none * 2

            if obj.ndb.shardhaven_sneak_value:
                weight_none += (obj.ndb.shardhaven_sneak_value * 10)
                if obj.ndb.shardhaven_sneak_value > 0:
                    self.msg_contents("%s sneaks quietly into the room, hoping not to disturb any monsters." % obj.name)
                elif obj.ndb.shardhaven_sneak_value < 0:
                    self.msg_contents("%s attempts to sneak into the room, but ends up making more "
                                      "noise than if they'd just walked!" % obj.name)
                obj.ndb.shardhaven_sneak_value = None

            if weight_none < 0:
                weight_none = 0

            if weight_none > 0:
                picker.add_option(None, weight_none)

            picker.add_option("mook", haven.weight_mook_monster)
            picker.add_option("boss", haven.weight_boss_monster)

            monster = picker.pick()

            if monster:
                self.ndb.last_monster_type = monster
                self.ndb.monster_attack = obj.name
                self.scripts.add(SpawnMobScript)

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
            for mob in monsters:
                if mob.combat and mob.combat.state:
                    mob.combat.state.add_foe(obj)

    def at_object_leave(self, obj, target_location):
        if (obj.has_player or (hasattr(obj, 'is_character') and obj.is_character)) \
                and not obj.check_permstring("builders"):
            mobs = []
            characters = []

            for testobj in self.contents:
                if testobj.has_player or (hasattr(testobj, 'is_character') and testobj.is_character):
                    if testobj.is_typeclass('world.exploration.npcs.BossMonsterNpc') \
                            or testobj.is_typeclass('world.exploration.npcs.MookMonsterNpc'):
                        mobs.append(testobj)
                    elif testobj != obj and not testobj.check_permstring("builders"):
                        characters.append(testobj)

            if len(characters) == 0:
                for mob in mobs:
                    mob.location = None
                haven_square = self.shardhaven_square
                if haven_square:
                    haven_square.mark_emptied()

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
                    and not testobj.is_typeclass('typeclasses.exits.Exit'):
                # Someone dropped something in the shardhaven.  Let's not destroy it.
                testobj.location = None
