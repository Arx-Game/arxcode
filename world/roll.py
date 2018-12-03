"""
A Roll class is all the information about a roll that is made. Crits,
karma spent, or any number of other modifiers is saved to decide what
message will be sent, if any. While it could be a simulated roll made
by a GM, a character's roll will be stored in character.ndb.last_roll 
attribute.
"""
from random import randint


# The number of 'keep dice' all rolls have as a default. The higher
# this number is, the less significant the difference between a highly
# skilled and unskilled character is.
DEFAULT_KEEP = 2


class Roll(object):
    # This is the number that the roll needs to be >= for an extra die
    EXPLODE_VAL = 10
    
    def __init__(self, caller=None, stat=None, skill=None, difficulty=15, stat_list=None,
                 skill_list=None, skill_keep=True, stat_keep=False, quiet=True, announce_room=None,
                 keep_override=None, bonus_dice=0, divisor=1, average_lists=False, can_crit=True,
                 average_stat_list=False, average_skill_list=False, announce_values=False, flub=False,
                 use_real_name=False, bonus_keep=0, flat_modifier=0):
        self.character = caller
        self.difficulty = difficulty
        self.skill_keep = skill_keep
        self.stat_keep = stat_keep
        self.quiet = quiet
        self.announce_room = announce_room
        self.keep_override = keep_override
        self.bonus_dice = bonus_dice
        self.divisor = divisor
        self.average_lists = average_lists
        self.can_crit = can_crit
        self.average_stat_list = average_stat_list
        self.average_skill_list = average_skill_list
        self.announce_values = announce_values
        self.flub = flub
        self.stats = {}
        self.skills = {}
        self.bonus_crit_chance = 0
        self.bonus_crit_mult = 0
        self.bonus_keep = bonus_keep
        self.result = 0
        self.crit_mult = 1
        self.msg = ""
        self.character_name = ""
        self.flat_modifier = flat_modifier
        if self.character:
            caller.ndb.last_roll = self
            # None isn't iterable so make an empty set of stats
            stat_list = stat_list or []
            # add individual stat to the list
            if stat and stat not in stat_list:
                stat_list.append(stat)
            stat_list = [ob.lower() for ob in stat_list]
            # look up each stat from supplied caller, adds to stats dict
            for somestat in stat_list:
                self.stats[somestat] = self.character.attributes.get(somestat, 0)
            # None isn't iterable so make an empty set of skills
            skill_list = skill_list or []
            # add individual skill to the list
            if skill and skill not in skill_list:
                skill_list.append(skill)
            skill_list = [ob.lower() for ob in skill_list]
            # grabs the caller's skills or makes blank dict
            skills = caller.db.skills or {}
            # compares skills to dict we just made, adds to self.skills dict
            for someskill in skill_list:
                self.skills[someskill] = skills.get(someskill, 0)
            self.bonus_crit_chance = caller.db.bonus_crit_chance or 0
            self.bonus_crit_mult = caller.db.bonus_crit_mult or 0
            if use_real_name:
                self.character_name = caller.key
            else:
                self.character_name = caller.name

    def roll(self):
        """
        Do a dice check and return number of successes or botches. Positive number for
        successes, negative for botches.
        Stat and skill are strings that are assumed to already be run through get_partial_match.
        We'll try to match them against the character object to get values, and 0 if there's no
        matches for them.
        """
        announce_room = self.announce_room
        if not announce_room and self.character:
            announce_room = self.character.location
        statval = sum(self.stats.values())
        if self.average_lists or self.average_stat_list:
            statval //= len(self.stats)
        skillval = sum(self.skills.values())
        if self.average_lists or self.average_skill_list:
            skillval //= len(self.skills)
        # keep dice is either based on some combination of stats or skills, or supplied by caller
        keep_dice = DEFAULT_KEEP
        if self.stat_keep:
            keep_dice += statval
        if self.skill_keep:
            if len(self.stats) == 1 and statval:
                keep_dice = 1 + (statval // 2)
            keep_dice += skillval
        if self.keep_override:
            keep_dice = self.keep_override
        keep_dice += self.bonus_keep
        # the number of 'dice' we roll is equal to stat + skill
        num_dice = int(statval) + int(skillval) + self.bonus_dice
        rolls = [randint(1, 10) for _ in range(num_dice)]
        for x in range(len(rolls)):
            rolls[x] = self.explode_check(rolls[x])
        # Now we sort the rolls from least to highest, and keep a number of our
        # highest rolls equal to our 'keep dice'. Those are then added as our result.
        rolls.sort()
        rolls = rolls[-keep_dice:]
        result = sum(rolls)
        divisor = self.divisor or 1
        result /= divisor
        # crit chance is determined here. If we can't crit, we just set the multiplier to be 1
        crit_mult = self.check_crit_mult()
        self.crit_mult = crit_mult
        # if our difficulty is higher than 0, then crit is applied to our roll before difficulty is subtracted,
        # to give it a greater chance of success
        if self.difficulty > 0:
            result = int(result * crit_mult)
        result -= self.difficulty
        # if difficulty is less than 0, then our result is added up before crit is applied, to make the result higher
        # this is important for things like crafting, where they continue to accumulate negative difficulty, so it
        # makes those investments far more meaningful.
        if self.difficulty <= 0:
            result = int(result * crit_mult)
        # flat modifier is after crits/botches, but before a flubbed result
        result += self.flat_modifier
        if self.flub:
            rand_cap = max(1, min(len(rolls) * 5, self.difficulty))
            surrender = randint(1, rand_cap) - self.difficulty
            if result > surrender:
                result = surrender
        self.result = result
        # if quiet is not set, then we send a message to the room.
        if not self.quiet and announce_room:
            msg = self.build_msg()
            announce_room.msg_contents(msg, options={'roll': True})
        # end result is the sum of our kept dice minus the difficulty of what we were
        # attempting. Positive number is a success, negative is a failure.
        return self.result
        
    def explode_check(self, num):
        """
        Recursively call itself and return the sum for exploding rolls.
        """
        if num < self.EXPLODE_VAL:
            return num
        return num + self.explode_check(randint(1, 10))
    
    def check_crit_mult(self):
        try:
            if not self.can_crit:
                return 1
            bonus_crit_chance = self.bonus_crit_chance
            bonus_crit_mult = self.bonus_crit_mult
            roll = randint(1, 100)
            if roll > (5 + bonus_crit_chance):
                return 1
            if roll > (4 + bonus_crit_chance):
                return 1.5 + bonus_crit_mult
            if roll > (3 + bonus_crit_chance):
                return 1.75 + bonus_crit_mult
            if roll > (2 + bonus_crit_chance):
                return 2 + bonus_crit_mult
            if roll > (1 + bonus_crit_chance):
                return 2.25 + bonus_crit_mult
            return 2.5 + bonus_crit_mult
        except (TypeError, ValueError, AttributeError):
            return 1

    def build_msg(self):
        name = self.character_name
        if self.result + self.difficulty >= self.difficulty:
            resultstr = "rolling {w%s higher{n" % self.result
        else:
            resultstr = "rolling {r%s lower{n" % -self.result
        msg = ""
        if self.stats:
            stat_str = ", ".join(self.stats.keys())
            if self.announce_values:
                stat_str += "(%s)" % sum(self.stats.values())
        else:
            stat_str = ""
        if self.skills:
            skill_str = ", ".join(self.skills.keys())
            if self.announce_values:
                skill_str += "(%s)" % sum(self.skills.values())
        else:
            skill_str = ""
        if not stat_str or not skill_str:
            roll_msg = "{c%s{n checked %s at difficulty %s, %s." % (name, stat_str or skill_str, self.difficulty,
                                                                    resultstr)
        else:
            roll_msg = "{c%s{n checked %s + %s at difficulty %s, %s." % (name, stat_str, skill_str, self.difficulty,
                                                                         resultstr)
        if self.crit_mult > 1 and self.result >= 0:
            msg += "{y%s has rolled a critical success!\n{n" % name
        msg += roll_msg
        self.msg = msg
        return msg
