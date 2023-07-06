from evennia_extensions.object_extensions.item_data_handler import ItemDataHandler
from server.utils.arx_utils import sub_old_ansi, text_box, lowercase_kwargs
import re
from datetime import datetime
from evennia.utils.utils import lazy_property
from evennia.utils.ansi import parse_ansi

from typeclasses.exceptions import InvalidTargetError
from world.conditions.triggerhandler import TriggerHandler
from world.crafting.craft_data_handlers import CraftDataHandler
from world.crafting.junk_handlers import RefundMaterialsJunkHandler
from world.templates.models import Template
from world.templates.mixins import TemplateMixins


class DescMixins(object):
    """
    Handles descriptions for objects, which is controlled by two storage values:
    item_data.permanent_description and item_data.temporary_description.
    These are wrapped by three properties: desc, perm_desc, and temp_desc.
    perm_desc is the permanent description, temp_desc is the temporary one.
    desc is the one that is actually displayed, and is the one that should be
    set by the user. It will return temp_desc if it is set, otherwise it will
    return perm_desc. If perm_desc is not set, it will return the default
    permanent description, which is set by the item typeclass.

    So for a temporary disguise, use .temp_desc. For a permanent change
    that won't override any current disguise, use .perm_desc. For a change
    that will change everything right now, disguise or not, use .desc.
    """

    default_permanent_description = ""
    default_size = 1
    default_capacity = 100
    default_quantity = 1
    default_is_locked = False
    can_stack = False

    @property
    def base_desc(self):
        return self.item_data.permanent_description

    @property
    def desc(self):
        """
        :type self: evennia.objects.models.ObjectDB
        :return:
        """
        temp_desc = self.temp_desc
        if temp_desc:
            return temp_desc
        return self.base_desc

    @desc.setter
    def desc(self, val):
        """
        :type self: ObjectDB
        """
        if self.temp_desc:
            del self.temp_desc
        self.item_data.permanent_description = val

    @property
    def temp_desc(self):
        """
        :type self: ObjectDB
        """
        return self.item_data.temporary_description

    @temp_desc.setter
    def temp_desc(self, val):
        """
        :type self: ObjectDB
        :type val: str
        """
        self.item_data.temporary_description = val
        self.ndb.cached_template_desc = None

    @temp_desc.deleter
    def temp_desc(self):
        """
        :type self: ObjectDB
        """
        del self.item_data.temporary_description
        self.ndb.cached_template_desc = None

    @property
    def perm_desc(self):
        """
        :type self: ObjectDB
        :return:
        """
        return self.item_data.permanent_description

    @property
    def used_capacity(self):
        """
        :type self: ObjectDB
        """
        total = 0
        for obj in self.contents:
            if not obj.item_data.currently_worn:
                vol = obj.item_data.total_size
                total += vol
        return total

    @property
    def dead(self):
        return False


class NameMixins(object):
    default_false_name = None
    default_colored_name = None

    @property
    def is_disguised(self):
        return bool(self.fakename)

    @property
    def fakename(self):
        """
        :type self: ObjectDB
        """
        return self.item_data.false_name

    @fakename.setter
    def fakename(self, val):
        """
        :type self: ObjectDB
        :param val: str
        """
        old = self.item_data.false_name
        self.item_data.false_name = val
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
        old = self.item_data.false_name
        if old:
            old = parse_ansi(old, strip_ansi=True)
            self.aliases.remove(old)
        self.item_data.false_name = None
        self.tags.remove("disguised")

    @property
    def name(self):
        """
        :type self: ObjectDB
        """
        name = self.fakename or self.item_data.colored_name or self.key or ""
        name = name.rstrip("{/").rstrip("|/") + (
            "{n" if ("{" in name or "|" in name or "%" in name) else ""
        )
        return name

    @name.setter
    def name(self, val):
        """
        :type self: ObjectDB
        """
        # convert color codes
        val = sub_old_ansi(val)
        uncolored_val = parse_ansi(val, strip_ansi=True)
        if val == uncolored_val:
            # if our name isn't colored, wipe the colored_name value
            del self.item_data.colored_name
        else:
            # update the colored_name value
            self.item_data.colored_name = val
        self.key = uncolored_val
        self.ndb.cached_template_desc = None
        self.save()

    def __str__(self):
        return self.name


# noinspection PyAttributeOutsideInit
class BaseObjectMixins(object):
    default_put_time = 0
    default_deleted_time = None
    default_pre_offgrid_location = None

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
    def is_container(self):
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
        self.location = None
        self.item_data.deleted_time = datetime.now()

    def undelete(self, move=True):
        """
        :type self: ObjectDB
        :type move: Boolean
        :return:
        """
        self.item_data.deleted_time = None
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
            obj_list = [
                ob for ob in obj_list if ob.at_before_move(destination, caller=caller)
            ]
        for obj in obj_list:
            obj.move_to(destination, quiet=True)
        return obj_list

    def at_before_move(self, destination, **kwargs):
        caller = kwargs.pop("caller", None)
        if caller:
            if not self.access(caller, "get") and self.location != caller:
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

    @lazy_property
    def health_status(self):
        try:
            return self.character_health_status
        except AttributeError:
            raise InvalidTargetError(f"{self} is not a valid target.")

    def leave_grid(self):
        """Moves an object off the grid, storing the location from which it left"""
        if self.location:
            self.item_data.pre_offgrid_location = self.location
            self.location = None

    def enter_grid(self):
        """
        Moves an object back on grid if not already there. Goes to its last
        known location or its home space.
        """
        if not self.location:
            self.location = self.item_data.pre_offgrid_location or self.home
            self.location.at_object_receive(self, None)


class AppearanceMixins(BaseObjectMixins, TemplateMixins):
    def get_numbered_name(self, count, looker, **kwargs):
        """
        Evennia's default get_numbered_name method uses the Inflect library, which is
        unreliable and doesn't fit the naming scheme of objects in Arx's database, so
        we won't use it.
        """
        key = kwargs.get("key", "")
        return key, key

    def return_contents(
        self,
        pobject,
        detailed=True,
        show_ids=False,
        strip_ansi=False,
        show_places=True,
        sep=", ",
    ):
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
        visible = (con for con in self.contents if con.access(pobject, "view"))
        exits, users, things, worn, sheathed, wielded, places, npcs = (
            [],
            [],
            [],
            [],
            [],
            [],
            [],
            [],
        )
        currency = self.return_currency()

        for con in visible:
            key = get_key(con)
            if con in getattr(self, "places", []):
                if show_places:
                    places.append(key)
                continue
            if con.destination:
                exits.append(key)
            # Only display worn items in inventory to other characters
            elif hasattr(con, "wear") and con.is_worn:
                if con.decorative:
                    worn.append(con)
                else:
                    sheathed.append(key)
            elif hasattr(con, "wield") and con.is_wielded:
                wielded.append(key)
            elif con.has_account:
                # we might have either a permapose or a fake name
                lname = con.name
                if con.db.room_title:
                    lname += "|w (%s)|n" % con.db.room_title
                elif con == pobject:
                    continue
                if con.key in lname and not con.item_data.false_name:
                    lname = lname.replace(key, "|c%s|n" % key)
                    users.append(lname)
                else:
                    users.append("{c%s{n" % lname)
            elif hasattr(con, "is_character") and con.is_character:
                npcs.append(con)
            else:
                things.append(con)
        if worn:
            worn = sorted(worn, key=lambda x: x.item_data.worn_time)
            string += (
                "\n"
                + "{wWorn items of note:{n "
                + ", ".join(get_key(ob) for ob in worn)
            )
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
                string += "\n{wCharacters:{n " + ", ".join(
                    users + [get_key(ob) for ob in npcs]
                )
            if things:
                things = sorted(things, key=lambda x: x.item_data.put_time)
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

            raise PayError(
                "pay_money called without checking sufficient funds in character. Not enough."
            )
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
        string = "coins worth a total of {:,.2f} silver pieces".format(currency)
        return string

    @property
    def should_format_desc(self):
        """
        :type self: ObjectDB
        Returns:
            True if desc should get newlines, False if not
        """
        return (
            not self.db.do_not_format_desc and "player_made_room" not in self.tags.all()
        )

    def return_appearance(
        self, pobject, detailed=False, format_desc=False, show_contents=True
    ):
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
        desc = self.desc
        if strip_ansi:
            try:
                desc = parse_ansi(desc, strip_ansi=True)
            except (AttributeError, ValueError, TypeError):
                pass
        if desc and self.should_format_desc:
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

    @lazy_property
    def mods(self):
        from world.conditions.modifiers_handlers import ModifierHandler

        return ModifierHandler(self)

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

    def add_modifier(
        self,
        value,
        check_type,
        user_tag="",
        target_tag="",
        stat="",
        skill="",
        ability="",
    ):
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
        mod = self.modifiers.get_or_create(
            check=check_type,
            user_tag=user_tag,
            target_tag=target_tag,
            stat=stat,
            skill=skill,
            ability=ability,
        )[0]
        mod.value = value
        mod.save()
        return mod

    @lowercase_kwargs(
        "user_tags",
        "target_tags",
        "stat_list",
        "skill_list",
        "ability_list",
        default_append="",
    )
    def get_modifier(
        self,
        check_type,
        user_tags=None,
        target_tags=None,
        stat_list=None,
        skill_list=None,
        ability_list=None,
    ):
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
        return self.modifiers.filter(
            check__in=check_types,
            user_tag__in=user_tags,
            target_tag__in=target_tags,
            stat__in=stat_list,
            skill__in=skill_list,
            ability__in=ability_list,
        ).aggregate(Sum("value"))[1]


class TriggersMixin(object):
    """
    Adds triggerhandler to our objects.
    """

    @lazy_property
    def triggerhandler(self):
        """Adds a triggerhandler property for caching trigger checks to avoid excessive queries"""
        return TriggerHandler(self)


class ObjectMixins(
    NameMixins, DescMixins, AppearanceMixins, ModifierMixin, TriggersMixin
):
    item_data_class = ItemDataHandler

    @lazy_property
    def item_data(self):
        return self.item_data_class(self)


class CraftingMixins(object):
    item_data_class = CraftDataHandler
    junk_handler_class = RefundMaterialsJunkHandler
    default_type_description_name = None
    should_format_desc = False
    default_recipe = None
    default_quality_level = None
    default_crafted_by = None

    @lazy_property
    def junk_handler(self):
        return self.junk_handler_class(self)

    def return_appearance(
        self, pobject, detailed=False, format_desc=False, show_contents=True
    ):
        string = super(CraftingMixins, self).return_appearance(
            pobject,
            detailed=detailed,
            format_desc=format_desc,
            show_contents=show_contents,
        )
        string += self.item_data.get_crafting_desc()
        return string

    @property
    def type_description(self):
        if self.item_data.recipe:
            return self.item_data.recipe.name
        return self.default_type_description_name

    @property
    def default_size(self):
        if self.item_data.recipe:
            return self.item_data.recipe.volume
        return 1


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
        if isinstance(text, tuple) and text:
            text = text[0]
        options = options or {}
        options.update(kwargs.get("options", {}))
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
        lang = options.get("language", None)
        msg_content = options.get("msg_content", None)
        if lang and msg_content:
            try:
                if (
                    not self.check_permstring("builders")
                    and lang.lower() not in self.languages.known_languages
                ):
                    text = text.replace(
                        msg_content,
                        "<Something in a language that you don't understand>.",
                    )
            except AttributeError:
                pass
        if options.get("is_pose", False):
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
                        text = self.namex.sub(
                            r'"\1%s%s\2"' % (self.key, quote_color), text
                        )
            if self.ndb.pose_history is None:
                self.ndb.pose_history = []
            if from_obj == self:
                self.ndb.pose_history = []
            else:
                try:
                    origin = from_obj
                    if not from_obj and options.get("is_magic", False):
                        origin = "Magic System"
                    self.ndb.pose_history.append((str(origin), text))
                except AttributeError:
                    pass
        if options.get("box", False):
            text = text_box(text)
        if options.get("roll", False):
            if hasattr(self.item_data, "dice_string"):
                text = "|w<" + self.item_data.dice_string + "> |n" + text
        if options.get("is_magic", False):
            if text[0] == "\n":
                text = text[1:]
            text = "{w<" + self.magic_word + "> |n" + text
            if options.get("is_pose"):
                if self.db.posebreak:
                    text = "\n" + text
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
            if from_obj and (
                options.get("is_pose", False) or options.get("log_msg", False)
            ):
                private_msg = False
                if (
                    hasattr(self, "location")
                    and hasattr(from_obj, "location")
                    and self.location == from_obj.location
                ):
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
        if "no_ascii" in player_ob.tags.all():
            text = RE_ASCII.sub("", text)
            text = RE_ALT_ASCII.sub(r"\1", text)
        else:
            text = RE_ASCII.sub(r"\1", text)
            text = RE_ALT_ASCII.sub("", text)
        return text

    def msg_location_or_contents(self, text=None, **kwargs):
        """A quick way to ensure a room message, no matter what it's called on. Requires rooms have null location."""
        self.get_room().msg_contents(text=text, **kwargs)


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
        if (
            caller
            and not caller.check_permstring("builders")
            and not self.access(caller, "usekey")
        ):
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
        if self.item_data.is_locked:
            if caller:
                caller.msg("%s is already locked." % self)
            return
        self.item_data.is_locked = True
        msg = "%s is now locked." % self.key
        if caller:
            caller.msg(msg)
        self.location.msg_contents(msg, exclude=caller)
        # set the locked attribute of the destination of this exit, if we have one
        if (
            self.destination
            and hasattr(self.destination, "entrances")
            and self.destination.item_data.is_locked is False
        ):
            entrances = [
                ob
                for ob in self.destination.entrances
                if ob.item_data.is_locked is False
            ]
            if not entrances:
                self.destination.item_data.is_locked = True

    def unlock(self, caller=None):
        """
        :type self: ObjectDB:
        :param caller: ObjectDB
        :return:
        """
        if not self.has_lock_permission(caller):
            return
        self.locks.add("traverse: all()")
        if not self.item_data.is_locked:
            if caller:
                caller.msg("%s is already unlocked." % self)
            return
        self.item_data.is_locked = False
        msg = "%s is now unlocked." % self.key
        if caller:
            caller.msg(msg)
        self.location.msg_contents(msg, exclude=caller)
        if self.destination:
            self.destination.item_data.is_locked = False

    @property
    def currently_open(self):
        return not self.item_data.is_locked

    @property
    def displayable(self):
        return self.tags.get("displayable")

    @property
    def should_show_contents(self):
        return self.currently_open or self.displayable

    def return_appearance(
        self, pobject, detailed=False, format_desc=False, show_contents=True
    ):
        """
        :type self: AppearanceMixins, Container
        :param pobject: ObjectDB
        :param detailed: bool
        :param format_desc: bool
        :param show_contents: bool
        :return: str
        """
        show_contents = self.should_show_contents and show_contents
        base = super(LockMixins, self).return_appearance(
            pobject,
            detailed=detailed,
            format_desc=format_desc,
            show_contents=show_contents,
        )
        return base + "\nIt is currently %s." % (
            "locked" if self.item_data.is_locked else "unlocked"
        )


# noinspection PyUnresolvedReferences
class InformMixin(object):
    def inform(self, message, category=None, week=0, append=True):
        if not append:
            inform = self.informs.create(message=message, week=week, category=category)
        else:
            informs = self.informs.filter(
                category=category, week=week, read_by__isnull=True
            )
            if informs:
                inform = informs[0]
                inform.message += "\n\n" + message
                inform.save()
            else:
                inform = self.informs.create(
                    message=message, category=category, week=week
                )
        self.notify_inform(inform)

    def notify_inform(self, new_inform):
        index = list(self.informs.all()).index(new_inform) + 1
        self.msg("{yYou have new informs. Use {w@inform %s{y to read them.{n" % index)

    @property
    def can_receive_informs(self):
        return True
