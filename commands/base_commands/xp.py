"""
XP and Skill stuff!

Most utilities for xp/costs and skill checks are all handled
in the gamesrc.objects.stats_and_skills file, which we'll use
liberally here. In general, all the commands players and builders
will use to see their skills, use or adjust xp, and so on will
be here, as well as related commands such as voting to give
other players xp awards for good roleplay.
"""

from commands.base import ArxCommand, ArxPlayerCommand
from world import stats_and_skills
from server.utils.arx_utils import inform_staff
from evennia.utils.utils import list_to_string
from evennia.accounts.models import AccountDB
from world.traits.models import Trait


class CmdUseXP(ArxCommand):
    """
    xp
    Usage:
        xp
        xp/spend  <stat or skill name>
        xp/cost   <stat or skill name>
        xp/transfer <alt>=<amount>

    Displays how much xp you have available when used with no arguments,
    and allows you to spend xp to increase stats or skills with the
    /spend switch. Costs can be reduced by finding a teacher who is willing
    to use the '{wtrain{n' command on you, and has a skill or stat of the
    appropriate rank you're trying to achieve. The training bonus vanishes
    when xp is spent.

    Dominion influence is bought with 'resources' rather than xp. The
    'learn' command is the same as 'xp/spend'.
    """

    key = "xp"
    aliases = ["+xp", "experience", "learn"]
    locks = "cmd:all()"
    help_category = "Progression"

    def display_traits(self):
        caller = self.caller
        caller.msg("{wCurrent Teacher:{n %s" % caller.db.trainer)
        caller.msg("{wUnspent XP:{n %s" % caller.item_data.xp)
        caller.msg("{wLifetime Earned XP:{n %s" % caller.item_data.total_xp)
        all_stats = ", ".join(Trait.get_valid_stat_names())
        caller.msg("\n{wStat names:{n")
        caller.msg(all_stats)
        caller.msg("\n{wSkill names:{n")
        caller.msg(", ".join(Trait.get_valid_skill_names()))
        caller.msg("\n{wDominion skill names:{n")
        caller.msg(", ".join(skill for skill in stats_and_skills.DOM_SKILLS))
        caller.msg("\n{wAbility names:{n")
        crafting = Trait.get_valid_ability_names(Trait.CRAFTING)
        abilities = caller.traits.abilities
        abilities = set(abilities.keys()) | set(crafting)
        if caller.check_permstring("builder"):
            caller.msg(", ".join(Trait.get_valid_ability_names()))
        else:
            caller.msg(", ".join(ability for ability in abilities))

    def transfer_xp(self):
        targ = self.caller.player.search(self.lhs)
        if not targ:
            return
        alt = targ.char_ob
        account = self.caller.roster.current_account
        if alt.roster.current_account != account:
            self.msg("%s is not an alt of yours." % alt)
            return
        try:
            amt = int(self.rhs)
            if amt <= 0:
                raise ValueError
        except (ValueError, TypeError):
            self.msg("Amount must be a positive number.")
            return
        history = self.caller.roster.accounthistory_set.filter(account=account).last()
        if amt > history.xp_earned:
            self.msg(
                "You cannot transfer more xp than you've earned since playing the character."
            )
            return
        if amt > self.caller.item_data.xp:
            self.msg("You do not have enough xp remaining.")
            return
        self.caller.adjust_xp(-amt)
        alt.adjust_xp(amt)
        self.msg("Transferred %s xp to %s." % (amt, alt))
        history.xp_earned -= amt
        history.save()
        if self.caller.item_data.total_xp:
            self.caller.item_data.total_xp -= amt

    # noinspection PyUnresolvedReferences
    def func(self):
        """
        Allows the character to check their xp, and spend it if they use
        the /spend switch and meet the requirements.
        """
        caller = self.caller
        dompc = None
        resource = None
        set_specialization = False
        spec_warning = False
        if self.cmdstring == "learn":
            self.switches.append("spend")
        if not self.args:
            # Just display our xp
            self.display_traits()
            return
        if "transfer" in self.switches:
            self.transfer_xp()
            return
        args = self.args.lower()
        # get cost already factors in if we have a trainer, so no need to check
        if args in Trait.get_valid_stat_names():
            cost = stats_and_skills.get_stat_cost(caller, args)
            current = caller.traits.get_stat_value(args)
            if not caller.traits.check_stat_can_be_raised(args):
                caller.msg("%s is already at its maximum." % args)
                return
            stype = "stat"
        elif args in Trait.get_valid_skill_names():
            current = caller.traits.get_skill_value(args)
            if current >= 6:
                caller.msg("%s is already at its maximum." % args)
                return
            if (
                current >= 5
                and stats_and_skills.get_skill_cost_increase(caller) <= -1.0
            ):
                caller.msg(
                    "You cannot buy a legendary skill while you still have catchup xp remaining."
                )
                return
            cost = stats_and_skills.get_skill_cost(caller, args)
            stype = "skill"
        elif args in stats_and_skills.DOM_SKILLS:
            try:
                dompc = caller.player.Dominion
                current = getattr(dompc, args)
                resource = stats_and_skills.get_dom_resource(args)
                if current >= 10:
                    caller.msg("%s is already at its maximum." % args)
                    return
                cost = stats_and_skills.get_dom_cost(caller, args)
                stype = "dom"
            except AttributeError:
                caller.msg("Dominion object not found.")
                return
        elif args in Trait.get_valid_ability_names():
            # if we don't have it, determine if we can learn it
            current = caller.traits.get_ability_value(args)
            if not current:
                if args in Trait.get_valid_ability_names(Trait.CRAFTING):
                    # check if we have valid skill:
                    if args == "tailor" and "sewing" not in caller.traits.skills:
                        caller.msg("You must have sewing to be a tailor.")
                        return
                    if (
                        args == "weaponsmith" or args == "armorsmith"
                    ) and "smithing" not in caller.traits.skills:
                        caller.msg("You must have smithing to be a %s." % args)
                        return
                    if args == "apothecary" and "alchemy" not in caller.traits.skills:
                        caller.msg("You must have alchemy to be an apothecary.")
                        return
                    if (
                        args == "leatherworker"
                        and "tanning" not in caller.traits.skills
                    ):
                        caller.msg("You must have tanning to be a leatherworker.")
                        return
                    if (
                        args == "carpenter"
                        and "woodworking" not in caller.traits.skills
                    ):
                        caller.msg("You must have woodworking to be a carpenter.")
                        return
                    if args == "jeweler" and "smithing" not in caller.traits.skills:
                        caller.msg("You must have smithing to be a jeweler.")
                        return
                    spec_warning = True
                elif not caller.check_permstring(args):
                    caller.msg("You do not have permission to learn %s." % args)
                    return
                else:
                    spec_warning = False
            if current >= 6:
                caller.msg("%s is already at its maximum." % args)
                return
            if args in Trait.get_valid_ability_names(Trait.CRAFTING):
                spec_warning = True
            if current == 5:
                if any(
                    key
                    for key, value in caller.traits.abilities.items()
                    if key in Trait.get_valid_ability_names(Trait.CRAFTING)
                    and value >= 6
                ):
                    caller.msg("You have already chosen a crafting specialization.")
                    return
                else:
                    set_specialization = True
                    spec_warning = False
            stype = "ability"
            cost = stats_and_skills.get_ability_cost(caller, args)
        else:
            caller.msg(
                "'%s' wasn't identified as a stat, ability, or skill." % self.args
            )
            return
        if "cost" in self.switches:
            caller.msg("Cost for %s: %s" % (self.args, cost))
            return
        if "spend" in self.switches:
            # ap_cost = 5 * (current + 1)
            # if not self.player.pay_action_points(ap_cost):
            #     self.msg("You do not have enough action points to spend xp on that.")
            #     return
            if stype == "dom":
                if cost > getattr(dompc.assets, resource):
                    msg = "Unable to buy influence in %s. The cost is %s, " % (
                        args,
                        cost,
                    )
                    msg += "and you have %s %s resources available." % (
                        getattr(dompc.assets, resource),
                        resource,
                    )
                    caller.msg(msg)
                    return
            elif cost > caller.item_data.xp:
                caller.msg(
                    "Unable to raise %s. The cost is %s, and you have %s xp."
                    % (args, cost, caller.item_data.xp)
                )
                return
            if stype == "stat":
                caller.adjust_xp(-cost)
                caller.traits.adjust_stat(args)
                caller.msg("You have increased your %s to %s." % (args, current + 1))
                return
            if stype == "skill":
                caller.adjust_xp(-cost)
                caller.traits.adjust_skill(args)
                caller.traits.record_skill_purchase(args, cost)
                caller.msg("You have increased your %s to %s." % (args, current + 1))
                if current + 1 == 6:  # legendary rating
                    inform_staff("%s has bought a rank 6 of %s." % (caller, args))
                return
            if stype == "ability":
                if set_specialization:
                    caller.msg("You have set your primary ability to be %s." % args)
                if spec_warning:
                    caller.msg(
                        "{wNote: The first crafting ability raised to 6 will be your specialization.{n"
                    )
                caller.adjust_xp(-cost)
                caller.traits.adjust_ability(args)
                ability_history = caller.db.ability_history or {}
                spent_list = ability_history.get(args, [])
                spent_list.append(cost)
                ability_history[args] = spent_list
                caller.db.ability_history = ability_history
                caller.msg("You have increased your %s to %s." % (args, current + 1))
                return
            if stype == "dom":
                # charge them influence
                setattr(dompc.assets, resource, getattr(dompc.assets, resource) - cost)
                caller.traits.adjust_dom(args)
                caller.msg(
                    "You have increased your %s influence for a cost of %s %s resources."
                    % (args, resource, cost)
                )
                caller.refresh_from_db()
                return
            return
        # invalid or no switch + arguments
        caller.msg("Usage: xp/spend <stat, ability or skill>")


class CmdTrain(ArxCommand):
    """
    train

    Usage:
        train/stat  <trainee>=<stat>
        train/skill <trainee>=<skill>
        train/ability <trainee>=<ability>
        train/retainer <owner>=<npc name or ID number>[, additional AP]

    Allows you to flag a character as being trained with you, imparting a
    temporary xp cost reduction to the appropriate stat or skill. This bonus
    only lasts until they log out or the server reboots, so it should be
    used promptly.

    You can train up to a max number of players depending on your teaching
    or animal ken skill without expending action points: 1 for skill 0-2,
    2 for 3-4, 3 for 5.

    Action points used for training is 100 - 15 * skill, where skill is the
    higher of animal ken or teaching.

    Additional AP can be spent when training a retainer to lower the chance
    of failure.
    """

    key = "train"
    aliases = ["+train", "teach", "+teach"]
    locks = "cmd:all()"
    help_category = "Progression"

    def get_help(self, caller, cmdset):
        if caller.char_ob:
            caller = caller.char_ob
        trained = ", ".join(ob.key for ob in self.currently_training(caller))
        if trained:
            trained = "You have trained %s this week. " % trained
        msg = (
            self.__doc__
            + """

    You can train {w%s{n people per week.
    %sYour current cost to train another character is {w%s{n AP.
    """
            % (self.max_trainees(caller), trained, self.action_point_cost(caller))
        )
        return msg

    def max_trainees(self, character):
        max_skill = self.max_skill(character)
        if max_skill < 3:
            return 1
        if max_skill < 5:
            return 2
        if max_skill < 6:
            return 3
        return 13

    @staticmethod
    def max_skill(character):
        skills_to_check = ("animal ken", "teaching")
        max_skill = 0
        for skill in skills_to_check:
            val = character.traits.get_skill_value(skill)
            if val > max_skill:
                max_skill = val
        return max_skill

    def action_point_cost(self, character):
        """Redundant attribute to try to resolve sync/caching errors."""
        num_trained = character.db.num_trained or 0
        if num_trained < len(self.currently_training(character)):
            num_trained = len(self.currently_training(character))
        if num_trained < self.max_trainees(character):
            return 0
        return 100 - 15 * self.max_skill(character)

    @staticmethod
    def currently_training(character):
        if character.db.currently_training is None:
            character.db.currently_training = []
        return character.db.currently_training

    def pay_ap_cost(self, character, additional_cost=0):
        cost = self.action_point_cost(character) + additional_cost
        if not cost:
            return True
        if not character.ndb.training_cost_confirmation:
            self.msg(
                "It will use %s action points to train. Repeat the command to confirm."
                % cost
            )
            character.ndb.training_cost_confirmation = True
            return
        character.ndb.training_cost_confirmation = False
        if character.player_ob.pay_action_points(cost):
            return True
        self.msg("You don't have enough action points to train another.")

    def check_attribute_name(self, valid_list, attr_type):
        if self.rhs.lower() not in valid_list:
            self.msg("%s is not a valid %s." % (self.rhs, attr_type))
            return False
        return True

    def check_attribute_value(self, trainer_attr, target_attr):
        if trainer_attr <= target_attr + 1:
            self.msg("Your %s is not high enough to train %s." % (self.rhs, self.lhs))
            return False
        return True

    # noinspection PyProtectedMember
    def func(self):
        """Execute command."""
        caller = self.caller
        switches = self.switches
        # try to handle possible caching errors
        caller.attributes._cache.pop("currently_training-None", None)
        caller.attributes._cache.pop("num_trained-None", None)
        caller.refresh_from_db()
        if not self.args:
            self.msg(
                "Currently training: %s"
                % ", ".join(str(ob) for ob in self.currently_training(caller))
            )
            self.msg("You can train %s targets." % self.max_trainees(caller))
            return
        if not self.lhs or not self.rhs or not self.switches:
            caller.msg(
                "Usage: train/[stat or skill] <character to train>=<name of stat or skill to train>"
            )
            return
        additional_cost = 0
        if "retainer" in self.switches:
            player = caller.player.search(self.lhs)
            from world.dominion.models import Agent

            if len(self.rhslist) < 2:
                rhs = self.rhs
            else:
                rhs = self.rhslist[0]
                try:
                    additional_cost = int(self.rhslist[1])
                except ValueError:
                    self.msg("Additional AP must be a number.")
                    return
            try:
                if rhs.isdigit():
                    targ = player.retainers.get(id=rhs).dbobj
                else:
                    targ = player.retainers.get(name__iexact=rhs).dbobj
                if not targ or not targ.pk:
                    raise Agent.DoesNotExist
            except (Agent.DoesNotExist, AttributeError):
                self.msg("Could not find %s's retainer named %s." % (player, rhs))
                return
            caller_msg = "You have trained %s." % targ
            targ_msg = ""
        else:
            targ = caller.search(self.lhs)
            if not targ:
                caller.msg("No one to train by the name of %s." % self.lhs)
                return
            if not targ.player:
                caller.msg("Use the /retainer switch to train non-player-characters.")
                return
            if "stat" in switches:
                stat = self.rhs.lower()
                if not self.check_attribute_name(Trait.get_valid_stat_names(), "stat"):
                    return
                if not self.check_attribute_value(
                    caller.traits.get_stat_value(stat), targ.traits.get_stat_value(stat)
                ):
                    return
            elif "skill" in switches:
                skill = self.rhs.lower()
                if not self.check_attribute_name(
                    Trait.get_valid_skill_names(), "skill"
                ):
                    return
                if not self.check_attribute_value(
                    caller.traits.get_skill_value(skill),
                    targ.traits.get_skill_value(skill),
                ):
                    return
            elif "ability" in switches:
                ability = self.rhs.lower()
                if not self.check_attribute_name(
                    Trait.get_valid_ability_names(), "ability"
                ):
                    return
                if not self.check_attribute_value(
                    caller.traits.get_ability_value(ability),
                    targ.traits.get_ability_value(ability),
                ):
                    return
            else:
                caller.msg(
                    "Usage: train/[stat or skill] <character>=<stat or skill name>"
                )
                return
            caller_msg = (
                "You have provided training to %s for them to increase their %s."
                % (targ.name, self.rhs)
            )
            targ_msg = "%s has provided you training, helping you increase your %s." % (
                caller.name,
                self.rhs,
            )
        if not targ.can_be_trained_by(caller):
            return
        if not self.pay_ap_cost(caller, additional_cost):
            return
        targ.post_training(
            caller, trainer_msg=caller_msg, targ_msg=targ_msg, ap_spent=additional_cost
        )
        return


class CmdAwardXP(ArxPlayerCommand):
    """
    @awardxp

    Usage:
        @awardxp  <character>=<value>[/<inform message>]

    Gives some of that sweet, sweet xp to a character.
    """

    key = "@awardxp"
    locks = "cmd:perm(Wizards)"
    help_category = "Progression"

    def func(self):
        """Execute command."""
        caller = self.caller
        targ = caller.search(self.lhs)
        if not targ:
            return
        inform_msg = ""
        try:
            rhs = self.rhs.split("/", 1)
            val = int(rhs[0])
            if len(rhs) > 1:
                inform_msg = rhs[1]
            if not val:
                raise ValueError
        except (TypeError, ValueError, AttributeError):
            self.msg("Invalid syntax: Must have an xp amount.")
            return
        char = targ.char_ob
        if not char:
            caller.msg("No active character found for that player.")
            return
        char.adjust_xp(val)
        if inform_msg:
            msg = "You have been awarded %d xp: %s" % (val, inform_msg)
            targ.inform(msg, category="XP")
            inform_msg = " Message sent to player: %s" % inform_msg
        caller.msg("Giving %s xp to %s.%s" % (val, char, inform_msg))
        inform_staff(
            "%s has adjusted %s's xp by %s.%s" % (caller, char, val, inform_msg)
        )


class CmdAdjustSkill(ArxPlayerCommand):
    """
    @adjustskill

    Usage:
        @adjustskill  <character>/<skill>=<value>
        @adjustability <character>/<ability>=<value>
        @adjustskill/ability <character>/<ability>=<value>
        @adjustskill/reset <character>=<vocation>
        @adjustskill/refund <character>=<skill>
        @adjustability/refund <character>=<ability>

    Changes character's skill to be set to the value. Stats can be changed
    by @set character/<stat>=value, but skills are stored in a dict and are
    easier to do with this command.

    Reset will set a character's stats and skills to the starting values
    for the given vocation, and reset how much xp they have to spend based
    on their lifetime earned xp + the bonus for their social rank.
    """

    key = "@adjustskill"
    locks = "cmd:perm(Wizards)"
    help_category = "Progression"
    aliases = ["@adjustskills", "@adjustability", "@adjustabilities"]

    # noinspection PyUnresolvedReferences
    def func(self):
        """Execute command."""
        caller = self.caller
        ability = (
            "ability" in self.switches
            or self.cmdstring == "@adjustability"
            or self.cmdstring == "@adjustabilities"
        )
        char = None
        if "reset" in self.switches or "refund" in self.switches:
            try:
                char = caller.search(self.lhs).char_ob
            except (AttributeError, ValueError, TypeError):
                caller.msg("No player by that name.")
                return
            if char.item_data.xp is None:
                char.item_data.xp = 0
            if "reset" in self.switches:
                try:
                    from commands.base_commands.guest import (
                        setup_voc,
                        XP_BONUS_BY_SRANK,
                    )

                    rhs = self.rhs.lower()
                    setup_voc(char, rhs)
                    char.item_data.vocation = rhs
                    total_xp = char.item_data.total_xp or 0
                    total_xp = int(total_xp)
                    xp = XP_BONUS_BY_SRANK[char.item_data.social_rank]
                    xp += total_xp
                    char.item_data.xp = xp
                    caller.msg(
                        "%s has had their skills and stats set up as a %s."
                        % (char, rhs)
                    )
                    return
                except (AttributeError, ValueError, TypeError, KeyError):
                    caller.msg("Could not set %s to %s vocation." % (char, self.rhs))
                    return
        if "refund" in self.switches:
            if not ability:
                try:
                    current = char.traits.get_skill_value(self.rhs)
                except KeyError:
                    caller.msg("No such skill.")
                    return
                if current <= 0:
                    caller.msg("That would give them a negative skill.")
                    return
                try:
                    cost = char.traits.remove_last_skill_purchase_record(self.rhs)
                except ValueError:
                    cost = stats_and_skills.cost_at_rank(self.rhs, current - 1, current)
                char.traits.set_skill_value(self.rhs, current - 1)
                char.item_data.xp += cost
            else:
                ability_history = char.db.ability_history or {}
                try:
                    current = char.traits.get_ability_value(self.rhs)
                    ability_list = ability_history[self.rhs]
                    cost = ability_list.pop()
                    ability_history[self.rhs] = ability_list
                    char.db.ability_history = ability_history
                except (KeyError, IndexError, TypeError):
                    current = char.traits.get_ability_value(self.rhs)
                    if not current:
                        caller.msg("No such ability.")
                        return
                    cost = stats_and_skills.cost_at_rank(self.rhs, current - 1, current)
                if current <= 0:
                    caller.msg("That would give them a negative rating.")
                    return
                char.traits.set_ability_value(self.rhs, current - 1)
                char.item_data.xp += cost
            caller.msg(
                "%s had %s reduced by 1 and was refunded %s xp."
                % (char, self.rhs, cost)
            )
            return
        try:
            player, skill = self.lhs.strip().split("/")
            rhs = int(self.rhs)
        except (AttributeError, ValueError, TypeError):
            caller.msg("Invalid syntax")
            return
        targ = caller.search(player)
        if not targ:
            caller.msg("No player found by that name.")
            return
        char = targ.char_ob
        if not char:
            caller.msg("No active character for %s." % targ)
            return
        if ability:
            char.traits.set_ability_value(skill, rhs)
        else:
            char.traits.set_skill_value(skill, rhs)
        if rhs <= 0:
            if ability:
                caller.msg("Removed ability %s from %s." % (skill, char))
            else:
                caller.msg("Removed skill %s from %s." % (skill, char))
        else:
            caller.msg("%s's %s set to %s." % (char, skill, rhs))
        if not caller.check_permstring("immortals"):
            inform_staff("%s set %s's %s skill to %s." % (caller, char, skill, rhs))


class CmdVoteXP(ArxPlayerCommand):
    """
    vote

    Usage:
        vote <player>
        unvote <player>

    Lodges a vote for a character to receive an additional xp point for
    this week due to excellent RP. Please vote for players who have
    impressed you in RP, rather than just your friends. Voting for your
    alts is obviously against the rules.

    Using vote with no arguments displays your votes.
    """

    key = "vote"
    aliases = ["+vote", "@vote", "unvote"]
    locks = "cmd:all()"
    help_category = "Progression"

    @property
    def caller_alts(self):
        return AccountDB.objects.filter(
            roster__current_account__isnull=False,
            roster__roster__name="Active",
            roster__current_account=self.caller.roster.current_account,
        )

    def count_votes(self):
        num_votes = 0
        for player in self.caller_alts:
            votes = player.db.votes or []
            num_votes += len(votes)
        return num_votes

    @property
    def max_votes(self):
        # import datetime
        base = 13
        # # only get events after the previous Sunday
        # diff = 7 - datetime.datetime.now().isoweekday()
        # recent_date = datetime.datetime.now() - datetime.timedelta(days=7-diff)
        # for alt in self.caller_alts:
        #     try:
        #         base += alt.Dominion.events_attended.filter(finished=True, date__gte=recent_date).count()
        #     except AttributeError:
        #         continue
        return base

    # noinspection PyUnresolvedReferences
    def func(self):
        """
        Stores a vote for the player in the caller's player object, to allow
        for easier sorting from the AccountDB manager. Players are allowed 5
        votes per week, each needing to be a distinct character with a different
        email address than the caller. Email addresses that are not set (having
        the 'dummy@dummy.com' default, will be rejected as unsuitable.
        """
        caller = self.caller
        if not caller.roster.current_account:
            raise ValueError("ERROR: No PlayerAccount set for this player!")
        if not self.args:
            votes = caller.db.votes or []
            voted_for = list_to_string(votes) or "no one"
            remaining = self.max_votes - self.count_votes()
            caller.msg(
                "You have voted for %s, and have %s votes remaining."
                % (voted_for, remaining)
            )
            return
        targ = caller.search(self.args)
        if not targ:
            caller.msg("Vote for who?")
            return
        if targ in self.caller_alts:
            caller.msg("You cannot vote for your alts.")
            return
        votes = caller.db.votes or []
        if targ.roster.roster.name != "Active" and targ not in votes:
            caller.msg("You can only vote for an active character.")
            return
        if not targ.char_ob:
            caller.msg("%s doesn't have a character object assigned to them." % targ)
            return
        if targ in votes:
            if self.cmdstring == "unvote":
                caller.msg("Removing your vote for %s." % targ)
                votes.remove(targ)
                caller.db.votes = votes
            else:
                caller.msg(
                    "You are already voting for %s. To remove them, use 'unvote'."
                    % targ
                )
            return
        else:
            if self.cmdstring == "unvote":
                caller.msg("You are not currently voting for %s." % targ)
                return
        num_votes = self.count_votes()
        if num_votes >= self.max_votes:
            caller.msg("You have voted %s times, which is the maximum." % num_votes)
            return
        votes.append(targ)
        caller.db.votes = votes
        caller.msg("Vote recorded for %s." % targ)
