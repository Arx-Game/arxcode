"""
Commands for agents
"""
from django.db.models import Q
from evennia.objects.models import ObjectDB

# noinspection PyProtectedMember
from evennia.objects.objects import _AT_SEARCH_RESULT

from commands.base import ArxCommand, ArxPlayerCommand
from server.utils.arx_utils import validate_name, caller_change_field
from typeclasses.npcs.npc_types import get_npc_type, generate_default_name_and_desc
from .models import Agent, Organization, AssetOwner
from world.traits.models import Trait


class CmdAgents(ArxPlayerCommand):
    """
    @agents

    Usage:
        @agents
        @agents <org name>
        @agents/guard player,<id #>,<amt>
        @agents/recall player,<id #>,<amt>
        @agents/hire <type>,<level>,<amount>=<organization>
        @agents/desc <ID #>,<desc>
        @agents/name <ID #>,name
        @agents/transferowner <ID #>,<new owner>

    Hires guards, assassins, spies, or any other form of NPC that has a
    presence in-game and can act on player orders. Agents are owned by an
    organization and are generic, while personalized agents are created and
    ordered by the @retainer command, which are unique individuals. To use
    any of the switches of this command, you must be in a space designated
    by GMs to be the barracks your agents report to.

    Switches:
    guard: The 'guard' switch assigns agents of the type and the
    amount to a given player, who can then use them via the +guard command.
    'name' should be what the type of guard is named - for example, name
    might be 'Thrax elite guards'.

    recall: Recalls guards of the given type listed by 'name' and the value
    given by the deployment number, and the amount listed. For example, you
    might have 10 Grayson House Guards deployed to player name A, and 15 to
    player B. To recall 10 of the guards assigned to player B, you would do
    @agents/recall grayson house guards,B,10=grayson.

    hire: enter the type, level, and quantity of the agents and the org you
    wish to buy them for. The type will generally be 'guard' for nobles,
    and 'thug' for crime families and the like. Cost = (lvl+1)^5 in
    military resources for each agent.

    """

    key = "@agents"
    locks = "cmd:all()"
    help_category = "Dominion"
    aliases = ["@agent"]

    @staticmethod
    def find_barracks(owner):
        """ "find rooms that are tagged as being barracks for that owner"""
        tagname = str(owner.owner) + "_barracks"
        rooms = ObjectDB.objects.filter(db_tags__db_key__iexact=tagname)
        return list(rooms)

    @staticmethod
    def get_cost(lvl):
        """Gets the cost of an agent"""
        cost = pow((lvl + 1), 5)
        return cost

    @staticmethod
    def get_guard_cap(char):
        """Gets maximum number of guards for a character"""
        return char.max_guards

    @staticmethod
    def get_allowed_types_from_org(org):
        """Gets types of agents allowed for an org"""
        if org.category in ("noble", "law", "discipleship"):
            return ["guards"]
        if "crime" in org.category:
            return ["thugs"]
        return []

    def func(self):
        """Executes agents command"""
        caller = self.caller
        personal = Agent.objects.filter(owner__player__player=caller)
        orgs = [
            org.assets
            for org in Organization.objects.filter(members__player=caller.Dominion)
            if org.access(caller, "guards")
        ]
        house = Agent.objects.filter(
            owner__organization_owner__members__player__player=caller,
            owner__organization_owner__in=[org.organization_owner for org in orgs],
        )
        agents = personal | house
        if not self.args:
            caller.msg(
                "{WYour agents:{n\n%s"
                % "".join(agent.display(caller=self.caller) for agent in agents),
                options={"box": True},
            )
            barracks = self.find_barracks(caller.Dominion.assets)
            for org in orgs:
                barracks.extend(self.find_barracks(org))
            caller.msg(
                "{wBarracks locations:{n %s" % ", ".join(ob.key for ob in barracks)
            )
            return
        if not self.switches:
            try:
                org = Organization.objects.get(
                    name__iexact=self.args, members__player=caller.Dominion
                )
            except Organization.DoesNotExist:
                caller.msg(
                    "You are not a member of an organization named %s." % self.args
                )
                return
            caller.msg(
                ", ".join(agent.display() for agent in org.assets.agents.all()),
                options={"box": True},
            )
            barracks = self.find_barracks(org.assets)
            caller.msg(
                "{wBarracks locations:{n %s" % ", ".join(ob.key for ob in barracks)
            )
            return
        try:
            owner_ids = []
            loc = caller.character.location
            if loc == caller.character.home:
                owner_ids.append(caller.Dominion.assets.id)
            if loc.db.barracks_owner:
                owner_ids.append(loc.db.barracks_owner)
            if loc.db.room_owner:
                owner_ids.append(loc.db.room_owner)
            if owner_ids:
                owners = [
                    ob
                    for ob in AssetOwner.objects.filter(id__in=owner_ids)
                    if ob == caller.Dominion.assets
                    or (
                        ob.organization_owner
                        and ob.organization_owner.access(caller, "guards")
                    )
                ]
                if not owners:
                    caller.msg("You do not have access to guards here.")
            else:
                self.msg("You do not have access to guards here.")
                return
            owner_ids = [ob.id for ob in owners]
            owner_names = ", ".join(str(ob) for ob in owners)
        except (AttributeError, AssetOwner.DoesNotExist, ValueError, TypeError):
            caller.msg("You do not have access to guards here.")
            return
        if not self.lhslist:
            caller.msg("Must provide arguments separated by commas.")
            return
        if "guard" in self.switches:
            try:
                player, pid, amt = self.lhslist
                amt = int(amt)
                if amt < 1:
                    self.msg("Must assign a positive number.")
                    return
                pid = int(pid)
                targ = caller.search(player)
                if not targ:
                    caller.msg("Could not find player by name %s." % player)
                    return
                avail_agent = Agent.objects.get(id=pid, owner_id__in=owner_ids)
                if avail_agent.quantity < amt:
                    caller.msg(
                        "You tried to assign %s, but only have %s available."
                        % (amt, avail_agent.quantity)
                    )
                    return
                try:
                    # assigning it to their character
                    targ = targ.char_ob
                    if not targ:
                        caller.msg("They have no character to assign to.")
                        return
                    cap = self.get_guard_cap(targ)
                    if targ.num_guards + amt > cap:
                        caller.msg(
                            "They can only have %s guards assigned to them." % cap
                        )
                        return
                    avail_agent.assign(targ, amt)
                    if avail_agent.unique:
                        self.msg("Assigned %s to %s." % (avail_agent, targ))
                    else:
                        caller.msg(
                            "Assigned %s %s to %s." % (amt, avail_agent.name, targ)
                        )
                    return
                except ValueError as err:
                    caller.msg(err)
                    return
            except Agent.DoesNotExist:
                caller.msg("%s owns no agents by that name." % owner_names)
                agents = Agent.objects.filter(owner_id__in=owner_ids)
                caller.msg(
                    "{wAgents:{n %s"
                    % ", ".join("%s (#%s)" % (agent.name, agent.id) for agent in agents)
                )
                return
            except ValueError:
                caller.msg(
                    "Invalid usage: provide player, ID, and amount, separated by commas."
                )
                return
        if "recall" in self.switches:
            try:
                pname, pid, amt = self.lhslist
                player = caller.search(pname)
                if not player:
                    caller.msg("No player found by %s." % pname)
                    return
                amt = int(amt)
                pid = int(pid)
                if amt < 1:
                    raise ValueError
                agent = Agent.objects.get(id=pid)
                if agent.owner.id not in owner_ids:
                    self.msg(
                        "They are owned by %s, and must be recalled from their barracks."
                        % agent.owner
                    )
                    return
                # look through our agent actives for a dbobj assigned to player
                agentob = agent.find_assigned(player)
                if not agentob:
                    caller.msg(
                        "No agents assigned to %s by %s." % (player, owner_names)
                    )
                    return
                num = agentob.recall(amt)
                if agent.unique:
                    caller.msg("You have recalled %s from %s." % (agent, player))
                else:
                    caller.msg(
                        "You have recalled %s from %s. They have %s left."
                        % (num, player, agentob.quantity)
                    )
                return
            except Agent.DoesNotExist:
                caller.msg("No agents found for those arguments.")
                return
            except ValueError:
                caller.msg("Amount and ID must be positive numbers.")
                return
        if "hire" in self.switches:
            try:
                org = caller.Dominion.current_orgs.get(name__iexact=self.rhs)
                owner = org.assets
            except (AttributeError, Organization.DoesNotExist):
                caller.msg("You are not in an organization by that name.")
                return
            try:
                gtype, level, amt = (
                    self.lhslist[0],
                    int(self.lhslist[1]),
                    int(self.lhslist[2]),
                )
            except (IndexError, TypeError, ValueError):
                caller.msg("Please give the type, level, and amount of agents to buy.")
                return
            if not org.access(caller, "agents"):
                caller.msg("You do not have permission to hire agents for %s." % org)
                return
            types = self.get_allowed_types_from_org(org)
            if gtype not in types:
                caller.msg("%s is not a type %s is allowed to hire." % (gtype, org))
                caller.msg("You can buy: %s" % ", ".join(types))
                return
            if level < 0 or amt < 1:
                self.msg("Level and amt must be positive.")
                return
            gtype_num = get_npc_type(gtype)
            cost = self.get_cost(level)
            cost *= amt
            if owner.military < cost:
                caller.msg(
                    "%s does not enough military resources. Cost was %s."
                    % (owner, cost)
                )
                return
            owner.military -= cost
            owner.save()
            # get or create agents of the appropriate type
            try:
                agent = owner.agents.get(quality=level, type=gtype_num)
            except Agent.DoesNotExist:
                gname, gdesc = generate_default_name_and_desc(gtype_num, level, org)
                agent = owner.agents.create(
                    quality=level, type=gtype_num, name=gname, desc=gdesc
                )
            except Agent.MultipleObjectsReturned:
                agent = owner.agents.filter(quality=level, type=gtype_num)[0]
            agent.quantity += amt
            agent.save()
            caller.msg("You bought %s, and now have %s." % (amt, agent))
            return
        if (
            "desc" in self.switches
            or "name" in self.switches
            or "transferowner" in self.switches
        ):
            try:
                agent = Agent.objects.get(id=int(self.lhslist[0]))
                strval = self.rhs
                if not agent.access(caller, "agents"):
                    caller.msg("No access.")
                    return
                if "desc" in self.switches:
                    attr = "desc"
                    strval = strval or ", ".join(self.lhslist[1:])
                    agent.desc = strval
                elif "name" in self.switches:
                    strval = strval or ", ".join(self.lhslist[1:])
                    name = strval
                    if not validate_name(name):
                        self.msg("That is not a valid name.")
                        return
                    agent.set_name(name)
                    self.msg("Name changed to %s" % name)
                    return
                elif "transferowner" in self.switches:
                    attr = "owner"
                    strval = self.lhslist[1]
                    try:
                        agent.owner = AssetOwner.objects.get(
                            Q(player__player__username__iexact=self.lhslist[1])
                            | Q(organization_owner__name__iexact=self.lhslist[1])
                        )
                        if agent.unique:
                            agent.dbobj.unassign()
                            try:
                                char = agent.owner.player.player.char_ob
                                agent.assign(char, 1)
                            except AttributeError:
                                pass
                    except AssetOwner.DoesNotExist:
                        self.msg("No owner found by that name to transfer to.")
                        return
                else:
                    self.msg("Invalid attr")
                    return
                agent.save()
                # do we need to do any refresh_from_db calls here to prevent sync errors with stale foreignkeys?
                caller.msg("Changed %s to %s." % (attr, strval))
                if attr == "owner":
                    agent.owner.inform_owner(
                        "You have been transferred ownership of %s from %s."
                        % (agent, caller),
                        category="agents",
                    )
                return
            except IndexError:
                self.msg("Wrong number of arguments.")
            except (TypeError, ValueError):
                self.msg("Wrong type of arguments.")
            except Agent.DoesNotExist:
                caller.msg("No agent found by that number.")
                return
        self.msg("Unrecognized switch.")


class CmdRetainers(ArxPlayerCommand):
    """
    @retainers

    Usage:
        @retainers
        @retainers/create <name>,<type>
        @retainers/train <owner>=<retainer name>
        @retainers/transferxp <id #>=<xp>[,retainer ID]
        @retainers/buyability <id #>=<ability>
        @retainers/buyskill <id #>=<skill>
        @retainers/buylevel <id #>=<field>
        @retainers/buystat <id #>=<stat>
        @retainers/upgradeweapon <id #>=<field>
        @retainers/changeweaponskill <id #>=<skill>
        @retainers/upgradearmor <id #>
        @retainers/desc <id #>=<new description>
        @retainers/name <id #>=<new name>
        @retainers/customize <id #>=<trait name>,<value>
        @retainers/viewstats <id #>
        @retainers/cost <id #>=<attribute>,<category>
        @retainer/delete <id #>

    Allows you to create and train unique agents that serve you,
    called retainers. They are still agents, and use the @agents
    command to set their name and description. They can be summoned
    in-game through the use of the +guards command while in your home.

    Retainers may be five types: champion, assistant, spy, animal, or
    small animal. Small animals are essentially pets that may be trained
    to perform tasks such as carrying messages, but no combat ability.
    Champions are guards and protectors. Non-small animals are assumed to
    be any large animal that can serve as a guardian or a mount. Assistants
    provide personal assistance in everyday tasks and adventures outside
    of combat. Spies may assist in criminal or sneaky activities.

    @retainers are upgraded through transfer of XP and the expenditure
    of resources. XP transferred to @retainers is multiplied by three,
    making it far easier (but much more expensive) to have skilled
    retainers. Changing the name, desc, or cosmetic traits of a retainer
    is free. The cost of a new retainer is 100 resources, with champions
    and large animals requiring military, assistants using economic, and
    spies requiring social. Small animals, due to their limited use, only
    cost 25 social resources.

    /delete will remove a retainer that you own forever.
    """

    key = "@retainers"
    aliases = ["@retainer"]
    locks = "cmd:all()"
    help_category = "Dominion"
    # cost of a new retainer in resources
    new_retainer_cost = 100
    retainer_types = ("champion", "assistant", "spy", "animal", "small animal")
    valid_traits = (
        "breed",
        "gender",
        "age",
        "hair_color",
        "eye_color",
        "skin_tone",
        "height",
    )
    valid_categories = ("skill", "stat", "ability", "level", "armor", "weapon")

    def get_agent_from_args(self, args):
        """Get our retainer's Agent model from an ID number in args"""
        if args.isdigit():
            return self.caller.retainers.get(id=args)
        return self.caller.retainers.get(agent_objects__dbobj__db_key__iexact=args)

    def display_retainers(self):
        """
        Displays retainers the player owns
        """
        agents = self.caller.retainers
        self.msg(
            "{WYour retainers:{n\n%s"
            % "".join(agent.display(caller=self.caller) for agent in agents),
            options={"box": True},
        )
        return

    def view_stats(self, agent):
        """Views the stats for a retainer"""
        char = agent.dbobj
        self.msg(agent.display())
        char.view_stats(self.caller, combat=True)

    def create_new_retainer(self):
        """
        Create a new retainer that will be attached to the assetowner
        object of the caller. The cost will be in resources determined
        by the type passed by arguments.
        """
        caller = self.caller
        try:
            aname, atype = self.lhslist[0], self.lhslist[1]
        except IndexError:
            caller.msg("You must provide both a name and a type for your new retainer.")
            return
        atype = atype.lower()
        if atype not in self.retainer_types:
            caller.msg(
                "The type of retainer must be one of the following: %s"
                % ", ".join(self.retainer_types)
            )
            return
        cost = self.new_retainer_cost
        if atype == "champion" or atype == "animal":
            rtype = "military"
        elif atype == "spy" or atype == "small animal":
            rtype = "social"
            if atype == "small animal":
                cost /= 4
        elif atype == "assistant":
            rtype = "economic"
        else:
            rtype = "military"

        if not caller.pay_resources(rtype, cost):
            caller.msg("You do not have enough %s resources." % rtype)
            return
        # all checks passed, and we've paid the cost. Create a new agent
        npc_type = get_npc_type(atype)
        desc = "An agent belonging to %s." % caller
        agent = caller.Dominion.assets.agents.create(
            type=npc_type, quality=0, name=aname, quantity=1, unique=True, desc=desc
        )
        caller.msg("You have created a new %s named %s." % (atype, aname))
        agent.assign(caller.char_ob, 1)
        caller.msg("Assigning %s to you." % aname)
        self.msg(
            "You now have a new agent. You can return to your home to summon them with the +guard command."
        )
        # sets its name and saves it
        agent.set_name(aname)
        return

    def train_retainer(self):
        """
        Trains a retainer belonging to a player
        """
        self.caller.execute_cmd("train/retainer %s" % self.args)

    def transfer_xp(self, agent):
        """
        Transfers xp to a retainer. All retainer upgrades cost xp and
        resources. XP transferred to a retainer is multiplied to make
        it appealing to dump xp on them rather than spend it personally.
        """
        if len(self.rhslist) < 2:
            char = self.caller.char_ob
            xp_multiplier = 3
            increase_training_cap = True
        else:
            try:
                char = self.get_agent_from_args(self.rhslist[1])
                xp_multiplier = 1
            except (Agent.DoesNotExist, ValueError):
                self.msg("Could not find an agent by those args.")
                return
            increase_training_cap = False
        try:
            amt = int(self.rhslist[0])
            if amt < 1:
                raise ValueError
        except (TypeError, ValueError):
            self.msg(
                "You must specify a positive xp value to transfer to your retainer."
            )
            return
        if char.xp < amt:
            self.msg("You want to transfer %s xp, but only have %s." % (amt, char.xp))
            return
        if hasattr(char, "xp_transfer_cap"):
            if amt > char.xp_transfer_cap:
                self.msg(
                    "You are trying to transfer %s xp and their transfer cap is %s."
                    % (amt, char.xp_transfer_cap)
                )
                return
            self.adjust_transfer_cap(char, -amt)
        char.adjust_xp(-amt)
        self.msg("%s has %s xp remaining." % (char, char.xp))
        amt *= xp_multiplier
        agent.adjust_xp(amt)
        self.adjust_transfer_cap(agent, amt)
        if increase_training_cap and agent.dbobj.uses_training_cap:
            agent.xp_training_cap += amt
            self.msg(
                "The training cap of %s is now %s xp." % (agent, agent.xp_training_cap)
            )
        self.msg("%s now has %s xp to spend." % (agent, agent.xp))
        return

    def adjust_transfer_cap(self, agent, amt):
        """Changes the xp transfer cap for an agent"""
        agent.xp_transfer_cap += amt
        self.msg("%s's xp transfer cap is now %s." % (agent, agent.xp_transfer_cap))

    # ------ Helper methods for performing pre-purchase checks -------------
    def check_categories(self, category):
        """Helper method for displaying categories"""
        if category not in self.valid_categories:
            self.msg(
                "%s is not a valid choice. It must be one of the following: %s"
                % (category, ", ".join(self.valid_categories))
            )
            return False
        return True

    def get_attr_from_args(self, agent, category="stat"):
        """
        Helper method that returns the attr that the player is buying
        or displays a failure message and returns None.
        """

        if not self.check_categories(category):
            return
        rhs = self.rhs
        if category == "level" and not rhs:
            rhs = agent.type_str
        if not rhs:
            if category == "ability":
                self.msg(
                    "Ability must be one of the following: %s"
                    % ", ".join(agent.buyable_abilities)
                )
                return
            self.msg("You must provide the name of what you want to purchase.")
            return
        attr = rhs.lower()
        if category == "stat":
            stat_names = Trait.get_valid_stat_names()
            if attr not in stat_names:
                self.msg(
                    "When buying a stat, it must be one of the following: %s"
                    % ", ".join(stat_names)
                )
                return
            return attr
        if category == "skill":
            skill_names = Trait.get_valid_skill_names()
            if attr not in skill_names:
                self.msg(
                    "When buying a skill, it must be one of the following: %s"
                    % ", ".join(skill_names)
                )
                return
            return attr
        if category == "ability":
            if attr not in agent.buyable_abilities:
                self.msg(
                    "Ability must be one of the following: %s"
                    % ", ".join(agent.buyable_abilities)
                )
                return
            return attr
        if category == "level":
            if attr not in self.retainer_types:
                self.msg(
                    "The type of level to buy must be one of the following: %s"
                    % ", ".join(self.retainer_types)
                )
                return
            return "%s_level" % attr
        if category == "armor":
            return "armor"
        if category == "weapon":
            try:
                cats = ("weapon_damage", "difficulty_mod")
                attr = self.rhslist[0]
                if attr not in cats:
                    self.msg("Must specify one of the following: %s" % ", ".join(cats))
                    return
            except IndexError:
                self.msg("Must specify a weapon field, and the weapon category.")
                return
            return attr

    def pay_resources(self, res_cost, res_type):
        """Attempts to pay resources"""
        if not self.caller.pay_resources(res_type, res_cost):
            self.msg(
                "You do not have enough %s resources. You need %s."
                % (res_type, res_cost)
            )
            return False
        return True

    def pay_xp_and_resources(self, agent, xp_cost, res_cost, res_type):
        """Attempts to pay xp and resource costs"""
        if xp_cost > agent.xp:
            self.msg("Cost is %s and they only have %s xp." % (xp_cost, agent.xp))
            return False
        if not self.pay_resources(res_cost, res_type):
            return False
        agent.xp -= xp_cost
        agent.save()
        self.msg(
            "You pay %s %s resources and %s %s's xp."
            % (res_cost, res_type, xp_cost, agent)
        )
        return True

    def check_max_for_attr(self, agent, attr, category):
        """Checks the maximum allowed for an agent's traits"""
        a_max = agent.get_attr_maximum(attr, category)
        current = self.get_attr_current_value(agent, attr, category)
        if current >= a_max:
            self.msg(
                "Their level in %s is currently %s, the maximum is %s."
                % (attr, current, a_max)
            )
            return False
        return True

    def get_attr_current_value(self, agent, attr, category):
        """Checks the current value for an agent's trait"""
        if not self.check_categories(category):
            return
        if category == "level":
            current = agent.dbobj.attributes.get(attr) or 0
        elif category == "armor":
            current = agent.dbobj.traits.armor_class
        elif category == "stat":
            current = agent.dbobj.traits.get_stat_value(attr)
        elif category == "skill":
            current = agent.dbobj.traits.get_skill_value(attr)
        elif category == "weapon":
            current = agent.dbobj.fakeweapon.get(attr, 0)
        elif category == "ability":
            current = agent.dbobj.traits.get_ability_value(attr)
        else:
            raise ValueError("Undefined category")
        return current

    def get_attr_cost(self, agent, attrname, category, current=None):
        """
        Determines the xp cost, resource cost, and type of resources based
        on the type of attribute we're trying to raise.
        """
        atype = agent.type_str
        xpcost = 0
        rescost = 0
        restype = "military"
        if current is None:
            current = self.get_attr_current_value(agent, attrname, category)
        newrating = current + 1
        if category == "level":
            base = (newrating * newrating * 5) + 25
            # increase the cost if not raising our primary type
            if atype not in attrname:
                base *= 2
            xpcost = base
            rescost = base
            if atype == self.retainer_types[1]:  # assistant
                restype = "economic"
            if atype == self.retainer_types[2]:  # spy
                restype = "social"
        if category == "skill":
            xpcost, rescost, restype = agent.get_skill_cost(attrname)
        if category == "stat":
            xpcost, rescost, restype = agent.get_stat_cost(attrname)
        if category == "ability":
            xpcost, rescost, restype = agent.get_ability_cost(attrname)
        if category == "armor":
            xpcost = newrating
            rescost = newrating
        if category == "weapon":
            if attrname == "weapon_damage":
                xpcost = newrating * newrating * 10
                rescost = newrating * newrating * 20
            elif attrname == "difficulty_mod":
                xpcost = newrating * 50
                rescost = newrating * 100
        return xpcost, rescost, restype

    # ----- Upgrade methods that use the purchase checks -------------------

    def buy_ability(self, agent):
        """
        Buys a command/ability for a retainer. Available commands are limited
        by the levels we have in the different categories available.
        """
        attr = self.get_attr_from_args(agent, category="ability")
        if not attr:
            return
        if not self.check_max_for_attr(agent, attr, category="ability"):
            return
        current = agent.dbobj.traits.get_ability_value(attr)
        xp_cost, res_cost, res_type = self.get_attr_cost(
            agent, attr, "ability", current
        )
        if not self.pay_xp_and_resources(agent, xp_cost, res_cost, res_type):
            return
        newval = current + 1
        agent.dbobj.traits.set_ability_value(attr, newval)
        self.msg("You have increased %s to %s." % (attr, newval))

    def buy_skill(self, agent):
        """
        Increase one of the retainer's skills. Maximum is determined by our
        level in one of the categories available.
        """
        attr = self.get_attr_from_args(agent, category="skill")
        if not attr:
            return
        if not self.check_max_for_attr(agent, attr, category="skill"):
            return
        current = agent.dbobj.traits.get_skill_value(attr)
        xp_cost, res_cost, res_type = self.get_attr_cost(agent, attr, "skill", current)
        if not self.pay_xp_and_resources(agent, xp_cost, res_cost, res_type):
            return
        newval = current + 1
        agent.dbobj.traits.set_skill_value(attr, newval)
        self.msg("You have increased %s to %s." % (attr, newval))

    def buy_stat(self, agent):
        """
        Increase one of the retainer's stats. Maximum is determined by our
        quality level.
        """
        attr = self.get_attr_from_args(agent)
        if not attr:
            return
        if not self.check_max_for_attr(agent, attr, category="stat"):
            return
        current = agent.dbobj.traits.get_stat_value(attr)
        xp_cost, res_cost, res_type = self.get_attr_cost(agent, attr, "stat", current)
        if not self.pay_xp_and_resources(agent, xp_cost, res_cost, res_type):
            return
        newval = current + 1
        agent.dbobj.traits.set_stat_value(attr, newval)
        self.msg("You have increased %s to %s." % (attr, newval))

    def buy_level(self, agent):
        """
        Increases one of the retainer's levels. If its our main category,
        raise our rating.
        """
        attrname = self.get_attr_from_args(agent, category="level")
        if not attrname:
            return
        if not self.check_max_for_attr(agent, attrname, category="level"):
            return
        current = agent.dbobj.attributes.get(attrname) or 0
        # check and pay costs
        xp_cost, res_cost, res_type = self.get_attr_cost(
            agent, attrname, "level", current
        )
        if not self.pay_xp_and_resources(agent, xp_cost, res_cost, res_type):
            return
        # all checks passed, increase it and raise quality if it was our main category
        agent.dbobj.attributes.add(attrname, current + 1)
        if agent.type_str in attrname:
            agent.quality += 1
            agent.save()
        self.msg("You have raised %s to %s" % (attrname, current + 1))

    def upgrade_weapon(self, agent):
        """
        Upgrade/buy a fake weapon for the agent. Should be significantly cheaper
        than using resources to buy the same sort of weapon for a player.
        """
        fields = ("weapon_damage", "difficulty_mod")
        if self.rhs not in fields:
            self.msg("You must specify one of the following: %s" % ", ".join(fields))
            return
        fake = agent.dbobj.fakeweapon
        current = fake.get(self.rhs, 0)
        if self.rhs == "difficulty_mod":
            current *= -1
            if current < 0:
                current = 0
        if not self.check_max_for_attr(agent, self.rhs, category="weapon"):
            return
        xp_cost, res_cost, res_type = self.get_attr_cost(
            agent, self.rhs, "weapon", current
        )
        if not self.pay_xp_and_resources(agent, xp_cost, res_cost, res_type):
            return
        newval = current + 1
        if self.rhs == "difficulty_mod":
            newval *= -1
        fake[self.rhs] = newval
        agent.dbobj.fakeweapon = fake
        agent.dbobj.combat.setup_weapon(fake)
        self.msg("You have raised %s's %s to %s." % (agent, self.rhs, newval))
        return

    def change_weapon_skill(self, agent):
        """
        Changes the weapon skill of agent's dbobj's fakeweapon

        Args:
            agent: Agent to modify
        """
        valid_skills = ("small wpn", "medium wpn", "huge wpn", "archery", "brawl")
        if self.rhs not in valid_skills:
            self.msg(
                "Weapon skill must be one of following: %s" % ", ".join(valid_skills)
            )
            return
        fake = agent.dbobj.fakeweapon
        fake["attack_skill"] = self.rhs
        agent.dbobj.fakeweapon = fake
        self.msg("%s will now use %s as their weapon skill." % (agent, self.rhs))

    def upgrade_armor(self, agent):
        """
        Upgrade/buy fake armor for the agent. Significantly cheaper than the same
        sort of armor would be for a real character. They can only raise 1 point
        of armor at a time, which is kind of tedious but allows us to easily
        have increasing costs.
        """
        current = agent.dbobj.traits.armor_class
        if not self.check_max_for_attr(agent, "armor", category="armor"):
            return
        xp_cost, res_cost, res_type = self.get_attr_cost(
            agent, "armor", "armor", current
        )
        if not self.pay_xp_and_resources(agent, xp_cost, res_cost, res_type):
            return
        agent.dbobj.traits.set_other_value("armor_class", current + 1)
        self.msg("You have raised %s's armor to %s." % (agent, current + 1))
        return

    # Cosmetic methods

    def change_desc(self, agent):
        """Changes description field of agent"""
        caller_change_field(self.caller, agent, "desc", self.rhs)
        return

    def change_name(self, agent):
        """Changes an agent's name"""
        old = agent.name
        name = self.rhs
        if not validate_name(name):
            self.msg("That is not a valid name.")
            return
        agent.set_name(name)
        self.msg("Name changed from %s to %s." % (old, self.rhs))
        return

    def customize(self, agent):
        """Changes other cosmetic attributes for agent"""
        try:
            attr, val = self.rhslist[0], self.rhslist[1]
        except (TypeError, ValueError, IndexError):
            self.msg("Please provide an trait and a value.")
            self.msg("Valid trait: %s" % ", ".join(self.valid_traits))
            return
        if attr not in self.valid_traits:
            self.msg(
                "Trait to customize must be one of the following: %s"
                % ", ".join(self.valid_traits)
            )
            return
        if attr != "age":
            agent.dbobj.item_data.check_value_allowed_for_race(attr, val)
        agent.dbobj.item_data.set_sheet_value(attr, val)
        self.msg("%s's %s set to %s." % (agent, attr, val))

    def delete(self, agent):
        """Deletes an agent"""
        if not self.caller.ndb.remove_agent_forever == agent:
            self.caller.ndb.remove_agent_forever = agent
            self.msg(
                "You wish to remove %s forever. Use the command again to confirm."
                % agent
            )
            return
        dbobj = agent.dbobj
        dbobj.softdelete()
        dbobj.unassign()
        agent.owner = None
        agent.save()
        self.msg("%s has gone to live with a nice farm family." % dbobj)

    def func(self):
        """Executes retainer command"""
        try:
            caller = self.caller
            if not self.args:
                self.display_retainers()
                return
            if "create" in self.switches:
                self.create_new_retainer()
                return
            if "train" in self.switches:
                self.train_retainer()
                return
            # methods that require an agent below
            try:
                agent = self.get_agent_from_args(self.lhs)
            except (Agent.DoesNotExist, ValueError, TypeError):
                caller.msg("No agent found that matches %s." % self.lhs)
                self.msg("Your current retainers:")
                self.display_retainers()
                return
            if "transferxp" in self.switches:
                self.transfer_xp(agent)
                return
            if "buyability" in self.switches:
                self.buy_ability(agent)
                return
            if "buyskill" in self.switches:
                self.buy_skill(agent)
                return
            if "buylevel" in self.switches:
                self.buy_level(agent)
                return
            if "buystat" in self.switches:
                self.buy_stat(agent)
                return
            if "upgradeweapon" in self.switches:
                self.upgrade_weapon(agent)
                return
            if "changeweaponskill" in self.switches:
                self.change_weapon_skill(agent)
                return
            if "upgradearmor" in self.switches:
                self.upgrade_armor(agent)
                return
            if "desc" in self.switches:
                self.change_desc(agent)
                return
            if "name" in self.switches:
                self.change_name(agent)
                return
            if "customize" in self.switches:
                self.customize(agent)
                return
            if "viewstats" in self.switches or "sheet" in self.switches:
                self.view_stats(agent)
                return
            if "cost" in self.switches:
                if len(self.rhslist) != 2:
                    self.msg("@retainers/cost <agent ID>=<attribute>,<category>")
                    self.check_categories("")
                    return
                category = self.rhslist[1]
                if not self.check_categories(category):
                    return
                # noinspection PyAttributeOutsideInit
                self.rhs = self.rhslist[0]
                attr = self.get_attr_from_args(agent, category)
                if not attr:
                    return
                current = self.get_attr_current_value(agent, attr, category)
                xpcost, rescost, restype = self.get_attr_cost(
                    agent, attr, category, current
                )
                self.msg(
                    "Raising %s would cost %s xp, %s %s resources."
                    % (attr, xpcost, rescost, restype)
                )
                return
            if "delete" in self.switches:
                self.delete(agent)
                return
            caller.msg("Invalid switch.")
        except self.error_class as err:
            self.msg(err)


class CmdGuards(ArxCommand):
    """
    +guards

    Usage:
        +guards
        +guards/summon <name>
        +guards/dismiss <name>
        +guards/attack <guard>=<victim>
        +guards/kill <guard>=<victim>
        +guards/stop <guard>
        +guards/follow <guard>=<person to follow>
        +guards/passive <guard>
        +guard/get <guard>=<object>
        +guard/give <guard>=<object> to <receiver>
        +guard/inventory <guard>
        +guard/discreet <guard>

    Controls summoned guards or retainers. Guards that belong to a
    player may be summoned from their home, while guards belonging
    to an organization may be summoned from their barracks. Dismissing
    them will cause the guards to temporarily leave, and they may be
    resummoned from close to that location. Guards will automatically
    attempt to protect their owner unless they are marked as passive,
    which may be toggled with the /passive switch. Some types of agents,
    such as small animals or assistants, are passive by default. Guards
    that are docked in your room from being dismissed or having logged
    out in that location will be automatically resummoned upon login
    unless the /discreet flag is set.
    """

    key = "+guards"
    locks = "cmd:all()"
    help_category = "Dominion"
    aliases = ["@guards", "guards", "+guard", "@guard", "guard"]

    def func(self):
        """Executes guard command"""
        caller = self.caller
        guards = caller.guards
        if not guards:
            caller.msg("You have no guards assigned to you.")
            return
        if not self.args and not self.switches:
            self.msg(
                "{WYour guards:{n\n%s"
                % "".join(
                    guard.agent.display() if guard.agent.unique else guard.display()
                    for guard in guards
                ),
                options={"box": True},
            )
            return
        if self.args:
            guard = ObjectDB.objects.object_search(
                self.lhs, candidates=guards, exact=False
            )
            if not guard:
                try:
                    guard = self.caller.player_ob.retainers.get(id=int(self.lhs)).dbobj
                except (Agent.DoesNotExist, ValueError, AttributeError):
                    _AT_SEARCH_RESULT(guard, caller, self.lhs)
                    return
            else:
                guard = guard[0]
        else:
            if len(guards) > 1:
                caller.msg("You must specify which guards.")
                for guard in guards:
                    caller.msg(guard.display())
                return
            guard = guards[0]
        if not self.switches:
            guard.display()
            return
        if "summon" in self.switches:
            if guard.location == caller.location:
                caller.msg("They are already here.")
                return
            # check maximum guards and how many we have
            current = caller.num_armed_guards + guard.num_armed_guards
            g_max = caller.max_guards
            if current > g_max:
                self.msg(
                    "You are only permitted to have %s guards, and summoning them would give you %s."
                    % (g_max, current)
                )
                return
            if not guard.item_data.guarding:
                self.msg("They are unassigned.")
                return
            loc = guard.location or guard.item_data.pre_offgrid_location
            if loc and caller.location == loc:
                guard.summon()
                return
            tagname = str(guard.agentob.agent_class.owner.owner) + "_barracks"
            barracks = ObjectDB.objects.filter(db_tags__db_key__iexact=tagname)
            if caller.location in barracks:
                guard.summon()
                return
            # if they're only one square away
            if loc and caller.location.locations_set.filter(db_destination_id=loc.id):
                guard.summon()
                return
            if caller.location == caller.home:
                guard.summon()
                return
            caller.msg(
                "Your guards aren't close enough to summon. They are at %s." % loc
            )
            return
        # after this point, need guards to be with us.
        if guard.location != caller.location:
            caller.msg(
                "Your guards are not here to receive commands. You must summon them to you first."
            )
            return
        if "dismiss" in self.switches:
            guard.dismiss()
            caller.msg("You dismiss %s." % guard.name)
            return
        if "stop" in self.switches:
            guard.stop()
            caller.msg("You order your guards to stop what they're doing.")
            return
        if "passive" in self.switches:
            current = guard.passive
            if current:
                guard.passive = False
                self.msg("%s will now actively protect you." % guard.name)
                return
            guard.passive = True
            self.msg("%s will no longer actively protect you." % guard.name)
            return
        if "discreet" in self.switches:
            current = guard.discreet
            if current:
                guard.discreet = False
                self.msg(
                    "%s will now be automatically summoned upon login if they are in your space."
                    % guard.name
                )
                return
            guard.discreet = True
            self.msg(
                "%s will no longer be automatically summoned upon login if they are in your space."
                % guard.name
            )
            return
        if "inventory" in self.switches:
            objects = guard.contents
            self.msg(
                "{c%s's {winventory:{n %s"
                % (guard, ", ".join(ob.name for ob in objects))
            )
            return
        if "give" in self.switches:
            self.msg("You order %s to give %s." % (guard, self.rhs))
            guard.execute_cmd("give %s" % self.rhs)
            return
        if "get" in self.switches:
            self.msg("You order %s to get %s." % (guard, self.rhs))
            guard.execute_cmd("get %s" % self.rhs)
            return
        targ = caller.search(self.rhs)
        if not targ:
            return
        if "attack" in self.switches:
            guard.attack(targ)
            caller.msg("You order %s to attack %s." % (guard.name, targ.name))
            return
        if "kill" in self.switches:
            guard.attack(targ, kill=True)
            caller.msg("You order %s to kill %s." % (guard.name, targ.name))
            return
        if "follow" in self.switches:
            guard.stop_follow(dismiss=False)
            guard.follow(targ)
            caller.msg("You order %s to follow %s." % (guard.name, targ.name))
            return
