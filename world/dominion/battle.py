"""
Battle system for dominion

So, what happens when two units fight? That's what this file is trying
to solve. We'll try for a more realistic approach in that units will
rarely fight until one side is completely annihilated - in general, units
will fight until they rout, and will often lose quite a few troops who
desert during the retreat, while others are killed in retreating.
"""
from django.conf import settings
from world.dominion.combat_grid import CombatGrid
from world.dominion.reports import BattleReport
import operator
import traceback
from server.utils.arx_utils import setup_log


XP_PER_BATTLE = 5
ATTACKER_FRONT = (0, 1, 0)
ATTACKER_BACK = (0, 0, 0)
DEFENDER_FRONT = (0, 5, 0)
DEFENDER_BACK = (0, 6, 0)


def get_combat(unit_obj, grid):
    unit = unit_obj.stats
    unit.grid = grid
    return unit


class Formation(object):
    # noinspection PyUnusedLocal
    def __init__(self, units, battle, front=None, back=None):
        # units in front/back rank in formation
        self.name = ""
        self.front_rank = []
        self.back_rank = []
        self.lost_units = []
        self.routed_units = []
        self.front_pos = front or (0, 0, 0)
        self.back_pos = back or (0, 0, 0)
        self.grid = battle.grid
        self.battle = battle

    def __str__(self):
        return self.name

    def __iter__(self):
        active_units = self.front_rank + self.back_rank
        for unit in active_units:
            yield unit

    def __contains__(self, unit):
        return unit in self.front_rank or unit in self.back_rank

    def __len__(self):
        return len(self.front_rank) + len(self.back_rank)

    def _get_all_units(self):
        return self.front_rank + self.back_rank + self.lost_units + self.routed_units

    all_units = property(_get_all_units)


class UnitFormation(Formation):
    """
    A formation is how we track the sides inside the battle. Each side is a
    formation, and a formation object is iterable with the currently active
    units returned. Similarly, the len() of a Formation object is its active
    units, and 'in' tests only against active units. It also stores lost units,
    and units which are currently in rout. Units which rout for more than one
    turn are then lost.
    """

    def __init__(self, units, battle, front=None, back=None):
        # setup standard formation stuff
        Formation.__init__(self, units, battle, front, back)
        # units that are no longer in formation
        self.lost_units = []
        # units that are routed
        self.routed_units = []
        # units storming enemy castle
        self.storming_units = []
        self.log = battle.log
        self.add_units(units)
        self._castle = None
        self.castle_pos = DEFENDER_BACK

    def _get_castle(self):
        return self._castle

    def _set_castle(self, castle):
        self._castle = castle
        for unit in self:
            self.recall_unit_to_castle(unit)

    castle = property(_get_castle, _set_castle)

    def add_units(self, unit_list):
        for unit in unit_list:
            self.add_unit(unit)
        self.sort_ranks(self.front_rank)
        self.sort_ranks(self.back_rank)

    def add_unit(self, unit):
        unit.formation = self
        unit.log = self.log
        if unit.ranged:
            self.back_rank.append(unit)
            self.grid.add_actor(unit, self.back_pos)
        else:
            self.front_rank.append(unit)
            self.grid.add_actor(unit, self.front_pos)

    def get_targs_for_units(self, enemy_formation):
        for unit in self:
            unit.acquire_target(enemy_formation)

    def get_target_from_formation_for_attacker(self, attacker):
        """
        We acquire a target if one exists. If the attacker is ranged,
        they choose the highest value target from either front or back
        ranks. If we're melee, we choose the highest value target in
        the front rank if the front rank exists, otherwise we choose
        the highest value target in the back rank.

        If we have a castle, we can only have ranged units exchange fire
        unless the enemy is storming us. If the attacker is not ranged
        and we have no enemies storming us, they cannot acquire a target.
        When no target is acquired, they will advance toward our castle
        during their movement phase, and will be added to storming list
        whenever they reach our position.
        """
        if len(self) == 0:
            return
        if self.castle:
            # add to storming units if they're in position and not already storming
            if (
                attacker.position == self.castle_pos
                and attacker not in self.storming_units
            ):
                self.storming_units.append(attacker)
                attacker.storming = True
            if not self.storming_units:
                # we let ranged units hit our own backline inside castle
                if self.back_rank and attacker.range:
                    return self.back_rank[0]
                # give them the pseudo-target of our castle's position
                attacker.storm_targ_pos = self.castle_pos
                return
        # to do - add this back in once we implement 'trampling through' targets
        # first we check if there's any units in melee with them.
        # units_at_pos = [unit for unit in attacker.grid.get_actors(attacker.position) if unit not in self]
        # if units_at_pos:
        #    units_at_pos.sort(key=operator.attrgetter('value'))
        #    units_at_pos[0]
        if attacker.range:
            all_units = self.sort_ranks(self.front_rank + self.back_rank)
            return all_units[0]
        if self.front_rank:
            return self.front_rank[0]
        if self.back_rank:
            return self.back_rank[0]

    @staticmethod
    def sort_ranks(rank_list):
        rank_list.sort(key=operator.attrgetter("value"))
        return rank_list

    def ranged_attacks(self):
        for unit in self:
            unit.ranged_attack()

    def movement(self):
        for unit in self:
            stay_put = False
            if self.castle:
                # we might have something for sorties later. for now, all units in castle stay
                stay_put = True
                # If we're outside the castle, go back
                if unit.position != self.castle_pos:
                    self.recall_unit_to_castle(unit)
            if not stay_put:
                unit.advance()

    def recall_unit_to_castle(self, unit):
        try:
            x, y, z = self.castle_pos
        except (TypeError, ValueError):
            print("ERROR: Invalid tuple in self.castle_pos: %s" % str(self.castle_pos))
            x, y, z = DEFENDER_BACK
        unit.castle = self.castle
        unit.move(x, y, z)

    def melee_attacks(self):
        for unit in self:
            unit.melee_attack()

    def check_rally(self):
        """
        Check if our units that are currently routed can be made to rally.
        If they fail, they will be lost.
        """
        for unit in self.routed_units:
            unit.rally_check()
        rallied = [unit for unit in self.routed_units if not unit.routed]
        for unit in rallied:
            self.routed_units.remove(rallied)
            self.add_unit(unit)

    def cleanup(self):
        """
        In the cleanup phase, units that were previously marked as routed
        are assumed to have failed all their rally checks and are now lost.
        Units that have been destroyed in battle are also marked lost.
        Any units that were marked as starting to rout are moved to the
        routed list, and will be lost next cleanup unless they rally.
        """
        self.lost_units = list(set(self.lost_units + self.routed_units))
        self.routed_units = []
        destroyed = []
        routed = []
        # important - we have to save them to temporary lists. If we removed
        # them from self while iterating, we'd get errors.
        for unit in self:
            # determine if the unit is destroyed or routed
            unit.cleanup()
            if unit.destroyed:
                destroyed.append(unit)
            elif unit.routed:
                routed.append(unit)
        # unpack destroyed as arguments for mark_lost, * is important
        self.mark_lost_or_routed(*destroyed)
        # for routed units, use routed=True
        self.mark_lost_or_routed(*routed, routed=True)

    def mark_lost_or_routed(self, *units, **kwargs):
        """
        usage:  formation.mark_lost_or_routed(*destroyed_list)
                formation.mark_lost_or_routed(unit1, unit2, unit3, ...)
                formation.mark_lost_or_routed(*routed, routed=True)

        Given an iterable argument, 'units', we will mark all the units
        as lost, checking what rank they are in to remove them from the
        lists of active units. If the keyword argument of 'routed' is
        set to True, then the units are marked as routed. Otherwise they
        are lost.
        """
        for unit in units:
            if unit in self.front_rank:
                self.front_rank.remove(unit)
            if unit in self.back_rank:
                self.back_rank.remove(unit)
            if kwargs.get("routed", False):
                self.routed_units.append(unit)
            else:
                self.lost_units.append(unit)

    # noinspection PyBroadException
    def save_models(self):
        """
        We iterate through all units that we have, retrieve their
        corresponding database model, and make appropriate adjustments
        to it based on the battle. Units that are lost have their model
        deleted from the database, others gain xp and suffer losses.
        """
        for unit in self.all_units:
            dbobj = unit.dbobj
            if unit.destroyed:
                dbobj.delete()
            else:
                if unit.routed:
                    dbobj.decimate()
                try:
                    dbobj.train(XP_PER_BATTLE)
                    dbobj.do_losses(unit.losses)
                    dbobj.save()
                except Exception:
                    print("ERROR in saving unit.")
                    traceback.print_exc()

    def _all_units(self):
        return set(
            self.front_rank + self.back_rank + self.lost_units + self.routed_units
        )

    all_units = property(_all_units)


class Battle(object):
    ATK_WIN = 0
    DEF_WIN = 1

    def __init__(
        self,
        armies_atk,
        armies_def,
        week,
        pc_atk=None,
        pc_def=None,
        atk_domain=None,
        def_domain=None,
    ):
        self.log = setup_log(settings.BATTLE_LOG)
        self.week = week
        self.armies_atk = []
        self.armies_def = []
        self.rounds = 0
        self.victor = None
        self.result = None
        self.attacker_pc = pc_atk
        self.defender_pc = pc_def
        self.ending = False
        self.formation_atk = None
        self.formation_def = None
        self.domain_atk = atk_domain
        self.domain_def = def_domain
        self.log.info("Attacker: %s\tDefender: %s" % (self.domain_atk, self.domain_def))
        for army in armies_atk:
            self.add_army(attacker=army)
        for army in armies_def:
            self.add_army(defender=army)
        self.grid = CombatGrid()
        self.castle = None

    def get_name(self, attacker=True):
        armyname = None
        if attacker:
            pc = self.attacker_pc
            if self.armies_atk:
                armyname = self.armies_atk[0].name
            domain = self.domain_atk or armyname or "Unknown"
        else:
            pc = self.defender_pc
            if self.armies_def:
                armyname = self.armies_def[0].name
            domain = self.domain_def or armyname or "Unknown"
        if pc:
            return "%s (%s)" % (str(domain), pc)
        return str(domain)

    def get_atk_name(self):
        return self.get_name()

    atk_name = property(get_atk_name)

    def get_def_name(self):
        return self.get_name(attacker=False)

    def_name = property(get_def_name)

    def get_atk_units(self):
        return self.formation_atk.all_units

    atk_units = property(get_atk_units)

    def get_def_units(self):
        return self.formation_def.all_units

    def_units = property(get_def_units)

    def add_army(self, attacker=None, defender=None):
        """
        Adds armies to either side and then either creates
        formations for them if they don't exist, or adds the armies
        to those formations.
        """
        if attacker:
            self.armies_atk.append(attacker)
            units = [get_combat(unit, self.grid) for unit in attacker.units.all()]
            if not self.formation_atk:
                self.formation_atk = UnitFormation(
                    units, self, ATTACKER_FRONT, ATTACKER_BACK
                )
                self.formation_atk.name = "Attacker"
                self.log.info(
                    "Attacker created with %s units." % str(len(self.formation_atk))
                )
            else:
                self.formation_atk.add_units(units)
        if defender:
            self.armies_def.append(defender)
            # if the defender Army model has a castle, we add it to the Battle
            if not self.castle and defender.castle:
                self.castle = defender.castle
            units = [get_combat(unit, self.grid) for unit in defender.units.all()]
            if not self.formation_def:
                self.formation_def = UnitFormation(
                    units, self, DEFENDER_FRONT, DEFENDER_BACK
                )
                self.formation_def.name = "Defender"
                self.log.info(
                    "Defender created with %s units." % str(len(self.formation_def))
                )
            else:
                self.formation_def.add_units(units)
            # if we got a castle earlier from defender, add it to the formation
            if self.castle and not self.formation_def.castle:
                self.formation_def.castle = self.castle
                self.log.info("Castle added: %s" % str(self.castle))

    def begin_combat(self):
        self.pre_round()
        return self.result

    def pre_round(self):
        """
        Called at the start of every combat round for battles. If we've gone
        over the round limit, we end combat. We also check if either side has
        achieved a victory condition, and if so, we end combat. Otherwise, we
        have the formations acquire their targets for their units and proceed
        with the combat round.
        """
        self.rounds += 1
        self.log.info("Round %s" % self.rounds)
        if self.rounds > 30:
            self.end_combat()
            return
        if self.check_victory():
            self.end_combat()
            return
        # for attackers: try to rally units who are routing then get targs
        self.formation_atk.check_rally()
        self.formation_atk.get_targs_for_units(self.formation_def)
        # for defenders: try to rally units who are routing then get targs
        self.formation_def.check_rally()
        self.formation_def.get_targs_for_units(self.formation_atk)
        self.combat_round()

    def check_victory(self):
        """
        If a formation has no active units left, we declare victory for
        one army or the other. If our domain does not have a ruler, then
        we list the victor as being the appropriate domain.
        """
        if not self.formation_atk and self.formation_def:
            self.result = Battle.DEF_WIN
            self.victor = self.def_name
            self.log.info("Victor declared: %s" % str(self.victor))
            return True
        if self.formation_atk and not self.formation_def:
            self.result = Battle.ATK_WIN
            self.victor = self.atk_name
            self.log.info("Victor declared: %s" % str(self.victor))
            return True
        if not self.formation_atk and not self.formation_def:
            self.log.info("Both formations empty. Ending combat with no victor.")
            return True

    def combat_round(self):
        # combat phases
        self.ranged_phase()
        if self.ending:
            return
        self.movement_phase()
        self.melee_phase()
        if self.ending:
            return
        self.pre_round()

    def ranged_phase(self):
        self.formation_atk.ranged_attacks()
        self.formation_def.ranged_attacks()
        self.cleanup()

    def movement_phase(self):
        self.formation_atk.movement()
        self.formation_def.movement()

    def melee_phase(self):
        self.formation_atk.melee_attacks()
        self.formation_def.melee_attacks()
        self.cleanup()

    def cleanup(self):
        """
        Process damage for each unit. Determine if a unit is routed or
        destroyed.
        """
        self.formation_atk.cleanup()
        self.formation_def.cleanup()
        if self.check_victory():
            self.end_combat()

    # noinspection PyBroadException
    def end_combat(self):
        """
        Save all changes to the models represented by the units inside
        our formations.
        """
        if not self.ending:
            self.formation_atk.save_models()
            self.formation_def.save_models()
            # to do: all the inform stuff
            self.log.info("Ending combat.")
            if self.attacker_pc:
                try:
                    BattleReport(self.attacker_pc, self)
                except Exception:
                    self.log.info(
                        "ERROR: Could not generate BattleReport for attacker."
                    )
            if self.defender_pc:
                try:
                    BattleReport(self.defender_pc, self)
                except Exception:
                    self.log.info(
                        "ERROR: Could not generate BattleReport for defender."
                    )
        self.ending = True
