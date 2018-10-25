"""
Crafting commands. BEHOLD THE MINIGAME.
"""
from django.conf import settings
from server.utils.arx_utils import ArxCommand
from world.dominion.models import (AssetOwner, PlayerOrNpc, CraftingRecipe, CraftingMaterials, CraftingMaterialType)
from world.dominion.setup_utils import setup_dom_for_char
from world.stats_and_skills import do_dice_check
from evennia.utils.create import create_object
from server.utils.prettytable import PrettyTable
from server.utils.arx_utils import validate_name, inform_staff
from evennia.utils import utils
from evennia.utils.utils import make_iter

AT_SEARCH_RESULT = utils.variable_from_module(*settings.SEARCH_AT_RESULT.rsplit('.', 1))

WIELD = "typeclasses.wearable.wieldable.Wieldable"
DECORATIVE_WIELD = "typeclasses.wearable.decorative_weapon.DecorativeWieldable"
WEAR = "typeclasses.wearable.wearable.Wearable"
PLACE = "typeclasses.places.places.Place"
BOOK = "typeclasses.readable.readable.Readable"
CONTAINER = "typeclasses.containers.container.Container"
WEARABLE_CONTAINER = "typeclasses.wearable.wearable.WearableContainer"
BAUBLE = "typeclasses.bauble.Bauble"
PERFUME = "typeclasses.consumable.perfume.Perfume"
MASK = "typeclasses.disguises.disguises.Mask"

QUALITY_LEVELS = {
    0: '{rawful{n',
    1: '{mmediocre{n',
    2: '{caverage{n',
    3: '{cabove average{n',
    4: '{ygood{n',
    5: '{yvery good{n',
    6: '{gexcellent{n',
    7: '{gexceptional{n',
    8: '{gsuperb{n',
    9: '{454perfect{n',
    10: '{553divine{n',
    11: '|355transcendent|n'
    }


def create_weapon(recipe, roll, proj, caller):
    skill = recipe.resultsdict.get("weapon_skill", "medium wpn")
    quality = get_quality_lvl(roll, recipe.difficulty)
    obj = create_obj(WIELD, proj[1], caller, caller, quality)
    obj.db.attack_skill = skill
    if skill == "archery":
        obj.ranged_mode()
    return obj, quality


def create_wearable(recipe, roll, proj, caller):
    quality = get_quality_lvl(roll, recipe.difficulty)
    obj = create_obj(WEAR, proj[1], caller, caller, quality)
    return obj, quality


def create_decorative_weapon(recipe, roll, proj, caller):
    skill = recipe.resultsdict.get("weapon_skill", "small wpn")
    quality = get_quality_lvl(roll, recipe.difficulty)
    obj = create_obj(DECORATIVE_WIELD, proj[1], caller, caller, quality)
    obj.db.attack_skill = skill
    return obj, quality


def create_place(recipe, roll, proj, caller):
    scaling = float(recipe.resultsdict.get("scaling", 0))
    base = int(recipe.resultsdict.get("baseval", 2))
    quality = get_quality_lvl(roll, recipe.difficulty)
    obj = create_obj(PLACE, proj[1], caller, caller, quality)
    obj.db.max_spots = base + int(scaling * quality)
    return obj, quality


def create_book(recipe, roll, proj, caller):
    quality = get_quality_lvl(roll, recipe.difficulty)
    obj = create_obj(BOOK, proj[1], caller, caller, quality)
    return obj, quality


def create_container(recipe, roll, proj, caller):
    scaling = float(recipe.resultsdict.get("scaling", 0))
    base = int(recipe.resultsdict.get("baseval", 2))
    quality = get_quality_lvl(roll, recipe.difficulty)
    obj = create_obj(CONTAINER, proj[1], caller, caller, quality)
    obj.db.max_volume = base + int(scaling * quality)
    if recipe.resultsdict.get("displayable") == "true":
       obj.tags.add("displayable")
    try:
        obj.grantkey(caller)
    except (TypeError, AttributeError, ValueError):
        import traceback
        traceback.print_exc()
    return obj, quality


def create_wearable_container(recipe, roll, proj, caller):
    scaling = float(recipe.resultsdict.get("scaling", 0))
    base = int(recipe.resultsdict.get("baseval", 2))
    quality = get_quality_lvl(roll, recipe.difficulty)
    obj = create_obj(WEARABLE_CONTAINER, proj[1], caller, caller, quality)
    obj.db.max_volume = base + int(scaling * quality)
    try:
        obj.grantkey(caller)
    except (TypeError, AttributeError, ValueError):
        import traceback
        traceback.print_exc()
    return obj, quality


def create_generic(recipe, roll, proj, caller):
    quality = get_quality_lvl(roll, recipe.difficulty)
    obj = create_obj(BAUBLE, proj[1], caller,
                     caller, quality)
    return obj, quality


def create_consumable(recipe, roll, proj, caller, typeclass):
    quality = get_quality_lvl(roll, recipe.difficulty)
    obj = create_obj(typeclass, proj[1], caller,
                     caller, quality)
    return obj, quality


def create_mask(recipe, roll, proj, caller, maskdesc):
    quality = get_quality_lvl(roll, recipe.difficulty)
    obj = create_obj(MASK, proj[1], caller,
                     caller, quality)
    obj.db.maskdesc = maskdesc
    return obj, quality


def create_obj(typec, key, loc, home, quality):
    if "{" in key and not key.endswith("{n"):
        key += "{n"
    obj = create_object(typeclass=typec, key=key, location=loc, home=home)
    obj.db.quality_level = quality
    # will set color name and strip ansi from colorized name for key
    obj.name = key
    return obj


def get_ability_val(char, recipe):
    """
    Returns a character's highest rank in any ability used in the
    recipe.
    """
    ability_list = (recipe.ability or "").split(",")
    abilities = char.db.abilities or {}
    skills = char.db.skills or {}
    if recipe.skill == "artwork":
        return char.db.skills.get("artwork", 0)
    if ability_list == "all" or not ability_list:
        # get character's highest ability
        values = sorted(abilities.values() + [skills.get("artwork", 0)], reverse=True)
        ability = values[0]
    else:
        abvalues = []
        for abname in ability_list:
            abvalues.append(abilities.get(abname, 0))
        ability = sorted(abvalues, reverse=True)[0]
    return ability


def get_highest_crafting_skill(character):
    """Returns the highest crafting skill for character"""
    from world.stats_and_skills import CRAFTING_SKILLS
    skills = character.db.skills or {}
    return max(CRAFTING_SKILLS + ("artwork",), key=lambda x: skills.get(x, 0))


def do_crafting_roll(char, recipe, diffmod=0, diffmult=1.0, room=None):
    diff = int(recipe.difficulty * diffmult) - diffmod
    ability = get_ability_val(char, recipe)
    skill = recipe.skill
    if skill in ("all", "any"):
        skill = get_highest_crafting_skill(char)
    stat = "luck" if char.db.luck > char.db.dexterity else "dexterity"
    can_crit = False
    try:
        if char.roster.roster.name == "Active":
            can_crit = True
    except AttributeError:
        pass
    # use real name if we're not present (someone using our shop, for example). If we're here, use masked name
    real_name = char.location != room
    return do_dice_check(char, stat=stat, difficulty=diff, skill=skill, bonus_dice=ability, quiet=False,
                         announce_room=room, can_crit=can_crit, use_real_name=real_name)


def get_difficulty_mod(recipe, money=0, action_points=0, ability=0):
    from random import randint
    divisor = recipe.value or 0
    if divisor < 1:
        divisor = 1
    val = float(money) / float(divisor)
    # for every 10% of the value of recipe we invest, we knock 1 off difficulty
    val = int(val/0.10) + 1
    if action_points:
        base = action_points / (14 - (2*ability))
        val += randint(base, action_points)
    return val


def get_quality_lvl(roll, diff):
    # roll was against difficulty, so add it for comparison
    roll += diff
    if roll < diff/4:
        return 0
    if roll < (diff * 3)/4:
        return 1
    if roll < diff * 1.2:
        return 2
    if roll < diff * 1.6:
        return 3
    if roll < diff * 2:
        return 4
    if roll < diff * 2.5:
        return 5
    if roll < diff * 3.5:
        return 6
    if roll < diff * 5:
        return 7
    if roll < diff * 7:
        return 8
    if roll < diff * 10:
        return 9
    return 10


def change_quality(crafting_object, new_quality):
    """
    Given a crafted crafting_object, change various attributes in it
    based on its new quality level and recipe.
    """
    recipe = crafting_object.db.recipe
    recipe = CraftingRecipe.objects.get(id=recipe)
    otype = recipe.type
    scaling = float(recipe.resultsdict.get("scaling", 0))
    base = float(recipe.resultsdict.get("baseval", 0))
    if otype == "place":
        crafting_object.db.max_spots = int(base) + int(scaling * new_quality)
    crafting_object.db.quality_level = new_quality
    if hasattr(crafting_object, "calc_weapon"):
        crafting_object.calc_weapon()
    if hasattr(crafting_object, "calc_armor"):
        crafting_object.calc_armor()


class CmdCraft(ArxCommand):
    """
    Crafts an object

    Usage:
        craft
        craft <recipe name>
        craft/name <name>
        craft/desc <description>
        craft/altdesc <description>
        craft/adorn <material type>=<amount>
        craft/translated_text <language>=<text>
        craft/preview [<player>]
        craft/finish [<additional silver to invest>, <action points>
        craft/abandon
        craft/refine <object>[=<additional silver to spend>, <action points>]
        craft/changename <object>=<new name>
        craft/addadorn <object>=<material type>,<amount>

    To start crafting, you must know recipes related to your crafting profession.
    Select a recipe then describe the object with /name and /desc. To add extra
    materials such as gemstones, use /adorn. No materials or silver are used
    until you are ready to /finish the project and make the roll for its quality.

    For things such as perfume, the desc is the description that appears on the
    character, not a description of the bottle. When crafting masks, the name is
    used to identify its wearer: "A Fox Mask" will bestow "Someone wearing A Fox
    Mask" upon its wearer, and the altdesc switch is used for their temporary
    description. For any desc, ascii can be enclosed in <ascii> tags that
    will note to not display them to screenreaders. Use <ascii> and <ascii/> with
    the desc between the opening and closing tags.

    If the item should contain words in a foreign tongue that you know, use
    translated_text to display what the translated words actually say.

    To finish a project, use /finish, or /abandon if you wish to stop and do
    something else. To attempt to change the quality level of a finished object,
    use /refine. Refinement cost is based on how much it took to create, and
    can never make the object worse. Use /addadorn to embellish an item with
    extra materials post-creation.

    Craft with no arguments will display the status of a current project.
    """
    key = "craft"
    locks = "cmd:all()"
    help_category = "Crafting"
    crafter = None
    crafting_switches = ("name", "desc", "altdesc", "adorn", "translated_text", "forgery", "finish", "abandon",
                         "refine", "changename", "addadorn", "preview")

    def get_refine_price(self, base):
        return 0

    def get_recipe_price(self, recipe):
        return 0

    def pay_owner(self, price, msg):
        return

    def display_project(self, proj):
        """
        Project is a list of data related to what a character
        is crafting. (recipeid, name, desc, adorns, forgerydict)
        """
        caller = self.caller
        dompc = caller.player_ob.Dominion
        recipe = CraftingRecipe.objects.get(id=proj[0])
        msg = "{wRecipe:{n %s\n" % recipe.name
        msg += "{wName:{n %s\n" % proj[1]
        msg += "{wDesc:{n %s\n" % proj[2]
        if len(proj) > 6 and proj[6]:
            msg += "{wAlt Desc:{n %s\n" % proj[6]
        adorns, forgery = proj[3], proj[4]
        if adorns:
            msg += "{wAdornments:{n %s\n" % ", ".join("%s: %s" % (CraftingMaterialType.objects.get(id=mat).name, amt)
                                                      for mat, amt in adorns.items())
        if forgery:
            msg += "{wForgeries:{n %s\n" % ", ".join("%s as %s" % (CraftingMaterialType.objects.get(id=value).name,
                                                                   CraftingMaterialType.objects.get(id=key).name)
                                                     for key, value in forgery.items())
        try:
            translation = proj[5]
            if translation:
                msg += "{wTranslation for{n %s\n" % "\n\n".join("%s:\n%s" % (lang, text)
                                                                for lang, text in translation.items())
        except IndexError:
            pass
        caller.msg(msg)
        caller.msg("{wTo finish it, use /finish after you gather the following:{n")
        caller.msg(recipe.display_reqs(dompc))

    def check_max_invest(self, recipe, invest):
        if invest > recipe.value:
            self.msg("The maximum amount you can invest is %s." % recipe.value)
            return
        return True

    def func(self):
        """Implement the command"""
        caller = self.caller
        if not self.crafter:
            self.crafter = caller
        crafter = self.crafter
        try:
            dompc = PlayerOrNpc.objects.get(player=caller.player)
            assets = AssetOwner.objects.get(player=dompc)
        except PlayerOrNpc.DoesNotExist:
            # dominion not set up on player
            dompc = setup_dom_for_char(caller)
            assets = dompc.assets
        except AssetOwner.DoesNotExist:
            # assets not initialized on player
            dompc = setup_dom_for_char(caller, create_dompc=False)
            assets = dompc.assets
        recipes = crafter.player_ob.Dominion.assets.recipes.all()
        if not self.args and not self.switches:
            # display recipes and any crafting project we have unfinished
            materials = assets.materials.all()
            caller.msg("{wAvailable recipes:{n %s" % ", ".join(recipe.name for recipe in recipes))
            caller.msg("{wYour materials:{n %s" % ", ".join(str(mat) for mat in materials))
            project = caller.db.crafting_project
            if project:
                self.display_project(project)
            return
        # start a crafting project
        if not self.switches or "craft" in self.switches:
            try:
                recipe = recipes.get(name__iexact=self.lhs)
            except CraftingRecipe.DoesNotExist:
                caller.msg("No recipe found by the name %s." % self.lhs)
                return
            try:
                self.get_recipe_price(recipe)
            except ValueError:
                caller.msg("That recipe does not have a price defined.")
                return
            # proj = [id, name, desc, adorns, forgery, translation]
            proj = [recipe.id, "", "", {}, {}, {}, ""]
            caller.db.crafting_project = proj
            stmsg = "You have" if caller == crafter else "%s has" % crafter
            caller.msg("{w%s started to craft:{n %s." % (stmsg, recipe.name))
            caller.msg("{wTo finish it, use /finish after you gather the following:{n")
            caller.msg(recipe.display_reqs(dompc))
            return
        if "changename" in self.switches or "refine" in self.switches or "addadorn" in self.switches:
            targ = caller.search(self.lhs, location=caller)
            if not targ:
                return
            recipe = getattr(targ, 'recipe', None)
            if not recipe:
                caller.msg("No recipe found for that item.")
                return
            if "changename" in self.switches:
                if not self.rhs:
                    self.msg("Usage: /changename <object>=<new name>")
                    return
                if not validate_name(self.rhs):
                    caller.msg("That is not a valid name.")
                    return
                if targ.tags.get("plot"):
                    self.msg("It cannot be renamed.")
                    return
                targ.aliases.clear()
                targ.name = self.rhs
                caller.msg("Changed name to %s." % targ)
                return
            # adding adorns post-creation
            if "addadorn" in self.switches:
                try:
                    material = self.rhslist[0]
                    amt = int(self.rhslist[1])
                    if amt < 1 and not caller.check_permstring('builders'):
                        raise ValueError
                except (IndexError, ValueError, TypeError):
                    caller.msg("Usage: /addadorn <object>=<adornment>,<amount>")
                    return
                if not recipe.allow_adorn:
                    caller.msg("This recipe does not allow for additional materials to be used.")
                    return
                try:
                    mat = CraftingMaterialType.objects.get(name__iexact=material)
                except CraftingMaterialType.DoesNotExist:
                    self.msg("Cannot use %s as it does not appear to be a crafting material." % material)
                    return
                # if caller isn't a builder, check and consume their materials
                if not caller.check_permstring('builders'):
                    pmats = caller.player.Dominion.assets.materials
                    try:
                        pmat = pmats.get(type=mat)
                        if pmat.amount < amt:
                            caller.msg("You need %s of %s, and only have %s." % (amt, mat.name, pmat.amount))
                            return
                    except CraftingMaterials.DoesNotExist:
                        caller.msg("You do not have any of the material %s." % mat.name)
                        return
                    pmat.amount -= amt
                    pmat.save()
                targ.add_adorn(mat, amt)
                caller.msg("%s is now adorned with %s of the material %s." % (targ, amt, mat))
                return
            if "refine" in self.switches:
                base_cost = recipe.value / 4
                caller.msg("The base cost of refining this recipe is %s." % base_cost)
                try:
                    price = self.get_refine_price(base_cost)
                except ValueError:
                    caller.msg("Price for refining not set.")
                    return
                if price:
                    caller.msg("The additional price for refining is %s." % price)
                action_points = 0
                invest = 0
                if self.rhs:
                    try:
                        invest = int(self.rhslist[0])
                        if len(self.rhslist) > 1:
                            action_points = int(self.rhslist[1])
                    except ValueError:
                        caller.msg("Amount of silver/action points to invest must be a number.")
                        return
                    if invest < 0 or action_points < 0:
                        caller.msg("Amount must be positive.")
                        return
                if not recipe:
                    caller.msg("This is not a crafted object that can be refined.")
                    return
                if targ.db.quality_level and targ.db.quality_level >= 10:
                    caller.msg("This object can no longer be improved.")
                    return
                ability = get_ability_val(crafter, recipe)
                if ability < recipe.level:
                    err = "You lack" if crafter == caller else "%s lacks" % crafter
                    caller.msg("%s the skill required to attempt to improve this." % err)
                    return
                if not self.check_max_invest(recipe, invest):
                    return
                cost = base_cost + invest + price
                # don't display a random number when they're prepping
                if caller.ndb.refine_targ != (targ, cost):
                    diffmod = get_difficulty_mod(recipe, invest)
                else:
                    diffmod = get_difficulty_mod(recipe, invest, action_points, ability)
                # difficulty gets easier by 1 each time we attempt it
                refine_attempts = crafter.db.refine_attempts or {}
                attempts = refine_attempts.get(targ.id, 0)
                if attempts > 60:
                    attempts = 60
                diffmod += attempts
                if diffmod:
                    self.msg("Based on silver spent and previous attempts, the difficulty is adjusted by %s." % diffmod)
                if caller.ndb.refine_targ != (targ, cost):
                    caller.ndb.refine_targ = (targ, cost)
                    caller.msg("The total cost would be {w%s{n. To confirm this, execute the command again." % cost)
                    return
                if cost > caller.db.currency:
                    caller.msg("This would cost %s, and you only have %s." % (cost, caller.db.currency))
                    return
                if action_points and not caller.player_ob.pay_action_points(action_points):
                    self.msg("You do not have enough action points to refine.")
                    return
                # pay for it
                caller.pay_money(cost)
                self.pay_owner(price, "%s has refined '%s', a %s, at your shop and you earn %s silver." % (caller, targ,
                                                                                                           recipe.name,
                                                                                                           price))

                roll = do_crafting_roll(crafter, recipe, diffmod, diffmult=0.75, room=caller.location)
                quality = get_quality_lvl(roll, recipe.difficulty)
                old = targ.db.quality_level or 0
                attempts += 1
                refine_attempts[targ.id] = attempts
                crafter.db.refine_attempts = refine_attempts
                self.msg("The roll is %s, a quality level of %s." % (roll, QUALITY_LEVELS[quality]))
                if quality <= old:
                    caller.msg("You failed to improve %s; the quality will remain %s." % (targ, QUALITY_LEVELS[old]))
                    return
                caller.msg("New quality level is %s." % QUALITY_LEVELS[quality])
                change_quality(targ, quality)
                return
        proj = caller.db.crafting_project
        if not proj:
            caller.msg("You have no crafting project.")
            return
        if "name" in self.switches:
            if not self.args:
                caller.msg("Name it what?")
                return
            if not validate_name(self.args):
                caller.msg("That is not a valid name.")
                return
            proj[1] = self.args
            caller.db.crafting_project = proj
            caller.msg("Name set to %s." % self.args)
            return
        if "desc" in self.switches:
            if not self.args:
                caller.msg("Describe it how?")
                return
            proj[2] = self.args
            caller.db.crafting_project = proj
            caller.msg("Desc set to:\n%s" % self.args)
            return
        if "abandon" in self.switches:
            caller.msg("You have abandoned this crafting project. You may now start another.")
            caller.db.crafting_project = None
            return
        if "translated_text" in self.switches:
            if not (self.lhs and self.rhs):
                caller.msg("Usage: craft/translated_text <language>=<text>")
                return
            lhs = self.lhs.lower()
            if lhs not in self.caller.languages.known_languages:
                caller.msg("Nice try. You cannot speak %s." % self.lhs)
                return
            proj[5].update({lhs: self.rhs})
            caller.db.crafting_project = proj
            self.display_project(proj)
            return
        if "altdesc" in self.switches:
            if not self.args:
                caller.msg("Describe them how? This is only used for disguise recipes.")
                return
            proj[6] = self.args
            caller.msg("This is only used for disguise recipes. Alternate description set to:\n%s" % self.args)
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
                caller.msg("This recipe does not allow for additional materials to be used.")
                return
            adorns = proj[3] or {}
            adorns[mat.id] = amt
            proj[3] = adorns
            caller.db.crafting_project = proj
            caller.msg("Additional materials: %s" % ", ".join("%s: %s" % (CraftingMaterialType.objects.get(id=mat).name,
                                                                          amt) for mat, amt in adorns.items()))
            return
        if "forgery" in self.switches:
            self.msg("Temporarily disabled until I have time to revamp this.")
            return
        if "preview" in self.switches:
            if self.args:
                viewer = self.caller.player.search(self.args)
                if not viewer:
                    return
                viewer.msg("{c%s{n is sharing a preview of their crafting project with you." % self.caller)
                self.msg("You share a preview of your crafting project with %s." % viewer)
            else:
                viewer = self.caller.player
            name = proj[1] or "[No Name Yet]"
            viewer.msg("{wPreview of {n%s {wdesc:{n\n%s" % (name, proj[2]))
            return
        # do rolls for our crafting. determine quality level, handle forgery stuff
        if "finish" in self.switches:
            if not proj[1]:
                caller.msg("You must give it a name first.")
                return
            if not proj[2]:
                caller.msg("You must write a description first.")
                return
            invest = 0
            action_points = 0
            if self.lhs:
                try:
                    invest = int(self.lhslist[0])
                    if len(self.lhslist) > 1:
                        action_points = int(self.lhslist[1])
                except ValueError:
                    caller.msg("Silver/Action Points to invest must be a number.")
                    return
                if invest < 0 or action_points < 0:
                    caller.msg("Silver/Action Points cannot be a negative number.")
                    return
            # first, check if we have all the materials required
            mats = {}
            try:
                recipe = recipes.get(id=proj[0])
            except CraftingRecipe.DoesNotExist:
                caller.msg("You lack the ability to finish that recipe.")
                return
            if not self.check_max_invest(recipe, invest):
                return
            if recipe.type == "disguise":
                if not proj[6]:
                    caller.msg("This kind of item requires craft/altdesc before it can be finished.")
                    return
            for mat in recipe.materials.all():
                mats[mat.id] = mats.get(mat.id, 0) + mat.amount
            for adorn in proj[3]:
                mats[adorn] = mats.get(adorn, 0) + proj[3][adorn]
            # replace with forgeries
            for rep in proj[4].keys():
                # rep is ID to replace
                forg = proj[4][rep]
                if rep in mats:
                    amt = mats[rep]
                    del mats[rep]
                    mats[forg] = amt
            # check silver cost
            try:
                price = self.get_recipe_price(recipe)
            except ValueError:
                caller.msg("That recipe does not have a price defined.")
                return
            cost = recipe.additional_cost + invest + price
            if cost < 0 or price < 0:
                errmsg = "For %s at %s, recipe %s, cost %s, price %s" % (caller, caller.location, recipe.id, cost,
                                                                         price)
                raise ValueError(errmsg)
            if not caller.check_permstring('builders'):
                if caller.db.currency < cost:
                    caller.msg("The recipe costs %s on its own, and you are trying to spend an additional %s." %
                               (recipe.additional_cost, invest))
                    if price:
                        caller.msg("The additional price charged by the crafter for this recipe is %s." % price)
                    caller.msg("You need %s silver total, and have only %s." % (cost, caller.db.currency))
                    return
                pmats = caller.player.Dominion.assets.materials
                # add up the total cost of the materials we're using for later
                realvalue = 0
                for mat in mats:
                    try:
                        c_mat = CraftingMaterialType.objects.get(id=mat)
                    except CraftingMaterialType.DoesNotExist:
                        inform_staff("Attempted to craft using material %s which does not exist." % mat)
                        self.msg("One of the materials required no longer seems to exist. Informing staff.")
                        return
                    try:
                        pmat = pmats.get(type=c_mat)
                        if pmat.amount < mats[mat]:
                            caller.msg("You need %s of %s, and only have %s." % (mats[mat], c_mat.name, pmat.amount))
                            return
                        realvalue += c_mat.value * mats[mat]
                    except CraftingMaterials.DoesNotExist:
                        caller.msg("You do not have any of the material %s." % c_mat.name)
                        return
                # check if they have enough action points
                if not caller.player_ob.pay_action_points(2 + action_points):
                    self.msg("You do not have enough action points left to craft that.")
                    return
                # pay the money
                caller.pay_money(cost)
                # we're still here, so we have enough materials. spend em all
                for mat in mats:
                    cmat = CraftingMaterialType.objects.get(id=mat)
                    pmat = pmats.get(type=cmat)
                    pmat.amount -= mats[mat]
                    pmat.save()
            else:
                realvalue = recipe.value
            # determine difficulty modifier if we tossed in more money
            ability = get_ability_val(crafter, recipe)
            diffmod = get_difficulty_mod(recipe, invest, action_points, ability)
            # do crafting roll
            roll = do_crafting_roll(crafter, recipe, diffmod, room=caller.location)
            # get type from recipe
            otype = recipe.type
            # create object
            if otype == "wieldable":
                obj, quality = create_weapon(recipe, roll, proj, caller)
            elif otype == "wearable":
                obj, quality = create_wearable(recipe, roll, proj, caller)
            elif otype == "place":
                obj, quality = create_place(recipe, roll, proj, caller)
            elif otype == "book":
                obj, quality = create_book(recipe, roll, proj, caller)
            elif otype == "container":
                obj, quality = create_container(recipe, roll, proj, caller)
            elif otype == "decorative_weapon":
                obj, quality = create_decorative_weapon(recipe, roll, proj, caller)
            elif otype == "wearable_container":
                obj, quality = create_wearable_container(recipe, roll, proj, caller)
            elif otype == "perfume":
                obj, quality = create_consumable(recipe, roll, proj, caller, PERFUME)
            elif otype == "disguise":
                obj, quality = create_mask(recipe, roll, proj, caller, proj[6])
            else:
                obj, quality = create_generic(recipe, roll, proj, caller)
            # finish stuff universal to all crafted objects
            obj.desc = proj[2]
            obj.save()
            obj.db.materials = mats
            obj.db.recipe = recipe.id
            obj.db.adorns = proj[3]
            obj.db.crafted_by = crafter
            obj.db.volume = int(recipe.resultsdict.get('volume', 0))
            self.pay_owner(price, "%s has crafted '%s', a %s, at your shop and you earn %s silver." % (caller, obj,
                                                                                                       recipe.name,
                                                                                                       price))
            if proj[4]:
                obj.db.forgeries = proj[4]
                obj.db.forgery_roll = do_crafting_roll(caller, recipe, room=caller.location)
                # forgery penalty will be used to degrade weapons/armor
                obj.db.forgery_penalty = (recipe.value/realvalue) + 1
            try:
                if proj[5]:
                    obj.db.translation = proj[5]
            except IndexError:
                pass
            cnoun = "You" if caller == crafter else crafter
            caller.msg("%s created %s." % (cnoun, obj.name))
            quality = QUALITY_LEVELS[quality]
            caller.msg("It is of %s quality." % quality)
            caller.db.crafting_project = None
            return


class CmdRecipes(ArxCommand):
    """
    recipes
    Usage:
        recipes [<ability or skill to filter by>]
        recipes/known
        recipes/learn <recipe name>
        recipes/info <recipe name>
        recipes/cost <recipe name>
        recipes/teach <character>=<recipe name>

    Check, learn, or teach recipes. Without an argument, recipes
    lists all recipes you know or can learn. The /info switch lists the
    requirements for learning a given recipe. Learning a recipe may or
    may not be free - cost lets you see the cost of a recipe beforehand.
    """
    key = "recipes"
    locks = "cmd:all()"
    aliases = ["recipe"]
    help_category = "Crafting"

    def display_recipes(self, recipes):
        from server.utils import arx_more
        if not recipes:
            self.caller.msg("(No recipes qualify.)")
            return
        known_list = CraftingRecipe.objects.filter(known_by__player__player=self.caller.player)
        table = PrettyTable(["{wKnown{n", "{wName{n", "{wAbility{n", "{wLvl{n", "{wCost{n"])
        from operator import attrgetter
        recipes = sorted(recipes, key=attrgetter('ability', 'difficulty', 'name'))
        for recipe in recipes:
            known = "{wX{n" if recipe in known_list else ""
            table.add_row([known, str(recipe), recipe.ability, recipe.difficulty, recipe.additional_cost])
        arx_more.msg(self.caller, str(table), justify_kwargs=False)

    def func(self):
        """Implement the command"""
        from django.db.models import Q
        caller = self.caller
        all_recipes = CraftingRecipe.objects.all()
        recipes = all_recipes.filter(known_by__player__player=caller.player)
        unknown = all_recipes.exclude(known_by__player__player=caller.player)
        if self.args and (not self.switches or 'known' in self.switches):
            filters = Q(name__iexact=self.args) | Q(skill__iexact=self.args) | Q(ability__iexact=self.args)
            recipes = recipes.filter(filters)
            unknown = unknown.filter(filters)
        recipes = list(recipes)
        can_learn = [ob for ob in unknown if ob.access(caller, 'learn')]
        try:
            dompc = PlayerOrNpc.objects.get(player=caller.player)
        except PlayerOrNpc.DoesNotExist:
            dompc = setup_dom_for_char(caller)
        if not self.switches:
            visible = recipes + can_learn
            self.display_recipes(visible)
            return
        if 'known' in self.switches:
            self.display_recipes(recipes)
            return
        if 'learn' in self.switches or 'cost' in self.switches:
            match = None
            if self.args:
                match = [ob for ob in can_learn if ob.name.lower() == self.args.lower()]
            if not match:
                learn_msg = ("You cannot learn '%s'. " % self.lhs) if self.lhs else ""
                caller.msg("%sRecipes you can learn:" % learn_msg)
                self.display_recipes(can_learn)
                return
            match = match[0]
            cost = 0 if caller.check_permstring('builders') else match.additional_cost
            cost_msg = "It will cost %s for you to learn %s." % (cost or "nothing", match.name)
            if 'cost' in self.switches:
                return caller.msg(cost_msg)
            elif cost > caller.currency:
                return caller.msg("You have %s silver. %s" % (caller.currency, cost_msg))
            caller.pay_money(cost)
            dompc.assets.recipes.add(match)
            coststr = (" for %s silver" % cost) if cost else ""
            caller.msg("You have learned %s%s." % (match.name, coststr))
            return
        if 'info' in self.switches:
            match = None
            info = list(can_learn) + list(recipes)
            if self.args:
                match = [ob for ob in info if ob.name.lower() == self.args.lower()]
            if not match:
                caller.msg("No recipe by that name. Recipes you can get /info on:")
                self.display_recipes(info)
                return
            match = match[0]
            display = match.display_reqs(dompc, full=True)
            caller.msg(display, options={'box': True})
            return
        if 'teach' in self.switches:
            match = None
            can_teach = [ob for ob in recipes if ob.access(caller, 'teach')]
            if self.rhs:
                match = [ob for ob in can_teach if ob.name.lower() == self.rhs.lower()]
            if not match:
                teach_msg = ("You cannot teach '%s'. " % self.rhs) if self.rhs else ""
                caller.msg("%sRecipes you can teach:" % teach_msg)
                self.display_recipes(can_teach)
                return
            recipe = match[0]
            character = caller.search(self.lhs)
            if not character:
                return
            if not recipe.access(character, 'learn'):
                caller.msg("They cannot learn %s." % recipe.name)
                return
            try:
                dompc = PlayerOrNpc.objects.get(player=character.player)
            except PlayerOrNpc.DoesNotExist:
                dompc = setup_dom_for_char(character)
            if recipe in dompc.assets.recipes.all():
                caller.msg("They already know %s." % recipe.name)
                return
            dompc.assets.recipes.add(recipe)
            caller.msg("Taught %s %s." % (character, recipe.name))


class CmdJunk(ArxCommand):
    """
    +junk

    Usage:
        +junk <object>

    Destroys an object, retrieving a portion of the materials
    used to craft it.
    """
    key = "junk"
    locks = "cmd:all()"
    help_category = "Crafting"

    def func(self):
        """Implement the command"""
        caller = self.caller
        pmats = caller.player.Dominion.assets.materials
        obj = caller.search(self.args, use_nicks=True, quiet=True)
        if not obj:
            AT_SEARCH_RESULT(obj, caller, self.args, False)
            return
        else:
            if len(make_iter(obj)) > 1:
                AT_SEARCH_RESULT(obj, caller, self.args, False)
                return
            obj = make_iter(obj)[0]
        if obj.location != caller:
            caller.msg("You can only +junk objects you are holding.")
            return
        if obj.player_ob or obj.player:
            caller.msg("You cannot +junk a character.")
            return
        if obj.contents:
            self.msg("It contains objects that must first be removed.")
            return
        if obj.db.destroyable:
            caller.msg("You have destroyed %s." % obj)
            obj.softdelete()
            return
        recipe = obj.db.recipe
        if not recipe:
            caller.msg("You may only +junk crafted objects.")
            return
        if "plot" in obj.tags.all():
            self.msg("This object cannot be destroyed.")
            return
        mats = obj.db.materials
        adorns = obj.db.adorns or {}
        refunded = []
        roll = self.get_refund_chance()

        def randomize_amount(amt):
            """Helper function to determine amount kept when junking"""
            from random import randint
            num_kept = 0
            for _ in range(amt):
                if randint(0, 100) <= roll:
                    num_kept += 1
            return num_kept

        for mat in adorns:
            cmat = CraftingMaterialType.objects.get(id=mat)
            amount = adorns[mat]
            amount = randomize_amount(amount)
            if amount:
                try:
                    pmat = pmats.get(type=cmat)
                except CraftingMaterials.DoesNotExist:
                    pmat = pmats.create(type=cmat)
                pmat.amount += amount
                pmat.save()
                refunded.append("%s %s" % (amount, cmat.name))
        for mat in mats:
            amount = mats[mat]
            if mat in adorns:
                amount -= adorns[mat]
            amount = randomize_amount(amount)
            if amount <= 0:
                continue
            cmat = CraftingMaterialType.objects.get(id=mat)
            try:
                pmat = pmats.get(type=cmat)
            except CraftingMaterials.DoesNotExist:
                pmat = pmats.create(type=cmat)
            pmat.amount += amount
            pmat.save()
            refunded.append("%s %s" % (amount, cmat.name))
        caller.msg("By destroying %s, you have received: %s" % (obj, ", ".join(refunded) or "Nothing."))
        obj.softdelete()

    def get_refund_chance(self):
        """Gets our chance of material refund based on a skill check"""
        roll = do_dice_check(self.caller, stat="dexterity", skill="legerdemain", quiet=False)
        return max(roll, 1)
