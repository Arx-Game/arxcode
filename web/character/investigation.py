"""
Commands for the 'Character' app that handles the roster,
stories, the timeline, etc.
"""
from datetime import datetime

from django.db.models import Q

from evennia.utils.evtable import EvTable
from evennia.server.models import ServerConfig
from server.utils.arx_utils import inform_staff, check_break, list_to_string
from commands.base import ArxCommand, ArxPlayerCommand
from commands.mixins import FormCommandMixin
from server.utils.exceptions import CommandError
from server.utils.prettytable import PrettyTable
from web.character.models import (Investigation, Clue, InvestigationAssistant, ClueDiscovery, Theory,
                                  RevelationDiscovery, Revelation, get_random_clue, SearchTag)
from web.character.forms import ClueCreateForm, RevelationCreateForm
from world.dominion.models import Agent
from world.dominion.plots.models import Plot
from world.stats_and_skills import VALID_STATS, VALID_SKILLS


class InvestigationFormCommand(ArxCommand):
    """
    ABC for creating commands based on investigations that process a form.
    """
    help_entry_tags = ["investigations"]
    form_verb = "Creating"
    form_switches = ("topic", "target", "tag", "tags", "story", "stat", "skill", "cancel", "finish")
    ap_cost = 10

    @property
    def new_clue_cost(self):
        """Fetch server config cost of investigating an unwritten clue."""
        return ServerConfig.objects.conf(key="NEW_CLUE_AP_COST") or 0

    def check_ap_cost(self, cost=None):
        if not cost:
            cost = self.ap_cost
            if cost < 0:
                cost = 0
        if self.caller.player_ob.pay_action_points(cost):
            return True
        else:
            self.msg("You cannot afford to do that action.")
            return False

    @property
    def form_attr(self):
        return "investigation_form"

    @property
    def investigation_form(self):
        return getattr(self.caller.ndb, self.form_attr)

    @investigation_form.setter
    def investigation_form(self, val):
        setattr(self.caller.ndb, self.form_attr, val)

    @investigation_form.deleter
    def investigation_form(self):
        self.caller.nattributes.remove(self.form_attr)

    @property
    def related_manager(self):
        return self.caller.roster.investigations

    def disp_investigation_form(self):
        form = self.investigation_form
        if not form:
            return
        story, stat, skill = form[1], form[2], form[3]
        msg = "|w%s an investigation:|n %s" % (self.form_verb, self.topic_string(color=True))
        msg += self.display_target_string()
        msg += "\n%s" % (story or "Story unfinished.")
        msg += "\n|wStat:|n %s - |wSkill:|n %s" % (stat or "???", skill or "???")
        self.msg(msg)

    def display_target_string(self):
        return "\n|w%s:|n %s" % (self.target_type.capitalize(), self.investigation_form[0])

    def topic_string(self, color=False):
        """Joins tag-requirements and tag-omissions into a string"""
        source_clue = self.investigation_form[6]
        if source_clue:
            return str(source_clue)
        tags_list = self.investigation_form[5]
        if not tags_list:
            return ""

        def colorize(val, col=None):
            if not color:
                return str(val)
            if not col:
                col = "|r-"
            return "%s%s|n" % (col, val)

        topic = "; ".join(colorize(ob, col="|235") for ob in tags_list[0])
        if tags_list[1]:
            topic += "; "
            topic += "; ".join(colorize(ob) for ob in tags_list[1])
        return topic

    @property
    def target_type(self):
        return "topic"

    @property
    def finished_form(self):
        """Property that validates the form that has been created."""
        try:
            form = self.investigation_form
            topic, story, stat, skill = form[0], form[1], form[2], form[3]
            if not topic:
                self.msg("You must have %s defined." % self.target_type.lower())
                return
            if not story:
                self.msg("You must have a story defined.")
                return
            return topic, story, stat, skill
        except (TypeError, ValueError, IndexError, AttributeError):
            self.msg("Your investigation form is not yet filled out.")
            return False

    @property
    def start_cost(self):
        return 0

    def pay_costs(self):
        dompc = self.caller.player_ob.Dominion
        amt = dompc.assets.social
        amt -= self.start_cost
        if amt < 0:
            self.msg("It costs %s social resources to start a new investigation." % self.start_cost)
            return False
        if self.need_new_clue_written and not self.offer_placeholder_clue():
            return False
        self.msg("You spend %s social resources to start a new investigation." % self.start_cost)
        dompc.assets.social = amt
        dompc.assets.save()
        return True

    def refuse_new_clue(self, reason):
        self.msg("%s Try different tags or abort." % reason)

    def offer_placeholder_clue(self):
        """
        Allows investigator to request a newly written clue
        """
        ap = self.new_clue_cost
        topic = self.topic_string(color=True)
        prompt = ("An opportunity has arisen to pursue knowledge previously unseen by mortal eyes. "
                 "It will require a great deal of energy (|c%s|n action points) to investigate. "
                 "Your tag requirements: %s\n|yRepeat the command to confirm and continue.|n" % (ap, topic))
        if not self.confirm_command("new_clue_write", topic, prompt):
            return False
        if not self.caller.player.pay_action_points(ap):
            self.refuse_new_clue("You're too busy for such an investigation. (low AP)")
            return False
        return True

    def mark_active(self, created_object):
        """
        Finishes setting up the created object with any fields that need to be filled out,
        and informs the caller of what was done, as well as announces to staff. Saves the
        created object.
        """
        pass

    def create_obj_from_form(self, form):
        """
        Create a new object from our related manager with the form we were given
        from finished form, with appropriate kwargs
        """
        kwargs = {self.target_type: form[0], "actions": form[1], "stat_used": form[2], "skill_used": form[3]}
        return self.related_manager.create(**kwargs)

    def do_finish(self):
        """
        the finished_form property checks if all
        the fields are valid. Further checks on whether the fields can
        be used are done by pay_costs. The object to be created is then
        created using our related_manager property, and the target is
        populated with add_target_to_obj. It's then setup with mark_active
        """
        form = self.finished_form
        if not form:
            return
        if not self.check_enough_time_left():
            return
        if not self.pay_costs():
            return
        if self.check_too_busy_to_finish():
            return
        inv_ob = self.create_obj_from_form(form)
        if self.need_new_clue_written:
            form = self.investigation_form
            source_clue = form[6]
            clue_name = "PLACEHOLDER for Investigation #%s" % inv_ob.id
            if source_clue:
                gm_notes = "Trying to find things related to Clue #%s: %s" % (source_clue.id, source_clue)
                search_tags = list(source_clue.search_tags.all())
            else:
                search_tags, omit_tags = form[5]
                gm_notes = "Added tags: %s\n" % list_to_string(search_tags)
                if omit_tags:
                    gm_notes += "Exclude tags: %s" % list_to_string([("-%s" % ob) for ob in omit_tags])
            clue = Clue.objects.create(name=clue_name, gm_notes=gm_notes, allow_investigation=True, rating=30)
            for tag in search_tags:
                clue.search_tags.add(tag)
            inv_ob.clue_target = clue
            inv_ob.save()
        self.mark_active(inv_ob)
        del self.investigation_form

    def check_too_busy_to_finish(self):
        """Checks whether we're too busy to finish the form"""
        return

    @property
    def initial_form_values(self):
        return ['', '', '', '', '', [], None]

    # noinspection PyAttributeOutsideInit
    def create_form(self):
        """
        Initially populates the form we use. Other switches will populate
        the fields, which will be used in do_finish()
        """
        self.investigation_form = self.initial_form_values
        self.disp_investigation_form()

    def get_target(self):
        """Sets the target of the object we'll create."""
        self.disp_investigation_form()

    def check_skill(self):
        if self.args.lower() not in self.caller.db.skills:
            self.msg("You have no skill by the name of %s." % self.args)
            return
        return True

    @property
    def need_new_clue_written(self):
        return

    def func(self):
        """
        Base version of the command that can be inherited. It allows for creation of the form with
        the 'new' switch, is populated with 'target', 'story', 'stat', and 'skill', aborted with 'cancel',
        and finished with 'finish'.
        """
        investigation = self.investigation_form
        if "new" in self.switches:
            self.create_form()
            return True
        if self.check_switches(self.form_switches):
            if not investigation:
                self.msg("You need to create a form first with /new.")
                return True
            if self.check_switches(("target", "topic", "tag", "tags")):
                self.get_target()
                return True
            if "story" in self.switches:
                investigation[1] = self.args
                self.disp_investigation_form()
                return True
            if "stat" in self.switches:
                if not self.caller.attributes.get(self.args.lower()):
                    self.msg("No stat by the name of %s." % self.args)
                    return
                investigation[2] = self.args
                self.disp_investigation_form()
                return True
            if "skill" in self.switches:
                if not self.check_skill():
                    return
                investigation[3] = self.args
                self.disp_investigation_form()
                return True
            if "cancel" in self.switches:
                del self.investigation_form
                self.msg("Investigation creation cancelled.")
                return True
            if "finish" in self.switches:
                self.do_finish()
                return True

    def check_enough_time_left(self):
        """Returns True if they have enough time left to create/modify an investigation, False otherwise."""
        from evennia.scripts.models import ScriptDB
        from datetime import timedelta
        script = ScriptDB.objects.get(db_key="Weekly Update")
        day = timedelta(hours=24, minutes=5)
        if script.time_remaining < day:
            self.msg("It is too close to the end of the week to do that.")
            return False
        return True

    def check_is_ongoing(self, investigation):
        if not investigation.ongoing:
            self.msg("That investigation is not ongoing.")
        else:
            return True

    def caller_cannot_afford(self):
        self.msg("You must specify a positive amount that you can afford.")


class CmdAssistInvestigation(InvestigationFormCommand):
    """
    @helpinvestigate
    Usage:
        @helpinvestigate
        @helpinvestigate/history
        @helpinvestigate/new
        @helpinvestigate/retainer <retainer ID>
        @helpinvestigate/target <investigation ID #>
        @helpinvestigate/story <text of how you/your retainer help>
        @helpinvestigate/stat <stat to use for the check>
        @helpinvestigate/skill <additional skill besides investigation>
        @helpinvestigate/cancel
        @helpinvestigate/finish
        @helpinvestigate/stop
        @helpinvestigate/resume <id #>
        @helpinvestigate/changestory <id #>=<new story>
        @helpinvestigate/changestat <id #>=<new stat>
        @helpinvestigate/changeskill <id #>=<new skill>
        @helpinvestigate/actionpoints <id #>=<AP amount>
        @helpinvestigate/silver <id #>=<additional silver to spend>
        @helpinvestigate/resource <id #>=<resource type>,<amount>
        @helpinvestigate/retainer/stop <retainer ID>
        @helpinvestigate/retainer/resume <id #>=<retainer ID>
        @helpinvestigate/retainer/changestory <retainer ID>/<id #>=<story>
        @helpinvestigate/retainer/changestat <retainer ID>/<id #>=<stat>
        @helpinvestigate/retainer/changeskill <retainer ID>/<id #>=<skill>
        @helpinvestigate/retainer/silver, or /resource, etc., as above

    Helps with an investigation, or orders a retainer to help
    with the investigation. You may only help with one investigation
    at a time, and only if you are not actively investigating something
    yourself. You may stop helping an investigation with /stop, and
    resume it with /resume. To set a retainer to help the investigation,
    use the /retainer switch and supply their number. Entering an invalid
    retainer ID will switch back to you as being the investigation's helper.
    """
    key = "@helpinvestigate"
    aliases = ["+helpinvestigate", "helpinvestigate"]
    locks = "cmd:all()"
    help_category = "Investigation"
    form_verb = "Helping"
    change_switches = ("changestory", "changestat", "changeskill", "actionpoints", "silver", "resource", "resources")

    def pay_costs(self):
        """No resource cost for helping investigations"""
        return True

    @property
    def related_manager(self):
        return self.helper.assisted_investigations

    @property
    def form_attr(self):
        return "assist_investigation_form"

    @property
    def initial_form_values(self):
        return ['', '', '', '', self.caller, [], None]

    @property
    def helper(self):
        """Returns caller or their retainer who they are using in the investigation"""
        try:
            return self.investigation_form[4] or self.caller
        except IndexError:
            return self.caller

    def disp_investigation_form(self):
        super(CmdAssistInvestigation, self).disp_investigation_form()
        self.msg("{wAssisting Character:{n %s" % self.helper)

    def check_eligibility(self, helper):
        helping = helper.assisted_investigations.filter(currently_helping=True)
        if helping:
            self.msg("%s is already helping an investigation: %s" % (helper, ", ".join(str(ob.investigation.id)
                                                                                       for ob in helping)))
            return False
        formid = self.investigation_form[0]
        if helper == self.caller:
            try:
                if self.caller.roster.investigations.filter(active=True):
                    self.msg("You cannot assist an investigation while having an active investigation.")
                    return False
                if self.caller.roster.investigations.get(id=formid):
                    self.msg("You cannot assist one of your own investigations. You must use a retainer.")
                    return False
            except (TypeError, ValueError, AttributeError, Investigation.DoesNotExist):
                pass

        return True

    def set_helper(self):
        if not self.investigation_form:
            self.msg("No form found. Use /new.")
            return
        try:
            helper = self.caller.player_ob.retainers.get(id=self.args).dbobj
            if not helper.db.abilities or helper.db.abilities.get("investigation_assistant", 0) < 1:
                self.msg("%s is not able to assist investigations." % helper)
                return
        except (AttributeError, ValueError, Agent.DoesNotExist):
            self.msg("No retainer by that number. Setting it to be you instead.")
            helper = self.caller
        if not self.check_eligibility(helper):
            return
        self.investigation_form[4] = helper
        self.disp_investigation_form()

    def disp_invites(self):
        invites = self.caller.db.investigation_invitations or []
        # check which are valid
        investigations = Investigation.objects.filter(id__in=invites, ongoing=True, active=True)
        investigations = investigations | self.caller.roster.investigations.filter(ongoing=True)
        self.msg("You are permitted to help the following investigations:\n%s" % "\n".join(
            "  %s (ID: %s)" % (str(ob), ob.id) for ob in investigations))
        invest_ids = [ob.id for ob in investigations]
        # prune out invitations to investigations that are not active
        invites = [num for num in invites if num in invest_ids]
        self.caller.db.investigation_invitations = invites

    @property
    def valid_targ_ids(self):
        invites = self.caller.db.investigation_invitations or []
        if self.helper != self.caller:
            # if it's a retainer, we add IDs of investigations we're running or assisting as valid for them
            invites.extend(list(Investigation.objects.filter(Q(character=self.caller.roster) |
                                                             Q(assistants__char=self.caller)
                                                             ).exclude(ongoing=False).values_list('id', flat=True)))
        return invites

    def get_target(self):
        """
        Sets the target of the object we'll create. For an assisting
        investigation, it'll be the ID of the investigation.
        """
        if not self.args:
            self.disp_invites()
            return
        try:
            targ = int(self.args)
        except ValueError:
            self.msg("You must supply the ID of an investigation.")
            return
        if targ not in self.valid_targ_ids:
            self.msg("No investigation by that ID.")
            return
        # check that we can't do our own unless it's a retainer
        helper = self.investigation_form[4]
        if helper == self.caller:
            if self.caller.roster.investigations.filter(ongoing=True, id=targ):
                self.msg("You cannot assist your own investigation.")
                return
        if helper.assisted_investigations.filter(investigation_id=targ):
            phrase = "%s is" % str(helper) if helper != self.caller else "You are"
            self.msg("%s already helping that investigation. You can /resume helping it." % phrase)
            return
        self.investigation_form[0] = targ
        super(CmdAssistInvestigation, self).get_target()

    def check_too_busy_to_finish(self):
        """Checks if helper is too busy"""
        try:
            if self.helper.roster.investigations.filter(active=True):
                already_investigating = True
                self.msg("You already have active investigations.")
            else:
                already_investigating = False
        except AttributeError:
            already_investigating = False
        return already_investigating

    def mark_active(self, created_object):
        """After the InvestigationAssistant has been created, check to see if we can mark it helping"""
        already_investigating = self.check_too_busy_to_finish()
        if not already_investigating and not self.check_enough_time_left():
            return
        if not already_investigating and not self.check_ap_cost():
            return
        current_qs = self.helper.assisted_investigations.filter(currently_helping=True).exclude(id=created_object.id)
        if current_qs:
            for ob in current_qs:
                ob.currently_helping = False
                ob.save()
            self.msg("%s was currently helping another investigation. Switching." % self.helper)
        if not already_investigating:
            created_object.currently_helping = True
            created_object.save()
            created_object.investigation.do_roll()
            self.msg("%s is now helping %s." % (self.helper, created_object.investigation))
        else:
            self.msg("You already have an active investigation. That must stop before you help another.\n"
                     "Once that investigation is no longer active, you may resume helping this investigation.")
        self.caller.attributes.remove(self.form_attr)

    @property
    def target_type(self):
        return "investigation"

    @property
    def finished_form(self):
        form = super(CmdAssistInvestigation, self).finished_form
        if not form:
            return
        invest_id, actions, stat, skill = form
        valid_investigations = self.valid_targ_ids
        if invest_id not in valid_investigations:
            self.msg("That is not a valid ID of an investigation for %s to assist." % self.helper)
            self.msg("Valid IDs: %s" % ", ".join(str(ob) for ob in valid_investigations))
            return
        try:
            investigation = Investigation.objects.get(id=invest_id)
        except Investigation.DoesNotExist:
            self.msg("No investigation by that ID found.")
            return
        return investigation, actions, stat, skill

    def disp_currently_helping(self, char):
        self.msg("%s and retainers is helping the following investigations:" % char)
        table = PrettyTable(["ID", "Character", "Investigation Owner", "Currently Helping"])
        if "history" in self.switches:
            investigations = char.assisted_investigations.filter(investigation__ongoing=False)
        else:
            investigations = char.assisted_investigations.filter(investigation__ongoing=True)
        retainers = [retainer.dbobj.id for retainer in char.player_ob.retainers.all() if retainer.dbobj]
        if "history" in self.switches:
            retainer_investigations = InvestigationAssistant.objects.filter(char__in=retainers,
                                                                            investigation__ongoing=False)
        else:
            retainer_investigations = InvestigationAssistant.objects.filter(char__in=retainers,
                                                                            investigation__ongoing=True)
        investigations = list(investigations) + list(retainer_investigations)
        for ob in investigations:
            def apply_color(object_to_format):
                if ob.investigation.active:
                    return "{w%s{n" % object_to_format
                return "{r%s{n" % object_to_format
            row = [apply_color(column) for column in (ob.investigation.id, ob.char, ob.investigation.char,
                                                      ob.currently_helping)]
            table.add_row(row)
        self.msg(table)

    def check_skill(self):
        if self.args.lower() not in self.helper.db.skills:
            self.msg("%s has no skill by the name of %s." % (self.helper, self.args))
            return
        return True

    def view_investigation(self):
        try:
            character_ids = [self.caller.id] + [ob.dbobj.id for ob in self.caller.player_ob.retainers]
            ob = Investigation.objects.filter(assistants__char_id__in=character_ids).distinct().get(id=self.args)
        except (Investigation.DoesNotExist, TypeError, ValueError):
            self.msg("Could not find an investigation you're helping by that number.")
            self.disp_currently_helping(self.caller)
            return
        self.msg(ob.display())

    def get_retainer_from_args(self, args):
        try:
            if args.isdigit():
                char = self.caller.player.retainers.get(id=args).dbobj
            else:
                char = self.caller.player.retainers.get(name=args).dbobj
            return char
        except (ValueError, TypeError, Agent.DoesNotExist):
            self.msg("Retainer not found by that name or number.")
            return

    def func(self):
        finished = super(CmdAssistInvestigation, self).func()
        if finished:
            return
        if not self.args and not self.switches or "history" in self.switches:
            if self.investigation_form:
                self.disp_investigation_form()
            self.disp_invites()
            self.disp_currently_helping(self.caller)
            return
        if "retainer" in self.switches and len(self.switches) == 1:
            self.set_helper()
            return
        if "view" in self.switches or not self.switches:
            self.view_investigation()
            return
        if "stop" in self.switches:
            if "retainer" in self.switches:
                char = self.get_retainer_from_args(self.args)
                if not char:
                    return
            else:
                char = self.caller
            refund = 0
            for ob in char.assisted_investigations.filter(currently_helping=True):
                ob.currently_helping = False
                ob.save()
                refund += self.ap_cost
            if refund:
                self.caller.player_ob.pay_action_points(-refund)
            self.msg("%s stopped assisting investigations." % char)
            return
        if "resume" in self.switches:
            if "retainer" in self.switches:
                try:
                    if self.rhs.isdigit():
                        char = self.caller.player.retainers.get(id=self.rhs).dbobj
                    else:
                        char = self.caller.player.retainers.get(name=self.rhs).dbobj
                except (Agent.DoesNotExist, AttributeError):
                    self.msg("No retainer found by that ID or number.")
                    return
            else:  # not a retainer, just the caller. So check if they have an active investigation
                char = self.caller
                if self.caller.roster.investigations.filter(active=True):
                    self.msg("You currently have an active investigation, and cannot assist an investigation.")
                    return
            # check if they already are assisting something
            if char.assisted_investigations.filter(currently_helping=True):
                self.msg("%s is already assisting an investigation." % char)
                return
            if not self.check_enough_time_left():
                return
            try:
                ob = char.assisted_investigations.get(investigation__id=self.lhs)
            except (ValueError, TypeError, InvestigationAssistant.DoesNotExist):
                self.msg("Not helping an investigation by that number.")
                return
            except InvestigationAssistant.MultipleObjectsReturned:
                self.msg("Well, this is awkward. You are assisting that investigation multiple times. This shouldn't "
                         "be able to happen, but here we are.")
                inform_staff("BUG: %s is assisting investigation %s multiple times." % (char, self.lhs))
                return
            # check if they have action points to afford it
            if not self.check_ap_cost():
                return
            # all checks passed, mark it as currently being helped if the investigation exists
            ob.currently_helping = True
            ob.save()
            self.msg("Now helping %s." % ob.investigation)
            return
        if set(self.change_switches) & set(self.switches):
            if "retainer" in self.switches:
                lhs = self.lhs.split("/")
                try:
                    char = self.get_retainer_from_args(lhs[0])
                    if not char:
                        return
                    investigation_id = lhs[1]
                except (IndexError, TypeError, ValueError):
                    self.msg("You must specify <retainer ID>/<investigation ID>.")
                    return
            else:
                char = self.caller
                investigation_id = self.lhs
            try:
                ob = char.assisted_investigations.get(investigation__id=investigation_id)
                if not self.check_is_ongoing(ob.investigation):
                    return
                if not self.check_enough_time_left():
                    return
                if "changestory" in self.switches:
                    ob.actions = self.rhs
                    field = "story"
                elif "changestat" in self.switches:
                    rhs = self.rhs.lower()
                    if rhs not in VALID_STATS:
                        self.msg("Not a valid stat.")
                        return
                    ob.stat_used = rhs
                    field = "stat"
                elif "changeskill" in self.switches:
                    rhs = self.rhs.lower()
                    if rhs not in VALID_SKILLS:
                        self.msg("Not a valid skill.")
                        return
                    ob.skill_used = rhs
                    field = "skill"
                elif "silver" in self.switches:
                    ob = ob.investigation
                    amt = self.caller.db.currency or 0.0
                    try:
                        val = int(self.rhs)
                        amt -= val
                        if amt < 0 or val <= 0:
                            raise ValueError
                        if val % 5000 or (ob.silver + val) > 50000:
                            self.msg("Silver must be a multiple of 5000, 50000 max.\nCurrent silver: %s" % ob.silver)
                            return
                    except (TypeError, ValueError):
                        self.caller_cannot_afford()
                        return
                    self.caller.pay_money(val)
                    ob.silver += val
                    ob.save()
                    # redo the roll with new difficulty
                    ob.do_roll()
                    self.msg("You add %s silver to the investigation." % val)
                    return
                elif "resource" in self.switches or "resources" in self.switches:
                    ob = ob.investigation
                    dompc = self.caller.player_ob.Dominion
                    try:
                        rtype, val = self.rhslist[0].lower(), int(self.rhslist[1])
                        if val <= 0:
                            raise ValueError
                        oamt = getattr(ob, rtype)
                        if oamt + val > 50:
                            self.msg("Maximum of 50 per resource. Current value: %s" % oamt)
                            return
                        current = getattr(dompc.assets, rtype)
                        current -= val
                        if current < 0:
                            self.msg("You do not have enough %s resources." % rtype)
                            return
                        setattr(dompc.assets, rtype, current)
                        dompc.assets.save()
                    except (TypeError, ValueError, IndexError, AttributeError):
                        self.msg("Invalid syntax.")
                        return
                    oamt += val
                    setattr(ob, rtype, oamt)
                    ob.save()
                    # redo the roll with new difficulty
                    ob.do_roll()
                    self.msg("You have added %s resources to the investigation." % val)
                    return
                elif "actionpoints" in self.switches:
                    ob = ob.investigation
                    if not ob.active:
                        self.msg("The investigation must be marked active to invest in it.")
                        return
                    # check if we can pay
                    try:
                        amt = int(self.rhs)
                        if amt <= 0:
                            raise ValueError
                        if amt % 5:
                            self.msg("Action points must be a multiple of 5")
                            self.msg("Current action points allocated: %s" % ob.action_points)
                            return
                        if not self.check_ap_cost(amt):
                            return
                    except (TypeError, ValueError):
                        self.caller_cannot_afford()
                        return
                    # add action points and save
                    ob.action_points += amt
                    ob.save()
                    self.msg("New action point total is %s." % ob.action_points)
                    return
                else:
                    self.msg("Unrecognized switch.")
                    return
                ob.save()
                self.msg("Changed %s to: %s" % (field, self.rhs))
            except (ValueError, InvestigationAssistant.DoesNotExist):
                self.msg("%s isn't helping an investigation by that number." % char)
            return
        self.msg("Unrecognized switch.")


class CmdInvestigate(InvestigationFormCommand):
    """
    @investigate
    Usage:
        @investigate
        @investigate/history
        @investigate/view <id #>
        @investigate/active <id #>
        @investigate/silver <id #>=<additional silver to spend>
        @investigate/resource <id #>=<resource type>,<amount>
        @investigate/actionpoints <id #>=<additional points to spend>
        @investigate/changestory <id #>=<new story>
        @investigate/changestat <id #>=<new stat>
        @investigate/changeskill <id #>=<new skill>
        @investigate/abandon <id #>
        @investigate/resume <id #>
        @investigate/pause <id #>
        @investigate/requesthelp <id #>=<player>[,<player2>,...]
    Create Usage:
        @investigate/new
        @investigate/tags <tag to investigate>[/-<tag to omit>...]
        @investigate/story <text of how you do the investigation>
        @investigate/stat <stat to use for the check>
        @investigate/skill <additional skill to use besides investigation>
        @investigate/cancel
        @investigate/finish

    Investigation allows characters to research secrets and unravel some
    of the world's mysteries. To start, use @investigate/new and fill out
    required fields with /tags and /story switches, then use /finish to
    finalize your investigation for GMs to see. A tag is a word defining
    the topic of research, while story tells how it will be accomplished.
    The /stat and /skill switches let you set the appropriate roll used by
    your story. The 'investigation' skill will always be taken into account.
    Use /cancel to cancel the form.

    While you can have many ongoing investigations, one advances weekly.
    Determine which by selecting the /active investigation. Spend silver and
    resources to attempt to help your investigation progress. Use /pause
    switch to mark an investigation inactive, or /abandon it altogether.

    About topic/tags: Using multiple tags results in very specific research
    on a clue involving ALL those topics. You may place '-' in front to
    omit clues with that tag. ex: "@investigate/tags primum/tyrval/-adept"
    Alternately, you may specify an existing clue to try to find out things
    related to it, by setting the topic with 'Clue: <id or name>'. So if you
    want to find more things related to clue 50, it would be 'Clue: 50'.
    Be aware that specificity may result in nothing found, but you might be
    offered the chance to expend great effort (100 AP) into researching a
    clue that no one has found before.
    """
    key = "@investigate"
    locks = "cmd:all()"
    help_category = "Investigation"
    aliases = ["+investigate", "investigate"]
    base_cost = 25
    model_switches = ("view", "active", "silver", "resource", "pause", "actionpoints",
                      "changestory", "abandon", "resume", "requesthelp", "changestat", "changeskill")
    needs_ongoing = ("active", "silver", "resource", "pause", "actionpoints", "abandon",
                      "requesthelp", "changestat", "changeskill", "changestory")

    # noinspection PyAttributeOutsideInit
    def get_help(self, caller, cmdset):
        doc = self.__doc__
        caller = caller.char_ob
        self.caller = caller
        doc += "\n\nThe cost to make an investigation active is %s action points and %s resources." % (
            self.ap_cost, self.start_cost)
        return doc

    @property
    def ap_cost(self):
        return Investigation.ap_cost(self.caller)

    def list_ongoing_investigations(self):
        qs = self.related_manager.filter(ongoing=True)
        table = PrettyTable(["ID", "Tag/Topic", "Active"])
        for ob in qs:
            table.add_row([ob.id, ob.topic, "{wX{n" if ob.active else ""])
        self.msg("Ongoing investigations:\n%s" % table)

    def list_old_investigations(self):
        qs = self.related_manager.filter(ongoing=False)
        table = PrettyTable(["ID", "Tag/Topic"])
        for ob in qs:
            table.add_row([ob.id, ob.topic])
        self.msg("Old investigations:\n%s" % table)

    @property
    def start_cost(self):
        caller = self.caller
        try:
            skill = caller.db.skills.get("investigation", 0)
            cost = self.base_cost - (5 * skill)
            if cost < 0:
                cost = 0
            return cost
        except AttributeError:
            return self.base_cost

    def display_target_string(self):
        return ""

    def mark_active(self, created_object):
        if not (self.related_manager.filter(active=True) or
                self.caller.assisted_investigations.filter(currently_helping=True)):
            if not self.caller.assisted_investigations.filter(currently_helping=True):
                if self.caller.player_ob.pay_action_points(self.ap_cost):
                    created_object.mark_active()
                    self.msg("New investigation created. This has been set as your active investigation " +
                             "for the week, and you may add resources/silver to increase its chance of success.")
                else:
                    self.msg("New investigation created. You could not afford the action points to mark it active.")
            else:
                self.msg("New investigation created. This investigation is not active because you are " +
                         "currently assisting an investigation already.")
        else:
            self.msg("New investigation created. You already are participating in an active investigation " +
                     "for this week, but may still add resources/silver to increase its chance of success " +
                     "for when you next mark this as active.")
        self.msg("You may only have one active investigation per week, and cannot change it once " +
                 "it has received GM attention. Only the active investigation can progress.")
        created_object.save()
        staffmsg = "%s has started an investigation on %s." % (self.caller, created_object.topic)
        if created_object.targeted_clue:
            staffmsg += " They will roll to find clue %s." % created_object.targeted_clue
            created_object.setup_investigation_for_clue(created_object.targeted_clue)
        else:
            staffmsg += " Their topic does not target a clue, and will automatically fail unless GM'd."
        inform_staff(staffmsg)

    def create_form(self):
        if not self.check_enough_time_left():
            return
        super(CmdInvestigate, self).create_form()

    def get_target(self):
        """Sets the target of the object we'll create. For an investigation,
        this will be the topic."""
        no_tags_msg = "You must include a tag or clue to investigate"
        if not self.args:
            return self.msg(no_tags_msg + ".")
        try:
            search_tags, omit_tags, source_clue = self.get_tags_or_clue_from_args()
        except CommandError as err:
            return self.msg(err)
        if not search_tags and not source_clue:
            return self.msg(no_tags_msg + ", not just tags you want to omit.")
        clue = get_random_clue(self.caller.roster, search_tags, omit_tags, source_clue)
        if not clue:
            if check_break():
                return self.refuse_new_clue("Investigations that require new writing are not " +
                                            "allowed during staff break.")
            if len(search_tags) + len(omit_tags) > 6:
                return self.refuse_new_clue("That investigation would be too specific.")
            self.msg("The tag(s) or clue specified does not match an existing clue, and will be much more difficult and"
                     " more expensive to look into than normal. Try other tags for an easier investigation, or "
                     "proceed to /finish for a much more difficult one.")
        self.investigation_form[5] = [search_tags, omit_tags]
        self.investigation_form[4] = clue
        self.investigation_form[0] = self.args
        self.investigation_form[6] = source_clue
        super(CmdInvestigate, self).get_target()

    def get_tags_or_clue_from_args(self):
        args = self.args.split("/")
        search_tags = []
        omit_tags = []
        source_clue = None
        if args[0].lower().startswith("clue:"):
            args = args[0].lower()
            name = args.lstrip("clue:").strip()
            q_args = Q(characters=self.caller.roster)
            source_clue = self.get_by_name_or_id(Clue, name, q_args=q_args)
            return search_tags, omit_tags, source_clue
        for tag_txt in args:
            tag = self.get_by_name_or_id(SearchTag, tag_txt.lstrip("-"))
            if tag_txt.startswith("-"):
                omit_tags.append(tag)
            else:
                search_tags.append(tag)
        return search_tags, omit_tags, source_clue

    @property
    def need_new_clue_written(self):
        return not bool(self.investigation_form[4])

    def func(self):
        finished = super(CmdInvestigate, self).func()
        if finished:
            return
        caller = self.caller
        entry = caller.roster
        dompc = caller.player_ob.Dominion
        investigation = self.investigation_form
        if not self.args and not self.switches:
            if investigation:
                self.disp_investigation_form()
            self.list_ongoing_investigations()
            return
        if "history" in self.switches:
            # display history
            self.list_old_investigations()
            return
        if (set(self.switches) & set(self.model_switches)) or not self.switches:
            try:
                ob = self.related_manager.get(id=int(self.lhs))
            except (TypeError, ValueError):
                caller.msg("Must give ID of investigation.")
                return
            except Investigation.DoesNotExist:
                caller.msg("Investigation not found.")
                return
            if self.check_switches(self.needs_ongoing) and not self.check_is_ongoing(ob):
                return
            if "resume" in self.switches:
                msg = "To mark an investigation as active, use /active."
                if ob.ongoing:
                    self.msg("Already ongoing. %s" % msg)
                    return
                if ob.clue_discoveries.exists():
                    self.msg("This investigation has found something already. Start another.")
                    return
                if not self.check_enough_time_left():
                    return
                ob.ongoing = True
                ob.save()
                caller.msg("Investigation has been marked to be ongoing. %s" % msg)
                return
            if "pause" in self.switches:
                if not ob.active:
                    self.msg("It was already inactive.")
                    return
                self.caller.player_ob.pay_action_points(-self.ap_cost)
                ob.active = False
                ob.save()
                caller.msg("Investigation is no longer active.")
                return
            if "abandon" in self.switches or "stop" in self.switches:
                ob.ongoing = False
                if ob.active:
                    self.caller.player_ob.pay_action_points(-self.ap_cost)
                ob.active = False
                ob.save()
                asslist = []
                for ass in ob.active_assistants:
                    ass.currently_helping = False
                    ass.save()
                    asslist.append(str(ass.char))
                caller.msg("Investigation has been marked to no longer be ongoing nor active.")
                caller.msg("You can resume it later with /resume.")
                if asslist:
                    caller.msg("The following assistants have stopped helping: %s" % ", ".join(asslist))
                return
            if "view" in self.switches or not self.switches:
                caller.msg(ob.display())
                return
            if "active" in self.switches:
                if ob.active:
                    self.msg("It is already active.")
                    return
                try:
                    current_active = entry.investigations.get(active=True)
                except Investigation.DoesNotExist:
                    current_active = None
                if caller.assisted_investigations.filter(currently_helping=True):
                    self.msg("You are currently helping an investigation, and must stop first.")
                    return
                if check_break() and not ob.targeted_clue:
                    self.msg("Investigations that do not target a clue cannot be marked active during the break.")
                    return
                if not self.check_enough_time_left():
                    return
                if current_active:
                    if not current_active.automate_result:
                        caller.msg("You already have an active investigation " +
                                   "that has received GMing this week, and cannot be switched.")
                        return
                    if not self.check_ap_cost():
                        return
                    current_active.active = False
                    current_active.save()
                else:  # check cost if we don't have a currently active investigation
                    if not self.check_ap_cost():
                        return
                # can afford it, proceed to turn off assisted investigations and mark active
                for ass in caller.assisted_investigations.filter(currently_helping=True):
                    ass.currently_helping = False
                    ass.save()
                    self.msg("No longer assisting in %s" % ass.investigation)
                ob.mark_active()
                caller.msg("%s set to active." % ob)
                return
            if "silver" in self.switches:
                if not self.check_enough_time_left():
                    return
                amt = caller.db.currency or 0.0
                try:
                    val = int(self.rhs)
                    amt -= val
                    if amt < 0 or val <= 0:
                        raise ValueError
                    if val % 5000 or (ob.silver + val) > 50000:
                        caller.msg("Silver must be a multiple of 5000, 50000 max.\nCurrent silver: %s" % ob.silver)
                        return
                except (TypeError, ValueError):
                    self.caller_cannot_afford()
                    return
                caller.pay_money(val)
                ob.silver += val
                ob.save()
                # redo the roll with new difficulty
                ob.do_roll()
                caller.msg("You add %s silver to the investigation." % val)
                return
            if "actionpoints" in self.switches:
                if not self.check_enough_time_left():
                    return
                if not ob.active:
                    self.msg("The investigation must be marked active to invest time in it.")
                    return
                try:
                    val = int(self.rhs)
                    if val <= 0:
                        raise ValueError
                    if val % 5:
                        caller.msg("Action points must be a multiple of 5")
                        caller.msg("Current action points allocated: %s" % ob.action_points)
                        return
                    if not self.check_ap_cost(val):
                        return
                except (TypeError, ValueError):
                    self.caller_cannot_afford()
                    return
                ob.action_points += val
                ob.save()
                # redo the roll with new difficulty
                ob.do_roll()
                caller.msg("You add %s action points to the investigation." % val)
                return
            if "resource" in self.switches or "resources" in self.switches:
                if not self.check_enough_time_left():
                    return
                try:
                    rtype, val = self.rhslist[0].lower(), int(self.rhslist[1])
                    if val <= 0:
                        raise ValueError
                    oamt = getattr(ob, rtype)
                    if oamt + val > 50:
                        caller.msg("Maximum of 50 per resource. Current value: %s" % oamt)
                        return
                    current = getattr(dompc.assets, rtype)
                    current -= val
                    if current < 0:
                        caller.msg("You do not have enough %s resources." % rtype)
                        return
                    setattr(dompc.assets, rtype, current)
                    dompc.assets.save()
                except (TypeError, ValueError, IndexError, AttributeError):
                    caller.msg("Invalid syntax.")
                    return
                oamt += val
                setattr(ob, rtype, oamt)
                ob.save()
                # redo the roll with new difficulty
                ob.do_roll()
                caller.msg("You have added %s resources to the investigation." % val)
                return
            if "changestory" in self.switches:
                ob.actions = self.rhs
                ob.save()
                caller.msg("The new story of your investigation is:\n%s" % self.rhs)
                return
            if "changestat" in self.switches:
                if self.rhs not in VALID_STATS:
                    self.msg("That is not a valid stat name.")
                    return
                ob.stat_used = self.rhs
                ob.save()
                caller.msg("The new stat is: %s" % self.rhs)
                return
            if "changeskill" in self.switches:

                if self.rhs not in VALID_SKILLS:
                    self.msg("That is not a valid skill name.")
                    return
                ob.skill_used = self.rhs
                ob.save()
                caller.msg("The new skill is: %s" % self.rhs)
                return
            if "requesthelp" in self.switches:
                from typeclasses.characters import Character

                if not (ob.active and ob.ongoing):
                    self.msg("You may only invite others to active investigations.")
                    return
                for target in self.rhslist:
                    try:
                        char = Character.objects.get(db_key__iexact=target, roster__roster__name="Active")
                    except Character.DoesNotExist:
                        self.msg("No active player found named %s" % target)
                        continue
                    if char == caller:
                        self.msg("You cannot invite yourself.")
                        continue
                    if char.assisted_investigations.filter(investigation=ob):
                        self.msg("%s are already able to assist the investigation." % target)
                        continue
                    current = char.db.investigation_invitations or []
                    if ob.id in current:
                        self.msg("%s already has an invitation to assist this investigation." % target)
                        continue

                    self.msg("Asking %s to assist with %s." % (char.key, ob))
                    current.append(ob.id)
                    char.db.investigation_invitations = current
                    name = caller.key
                    inform_msg = "%s has requested your help in their investigation, ID %s.\n" % (name, ob.id)
                    inform_msg += "To assist them, use the {w@helpinvestigate{n command, creating a "
                    inform_msg += "form with {w@helpinvestigate/new{n, setting the target with "
                    inform_msg += "{w@helpinvestigate/target %s{n, and filling in the other fields." % ob.id
                    inform_msg += "\nThe current actions of their investigation are: %s" % ob.actions
                    char.player_ob.inform(inform_msg, category="Investigation Request From %s" % name,
                                          append=False)
                return
        caller.msg("Invalid switch.")
        return


class CmdAdminInvestigations(ArxPlayerCommand):
    """
    @gminvestigations

    Usage:
        @gminvest
        @gminvest/view <ID #>
        @gminvest/target <ID #>=<Clue #>
        @gminvest/randomtarget <ID #>
        @gminvest/roll <ID #>[=<roll mod>,<difficulty>]
        @gminvest/result <ID #>=<result string>
        @gminvest/cluemessage <ID #>=<message>
        @gminvest/setprogress <ID #>=<amount>
        @gminvest/search <character>=<keyword>

    Checks active investigations, and allows you to override their
    automatic results. You can /roll to see a result - base difficulty
    is 50 unless you override it. Specifying a result string will
    cause that to be returned to them in weekly maintenance, otherwise
    it'll process the event as normal to find a clue based on the topic.

    /search is used to search undiscovered clues that match a keyword for
    a given character to try to find possible matches.
    """
    key = "@gminvest"
    aliases = ["@gminvestigations"]
    locks = "cmd:perm(wizards)"
    help_category = "Investigation"

    @property
    def qs(self):
        return Investigation.objects.filter(active=True, ongoing=True,
                                            character__roster__name="Active")

    def disp_active(self):
        qs = list(self.qs)
        if len(qs) <= 20:
            table = EvTable("ID", "Char", "Topic", "Targeted Clue", "Roll", border="cells", width=78)
            for ob in qs:
                roll = ob.get_roll()
                roll = "{r%s{n" % roll if roll < 1 else "{w%s{n" % roll
                target = "{rNone{n" if not ob.targeted_clue else str(ob.targeted_clue)
                character = "{c%s{n" % ob.character
                table.add_row(ob.id, character, str(ob.topic), target, roll)
        else:
            table = PrettyTable(["ID", "Char", "Topic", "Targeted Clue", "Roll"])
            for ob in qs:
                roll = ob.get_roll()
                roll = "{r%s{n" % roll if roll < 1 else "{w%s{n" % roll
                target = "{rNone{n" if not ob.targeted_clue else str(ob.targeted_clue)[:30]
                character = "{c%s{n" % ob.character
                table.add_row([ob.id, character, str(ob.topic)[:15], target, roll])
        self.msg(str(table))

    def set_roll(self, ob, roll, mod=0, diff=None):
        ob.roll = roll
        ob.save()
        self.msg("Recording their new roll as: %s." % roll)
        check = ob.check_success(modifier=mod, diff=diff)
        if check:
            self.msg("They will {wsucceed{n the check to discover a clue this week.")
        else:
            self.msg("They will {rfail{n the check to discover a clue this week.")

    def func(self):
        caller = self.caller
        if not self.args:
            self.disp_active()
            return
        if "search" in self.switches:
            player = self.caller.search(self.lhs)
            if not player:
                return
            clue_query = (Q(desc__icontains=self.rhs) | Q(name__icontains=self.rhs) |
                          Q(search_tags__name__icontains=self.rhs))
            rev_query = Q(revelations__desc__icontains=self.rhs) | Q(revelations__search_tags__name__icontains=self.rhs)
            rev_query |= Q(revelations__name__icontains=self.rhs)
            undisco = (player.roster.undiscovered_clues.filter(allow_investigation=True)
                                                       .filter(clue_query | rev_query).distinct())
            self.msg("Clues that match: %s" % ", ".join("(ID:%s, %s)" % (ob.id, ob) for ob in undisco))
            return
        try:
            if "view" in self.switches or not self.switches:
                ob = Investigation.objects.get(id=int(self.args))
                caller.msg(ob.gm_display())
                return
            if "randomtarget" in self.switches:
                ob = Investigation.objects.get(id=int(self.args))
                ob.clue_target = None
                self.msg("%s now targets %s" % (ob, ob.targeted_clue))
                return
            if "target" in self.switches:
                ob = self.qs.get(id=int(self.lhs))
                try:
                    targ = Clue.objects.get(id=int(self.rhs))
                except Clue.DoesNotExist:
                    caller.msg("No clue by that ID.")
                    return
                if targ in ob.character.clues.all():
                    self.msg("|rThey already have that clue. Aborting.")
                    return
                ob.setup_investigation_for_clue(targ)  # will also handle saving the investigation
                caller.msg("%s set to %s." % (ob, targ))
                return
            if "roll" in self.switches:
                mod = 0
                diff = None
                ob = self.qs.get(id=int(self.lhs))
                try:
                    mod = int(self.rhslist[0])
                    diff = int(self.rhslist[1])
                except IndexError:
                    pass
                roll = ob.do_roll(mod=mod, diff=diff)
                self.set_roll(ob, roll)
                return
            if "result" in self.switches:
                ob = self.qs.get(id=int(self.lhs))
                ob.result = self.rhs
                ob.save()
                caller.msg("Result is now:\n%s" % ob.result)
                return
            if "setprogress" in self.switches:
                ob = self.qs.get(id=int(self.lhs))
                ob.progress = int(self.rhs)
                ob.save()
                self.msg("Their progress is now %s, required to complete is %s." % (ob.progress, ob.completion_value))
                return
        except (TypeError, ValueError):
            caller.msg("Arguments must be numbers.")
            return
        except Investigation.DoesNotExist:
            caller.msg("No Investigation by that ID.")
            return
        caller.msg("Invalid switch.")
        return


class CmdListClues(ArxPlayerCommand):
    """
    @clues

    Usage:
        @clues
        @clues <clue #>
        @clues/share <clue #>[,<clue2 #>...]=<target>[,<target2>...]/<note>
        @clues/search <text>
        @clues/addnote <clue #>=[text to append]

    Displays the clues that your character has discovered in game,
    or shares them with others. /search returns the clues that
    contain the text specified. /addnote allows you to add more text to
    your discovery of the clue.

    When sharing clues, please roleplay a bit about them first. Don't dump
    information on people without any context. You must also write a note
    which is appended to their clue that serves as a record about the scene:
    please briefly describe the scene in which the clue was shared, or why
    they were told, or any other contextual notes about it.
    """
    key = "clues"
    locks = "cmd:all()"
    aliases = ["clue", "@zoinks", "@jinkies"]
    help_category = "Information"

    def get_help(self, caller, cmdset):
        """Custom helpfile that lists clue sharing costs"""
        caller = caller.player_ob
        doc = self.__doc__
        doc += "\n\nYour cost of sharing clues is %s." % caller.clue_cost
        return doc

    @property
    def clue_discoveries(self):
        """Clue discovery objects for our caller"""
        try:
            return self.caller.roster.clue_discoveries.all()
        except AttributeError:
            return ClueDiscovery.objects.none()

    def func(self):
        """Executes clues command"""
        try:
            if not self.args or "search" in self.switches:
                return self.disp_clue_table()
            if "share" in self.switches:
                return self.share_clues()
            # get clue for display or sharing
            try:
                discovery = self.clue_discoveries.get(clue_id=self.lhs)
            except (ClueDiscovery.DoesNotExist, ValueError, TypeError):
                discovery = None
                if not self.switches and self.caller.check_permstring("builders"):
                    try:
                        discovery = Clue.objects.get(id=self.lhs)
                    except Clue.DoesNotExist:
                        pass
                if not discovery:
                    self.msg("No clue found by this ID: {w%s{n." % self.lhs)
                    return
            if not self.switches:
                self.msg(discovery.display(show_gm_notes=self.called_by_staff))
                return
            if "addnote" in self.switches:
                return self.add_note(discovery)
            self.msg("Invalid switch")
        except CommandError as err:
            self.msg(err)

    def share_clues(self):
        """Shares clues with others in room"""
        discoveries_to_share = []
        clue_err_msg = ""
        for arg in self.lhslist:
            try:
                discovery = self.clue_discoveries.get(clue_id=arg)
            except (ClueDiscovery.DoesNotExist, ValueError, TypeError):
                clue_err_msg += "No clue found by this ID: {w%s{n. " % arg
                continue
            if discovery.clue.allow_sharing:
                discoveries_to_share.append(discovery)
            else:
                clue_err_msg += "{w%s{n cannot be shared. " % discovery.clue
        if clue_err_msg:
            self.msg(clue_err_msg)
        if not discoveries_to_share:
            return
        if not self.rhs:
            raise CommandError("Who are you sharing with?")
        split_result = self.rhs.split("/", 1)
        try:
            rhslist, note = split_result[0], split_result[1]
        except IndexError:
            raise CommandError("You must provide a note that gives context to the clues you're sharing.")
        if len(note) < 80:
            raise CommandError("Please write a longer note that gives context to the clues you're sharing.")
        rhslist = rhslist.split(",")
        shared_names = []
        targets = []
        for arg in rhslist:
            pc = self.caller.search(arg)
            if not pc:
                return
            if not pc.char_ob.location or self.caller.char_ob.location != pc.char_ob.location:
                raise CommandError("You can only share clues with someone in the same room. Please don't share "
                                   "clues without some RP talking about them.")
            targets.append(pc)
        cost = len(targets) * len(discoveries_to_share) * self.caller.clue_cost
        if not self.caller.pay_action_points(cost):
            raise CommandError("Sharing the clue(s) with them would cost %s action points." % cost)
        for targ in targets:
            for discovery in discoveries_to_share:
                discovery.share(targ.roster, note=note)
            shared_names.append(str(targ.roster))
        msg = "You have shared the clue(s) '%s' with %s." % (", ".join(str(ob.clue) for ob in discoveries_to_share),
                                                             ", ".join(shared_names))
        if note:
            msg += "\nYour note: %s" % note
        self.msg(msg)

    def disp_clue_table(self):
        table = PrettyTable(["{wClue #{n", "{wSubject{n", "{wType{n"])
        discoveries = self.clue_discoveries.select_related('clue').order_by('date')
        if "search" in self.switches:
            msg = "{wMatching Clues{n\n"
            discoveries = discoveries.filter(Q(message__icontains=self.args) | Q(clue__desc__icontains=self.args) |
                                             Q(clue__name__icontains=self.args) |
                                             Q(clue__search_tags__name__iexact=self.args)).distinct()
        else:
            msg = "{wDiscovered Clues{n\n"
        for discovery in discoveries:
            table.add_row([discovery.clue.id, discovery.name, discovery.clue.get_clue_type_display()])
        msg += str(table)
        self.msg(msg, options={'box': True})

    def add_note(self, discovery):
        if not self.rhs:
            self.msg("Must contain a note to add.")
            return
        header = "\n[%s] %s wrote: " % (datetime.now().strftime("%x %X"), self.caller.key)
        discovery.message += header + self.rhs
        discovery.save()
        self.msg(discovery.display())


class CmdListRevelations(ArxPlayerCommand):
    """
    @revelations

    Usage:
        @revelations
        @revelations <ID>
        @revelations/checkmissed

        The first form of this command will just list all the revelations you know.
        The second form views a specific revelation.
        The third form will check if there are any revelations you should know which were missed
        due to clues being added to revelations later.

    """
    key = "@revelations"
    locks = "cmd:all()"
    help_category = "Information"

    def disp_rev_table(self):
        caller = self.caller
        table = PrettyTable(["{wRevelation #{n", "{wSubject{n"])
        revs = caller.roster.revelations.all()
        msg = "{wDiscovered Revelations{n\n"
        for rev in revs:
            table.add_row([rev.id, rev.name])
        msg += str(table)
        caller.msg(msg, options={'box': True})

    def resync_revelations(self):
        character = self.caller.roster
        revelations = Revelation.objects.filter(~Q(characters=character)).distinct()
        discovered = []
        for revelation in revelations:
            if revelation.player_can_discover(character):
                discovered.append(revelation)

        date = datetime.now()
        for revelation in discovered:
            message = "You had a revelation which had been missed!"
            RevelationDiscovery.objects.create(character=character, discovery_method="Checked for Missing",
                                               message=message, investigation=None,
                                               revelation=revelation, date=date)

            self.msg("You were missing a revelation: %s" % str(revelation))

    def func(self):
        if "checkmissed" in self.switches:
            self.msg("Checking for missed revelations...")
            self.resync_revelations()
            self.msg("Done!")
            return
        if not self.args:
            self.disp_rev_table()
            return
        try:
            rev = self.caller.roster.revelation_discoveries.get(revelation_id=self.args)
        except (ValueError, TypeError, RevelationDiscovery.DoesNotExist):
            rev = None
            if self.caller.check_permstring("builders"):
                try:
                    rev = Revelation.objects.get(id=self.args)
                except Revelation.DoesNotExist:
                    pass
            if not rev:
                self.msg("No revelation by that number.")
                self.disp_rev_table()
                return
        self.msg(rev.display())
        clues = self.caller.roster.clues.filter(revelations=rev.revelation)
        self.msg("Related Clues: %s" % "; ".join(str(clue) for clue in clues))


class CmdTheories(ArxPlayerCommand):
    """
    @theories

    Usage:
        @theories
        @theories/mine
        @theories <theory ID #>
        @theories/share <theory ID #>=<player>[,<player2>,...]
        @theories/create <topic>=<description>
        @theories/addclue <theory ID #>=<clue ID #>
        @theories/rmclue <theory ID #>=<clue ID #>
        @theories/addrelatedtheory <your theory ID #>=<other's theory ID #>
        @theories/forget <theory ID #>
        @theories/editdesc <theory ID #>=<desc>
        @theories/edittopic <theory ID #>=<topic>
        @theories/shareall <theory ID #>=<player>
        @theories/readall <theory ID #>
        @theories/addeditor <theory ID #>=<player>
        @theories/rmeditor <theory ID #>=<player>

    Allows you to create and share theories your character comes up with,
    and associate them with clues and other theories. You may only create
    associations for theories that you created.

    /shareall allows you to also share any clue you know that is related
    to the theory specify.
    """
    key = "@theories"
    locks = "cmd:all()"
    help_category = "Investigation"

    def display_theories(self):
        table = EvTable("{wID #{n", "{wTopic{n")
        if "mine" in self.switches:
            qs = self.caller.editable_theories.all().order_by('id')
        else:
            qs = self.caller.known_theories.all().order_by('id')
        for theory in qs:
            table.add_row(theory.id, theory.topic)
        self.msg(table)

    def view_theory(self):
        theories = self.caller.known_theories.all()
        try:
            theory = theories.get(id=self.args)
        except (Theory.DoesNotExist, ValueError, TypeError):
            self.msg("No theory by that ID.")
            return
        self.msg(theory.display())
        self.msg("{wRelated Theories{n: %s\n" %
                 ", ".join(str(ob.id) for ob in theory.related_theories.filter(id__in=theories)))
        disp_clues = theory.related_clues.filter(id__in=self.caller.roster.clues.all())
        self.msg("{wRelated Clues:{n %s" % ", ".join(ob.name for ob in disp_clues))
        if "readall" in self.switches:
            for clue in disp_clues:
                clue_display = "{wName{n: %s\n\n%s\n" % (clue.name, clue.desc)
                self.msg(clue_display)

    def func(self):
        if not self.args:
            self.display_theories()
            return
        if not self.switches or "view" in self.switches or "readall" in self.switches:
            self.view_theory()
            return
        if "search" in self.switches:
            matches = self.caller.known_theories.filter(Q(topic__icontains=self.args) | Q(desc__icontains=self.args))
            self.msg("Matches: %s" % ", ".join("%s (#%s)" % (ob, ob.id) for ob in matches))
            return
        if "create" in self.switches:
            theory = self.caller.created_theories.create(topic=self.lhs, desc=self.rhs)
            theory.add_editor(self.caller)
            self.msg("You have created a new theory.")
            return
        if "share" in self.switches or "shareall" in self.switches:
            try:
                theory = self.caller.known_theories.get(id=self.lhs)
            except (Theory.DoesNotExist, ValueError):
                self.msg("No theory found by that ID.")
                return
            targs = []
            for arg in self.rhslist:
                targ = self.caller.search(arg)
                if not targ:
                    continue
                targs.append(targ)
            if not targs:
                return
            clue_discoveries = self.caller.roster.clue_discoveries.filter(clue__id__in=theory.related_clues.all())
            per_targ_cost = self.caller.clue_cost
            for targ in targs:
                if "shareall" in self.switches:
                    cost = len(targs) * len(clue_discoveries) * per_targ_cost
                    if cost > self.caller.roster.action_points:
                        self.msg("That would cost %s action points." % cost)
                        return
                    try:
                        if targ.char_ob.location != self.caller.char_ob.location:
                            self.msg("You must be in the same room.")
                            continue
                    except AttributeError:
                        self.msg("One of you does not have a character object.")
                        continue
                    for clue in clue_discoveries:
                        if not clue.clue.allow_sharing:
                            self.msg("%s cannot be shared. Skipping." % clue.clue)
                            continue
                        clue.share(targ.roster)
                        self.msg("Shared clue %s with %s" % (clue.name, targ))
                    self.caller.pay_action_points(cost)
                if theory in targ.known_theories.all():
                    self.msg("They already know that theory.")
                    continue
                theory.share_with(targ)
                self.msg("Theory %s added to %s." % (self.lhs, targ))
                targ.inform("%s has shared theory {w'%s'{n with you. Use {w@theories %s{n to view it." % (
                    self.caller, theory.topic, self.lhs), category="Theories")
            return
        if "delete" in self.switches or "forget" in self.switches:
            try:
                theory = self.caller.known_theories.get(id=self.lhs)
            except (Theory.DoesNotExist, ValueError):
                self.msg("No theory by that ID.")
                return
            theory.forget_by(self.caller)
            self.msg("Theory forgotten.")
            if not theory.known_by.all():  # if no one knows about it now
                theory.delete()
            return
        if "addeditor" in self.switches or "rmeditor" in self.switches:
            try:
                theory = self.caller.editable_theories.get(id=self.lhs)
            except (Theory.DoesNotExist, ValueError):
                self.msg("No theory by that ID.")
                return
            player = self.caller.search(self.rhs)
            if not player:
                return
            if not theory.known_by.filter(id=player.id).exists():
                self.msg("They do not know the theory yet.")
                return
            if "addeditor" in self.switches:
                theory.add_editor(player)
                self.msg("%s can now edit the theory." % player)
                return
            if "rmeditor" in self.switches:
                if player == theory.creator:
                    self.msg("%s is the theory's original author, and cannot be removed." % player)
                else:
                    theory.remove_editor(player)
                    self.msg("%s cannot edit the theory." % player)
                return
        try:
            theory = self.caller.editable_theories.get(id=self.lhs)
        except (Theory.DoesNotExist, ValueError):
            self.msg("You cannot edit a theory by that number.")
            return
        if "editdesc" in self.switches:
            theory.desc = self.rhs
            theory.save()
            self.msg("New desc is: %s" % theory.desc)
            for player in theory.known_by.all():
                if player == self.caller:
                    continue
                player.inform("%s has been edited." % theory, category="Theories")
            return
        if "edittopic" in self.switches:
            theory.topic = self.rhs
            theory.save()
            self.msg("New topic is: %s" % theory.topic)
            return
        if "addrelatedtheory" in self.switches or "rmrelatedtheory" in self.switches:
            try:
                other_theory = self.caller.known_theories.get(id=self.rhs)
            except (Theory.DoesNotExist, ValueError):
                self.msg("You do not know a theory by that id.")
                return
            if "addrelatedtheory" in self.switches:
                theory.related_theories.add(other_theory)
                self.msg("Theory added.")
            else:
                theory.related_theories.remove(other_theory)
                self.msg("Theory removed.")
            return
        if "addclue" in self.switches or "rmclue" in self.switches:
            try:
                clue = self.caller.roster.clues.get(id=self.rhs)
            except (Clue.DoesNotExist, ValueError, TypeError, AttributeError):
                self.msg("No clue by that ID.")
                return
            if "addclue" in self.switches:
                theory.related_clues.add(clue)
                self.msg("Added clue %s to theory." % clue.name)
            else:
                theory.related_clues.remove(clue)
                self.msg("Removed clue %s from theory." % clue.name)
            return
        self.msg("Invalid switch.")


class ListPlotsMixin(object):
    """Mixin for commands that use plots"""

    @property
    def gm_plots(self):
        """Plots our caller is gming"""
        return self.caller.Dominion.plots_we_can_gm

    @property
    def gm_revelations(self):
        """Revelations our caller has written"""
        return self.caller.roster.revelations_written.all()

    def list_gm_plots(self):
        """Lists plots we're gming, and clues and revelations we've created"""
        plots = self.gm_plots
        clues = self.caller.roster.clues_written.all()
        revelations = self.caller.roster.revelations_written.all()

        def format_list(some_iter):
            """Helper function for formatting"""
            return ["%s (#%s)" % (ob, ob.id) for ob in some_iter]

        msg = "{wPlots GMd:{n %s\n" % list_to_string(format_list(plots))
        msg += "{wClues Written:{n %s\n" % list_to_string(format_list(clues))
        msg += "{wRevelations Written:{n %s\n" % list_to_string(format_list(revelations))
        return msg

    def get_revelation(self):
        """Gets a revelation by ID"""
        try:
            if self.args.isdigit():
                revelation = self.gm_revelations.get(id=self.args)
            else:
                revelation = self.gm_revelations.get(name__iexact=self.args)
            return revelation
        except (Revelation.DoesNotExist, ValueError, TypeError):
            raise CommandError("No Revelation by that name or number.\n" + self.list_gm_plots())


class PRPLorecommand(ListPlotsMixin, FormCommandMixin, ArxPlayerCommand):
    """Base class for commands that make lore for PRPs"""


class CmdPRPClue(PRPLorecommand):
    """
    Creates a clue for a PRP you ran

    Usage:
        +prpclue
        +prpclue/create
        +prpclue/revelation <revelation ID or name>
        +prpclue/name <clue name>
        +prpclue/desc <description>
        +prpclue/rating <investigation difficulty, 1-50>
        +prpclue/tags <tag 1>,<tag 2>,etc
        +prpclue/fake
        +prpclue/noinvestigate
        +prpclue/noshare
        +prpclue/finish
        +prpclue/abandon
        +prpclue/sendclue <clue ID>=<participant>
        +prpclue/listclues <revelation ID>

    Allows a GM to create custom clues for their PRP, and then send it to
    participants. Tags are the different keywords/phrases that allow it
    to be matched to an investigate. Setting a clue as fake means that it's
    false/a hoax. /noinvestigate and /noshare prevent investigating the
    clue or sharing it, respectively.

    Once the clue is created, it can be sent to any participant with the
    /sendclue switch. Clues must have a revelation written that is tied
    to the plot. See the prprevelation command for details.
    """
    key = "prpclue"
    help_category = "PRP"
    locks = "cmd: all()"
    form_class = ClueCreateForm
    form_attribute = "clue_creation_form"
    form_initial_kwargs = (('allow_sharing', True), ('allow_investigation', True), ('red_herring', False))

    def func(self):
        try:
            if not self.args and not self.switches:
                self.msg(self.list_gm_plots())
                self.display_form()
                return
            if "abandon" in self.switches:
                self.caller.attributes.remove(self.form_attribute)
                self.msg("Abandoned.")
                return
            if "create" in self.switches:
                return self.create_form()
            if "listclues" in self.switches:
                revelation = self.get_revelation()
                if not revelation:
                    return
                self.msg("Clues: %s" % ", ".join("%s (#%s)" % (clue, clue.id) for clue in revelation.clues.all()))
                return
            if "sendclue" in self.switches:
                try:
                    clue = Clue.objects.filter(revelations__plots__in=self.gm_plots).distinct().get(id=self.lhs)
                except (TypeError, ValueError, Clue.DoesNotExist):
                    self.msg("No clue found by that ID.")
                    return
                targ = self.caller.search(self.rhs)
                if not targ:
                    return
                if not self.gm_plots.filter(dompcs=targ.Dominion).exists():
                    self.msg("Target is not among the participants of the plots you GM.")
                    return
                targ.roster.discover_clue(clue)
                self.msg("You have sent them a clue.")
                targ.inform("Clue '%s' has been sent to you about a plot you're on. Use @clues to view it." % clue,
                            category="Clue Discovery")
                return
            form = self.caller.attributes.get(self.form_attribute)
            if not form:
                self.msg("Use /create to start a new form.")
                return
            if "finish" in self.switches:
                return self.submit_form()
            if "name" in self.switches:
                form['name'] = self.args
            if "desc" in self.switches:
                form['desc'] = self.args
            if "revelation" in self.switches:
                revelation = self.get_revelation()
                if not revelation:
                    return
                form['revelation'] = revelation.id
            if "rating" in self.switches:
                form['rating'] = self.args
            if "tags" in self.switches:
                form['tag_names'] = self.args
            if "fake" in self.switches:
                form['red_herring'] = not form.get('red_herring')
            if "noinvestigate" in self.switches:
                form['allow_investigation'] = not form.get('allow_investigation', True)
            if "noshare" in self.switches:
                form['allow_sharing'] = not form.get('allow_sharing', True)
            self.display_form()
        except CommandError as err:
            self.msg(err)


class CmdPRPRevelation(PRPLorecommand):
    """
    Creates a revelation for a PRP you are GMing for

    Usage:
        +prprevelation
        +prprevelation/create
        +prprevelation/name <name>
        +prprevelation/desc <description>
        +prprevelation/rating <total value of clues required for discovery>
        +prprevelation/tags <tag 1>,<tag 2>,etc
        +prprevelation/plot <plot ID>[=<notes about relationship to plot>]
        +prprevelation/finish
        +prprevelation/abandon

    Allows a GM for a PRP to create lore for PRPs they're running. A Revelation
    is a summation of significant game lore, while a Clue's a small part of it:
    either a specific perspective of someone, providing more context/detail on
    some aspect of it, etc. For example, if you ran a PRP on a haunted castle,
    the revelation might be 'The Haunted Castle of Foobar'. The Revelation's
    desc would be a synopsis of the narrative of the entire plot. Clues would
    be about the history of House Foobar, the structure of the castle, events
    that caused it to become haunted, etc.

    Tags are keywords/phrases used specifically for searching/indexing topics
    in the database. Please use them liberally on anything significant in the
    revelation to help staff out. For example, you would add a tag for Foobar
    in the above example, and if the House was destroyed by 'The Bloodcurse',
    you would add that as a tag as well.
    """
    key = "prprevelation"
    help_category = "PRP"
    locks = "cmd: all()"
    form_class = RevelationCreateForm
    form_attribute = "revelation_creation_form"
    form_initial_kwargs = (('red_herring', False),)

    def func(self):
        """Executes command"""
        try:
            if not self.args and not self.switches:
                self.msg(self.list_gm_plots())
                self.display_form()
                return
            if "abandon" in self.switches:
                self.caller.attributes.remove(self.form_attribute)
                self.msg("Abandoned.")
                return
            if "create" in self.switches:
                return self.create_form()
            form = self.caller.attributes.get(self.form_attribute)
            if not form:
                self.msg("Use /create to start a new form.")
                return
            if "finish" in self.switches:
                return self.submit_form()
            if "name" in self.switches:
                form['name'] = self.args
            if "desc" in self.switches:
                form['desc'] = self.args
            if "plot" in self.switches:
                try:
                    if self.lhs.isdigit():
                        plot = self.gm_plots.get(id=self.lhs)
                    else:
                        plot = self.gm_plots.get(name__iexact=self.lhs)
                except Plot.DoesNotExist:
                    raise CommandError("No plot by that name or number.")
                form['plot'] = plot.id
                form['plot_gm_notes'] = self.rhs
            if "tags" in self.switches:
                form['tag_names'] = self.args
            if "fake" in self.switches:
                form['red_herring'] = not form.get('red_herring')
            if "rating" in self.switches:
                form['required_clue_value'] = self.args
            self.display_form()
        except CommandError as err:
            self.msg(err)
