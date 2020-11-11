"""
The Attacks class represents one or more simultaneous attacks done by
an attacker against one or more targets.

Flow of how a typical attack goes, from the intial call to assigning damage:
-start with a command such as harm or attack, or queued attack in statehandler
-character's combathandler.do_attack() is called, creating a new Attack instance
-attack.execute()
    build_attack_list()
    apply_attack_penalties()
    make_attacks()
        roll_attack()
            do_dice_check()
            modify_difficulty_by_risk() - if npc attacker
            get_modifier() - attack roll
        roll_defense() - returns unconscious autohit or highest of parry, block, dodge
        handle_atk_botch() - may trigger a riposte w/do_attack() & return its Attack obj
        calculate_damage() - returns a real damage value and mitigation message
            roll_damage()
                do_dice_check()
                modify_difficulty_by_risk() - if npc attacker
                get_modifier() - damage roll
            roll_mitigation()
            get_modifier() - defense roll
        build_dmg_msg() - several times, creating str: " for no/serious/etc damage"
        wake_up_sleeper()
        **returns if self is riposte**
        send_message_to_attacker()
        build_and_broadcast_story() - translates dict into self.story
            send_story_to_combat() - sends self.story to combat's messaging
    take_damage() - to targets, then again from ripostes to attacker
        change_health()
        do_dice_check() - several times, unconscious/death checks
        modify_difficulty_by_risk()
        msg_contents() - location, if someone saves vs unconscious/death
        fall_asleep()
        death_process()
        remove_combatant()
"""

from . import combat_settings
from collections import defaultdict
from server.utils.exceptions import WalrusJudgement
from server.utils.arx_utils import list_to_string
from world.conditions.models import RollModifier
from world.stats_and_skills import do_dice_check
from world.roll import Roll
from random import randint


class Attack(object):
    """
    For creating an attack, if an attacker is specified then any kwargs which are default values
    will be overridden with the attacker's own vaules. Some defaults that are None will actually
    be changed to 'True' unless they're specifically designated as False, in order to emulate
    the defaults expected for normal attacks: it's expected that a normal attack can be blocked,
    parried, and dodged unless explicitly set to False for those values. So bear in mind that
    'None' doesn't necessarily mean 'False' in this case.
    """

    AUTO_HIT = 9999

    # noinspection PyUnusedLocal
    def __init__(
        self,
        target=None,
        attacker=None,
        attack_penalty=0,
        defense_penalty=0,
        dmg_penalty=0,
        allow_botch=None,
        free_attack=False,
        targets=None,
        attacker_name=None,
        combat=None,
        stance=None,
        prev_targ=None,
        can_cleave=False,
        switch_chance=None,
        affect_real_dmg=None,
        can_be_parried=None,
        lost_turn_penalty=0,
        atk_modifiers=0,
        difficulty_mod=0,
        attack_stat="",
        attack_skill="",
        can_be_blocked=None,
        can_be_dodged=None,
        attack_stat_value=0,
        attack_skill_value=0,
        use_mitigation=True,
        can_kill=True,
        is_riposte=None,
        damage=None,
        private=None,
        inflictor=None,
        story=None,
        attack_tags=None,
        modifiers_override=None,
        remaining_attacks=None,
        damage_stat=None,
        armor_pierce_bonus=None,
        risk=None,
        attacker_is_npc=False,
        *args,
        **kwargs
    ):

        self.attacker = attacker
        if attacker:
            self.handler = attacker.combat
            self.combat = combat or attacker.combat.combat
            self.stance = stance or attacker.combat.stance
            self.state = attacker.combat.state
            self.prev_targ = prev_targ or self.state and self.state.prev_targ
            self.cleaving = can_cleave or attacker.combat.can_cleave
            self.switch_chance = (
                switch_chance
                if switch_chance is not None
                else attacker.combat.switch_chance
            )
            self.affect_real_dmg = (
                affect_real_dmg
                if affect_real_dmg is not None
                else self.combat and self.combat.ndb.affect_real_dmg
            )
            self.can_be_parried = (
                can_be_parried
                if can_be_parried is not None
                else attacker.combat.can_be_parried
            )
            self.can_be_dodged = (
                can_be_dodged
                if can_be_dodged is not None
                else attacker.combat.can_be_dodged
            )
            self.can_be_blocked = (
                can_be_blocked
                if can_be_blocked is not None
                else attacker.combat.can_be_blocked
            )
            self.targets = targets or self.state and self.state.targets
            self.atk_modifiers = atk_modifiers or attacker.combat.attack_modifier
            self.difficulty_mod = difficulty_mod or attacker.combat.difficulty_mod
            self.attack_stat = attack_stat or attacker.combat.attack_stat
            self.attack_skill = attack_skill or attacker.combat.attack_skill
            self.attack_tags = attack_tags or attacker.combat.modifier_tags
            self.remaining_attacks = (
                remaining_attacks or (self.state and self.state.remaining_attacks) or 1
            )
            self.damage_stat = damage_stat or attacker.combat.damage_stat
            self.allow_botch = allow_botch if allow_botch is not None else True
        else:
            self.handler = None
            self.state = None
            self.combat = combat
            self.stance = stance
            self.prev_targ = prev_targ
            self.cleaving = can_cleave
            self.switch_chance = switch_chance or 0
            self.affect_real_dmg = affect_real_dmg
            # make default for parrying/dodging/blocking be True unless False is specified
            self.can_be_parried = can_be_parried is None
            self.can_be_dodged = can_be_dodged is None
            self.can_be_blocked = can_be_blocked is None
            self.targets = targets or []
            self.atk_modifiers = atk_modifiers
            self.difficulty_mod = difficulty_mod
            self.attack_stat = attack_stat
            self.attack_skill = attack_skill
            self.attack_stat_value = attack_stat_value
            self.attack_skill_value = attack_skill_value
            self.attack_tags = attack_tags or ["physical", "mundane"]
            self.remaining_attacks = remaining_attacks or 1
            self.damage_stat = damage_stat
            self.allow_botch = allow_botch if allow_botch is not None else False
        self.lost_turn_penalty = lost_turn_penalty
        self.free_attack = free_attack
        self.target = target
        self.attack_penalty = attack_penalty
        self.defense_penalty = defense_penalty
        self.dmg_penalty = dmg_penalty
        self.damage = damage  # if set, we skip to-hit rolls and combat messaging
        self.story = story or ""
        self.story_spacer = " " if self.story else ""
        self.use_mitigation = use_mitigation
        self.attacker_name = attacker_name or str(attacker)
        self.can_kill = can_kill
        self.modifiers_override = modifiers_override or {}
        self.is_riposte = is_riposte
        self.armor_pierce_bonus = armor_pierce_bonus or 0
        self.riposte_dmg = 0
        self.private = private
        # A GM caller who can be messaged, not personally attacking
        self.inflictor = inflictor
        self.attacker_is_npc = attacker_is_npc
        if risk is None:
            from world.dominion.models import RPEvent

            self.risk = RPEvent.NORMAL_RISK
        else:
            self.risk = risk
        self.attack_dmgs = defaultdict(int)
        self.riposte_dmgs = []

    def __str__(self):
        return str(self.attacker_name)

    def execute(self):
        """
        Executes a full attack. Attacks may be simulated by calls of the other methods, but this by
        itself will call all of them and execute the attack in total.
        """
        if self.damage is None:  # None means a combat attack
            attack_list = self.build_attack_list()
            self.apply_attack_penalties()
        else:
            attack_list = self.targets
        if not attack_list:
            raise combat_settings.CombatError("No one to attack.")
        self.make_attacks(attack_list)
        if self.is_riposte:
            return self
        # apply damage to everyone who took it
        for target, dmg in self.attack_dmgs.items():
            self.take_damage(target, dmg)
        for riposte in self.riposte_dmgs:
            riposte.take_damage(self.attacker, riposte.riposte_dmg)

    def make_attacks(self, attack_list):
        """
        Iterate the attack list by rolling for attacker and defender and calculating damage
        if the attack succeeds. If this attack is a riposte, damage is recorded and the method
        ends. Otherwise, it builds a str dict about the attack. Then damage is applied
        to defenders and possibly to the attacker if there were any successful ripostes.
        """
        autohit = self.damage is not None  # True means a non-combat attack
        attack_prefix = "{c%s{n attacks " % self
        hits_and_misses = defaultdict(list)
        attacker_summaries = []
        for target in attack_list:
            damage = 0
            d_fite = target.combat
            defense_penalty = self.defense_penalty
            defense_penalty += combat_settings.STANCE_DEF_MOD[d_fite.stance]
            mit_msg = ""
            if d_fite.state and d_fite.state.covering_targs:
                defense_penalty += 5
            if autohit:
                a_roll = None
                d_roll = None
                result = 0
                riposte_attack = None
            else:
                a_roll = self.roll_attack(target, self.attack_penalty)
                d_roll = self.roll_defense(target, defense_penalty)
                result = a_roll - d_roll
                riposte_attack = self.handle_atk_botch(a_roll, result, target)
            if riposte_attack:
                riposte_dmg = riposte_attack.riposte_dmg
                if riposte_dmg > 0:
                    riposte_wound_desc = self.build_dmg_msg(self.attacker, riposte_dmg)
                    outcome = "{griposte %s{n" % riposte_wound_desc
                    self.riposte_dmgs.append(riposte_attack)
                else:
                    outcome = "parry"
            elif result <= -30:  # attacker botch without riposte
                outcome = "miss"
            elif result <= -16:  # defended against
                outcome = target.combat.state.last_defense_method or "miss"
            elif result > -16:  # a hit!
                dmgmult = 1.0 if autohit else self.get_dmgmult(result)
                damage, mit_msg = self.calculate_damage(
                    target, result, self.dmg_penalty, dmgmult
                )
                color = "{r" if damage else ""
                if autohit:
                    wound_desc = (
                        "unharmed"
                        if damage <= 0
                        else "harmed%s" % self.build_dmg_msg(target, damage)
                    )
                else:
                    wound_desc = self.granulate_hit_adjective(
                        dmgmult
                    ) + self.build_dmg_msg(target, damage)
                outcome = "%s%s{n" % (color, wound_desc)
                # record that they took damage, but don't apply it yet
                if damage > 0:
                    self.attack_dmgs[target] += damage
            self.wake_up_sleeper(target)
            if self.is_riposte:
                self.riposte_dmg = damage
                return
            elif autohit:
                outcome_summary = "is %s" % outcome
                # For non-combat attacks, individual message is sent per target.
                self.send_message_to_target(target, outcome_summary, mit_msg)
            else:
                # outcome_summary and target_outcome_summary are verbose about dice rolls / mitigation
                # for the target/attacker views, but 'outcome' is what the public see
                dmg_msg = " (%d)" % damage if damage else ""
                outcome_summary = "%d vs %d: %s%s" % (a_roll, d_roll, outcome, dmg_msg)
                target_outcome_summary = outcome_summary + ". " + mit_msg
                target.msg(
                    "%sYOU and rolled %s" % (attack_prefix, target_outcome_summary),
                    options={"roll": True},
                )
                hits_and_misses[target].append(outcome)
            attacker_summaries.append("{c%s{n %s" % (target, outcome_summary))
        # For both combat & non-combat attacks, the attacker sees rolls & dmg of each target.
        self.send_message_to_attacker(attacker_summaries)
        if not autohit:
            # For combat attacks, the summary gets sent to everyone in the fight
            self.build_and_broadcast_story(attack_prefix, hits_and_misses)

    @staticmethod
    def get_dmgmult(result):
        """Returns the damage multiplier based on the result"""
        if -5 > result >= -15:
            dmgmult = 0.25
        elif 5 > result >= -5:
            dmgmult = 0.5
        elif 15 > result >= 5:
            dmgmult = 0.75
        elif result > 9000:
            dmgmult = 2.0
        else:  # 15 or higher over defense roll
            dmgmult = 1.0
        return dmgmult

    @staticmethod
    def granulate_hit_adjective(dmgmult):
        """Returns the message based on the damage multiplier"""
        message = ""
        if 0 < dmgmult <= 0.25:
            message = "barely touch"
        elif dmgmult <= 0.5:
            message = "graze"
        elif dmgmult <= 0.75:
            message = "glancing hit"
        elif dmgmult <= 1.0:
            message = "hit"
        elif dmgmult >= 2.0:
            message = "no-contest hit"
        return message

    @staticmethod
    def build_dmg_msg(targ, dmg):
        """Builds a message based on wound descriptor"""
        return " for %s damage" % targ.get_wound_descriptor(dmg)

    def apply_attack_penalties(self):
        """If you have a penalty, I'll apply it! --Wimp Co(de)"""
        # modifier if we're covering anyone's retreat
        if self.state and self.state.covering_targs:
            self.attack_penalty += 5
        # modifiers from our stance (aggressive, defensive, etc)
        self.attack_penalty += combat_settings.STANCE_ATK_MOD[self.stance]

    def build_attack_list(self):
        """Who are we killing, again? Oh everyone? Fun! --Emerald"""
        attack_list = (
            self.targets if self.cleaving and not self.free_attack else [self.target]
        )
        if (
            not self.free_attack
            and self.switch_chance
            and (self.remaining_attacks - 1) > 0
        ):
            from .utils import npc_target_choice

            for _ in range(self.remaining_attacks - 1):
                attack_list.append(
                    npc_target_choice(
                        self.target, self.targets, self.prev_targ, self.switch_chance
                    )
                )
        return attack_list

    def get_modifier(self, target, check_type):
        """
        Gets a modifier for a roll based on what the type is and who's rolling
        Args:
            target: The target we're checking
            check_type: Integer constant that corresponds to a type of check

        Returns:
            Value of the modifier to the roll as an integer
        """
        if check_type == RollModifier.DEFENSE:
            return target.get_total_modifier(check_type, target_tags=self.attack_tags)
        val = 0
        tags = target.combat.modifier_tags
        if self.attacker:
            val += self.attacker.get_total_modifier(check_type, target_tags=tags)
        elif self.modifiers_override:
            for tag in tags:
                val += self.modifiers_override.get(tag, 0)
        return val

    def roll_attack(self, target, penalty=0):
        """
        Returns our roll to hit with an attack. Half of our roll is randomized.
        """
        autohit = self.damage is not None
        diff = 2  # base difficulty before mods
        penalty -= self.atk_modifiers
        diff += penalty
        diff += self.difficulty_mod
        if not autohit:
            roll = do_dice_check(
                self.attacker,
                stat=self.attack_stat,
                skill=self.attack_skill,
                difficulty=diff,
            )
        else:
            roll_object = Roll()
            roll_object.character_name = self.attacker_name
            if self.attack_skill:
                roll_object.skills = {self.attack_skill: self.attack_skill_value}
            else:
                roll_object.stat_keep = True
                roll_object.skill_keep = False
            roll_object.stats = {self.attack_stat: self.attack_stat_value}
            roll = roll_object.roll()
        if self.attacker_is_npc:
            roll = self.modify_difficulty_by_risk(roll)
        if roll > 2:
            roll = (roll // 2) + randint(0, (roll // 2))
        if not autohit:
            roll += self.get_modifier(target, RollModifier.ATTACK)
        return roll

    def handle_atk_botch(self, a_roll, result, target):
        """
        Processes the results of botching an executed attack.
        Returns the riposte Attack object.
        """
        botcher = self.attacker
        riposte_attack = None
        d_fite = target.combat
        if self.allow_botch:
            if a_roll < 0 and result < -30:
                can_riposte = self.can_be_parried and d_fite.can_riposte
                if not target.conscious:
                    can_riposte = False
                if can_riposte and target and botcher:
                    riposte_attack = target.combat.do_attack(
                        target=botcher,
                        attacker=target,
                        allow_botch=False,
                        free_attack=True,
                        is_riposte=True,
                    )
                else:
                    self.lost_turn_penalty = (
                        1  # Not += because cleave might accumulate a bunch
                    )
        return riposte_attack

    @staticmethod
    def wake_up_sleeper(target):
        """Wakes up our target if they are asleep."""
        if not target.conscious and target.db.sleep_status == "asleep":
            target.wake_up()

    def roll_defense(self, target, penalty=0):
        """
        Returns target's roll to avoid being hit. We use the highest roll out of
        parry, block, and dodge. Half of our roll is then randomized.
        """
        if not target.conscious:
            return -self.AUTO_HIT
        defense = target.combat
        # making defense easier than attack to slightly lower combat lethality
        diff = -2  # base difficulty before mods
        penalty -= defense.defense_modifier
        diff += penalty
        if defense.state:
            defense.state.times_attacked += 1
        total = None

        def change_total(current_total, new_roll):
            """Helper function to change total of defense rolls"""
            if new_roll >= 2:
                new_roll = (new_roll // 2) + randint(0, (new_roll // 2))
            if not current_total:
                current_total = new_roll
            elif new_roll > 0:
                if current_total > new_roll:
                    current_total += new_roll // 2
                else:
                    current_total = (current_total // 2) + new_roll
            elif new_roll > current_total:
                current_total = (current_total + new_roll) // 2
            return current_total, new_roll

        if self.can_be_parried and defense.can_parry:
            parry_diff = diff + 10
            parry_roll = int(
                do_dice_check(
                    target,
                    stat=defense.attack_stat,
                    skill=self.attack_skill,
                    difficulty=parry_diff,
                )
            )
            if parry_roll > 1:
                parry_roll = (parry_roll // 2) + randint(0, (parry_roll // 2))
            total = parry_roll
        else:
            parry_roll = -1000
        if self.can_be_blocked and defense.can_block:
            try:
                block_diff = diff + defense.dodge_penalty
            except (AttributeError, TypeError, ValueError):
                block_diff = diff
            block_roll = int(
                do_dice_check(
                    target, stat="dexterity", skill="dodge", difficulty=block_diff
                )
            )
            total, block_roll = change_total(total, block_roll)
        else:
            block_roll = -1000
        if self.can_be_dodged and defense.can_dodge:
            # dodging is easier than parrying
            dodge_diff = diff - 10
            try:
                dodge_diff += defense.dodge_penalty
            except (AttributeError, TypeError, ValueError):
                pass
            dodge_roll = int(
                do_dice_check(
                    target, stat="dexterity", skill="dodge", difficulty=dodge_diff
                )
            )
            total, dodge_roll = change_total(total, dodge_roll)
        else:
            dodge_roll = -1000
        if total is None:
            total = -1000
        # return our highest defense roll
        if parry_roll > block_roll and parry_roll > dodge_roll:
            defense.last_defense_method = "parry"
        elif block_roll > parry_roll and block_roll > dodge_roll:
            defense.last_defense_method = "block"
        else:
            defense.last_defense_method = "dodge"
        return total

    def roll_damage(self, target, penalty=0, dmgmult=1.0):
        """
        Returns our roll for damage against target. If damage is to be
        enhanced, (dmgmult > 1.0) it is done pre-mitigation, here.
        """
        keep_dice = self.handler.weapon_damage + 1
        try:
            keep_dice += self.attacker.traits.get_stat_value(self.damage_stat) // 2
        except (TypeError, AttributeError, ValueError):
            pass
        if keep_dice < 3:
            keep_dice = 3
        diff = 0  # base difficulty before mods
        diff += penalty
        damage = do_dice_check(
            self.attacker,
            stat=self.handler.damage_stat,
            stat_keep=True,
            difficulty=diff,
            bonus_dice=self.handler.weapon_damage,
            keep_override=keep_dice,
        )
        damage += self.handler.flat_damage_bonus
        if dmgmult > 1.0:  # if dmg is enhanced, it is done pre-mitigation
            damage = int(damage * dmgmult)
        if self.attacker_is_npc:
            damage = self.modify_difficulty_by_risk(damage)
        if damage <= 0:
            damage = 1
        # 3/4ths of our damage is purely random
        damage = damage // 4 + randint(0, ((damage * 3) // 4) + 1)
        damage += self.get_modifier(target, RollModifier.DAMAGE)
        return damage

    def roll_mitigation(self, target, result=0):
        """
        Returns our damage reduction against attacker. If the 'result' is
        higher than 15, that number is subtracted off our armor.
        """
        if hasattr(target, "armor"):
            armor = target.armor
        else:
            armor = target.db.armor_class or 0
        # our soak is sta+willpower+survival
        armor += randint(0, (target.combat.soak * 2) + 1)
        # if the resulting difference of attack/defense rolls is huge, like
        # for unconsciousness, armor is zilched. TODO: Maybe change this?
        result -= target.armor_resilience - self.armor_pierce_bonus
        if result > 0:
            armor -= result
        if armor <= 0:
            return 0
        if armor < 2:
            return randint(0, armor)
        # half of our armor is random
        return (armor // 2) + randint(0, (armor // 2))

    def calculate_damage(self, target, result=0, dmg_penalty=0, dmgmult=1.0):
        """
        Damage may be reduced/soaked by modifiers such as armor. If damage is to
        be reduced, (dmgmult < 1.0) it is done post-mitigation, here.
        """
        mit_msg = ""
        dmg = self.damage  # a damage override means non-combat attack
        if dmg is None:
            dmg = self.roll_damage(target, dmg_penalty, dmgmult)
        if self.use_mitigation:
            mitigation = self.roll_mitigation(target, result=result)
            mitigation += self.get_modifier(target, RollModifier.DEFENSE)
            new_dmg = dmg - mitigation
            if new_dmg < 0:
                new_dmg = 0
            riposte = "riposte " if self.is_riposte else ""
            mit_msg = "Your armor mitigated %d of the %sdamage." % (
                dmg - new_dmg,
                riposte,
            )
            if (
                riposte
            ):  # otherwise, riposte mitigation messages would be lost to the void
                target.msg(mit_msg)
            dmg = new_dmg
        if dmgmult < 1.0:  # if dmg is reduced, it is done post-mitigation
            dmg = int(dmg * dmgmult)
        return dmg, mit_msg

    def take_damage(self, victim, dmg):
        """
        This is where the consequences of final damage are applied to a victim. They can
        be knocked unconscious or killed, and any combat they're in is informed.
        Characters who are incapacitated are moved to the appropriate dictionary.
        Health rating is 10xsta + 10.
        Unconsciousness checks are after health rating is exceeded. When
        damage is double health rating, death checks begin. Player characters
        will always fall unconscious first, then be required to make death
        checks after further damage, with the exception of extraordinary
        situations. NPCs, on the other hand, can be killed outright.

            Args:
                victim: Our target
                dmg: The amount of damage after all mitgation/reductions
        """
        allow_one_shot = True
        affect_real_dmg = self.affect_real_dmg
        can_kill = self.can_kill
        if self.combat:
            allow_one_shot = self.combat.ndb.random_deaths
        loc = victim.location
        # some flags so messaging is in proper order
        knock_uncon = False
        kill = False
        remove = False
        glass_jaw = victim.glass_jaw
        is_npc = victim.is_npc
        message = ""
        # max hp is (stamina * 10) + 10
        max_hp = victim.max_hp
        # apply AE damage to multinpcs if we're cleaving
        if self.cleaving and hasattr(victim, "ae_dmg"):
            victim.ae_dmg += dmg
        victim.change_health(
            -dmg, quiet=True, affect_real_dmg=affect_real_dmg, wake=False
        )
        grace_period = (
            False  # one round delay between incapacitation and death for PCs if allowed
        )
        if victim.dmg > max_hp:
            # if we're not incapacitated, we start making checks for it
            if victim.conscious and not victim.sleepless:
                # check is sta + willpower against % dmg past uncon to stay conscious
                if not glass_jaw:
                    diff = int((float(victim.dmg - max_hp) / max_hp) * 100)
                    consc_check = do_dice_check(
                        victim,
                        stat_list=["stamina", "willpower"],
                        skill="survival",
                        stat_keep=True,
                        difficulty=diff,
                        quiet=False,
                    )
                else:
                    consc_check = -1
                if consc_check >= 0:
                    if not self.private:
                        message = "%s remains capable of fighting." % victim
                    grace_period = True  # we can't be killed if we succeeded this check to remain standing
                    # we're done, so send the message for the attack
                else:
                    knock_uncon = True
                # for PCs who were knocked unconscious this round
                if not is_npc and not grace_period and not allow_one_shot:
                    grace_period = (
                        True  # if allow_one_shot is off, we can't be killed yet
                    )
            # PC/NPC who was already unconscious before attack, or an NPC who was knocked unconscious by our attack
            if not grace_period:  # we are allowed to kill the character
                dt = victim.death_threshold
                diff = int(
                    (float(victim.dmg - int(dt * max_hp)) / int(dt * max_hp)) * 100
                )
                if affect_real_dmg and not is_npc and not glass_jaw:
                    diff = self.modify_difficulty_by_risk(diff)
                if diff < 0:
                    diff = 0
                # npcs always die. Sucks for them.
                if (
                    not glass_jaw
                    and do_dice_check(
                        victim,
                        stat_list=["stamina", "willpower"],
                        skill="survival",
                        stat_keep=True,
                        difficulty=diff,
                        quiet=False,
                    )
                    >= 0
                ):
                    message = "%s remains alive, but close to death." % victim
                    if victim.combat.multiple:
                        # was incapacitated but not killed, but out of fight and now we're on another targ
                        if affect_real_dmg:
                            victim.real_dmg = victim.ae_dmg
                        else:
                            victim.temp_dmg = victim.ae_dmg
                elif not victim.combat.multiple:
                    if affect_real_dmg:
                        kill = can_kill
                    # remove a 'killed' character from combat whether it was a real death or fake
                    remove = True
                else:
                    if affect_real_dmg:
                        kill = can_kill
                    else:
                        knock_uncon = True
        if loc and message:
            loc.msg_contents(message, options={"roll": True})
        if knock_uncon:
            victim.fall_asleep(
                uncon=True, verb="incapacitated", affect_real_dmg=affect_real_dmg
            )
        if kill:
            victim.death_process(affect_real_dmg=affect_real_dmg)
        if victim.combat.multiple:
            try:
                if victim.quantity <= 0:
                    remove = True
            except AttributeError:
                pass
        if self.combat and remove:
            self.combat.remove_combatant(victim)

    def modify_difficulty_by_risk(self, difficulty):
        """Calculate difference in difficulty based on the risk"""
        risk = self.risk
        return int(difficulty * risk * 0.25)

    def build_and_broadcast_story(self, attack_prefix, hits_and_misses):
        """
        Takes a dict of targets/outcomes of this attack & transform into a story.

            Args:
                attack_prefix (string): Introduces the attacker.
                hits_and_misses (dict): Each target's list of responses to attacks.

        Counts attacks against a target and groups the outcomes thereafter. Example:
        'Emerald attacks Bob 2 times (hit for major damage, parry), Jane (graze for no damage),
        and Bill (riposte for no damage).'
        """
        if not hits_and_misses:
            raise WalrusJudgement
        all_target_msgs = []
        for victim, list_of_attacks in hits_and_misses.items():
            msg = "{c%s{n" % victim
            if len(list_of_attacks) > 1:
                msg += " %s times" % len(list_of_attacks)
            msg += " (%s)" % list_to_string(list_of_attacks)
            all_target_msgs.append(msg)
        message = attack_prefix + list_to_string(all_target_msgs) + "."
        self.story = self.story_spacer + message
        self.send_story_to_combat()

    def send_story_to_combat(self):
        """Walrus says Story or GTFO."""
        if self.combat:
            self.combat.msg(self.story, options={"roll": True})
        else:
            raise WalrusJudgement

    def send_message_to_target(self, target, summary, mit_msg):
        """Sends individual message to a target or their location, or sends them an inform."""
        message = (
            self.story
            + self.story_spacer
            + "%d inflicted and {c%s{n %s." % (self.damage, target, summary)
        )
        if mit_msg and (self.private or not target.location):
            message = message + " " + mit_msg
        if not target.location:
            target.player_ob.inform(message, category="Damage")
        elif self.private:
            target.msg(message, options={"roll": True})
        else:
            target.location.msg_contents(message, options={"roll": True})
            if mit_msg:
                target.msg(mit_msg)

    def send_message_to_attacker(self, attacker_summaries):
        """
        Sends a summary of damage to whomever is responsible for dealing it.

            Args:
                attacker_summaries (list): List of strings that show victim and
                    the outcome of attack. When the resulting message is for an
                    attacker, strings are verbose with dice/damage numbers.

        Example for self.inflictor:
        'The trap springs! You inflict 30. Bob is harmed for critical damage, Bill is unharmed,
        and Jane is harmed for minor damage.'

        Example for self.attacker:
        'YOU attack Bob 32 vs 4: graze for minor damage (6), Jane -16 vs 4: parry,
        and Bill -32 vs 17: riposte for minor damage.'
        """
        if self.inflictor:
            self.inflictor.msg(
                "%s%sYou inflict %s. %s."
                % (
                    self.story,
                    self.story_spacer,
                    self.damage,
                    list_to_string(attacker_summaries),
                ),
                options={"roll": True},
            )
        elif self.attacker:
            self.attacker.msg(
                "YOU attack %s." % list_to_string(attacker_summaries),
                options={"roll": True},
            )
