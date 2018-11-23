from server.utils.arx_utils import sub_old_ansi, text_box, lowercase_kwargs
import re
from evennia.utils.utils import lazy_property
from evennia.utils.ansi import parse_ansi

from world.conditions.triggerhandler import TriggerHandler
from world.templates.models import Template
from world.templates.mixins import TemplateMixins

class DescMixins(object):
    """
    Handles descriptions for objects, which is controlled by three
    Evennia Attributes: desc, raw_desc, and general_desc. desc is
    the current description that is used/seen when looking at an
    object. raw_desc is a permanent desc that might be elaborated
    upon with other things, such as additional strings from other
    methods or properties. general_desc is a fallback that can be
    used if raw_desc is unavailable or unused.

    These are accessed by three properties: desc, temp_desc, and
    perm_desc. desc returns the temporary desc first if it exists,
    then the raw_desc, then the fallback general_desc, the the desc
    setter will set all three of these to the same value, intended
    to be a universal change. temp_desc will return the same value
    as desc, but its setter only modifies the temporary desc, and
    it has a deleter that sets the temporary desc to an empty string.
    perm_desc returns the raw_desc first or its fallback, only returning
    the temporary desc if neither exist. Its setter sets the general_desc
    and raw_desc, but not the temporary desc.

    So for a temporary disguise, use .temp_desc. For a permanent change
    that won't override any current disguise, use .perm_desc. For a change
    that will change everything right now, disguise or not, use .desc.
    """
    def _desc_get(self):
        """
        :type self: evennia.objects.models.ObjectDB
        :return:
        """
        return (self.db.desc or self.db.raw_desc or self.db.general_desc or "") + self.additional_desc

    def _desc_set(self, val):
        """
        :type self: ObjectDB
        """
        # desc may be changed dynamically
        self.db.desc = val
        if self.db.raw_desc:
            self.db.raw_desc = val
        if self.db.general_desc:
            # general desc is our fallback
            self.db.general_desc = val
        self.ndb.cached_template_desc = None
    desc = property(_desc_get, _desc_set)

    def __temp_desc_get(self):
        """
        :type self: ObjectDB
        """
        return self.db.desc or self.db.raw_desc or self.db.general_desc

    def __temp_desc_set(self, val):
        """
        :type self: ObjectDB
        """
        # Make sure we're not using db.desc as our permanent desc before wiping it
        if not self.db.raw_desc:
            self.db.raw_desc = self.db.desc
        if not self.db.general_desc:
            self.db.desc = self.db.desc
        self.ndb.cached_template_desc = None
        self.db.desc = val

    def __temp_desc_del(self):
        """
        :type self: ObjectDB
        """
        # Make sure we're not using db.desc as our permanent desc before wiping it
        if not self.db.raw_desc:
            self.db.raw_desc = self.db.desc
        if not self.db.general_desc:
            self.db.general_desc = self.db.desc
        self.db.desc = ""
        self.ndb.cached_template_desc = None
    temp_desc = property(__temp_desc_get, __temp_desc_set, __temp_desc_del)

    def __perm_desc_get(self):
        """
        :type self: ObjectDB
        :return:
        """
        return (self.db.raw_desc or self.db.general_desc or self.db.desc or "") + self.additional_desc

    def __perm_desc_set(self, val):
        """
        :type self: ObjectDB
        """
        self.db.general_desc = val
        self.db.raw_desc = val
        self.ndb.cached_template_desc = None
    perm_desc = property(__perm_desc_get, __perm_desc_set)

    def __get_volume(self):
        """
        :type self: ObjectDB
        """
        total = 0
        for obj in self.contents:
            if not obj.db.currently_worn and obj.db.sheathed_by != self:
                vol = obj.db.volume or 1
                total += vol
        return total
    volume = property(__get_volume)

    @property
    def health_status(self):
        """
        :type self: ObjectDB
        """
        return self.db.health_status or "nonliving"

    @health_status.setter
    def health_status(self, value):
        """
        :type self: ObjectDB
        """
        self.db.health_status = value

    @property
    def dead(self):
        return self.health_status == "dead"

    @property
    def alive(self):
        return self.health_status == "alive"

    @property
    def additional_desc(self):
        """
        :type self: ObjectDB
        """
        try:
            if self.db.additional_desc:
                return "\n\n" + "{w({n%s{w){n" % self.db.additional_desc
        except TypeError:
            return ""
        return ""

    @additional_desc.setter
    def additional_desc(self, value):
        """
        :type self: ObjectDB
        """
        if not value:
            self.db.additional_desc = ""
        else:
            self.db.additional_desc = str(value)

    @additional_desc.deleter
    def additional_desc(self):
        """
        :type self: ObjectDB
        """
        self.attributes.remove("additional_desc")


class NameMixins(object):

    @property
    def is_disguised(self):
        return bool(self.fakename)

    @property
    def fakename(self):
        """
        :type self: ObjectDB
        """
        return self.db.false_name

    @fakename.setter
    def fakename(self, val):
        """
        :type self: ObjectDB
        :param val: str
        """
        old = self.db.false_name
        self.db.false_name = val
        if old:
            old = parse_ansi(old, strip_ansi=True)
            self.aliases.remove(old)
        val = parse_ansi(val, strip_ansi=True)
        self.aliases.add(val)
        self.tags.add("disguised")

    @fakename.deleter
    def fakename(self):
        """
        :type self: ObjectDB
        """
        old = self.db.false_name
        if old:
            old = parse_ansi(old, strip_ansi=True)
            self.aliases.remove(old)
        self.attributes.remove("false_name")
        self.tags.remove("disguised")

    def __name_get(self):
        """
        :type self: ObjectDB
        """
        name = self.fakename or self.db.colored_name or self.key or ""
        name = name.rstrip("{/").rstrip("|/") + ("{n" if ("{" in name or "|" in name or "%" in name) else "")
        return name

    def __name_set(self, val):
        """
        :type self: ObjectDB
        """
        # convert color codes
        val = sub_old_ansi(val)
        self.db.colored_name = val
        self.key = parse_ansi(val, strip_ansi=True)
        self.ndb.cached_template_desc = None
        self.save()
    name = property(__name_get, __name_set)

    def __str__(self):
        return self.name

    def __unicode__(self):
        return self.name


# noinspection PyAttributeOutsideInit
class BaseObjectMixins(object):
    @property
    def is_room(self):
        return False

    @property
    def is_exit(self):
        return False

    @property
    def is_character(self):
        return False

    @property
    def player(self):
        return self.account

    @player.setter
    def player(self, value):
        self.account = value

    def softdelete(self):
        """
        Only fake-delete the object, storing the date it was fake deleted for removing it permanently later.

        :type self: ObjectDB
        """
        import time
        self.location = None
        self.tags.add("deleted")
        self.db.deleted_time = time.time()

    def undelete(self, move=True):
        """
        :type self: ObjectDB
        :type move: Boolean
        :return:
        """
        self.tags.remove("deleted")
        self.attributes.remove("deleted_time")
        if move:
            from typeclasses.rooms import ArxRoom
            try:
                room = ArxRoom.objects.get(db_key__iexact="Island of Lost Toys")
                self.location = room
            except ArxRoom.DoesNotExist:
                pass

    # properties for determining our Player object, and that we are not a Player object
    @property
    def player_ob(self):
        """
        Returns our player object if we have one
        :type self: ObjectDB
        """
        try:
            return self.roster.player
        except AttributeError:
            pass

    @property
    def has_player(self):
        """
        :type self: ObjectDB
        :return: AccountDB
        """
        return self.has_account

    @property
    def char_ob(self):
        return None

    def transfer_all(self, destination, caller=None):
        """
        Transfers all objects to our new destination.
        Args:
            :type self: ObjectDB
            :type destination: ObjectDB
            :type caller: ObjectDB

        Returns:
            Items transferred
        """
        obj_list = self.contents
        if caller:
            obj_list = [ob for ob in obj_list if ob.at_before_move(destination, caller=caller)]
        for obj in obj_list:
            obj.move_to(destination, quiet=True)
        return obj_list

    def at_before_move(self, destination, **kwargs):
        caller = kwargs.pop('caller', None)
        if caller:
            if not self.access(caller, 'get') and self.location != caller:
                caller.msg("You cannot get %s." % self)
                return False
        return super(BaseObjectMixins, self).at_before_move(destination, **kwargs)

    def get_room(self):
        """Returns the outermost location/room of this object."""
        # if we have no location, we are the room
        if not self.location:
            return self
        # recursive call to get the room
        return self.location.get_room()


class AppearanceMixins(BaseObjectMixins, TemplateMixins):
    def return_contents(self, pobject, detailed=True, show_ids=False,
                        strip_ansi=False, show_places=True, sep=", "):
        """
        Returns contents of the object, used in formatting our description,
        as well as when in 'brief mode' and skipping a description, but
        still seeing contents.

        :type self: evennia.objects.models.ObjectDB
        :param pobject: ObjectDB
        :param detailed: bool
        :param show_ids: bool
        :param strip_ansi: bool
        :param show_places: bool
        :param sep: str
        """

        def get_key(ob):
            if show_ids:
                object_key = "%s {w(ID: %s){n" % (ob.name, ob.id)
            else:
                object_key = ob.name
            if strip_ansi:
                try:
                    object_key = parse_ansi(object_key, strip_ansi=True)
                except (AttributeError, TypeError, ValueError):
                    pass
            return object_key

        string = ""
        # get and identify all objects
        visible = (con for con in self.contents if con != pobject and con.access(pobject, "view"))
        exits, users, things, worn, sheathed, wielded, places, npcs = [], [], [], [], [], [], [], []
        currency = self.return_currency()
        from typeclasses.places.places import Place
        qs = list(Place.objects.filter(db_location=self))
        for con in visible:
            key = get_key(con)
            if con in qs and show_places:
                places.append(key)
                continue
            if con.destination:
                exits.append(key)
            # Only display worn items in inventory to other characters
            elif hasattr(con, 'wear') and con.is_worn:
                if con.decorative:
                    worn.append(con)
                else:
                    sheathed.append(key)
            elif hasattr(con, 'wield') and con.is_wielded:
                if not con.db.stealth:
                    wielded.append(key)
                elif hasattr(pobject, 'sensing_check') and pobject.sensing_check(con, diff=con.db.sense_difficulty) > 0:
                    key += "{w (hidden){n"
                    wielded.append(key)
            elif con.has_player:
                # we might have either a title or a fake name
                lname = con.name
                if con.db.room_title:
                    lname += "{w(%s){n" % con.db.room_title
                if con.key in lname and not con.db.false_name:
                    lname = lname.replace(key, "{c%s{n" % key)
                    users.append(lname)
                else:
                    users.append("{c%s{n" % lname)
            elif hasattr(con, 'is_character') and con.is_character:
                npcs.append(con)
            else:
                if not self.db.places:
                    things.append(con)
                elif self.db.places and con not in self.db.places:
                    things.append(con)
        if worn:
            worn = sorted(worn, key=lambda x: x.db.worn_time)
            string += "\n" + "{wWorn items of note:{n " + ", ".join(get_key(ob) for ob in worn)
        if sheathed:
            string += "\n" + "{wWorn/Sheathed weapons:{n " + ", ".join(sheathed)
        if wielded:
            string += "\n" + "{wWielding:{n " + ", ".join(wielded)
        if detailed:
            if show_places and places:
                string += "\n{wPlaces:{n " + ", ".join(places)
            if exits:
                string += "\n{wExits:{n " + ", ".join(exits)
            if users or npcs:
                string += "\n{wCharacters:{n " + ", ".join(users + [get_key(ob) for ob in npcs])
            if things:
                things = sorted(things, key=lambda x: x.db.put_time)
                string += "\n{wObjects:{n " + sep.join([get_key(ob) for ob in things])
            if currency:
                string += "\n{wMoney:{n %s" % currency
        return string

    @property
    def currency(self):
        """
        :type self: ObjectDB
        :return: float
        """
        return round(self.db.currency or 0.0, 2)

    @currency.setter
    def currency(self, val):
        """
        :type self: ObjectDB
        :param val: float
        """
        self.db.currency = val

    def pay_money(self, amount, receiver=None):
        """
        A method to pay money from this object, possibly to a receiver.
        All checks should be done before this, and messages also sent
        outside. This just transfers the money itself.
        :type self: ObjectDB
        :param amount: int
        :param receiver: ObjectDB
        """
        currency = self.currency
        amount = round(amount, 2)
        if amount > currency:
            from server.utils.exceptions import PayError
            raise PayError("pay_money called without checking sufficient funds in character. Not enough.")
        self.currency -= amount
        if receiver:
            receiver.currency += amount
        return True

    def return_currency(self):
        """
        :type self: ObjectDB
        """
        currency = self.currency
        if not currency:
            return None
        string = "coins worth a total of %.2f silver pieces" % currency
        return string

    def return_appearance(self, pobject, detailed=False, format_desc=False,
                          show_contents=True):
        """
        This is a convenient hook for a 'look'
        command to call.
        :type self: ObjectDB
        :param pobject: ObjectDB
        :param detailed: bool
        :param format_desc: bool
        :param show_contents: bool
        """
        if not pobject:
            return
        strip_ansi = pobject.db.stripansinames
        # always show contents if a builder+
        show_contents = show_contents or pobject.check_permstring("builders")
        contents = self.return_contents(pobject, strip_ansi=strip_ansi)
        # get description, build string
        string = "{c%s{n" % self.name
        # if altered_desc is true, we use the alternate desc set by an attribute.
        # usually this is some dynamic description set at runtime, such as based
        # on an illusion, wearing a mask, change of seasons, etc.
        if self.db.altered_desc:
            desc = self.db.desc
        else:
            desc = self.desc
        if strip_ansi:
            try:
                desc = parse_ansi(desc, strip_ansi=True)
            except (AttributeError, ValueError, TypeError):
                pass
        if desc and not self.db.recipe and not self.db.do_not_format_desc and "player_made_room" not in self.tags.all():
            if format_desc:
                string += "\n\n%s{n\n" % desc
            else:
                string += "\n%s{n" % desc
        else:  # for crafted objects, respect formatting
            string += "\n%s{n" % desc

            if self.ndb.cached_template_desc:
                string = self.ndb.cached_template_desc
            else:
                templates = Template.objects.in_list(self.find_template_ids(string))
                if templates.exists():
                    string = self.replace_template_values(string, templates)
                self.ndb.cached_template_desc = string

        if contents and show_contents:
            string += contents
        return string

    def transfer_all(self, destination, caller=None):
        self.pay_money(self.currency, destination)
        return super(AppearanceMixins, self).transfer_all(destination, caller)


class ModifierMixin(object):
    """
    Allows us to set modifiers in different situations with specific values. We check against a tag in the target,
    and if there's a match we apply the modifier.
    """
    @property
    def modifier_tags(self):
        """Gets list of modifier tags this object has"""
        return self.tags.get(category="modifiers", return_list=True)

    def add_modifier_tag(self, tag_name):
        """Adds a tag to this object"""
        self.tags.add(tag_name, category="modifiers")

    def rm_modifier_tag(self, tag_name):
        """Removes a modifier tag from this object"""
        self.tags.remove(tag_name, category="modifiers")

    def add_modifier(self, value, check_type, user_tag="", target_tag="", stat="", skill="", ability=""):
        """
        Sets the modifier for this object for a type of tag. For example, if we want to give a bonus against
        all Abyssal creatures, we'd have tag_name 'abyssal' and keep check_type as 'all'.

            Args:
                value (int): Positive for a bonus, negative for a penalty. Flatly applied to rolls.
                check_type: Type of roll we're making. Must be in CHECK_CHOICES.
                user_tag: Name of the tag user must have for this to apply.
                target_tag: Name of the tag target must have for this to apply.
                stat: Stat that must be used for this modifier to apply.
                skill: Skill that must be used for this modifier to apply.
                ability: Ability that must be used for this modifier to apply.
        """
        from world.conditions.models import RollModifier
        check_types = [ob[0] for ob in RollModifier.CHECK_CHOICES]
        if check_type not in check_types:
            raise ValueError("check_type was not valid.")
        user_tag = user_tag.lower()
        target_tag = target_tag.lower()
        stat = stat.lower()
        skill = skill.lower()
        ability = ability.lower()
        mod = self.modifiers.get_or_create(check=check_type, user_tag=user_tag, target_tag=target_tag, stat=stat,
                                           skill=skill, ability=ability)[0]
        mod.value = value
        mod.save()
        return mod

    @lowercase_kwargs("user_tags", "target_tags", "stat_list", "skill_list", "ability_list", default_append="")
    def get_modifier(self, check_type, user_tags=None, target_tags=None, stat_list=None,
                     skill_list=None, ability_list=None):
        """Returns an integer that is the value of our modifier for the listed tags and check.

            Args:
                check_type: The type of roll/check we're making
                user_tags: Tags of the user we wanna check
                target_tags: Tags of the target we wanna check
                stat_list: Only check modifiers for this stat
                skill_list: Only check modifiers for this skill
                ability_list: Only check modifiers for this ability

            Returns:
                Integer value of the total mods we calculate.
        """
        from django.db.models import Sum
        from world.conditions.models import RollModifier
        check_types = RollModifier.get_check_type_list(check_type)
        return self.modifiers.filter(check__in=check_types, user_tag__in=user_tags, target_tag__in=target_tags,
                                     stat__in=stat_list, skill__in=skill_list, ability__in=ability_list
                                     ).aggregate(Sum('value'))[1]


class TriggersMixin(object):
    """
    Adds triggerhandler to our objects.
    """
    @lazy_property
    def triggerhandler(self):
        """Adds a triggerhandler property for caching trigger checks to avoid excessive queries"""
        return TriggerHandler(self)


class ObjectMixins(DescMixins, AppearanceMixins, ModifierMixin, TriggersMixin):
    @property
    def has_player(self):
        return self.has_account


class CraftingMixins(object):
    def return_appearance(self, pobject, detailed=False, format_desc=False,
                          show_contents=True):
        """
        This is a convenient hook for a 'look'
        command to call.
        :type self: ObjectDB
        :param pobject: ObjectDB
        :param detailed: bool
        :param format_desc: bool
        :param show_contents: bool
        """
        string = super(CraftingMixins, self).return_appearance(pobject, detailed=detailed, format_desc=format_desc,
                                                               show_contents=show_contents)
        string += self.return_crafting_desc()
        return string

    def junk(self, caller):
        """Checks our ability to be junked out."""
        from server.utils.exceptions import CommandError
        if self.location != caller:
            raise CommandError("You can only +junk objects you are holding.")
        if self.contents:
            raise CommandError("It contains objects that must first be removed.")
        if not self.junkable:
            raise CommandError("This object cannot be destroyed.")
        self.do_junkout(caller)

    def do_junkout(self, caller):
        """Attempts to salvage materials from crafted item, then junks it."""
        from world.dominion.models import (CraftingMaterials, CraftingMaterialType)

        def get_refund_chance():
            """Gets our chance of material refund based on a skill check"""
            from world.stats_and_skills import do_dice_check
            roll = do_dice_check(caller, stat="dexterity", skill="legerdemain", quiet=False)
            return max(roll, 1)

        def randomize_amount(amt):
            """Helper function to determine amount kept when junking"""
            from random import randint
            num_kept = 0
            for _ in range(amt):
                if randint(0, 100) <= roll:
                    num_kept += 1
            return num_kept

        pmats = caller.player.Dominion.assets.materials
        mats = self.db.materials
        adorns = self.db.adorns or {}
        refunded = []
        roll = get_refund_chance()
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
        destroy_msg = "You destroy %s." % self
        if refunded:
            destroy_msg += " Salvaged materials: %s" % ", ".join(refunded)
        caller.msg(destroy_msg)
        self.softdelete()

    @property
    def recipe(self):
        """
        Gets the crafting recipe used to create us if one exists.

        :type self: ObjectDB
        Returns:
            The crafting recipe used to create this object.
        """
        if self.db.recipe:
            from world.dominion.models import CraftingRecipe
            try:
                recipe = CraftingRecipe.objects.get(id=self.db.recipe)
                return recipe
            except CraftingRecipe.DoesNotExist:
                pass

    @property
    def adorns(self):
        """
        Returns a dict of crafting materials we have.

        :type self: ObjectDB
            Returns:
                ret (dict): dict of crafting materials as keys to amt

        SharedMemoryModel causes all .get by ID to be cached inside the class,
        so these queries will only hit the database once. After that, we're just
        building a dict so it'll be insignificant.
        """
        from world.dominion.models import CraftingMaterialType
        ret = {}
        adorns = self.db.adorns or {}
        for adorn_id in adorns:
            try:
                mat = CraftingMaterialType.objects.get(id=adorn_id)
            except CraftingMaterialType.DoesNotExist:
                continue
            ret[mat] = adorns[adorn_id]
        return ret

    def return_crafting_desc(self):
        """
        :type self: ObjectDB
        """
        string = ""
        adorns = self.adorns
        # adorns are a dict of the ID of the crafting material type to amount
        if adorns:
            adorn_strs = ["%s %s" % (amt, mat.name) for mat, amt in adorns.items()]
            string += "\nAdornments: %s" % ", ".join(adorn_strs)
        # recipe is an integer matching the CraftingRecipe ID
        if hasattr(self, 'type_description') and self.type_description:
            from server.utils.arx_utils import a_or_an
            td = self.type_description
            part = a_or_an(td)
            string += "\nIt is %s %s." % (part, td)
        if self.db.quality_level:
            string += self.get_quality_appearance()
        if self.db.quantity:
            string += "\nThere are %d units." % self.db.quantity
        if hasattr(self, 'origin_description') and self.origin_description:
            string += self.origin_description
        if self.db.translation:
            string += "\nIt contains script in a foreign tongue."
        # signed_by is a crafter's character object
        signed = self.db.signed_by
        if signed:
            string += "\n%s" % (signed.db.crafter_signature or "")
        return string

    @property
    def type_description(self):
        if self.recipe:
            return self.recipe.name

        return None

    @property
    def origin_description(self):
        if self.db.found_shardhaven:
            return "\nIt was found in %s." % self.db.found_shardhaven
        return None

    @property
    def quality_level(self):
        return self.db.quality_level or 0

    def get_quality_appearance(self):
        """
        :type self: ObjectDB
        :return str:
        """
        if self.quality_level < 0:
            return ""
        from commands.base_commands.crafting import QUALITY_LEVELS
        qual = min(self.quality_level, 11)
        qual = QUALITY_LEVELS.get(qual, "average")
        return "\nIts level of craftsmanship is %s." % qual

    def add_adorn(self, material, quantity):
        """
        Adds an adornment to this crafted object.
        :type self: ObjectDB
        :type material: CraftingMaterialType
        :type quantity: int

        Args:
            material: The crafting material type that we're adding
            quantity: How much we're adding
        """
        adorns = self.db.adorns or {}
        amt = adorns.get(material.id, 0)
        adorns[material.id] = amt + quantity
        self.db.adorns = adorns

    @property
    def is_plot_related(self):
        if "plot" in self.tags.all() or self.search_tags.all().exists() or self.clues.all().exists():
            return True

    @property
    def junkable(self):
        """A check for this object's plot connections."""
        if not self.recipe:
            raise AttributeError
        return not self.is_plot_related


# regex removes the ascii inside an ascii tag
RE_ASCII = re.compile(r"<ascii>(.*?)</ascii>", re.IGNORECASE | re.DOTALL)
# designates text to be ascii-free by a crafter
RE_ALT_ASCII = re.compile(r"<noascii>(.*?)</noascii>", re.IGNORECASE | re.DOTALL)
RE_COLOR = re.compile(r'"(.*?)"')


# noinspection PyUnresolvedReferences
class MsgMixins(object):
    @lazy_property
    def namex(self):
        # regex that contains our name inside quotes
        name = self.key
        return re.compile(r'"(.*?)%s{n(.*?)"' % name)

    def msg(self, text=None, from_obj=None, session=None, options=None, **kwargs):
        """
        :type self: ObjectDB
        :param text: str or tuple
        :param from_obj: ObjectDB
        :param session: Session
        :param options: dict
        :param kwargs: dict
        """
        # if we have nothing to receive message, we're done.
        if not self.sessions.all():
            return
        # compatibility change for Evennia changing text to be either str or tuple
        if hasattr(text, '__iter__'):
            text = text[0]
        options = options or {}
        options.update(kwargs.get('options', {}))
        try:
            text = str(text)
        except (TypeError, UnicodeDecodeError, ValueError):
            pass
        if text.endswith("|"):
            text += "{n"
        text = sub_old_ansi(text)
        if from_obj and isinstance(from_obj, dict):
            # somehow our from_obj had a dict passed to it. Fix it up.
            # noinspection PyBroadException
            try:
                options.update(from_obj)
                from_obj = None
            except Exception:
                import traceback
                traceback.print_exc()
        lang = options.get('language', None)
        msg_content = options.get('msg_content', None)
        if lang and msg_content:
            try:
                if not self.check_permstring("builders") and lang.lower() not in self.languages.known_languages:
                    text = text.replace(msg_content, "<Something in a language that you don't understand>.")
            except AttributeError:
                pass
        if options.get('is_pose', False):
            if self.db.posebreak:
                text = "\n" + text
            name_color = self.db.name_color
            if name_color:
                text = text.replace(self.key, name_color + self.key + "{n")
            quote_color = self.db.pose_quote_color
            # colorize people's quotes with the given text
            if quote_color:
                text = RE_COLOR.sub(r'%s"\1"{n' % quote_color, text)
                if name_color:
                    # counts the instances of name replacement inside quotes and recolorizes
                    for _ in range(0, text.count("%s{n" % self.key)):
                        text = self.namex.sub(r'"\1%s%s\2"' % (self.key, quote_color), text)
            if self.ndb.pose_history is None:
                self.ndb.pose_history = []
            if from_obj == self:
                self.ndb.pose_history = []
            else:
                try:
                    self.ndb.pose_history.append((from_obj, text))
                except AttributeError:
                    pass
        if options.get('box', False):
            text = text_box(text)
        if options.get('roll', False):
            if self.attributes.has("dice_string"):
                text = "{w<" + self.db.dice_string + "> {n" + text
        try:
            if self.char_ob:
                msg_sep = self.tags.get("newline_on_messages")
                player_ob = self
            else:
                msg_sep = self.player_ob.tags.get("newline_on_messages")
                player_ob = self.player_ob
        except AttributeError:
            msg_sep = None
            player_ob = self
        try:
            if msg_sep:
                text += "\n"
        except (TypeError, ValueError):
            pass
        try:
            if from_obj and (options.get('is_pose', False) or options.get('log_msg', False)):
                private_msg = False
                if hasattr(self, 'location') and hasattr(from_obj, 'location') and self.location == from_obj.location:
                    if self.location.tags.get("private"):
                        private_msg = True
                if not private_msg:
                    player_ob.log_message(from_obj, text)
        except AttributeError:
            pass
        text = self.strip_ascii_from_tags(text)
        super(MsgMixins, self).msg(text, from_obj, session, options, **kwargs)

    def strip_ascii_from_tags(self, text):
        """Removes ascii within tags for formatting."""
        player_ob = self.player_ob or self
        if 'no_ascii' in player_ob.tags.all():
            text = RE_ASCII.sub("", text)
            text = RE_ALT_ASCII.sub(r"\1", text)
        else:
            text = RE_ASCII.sub(r"\1", text)
            text = RE_ALT_ASCII.sub("", text)
        return text

    def msg_location_or_contents(self, text=None, **kwargs):
        """A quick way to ensure a room message, no matter what it's called on. Requires rooms have null location."""
        self.get_room().msg_contents(text=text, **kwargs)

    def confirmation(self, attr, val, prompt_msg):
        """
        Prompts the player or character to confirm a choice.

            Args:
                attr: Name of the confirmation check.
                val: Value of the NAttribute to use.
                prompt_msg: Confirmation prompt message.

            Returns:
                True if we already have the NAttribute set, False if we have to set
                it and prompt them for confirmation.
        """
        attr = "confirm_%s" % attr
        if self.nattributes.get(attr) == val:
            self.nattributes.remove(attr)
            return True
        self.nattributes.add(attr, val)
        self.msg(prompt_msg)


class LockMixins(object):
    def has_lock_permission(self, caller):
        """
        Checks if a caller has permission to open this object - assume we're a locked door or chest.

        :type self: ObjectDB
        :type caller: ObjectDB or AccountDB
        Args:
            caller: Caller object to check access.

        Returns:
            True if they have access, False otherwise.
        """
        if caller and not caller.check_permstring("builders") and not self.access(caller, 'usekey'):
            caller.msg("You do not have a key to %s." % self)
            return False
        return True

    def lock(self, caller=None):
        """
        :type self: ObjectDB
        :param caller: ObjectDB
        """
        if not self.has_lock_permission(caller):
            return
        self.locks.add("traverse: perm(builders)")
        if self.db.locked:
            if caller:
                caller.msg("%s is already locked." % self)
            return
        self.db.locked = True
        msg = "%s is now locked." % self.key
        if caller:
            caller.msg(msg)
        self.location.msg_contents(msg, exclude=caller)
        # set the locked attribute of the destination of this exit, if we have one
        if self.destination and hasattr(self.destination, 'entrances') and self.destination.db.locked is False:
            entrances = [ob for ob in self.destination.entrances if ob.db.locked is False]
            if not entrances:
                self.destination.db.locked = True

    def unlock(self, caller=None):
        """
        :type self: ObjectDB:
        :param caller: ObjectDB
        :return:
        """
        if not self.has_lock_permission(caller):
            return
        self.locks.add("traverse: all()")
        if not self.db.locked:
            if caller:
                caller.msg("%s is already unlocked." % self)
            return
        self.db.locked = False
        msg = "%s is now unlocked." % self.key
        if caller:
            caller.msg(msg)
        self.location.msg_contents(msg, exclude=caller)
        if self.destination:
            self.destination.db.locked = False

    def return_appearance(self, pobject, detailed=False, format_desc=False,
                          show_contents=True):
        """
        :type self: AppearanceMixins, Container
        :param pobject: ObjectDB
        :param detailed: bool
        :param format_desc: bool
        :param show_contents: bool
        :return: str
        """
        currently_open = not self.db.locked
        show_contents = (currently_open or self.tags.get("displayable")) and show_contents
        base = super(LockMixins, self).return_appearance(pobject, detailed=detailed,
                                                         format_desc=format_desc, show_contents=show_contents)
        return base + "\nIt is currently %s." % ("locked" if self.db.locked else "unlocked")


# noinspection PyUnresolvedReferences
class InformMixin(object):
    def inform(self, message, category=None, week=0, append=True):
        if not append:
            inform = self.informs.create(message=message, week=week, category=category)
        else:
            informs = self.informs.filter(category=category, week=week,
                                          read_by__isnull=True)
            if informs:
                inform = informs[0]
                inform.message += "\n\n" + message
                inform.save()
            else:
                inform = self.informs.create(message=message, category=category,
                                             week=week)
        self.notify_inform(inform)

    def notify_inform(self, new_inform):
        index = list(self.informs.all()).index(new_inform) + 1
        self.msg("{yYou have new informs. Use {w@inform %s{y to read them.{n" % index)

    @property
    def can_receive_informs(self):
        return True
