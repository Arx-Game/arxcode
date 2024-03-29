"""
Commands related to @actions, the main way that players interact with the metaplot or their
own personal story.
"""
from django.db.models import Q

from commands.base import ArxPlayerCommand
from evennia.objects.models import ObjectDB
from evennia.utils.evtable import EvTable
from server.utils import arx_more
from server.utils.arx_utils import dict_from_choices_field
from server.utils.exceptions import ActionSubmissionError
from web.character.models import Clue, Revelation
from world.dominion.models import Organization
from world.dominion.plots.models import (
    Plot,
    PlotAction,
    PlotActionAssistant,
    ActionOOCQuestion,
    ActionRequirement,
    PlotUpdate,
)
from world.magic.models import Spell, SkillNode
from world.stat_checks.models import CheckRank
from world.traits.models import Trait


# noinspection PyUnresolvedReferences
class ActionCommandMixin(object):
    """Mixin for shared methods between player @action command and staff @gm command."""

    def set_action_field(self, action, field_name, value, verbose_name=None):
        """Sets a field in a model with a value and provides command feedback."""
        setattr(action, field_name, value)
        action.save()
        verbose_name = verbose_name or field_name
        if field_name in ("status", "category"):
            value = getattr(action, "get_%s_display" % field_name)()
        self.msg("%s set to %s." % (verbose_name, value))

    def view_action(self, action, disp_old=False):
        """Views an action for caller"""
        text = action.view_action(caller=self.caller, disp_old=disp_old)
        arx_more.msg(self.caller, text, justify_kwargs=False, pages_by_char=True)

    def invite_assistant(self, action):
        """Invites an assistant to an action"""
        player_list = [self.caller.search(arg) for arg in self.rhslist]
        player_list = [ob for ob in player_list if ob]
        if not player_list:
            return
        for player in player_list:
            dompc = player.Dominion
            try:
                action.invite(dompc)
            except ActionSubmissionError as err:
                self.msg(err)
            else:
                self.msg("You have invited %s to join your action." % dompc)


class CmdAction(ActionCommandMixin, ArxPlayerCommand):
    """
    A character's story actions that a GM responds to.

    Usage:
        @action/newaction <plot #>=<story of action>
        @action/tldr <action #>=<title>
        @action/category <action #>=<category>
        @action/roll <action #>=<stat>,<skill>
        @action/ooc_intent <action #>=<ooc intent, then post-submission questions>
        @action/question <action #>=<ask a question>
        @action/cancel <action #>
        @action/readycheck <action #>
        @action/submit <action #>
    Options:
        @action [<action #>]
        @action/invite <action #>=<character>[,<character2>,...]
        @action/setaction <action #>=<action text>
        @action/setsecret[/traitor] <action #>=<secret action>
        @action/setcrisis <action #>=<crisis #>
        @action/add <action#>=<type>,<amount or object ID#>[,notes]
        @action/makepublic <action #>
        @action/toggletraitor <action #>
        @action/toggleattend <action #>
        @action/noscene <action #>
        @action/org <action #>=<org name>
        @action/plot <action #>=<plot #>

    Creating /newaction costs Action Points (ap). Requires 'tldr' which is a
    short summary in a few words of the action, a category, stat/skill for
    the dice check (just pick whatever might be plausible, GMs can adjust it
    if they disagree), and /ooc_intent which is the what sort of outcome you
    are hoping for, whether that's reputation adjustments, some advancement
    in a story, the favor of important npcs, magical power, whatever. It's just
    to make sure that GMs know what you have in mind for what you're trying
    to accomplish. Use /submit after all options, when ready for GM review. GMs
    may require more info or ask you to edit with /setaction and /submit again.
    Categories: combat, scouting, support, diplomacy, sabotage, research.

    With /invite you ask others to assist your action. They use /setaction or
    /cancel, and require all the same fields except category. A covert action
    can be added with /setsecret. Optional /traitor (and /toggletraitor) switch
    makes your dice roll detract from goal. With /setcrisis this becomes your
    response to a Crisis. Allocate resources with /add by specifying a type
    (ap, army, social, silver, etc.) and amount, or the ID# of your army. The
    /makepublic switch allows everyone to see your action after a GM publishes
    an outcome. If you prefer offscreen resolution, use /noscene toggle. To
    ask questions for GMs, use /question.

    Using /toggleattend switches whether your character is physically present,
    or arranging for the action's occurance in other ways. One action may be
    attended per crisis update; all others must be passive to represent
    simultaneous response by everyone involved. Up to 5 attendees are allowed
    per crisis response action, unless it is /noscene.

    Actions are private by default, but there's a small xp reward for marking
    a completed action as public with the /makepublic switch.

    The /add switch allows you to add something to an action to satisfy a
    requirement that a GM has specified must be met before the action can
    be resolved. The 'type' argument can be one of the following: silver,
    economic, military, ap, clue, revelation, spell, skillnode, item, army,
    or rfr. You then specify either the amount of resource to add or the ID
    of the entity required which your character has access to.

    A player is permitted one personal action per episode (not one per
    character), and orgs separately are allowed one crisis action per
    episode.
    """

    key = "@action"
    locks = "cmd:all()"
    help_category = "Story"
    help_entry_tags = ["actions"]
    aliases = ["@actions", "+storyrequest"]
    action_categories = dict_from_choices_field(PlotAction, "CATEGORY_CHOICES")
    requires_draft_switches = ("invite", "setcrisis", "readycheck")
    requires_editable_switches = (
        "roll",
        "tldr",
        "title",
        "category",
        "submit",
        "invite",
        "setaction",
        "setcrisis",
        "add",
        "toggletraitor",
        "toggleattend",
        "ooc_intent",
        "setsecret",
        "org",
        "plot",
    )
    requires_unpublished_switches = ("question", "cancel", "noscene")
    requires_owner_switches = (
        "invite",
        "makepublic",
        "category",
        "setcrisis",
        "noscene",
        "readycheck",
    )

    @property
    def dompc(self):
        """Shortcut for getting their dominion playerornpc object"""
        return self.caller.Dominion

    @property
    def actions_and_invites(self):
        """Lists non-cancelled actions for creator and those invited to it"""
        return (
            PlotAction.objects.filter(Q(dompc=self.dompc) | Q(assistants=self.dompc))
            .exclude(status=PlotAction.CANCELLED)
            .distinct()
        )

    def func(self):
        """Executes @action command"""
        try:
            if not self.args and not self.switches:
                return self.list_actions()
            if "newaction" in self.switches:
                return self.new_action()
            action = self.get_action(self.lhs)
            if not action:
                return
            if not self.switches:
                return self.view_action(action)
            if not self.check_valid_switch_for_action_type(action):
                return
            if "makepublic" in self.switches:
                return self.make_public(action)
            if "question" in self.switches:
                return self.ask_question(action)
            if self.check_switches(self.requires_draft_switches):
                return self.do_requires_draft_switches(action)
            if self.check_switches(self.requires_editable_switches):
                # PS - NV is fucking amazing
                return self.do_requires_editable_switches(action)
            if self.check_switches(self.requires_unpublished_switches):
                return self.do_requires_unpublished_switches(action)
            else:
                self.msg("Invalid switch. See 'help @action'.")
        except self.error_class as err:
            self.msg(err)

    def check_valid_switch_for_action_type(self, action):
        """
        Checks if the specified switches require the main action, and if so, whether our action is the main action.

            Args:
                action (PlotAction or PlotActionAssistant): action or assisting action

            Returns:
                True or False for whether we're okay to proceed.
        """
        if not (set(self.switches) & set(self.requires_owner_switches)):
            return True
        if action.is_main_action:
            return True
        self.msg("Only the action leader can use that switch.")
        return False

    def make_public(self, action):
        """Makes an action public knowledge"""
        try:
            action.make_public()
        except ActionSubmissionError as err:
            self.msg(err)

    def do_requires_draft_switches(self, action):
        """Executes switches that require the action to be in Draft status"""
        if not action.status == PlotAction.DRAFT:
            return self.send_too_late_msg()
        elif "invite" in self.switches:
            return self.invite_assistant(action)
        elif "setcrisis" in self.switches or "plot" in self.switches:
            return self.set_crisis(action)
        elif "readycheck" in self.switches:
            return self.ready_check(action)

    def do_requires_editable_switches(self, action):
        """Executes switches that requires the action to be in an editable state"""
        if not action.editable and not action.main_action.editable:
            return self.send_no_edits_msg()
        if "roll" in self.switches:
            return self.set_roll(action)
        if "tldr" in self.switches or "title" in self.switches:
            return self.set_topic(action)
        elif "category" in self.switches:
            return self.set_category(action)
        elif "submit" in self.switches:
            return self.submit_action(action)
        elif "setaction" in self.switches:
            return self.set_action(action)
        elif "org" in self.switches:
            return self.set_org(action)
        elif "add" in self.switches:
            return self.add_required_value(action)
        elif "toggletraitor" in self.switches:
            return self.toggle_traitor(action)
        elif "toggleattend" in self.switches:
            return self.toggle_attend(action)
        elif "ooc_intent" in self.switches:
            return self.set_ooc_intent(action)
        elif "setsecret" in self.switches:
            return self.set_secret_action(action)

    def do_requires_unpublished_switches(self, action):
        """Executes switches that require the action to not be Published"""
        if action.status in (PlotAction.PUBLISHED, PlotAction.PENDING_PUBLISH):
            return self.send_no_edits_msg()
        elif "cancel" in self.switches:
            return self.cancel_action(action)
        elif "noscene" in self.switches:
            return self.toggle_noscene(action)

    def send_no_edits_msg(self):
        """Tells the caller they can't edit the action."""
        self.msg("You cannot edit that action at this time.")

    def send_too_late_msg(self):
        """Tells the caller that they could only do that in Draft mode"""
        self.msg("Can only be done while the action is in Draft status.")

    def list_actions(self):
        """Prints a table of the actions we've taken"""
        table = EvTable("ID", "Crisis", "Date", "Owner", "Status")
        actions = self.actions_and_invites
        attending = list(
            actions.filter(
                Q(dompc=self.dompc, attending=True)
                | Q(
                    assisting_actions__dompc=self.dompc,
                    assisting_actions__attending=True,
                )
            )
        )
        for action in actions:
            date = "--"
            if action.date_submitted:
                date = action.date_submitted.strftime("%x")

            def color_unsubmitted(string):
                """Colors the status display for assisting actions of the player that aren't ready to submit"""
                if (
                    action.status == PlotAction.DRAFT
                    and action.check_unready_assistant(self.dompc)
                ):
                    return "|r%s|n" % string
                return string

            is_attending = action in attending
            id_str = "{w*%s{n" % action.id if is_attending else str(action.id)
            table.add_row(
                id_str,
                str(action.plot)[:20],
                date,
                str(action.dompc),
                color_unsubmitted(action.get_status_display()),
            )
        msg = "\nActions you're attending will be highlighted with {w*{n."
        self.msg(str(table) + msg)

    def send_no_args_msg(self, noun):
        """Sends failure message about what they're missing."""
        if not noun:
            noun = "args"
        self.msg("You need to include %s." % noun)

    def new_action(self):
        """Create a new action."""
        if not self.args:
            return self.send_no_args_msg("a story")
        crisis = None
        crisis_msg = ""
        actions = self.lhs
        if self.rhs:
            crisis = self.get_valid_crisis(self.lhs)
            actions = self.rhs
            crisis_msg = " to respond to %s" % str(crisis)
            if not crisis:
                return
        if not self.can_create(crisis):
            return
        action = self.dompc.actions.create(
            actions=actions, plot=crisis, stat_used="", skill_used=""
        )
        self.msg(
            "You have drafted a new action {w(#%s){n%s: %s"
            % (action.id, crisis_msg, actions)
        )
        self.msg(
            "Please note that you cannot invite players to an action once it is submitted."
        )

    def get_action(self, arg):
        """Returns an action we are involved in from ID# args.

        Args:
            arg (str): String to use to find the ID of the crisis action.

        Returns:
            A CrisisAction or a CrisisActionAssistant depending if the caller is the owner of the main action or
            an assistant.
        """
        try:
            dompc = self.dompc
            action = self.actions_and_invites.get(id=arg)
            try:
                action = action.assisting_actions.get(dompc=dompc)
            except PlotActionAssistant.DoesNotExist:
                pass
            return action
        except (PlotAction.DoesNotExist, ValueError):
            self.msg("No action found by that ID.")
            self.list_actions()

    def get_my_actions(self, crisis=False, assists=False):
        """Returns caller's actions."""
        dompc = self.dompc
        if not assists:
            actions = dompc.actions.all()
        else:
            actions = PlotAction.objects.filter(
                Q(dompc=dompc) | Q(assistants=dompc)
            ).distinct()
        if not crisis:
            actions = actions.filter(plot__isnull=True)
        return actions

    def get_valid_crisis(self, name_or_id):
        """Gets crisis they can participate in that matches name or ID"""
        try:
            qs = Plot.objects.viewable_by_player(self.caller)
            if name_or_id.isdigit():
                return qs.get(id=name_or_id)
            return qs.get(name__iexact=name_or_id)
        except Plot.DoesNotExist:
            self.msg("No crisis/plot found by that name or ID.")

    def can_create(self, crisis=None):
        """Checks criteria for creating a new action."""
        if crisis and not self.can_set_crisis(crisis):
            return False
        my_draft = self.get_my_actions().filter(status=PlotAction.DRAFT).last()
        if my_draft:
            self.msg(
                "You have drafted an action which needs to be submitted or canceled: %s"
                % my_draft.id
            )
            return False
        if not self.caller.pay_action_points(PlotAction.BASE_AP_COST):
            self.msg("You do not have enough action points.")
            return False
        return True

    def can_set_crisis(self, crisis):
        """Checks criteria for linking to a Crisis."""
        try:
            crisis.raise_creation_errors(self.dompc)
        except ActionSubmissionError as err:
            self.msg(err)
            return False
        return True

    def set_category(self, action):
        """Sets the category for an action"""
        if not action.is_main_action:
            self.msg("Only the main action has a category.")
            return
        if not self.rhs:
            return self.send_no_args_msg("a category")
        category_names = self.action_categories.keys()
        if self.rhs not in category_names:
            category_names = sorted(set(ob.lower() for ob in category_names))
            self.send_no_args_msg(
                "one of these categories: %s" % ", ".join(category_names)
            )
            return
        self.set_action_field(action, "category", self.action_categories[self.rhs])

    def set_roll(self, action):
        """Sets a stat and skill for action or assistant"""

        try:
            stat, skill = self.rhslist
            stat = stat.lower()
            skill = skill.lower()
        except (ValueError, TypeError, AttributeError):
            self.msg("Usage: @action/roll <action #>=<stat>,<skill>")
            return
        if (
            stat not in Trait.get_valid_stat_names()
            or skill not in Trait.get_valid_skill_names()
        ):
            self.msg("You must provide a valid stat and skill.")
            return
        field_name = "stat_used"
        self.set_action_field(action, field_name, stat, verbose_name="stat")
        field_name = "skill_used"
        return self.set_action_field(action, field_name, skill, verbose_name="skill")

    def add_required_value(self, action):
        """Adds a resource based on arguments"""
        if len(self.rhslist) < 2:
            self.send_no_args_msg(
                "a resource type such as 'economic' or 'ap' and the amount."
                " Or 'army' and an army ID#"
            )
            return
        try:
            r_type = self.rhslist[0].lower()
            value = self.rhslist[1]
        except (IndexError, ValueError, TypeError, AttributeError):
            self.msg("Must have a resource type and value.")
            return
        explanation = ""
        if r_type == "clue":
            value = self.get_by_name_or_id(
                Clue, value, filter_kwargs={"characters": self.caller.roster}
            )
        if r_type == "revelation":
            value = self.get_by_name_or_id(
                Revelation, value, filter_kwargs={"characters": self.caller.roster}
            )
        if r_type == "spell":
            value = self.get_by_name_or_id(
                Spell,
                value,
                filter_kwargs={"practitioner__character": self.caller.char_ob},
            )
        if r_type == "skillnode":
            value = self.get_by_name_or_id(
                SkillNode,
                value,
                filter_kwargs={
                    "known_by__practitioner__character": self.caller.char_ob
                },
            )
        if r_type == "item":
            value = self.caller.char_ob.search(value)
            if not value:
                return
        if r_type == "rfr":
            value = self.get_by_name_or_id(PlotUpdate, value)
            try:
                explanation = self.rhslist[2]
            except IndexError:
                self.fail(
                    "You must provide an explanation of why the RFR is relevant for this requirement."
                )
        try:
            action.add_required_resource(r_type, value, explanation)
        except ActionSubmissionError as err:
            self.msg(err)
        else:
            if r_type == "army":
                self.msg("You have successfully relayed new orders to that army.")
                return
            else:
                totals = action.view_total_requirements_msg()
                self.msg(
                    "{c%s{n %s added. {wAction #%d %s"
                    % (value, r_type, action.main_action.id, totals)
                )

    def set_topic(self, action):
        """Sets the topic for an action"""
        if not self.rhs:
            return self.send_no_args_msg("a title")
        if len(self.rhs) > 80:
            self.send_no_args_msg("a shorter title; aim for under 80 characters")
            return
        return self.set_action_field(action, "topic", self.rhs)

    def set_ooc_intent(self, action):
        """
        Sets our ooc intent, or if we're already submitted and have an intent set, it asks a question.
        """
        if not self.rhs:
            self.msg("You must enter a message.")
            return
        action.set_ooc_intent(self.rhs)
        self.msg("You have set your ooc intent to be: %s" % self.rhs)

    def ask_question(self, action):
        """Submits an OOC question for an action"""
        if not self.rhs:
            self.msg("You must enter text for your question.")
            return
        action.ask_question(self.rhs)
        self.msg("You have submitted a question: %s" % self.rhs)

    def cancel_action(self, action):
        """Cancels the action"""
        action.cancel()
        self.msg("Action cancelled.")

    def submit_action(self, action):
        """I love a bishi. He too will submit."""
        try:
            action.submit()
        except ActionSubmissionError as err:
            self.msg(err)
        else:
            self.msg("You have submitted your action.")

    def toggle_noscene(self, action):
        """Toggles whether they prefer the action get offscreen resolution"""
        action.prefer_offscreen = not action.prefer_offscreen
        action.save()
        color = "{r" if action.prefer_offscreen else "{w"
        self.msg(
            "Preference for offscreen resolution set to: %s%s"
            % (color, action.prefer_offscreen)
        )

    def toggle_traitor(self, action):
        """Toggles whether they're working against the main action/crisis"""
        action.traitor = not action.traitor
        color = "{r" if action.traitor else "{w"
        action.save()
        self.msg("Traitor is now set to: %s%s{n" % (color, action.traitor))

    def set_action(self, action):
        """Sets the main story of what they're doing in the action"""
        if not self.rhs:
            return self.send_no_args_msg("a story")
        if not action.is_main_action:
            try:
                action.set_action(self.rhs)
            except ActionSubmissionError as err:
                self.msg(err)
                return
            else:
                self.msg(
                    "%s now has your assistance: %s" % (action.plot_action, self.rhs)
                )
        else:
            self.set_action_field(action, "actions", self.rhs)
        if action.plot:
            self.do_passive_warnings(action)

    def set_secret_action(self, action):
        """Sets a secret story of what they're doing in the action"""
        if not self.rhs:
            return self.send_no_args_msg("a story of your secret actions")
        self.set_action_field(
            action, "secret_actions", self.rhs, verbose_name="Secret actions"
        )

    def warn_crisis_overcrowd(self, action):
        """Warns that too many people are attending"""
        try:
            action.check_plot_overcrowd()
        except ActionSubmissionError as err:
            self.msg("{yWarning:{n %s" % err)

    def do_passive_warnings(self, action):
        """Delivers warnings of what would make submission fail"""
        if not action.prefer_offscreen:
            self.warn_crisis_overcrowd(action)

    def set_crisis(self, action):
        """Sets the crisis for the action"""
        noun = "plot" if "plot" in self.switches else "crisis"
        if not self.rhs:
            action.plot = None
            action.save()
            self.msg(f"Your action no longer targets any {noun}.")
            return
        crisis = self.get_valid_crisis(self.rhs)
        if not crisis:
            return
        if not self.can_set_crisis(crisis):
            return
        action.plot = crisis
        action.save()
        self.msg(f"You have set the action to be for {noun}: %s" % crisis)
        self.do_passive_warnings(action)

    def ready_check(self, action):
        """Checks whether assistants are ready for the player"""
        unready = action.get_unready_assisting_actions()
        if not unready:
            self.msg("All invited assistants are currently ready.")
        else:
            self.msg(
                "The following assistants aren't ready: %s"
                % ", ".join(str(ob.author) for ob in unready)
            )

    def toggle_attend(self, action):
        """Toggles whether they're attending the action in-person, onscreen"""
        if action.attending:
            action.attending = False
            action.save()
            self.msg("You are marked as no longer attending the action.")
            return
        try:
            action.mark_attending()
        except ActionSubmissionError as err:
            self.msg(err)
            return
        self.msg(
            "You have marked yourself as physically being present for that action."
        )

    def set_org(self, action):
        access_type = "crisis"
        try:
            org = Organization.objects.get(name__iexact=self.rhs)
        except Organization.DoesNotExist:
            raise self.error_class(f"No org by the name '{self.rhs}'")
        if access_type not in org.locks.locks.keys():
            org.locks.add("%s:rank(%s)" % (access_type, 2))
            org.save()
        if not org.access(self.caller, "crisis"):
            raise self.error_class(
                f"You do not have permission to start an action for {org}."
            )
        if action.plot.usage != action.plot.CRISIS:
            raise self.error_class("Orgs may only be assigned to crisis actions.")
        action.org = org
        action.save()
        self.msg(
            f"You have set {org} to be the org for this crisis action. Orgs can only respond to one crisis per episode."
        )


class CmdGMAction(ActionCommandMixin, ArxPlayerCommand):
    """
    Allows you to resolve character actions for GMing

    Usage:
        Commands for viewing actions:
        @gm [<action #> or <character or alias> or <crisis name> or <gm name>]
        @gm/mine
        @gm/old
        @gm[/needgm, /needplayer, /cancelled, /pending, /draft, /everyone]
        @gm/search <search term>

        Commands for modifying an action stats or results:
        @gm/story <action #>=<the IC result of their action, told as a story>
        @gm/secretstory <action #>=<the IC result of their secret actions>
        @gm/check <action #>
        @gm/stat <action #>[,assistant name]=<stat>
        @gm/skill <action #>[,assistant name]=<skill>
        @gm/diff <action #>=<rank # or daunting | hard | normal | easy>

        Commands for answering questions or requiring player response:
        @gm/ooc[/allowedit] <action #>[,assistant name]=<answer to OOC question>
        @gm/markanswered <action #>

        Commands for action administration:
        @gm/publish <action #>[=<story>]
        @gm/markpending <action #>
        @gm/cancel <action #>
        @gm/assign <action #>=<gm>
        @gm/gemit <action #>[,<action #>,...]=<text to post>[/<new episode name>]
        @gm/allowedit <action #>[,assistant name]
        @gm/togglefree <action #>[,assistant name]
        @gm/invite <action #>=<player to add as assistant>[,player2,...]
        @gm/addrequirement
           .../resources <action #>=<resource type>,<amount>[,max weekly rate]
           .../clue <action #>=<clue ID>
           .../revelation <action #>=<revelation ID>
           .../skillnode <action #>=<skill node ID>
           .../spell <action #>=<spell ID>
           .../item <action #>=<item ID>
           .../forces <action #>=<Description of required force>
           .../event <action #>=<Text description of what needs to happen>

    Commands for GMing. @actions can be claimed/assigned to GMs with the /assign
    switch, and then viewed with @gm/mine. Actions are initially in a draft state
    when players are still in the process of creating them, then are put in the
    /needgm status when they want a GM response. Players have to mark themselves
    as physically attending an action if they're there in person, and they're
    only allowed to be physically present for one crisis action per update.

    If you think players need to change something, or want to answer a question,
    use the /ooc switch. /allowedit will mark them in a state where the player
    can change their action/assist, and then they can submit changes again when
    done. /check rolls for the action and records the outcome. For adding a
    requirement that must be satisfied before the action can be resolved, use
    /addrequirement switch. This allows you to specify needing some concrete
    value or knowledge required for success, or you can specify an event
    which can be anything that they submit is satisfied by an RPEvent,
    Goal review, another action, etc.

    The result of the action is the /story and optional /secretstory. A
    response may only be written for the main action - players who want an
    individual response should create their own action.

    When done, actions can either be marked as waiting publish for a later date
    with /markpending, or published immediately with /publish. /gemit
    will publish the actions, make a gemit, and post on the story board. To
    make a crisis update, use @gmcrisis/update - this will make a new gemit and
    associate all published/pending publish action with the update, allowing
    players to then create a new crisis action if the crisis is not resolved and
    a new date is set.
    """

    key = "@gm"
    locks = "cmd:perm(builders)"
    help_category = "GMing"
    list_switches = (
        "old",
        "pending",
        "draft",
        "cancelled",
        "needgm",
        "needplayer",
        "search",
    )
    gming_switches = (
        "story",
        "secretstory",
        "check",
        "stat",
        "skill",
        "diff",
    )
    followup_switches = ("ooc", "markanswered")
    admin_switches = (
        "publish",
        "markpending",
        "cancel",
        "assign",
        "gemit",
        "allowedit",
        "invite",
        "togglefree",
        "addrequirement",
    )
    difficulties = {
        "easy": PlotAction.EASY_DIFFICULTY,
        "normal": PlotAction.NORMAL_DIFFICULTY,
        "hard": PlotAction.HARD_DIFFICULTY,
        "daunting": PlotAction.DAUNTING_DIFFICULTY,
    }

    def func(self):
        """Executes the @gm command"""
        try:
            if not self.args or (
                (not self.switches or self.check_switches(self.list_switches))
                and not self.args.isdigit()
            ):
                return self.list_actions()
            try:
                action = PlotAction.objects.get(id=self.lhslist[0])
            except (PlotAction.DoesNotExist, ValueError):
                self.msg("No action by that ID #.")
                return
            if "tldr" in self.switches:
                return self.msg(action.view_tldr())
            if not self.switches or self.check_switches(self.list_switches):
                return self.view_action(action, disp_old=True)
            if self.check_switches(self.gming_switches):
                return self.do_gming(action)
            if self.check_switches(self.followup_switches):
                return self.do_followup(action)
            if self.check_switches(self.admin_switches):
                return self.do_admin(action)
        except (self.error_class, ActionSubmissionError) as err:
            return self.msg(err)
        self.msg("Invalid switch.")

    def list_actions(self):
        """Lists the actions for the matching queryset"""
        qs = self.get_queryset_from_switches()
        table = EvTable(
            "{wID", "{wplayer", "{wtldr", "{wdate", "{wcrisis", width=78, border="cells"
        )
        for action in qs:
            if action.unanswered_questions:
                action_id = "{c*%s{n" % action.id
            else:
                action_id = action.id
            date = (
                action.date_submitted.strftime("%m/%d")
                if action.date_submitted
                else "----"
            )
            table.add_row(action_id, action.dompc, action.topic, date, action.plot)
        table.reformat_column(0, width=9)
        table.reformat_column(1, width=10)
        table.reformat_column(2, width=37)
        table.reformat_column(3, width=8)
        table.reformat_column(4, width=14)
        arx_more.msg(self.caller, str(table), justify_kwargs=False, pages_by_char=True)

    def get_queryset_from_switches(self):
        """Filters the queryset of actions based on given options from switches/args"""
        old_status = PlotAction.PUBLISHED
        draft_status = PlotAction.DRAFT
        cancelled_status = PlotAction.CANCELLED
        pending_status = PlotAction.PENDING_PUBLISH
        qs = PlotAction.objects.all()
        if "old" in self.switches:
            qs = qs.filter(status=old_status)
        elif "draft" in self.switches:
            qs = qs.filter(status=draft_status)
        elif "needgm" in self.switches:
            qs = qs.filter(status=PlotAction.NEEDS_GM)
        elif "needplayer" in self.switches:
            qs = qs.filter(status=PlotAction.NEEDS_PLAYER)
        elif "pending" in self.switches:
            qs = qs.filter(status=pending_status)
        elif "cancelled" in self.switches:
            qs = qs.filter(status=cancelled_status)
        elif "search" in self.switches:
            qs = qs.filter(
                Q(story__icontains=self.args)
                | Q(actions__icontains=self.args)
                | Q(secret_actions__icontains=self.args)
                | Q(assisting_actions__actions__icontains=self.args)
                | Q(assisting_actions__secret_actions__icontains=self.args)
            )
        else:
            unanswered_questions = ActionOOCQuestion.objects.filter(
                answers__isnull=True, mark_answered=False
            ).exclude(is_intent=True)
            qs = qs.filter(
                Q(questions__in=unanswered_questions)
                | ~Q(
                    status__in=(
                        old_status,
                        draft_status,
                        cancelled_status,
                        pending_status,
                    )
                )
            )
        if "mine" in self.switches:
            qs = qs.filter(gm=self.caller)
        elif not self.args and "everyone" not in self.switches:
            qs = qs.filter(gm__isnull=True)
        if self.args and "search" not in self.switches:
            name = self.args
            qs = qs.filter(
                Q(plot__name__iexact=name)
                | Q(dompc__player__username__iexact=name)
                | Q(category__iexact=name)
                | Q(assistants__player__username__iexact=name)
                | Q(gm__username__iexact=name)
            )
        return qs.distinct().order_by("date_submitted")

    def do_gming(self, action):
        """Do changes to the action that are based on GMing it"""
        if "story" in self.switches:
            return self.set_action_field(action, "story", self.rhs)
        if "secretstory" in self.switches:
            return self.set_action_field(action, "secret_story", self.rhs)
        if "check" in self.switches:
            return self.do_checks(action)
        if "diff" in self.switches:
            return self.set_difficulty(action)
        if len(self.lhslist) > 1:
            action = self.replace_action_with_assistant_if_provided(action)
            if not action:
                return
        if "stat" in self.switches:
            return self.set_action_field(action, "stat", self.rhs)
        if "skill" in self.switches:
            return self.set_action_field(action, "skill", self.rhs)

    def do_checks(self, action):
        """Make rolls for the action"""
        outcome = action.roll_all()
        self.msg("The new outcome for the action is: %s" % outcome)

    def set_difficulty(self, action):
        """Sets difficulty of rolls forthe action"""
        if self.rhs in self.difficulties:
            value = self.difficulties[self.rhs]
        else:
            try:
                value = int(self.rhs)
            except (TypeError, ValueError):
                self.msg(
                    "Difficulty must be a number or %s."
                    % ", ".join(self.difficulties.keys())
                )
                return
        try:
            rank = CheckRank.objects.get(id=value)
        except CheckRank.DoesNotExist:
            raise self.error_class("That is not a valid Check Rank id.")
        self.set_action_field(action, "target_rank", rank)

    def replace_action_with_assistant_if_provided(self, action, name=None):
        """Gets an assisting action instead"""
        if not name:
            try:
                name = self.lhslist[1]
            except IndexError:
                return action
        if action.dompc.player.username.lower() == name.lower():
            return action
        try:
            return action.assisting_actions.get(dompc__player__username__iexact=name)
        except PlotActionAssistant.DoesNotExist:
            self.msg("No assistant by that name.")

    def do_followup(self, action):
        """Follows up on an OOC question"""
        action = self.replace_action_with_assistant_if_provided(action)
        if not action:
            return
        if "markanswered" in self.switches:
            return self.mark_answered(action)
        if "allowedit" in self.switches:
            self.set_action_field(action, "editable", True)
        if not self.rhs:
            self.msg(action.display_followups())
        else:
            action.add_answer(gm=self.caller, text=self.rhs)
            self.msg("Answer added.")

    def mark_answered(self, action):
        """Marks a question as answered"""
        action.mark_answered(gm=self.caller)
        self.msg("You have marked the questions as answered.")

    def do_admin(self, action):
        """Do various administrative tasks for an action"""
        if "publish" in self.switches:
            return self.publish_action(action)
        if "markpending" in self.switches:
            return self.set_action_field(action, "status", PlotAction.PENDING_PUBLISH)
        if "cancel" in self.switches:
            return self.cancel_action(action)
        if "assign" in self.switches:
            return self.assign_action(action)
        if "gemit" in self.switches:
            return self.do_gemit_for_action(action)
        if "allowedit" in self.switches:
            return self.toggle_editable(action)
        if "togglefree" in self.switches:
            return self.toggle_free(action)
        if "invite" in self.switches:
            return self.invite_assistant(action)
        if "addrequirement" in self.switches:
            return self.add_requirement(action)

    def publish_action(self, action):
        """Publishes an action, marking it as resolved and telling players the outcome"""
        if self.rhs:
            if action.story:
                self.msg(
                    "That story already has an action written. To prevent accidental overwrites, please change "
                    "it manually and then /publish without additional arguments."
                )
                return
            action.story = self.rhs
            action.save()
        action.send(caller=self.caller)
        self.msg("You have published the action and sent the players informs.")

    def cancel_action(self, action):
        """Cancels an action, refunding players and marking it as cancelled"""
        action.cancel()
        self.msg("Action cancelled.")

    def assign_action(self, action):
        """Assigns an action to a GM"""
        player = None
        if self.rhs:
            player = self.caller.search(self.rhs)
            if not player:
                return
        self.set_action_field(action, "gm", player)
        self.msg("GM for the action set to %s" % player)

    def do_gemit_for_action(self, action):
        """Makes a gemit(game announcement) for a given action"""
        from server.utils.arx_utils import create_gemit_and_post

        actions = [action]
        for id_num in self.lhslist[1:]:
            try:
                another_action = PlotAction.objects.get(id=id_num)
            except (PlotAction.DoesNotExist, ValueError, TypeError):
                self.msg("Invalid ID.")
                return
            else:
                actions.append(another_action)
        rhslist = self.rhs.split("/")
        msg = rhslist[0]
        episode_name = None
        if len(rhslist) > 1:
            episode_name = rhslist[1]
        gemit = create_gemit_and_post(msg, self.caller, episode_name)
        for action_object in actions:
            action_object.gemit = gemit
            action_object.send(caller=self.caller)
        self.msg("StoryEmit created.")

    def toggle_editable(self, action):
        """Toggles whether an action is editable or not"""
        action = self.replace_action_with_assistant_if_provided(action)
        if not action:
            return
        action.editable = not action.editable
        action.save()
        if action.editable:
            action.inform("Your action is now editable and changes are required.")
            self.msg(
                "You have made their action editable and the player has been informed."
            )
        else:
            self.msg("Their action is no longer editable.")

    def toggle_free(self, action):
        """Toggles whether an action is free or not"""
        action = self.replace_action_with_assistant_if_provided(action)
        if not action:
            return
        action.free_action = not action.free_action
        action.save()
        if action.free_action:
            action.inform(
                "Your action is now a free action and will not count towards your maximum."
            )
            self.msg(
                "You have made their action free and the player has been informed."
            )
        else:
            self.msg("Their action is no longer free.")

    def add_requirement(self, action: PlotAction):
        """Adds a requirement to an action"""
        if not self.rhs:
            self.fail("Must specify an argument.")
        max_rate = 0
        value = self.rhs
        if "resources" in self.switches:
            if len(self.rhslist) < 2:
                self.fail("Must specify at least a resource type and value.")
            try:
                r_type, value = self.rhslist[0], int(self.rhslist[1])
                if value < 1:
                    raise ValueError
                if len(self.rhslist) > 2:
                    max_rate = int(self.rhslist[2])
                    if max_rate < 1:
                        raise ValueError
            except (TypeError, ValueError):
                self.fail("Value must be a positive number.")
            try:
                requirement_type = ActionRequirement.get_choice_constant_from_string(
                    r_type
                )
            except KeyError:
                self.fail("Must be a valid resource type")
        elif "clue" in self.switches:
            value = self.get_by_name_or_id(Clue, self.rhs)
            requirement_type = ActionRequirement.CLUE
        elif "revelation" in self.switches:
            value = self.get_by_name_or_id(Revelation, self.rhs)
            requirement_type = ActionRequirement.REVELATION
        elif "item" in self.switches:
            value = self.get_by_name_or_id(ObjectDB, self.rhs, field_name="db_key")
            requirement_type = ActionRequirement.ITEM
        elif "spell" in self.switches:
            value = self.get_by_name_or_id(Spell, self.rhs)
            requirement_type = ActionRequirement.SPELL
        elif "skillnode" in self.switches or "skill_node" in self.switches:
            value = self.get_by_name_or_id(SkillNode, self.rhs)
            requirement_type = ActionRequirement.SKILL_NODE
        elif "event" in self.switches:
            requirement_type = ActionRequirement.EVENT
        elif "forces" in self.switches or "army" in self.switches:
            requirement_type = ActionRequirement.FORCES
        else:
            self.fail("That is not a recognized requirement type.")

        req = action.add_action_requirement(requirement_type, value, max_rate)
        self.msg(f"You have added a requirement: {req.display_action_requirement()}")
