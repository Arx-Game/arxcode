"""
Commands for dice checks.
"""
from commands.base import ArxCommand
from world import stats_and_skills
from world.roll import Roll
from world.dominion.models import Agent

class CmdDiceString(ArxCommand):
    """
    @dicestring

    Usage:
      @dicestring <your very own dicestring here>

    Customizes a message you see whenever any character does a @check,
    in order to ensure that it is a real @check and not a pose.
    """
    key = "@dicestring"
    locks = "cmd:all()"

    def func(self):
        """ Handles the toggle """
        caller = self.caller
        args = self.args
        dicest = caller.db.dice_string
        if not dicest:
            dicest = "None."
        if not args:
            caller.msg("Your current dicestring is: {w%s" % dicest)
            caller.msg("To change your dicestring: {w@dicestring <word or phrase>")
            return
        caller.attributes.add("dice_string", args)
        caller.msg("Your dice string is now: %s" % args)
        return


class CmdDiceCheck(ArxCommand):
    """
    @check

    Usage:
      @check <stat>[+<skill>][ at <difficulty number>][=receivers]
      @check/flub <same as above>
      @check/retainer <retainer id>|<same as above>

    Performs a stat/skill check for your character, generally to
    determine success in an attempted action. For example, if you
    tell a GM you want to climb up the wall of a castle, they might
    ask you to 'check dex + athletics, difficulty 30'.
    You would then '@check dexterity+athletics at 30'. You can also
    send results to specific people only. For example, if you
    are attempting to lie to someone in a whispered conversation,
    you might '@check charm+manipulation=Bob' for lying to Bob at
    the default difficulty of 15. The flub switch allows you to
    intentionally, silently fail and uses the same arguments as a
    regular check.

    The dice roll system has a stronger emphasis on skills than
    stats. A character attempting something that they have a skill
    of 0 in may find the task very difficult while someone with a
    skill of 2 may find it relatively easy.
    """

    key = "check"
    aliases = ['+roll']
    locks = "cmd:all()"

    def func(self):
        """Run the @check command"""
        caller = self.caller
        retainer = None
        is_retainer = "retainer" in self.switches
        flub = "flub" in self.switches

        if not self.args:
            if is_retainer:
                caller.msg("Usage: @check/retainer <id>|<stat>[+<skill>][ at <difficulty number>][=receiver1,receiver2,etc]")
                return
            else:
                caller.msg("Usage: @check <stat>[+<skill>][ at <difficulty number>][=receiver1,receiver2,etc]")
                return
 
        args = self.lhs if self.rhs else self.args
        args = args.lower()
        quiet = bool(self.rhs)

        # NOTE: The order of calls here matters, due to str.split() usage.
        # Retainer ID -> Difficulty -> Stat/Skill.
        try:
            if is_retainer:
                args, retainer_id = self._extract_retainer_id(args)
                # TODO: Get this access to work in tests.
                # retainer = caller.player_ob.retainers.get(retainer_id)

            args, difficulty = self._extract_difficulty(args)
            stat, skill = self._extract_stat_skill(args)
        except ValueError as err:
            caller.msg(str(err))
            return
        except Agent.DoesNotExist:
            caller.msg("No retainer found with ID %s." % retainer_id)
            return

        stats_and_skills.do_dice_check(caller, retainer=retainer, stat=stat, skill=skill, difficulty=difficulty, quiet=quiet, flub=flub)
        
        if quiet:
            self._send_quiet_roll_msg()


    def _extract_retainer_id(self, args: str) -> (str, int):
        """
        Extracts retainer's ID number from args.

        Args must be of the form '<id>|<stat>[+<skill>][ at <difficulty number>]'
        
        Returns retainer's ID and '<stat>[+<skill>][ at <difficulty number>]'
        """
        split_str = args.split("|")
        if not split_str[0].lstrip('-').isdigit():
            raise ValueError("Usage: @check/retainer <id>|<stat>[+<skill>][ at <difficulty number>][=receiver1,receiver2,etc]")

        if split_str[0].lstrip('-').isdigit() and not int(split_str[0]) > 0:
            raise ValueError("Retainer ID must be a positive number.")

        retainer_id = int(split_str[0])

        return split_str[1], retainer_id


    def _extract_difficulty(self, args: str) -> (str, int):
        """
        Extracts difficulty value if specified.  Otherwise, sets difficulty
        to be DIFF_DEFAULT.

        Args must be of the form '<stat>[+<skill>][ at <difficulty number>]'
        
        Returns difficulty and '<stat>[+<skill>]'
        """
        difficulty = stats_and_skills.DIFF_DEFAULT
        maximum_difference = 100

        # if args contains ' at ', then we split into halves. otherwise it's default difficulty
        split_str = args.split(' at ')
        if len(split_str) > 1:
            if not split_str[1].isdigit() or not 0 < int(split_str[1]) < maximum_difference:
                raise ValueError("Difficulty must be a number between 1 and %s." % maximum_difference)
                return
            difficulty = int(split_str[1])
        
        return split_str[0], difficulty


    def _extract_stat_skill(self, args: str) -> (str, str):
        """
        Extracts and validates the stat and skill names.

        Args must be of the form '<stat>[+<skill>]'
        """
        stat, skill = None, None

        split_str = args.split("+")
        stat = split_str[0].strip()
        if len(split_str) > 1:
            skill = split_str[1].strip()

        matches = stats_and_skills.get_partial_match(stat, "stat")
        if not matches or len(matches) > 1:
            raise ValueError("There must be one unique match for a character stat. Please check spelling and try again.")
        # get unique string that matches stat
        stat = matches[0]

        if skill:
            matches = stats_and_skills.get_partial_match(skill, "skill")
            if not matches:
                # check for a skill not in the normal valid list
                if skill in self.caller.db.skills:
                    matches = [skill]
                else:
                    raise ValueError("No matches for a skill by that name. Check spelling and try again.")
            if len(matches) > 1:
                raise ValueError("There must be one unique match for a character skill. Please check spelling and try again.")
            skill = matches[0]

        return stat, skill


    def _send_quiet_roll_msg(self):
        """
        Notifies all staff and specified player(s) in the room of the result
        of the roll.
        """

        namelist = []
        roll_msg = "|w[Private Roll]|n " + Roll.build_msg(self.caller.ndb.last_roll)
        if self.rhs.lower() in ("me", "self", str(self.caller), str(self.caller.key)):
            namelist.append("self-only")
        else:  # send roll message to each recipient
            for name in self.rhs.split(","):
                recipient = self.caller.search(name.strip(), use_nicks=True)
                if recipient:
                    namelist.append(name.strip())
                    recipient.msg(roll_msg, options={'roll':True})
        roll_msg += " (Shared with: %s)" % ", ".join(namelist)
        self.caller.msg(roll_msg, options={'roll':True})
        # GMs always get to see rolls.
        staff_list = [x for x in self.caller.location.contents if x.check_permstring("Builders")]
        for gm in staff_list:
            gm.msg(roll_msg, options={'roll':True})


class CmdSpoofCheck(ArxCommand):
    """
    @gmcheck

    Usage:
        @gmcheck <stat>/<value>[+<skill>/<value>][ at <difficulty>]
        @gmcheck/can_crit <same as above>
        @gmcheck/flub <same as above>

    Performs a stat + skill at difficulty check with specified values. If no
    difficulty is set, default is used. Intended for GMs to make rolls for NPCs
    that don't necessarily exist as characters in-game. The /can_crit switch
    allows the roll to crit. The /flub switch intentionally, silently fails.
    """

    key = "@gmcheck"
    locks = "cmd:all()"

    def get_value_pair(self, argstr):
        try:
            argstr = argstr.strip()
            args = argstr.split("/")
            key = args[0]
            val = int(args[1])
            if val < 1 or val > 20:
                self.msg("Please enter a value between 1 and 20.")
                return
            return key, val
        except (IndexError, TypeError, ValueError):
            self.msg("Specify name/value for stats/skills.")

    def func(self):
        maximum_difference = 100
        crit = "can_crit" in self.switches
        flub = "flub" in self.switches
        roll = Roll(can_crit=crit, quiet=False, announce_room=self.caller.location, announce_values=True, flub=flub)
        try:
            # rest of the command here. PS, I love you. <3
            # checks to see if difficulty exists. PPS Love you too!
            args_list = self.args.lower().split(' at ')
            if len(args_list) > 1:
                if not args_list[1].isdigit() or not 0 < int(args_list[1]) < maximum_difference:
                    self.msg("Difficulty must be a number between 1 and %s." % maximum_difference)
                    return
                difficulty = int(args_list[1])
                roll.difficulty = difficulty
            # 'args' here is the remainder after difficulty was split away.
            # it is not self.args
            args = args_list[0]
            other_list = args.split("+")
            if len(other_list) > 1:
                skilltup = self.get_value_pair(other_list[1])
                if not skilltup:
                    return
                roll.skills = {skilltup[0]: skilltup[1]}
            else:
                roll.stat_keep = True
                roll.skill_keep = False
            stattup = self.get_value_pair(other_list[0])
            if not stattup:
                return
            roll.stats = {stattup[0]: stattup[1]}
            roll.character_name = "%s GM Roll" % self.caller
            # Just so you know, you are beautiful and I love you. <3
            roll.roll()
        except IndexError:
            self.msg("usage: @gmcheck <stat>/<value>[+<skill>/<value>] at <difficulty number>")
            return
