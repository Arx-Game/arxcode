"""
This contains the CombatHandler which stores combat stats for a character. Their actual state in a given
combat is the CombatantStateHandler, which is stored in CombatHandler's state attribute, and instantiated/set
by the combat_script when they join a fight.
"""
from typeclasses.scripts.combat import combat_settings
from typeclasses.scripts.combat.combat_settings import CombatError
from world.stats_and_skills import do_dice_check


# noinspection PyAttributeOutsideInit
class CombatHandler(object):
    """
    Stores information about the character in this particular
    fight - where they're standing (rank), how they might be
    attacking (weapon and combat_style).
    Properties to know:
    self.state - Our combat state, if we're in any combats
    self.spectated_combat - Any combat we're currently observing, not participating in
    self.char - the character we're wrapped around
    self.weapon - the character's weapon if it exists
    self.shield - our shield if it exists
    self.initiative - current initiative roll
    self.status - "active" means they can fight
    self.lost_turn_counter - how many turns we have to sit idle
    self.blocker_list - people stopping us from fleeing
    self.block_flee - anyone we're stopping from fleeing
    self.covering_targs - who we're helping flee
    self.covered_by - people who are helping us flee

    Stuff about how we attack:
    self.can_be_blocked, self.can_be_dodged, self.can_be_parried - all about our attack type
    opposites are self.can_block, self.can_dodge, self.can_parry.
    self.riposte - determines whether we can hit someone who botches
    self.stance - "defensive" to "reckless". gives attack/defense mods
    self.can_cleave - first attack affects all targets
    self.switch_chance - percent chance of switching targets
    """

    def __init__(self, character):
        self.state = None
        self.char = character
        self.spectated_combat = None
        if character.db.num_living:
            self.multiple = True
            self.switch_chance = 50
            try:
                self.base_name = character.get_singular_name()
                self.plural_name = character.get_plural_name()
            except AttributeError:
                self.base_name = character.name
                self.plural_name = character.name
        else:
            self.multiple = False
            self.base_name = character.name
            self.plural_name = character.name
            self.switch_chance = 0
        self.shield = character.db.shield
        if hasattr(character, "weapondata"):
            self.setup_weapon(character.weapondata)
        else:
            self.setup_weapon()
        self.can_cleave = bool(character.tags.get("cleave", category="combat"))

    @property
    def autoattack(self):
        """Whether our character will automatically try to attack every round"""
        return self.char.db.autoattack or self.automated

    @autoattack.setter
    def autoattack(self, val):
        """Sets whether our character will try to attack every round"""
        self.char.db.autoattack = val

    @property
    def automated(self):
        """If the character doesn't have a saved autoattack value, we check to see if they're automated"""
        if self.state:
            return self.state.automated
        return not bool(self.char.player)

    @property
    def combat(self):
        """Gets the combat we're currently in"""
        if not self.state:
            return None
        return self.state.combat

    @property
    def num(self):
        """The number of characters in this object. 1 for normal things, number of dudes for multi-npcs"""
        if self.multiple:
            try:
                return self.char.quantity
            except AttributeError:
                pass
        return 1

    @property
    def stance(self):
        """Our current combat stance"""
        _stance = self.char.db.combat_stance
        if _stance not in combat_settings.COMBAT_STANCES:
            return "balanced"
        return _stance

    @stance.setter
    def stance(self, val):
        self.char.db.combat_stance = val

    def setup_weapon(self, weapon=None):
        """Sets up our weapon in the combat handler"""
        self.weapon = weapon
        if weapon:  # various optional weapon fields w/default values
            self.combat_style = self.char.db.combat_style or "melee"
            self.attack_skill = self.weapon.get("attack_skill", "brawl")
            self.attack_stat = self.weapon.get("attack_stat", "dexterity")
            self.damage_stat = self.weapon.get("damage_stat", "strength")
            self.weapon_damage = self.weapon.get("weapon_damage", 0)
            self.attack_type = self.weapon.get("attack_type", "melee")
            self.can_be_parried = self.weapon.get("can_be_parried", True)
            self.can_be_blocked = self.weapon.get("can_be_blocked", True)
            self.can_be_dodged = self.weapon.get("can_be_dodged", True)
            self.can_parry = self.weapon.get("can_parry", True)
            self.can_riposte = self.weapon.get("can_riposte", True)
            self.difficulty_mod = self.weapon.get("difficulty_mod", 0)
            if self.shield:
                self.can_block = self.shield.db.can_block or False
            else:
                self.can_block = False
            self.can_dodge = True
            self._flat_damage_bonus = self.weapon.get("flat_damage", 0)
            # self.reach = self.weapon.get('reach', 1)
            # self.minimum_range = self.weapon.get('minimum_range', 0)
        else:  # unarmed combat
            self.combat_style = self.char.db.combat_style or "brawling"
            self.attack_skill = "brawl"
            self.attack_stat = "dexterity"
            self.damage_stat = "strength"
            self.weapon_damage = 0
            self.attack_type = "melee"
            self.can_be_parried = True
            self.can_be_blocked = True
            self.can_be_dodged = True
            self.can_parry = False
            self.can_riposte = (
                True  # can't block swords with hands, but can punch someone
            )
            self.can_block = False
            self.can_dodge = True
            # possibly use these in future
            # self.reach = 1 #number of ranks away from them they can hit
            # self.minimum_range = 0 #minimum ranks away to attack
            self.difficulty_mod = 0
            self._flat_damage_bonus = 0

    def display_stats(self):
        """Returns a string display of all our combat stats."""
        weapon = self.char.db.weapon
        try:
            max_hp = self.char.max_hp
            hp = "%s/%s" % (self.char.current_hp, max_hp)
        except AttributeError:
            hp = "?/?"
        fdiff = 20
        if self.state:
            fdiff += int(self.state.num_actions)
        try:
            armor_penalty = int(self.char.armor_penalties)
        except AttributeError:
            armor_penalty = 0
        fdiff += armor_penalty
        diff_mod = (
            "{g%s{n" % self.difficulty_mod
            if self.difficulty_mod < 0
            else "{r%s{n" % self.difficulty_mod
        )
        atk_mod = self.attack_modifier
        atk_modifier_string = "Attack Roll Mod: "
        atk_modifier_string += (
            "{g%s{n" % atk_mod if atk_mod >= 0 else "{r%s{n" % atk_mod
        )
        def_mod = self.defense_modifier
        def_modifier_string = "Defense Roll Mod: "
        def_modifier_string += (
            "{g%s{n" % def_mod if def_mod >= 0 else "{r%s{n" % def_mod
        )
        smsg = """
                    {wStatus{n
{w==================================================================={n
{wHealth:{n %(hp)-25s {wFatigue Level:{n %(fatigue)-20s
{wDifficulty of Fatigue Rolls:{n %(fdiff)-4s {wStatus:{n %(status)-20s
{wCombat Stance:{n %(stance)-25s
{wPenalty to rolls from wounds:{n %(wound)s
           """ % {
            "hp": hp,
            "fatigue": self.state.fatigue_penalty if self.state else 0,
            "fdiff": fdiff,
            "status": self.state.status if self.state else "active",
            "stance": self.stance,
            "wound": self.wound_penalty,
        }
        omsg = """
                    {wOffensive stats{n
{w==================================================================={n
{wWeapon:{n %(weapon)-20s
{wWeapon Damage:{n %(weapon_damage)-17s {wFlat Damage Bonus:{n %(flat)s
{wAttack Stat:{n %(astat)-19s {wDamage Stat:{n %(dstat)-20s
{wAttack Skill:{n %(askill)-18s {wAttack Type:{n %(atype)-20s
{wDifficulty Mod:{n %(dmod)-20s {wCan Be Parried:{n %(bparried)-20s
{wCan Be Blocked:{n %(bblocked)-16s {wCan Be Dodged:{n %(bdodged)-20s
{w%(atkmodstring)-20s
           """ % {
            "weapon": weapon,
            "weapon_damage": self.weapon_damage,
            "astat": self.attack_stat,
            "dstat": self.damage_stat,
            "askill": self.attack_skill,
            "atype": self.attack_type,
            "dmod": diff_mod,
            "bparried": self.can_be_parried,
            "bblocked": self.can_be_blocked,
            "bdodged": self.can_be_dodged,
            "flat": self.flat_damage_bonus,
            "atkmodstring": atk_modifier_string,
        }
        dmsg = """
                    {wDefensive stats{n
{w==================================================================={n
{wMitigation:{n %(mit)-20s {wPenalty to Fatigue Rolls:{n %(apen)s
{wCan Parry:{n %(cparry)-21s {wCan Riposte:{n %(criposte)s
{wCan Block:{n %(cblock)-21s {wCan Dodge:{n %(cdodge)s
{w%(defmodstring)-36s {wSoak Rating:{n %(soak)s""" % {
            "mit": self.armor,
            "defmodstring": def_modifier_string,
            "apen": armor_penalty,
            "cparry": self.can_parry,
            "criposte": self.can_riposte,
            "cblock": self.can_block,
            "cdodge": self.can_dodge,
            "soak": self.soak,
        }
        if self.can_parry:
            dmsg += "\n{wParry Skill:{n %-19s {wParry Stat:{n %s" % (
                self.attack_skill,
                self.attack_stat,
            )
        if self.can_dodge:
            dmsg += "\n{wDodge Skill:{n %-19s {wDodge Stat:{n %s" % (
                self.char.traits.get_skill_value("dodge"),
                "dexterity",
            )
            dmsg += "\n{wDodge Penalty:{n %s" % self.dodge_penalty
        msg = smsg + omsg + dmsg
        return msg

    def __str__(self):
        if self.multiple:
            return self.base_name
        return self.char.name

    def __repr__(self):
        return "<Class CombatHandler: %s>" % self.char

    def msg(self, mssg):
        """Passthrough method to pass along a msg to our character."""
        self.char.msg(mssg)

    @property
    def can_fight(self):
        """
        Whether we're totally out of the fight. Can be killed, but no longer
        a combatant.
        """
        if self.state and not self.state.valid_target:
            return False
        if not self.char.conscious:
            return False
        return True

    @property
    def name(self):
        """Name of our character. Altered number for multinpcs"""
        if not self.multiple:
            return self.char.name
        return "%s %s" % (self.num, self.plural_name)

    @property
    def singular_name(self):
        """Single name for multinpcs"""
        return self.base_name

    @property
    def modifier_tags(self):
        """Returns tags for our attack or that they're physical and mundane"""
        tags = self.char.modifier_tags
        if self.weapon:
            tags += self.weapon.get("modifier_tags", [])
        return tags or ["mundane"]

    @property
    def wound_penalty(self):
        """
        A difficulty penalty based on how hurt we are. Penalty is
        1 per 10% damage. So over +10 diff if we're holding on from uncon.
        """
        # if we're a multi-npc, only the damaged one gets wound penalties
        if (
            self.state
            and self.multiple
            and self.state.remaining_attacks != self.state.num_attacks
        ):
            return 0
        # noinspection PyBroadException
        try:
            dmg = self.char.db.damage or 0
            base = int((dmg * 100.0) / (self.char.max_hp * 10.0))
            base -= self.char.boss_rating * 10
            if base < 0:
                base = 0
            return base
        except Exception:
            return 0

    @property
    def armor(self):
        """Base character armor plus anything from state"""
        value = self.char.armor
        if self.state:
            value += self.state.mitigation_modifier
        return value

    @property
    def flat_damage_bonus(self):
        """Flat damage bonus from weapon plus anything from state"""
        value = self._flat_damage_bonus
        if self.state:
            value += self.state.damage_modifier
        return value

    @property
    def attack_modifier(self):
        """Our current attack modifier, including temporary modifiers from our combat state, if any."""
        value = self.char.attack_modifier
        value -= self.wound_penalty / 2
        if self.state:
            value += self.state.total_attack_modifier
        return value

    @property
    def defense_modifier(self):
        """Our current defense penalties, including temporary modifiers from our combat state, if any."""
        value = self.char.defense_modifier
        value -= self.wound_penalty
        if self.state:
            value += self.state.total_defense_modifier
        return value

    @property
    def dodge_penalty(self):
        """Penalty to dodge based on wearing heavy armor"""
        return int(self.char.armor_penalties * 1.25)

    @property
    def soak(self):
        """Natural damage absorption based on toughness"""
        val = self.char.traits.stamina
        val += self.char.traits.willpower
        val += self.char.traits.get_skill_value("survival")
        return val

    @property
    def armor_pierce_modifier(self):
        """The value of how much armor we ignore"""
        val = self.char.db.armor_pierce_modifier or 0
        val += self.char.boss_rating * 15
        if self.state:
            val += self.state.armor_pierce_modifier
        return val

    def toggle_cleave(self, caller=None):
        """Toggles whether we're cleaving or not. Cleave is AE attacking."""
        self.can_cleave = not self.can_cleave
        if caller:
            caller.msg("%s has cleaving set to: %s" % (self, self.can_cleave))

    def set_switch_chance(self, val, caller=None):
        """Sets the chance for an npc to switch targets between multiple attacks."""
        try:
            val = int(val)
            if val < 0 or val > 100:
                raise ValueError
            self.switch_chance = val
            msg = "%s will switch targets %s percent of the time." % (self, val)
        except ValueError:
            msg = (
                "Use a number between 0-100 to adjust chance of switching targets for %s."
                % self
            )
        if caller:
            caller.msg(msg)

    def sense_ambush(self, attacker, sneaking=False, invis=False):
        """
        Returns the dice roll of our attempt to detect an ambusher.
        """
        diff = 0  # base difficulty
        if sneaking:
            diff += 15
        sense = self.char.sensing_check(difficulty=0, invis=invis)
        stealth = do_dice_check(attacker, stat="dexterity", skill="stealth")
        return sense - stealth

    def character_ready(self):
        """
        Character is ready to proceed from phase 1. Once all
        characters hit ready, we move to phase 2.
        """
        if self.state:
            self.state.character_ready()

    def do_attack(self, *args, **kwargs):
        """
        Processes an attack between a single attacker and a defender. This
        method is caller by the combat command set, via an attack command.
        Mods are determined by switches in the attack command or other
        attributes set in the attacker, target, or the environment when
        the attack command is used. By the time we're here, the final target
        has been determined and the mods have been calculated. All penalties
        are positive numbers as they increase the difficulty of checks. Bonuses
        are negative values, as they reduce difficulties to 0 or less.
        """
        from .attacks import Attack

        if self.combat:
            kwargs["risk"] = self.combat.ndb.risk
        kwargs["armor_pierce_bonus"] = self.armor_pierce_modifier + kwargs.get(
            "armor_pierce_bonus", 0
        )
        attack = Attack(*args, **kwargs)
        is_riposte = kwargs.get("is_riposte", False)
        try:
            if is_riposte:
                return attack.execute()
            attack.execute()
        except CombatError as err:
            if not is_riposte:
                self.char.msg(err)
        if self.state:
            self.state.lost_turn_counter += attack.lost_turn_penalty
        free_attack = kwargs.get("free_attack", False)
        if (
            not free_attack and self.state
        ):  # situations where a character gets a 'free' attack
            self.state.take_action(self.state.remaining_attacks)
            if self.state:  # could have left combat based on that action
                self.state.roll_fatigue()
        return attack

    def get_defenders(self):
        """Returns our defenders, in or out of combat"""
        if self.state:
            return self.state.get_defenders()
        return self.char.db.defenders

    def do_flank(self, target, sneaking=False, invis=False, attack_guard=True):
        """
        Attempts to circle around a character. If successful, we get an
        attack with a bonus.
        """
        attacker = self.char
        combat = self.combat
        defenders = self.get_defenders()
        message = (
            "%s attempts to move around %s to attack them while they are vulnerable. "
            % (attacker.name, target.name)
        )
        if defenders:
            # guards, have to go through them first
            for guard in defenders:
                g_fite = guard.combat
                if g_fite.sense_ambush(attacker, sneaking, invis) > 0:
                    if not attack_guard:
                        message += "%s sees them, and they back off." % guard.name
                        combat.msg(message)
                        combat.next_character_turn()
                        return
                    message += "%s stops %s but is attacked." % (
                        guard.name,
                        attacker.name,
                    )
                    combat.msg(message)
                    def_pen = -5 + combat_settings.STANCE_DEF_MOD[g_fite.stance]
                    self.do_attack(
                        guard,
                        attacker=attacker,
                        attack_penalty=5,
                        defense_penalty=def_pen,
                    )
                    return
        t_fite = target.combat
        if t_fite.sense_ambush(attacker, sneaking, invis) > 0:
            message += "%s moves in time to not be vulnerable." % target
            combat.msg(message)
            def_pen = -5 + combat_settings.STANCE_DEF_MOD[t_fite.stance]
            self.do_attack(
                target, attacker=attacker, attack_penalty=5, defense_penalty=def_pen
            )
            return
        message += "They succeed."
        self.msg(message)
        def_pen = 5 + combat_settings.STANCE_DEF_MOD[t_fite.stance]
        self.do_attack(
            target, attacker=attacker, attack_penalty=-5, defense_penalty=def_pen
        )

    def change_stance(self, new_stance):
        """
        Updates character's combat stance
        """
        self.char.msg("Stance changed to %s." % new_stance)
        self.stance = new_stance
        self.changed_stance = True
