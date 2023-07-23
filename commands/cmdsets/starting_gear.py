"""
This commandset attempts to define the combat state.
Combat in Arx isn't designed to mimic the real-time
nature of MMOs, or even a lot of MUDs. Our model is
closer to tabletop RPGs - a turn based system that
can only proceed when everyone is ready. The reason
for this is that having 'forced' events based on a
time limit, while perfectly appropriate for a video
game, is unacceptable when attempting to have a game
that is largely an exercise in collaborative story-
telling. It's simply too disruptive, and often creates
situations that are damaging to immersion and the
creative process.
"""
from world.dominion.setup_utils import setup_dom_for_char
from evennia import CmdSet
from evennia.utils.logger import log_info
from commands.base import ArxCommand, ArxPlayerCommand
from server.utils import arx_utils
from world.crafting.models import (
    CraftingMaterialType,
    CraftingRecipe,
)
from world.dominion.models import (
    PlayerOrNpc,
    AssetOwner,
)
from commands.base_commands.crafting import (
    create_decorative_weapon,
    create_wearable,
    create_weapon,
    create_place,
    create_container,
    create_wearable_container,
    create_generic,
    PERFUME,
    create_mask,
    create_consumable,
)

CASH = 6000


class StartingGearCmdSet(CmdSet):
    """CmdSet for a market."""

    key = "StartingGearCmdSet"
    priority = 101
    duplicates = False
    no_exits = False
    no_objs = False

    def at_cmdset_creation(self):
        """
        This is the only method defined in a cmdset, called during
        its creation. It should populate the set with command instances.

        Note that it can also take other cmdsets as arguments, which will
        be used by the character default cmdset to add all of these onto
        the internal cmdset stack. They will then be able to removed or
        replaced as needed.
        """
        self.add(CmdStartingGear())


class CmdStartingGear(ArxCommand):
    """
    startgear
    Usage:
        startgear
        startgear <recipe name>
        startgear/name
        startgear/adorn <type of material>=<amount>
        startgear/desc
        startgear/altdesc
        startgear/abandon
        startgear/finish
        startgear/refundremainder

    Used to create and customize your starting objects. Select an
    object to create based on the recipe name, then set its name and
    desc before using /finish. Once you have crafted all you choose,
    you can cash in the remainder of your starting funds with
    /refundremainder, which removes this command permanently.
    For a list of valid recipes, please look at:
    http://play.arxmush.org/topics/recipes/

    Note that the silver cost is an additional cost on top of the
    cost of materials, so the actual cost of an item is far higher
    than seen there. You must add in the cost of the materials
    listed on the page for an accurate cost of crafting an item.
    """

    key = "startgear"
    locks = "cmd:all()"
    help_category = "Progression"

    @staticmethod
    def display_project(proj):
        """
        Project is a list of data related to what a character
        is crafting. (recipeid, name, desc, adorns, forgerydict)
        """
        recipe = CraftingRecipe.objects.get(id=proj[0])
        msg = "{wRecipe:{n %s\n" % recipe.name
        msg += "{wName:{n %s\n" % proj[1]
        msg += "{wDesc:{n %s\n" % proj[2]
        if proj[4]:
            msg += "{wAlt Desc:{n %s\n" % proj[4]
        adorns = proj[3]
        if adorns:
            msg += "{wAdornments:{n %s\n" % ", ".join(
                "%s: %s" % (CraftingMaterialType.objects.get(id=mat).name, amt)
                for mat, amt in adorns.items()
            )
        return msg

    def func(self):
        """Implement the command"""
        caller = self.caller
        try:
            dompc = PlayerOrNpc.objects.get(player=caller.player)
            AssetOwner.objects.get(player=dompc)
        except PlayerOrNpc.DoesNotExist:
            # dominion not set up on player
            setup_dom_for_char(caller)
        except AssetOwner.DoesNotExist:
            # assets not initialized on player
            setup_dom_for_char(caller, create_dompc=False)

        if not self.args and not self.switches:
            project = caller.db.startgear_project
            if project:
                caller.msg(self.display_project(project))
                caller.msg("{wTo finish it, use /finish.")
            caller.msg(
                "You have the equivalent of {w%s{n silver remaining to spend on gear."
                % caller.db.startgear_val
            )
            return
        # start a crafting project
        if not self.switches:
            try:
                recipe = CraftingRecipe.objects.get(name__iexact=self.lhs)
            except CraftingRecipe.DoesNotExist:
                caller.msg("No recipe found by the name %s." % self.lhs)
                return
            # proj = [id, name, desc, adorns, altdesc]
            proj = [recipe.id, "", "", {}, ""]
            cost = recipe.value
            caller.msg("Its cost is {w%s{n." % cost)
            if cost > caller.db.startgear_val:
                caller.msg(
                    "{rYou only have {w%s{r silver remaining for gear.{n"
                    % caller.db.startgear_val
                )
                return
            caller.db.startgear_project = proj
            caller.msg("{wYou have started to craft:{n %s." % recipe.name)
            caller.msg(
                "You will have {w%s{n remaining after finishing."
                % (caller.db.startgear_val - cost)
            )
            caller.msg(
                "{wTo finish it, use /finish after you set its name and description."
            )
            caller.msg("{wTo abandon this, use /abandon.{n")
            return
        proj = caller.db.startgear_project
        if not proj and "refundremainder" not in self.switches:
            caller.msg("You have no crafting project.")
            return
        if "adorn" in self.switches:
            if not (self.lhs and self.rhs):
                caller.msg("Usage: craft/adorn <material>=<amount>")
                return
            try:
                mat = CraftingMaterialType.objects.get(name__iexact=self.lhs)
                amt = int(self.rhs)
            except CraftingMaterialType.DoesNotExist:
                caller.msg("No material named %s." % self.lhs)
                return
            except CraftingMaterialType.MultipleObjectsReturned:
                caller.msg("More than one match. Please be more specific.")
                return
            except (TypeError, ValueError):
                caller.msg("Amount must be a number.")
                return
            if amt < 1:
                caller.msg("Amount must be positive.")
                return
            recipe = CraftingRecipe.objects.get(id=proj[0])
            if not recipe.allow_adorn:
                caller.msg(
                    "This recipe does not allow for additional materials to be used."
                )
                return

            cost = recipe.value
            adorns = proj[3] or {}
            adorns[mat.id] = amt
            for adorn_id in adorns:
                mat = CraftingMaterialType.objects.get(id=adorn_id)
                amt = adorns[adorn_id]
                cost += mat.value * amt
            caller.msg("The cost of your item is now %s." % cost)
            if cost > caller.db.startgear_val:
                caller.msg("You cannot afford those adorns. Removing them all.")
                proj[3] = {}
                return
            proj[3] = adorns
            caller.db.crafting_project = proj
            caller.msg(
                "Additional materials: %s"
                % ", ".join(
                    "%s: %s" % (CraftingMaterialType.objects.get(id=mat).name, amt)
                    for mat, amt in adorns.items()
                )
            )
            return
        if "name" in self.switches:
            if not self.args:
                caller.msg("Name it what?")
                return
            if not arx_utils.validate_name(self.args):
                caller.msg("That is not a valid name.")
                return
            proj[1] = self.args
            caller.db.startgear_project = proj
            caller.msg("Name set to %s." % self.args)
            return
        if "desc" in self.switches:
            if not self.args:
                caller.msg("Name it what?")
                return
            proj[2] = self.args
            caller.db.startgear_project = proj
            caller.msg("Desc set to:\n%s" % self.args)
            return
        if "altdesc" in self.switches:
            if not self.args:
                caller.msg("Describe them how? This is only used for disguise recipes.")
                return
            proj[4] = self.args
            caller.msg(
                "This is only used for disguise recipes. Alternate description set to:\n%s"
                % self.args
            )
            return
        if "abandon" in self.switches or "abort" in self.switches:
            caller.msg(
                "You have abandoned this crafting project. You may now start another."
            )
            caller.attributes.remove("startgear_project")
            return
        # do rolls for our crafting. determine quality level, handle forgery stuff
        if "finish" in self.switches:
            if not proj[1]:
                caller.msg("You must give it a name first.")
                return
            if not proj[2]:
                caller.msg("You must write a description first.")
                return
            # first, check if we have all the materials required
            mats = {}
            recipe = CraftingRecipe.objects.get(id=proj[0])
            cost = recipe.value
            for mat in recipe.required_materials.all():
                mats[mat.type_id] = mats.get(mat.type_id, 0) + mat.amount
            for adorn in proj[3]:
                mats[adorn] = mats.get(adorn, 0) + proj[3][adorn]
                mat = CraftingMaterialType.objects.get(id=adorn)
                cost += mat.value * proj[3][adorn]
            if caller.db.startgear_val < cost:
                caller.msg(
                    "You need %s silver to finish the recipe, and have only %s."
                    % (cost, caller.db.startgear_val)
                )
                return
            caller.db.startgear_val -= cost
            # quality will always be average
            roll = 0
            # get type from recipe
            otype = recipe.type
            # create object
            crafter = caller
            if otype == "wieldable":
                obj, quality = create_weapon(recipe, roll, proj, caller, crafter)
            elif otype == "wearable":
                obj, quality = create_wearable(recipe, roll, proj, caller, crafter)
            elif otype == "place":
                obj, quality = create_place(recipe, roll, proj, caller, crafter)
            elif otype == "container":
                obj, quality = create_container(recipe, roll, proj, caller, crafter)
            elif otype == "decorative_weapon":
                obj, quality = create_decorative_weapon(
                    recipe, roll, proj, caller, crafter
                )
            elif otype == "wearable_container":
                obj, quality = create_wearable_container(
                    recipe, roll, proj, caller, crafter
                )
            elif otype == "perfume":
                obj, quality = create_consumable(
                    recipe, roll, proj, caller, PERFUME, crafter
                )
            elif otype == "disguise":
                obj, quality = create_mask(recipe, roll, proj, caller, proj[6], crafter)
            else:
                obj, quality = create_generic(recipe, roll, proj, caller, crafter)
            # finish stuff universal to all crafted objects
            obj.desc = proj[2]
            obj.save()
            for mat_id, amount in proj[3].items():
                obj.item_data.add_adorn(mat_id, amount)
            caller.msg("You created %s." % obj.name)
            caller.attributes.remove("startgear_project")
            return
        if "refundremainder" in self.switches:
            money = caller.item_data.currency
            refund = caller.db.startgear_val
            money += refund
            caller.attributes.remove("startgear_val")
            caller.item_data.currency = money
            caller.msg("You receive %s silver coins." % refund)
            caller.cmdset.delete(StartingGearCmdSet)
            return
        caller.msg("Invalid switch.")


def setup_gear_for_char(character, money=CASH, reset=False):
    if not reset and "given_starting_gear" in character.tags.all():
        log_info("Startgear aborted for %s" % character)
        return
    character.db.startgear_val = money
    cmds = StartingGearCmdSet
    if cmds.key not in [ob.key for ob in character.cmdset.all()]:
        character.cmdset.add(cmds, permanent=True)
    else:
        log_info("startgear command not added to %s" % character)
    character.tags.add("given_starting_gear")
    log_info("Startgear setup finished for %s" % character)


class CmdSetupGear(ArxPlayerCommand):
    """
    @setupgear
    Usage:
        @setupgear <character>[=<money>]

    Grants starting money to a character to buy their gear and
    adds the startgear command to them to create it.
    """

    key = "@setupgear"
    locks = "cmd:perm(Builders)"
    help_category = "Building"

    def func(self):
        """Implement the command"""
        caller = self.caller
        targ = caller.search(self.lhs)
        if not targ:
            return
        char = targ.char_ob
        if not char:
            caller.msg("No char.")
            return
        if self.rhs:
            setup_gear_for_char(char, int(self.rhs), reset=True)
        else:
            setup_gear_for_char(char, reset=True)
        caller.msg("Starting money for gear granted to %s." % char)
        arx_utils.inform_staff("%s has given %s money for startgear." % (caller, char))
