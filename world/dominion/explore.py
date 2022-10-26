"""
Exploration Events

This module creates various random events that will occur for players when
they have their armies scout out unexplored territory in order to expand
their borders. They can encounter hostiles such as bandits, small clans
of Abandoned, fell sorcery, or horrible monsters. They can also have positive
events, such as discovering riches, natural resources, ancient artifacts/
magical items, and so on.
"""
import random
from world.dominion.reports import ExplorationReport
from world.dominion import unit_types

NOTHING = 0
# types of events
SERFS = 1
LOOT = 2
BUILDING = 3
BANDITS = 4
ABANDONED = 5

# types of discovered buildings
HOUSE = 1
FARM = 2
MILL = 3
LUMBER = 4
MINE = 5


class Exploration(object):
    def __init__(self, army, land, domain, week):
        self.army = army
        self.land = land
        self.domain = domain
        self.type = NOTHING
        self.building_type = NOTHING
        self.victory = False
        self.num_serfs = 0
        self.cash = 0
        self.num_hostiles = 0
        self.week = week
        self.player = None

    def _get_outcome(self):
        txt = ""
        if self.type == NOTHING:
            txt = "Your army explored more territory without incident, "
            txt += "claiming more land for your domain."
        elif self.type == SERFS:
            txt = "Your army encountered a group of lordless peasants "
            txt += "farming their land, who wish to live under your rule. "
            txt += "You have added them and their farmlands to your domain."
        elif self.type == LOOT:
            txt = "Your army found discarded valuables in old ruins in "
            txt += "the area they have claimed for your domain. Your vault "
            txt += "receives %s coins." % str(self.cash)
        elif self.type == BANDITS:
            txt = self.get_combat_text(BANDITS)
        elif self.type == ABANDONED:
            txt = self.get_combat_text(ABANDONED)
        return txt

    outcome = property(_get_outcome)

    def get_combat_text(self, hostile_type):
        stype = "unknown"
        if hostile_type == BANDITS:
            stype = "bandits"
        elif hostile_type == ABANDONED:
            stype = "abandoned"
        txt = "Your army discovered a group of %s claiming the " % stype
        txt += "as their own domain, who engaged your army in battle. "
        if self.victory:
            txt += "Your army was successful and conquered the territory "
            txt += "the %s held." % stype
        else:
            txt += "Your army was defeated, and the %s still claim " % stype
            txt += "the territory as a petty kingdom."
        return txt

    # noinspection PyBroadException
    def event(self):
        """
        The exploration event. 50% of the time, nothing will happen
        and we annex the land peacefully. There is a chance, however, of
        us either having a positive or negative event - finding valuables
        or encountering hostiles. If we encounter hostiles, a fight breaks
        out and if we win, we get the land. If we lose, they're added as
        a new domain.
        """
        roll = random.randint(1, 100)
        land = self.land
        area = 1  # default value we explore
        max_area = land.free_area
        if roll <= 50:
            # nothing happened
            self.domain.area += area
            self.domain.save()
        elif roll <= 60:
            self.type = SERFS
            self.num_serfs = random.randint(1, 100)
            self.domain.active_serfs += self.num_serfs
            self.domain.area += 1
            self.domain.save()
        elif roll <= 70:
            self.type = LOOT
            domain = self.domain
            domain.area += area
            self.cash = random.randint(100, 2000)
            if domain.owner:
                domain.owner.vault += self.cash
                domain.owner.save()
            domain.save()
        elif roll <= 80:
            self.type = BUILDING
            domain = self.domain
            if domain.land == self.land:
                b_roll = random.randint(1, 5)
                self.building_type = b_roll
                if b_roll == HOUSE:
                    domain.num_housing += area
                elif b_roll == FARM:
                    domain.num_farms += area
                elif b_roll == MILL:
                    domain.num_mills += area
                elif b_roll == LUMBER:
                    domain.num_lumber_yards += area
                elif b_roll == MINE:
                    domain.num_mines += area
                domain.area += area
                domain.save()
        # fight, and if we win we get the land
        elif roll <= 90:
            area = random.randint(1, 5)
            if area > max_area:
                area = max_area
            self.type = BANDITS
            bandit_domain = self.land.domains.create(name="Bandits", area=area)
            bandit_army = bandit_domain.armies.create(
                name="Bandits", morale=80, land=self.land
            )
            bandit_army.units.create(type=unit_types.INFANTRY, quantity=100 * area)
            self.victory = self.army.do_battle(bandit_domain, self.week)
        elif roll <= 100:
            area = random.randint(1, 20)
            if area > max_area:
                area = max_area
            self.type = ABANDONED
            aban_domain = self.land.domains.create(name="Abandoned", area=area)
            aban_army = aban_domain.armies.create(
                name="Abandoned", morale=80, land=self.land
            )
            aban_army.units.create(type=unit_types.INFANTRY, quantity=100 * area)
            self.victory = self.army.do_battle(aban_domain, self.week)
        land.save()
        try:
            ExplorationReport(self.player, self)
        except Exception:
            print(
                "Could not generate exploration report for player %s."
                % str(self.player)
            )
