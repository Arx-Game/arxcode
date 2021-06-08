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

from world.stats_and_skills import (
    do_dice_check,
    get_stat_cost,
    get_skill_cost,
)
from django.core.exceptions import ObjectDoesNotExist


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
        self.db.automate_combat = True
        self.at_init()

    def sensing_check(self, difficulty=15, invis=False, allow_wake=False):
        """
        See if the character detects something that is hiding or invisible.
        The difficulty is supplied by the calling function.
        Target can be included for additional situational
        """
        roll = do_dice_check(
            self, stat="perception", stat_keep=True, difficulty=difficulty
        )
        return roll

    def get_fakeweapon(self, force_update=False):
        from .npc_types import get_npc_weapon

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
        from .npc_types import (
            get_npc_weapon,
            get_npc_stats,
            get_npc_skills,
            get_armor_bonus,
            get_hp_bonus,
        )

        self.db.npc_quality = threat
        for stat, value in get_npc_stats(ntype).items():
            self.traits.set_stat_value(stat, value)
        skills = get_npc_skills(ntype)
        for skill in skills:
            skills[skill] += threat
        self.traits.skills = skills
        self.db.fakeweapon = get_npc_weapon(ntype, threat)
        self.traits.set_other_value(
            "armor_class", get_armor_bonus(self._get_npc_type(), self._get_quality())
        )
        self.traits.set_other_value(
            "bonus_max_hp", get_hp_bonus(self._get_npc_type(), self._get_quality())
        )

    @property
    def num_armed_guards(self):
        if self.weaponized:
            return self.quantity
        return 0

    def setup_npc(
        self,
        ntype=0,
        threat=0,
        num=1,
        sing_name=None,
        plural_name=None,
        desc=None,
        keepold=False,
    ):
        self.health_status.full_restore()

        from commands.cmdsets import death, sleep

        self.cmdset.delete(sleep.SleepCmdSet)
        self.cmdset.delete(death.DeathCmdSet)

        # if we don't
        if not keepold:
            self.db.npc_type = ntype
            self.set_npc_new_name(sing_name, plural_name)
            self.set_npc_new_desc(desc)
        self.setup_stats(ntype, threat)

    def set_npc_new_name(self, sing_name=None, plural_name=None):
        self.name = sing_name or plural_name or "#%s" % self.id

    @property
    def default_desc(self):
        from .npc_types import get_npc_desc

        return get_npc_desc(self.db.npc_type or 0)

    def set_npc_new_desc(self, desc=None):
        if desc:
            self.desc = desc


class MultiNpc(Npc):
    def multideath(self, num, death=False):
        living = self.item_data.quantity or 0
        if num > living:
            num = living
        self.item_data.quantity = living - num
        if death:
            dead = self.db.num_dead or 0
            self.db.num_dead = dead + num
        else:
            incap = self.db.num_incap or 0
            self.db.num_incap = incap + num

    def get_singular_name(self):
        from .npc_types import get_npc_singular_name

        return self.db.singular_name or get_npc_singular_name(self._get_npc_type())

    def get_plural_name(self):
        from .npc_types import get_npc_plural_name

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
        from .npc_types import get_npc_plural_name, get_npc_singular_name

        num = 1
        if self.ae_dmg >= self.max_hp:
            num = self.quantity
            message = "{r%s have all died.{n" % get_npc_plural_name(
                self._get_npc_type()
            )
        else:
            message = "{r%s has died.{n" % get_npc_singular_name(self._get_npc_type())
        if self.location:
            self.location.msg_contents(message)
        if kwargs.get("affect_real_dmg", True):
            self.multideath(num=num, death=True)
            self.real_dmg = self.ae_dmg
        else:
            self.temp_losses += num
            self.temp_dmg = self.ae_dmg
        self.post_death()
        return True

    def post_death(self):
        if self.quantity <= 0:
            if self.combat.combat:
                self.combat.combat.remove_combatant(self)

    def fall_asleep(self, uncon=False, quiet=False, verb=None, **kwargs):
        """
        Falls asleep. Uncon flag determines if this is regular sleep,
        or unconsciousness.
        """
        from .npc_types import get_npc_singular_name

        reason = " is %s and " % verb if verb else ""
        if self.location:
            self.location.msg_contents(
                "{w%s%s falls %s.{n"
                % (
                    get_npc_singular_name(self._get_npc_type()),
                    reason,
                    "unconscious" if uncon else "asleep",
                )
            )
        if kwargs.get("affect_real_dmg", True):
            self.multideath(num=1, death=False)
        else:
            self.temp_losses += 1
        # don't reset damage here since it's used for death check. Reset in combat process
        self.post_death()

    # noinspection PyAttributeOutsideInit
    def setup_name(self):
        from .npc_types import get_npc_singular_name, get_npc_plural_name

        npc_type = self.db.npc_type
        if self.item_data.quantity == 1 and not self.db.num_dead:
            self.key = self.db.singular_name or get_npc_singular_name(npc_type)
        else:
            if self.item_data.quantity == 1:
                noun = self.db.singular_name or get_npc_singular_name(npc_type)
            else:
                noun = self.db.plural_name or get_npc_plural_name(npc_type)
            if not self.item_data.quantity and self.db.num_dead:
                noun = "dead %s" % noun
                self.key = "%s %s" % (self.db.num_dead, noun)
            else:
                self.key = "%s %s" % (self.item_data.quantity, noun)
        self.save()

    def setup_npc(
        self,
        ntype=0,
        threat=0,
        num=1,
        sing_name=None,
        plural_name=None,
        desc=None,
        keepold=False,
    ):
        self.item_data.quantity = num
        self.db.num_dead = 0
        self.db.num_incap = 0
        self.health_status.full_restore()
        # if we don't
        if not keepold:
            self.db.npc_type = ntype
            self.db.singular_name = sing_name
            self.db.plural_name = plural_name
            self.set_npc_new_desc(desc)
        self.setup_stats(ntype, threat)
        self.setup_name()

    # noinspection PyAttributeOutsideInit
    def dismiss(self):
        self.location = None
        self.save()

    @property
    def quantity(self):
        num = self.item_data.quantity or 0
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
    def default_colored_name(self):
        try:
            return self.agent.colored_name
        except ObjectDoesNotExist:
            return None

    @property
    def desc(self):
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
            msg += " {wLocation:{n %s" % (
                self.location or self.item_data.pre_offgrid_location or "Home Barracks"
            )
        return msg

    def setup_agent(
        self,  # type: Retainer or Agent
    ):
        """
        We'll set up our stats based on the type given by our agent class.
        """
        from .npc_types import check_passive_guard

        agent = self.agentob
        agent_class = agent.agent_class
        quality = agent_class.quality or 0
        # set up our stats based on our type
        desc = agent_class.desc
        atype = agent_class.type
        self.setup_npc(ntype=atype, threat=quality, num=agent.quantity, desc=desc)
        self.db.passive_guard = check_passive_guard(atype)

    def setup_locks(
        self,  # type: Retainer or Agent
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

    def assign(
        self,  # type: Retainer or Agent
        targ,
    ):
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
    def guarding(
        self,  # type: Retainer or Agent
    ):
        return self.db.guarding

    @guarding.setter
    def guarding(
        self,  # type: Retainer or Agent
        val,
    ):
        if not val:
            self.attributes.remove("guarding")
            return
        self.db.guarding = val

    def start_guarding(self, val):
        self.guarding = val

    def stop_guarding(
        self,  # type: Retainer or Agent
    ):
        targ = self.guarding
        if targ:
            targ.remove_guard(self)
        self.stop_follow()
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

    def unassign(
        self,  # type: Retainer or Agent
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

    def stop_follow(
        self,  # type: Retainer or Agent
        dismiss=True,
    ):
        super(AgentMixin, self).stop_follow()
        # if we're not being unassigned, we dock them. otherwise, they're gone
        if dismiss:
            self.dismiss()

    def summon(
        self,  # type: Retainer or Agent
    ):
        """
        Have these guards appear to defend the character. This should generally only be
        called in a location that permits it, such as their house barracks, or in a
        square close to where the guards were docked.
        """
        if not self.guarding:
            return
        loc = self.guarding.location
        if loc:
            mapping = {"secret": True}
            self.move_to(loc, mapping=mapping)
            self.follow(self.guarding)
            self.item_data.pre_offgrid_location = None

    def dismiss(
        self,  # type: Retainer or Agent
    ):
        """
        Dismisses our guards. If they're not being dismissed permanently, then
        we dock them at the location they last occupied, saving it as an attribute.
        """
        prior_location = self.location
        self.leave_grid()
        if prior_location:
            prior_location.msg_contents("%s have been dismissed." % self.name)
        if self.ndb.combat_manager:
            self.ndb.combat_manager.remove_combatant(self)

    def at_init(
        self,  # type: Retainer or Agent
    ):
        try:
            if (
                self.location
                and self.db.guarding
                and self.db.guarding.location == self.location
            ):
                self.follow(self.db.guarding)
        except AttributeError:
            import traceback

            traceback.print_exc()

    def get_stat_cost(
        self,  # type: Retainer or Agent
        attr,
    ):
        """
        Get the cost of a stat based on our current
        rating and the type of agent we are.
        """
        from .npc_types import primary_stats
        from world.traits.models import Trait

        atype = self.agent.type
        stats = primary_stats.get(atype, [])
        base = get_stat_cost(self, attr)
        if attr not in stats:
            base *= 2
        xpcost = base
        rescost = base
        if attr in Trait.get_valid_stat_names(Trait.MENTAL):
            restype = "economic"
        elif attr in Trait.get_valid_stat_names(Trait.SOCIAL):
            restype = "social"
        elif attr in Trait.get_valid_stat_names(Trait.PHYSICAL):
            restype = "military"
        else:  # special stats
            restype = "military"
        return xpcost, rescost, restype

    def get_skill_cost(self, attr):
        """
        Get the cost of a skill based on our current rating and the
        type of agent that we are.
        """
        from .npc_types import get_npc_skills, spy_skills, assistant_skills

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
        from .npc_types import primary_stats, get_npc_stat_cap

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
        from .npc_types import get_npc_skills

        atype = self.agent.type
        primary_skills = get_npc_skills(atype)
        if attr in primary_skills:
            return self.agent.quality
        return self.agent.quality - 1

    @property
    def agent(
        self,  # type: Retainer or Agent
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
    def species(
        self,  # type: Retainer or Agent
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
    def weaponized(
        self,  # type: Retainer or Agent
    ):
        from .npc_types import COMBAT_TYPES

        if self.npc_type in COMBAT_TYPES:
            return True
        if self.weapons_hidden:
            return False
        try:
            if self.weapondata.get("weapon_damage", 1) > 2:
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
        from typeclasses.npcs.constants import SMALL_ANIMAL
        from typeclasses.npcs.constants import ANIMAL

        return self.npc_type not in (ANIMAL, SMALL_ANIMAL)

    @property
    def xp_training_cap(self):
        return self.db.xp_training_cap or 0

    @xp_training_cap.setter
    def xp_training_cap(self, value):
        self.db.xp_training_cap = value

    @property
    def xp_transfer_cap(
        self,  # type: Retainer or Agent
    ):
        return self.db.xp_transfer_cap or 0

    @xp_transfer_cap.setter
    def xp_transfer_cap(
        self,  # type: Retainer or Agent
        value,
    ):
        self.db.xp_transfer_cap = value

    @property
    def conditioning(
        self,  # type: Retainer or Agent
    ):
        return self.db.conditioning_for_training or 0

    @conditioning.setter
    def conditioning(
        self,  # type: Retainer or Agent
        value,
    ):
        self.db.conditioning_for_training = value


class Retainer(AgentMixin, Npc):
    ATK_MOD = 0
    DEF_MOD = 0

    # noinspection PyUnusedLocal
    def setup_npc(
        self,
        ntype=0,
        threat=0,
        num=1,
        sing_name=None,
        plural_name=None,
        desc=None,
        keepold=False,
    ):
        super().setup_npc(
            ntype=ntype,
            threat=threat,
            num=num,
            sing_name=sing_name,
            plural_name=plural_name,
            desc=desc,
            keepold=True,
        )
        self.name = self.agentob.agent_class.name

    @property
    def buyable_abilities(self):
        """
        Returns a list of ability names that are valid to buy for this agent
        """
        from .npc_types import get_innate_abilities

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
        from .npc_types import ABILITY_COSTS

        cost, res_type = ABILITY_COSTS.get(attr)
        return cost, cost, res_type

    def can_be_trained_by(self, trainer):
        skill = trainer.traits.get_skill_value(self.training_skill)
        if not skill:
            trainer.msg("You must have %s skill to train them." % self.training_skill)
            return False
        if self.uses_training_cap and self.xp_training_cap <= 0:
            trainer.msg(
                "They need more xp transferred to them before they can benefit from training."
            )
            return False
        return super(Retainer, self).can_be_trained_by(trainer)

    def post_training(self, trainer, trainer_msg="", targ_msg="", ap_spent=0, **kwargs):
        # if post_training works, then we proceed with training the agent
        if super(Retainer, self).post_training(
            trainer, trainer_msg=trainer_msg, targ_msg=targ_msg
        ):
            currently_training = trainer.db.currently_training or []
            if self not in currently_training:
                # this should not be possible. Nonetheless, it has happened.
                from server.utils.arx_utils import trainer_diagnostics

                raise RuntimeError(
                    "Error: Training list not properly updated: %s"
                    % trainer_diagnostics(trainer)
                )
            self.train_agent(trainer, ap_spent)
        else:
            raise RuntimeError(
                "Somehow, post_training was not called or did not return a value."
            )

    @property
    def training_difficulty(self):
        difficulty_multiplier = 0.75 if self.training_skill == "animal ken" else 1
        unspent_xp_penalty = self.agent.xp / 2 - (self.agent.quality * 15)
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
        roll = do_dice_check(
            trainer,
            stat="command",
            skill=self.training_skill,
            difficulty=self.training_difficulty,
            quiet=False,
            use_real_name=use_real_name,
        )
        if roll < 0:
            trainer.msg("You have failed to teach them anything.")
            msg = (
                "%s has attempted to train %s, but utterly failed to teach them anything."
                % (name, self)
            )
        else:
            if self.uses_training_cap:
                if roll > self.xp_training_cap:
                    roll = self.xp_training_cap
                    trainer.msg(
                        "You were limited by %s's training cap, and could only give them %s xp."
                        % (self, roll)
                    )
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
        from .npc_types import get_npc_singular_name, get_npc_plural_name

        a_type = self.agentob.agent_class.type
        noun = self.agentob.agent_class.name
        if not noun:
            if self.item_data.quantity == 1:
                noun = get_npc_singular_name(a_type)
            else:
                noun = get_npc_plural_name(a_type)
        if self.item_data.quantity:
            self.key = "%s %s" % (self.item_data.quantity, noun)
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
        if num > self.item_data.quantity:
            num = self.item_data.quantity
        self.multideath(num, death)
        self.agentob.lose_agents(num)
        self.setup_name()
        if self.item_data.quantity <= 0:
            self.unassign()
        return num

    def gain_agents(self, num):
        self.item_data.quantity += num
        self.setup_name()

    def death_process(self, *args, **kwargs):
        """
        This object dying. Set its state to dead, send out
        death message to location.
        """
        from .npc_types import get_npc_singular_name, get_npc_plural_name

        num = 1
        if self.ae_dmg >= self.max_hp:
            num = self.quantity
            message = "{r%s have all died.{n" % get_npc_plural_name(
                self._get_npc_type()
            )
        else:
            message = "{r%s has died.{n" % get_npc_singular_name(self._get_npc_type())
        if self.location:
            self.location.msg_contents(message)
        if kwargs.get("affect_real_dmg", False):
            self.lose_agents(num=num, death=True)
            self.real_dmg = self.ae_dmg
        else:
            self.temp_losses += num
            self.temp_dmg = self.ae_dmg
