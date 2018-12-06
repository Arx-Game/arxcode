"""
Npc guards, which are connected to an AgentOb instance,
which is itself connected to an Agent instance. The Agent
instance determines the type of agents (guards, spies, etc),
and how many are currently unassigned. AgentOb is for assigned
agents, and stores how many, and this object which acts as its
in-game representation on the grid.

For this object, our values are populated by setup_agent, while
we already have the 'agentob' property given by the related
OneToOne field from our associated AgentOb.

We come into being in one of two ways:
1) We're assigned to an individual player as that player-character's
agents, who can them summon them.
2) A player is in a square that is marked as having the attribute
'unassigned_guards' which points to an Agent instance, and then
should have the cmdset in that room that allows them to draw upon
those guards if they meet certain criteria. If they execute that
command, it then summons guards for that player character.

"""
from typeclasses.characters import Character
from .npc_types import (get_npc_stats, get_npc_desc, get_npc_skills,
                        get_npc_singular_name, get_npc_plural_name, get_npc_weapon,
                        get_armor_bonus, get_hp_bonus, primary_stats,
                        assistant_skills, spy_skills, get_npc_stat_cap, check_passive_guard,
                        COMBAT_TYPES, get_innate_abilities, ABILITY_COSTS, ANIMAL, SMALL_ANIMAL)
from world.stats_and_skills import (do_dice_check, get_stat_cost, get_skill_cost,
                                    PHYSICAL_STATS, MENTAL_STATS, SOCIAL_STATS)
import time


class Npc(Character):
    """
    NPC objects

    """
    ATK_MOD = 30
    DEF_MOD = -30
    # ------------------------------------------------
    # PC command methods
    # ------------------------------------------------

    def attack(self, targ, kill=False):
        """
        Attack a given target. If kill is False, we will not kill any
        characters in combat.
        """
        self.execute_cmd("+fight %s" % targ)
        if kill:
            self.execute_cmd("kill %s" % targ)
        else:
            self.execute_cmd("attack %s" % targ)
        # if we're ordered to attack, don't vote to end
        if self.combat.state:
            self.combat.state.wants_to_end = False

    def stop(self):
        """
        Stop attacking/exit combat.
        """
        state = self.combat.state
        if state:
            state.wants_to_end = True
            state.reset()
            state.setup_phase_prep()

    def _get_passive(self):
        return self.db.passive_guard or False

    def _set_passive(self, val):
        if val:
            self.db.passive_guard = True
            self.stop()
        else:
            self.db.passive_guard = False
            if self.combat.state:
                self.combat.state.wants_to_end = False
    passive = property(_get_passive, _set_passive)

    @property
    def discreet(self):
        return self.db.discreet_guard or False

    @discreet.setter
    def discreet(self, val):
        if val:
            self.db.discreet_guard = True
        else:
            self.db.discreet_guard = False

    # ------------------------------------------------
    # Inherited Character methods
    # ------------------------------------------------
    def at_object_creation(self):
        """
        Called once, when this object is first created.
        """
        self.db.health_status = "alive"
        self.db.sleep_status = "awake"
        self.db.automate_combat = True
        self.db.damage = 0
        self.at_init()

    def resurrect(self, *args, **kwargs):
        """
        Cue 'Bring Me Back to Life' by Evanessence.
        """
        self.db.health_status = "alive"
        if self.location:
            self.location.msg_contents("{w%s has returned to life.{n" % self.name)

    def fall_asleep(self, uncon=False, quiet=False, verb=None, **kwargs):
        """
        Falls asleep. Uncon flag determines if this is regular sleep,
        or unconsciousness.
        """
        reason = " is %s and" % verb if verb else ""
        if uncon:
            self.db.sleep_status = "unconscious"
        else:
            self.db.sleep_status = "asleep"
        if self.location and not quiet:
            self.location.msg_contents("%s%s falls %s." % (self.name, reason, self.db.sleep_status))

    def wake_up(self, quiet=False):
        """
        Wakes up.
        """
        self.db.sleep_status = "awake"
        if self.location:
            self.location.msg_contents("%s wakes up." % self.name)

    def get_health_appearance(self):
        """
        Return a string based on our current health.
        """
        name = self.name
        if self.db.health_status == "dead":
            return "%s is currently dead." % name
        wound = float(self.dmg)/float(self.max_hp)
        if wound <= 0:
            msg = "%s is in perfect health." % name
        elif 0 < wound <= 0.1:
            msg = "%s is very slightly hurt." % name
        elif 0.1 < wound <= 0.25:
            msg = "%s is moderately wounded." % name
        elif 0.25 < wound <= 0.5:
            msg = "%s is seriously wounded." % name
        elif 0.5 < wound <= 0.75:
            msg = "%s is very seriously wounded." % name
        elif 0.75 < wound <= 2.0:
            msg = "%s is critically wounded." % name
        else:
            msg = "%s is very critically wounded, possibly dying." % name
        awake = self.db.sleep_status
        if awake and awake != "awake":
            msg += " They are %s." % awake
        return msg

    def recovery_test(self, diff_mod=0, free=False):
        """
        A mechanism for healing characters. Whenever they get a recovery
        test, they heal the result of a willpower+stamina roll, against
        a base difficulty of 0. diff_mod can change that difficulty value,
        and with a higher difficulty can mean it can heal a negative value,
        resulting in the character getting worse off. We go ahead and change
        the player's health now, but leave the result of the roll in the
        caller's hands to trigger other checks - death checks if we got
        worse, unconsciousness checks, whatever.
        """
        diff = 0 + diff_mod
        roll = do_dice_check(self, stat_list=["willpower", "stamina"], difficulty=diff)
        if roll > 0:
            self.msg("You feel better.")
        else:
            self.msg("You feel worse.")
        applied_damage = self.dmg - roll  # how much dmg character has after the roll
        if applied_damage < 0:
            applied_damage = 0  # no remaining damage
        self.db.damage = applied_damage
        if not free:
            self.db.last_recovery_test = time.time()
        return roll

    def sensing_check(self, difficulty=15, invis=False, allow_wake=False):
        """
        See if the character detects something that is hiding or invisible.
        The difficulty is supplied by the calling function.
        Target can be included for additional situational
        """
        roll = do_dice_check(self, stat="perception", stat_keep=True, difficulty=difficulty)
        return roll

    def get_fakeweapon(self, force_update=False):
        if not self.db.fakeweapon or force_update:
            npctype = self._get_npc_type()
            quality = self._get_quality()
            self.db.fakeweapon = get_npc_weapon(npctype, quality)
        return self.db.fakeweapon

    def _set_fakeweapon(self, val):
        self.db.fakeweapon = val

    fakeweapon = property(get_fakeweapon, _set_fakeweapon)

    @property
    def is_npc(self):
        return True

    @property
    def death_threshold(self):
        """
        Npcs are easier to kill than player characters. Make death checks immediately.
        Returns:
            float: Multiplier on how much higher than our max health our damage must be to
                make rolls to survive death.
        """
        return 1.0

    @property
    def glass_jaw(self):
        return "story_npc" not in self.tags.all()

    # npcs are easier to hit than players, and have an easier time hitting
    @property
    def defense_modifier(self):
        return super(Npc, self).defense_modifier + self.DEF_MOD

    @property
    def attack_modifier(self):
        return super(Npc, self).attack_modifier + self.ATK_MOD

    # ------------------------------------------------
    # New npc methods
    # ------------------------------------------------
    def _get_npc_type(self):
        return self.db.npc_type or 0
    npc_type = property(_get_npc_type)

    def _get_quality(self):
        return self.db.npc_quality or 0
    quality = property(_get_quality)

    @property
    def quantity(self):
        return 1 if self.conscious else 0

    @property
    def weaponized(self):
        return True

    def setup_stats(self, ntype, threat):
        self.db.npc_quality = threat
        for stat, value in get_npc_stats(ntype).items():
            self.attributes.add(stat, value)
        skills = get_npc_skills(ntype)
        for skill in skills:
            skills[skill] += threat
        self.db.skills = skills
        self.db.fakeweapon = get_npc_weapon(ntype, threat)
        self.db.armor_class = get_armor_bonus(self._get_npc_type(), self._get_quality())
        self.db.bonus_max_hp = get_hp_bonus(self._get_npc_type(), self._get_quality())

    @property
    def num_armed_guards(self):
        if self.weaponized:
            return self.quantity
        return 0

    def setup_npc(self, ntype=0, threat=0, num=1, sing_name=None, plural_name=None, desc=None, keepold=False):
        self.db.damage = 0
        self.db.health_status = "alive"
        self.db.sleep_status = "awake"

        from commands.cmdsets import death
        self.cmdset.delete(death.DeathCmdSet)

        # if we don't
        if not keepold:
            self.db.npc_type = ntype
            self.set_npc_new_name(sing_name, plural_name)
            self.set_npc_new_desc(desc)
        self.setup_stats(ntype, threat)

    def set_npc_new_name(self, sing_name=None, plural_name=None):
        self.name = sing_name or plural_name or "#%s" % self.id

    def set_npc_new_desc(self, desc=None):
        self.desc = desc or get_npc_desc(self.db.npc_type or 0)


class MultiNpc(Npc):
    def multideath(self, num, death=False):
        living = self.db.num_living or 0
        if num > living:
            num = living
        self.db.num_living = living - num
        if death:
            dead = self.db.num_dead or 0
            self.db.num_dead = dead + num
        else:
            incap = self.db.num_incap or 0
            self.db.num_incap = incap + num

    def get_singular_name(self):
        return self.db.singular_name or get_npc_singular_name(self._get_npc_type())

    def get_plural_name(self):
        return self.db.plural_name or get_npc_plural_name(self._get_npc_type())

    @property
    def ae_dmg(self):
        return self.ndb.ae_dmg or 0

    @ae_dmg.setter
    def ae_dmg(self, val):
        self.ndb.ae_dmg = val

    # noinspection PyAttributeOutsideInit
    def death_process(self, *args, **kwargs):
        """
        This object dying. Set its state to dead, send out
        death message to location. Add death commandset.
        """
        num = 1
        if self.ae_dmg >= self.max_hp:
            num = self.quantity
            message = "{r%s have all died.{n" % get_npc_plural_name(self._get_npc_type())
        else:
            message = "{r%s has died.{n" % get_npc_singular_name(self._get_npc_type())
        if self.location:
            self.location.msg_contents(message)
        if kwargs.get('affect_real_dmg', True):
            self.multideath(num=num, death=True)
            self.real_dmg = self.ae_dmg
        else:
            self.temp_losses += num
            self.temp_dmg = self.ae_dmg

    def fall_asleep(self, uncon=False, quiet=False, verb=None, **kwargs):
        """
        Falls asleep. Uncon flag determines if this is regular sleep,
        or unconsciousness.
        """
        reason = " is %s and " % verb if verb else ""
        if self.location:
            self.location.msg_contents("{w%s%s falls %s.{n" % (get_npc_singular_name(self._get_npc_type()),
                                                               reason, "unconscious" if uncon else "asleep"))
        if kwargs.get('affect_real_dmg', True):
            self.multideath(num=1, death=False)
        else:
            self.temp_losses += 1
        # don't reset damage here since it's used for death check. Reset in combat process

    # noinspection PyAttributeOutsideInit
    def setup_name(self):
        npc_type = self.db.npc_type
        if self.db.num_living == 1 and not self.db.num_dead:
            self.key = self.db.singular_name or get_npc_singular_name(npc_type)
        else:
            if self.db.num_living == 1:
                noun = self.db.singular_name or get_npc_singular_name(npc_type)
            else:
                noun = self.db.plural_name or get_npc_plural_name(npc_type)
            if not self.db.num_living and self.db.num_dead:
                noun = "dead %s" % noun
                self.key = "%s %s" % (self.db.num_dead, noun)
            else:
                self.key = "%s %s" % (self.db.num_living, noun)
        self.save()

    def setup_npc(self, ntype=0, threat=0, num=1, sing_name=None, plural_name=None, desc=None, keepold=False):
        self.db.num_living = num
        self.db.num_dead = 0
        self.db.num_incap = 0
        self.db.damage = 0
        self.db.health_status = "alive"
        self.db.sleep_status = "awake"
        # if we don't
        if not keepold:
            self.db.npc_type = ntype
            self.db.singular_name = sing_name
            self.db.plural_name = plural_name
            self.desc = desc or get_npc_desc(ntype)
        self.setup_stats(ntype, threat)
        self.setup_name()

    # noinspection PyAttributeOutsideInit
    def dismiss(self):
        self.location = None
        self.save()

    @property
    def quantity(self):
        num = self.db.num_living or 0
        return num - self.temp_losses

    @property
    def conscious(self):
        return self.quantity > 0

    @property
    def temp_losses(self):
        if self.ndb.temp_losses is None:
            self.ndb.temp_losses = 0
        return self.ndb.temp_losses

    @temp_losses.setter
    def temp_losses(self, val):
        self.ndb.temp_losses = val


# noinspection PyAttributeOutsideInit
class AgentMixin(object):

    @property
    def desc(self):
        self.agent.refresh_from_db(fields=('desc',))
        return self.agent.desc

    @desc.setter
    def desc(self, val):
        self.agent.desc = val
        self.agent.save()

    def assignment_string(self, guarding_name):
        if self.agent.unique:
            return "{wAssigned to:{n %s " % guarding_name
        return "{w%s Assigned to:{n %s" % (self.agentob.quantity, guarding_name)

    def display(self, caller=None):
        guarding = self.db.guarding
        if guarding:
            guarding_name = self.db.guarding.key
        else:
            guarding_name = "None"
        msg = self.assignment_string(guarding_name)
        if not guarding or (caller and guarding == caller.char_ob):
            msg += " {wLocation:{n %s" % (self.location or self.db.docked or "Home Barracks")
        return msg

    def setup_agent(self  # type: Retainer or Agent
                    ):
        """
        We'll set up our stats based on the type given by our agent class.
        """
        agent = self.agentob
        agent_class = agent.agent_class
        quality = agent_class.quality or 0
        # set up our stats based on our type
        desc = agent_class.desc
        atype = agent_class.type
        self.setup_npc(ntype=atype, threat=quality, num=agent.quantity, desc=desc)
        self.db.passive_guard = check_passive_guard(atype)

    def setup_locks(self  # type: Retainer or Agent
                    ):
        # base lock - the 'command' lock string
        lockfunc = ["command: %s", "desc: %s"]
        player_owner = None
        assigned_char = self.guarding
        owner = self.agentob.agent_class.owner
        if owner.player:
            player_owner = owner.player.player
        if not player_owner:
            org_owner = owner.organization_owner
            if assigned_char:
                perm = "rank(2, %s) or id(%s)" % (org_owner.name, assigned_char.id)
            else:
                perm = "rank(2, %s)" % org_owner.name
        else:
            if assigned_char:
                perm = "pid(%s) or id(%s)" % (player_owner.id, assigned_char.id)
            else:
                perm = "pid(%s)" % player_owner.id
        for lock in lockfunc:
            # add the permission to the lock function from above
            # noinspection PyAugmentAssignment
            lock = lock % perm
            # note that this will replace any currently defined 'command' lock
            self.locks.add(lock)

    def assign(self,  # type: Retainer or Agent
               targ):
        """
        When given a Character as targ, we add ourselves to their list of
        guards, saved as an Attribute in the character object.
        """
        guards = targ.db.assigned_guards or []
        if self not in guards:
            guards.append(self)
        targ.db.assigned_guards = guards
        self.guarding = targ
        self.setup_locks()
        self.setup_name()
        if self.agentob.quantity < 1:
            self.agentob.quantity = 1
            self.agentob.save()

    @property
    def guarding(self  # type: Retainer or Agent
                 ):
        return self.db.guarding

    @guarding.setter
    def guarding(self,  # type: Retainer or Agent
                 val):
        if not val:
            self.attributes.remove("guarding")
            return
        self.db.guarding = val

    def start_guarding(self, val):
        self.guarding = val

    def stop_guarding(self  # type: Retainer or Agent
                      ):
        targ = self.guarding
        if targ:
            targ.remove_guard(self)
        self.stop_follow(unassigning=True)
        self.guarding = None
        self.assisted_investigations.update(currently_helping=False)

    def lose_agents(self, num, death=False):
        if num < 1:
            return 0
        self.unassign()

    def gain_agents(self, num):
        self.setup_name()

    def setup_name(self):
        self.name = self.agent.colored_name or self.agent.name

    def unassign(self  # type: Retainer or Agent
                 ):
        """
        When unassigned from the Character we were guarding, we remove
        ourselves from their guards list and then call unassign in our
        associated AgentOb.
        """
        self.agentob.unassign()
        self.locks.add("command: false()")
        self.stop_guarding()

    def _get_npc_type(self):
        return self.agent.type

    def _get_quality(self):
        return self.agent.quality or 0
    npc_type = property(_get_npc_type)
    quality = property(_get_quality)

    def stop_follow(self,  # type: Retainer or Agent
                    dismiss=True, unassigning=False):
        super(AgentMixin, self).stop_follow()
        # if we're not being unassigned, we dock them. otherwise, they're gone
        if dismiss:
            self.dismiss(dock=not unassigning)

    def summon(self,  # type: Retainer or Agent
               summoner=None):
        """
        Have these guards appear to defend the character. This should generally only be
        called in a location that permits it, such as their house barracks, or in a
        square close to where the guards were docked.
        """
        if not summoner:
            summoner = self.db.guarding
        loc = summoner.location
        mapping = {'secret': True}
        self.move_to(loc, mapping=mapping)
        self.follow(self.db.guarding)
        docked_loc = self.db.docked
        if docked_loc and docked_loc.db.docked_guards and self in docked_loc.db.docked_guards:
            docked_loc.db.docked_guards.remove(self)
        self.db.docked = None

    def dismiss(self,  # type: Retainer or Agent
                dock=True):
        """
        Dismisses our guards. If they're not being dismissed permanently, then
        we dock them at the location they last occupied, saving it as an attribute.
        """
        loc = self.location
        # being dismissed permanently while gone
        if not loc:
            docked = self.db.docked
            if docked and docked.db.docked_guards and self in docked.db.docked_guards:
                docked.db.docked_guards.remove(self)
            return
        self.db.prelogout_location = loc
        if dock:
            self.db.docked = loc
            docked = loc.db.docked_guards or []
            if self not in docked:
                docked.append(self)
            loc.db.docked_guards = docked
        loc.msg_contents("%s have been dismissed." % self.name)
        self.location = None
        if self.ndb.combat_manager:
            self.ndb.combat_manager.remove_combatant(self)

    def at_init(self  # type: Retainer or Agent
                ):
        try:
            if self.location and self.db.guarding and self.db.guarding.location == self.location:
                self.follow(self.db.guarding)
        except AttributeError:
            import traceback
            traceback.print_exc()

    def get_stat_cost(self,  # type: Retainer or Agent
                      attr):
        """
        Get the cost of a stat based on our current
        rating and the type of agent we are.
        """
        atype = self.agent.type
        stats = primary_stats.get(atype, [])
        base = get_stat_cost(self, attr)
        if attr not in stats:
            base *= 2
        xpcost = base
        rescost = base
        if attr in MENTAL_STATS:
            restype = "economic"
        elif attr in SOCIAL_STATS:
            restype = "social"
        elif attr in PHYSICAL_STATS:
            restype = "military"
        else:  # special stats
            restype = "military"
        return xpcost, rescost, restype

    def get_skill_cost(self, attr):
        """
        Get the cost of a skill based on our current rating and the
        type of agent that we are.
        """
        restype = "military"
        atype = self.agent.type
        primary_skills = get_npc_skills(atype)
        base = get_skill_cost(self, attr, unmodified=True)
        if attr not in primary_skills:
            base *= 2
        xpcost = base
        rescost = base
        if attr in spy_skills:
            restype = "social"
        elif attr in assistant_skills:
            restype = "economic"
        return xpcost, rescost, restype

    def get_stat_maximum(self, attr):
        """
        Get the current max for a stat based on the type
        of agent we are. If it's primary stats, == to our
        quality level. Otherwise, quality - 1.
        """
        atype = self.agent.type
        pstats = primary_stats.get(atype, [])
        if attr in pstats:
            cap = self.agent.quality
        else:
            cap = self.agent.quality - 1
        typecap = get_npc_stat_cap(atype, attr)
        if cap > typecap:
            cap = typecap
        return cap

    def get_skill_maximum(self, attr):
        """
        Get the current max for a skill based on the type
        of agent we are
        """
        atype = self.agent.type
        primary_skills = get_npc_skills(atype)
        if attr in primary_skills:
            return self.agent.quality
        return self.agent.quality - 1

    @property
    def agent(self  # type: Retainer or Agent
              ):
        """
        Returns the agent type that this object belongs to.
        """
        return self.agentob.agent_class

    def train_agent(self, trainer, conditioning):
        trainer.msg("This type of agent cannot be trained.")
        return False

    @property
    def training_skill(self):
        if "animal" in self.agent.type_str:
            return "animal ken"
        return "teaching"

    @property
    def species(self  # type: Retainer or Agent
                ):
        if "animal" in self.agent.type_str:
            default = "animal"
        else:
            default = "human"
        return self.db.species or default

    @property
    def owner(self):
        return self.agent.owner

    def inform_owner(self, text):
        """Passes along an inform to our owner."""
        self.owner.inform_owner(text, category="Agents")

    @property
    def weaponized(self  # type: Retainer or Agent
                   ):
        if self.npc_type in COMBAT_TYPES:
            return True
        if self.weapons_hidden:
            return False
        try:
            if self.weapondata.get('weapon_damage', 1) > 2:
                return True
        except (AttributeError, KeyError):
            return False

    @property
    def xp(self):
        return self.agent.xp

    @xp.setter
    def xp(self, value):
        self.agent.xp = value
        self.agent.save()

    def adjust_xp(self, value):
        self.xp += value

    @property
    def uses_training_cap(self):
        return self.npc_type not in (ANIMAL, SMALL_ANIMAL)

    @property
    def xp_training_cap(self):
        return self.db.xp_training_cap or 0

    @xp_training_cap.setter
    def xp_training_cap(self, value):
        self.db.xp_training_cap = value

    @property
    def xp_transfer_cap(self  # type: Retainer or Agent
                        ):
        return self.db.xp_transfer_cap or 0

    @xp_transfer_cap.setter
    def xp_transfer_cap(self,  # type: Retainer or Agent
                        value):
        self.db.xp_transfer_cap = value

    @property
    def conditioning(self  # type: Retainer or Agent
                     ):
        return self.db.conditioning_for_training or 0

    @conditioning.setter
    def conditioning(self,  # type: Retainer or Agent
                     value):
        self.db.conditioning_for_training = value


class Retainer(AgentMixin, Npc):
    ATK_MOD = 0
    DEF_MOD = 0

    # noinspection PyUnusedLocal
    def setup_npc(self, ntype=0, threat=0, num=1, sing_name=None, plural_name=None, desc=None, keepold=False):
        self.db.damage = 0
        self.db.health_status = "alive"
        self.db.sleep_status = "awake"
        self.setup_stats(ntype, threat)
        self.name = self.agentob.agent_class.name

    @property
    def buyable_abilities(self):
        """
        Returns a list of ability names that are valid to buy for this agent
        """
        abilities = ()
        innate = get_innate_abilities(self.agent.type)
        abilities += innate
        # to do - get abilities based on level and add em to the ones they get innately
        return abilities

    # noinspection PyUnusedLocal
    def get_ability_maximum(self, attr):
        """Returns max for an ability that we can buy"""
        # to do - make it different based on off-classes
        return self.agent.quality + 1

    # noinspection PyMethodMayBeStatic
    def get_ability_cost(self, attr):
        cost, res_type = ABILITY_COSTS.get(attr)
        return cost, cost, res_type

    def can_be_trained_by(self, trainer):
        skill = trainer.db.skills.get(self.training_skill, 0)
        if not skill:
            trainer.msg("You must have %s skill to train them." % self.training_skill)
            return False
        if self.uses_training_cap and self.xp_training_cap <= 0:
            trainer.msg("They need more xp transferred to them before they can benefit from training.")
            return False
        return super(Retainer, self).can_be_trained_by(trainer)

    def post_training(self, trainer, trainer_msg="", targ_msg="", ap_spent=0, **kwargs):
        # if post_training works, then we proceed with training the agent
        if super(Retainer, self).post_training(trainer, trainer_msg=trainer_msg, targ_msg=targ_msg):
            currently_training = trainer.db.currently_training or []
            if self not in currently_training:
                # this should not be possible. Nonetheless, it has happened.
                from server.utils.arx_utils import trainer_diagnostics
                raise RuntimeError("Error: Training list not properly updated: %s" % trainer_diagnostics(trainer))
            self.train_agent(trainer, ap_spent)
        else:
            raise RuntimeError("Somehow, post_training was not called or did not return a value.")

    @property
    def training_difficulty(self):
        difficulty_multiplier = 0.75 if self.training_skill == "animal ken" else 1
        unspent_xp_penalty = self.agent.xp/2 - (self.agent.quality * 15)
        if unspent_xp_penalty < 0:
            unspent_xp_penalty = 0
        agent_level_penalty = self.agent.quality * 5
        difficulty = unspent_xp_penalty + agent_level_penalty
        difficulty = int(difficulty * difficulty_multiplier) - self.conditioning
        if difficulty < -10:
            return -10
        return difficulty

    def train_agent(self, trainer, conditioning):
        """
        Gives xp to this agent if they haven't been trained yet this week.
        The skill used to train them is based on our type - animal ken for
        animals, teaching for non-animals.
        """
        # use real name if we're not present. If we're here, use masked name
        use_real_name = self.location != trainer.location
        name = trainer.key if use_real_name else str(trainer)
        self.conditioning += conditioning
        roll = do_dice_check(trainer, stat="command", skill=self.training_skill, difficulty=self.training_difficulty,
                             quiet=False, use_real_name=use_real_name)
        if roll < 0:
            trainer.msg("You have failed to teach them anything.")
            msg = "%s has attempted to train %s, but utterly failed to teach them anything." % (name, self)
        else:
            if self.uses_training_cap:
                if roll > self.xp_training_cap:
                    roll = self.xp_training_cap
                    trainer.msg("You were limited by %s's training cap, and could only give them %s xp." % (self, roll))
                self.xp_training_cap -= roll
            self.agent.xp += roll
            self.agent.save()
            trainer.msg("You have trained %s, giving them %s xp." % (self, roll))
            msg = "%s has trained %s, giving them %s xp." % (name, self, roll)
            self.conditioning = 0
        self.inform_owner(msg)
        print("Training log: %s" % msg)

    def view_stats(self, viewer, combat=False):
        super(Retainer, self).view_stats(viewer, combat)
        msg = "\n{wCurrent Training Difficulty:{n %s" % self.training_difficulty
        if self.uses_training_cap:
            msg += "\n{wCurrent XP Training Cap:{n %s" % self.xp_training_cap
        viewer.msg(msg)


# noinspection PyAttributeOutsideInit
class Agent(AgentMixin, MultiNpc):
    # -----------------------------------------------
    # AgentHandler Admin client methods
    # -----------------------------------------------

    def setup_name(self):
        a_type = self.agentob.agent_class.type
        noun = self.agentob.agent_class.name
        if not noun:
            if self.db.num_living == 1:
                noun = get_npc_singular_name(a_type)
            else:
                noun = get_npc_plural_name(a_type)
        if self.db.num_living:
            self.key = "%s %s" % (self.db.num_living, noun)
        else:
            self.key = noun
        self.save()

    @property
    def name(self):
        return self.key

    @name.setter
    def name(self, val):
        self.key = val

    def lose_agents(self, num, death=False):
        """
        Called whenever we lose one of our agents, due to them being recalled
        or dying.
        """
        if num < 0:
            raise ValueError("Must pass a positive integer to lose_agents.")
        if num > self.db.num_living:
            num = self.db.num_living
        self.multideath(num, death)
        self.agentob.lose_agents(num)
        self.setup_name()
        if self.db.num_living <= 0:
            self.unassign()
        return num

    def gain_agents(self, num):
        self.db.num_living += num
        self.setup_name()

    def death_process(self, *args, **kwargs):
        """
        This object dying. Set its state to dead, send out
        death message to location.
        """
        num = 1
        if self.ae_dmg >= self.max_hp:
            num = self.quantity
            message = "{r%s have all died.{n" % get_npc_plural_name(self._get_npc_type())
        else:
            message = "{r%s has died.{n" % get_npc_singular_name(self._get_npc_type())
        if self.location:
            self.location.msg_contents(message)
        if kwargs.get('affect_real_dmg', False):
            self.lose_agents(num=num, death=True)
            self.real_dmg = self.ae_dmg
        else:
            self.temp_losses += num
            self.temp_dmg = self.ae_dmg
