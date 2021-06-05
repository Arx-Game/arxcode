"""
This script keeps a timer that will cause an update to happen
on a weekly basis. Things we'll be updating are counting votes
for players, and processes for Dominion.
"""
import traceback
from collections import defaultdict
from datetime import datetime, timedelta

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q, F


from evennia.objects.models import ObjectDB
from evennia.utils.evtable import EvTable

from world.dominion.models import AssetOwner, Member, AccountTransaction
from world.dominion.domain.models import Army, Orders
from world.dominion.plots.models import ActionRequirement
from world.msgs.models import Inform
from typeclasses.bulletin_board.bboard import BBoard
from typeclasses.accounts import Account
from .scripts import Script
from .script_mixins import RunDateMixin
from server.utils.arx_utils import inform_staff, cache_safe_update
from web.character.models import Investigation, RosterEntry


EVENT_SCRIPT_NAME = "Weekly Update"
VOTES_BOARD_NAME = "Votes"
PRESTIGE_BOARD_NAME = "Prestige Changes"
TRAINING_CAP_PER_WEEK = 10

PLAYER_ATTRS = (
    "votes",
    "claimed_scenelist",
    "random_scenelist",
    "validated_list",
    "praises",
    "condemns",
    "requested_validation",
    "donated_ap",
    "masked_validated_list",
    "event_xp",
)
CHARACTER_ATTRS = (
    "currently_training",
    "trainer",
    "scene_requests",
    "num_trained",
    "num_journals",
    "num_rel_updates",
    "num_comments",
    "num_flashbacks",
    "support_cooldown",
    "support_points_spent",
    "rp_command_used",
    "random_rp_command_this_week",
)


class BulkInformCreator(object):
    """
    A container where we can add informs one at a time to be created after all are
    ready.
    """

    def __init__(self, week=None):
        self.informs = []
        self.receivers_to_notify = set()
        self.week = week

    def add_player_inform(self, player, msg, category, week=None):
        """Adds an inform for a player to our list"""
        return self.make_initial_inform(msg, category, week, player=player)

    def add_org_inform(self, org, msg, category, week=None):
        """Adds an inform for an org to our list"""
        return self.make_initial_inform(msg, category, week, org=org)

    def make_initial_inform(self, msg, category, week=None, player=None, org=None):
        """Creates a base Inform object. This isn't in the database yet."""
        week = week or self.week or 0
        inform = Inform(
            message=msg, week=week, category=category, player=player, organization=org
        )
        # for efficiency we're going to skip notifying orgs, as that's expensive
        if player:
            self.receivers_to_notify.add(player)
        self.informs.append(inform)
        return inform

    def create_and_send_informs(self, sender="the Weekly Update script"):
        """Creates all our informs and notifies players/orgs about them"""
        Inform.objects.bulk_create(self.informs)
        for receiver in self.receivers_to_notify:
            receiver.msg("{yYou have new informs from %s.{n" % sender)


class WeeklyEvents(RunDateMixin, Script):
    """
    This script repeatedly saves server times so
    it can be retrieved after server downtime.
    """

    XP_TYPES_FOR_RESOURCES = ("votes", "scenes")

    # noinspection PyAttributeOutsideInit
    def at_script_creation(self):
        """
        Setup the script
        """
        self.key = EVENT_SCRIPT_NAME
        self.desc = "Triggers weekly events"
        self.interval = 3600
        self.persistent = True
        self.start_delay = True
        self.attributes.add("run_date", datetime.now() + timedelta(days=7))

    def at_start(self, **kwargs):
        super(WeeklyEvents, self).at_start(**kwargs)
        from world.magic.advancement import init_magic_advancement

        init_magic_advancement()

    @property
    def inform_creator(self):
        """Returns a bulk inform creator we'll use for gathering informs from the weekly update"""
        if self.ndb.inform_creator is None:
            self.ndb.inform_creator = BulkInformCreator(week=self.db.week)
        return self.ndb.inform_creator

    def at_repeat(self):
        """
        Called every minute to update the timers.
        """
        if self.check_event():
            # check if we've been tagged to not reset next time we run
            self.do_weekly_events()
        else:
            hour = timedelta(minutes=65)
            if self.time_remaining < hour:
                from evennia.server.sessionhandler import SESSIONS

                cron_msg = (
                    "{wReminder: Weekly Updates will be running in about an hour.{n"
                )
                SESSIONS.announce_all(cron_msg)

    def do_weekly_events(self, reset=True):
        """
        It's time for us to do events, like count votes, update dominion, etc.
        """
        # schedule next weekly update for one week from now
        self.db.run_date += timedelta(days=7)
        # initialize temporary dictionaries we used for aggregating values
        self.initialize_temp_dicts()
        # processing for each player
        self.do_events_per_player()
        # awarding votes we counted
        self.award_scene_xp()
        self.award_vote_xp()
        self.post_top_rpers()
        self.post_top_prestige()
        # dominion stuff
        self.do_dominion_events()
        self.cleanup_stale_attributes()
        self.post_inactives()
        self.db.pose_counter = (self.db.pose_counter or 0) + 1
        if self.db.pose_counter % 4 == 0:
            self.db.pose_counter = 0
            self.count_poses()
        self.db.week += 1
        self.reset_action_points()
        self.do_investigations()
        self.inform_creator.create_and_send_informs()
        if reset:
            self.record_awarded_values()

    def do_dominion_events(self):
        """Does all the dominion weekly events"""
        for owner in AssetOwner.objects.all():
            owner.prestige_decay()

        for owner in AssetOwner.objects.filter(
            Q(organization_owner__isnull=False)
            | (
                Q(player__player__roster__roster__name="Active")
                & Q(player__player__roster__frozen=False)
            )
        ).distinct():
            try:
                owner.do_weekly_adjustment(self.db.week, self.inform_creator)
            except Exception as err:
                traceback.print_exc()
                print("Error in %s's weekly adjustment: %s" % (owner, err))
        # resets the weekly record of work command
        cache_safe_update(
            Member.objects.filter(deguilded=False),
            work_this_week=0,
            investment_this_week=0,
        )
        # decrement timer of limited transactions, remove transactions that are over
        AccountTransaction.objects.filter(repetitions_left__gt=0).update(
            repetitions_left=F("repetitions_left") - 1
        )
        AccountTransaction.objects.filter(repetitions_left=0).delete()
        for army in Army.objects.filter(orders__week=self.db.week):
            try:
                army.execute_orders(self.db.week)
            except Exception as err:
                traceback.print_exc()
                print("Error in %s's army orders: %s" % (army, err))
        old_orders = Orders.objects.filter(complete=True, week__lt=self.db.week - 4)
        old_orders.delete()
        for requirement in ActionRequirement.objects.filter(weekly_total__gt=0):
            requirement.weekly_total = 0
            requirement.save()
        inform_staff("Dominion weekly events processed for week %s." % self.db.week)

    @staticmethod
    def reset_action_points():
        """
        Originally did this with RosterEntry update but ran into issues with cache being out
        of sync, so action_points didn't properly update. Look into solving that in the future
        for more efficient bulk update implementation.
        """
        qs = Account.objects.filter(roster__roster__name="Active").distinct()
        for ob in qs:
            current = ob.roster.action_points
            max_ap = ob.roster.max_action_points
            regen = ob.roster.action_point_regen
            if (current + regen) > max_ap:
                increment = max_ap - current
            else:
                increment = regen
            if increment:
                ob.pay_action_points(-increment)

    def do_investigations(self):
        """Does all the investigation events"""
        for investigation in Investigation.objects.filter(
            active=True, ongoing=True, character__roster__name="Active"
        ):
            try:
                investigation.process_events(self.inform_creator)
            except Exception as err:
                traceback.print_exc()
                print("Error in investigation %s: %s" % (investigation, err))

    @staticmethod
    def cleanup_stale_attributes():
        """Deletes stale attributes"""
        try:
            from evennia.typeclasses.attributes import Attribute

            attr_names = CHARACTER_ATTRS + PLAYER_ATTRS
            qs = Attribute.objects.filter(db_key__in=attr_names)
            qs.delete()
        except Exception as err:
            traceback.print_exc()
            print("Error in cleanup: %s" % err)

    # noinspection PyProtectedMember
    def do_events_per_player(self):
        """
        All the different processes that need to occur per player.
        These should be able to occur in any particular order. Because
        votes and prestige gains are tallied we don't do the awards here,
        but handle them separately for efficiency. Things that don't need
        to be recorded will just be processed in their methods.
        """
        self.check_freeze()
        players = [
            ob
            for ob in Account.objects.filter(
                Q(Q(roster__roster__name="Active") & Q(roster__frozen=False))
                | Q(is_staff=True)
            ).distinct()
            if ob.char_ob
        ]
        for player in players:
            self.count_votes(player)
            # journal XP
            self.process_journals(player)
            self.count_scenes(player)
            # niche XP?
            # first-time RP XP?
            # losing gracefully
            # taking damage
            # conditions/social imperative
            # aspirations/progress toward goals
            char = player.char_ob
            # for lazy refresh_from_db calls for queries right after the script runs, but unnecessary after a @reload
            char.ndb.stale_ap = True
            # wipe cached attributes
            for attrname in PLAYER_ATTRS:
                try:
                    del player.attributes._cache["%s-None" % attrname]
                except KeyError:
                    continue
            for attrname in CHARACTER_ATTRS:
                try:
                    del char.attributes._cache["%s-None" % attrname]
                except KeyError:
                    continue
            for agent in player.retainers:
                try:
                    del agent.dbobj.attributes._cache["trainer-None"]
                except (KeyError, AttributeError, ObjectDoesNotExist):
                    continue

    def initialize_temp_dicts(self):
        """Initializes dicts we record weekly values in"""
        # our votes are a dict of player to their number of votes
        self.ndb.recorded_votes = defaultdict(int)
        self.ndb.vote_history = {}
        # storing how much xp each player gets to post after
        self.ndb.xp = defaultdict(int)
        self.ndb.xptypes = {}
        self.ndb.requested_support = {}
        self.ndb.scenes = defaultdict(int)

    @staticmethod
    def check_freeze():
        """Checks if a character should be frozen now"""
        try:
            date = datetime.now()
            Account.objects.filter(last_login__isnull=True).update(last_login=date)
            offset = timedelta(days=-14)
            date = date + offset
            RosterEntry.objects.filter(player__last_login__lt=date).update(frozen=True)
        except Exception as err:
            import traceback

            traceback.print_exc()
            print("Error on freezing accounts: %s" % err)

    def post_inactives(self):
        """Makes a board post of inactive characters"""
        date = datetime.now()
        cutoffdate = date - timedelta(days=30)
        qs = Account.objects.filter(
            roster__roster__name="Active", last_login__isnull=False
        ).filter(last_login__lte=cutoffdate)
        board = BBoard.objects.get(db_key__iexact="staff")
        table = EvTable("{wName{n", "{wLast Login Date{n", border="cells", width=78)
        for ob in qs:
            table.add_row(ob.key.capitalize(), ob.last_login.strftime("%x"))
        board.bb_post(
            poster_obj=self,
            msg=str(table),
            subject="Inactive List",
            poster_name="Inactives",
        )
        inform_staff("List of Inactive Characters posted.")

    def count_poses(self):
        """Makes a board post of characters with insufficient pose-counts"""
        qs = ObjectDB.objects.filter(roster__roster__name="Active")
        min_poses = 20
        low_activity = []
        for ob in qs:
            if ob.posecount < min_poses and (
                ob.tags.get("rostercg")
                and ob.player_ob
                and not ob.player_ob.tags.get("staff_alt")
            ):
                low_activity.append(ob)
            ob.db.previous_posecount = ob.posecount
            ob.posecount = 0
        board = BBoard.objects.get(db_key__iexact="staff")
        table = EvTable("{wName{n", "{wNum Poses{n", border="cells", width=78)
        for ob in low_activity:
            table.add_row(ob.key, ob.db.previous_posecount)
        board.bb_post(poster_obj=self, msg=str(table), subject="Inactive by Poses List")

    # Various 'Beats' -------------------------------------------------

    def process_journals(self, player):
        """
        In the journals here, we're processing all the XP gained for
        making journals, comments, or updating relationships.
        """
        char = player.char_ob
        try:
            account = player.roster.current_account
            if account.id in self.ndb.xptypes:
                total = self.ndb.xptypes[account.id].get("journals", 0)
            else:
                self.ndb.xptypes[account.id] = {}
                total = 0
            journal_total = char.messages.num_weekly_journals
            xp = 0
            if journal_total > 0:
                xp += 4
            if journal_total > 1:
                xp += 2
            if journal_total > 2:
                xp += 1
            # XP capped at 7 for all sources
            if xp > 7:
                xp = 7
            if xp + total > 7:
                xp = 7 - total
            if xp <= 0:
                return
        except (ValueError, TypeError):
            return
        except AttributeError:
            return
        except Exception as err:
            print("ERROR in process journals: %s" % err)
            traceback.print_exc()
            return
        if xp:
            msg = (
                "You received %s xp this week for journals/comments/relationship updates."
                % xp
            )
            self.award_xp(char, xp, player, msg, xptype="journals")

    # -----------------------------------------------------------------

    def count_votes(self, player):
        """
        Counts the votes for each player. We may log voting patterns later if
        we need to track against abuse, but since voting is stored in each
        player it's fairly trivial to check each week on an individual basis
        anyway.
        """
        votes = player.db.votes or []
        for ob in votes:
            self.ndb.recorded_votes[ob] += 1
        if votes:
            self.ndb.vote_history[player] = votes

    def count_scenes(self, player):
        """
        Counts the @randomscenes for each player. Each player can generate up to 3
        random scenes in a week, and each scene that they participated in gives them
        2 xp.
        """
        scenes = player.db.claimed_scenelist or []
        charob = player.char_ob
        for ob in scenes:
            # give credit to the character the player had a scene with
            self.ndb.scenes[ob] += 1
            # give credit to the player's character, once per scene
            if charob:
                self.ndb.scenes[charob] += 1
        requested_scenes = charob.db.scene_requests or {}
        if requested_scenes:
            self.ndb.scenes[charob] += len(requested_scenes)

    def award_scene_xp(self):
        """Awards xp for a character basedon their number of scenes"""
        for char in self.ndb.scenes:
            player = char.player_ob
            if char and player:
                scenes = self.ndb.scenes[char]
                xp = self.scale_xp(scenes * 2)
                if scenes and xp:
                    msg = "You were in %s random scenes this week, earning %s xp." % (
                        scenes,
                        xp,
                    )
                    self.award_xp(char, xp, player, msg, xptype="scenes")

    @staticmethod
    def scale_xp(votes):
        """Helper method for diminishing returns of xp"""
        xp = 0
        # 1 vote is 3 xp
        if votes > 0:
            xp = 3
        # 2 votes is 5 xp
        if votes > 1:
            xp += 2
        # 3 to 5 votes is 6 to 8 xp
        max_range = votes if votes <= 5 else 5
        for n in range(2, max_range):
            xp += 1

        def calc_xp(num_votes, start, stop, div):
            """Helper function for calculating bonus xp"""
            bonus_votes = num_votes
            if stop and (bonus_votes > stop):
                bonus_votes = stop
            bonus_xp = bonus_votes - start
            bonus_xp //= div
            if (bonus_votes - start) % div:
                bonus_xp += 1
            return bonus_xp

        # 1 more xp for each 3 between 6 to 14
        if votes > 5:
            xp += calc_xp(votes, 5, 14, 3)
        # 1 more xp for each 4 votes after 14
        if votes > 14:
            xp += calc_xp(votes, 14, 26, 4)
        # 1 more xp for each 5 votes after 26
        if votes > 26:
            xp += calc_xp(votes, 26, 41, 5)
        # 1 more xp for each 10 votes after 36
        if votes > 41:
            xp += calc_xp(votes, 41, None, 10)
        return xp

    def award_vote_xp(self):
        """
        Go through all of our votes and award xp to the corresponding character
        object of each player we've recorded votes for.
        """
        # go through each key in our votes dict, get player, award xp to their character
        for player, votes in self.ndb.recorded_votes.items():
            # important - get their character, not the player object
            try:
                char = player.char_ob
                if char:
                    xp = self.scale_xp(votes)
                    if votes and xp:
                        msg = "You received %s votes this week, earning %s xp." % (
                            votes,
                            xp,
                        )
                        self.award_xp(char, xp, player, msg, xptype="votes")
            except (AttributeError, ValueError, TypeError):
                print("Error for in award_vote_xp for key %s" % player)

    def award_xp(self, char, xp, player=None, msg=None, xptype="all"):
        """Awards xp for a given character"""
        try:
            try:
                account = char.roster.current_account
                if account.id not in self.ndb.xptypes:
                    self.ndb.xptypes[account.id] = {}
                self.ndb.xptypes[account.id][xptype] = xp + self.ndb.xptypes[
                    account.id
                ].get(xptype, 0)
            except AttributeError:
                pass
            xp = int(xp)
            char.adjust_xp(xp)
            self.ndb.xp[char] += xp
        except Exception as err:
            traceback.print_exc()
            print("Award XP encountered ERROR: %s" % err)
        if player and msg:
            self.inform_creator.add_player_inform(player, msg, "XP", week=self.db.week)
            self.award_resources(player, xp, xptype)

    def award_resources(self, player, xp, xptype="all"):
        """Awards resources to someone based on their xp awards"""
        if xptype not in self.XP_TYPES_FOR_RESOURCES:
            return
        resource_msg = ""
        amt = 0
        try:
            for r_type in ("military", "economic", "social"):
                amt = player.gain_resources(r_type, xp)
            if amt:
                resource_msg = (
                    "Based on your number of %s, you have gained %s resources of each type."
                    % (xptype, amt)
                )
        except AttributeError:
            pass
        if resource_msg:
            self.inform_creator.add_player_inform(
                player, resource_msg, "Resources", week=self.db.week
            )

    def post_top_rpers(self):
        """
        Post ourselves to a bulletin board to celebrate the highest voted RPers
        this week. We post how much xp each player earned, not how many votes
        they received.
        """
        import operator

        # this will create a sorted list of tuples of (id, votes), sorted by xp, highest to lowest
        sorted_xp = sorted(
            self.ndb.xp.items(), key=operator.itemgetter(1), reverse=True
        )
        string = "{wTop RPers this week by XP earned{n".center(60)
        string += "\n{w" + "-" * 60 + "{n\n"
        sorted_xp = sorted_xp[:20]
        num = 0
        for tup in sorted_xp:
            num += 1
            try:
                char = tup[0]
                votes = tup[1]
                name = char.item_data.longname or char.key
                string += "{w%s){n %-35s {wXP{n: %s\n" % (num, name, votes)
            except AttributeError:
                print("Could not find character of id %s during posting." % str(tup[0]))
        board = BBoard.objects.get(db_key__iexact=VOTES_BOARD_NAME)
        board.bb_post(
            poster_obj=self,
            msg=string,
            subject="Weekly Votes",
            poster_name="Vote Results",
        )
        inform_staff("Vote process awards complete. Posted on %s." % board)

    def post_top_prestige(self):
        """Makes a board post of the top prestige earners this past week"""
        import random
        from world.dominion.models import PraiseOrCondemn

        changes = PraiseOrCondemn.objects.filter(week=self.db.week).exclude(
            target__organization_owner__secret=True
        )
        praises = defaultdict(list)
        condemns = defaultdict(list)
        total_values = {}
        for praise in changes.filter(value__gte=0):
            praises[praise.target].append(praise)
        for condemn in changes.filter(value__lt=0):
            condemns[condemn.target].append(condemn)
        for change in changes:
            current = total_values.get(change.target, 0)
            current += change.value
            total_values[change.target] = current

        board = BBoard.objects.get(db_key__iexact=PRESTIGE_BOARD_NAME)

        def get_total_from_list(entry_list):
            """Helper function to get total prestige amount from a list"""
            return sum(praise_ob.value for praise_ob in entry_list)

        sorted_praises = sorted(
            praises.items(), key=lambda x: get_total_from_list(x[1]), reverse=True
        )
        sorted_praises = sorted_praises[:20]
        table = EvTable("{wName{n", "{wValue{n", "{wMsg{n", border="cells", width=78)
        for tup in sorted_praises:
            praise_messages = [ob.message for ob in tup[1] if ob.message]
            selected_message = ""
            if praise_messages:
                selected_message = random.choice(praise_messages)
            table.add_row(
                str(tup[0]).capitalize()[:18],
                get_total_from_list(tup[1]),
                selected_message,
            )
        table.reformat_column(0, width=18)
        table.reformat_column(1, width=10)
        table.reformat_column(2, width=50)
        prestige_msg = "{wMost Praised this week{n".center(72)
        prestige_msg = "%s\n%s" % (prestige_msg, str(table).lstrip())
        prestige_msg += "\n\n"
        try:
            # sort by our prestige change amount
            sorted_changes = sorted(
                total_values.items(), key=lambda x: abs(x[1]), reverse=True
            )
            sorted_changes = sorted_changes[:20]
            table = EvTable(
                "{wName{n",
                "{wPrestige Change Amount{n",
                "{wPrestige Rank{n",
                border="cells",
                width=78,
            )
            rank_order = list(
                AssetOwner.objects.filter(
                    player__player__roster__roster__name="Active"
                ).distinct()
            )
            rank_order = sorted(rank_order, key=lambda x: x.prestige, reverse=True)
            for tup in sorted_changes:
                # get our prestige ranking compared to others
                owner = tup[0]
                try:
                    rank = rank_order.index(owner) + 1
                except ValueError:
                    # they rostered mid-week or whatever, skip them
                    continue
                # get the amount that our prestige has changed. add + for positive
                amt = tup[1]
                if amt > 0:
                    amt = "+%s" % amt
                table.add_row(owner, amt, rank)
            prestige_msg += "\n\n"
            prestige_msg += "{wTop Prestige Changes{n".center(72)
            prestige_msg = "%s\n%s" % (prestige_msg, str(table).lstrip())
        except (AttributeError, ValueError, TypeError):
            import traceback

            traceback.print_exc()
        board.bb_post(
            poster_obj=self,
            msg=prestige_msg,
            subject="Weekly Praises/Condemns",
            poster_name="Prestige",
        )
        inform_staff("Praises/condemns tally complete. Posted on %s." % board)

    def record_awarded_values(self):
        """Makes a record of all values for this week for review, if necessary"""
        self.db.recorded_votes = dict(self.ndb.recorded_votes)
        self.db.vote_history = self.ndb.vote_history
        # storing how much xp each player gets to post after
        self.db.xp = dict(self.ndb.xp)
        self.db.xptypes = self.ndb.xptypes
        self.db.requested_support = self.ndb.requested_support
        self.db.scenes = dict(self.ndb.scenes)
