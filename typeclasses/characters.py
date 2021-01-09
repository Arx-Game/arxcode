"""
Characters

Characters are (by default) Objects setup to be puppeted by Players.
They are what you "see" in game. The Character class in this module
is setup to be the "default" character type created by the default
creation commands.

"""
from django.urls import reverse
from evennia.objects.objects import DefaultCharacter

from server.utils.exceptions import PayError
from typeclasses.mixins import MsgMixins, ObjectMixins, NameMixins
from typeclasses.wearable.mixins import UseEquipmentMixins
from world.msgs.messagehandler import MessageHandler
from world.msgs.languagehandler import LanguageHandler
from evennia.utils.utils import lazy_property, variable_from_module
from world.stats_and_skills import do_dice_check
from world.magic.mixins import MagicMixins
from world.stat_checks.utils import get_check_by_name, get_check_maker_by_name
from world.stat_checks.constants import (
    DEATH_SAVE,
    UNCON_SAVE,
    PERMANENT_WOUND_SAVE,
    SERIOUS_WOUND,
    PERMANENT_WOUND,
)
from world.traits.traitshandler import Traitshandler


class Character(
    UseEquipmentMixins,
    NameMixins,
    MsgMixins,
    ObjectMixins,
    MagicMixins,
    DefaultCharacter,
):
    """
    The Character defaults to reimplementing some of base Object's hook methods with the
    following functionality:

    at_basetype_setup - always assigns the DefaultCmdSet to this object type
                    (important!)sets locks so character cannot be picked up
                    and its commands only be called by itself, not anyone else.
                    (to change things, use at_object_creation() instead).
    at_after_move - Launches the "look" command after every move.
    at_post_unpuppet(player) -  when Player disconnects from the Character, we
                    store the current location in the pre_logout_location Attribute and
                    move it to a None-location so the "unpuppeted" character
                    object does not need to stay on grid. Echoes "Player has disconnected"
                    to the room.
    at_pre_puppet - Just before Player re-connects, retrieves the character's
                    pre_logout_location Attribute and move it back on the grid.
    at_post_puppet - Echoes "PlayerName has entered the game" to the room.

    """

    def at_object_creation(self):
        """
        Called once, when this object is first created.
        """
        # setting up custom attributes for ArxMUSH
        # BriefMode is for toggling brief descriptions from rooms
        self.db.briefmode = False
        self.db.gender = "Female"
        self.db.age = 20
        self.db.concept = "None"
        self.db.fealty = "None"
        self.db.marital_status = "single"
        self.db.family = "None"
        self.db.dice_string = "Default Dicestring"
        self.at_init()
        self.locks.add("delete:perm(Immortals);tell:all()")

    @property
    def is_character(self):
        return True

    @lazy_property
    def messages(self):
        return MessageHandler(self)

    @lazy_property
    def languages(self):
        return LanguageHandler(self)

    @lazy_property
    def traits(self):
        return Traitshandler(self)

    @lazy_property
    def health_status(self):
        """
        Gets health_status object for a character that contains their state
        Returns:
            status (world.conditions.models.CharacterHealthStatus)
        """
        from world.conditions.models import CharacterHealthStatus

        try:
            return self.character_health_status
        except CharacterHealthStatus.DoesNotExist:
            return CharacterHealthStatus.objects.create(character=self)

    @property
    def sleep_description(self):
        return self.health_status.get_consciousness_display()

    @property
    def dead(self):
        return self.health_status.is_dead

    def at_after_move(self, source_location, **kwargs):
        """
        Hook for after movement. Look around, with brief determining how much detail we get.
        :param source_location: Room
        :return:
        """
        table = self.db.sitting_at_table
        if table and source_location != self.location:
            table.leave(self)
        if self.db.briefmode:
            string = ""
            # handle cases of self.location being None or not a Room object
            try:
                string = "{c%s{n" % self.location.name
                string += self.location.return_contents(self, show_places=False)
                string += self.location.event_string()
            except AttributeError:
                pass
            self.msg(string)
        else:
            self.msg(self.at_look(self.location))
        if self.ndb.waypoint:
            traversed = self.ndb.traversed or []
            try:
                traversed.append(source_location.id)
            except AttributeError:
                pass
            self.ndb.traversed = list(set(traversed))
            if self.location == self.ndb.waypoint:
                self.msg("You have reached your destination.")
                self.ndb.waypoint = None
                self.ndb.traversed = []
                return
            dirs = self.get_directions(self.ndb.waypoint)
            if dirs:
                self.msg("You sense your destination lies through the %s." % dirs)
            else:
                self.msg("You've lost track of how to get to your destination.")
                self.ndb.waypoint = None
                self.ndb.traversed = []
        if self.ndb.following and self.ndb.following.location != self.location:
            self.stop_follow()
        if self.db.room_title:
            self.attributes.remove("room_title")
        if self.combat.combat and self in self.combat.combat.ndb.observers:
            self.combat.combat.remove_observer(self)
        if self.location:
            self.location.triggerhandler.check_room_entry_triggers(self)

    def return_appearance(
        self, pobject, detailed=False, format_desc=False, show_contents=False
    ):
        """
        This is a convenient hook for a 'look'
        command to call.
        """
        if not pobject:
            return
        # get and identify all objects
        if pobject is self or pobject.check_permstring("builders"):
            detailed = True
        strip_ansi = pobject.db.stripansinames
        string = "{c%s{n" % self.get_fancy_name()
        # Health appearance will also determine whether we
        # use an alternate appearance if we are dead.
        health_appearance = self.get_health_appearance()
        # desc is our current appearance, can be fake. self.perm_desc is 'true' form
        desc = self.desc
        # to do: check to see through disguises
        if strip_ansi:
            try:
                from evennia.utils.ansi import parse_ansi

                desc = parse_ansi(desc, strip_ansi=True)
            except (AttributeError, ValueError, TypeError, UnicodeDecodeError):
                pass
        script = self.appearance_script
        if desc:
            extras = self.return_extras(pobject)
            if extras:
                extras += "\n"
            string += "\n\n%s%s" % (extras, desc)
        if script:
            scent = script.db.scent
            if scent:
                string += "\n\n%s{n" % scent
        if health_appearance:
            string += "\n\n%s" % health_appearance
        string += self.return_contents(pobject, detailed, strip_ansi=strip_ansi)
        return string

    @property
    def species(self):
        return self.db.species or "Human"

    @property
    def appearance_script(self):
        scripts = self.scripts.get("Appearance")
        if scripts:
            return scripts[0]

    def return_extras(self, pobject):
        """
        Return a string from glancing at us
        :param pobject: Character
        :return:
        """
        mask = self.db.mask
        if not mask:
            hair = self.db.haircolor or ""
            eyes = self.db.eyecolor or ""
            skin = self.db.skintone or ""
            height = self.db.height or ""
            species = self.species
            gender = self.db.gender or ""
            age = self.db.age
        else:
            hair = mask.db.haircolor or "--"
            eyes = mask.db.eyecolor or "--"
            skin = mask.db.skintone or "--"
            height = mask.db.height or "--"
            species = mask.db.species or "--"
            gender = mask.db.gender or "--"
            age = mask.db.age or "--"
        hair = hair.capitalize()
        eyes = eyes.capitalize()
        skin = skin.capitalize()
        gender = gender.capitalize()
        if pobject.check_permstring("builders"):
            true_age = self.db.real_age
            if true_age and true_age != age:
                pobject.msg("{wThis true age is:{n %s" % true_age)
        string = """
{w.---------------------->Physical Characteristics<---------------------.{n
{w|                                                                     |{n
{w| Species:{n %(species)-14s {wGender:{n %(gender)-15s {wAge:{n %(age)-15s{w|{n
{w| Height:{n %(height)-15s {wEye Color:{n %(eyes)-15s                  {w|{n
{w| Hair Color:{n %(hair)-11s {wSkin Tone:{n %(skin)-17s                {w|{n
{w.---------------------------------------------------------------------.{n
""" % (
            {
                "species": species,
                "hair": hair,
                "eyes": eyes,
                "height": height,
                "gender": gender,
                "age": age,
                "skin": skin,
            }
        )
        return string

    def death_process(self, *args, **kwargs):
        """
        This object dying. Set its state to dead, send out
        death message to location. Add death commandset.

        Returns:
            True if the character is dead, indicating other rolls for
            unconsciousness and the like should not proceed. False if
            they lived and should check for other effects.
        """
        if self.dead:
            return True
        self.health_status.set_dead()
        self.db.container = True
        if self.location:
            self.location.msg_contents("{r%s has died.{n" % self.name)
        try:
            from commands.cmdsets import death

            cmds = death.DeathCmdSet
            if cmds.key not in [ob.key for ob in self.cmdset.all()]:
                self.cmdset.add(cmds, permanent=True)
        except Exception as err:
            print("<<ERROR>>: Error when importing death cmdset: %s" % err)
        from server.utils.arx_utils import inform_staff

        if not self.is_npc:
            inform_staff("{rDeath{n: Character {c%s{n has died." % self.key)
        self.post_death()
        return True

    def post_death(self):
        if self.combat.combat:
            self.combat.combat.remove_combatant(self)

    def resurrect(self):
        """
        Cue 'Bring Me Back to Life' by Evanessence.
        """
        self.health_status.set_alive()
        self.db.container = False
        if self.location:
            self.location.msg_contents("{w%s has returned to life.{n" % self.name)
        try:
            from commands.cmdsets import death

            self.cmdset.delete(death.DeathCmdSet)
        except Exception as err:
            print("<<ERROR>>: Error when importing mobile cmdset: %s" % err)
        # we'll also be asleep when we're dead, so that we're resurrected unconscious if we're brought back
        self.fall_asleep(uncon=True, quiet=True)

    def fall_asleep(self, uncon=False, quiet=False, verb=None, **kwargs):
        """
        Falls asleep. Uncon flag determines if this is regular sleep,
        or unconsciousness.
        """
        if not self.conscious:
            return
        reason = " is %s and" % verb if verb else ""
        if uncon:
            self.health_status.set_unconscious()
        else:
            self.health_status.set_asleep()
        if self.location and not quiet:
            self.location.msg_contents(
                "%s%s falls %s." % (self.name, reason, self.sleep_description)
            )
        try:
            from commands.cmdsets import sleep

            cmds = sleep.SleepCmdSet
            if cmds.key not in [ob.key for ob in self.cmdset.all()]:
                self.cmdset.add(cmds, permanent=True)
        except Exception as err:
            print("<<ERROR>>: Error when importing sleep cmdset: %s" % err)

    @property
    def conscious(self):
        return not self.dead and self.health_status.is_conscious

    def wake_up(self, quiet=False, light_waking=False, inform_character=False):
        """
        Wakes up. if light_waking is set, only wake up if we're asleep,
        not unconscious.
        """
        if self.dead:
            if inform_character:
                self.msg("You are dead and cannot wake.")
            return
        if light_waking and not self.health_status.is_asleep:
            if inform_character:
                self.msg(
                    f"You are currently {self.health_status.get_consciousness_display()} and cannot wake."
                )
            return
        if self.location:
            if not quiet and not self.conscious:
                self.location.msg_contents("%s wakes up." % self.name)
        try:
            from commands.cmdsets import sleep

            self.cmdset.delete(sleep.SleepCmdSet)
        except Exception as err:
            print("<<ERROR>>: Error when importing mobile cmdset: %s" % err)
        self.health_status.set_awake()

    def change_health(self, amount, quiet=False, affect_real_dmg=True, wake=True):
        """
        Change character's health and maybe tell them about it.
        Positive amount will 'heal'. Negative will 'harm'.
        Sleeping characters can wake upon taking damage.
        """
        difference = self.get_damage_percentage(abs(amount))
        if not quiet:
            msg = "You feel "
            if difference <= 0:
                msg += "no "
            elif difference <= 10:
                msg += "a little "
            elif difference <= 25:
                pass
            elif difference <= 50:
                msg += "a lot "
            elif difference <= 75:
                msg += "significantly "
            else:
                msg += "profoundly "
            msg += "better" if amount > 0 else "worse"
            punctuation = "." if difference < 50 else "!"
            self.msg(msg + punctuation)
        if affect_real_dmg:
            self.real_dmg -= amount
        else:
            self.temp_dmg -= amount
        if difference:
            self.triggerhandler.check_health_change_triggers(amount)
        # if we're alseep, wake up on taking damage
        if wake and self.dmg <= self.max_hp and not self.conscious:
            self.wake_up(light_waking=True)

    def get_damage_percentage(self, damage=None):
        """Returns the float percentage of the health. If damage is not specified, we use self.dmg"""
        if damage is None:
            damage = self.dmg
        return int(100 * (float(damage) / float(self.max_hp)))

    def get_health_percentage(self):
        return 100 - self.get_damage_percentage()

    def get_health_appearance(self):
        """
        Return a string based on our current health.
        """
        wounds = self.get_damage_percentage()
        msg = "%s " % self.name
        if self.dead:
            return msg + "is currently dead."
        elif wounds <= 0:
            msg += "is in perfect health"
        elif not self.check_past_death_threshold():
            msg += "seems to have %s injuries" % self.get_wound_descriptor(self.dmg)
        else:
            msg += "is in critical condition - possibly dying"
        if not self.conscious:
            msg += ", and is %s" % self.sleep_description
        msg += "."
        msg += self.health_status.get_wound_string()
        return msg

    def get_wound_descriptor(self, dmg):
        wound = self.get_damage_percentage(dmg)
        if wound <= 0:
            wound_desc = "no"
        elif wound <= 10:
            wound_desc = "minor"
        elif wound <= 25:
            wound_desc = "moderate"
        elif wound <= 50:
            wound_desc = "serious"
        elif wound <= 75:
            wound_desc = "severe"
        elif wound < 200:
            wound_desc = "grievous"
        else:
            wound_desc = "grave"
        return wound_desc

    def sensing_check(self, difficulty=15, invis=False, allow_wake=False):
        """
        See if the character detects something that is hiding or invisible.
        The difficulty is supplied by the calling function.
        Target can be included for additional situational
        """
        if not self.conscious and not allow_wake:
            return -100
        roll = do_dice_check(
            self, stat="perception", stat_keep=True, difficulty=difficulty
        )
        return roll

    def get_fancy_name(self, short=False, display_mask=True):
        """
        Returns either an illusioned name, a long_name with titles, or our key.
        """
        if self.db.false_name and display_mask:
            return self.db.false_name
        if not short and self.db.longname:
            return self.db.longname
        return self.db.colored_name or self.key

    @property
    def max_hp(self):
        """Returns our max hp"""
        return self.traits.get_max_hp()

    @property
    def current_hp(self):
        return self.max_hp - self.dmg

    def check_past_death_threshold(self):
        """
        Returns whether our character is past the threshold where we should
        check for death.
        """
        check = get_check_by_name(DEATH_SAVE)
        return check.should_trigger(self)

    def check_past_unconsciousness_threshold(self):
        check = get_check_by_name(UNCON_SAVE)
        return check.should_trigger(self)

    def check_past_permanent_wound_threshold(self, damage):
        check = get_check_by_name(PERMANENT_WOUND_SAVE)
        percent_damage = (damage * 100.0) / self.max_hp
        return check.should_trigger(self, percent_damage=percent_damage)

    @property
    def dmg(self):
        """Returns how much damage we've taken."""
        return self.real_dmg + self.temp_dmg

    @dmg.setter
    def dmg(self, value):
        self.real_dmg = value

    # alias for dmg
    damage = dmg

    @property
    def temp_dmg(self):
        if self.ndb.temp_dmg is None:
            self.ndb.temp_dmg = 0
        return self.ndb.temp_dmg

    @temp_dmg.setter
    def temp_dmg(self, value):
        self.ndb.temp_dmg = value

    @property
    def real_dmg(self):
        return self.health_status.damage

    @real_dmg.setter
    def real_dmg(self, dmg):
        if dmg < 1:
            dmg = 0
        self.health_status.damage = dmg
        self.health_status.save()

    @property
    def xp(self):
        if self.db.xp is None:
            self.db.xp = 0
        return self.db.xp

    @xp.setter
    def xp(self, value):
        self.db.xp = value

    def adjust_xp(self, value):
        """
        Spend or earn xp. Total xp keeps track of all xp we've earned on this
        character, and isn't lowered by spending xp. Checks for having sufficient
        xp should be before this takes place, so we'll raise an exception if they
        can't pay the cost.
        """
        if not self.db.total_xp:
            self.db.total_xp = 0
        if value > 0:
            self.db.total_xp += value
            try:
                self.roster.adjust_xp(value)
            except (AttributeError, ValueError, TypeError):
                pass
            self.xp += value
        else:
            self.pay_xp(abs(value))

    def pay_xp(self, value):
        """Attempts to spend xp"""
        if value < 0:
            raise ValueError("Attempted to spend negative xp.")
        if self.xp < value:
            raise PayError(
                "You tried to spend %s xp, but only have %s available."
                % (value, self.xp)
            )
        self.xp -= value
        self.msg("You spend %s xp and have %s remaining." % (value, self.xp))

    def follow(self, targ):
        if not targ.ndb.followers:
            targ.ndb.followers = []
        targ.msg(
            "%s starts to follow you. To remove them as a follower, use 'ditch'."
            % self.name
        )
        if self not in targ.ndb.followers:
            targ.ndb.followers.append(self)
        self.msg(
            "You start to follow %s. To stop following, use 'follow' with no arguments."
            % targ.name
        )
        self.ndb.following = targ

    def stop_follow(self):
        f_targ = self.ndb.following
        if not f_targ:
            return
        self.msg("You stop following %s." % f_targ.name)
        if f_targ.ndb.followers:
            try:
                f_targ.ndb.followers.remove(self)
                f_targ.msg("%s stops following you." % self.name)
            except (ValueError, TypeError, AttributeError):
                pass
        self.ndb.following = None

    def msg_watchlist(self, msg):
        """
        Sends a message to all players who are watching this character if
        we are not hiding from watch.
        """
        watchers = self.db.watched_by or []
        pc = self.player_ob
        if not pc:
            return
        if not watchers or pc.db.hide_from_watch:
            return
        for watcher in watchers:
            spam = watcher.ndb.journal_spam or []
            if self not in spam:
                watcher.msg(msg)
                spam.append(self)
                watcher.ndb.journal_spam = spam

    def _get_max_support(self):
        try:
            dompc = self.player_ob.Dominion
            remaining = 0
            for member in dompc.memberships.filter(deguilded=False):
                remaining += member.pool_share
            for ren in dompc.renown.all():
                remaining += ren.level
        except (TypeError, AttributeError, ValueError):
            return 0
        interval = self.social_clout
        multiplier = 1.0
        total = 0
        if interval <= 0:
            return 0
        while multiplier > 0:
            if interval >= remaining:
                total += remaining * multiplier
                return int(total)
            total += interval * multiplier
            multiplier -= 0.25
            remaining -= interval
        return int(total)

    max_support = property(_get_max_support)

    @property
    def social_clout(self):
        """Another representation of social value of a character"""
        total = 0
        my_skills = self.traits.skills
        skills_used = {
            "diplomacy": 2,
            "empathy": 2,
            "seduction": 2,
            "etiquette": 2,
            "manipulation": 2,
            "propaganda": 2,
            "intimidation": 1,
            "leadership": 1,
            "streetwise": 1,
            "performance": 1,
            "haggling": 1,
        }
        stats_used = {"charm": 2, "composure": 1, "command": 1}
        for skill, exponent in skills_used.items():
            total += pow(my_skills.get(skill, 0), exponent)
        for stat, exponent in stats_used.items():
            total += pow(self.traits.get_stat_value(stat), exponent)
        return total // 5

    @property
    def guards(self):
        if self.db.assigned_guards is None:
            self.db.assigned_guards = []
        return self.db.assigned_guards

    def remove_guard(self, guard):
        """
        This discontinues anything we were using the guard for.
        Args:
            guard: Previously a guard, possibly a retainer.
        """
        if guard in self.guards:
            self.guards.remove(guard)
        if self.messages.custom_messenger == guard:
            self.messages.custom_messenger = None

    @property
    def num_guards(self):
        return sum(ob.quantity for ob in self.guards)

    @property
    def present_guards(self):
        return [ob for ob in self.guards if ob.location == self.location]

    @property
    def num_armed_guards(self):
        try:
            return sum([ob.num_armed_guards for ob in self.present_guards])
        except TypeError:
            return 0

    @property
    def max_guards(self):
        try:
            return 15 - (self.db.social_rank or 10)
        except TypeError:
            return 5

    def get_directions(self, room):
        """
        Uses the ObjectDB manager and repeated related_set calls in order
        to find the exit in the current room that directly points to it.
        """
        loc = self.location
        if not loc:
            return
        x_ori = loc.db.x_coord
        y_ori = loc.db.y_coord
        x_dest = room.db.x_coord
        y_dest = room.db.y_coord
        check_exits = []
        try:
            x = x_dest - x_ori
            y = y_dest - y_ori
            dest = ""
            if y > 0:
                dest += "north"
            if y < 0:
                dest += "south"
            check_exits.append(dest)
            if x > 0:
                dest += "east"
                check_exits.append("east")
            if x < 0:
                dest += "west"
                check_exits.append("west")
            if abs(x) > abs(y):
                check_exits.reverse()
            # inserts the NE/SE/SW/NW direction at 0 to be highest priority
            check_exits.insert(0, dest)
            for dirname in check_exits:
                if loc.locations_set.filter(db_key__iexact=dirname).exclude(
                    db_destination__in=self.ndb.traversed or []
                ):
                    return "{c" + dirname + "{n"
            dest = (
                "{c"
                + dest
                + "{n roughly. Please use '{w@map{n' to determine an exact route"
            )
        except (AttributeError, TypeError, ValueError):
            print("Error in using directions for rooms: %s, %s" % (loc.id, room.id))
            print(
                "origin is (%s,%s), destination is (%s, %s)"
                % (x_ori, y_ori, x_dest, y_dest)
            )
            self.msg("Rooms not properly set up for @directions. Logging error.")
            return
        # try to find it through traversal
        base_query = "db_destination_id"
        exit_name = []
        iterations = 0
        # anything beyond 10 squares becomes extremely lengthy
        max_iter = 5
        exit_ids = [ob.id for ob in loc.exits]
        q_add = ""
        from django.db.models import Q

        exclude_ob = Q()

        def get_new_exclude_ob():
            """Helper function to build Q() objects to exclude"""
            base_exclude_query = "db_tags__db_key"
            other_exclude_query = {q_add + "db_destination_id": loc.id}
            traversed_query = {
                q_add + "db_destination_id__in": self.ndb.traversed or []
            }
            exclude_query = q_add + base_exclude_query
            exclude_dict = {exclude_query: "secret"}
            return Q(**exclude_dict) | Q(**other_exclude_query) | Q(**traversed_query)

        while not exit_name and iterations < max_iter:
            q_add = "db_destination__locations_set__" * iterations
            query = q_add + base_query
            filter_dict = {query: room.id}
            exclude_ob |= get_new_exclude_ob()
            q_ob = Q(Q(**filter_dict) & ~exclude_ob)
            exit_name = (
                loc.locations_set.distinct()
                .filter(id__in=exit_ids)
                .exclude(exclude_ob)
                .filter(q_ob)
            )
            iterations += 1
        if not exit_name:
            return "{c" + dest + "{n"
        return "{c" + str(exit_name[0]) + "{n"

    def at_post_puppet(self):
        """
        Called just after puppeting has completed.

        :type self: Character
        """

        super(Character, self).at_post_puppet()
        try:
            self.messages.messenger_notification(2, force=True)
        except (AttributeError, ValueError, TypeError):
            import traceback

            traceback.print_exc()

        guards = self.guards
        for guard in guards:
            if guard.discreet:
                continue
            docked_location = guard.db.docked
            if docked_location and docked_location == self.location:
                guard.summon()

    def at_post_unpuppet(self, player, session=None, **kwargs):
        """
        We stove away the character when the player goes ooc/logs off,
        otherwise the character object will remain in the room also after the
        player logged off ("headless", so to say).

        :type self: Character
        :type player: Player
        :type session: Session
        """
        super(Character, self).at_post_unpuppet(player, session)
        if not self.sessions.count():
            table = self.db.sitting_at_table
            if table:
                table.leave(self)
            guards = self.guards
            for guard in guards:
                try:
                    if guard.location and "persistent_guard" not in guard.tags.all():
                        guard.dismiss()
                except AttributeError:
                    continue

    @property
    def portrait(self):
        from web.character.models import Photo

        try:
            return self.roster.profile_picture
        except (AttributeError, Photo.DoesNotExist):
            return None

    def get_absolute_url(self):
        return reverse("character:sheet", kwargs={"object_id": self.id})

    @lazy_property
    def combat(self):
        from typeclasses.scripts.combat.combatant import CombatHandler

        return CombatHandler(self)

    def view_stats(self, viewer, combat=False):
        from commands.base_commands.roster import (
            display_stats,
            display_skills,
            display_abilities,
        )

        display_stats(viewer, self)
        display_skills(viewer, self)
        display_abilities(viewer, self)
        if combat:
            viewer.msg(self.combat.display_stats())

    @property
    def posecount(self):
        return self.db.pose_count or 0

    @posecount.setter
    def posecount(self, val):
        self.db.pose_count = val

    @property
    def previous_posecount(self):
        return self.db.previous_posecount or 0

    @previous_posecount.setter
    def previous_posecount(self, val):
        self.db.previous_posecount = val

    @property
    def total_posecount(self):
        return self.posecount + self.previous_posecount

    def announce_move_from(self, destination, msg=None, mapping=None, **kwargs):
        """
        Called if the move is to be announced. This is
        called while we are still standing in the old
        location.
        Args:
            destination (Object): The place we are going to.
            msg (str, optional): a replacement message.
            mapping (dict, optional): additional mapping objects.
        """

        def format_string(viewer):
            if msg:
                return msg
            if secret:
                return "%s is leaving." % self.get_display_name(viewer)
            else:
                return "%s is leaving, heading for %s." % (
                    self.get_display_name(viewer),
                    destination.get_display_name(viewer),
                )

        if not self.location:
            return
        secret = False
        if mapping:
            secret = mapping.get("secret", False)
        for obj in self.location.contents:
            if obj != self:
                string = format_string(obj)
                obj.msg(string)

    def announce_move_to(self, source_location, msg=None, mapping=None, **kwargs):
        """
        Called after the move if the move was not quiet. At this point
        we are standing in the new location.

        Args:
            source_location (Object): The place we came from
            msg (str, optional): the replacement message if location.
            mapping (dict, optional): additional mapping objects.

        You can override this method and call its parent with a
        message to simply change the default message.  In the string,
        you can use the following as mappings (between braces):
            object: the object which is moving.
            exit: the exit from which the object is moving (if found).
            origin: the location of the object before the move.
            destination: the location of the object after moving.

        """
        if not source_location and self.location.has_account:
            # This was created from nowhere and added to a player's
            # inventory; it's probably the result of a create command.
            string = "You now have %s in your possession." % self.get_display_name(
                self.location
            )
            self.location.msg(string)
            return

        secret = False
        if mapping:
            secret = mapping.get("secret", False)

        def format_string(viewer):
            if msg:
                return msg
            if secret:
                return "%s arrives." % self.get_display_name(viewer)
            else:
                from_str = (
                    " from %s" % source_location.get_display_name(viewer)
                    if source_location
                    else ""
                )
                return "%s arrives%s." % (self.get_display_name(viewer), from_str)

        for obj in self.location.contents:
            if obj != self:
                string = format_string(obj)
                obj.msg(string)

    @property
    def can_crit(self):
        try:
            if self.roster.roster.name == "Active":
                return True
            else:
                return False
        except AttributeError:
            return False

    @property
    def titles(self):
        full_titles = self.db.titles or []
        return ", ".join(str(ob) for ob in full_titles)

    @property
    def is_npc(self):
        if self.tags.get("npc"):
            return True
        try:
            if self.roster.roster.name == "Unavailable":
                return True
        except AttributeError:
            pass
        return False

    @property
    def attackable(self):
        return not bool(self.tags.get("unattackable"))

    @property
    def boss_rating(self):
        return self.traits.boss_rating

    @boss_rating.setter
    def boss_rating(self, value):
        self.traits.set_other_value("boss_rating", value)

    @property
    def sleepless(self):
        """Cannot fall unconscious - undead, etc"""
        return bool(self.tags.get("sleepless"))

    @property
    def defense_modifier(self):
        return self.db.defense_modifier or 0

    @defense_modifier.setter
    def defense_modifier(self, value):
        self.db.defense_modifier = value

    @property
    def attack_modifier(self):
        base = self.db.attack_modifier or 0
        return base + (self.boss_rating * 10)

    @attack_modifier.setter
    def attack_modifier(self, value):
        self.db.attack_modifier = value

    def search(
        self,  # type: Character
        searchdata,
        global_search=False,
        use_nicks=True,
        typeclass=None,
        location=None,
        attribute_name=None,
        quiet=False,
        exact=False,
        candidates=None,
        nofound_string=None,
        multimatch_string=None,
        use_dbref=True,
    ):
        from django.conf import settings

        # if we're staff, we just return the regular search method:
        if self.check_permstring("builders"):
            return super(Character, self).search(
                searchdata,
                global_search=global_search,
                use_nicks=use_nicks,
                typeclass=typeclass,
                location=location,
                attribute_name=attribute_name,
                quiet=quiet,
                exact=exact,
                candidates=candidates,
                nofound_string=nofound_string,
                multimatch_string=multimatch_string,
                use_dbref=use_dbref,
            )
        # we're not staff. Our search results must filter objects out:
        results = super(Character, self).search(
            searchdata,
            global_search=global_search,
            use_nicks=use_nicks,
            typeclass=typeclass,
            location=location,
            attribute_name=attribute_name,
            quiet=True,
            exact=exact,
            candidates=candidates,
            nofound_string=nofound_string,
            multimatch_string=multimatch_string,
            use_dbref=use_dbref,
        )
        # filter out objects we can't see:
        results = [ob for ob in results if ob.access(self, "view")]
        # filter out masked objects unless our search wasn't by their real name:
        results = [
            ob
            for ob in results
            if not ob.db.false_name or searchdata.lower() != ob.key.lower()
        ]
        # quiet means that messaging is handled elsewhere
        if quiet:
            return results
        if location == self:
            nofound_string = nofound_string or "You don't carry '%s'." % searchdata
            multimatch_string = (
                multimatch_string or "You carry more than one '%s':" % searchdata
            )
        # call the _AT_SEARCH_RESULT func to transform our results and send messages
        _AT_SEARCH_RESULT = variable_from_module(
            *settings.SEARCH_AT_RESULT.rsplit(".", 1)
        )
        return _AT_SEARCH_RESULT(
            results,
            self,
            query=searchdata,
            nofound_string=nofound_string,
            multimatch_string=multimatch_string,
        )

    def can_be_trained_by(self, trainer):
        """
        Checks if we can be trained by trainer. If False, send a message to trainer and let them know why. The default
        implementation will just return True, but this is overridden in Retainers, for example.

        Args:
            trainer: Character to check training

        Returns:
            True if we can be trained, False otherwise.
        """
        if self.db.trainer:
            trainer.msg("They have already been trained.")
            return False
        return True

    def post_training(self, trainer, trainer_msg="", targ_msg="", **kwargs):
        """
        Handles bookkeeping after this character is trained.

        Args:
            trainer: Character that trained us.
            trainer_msg (str): Message to send to trainer
            targ_msg (str): Message to send to this Character

        Returns:
            True if everything went off. Used for trying to catch extremely elusive caching errors.
        """
        from server.utils.arx_utils import trainer_diagnostics

        currently_training = trainer.db.currently_training or []
        # num_trained is redundancy to attempt to prevent cache errors.
        num_trained = trainer.db.num_trained or len(currently_training)
        if num_trained < len(currently_training):
            num_trained = len(currently_training)
        num_trained += 1
        self.db.trainer = trainer
        currently_training.append(self)
        trainer.db.currently_training = currently_training
        trainer.db.num_trained = num_trained
        if trainer_msg:
            trainer.msg(trainer_msg)
        if targ_msg:
            self.msg(targ_msg)
        print("Character.post_training call: %s" % trainer_diagnostics(trainer))
        return True

    def show_online(self, caller, check_puppet=True):
        """

        Args:
            caller: Player who is checking to see if they can see us online
            check_puppet: Whether the Character needs an active puppet to show as online

        Returns:
            True if we're online and the player has privileges to see us. False otherwise
        """
        if check_puppet:
            if not self.sessions.all():
                return False
            player = self.player
        else:
            player = self.player_ob
        if not player:
            return False
        if not player.db.hide_from_watch:
            return True
        if caller.check_permstring("builders"):
            return True
        # we're hiding from watch and caller is not staff, so they don't see us online
        return False

    @property
    def glass_jaw(self):
        return False

    @property
    def valid_actions(self):
        from world.dominion.models import PlotAction
        from django.db.models import Q

        return (
            PlotAction.objects.filter(Q(dompc=self.dompc) | Q(assistants=self.dompc))
            .exclude(status=PlotAction.CANCELLED)
            .distinct()
        )

    @property
    def past_actions(self):
        return self.player_ob.past_actions

    @property
    def past_participated_actions(self):
        return self.player_ob.past_participated_actions

    @property
    def recent_actions(self):
        return self.player_ob.recent_actions

    @property
    def recent_assists(self):
        return self.player_ob.recent_assists

    @property
    def truesight(self):
        return self.check_permstring("builders") or self.tags.get("story_npc")

    def get_display_name(self, looker, **kwargs):
        if not self.is_disguised:
            return super(Character, self).get_display_name(looker, **kwargs)
        name = self.name
        try:
            if looker.truesight:
                name = "%s (%s)" % (self.name, self.key)
                if looker.check_permstring("builders"):
                    name += "(%s)" % self.id
        except AttributeError:
            pass
        return name

    @property
    def dompc(self):
        """Returns our Dominion object"""
        try:
            return self.player_ob.Dominion
        except AttributeError:
            return None

    @property
    def secrets(self):
        from web.character.models import Clue

        return (
            self.roster.clue_discoveries.filter(
                clue__clue_type=Clue.CHARACTER_SECRET, clue__tangible_object=self
            )
            .exclude(clue__desc="")
            .distinct()
        )

    def at_magic_exposure(self, alignment=None, affinity=None, strength=10):
        if not self.practitioner:
            return

        if not alignment:
            from world.magic.models import Alignment

            alignment = Alignment.PRIMAL

        self.practitioner.at_magic_exposure(
            alignment=alignment, affinity=affinity, strength=strength
        )

    @property
    def char_ob(self):
        return self

    def check_staff_or_gm(self):
        if self.check_permstring("builders"):
            return True
        if not self.location or not self.dompc:
            return False
        event = self.location.event
        if not event:
            return False
        return self.dompc in event.gms.all()

    def take_damage(
        self,
        amount: int,
        affect_real_damage: bool = True,
        can_kill: bool = True,
        cleaving: bool = False,
        private: bool = False,
        risk: int = 4,
    ):
        # apply AE damage to multinpcs if we're cleaving
        # TODO: move ae_dmg application to subclass
        if cleaving and hasattr(self, "ae_dmg"):
            self.ae_dmg += amount
        self.change_health(
            -amount, quiet=True, affect_real_dmg=affect_real_damage, wake=False
        )
        # check for death
        if can_kill and affect_real_damage:
            self.check_for_death(private)
        # if character is now dead, we're done
        if self.dead:
            return
        # determine if perm save is necessary
        self.check_for_permanent_wound(affect_real_damage, amount)
        # determine if unconsciousness save is necessary
        self.check_for_unconsciousness(private)

    def check_for_death(self, private=False):
        """Heads you live, tails you die. Okay, it's a bit more granular than that.
        But still, this is where you make a check to see if a character can die.

        Args:
            private (bool): Whether to broadcast msg

        Returns:
            True if the character is dead, indicating nothing else should happen.
            False if they lived and should check for unconsciousness/permanent wounds.
        """
        # Now you're just beating a dead horse
        if self.dead:
            return True
        # we might not even have taken enough damage yet to die. Whew.
        if not self.check_past_death_threshold():
            return False
        # if we're conscious, room for combat not permit us to be one-shot if not an npc
        if self.combat.combat:
            allow_one_shot = self.combat.combat.ndb.random_deaths
            if not self.is_npc and self.conscious and not allow_one_shot:
                return False
        # Hold your breath, kids. This is where the roll to live happens
        roller = get_check_maker_by_name(DEATH_SAVE, self)
        roller.make_check_and_announce()
        # if we succeeded our roll, we don't die
        if roller.is_success:
            if not private:
                self.msg_location_or_contents(
                    "%s remains alive, but close to death." % self
                )
            # if we survive, we're still unconscious
            self.fall_asleep(uncon=True, verb="incapacitated")
            return False
        # OH NOES. May flights of angels sing us to our rest.
        return self.death_process()

    def check_for_unconsciousness(self, private=False):
        if not self.conscious:
            return
        if not self.check_past_unconsciousness_threshold():
            return
        roller = get_check_maker_by_name(UNCON_SAVE, self)
        roller.make_check_and_announce()
        if roller.is_success:
            if not private:
                self.msg_location_or_contents("%s remains capable of fighting." % self)
            return
        self.fall_asleep(uncon=True, verb="incapacitated")

    def check_for_permanent_wound(self, affect_real_damage, amount):
        if not affect_real_damage:
            return
        if not self.check_past_permanent_wound_threshold(amount):
            return
        roller = get_check_maker_by_name(PERMANENT_WOUND_SAVE, self)
        roller.make_check_and_announce()
        if roller.is_success:
            self.msg_location_or_contents(
                f"Despite the terrible damage, {self} does not take a permanent wound."
            )
            return

        if roller.outcome.effect == SERIOUS_WOUND:
            self.traits.create_wound(SERIOUS_WOUND)
            self.msg_location_or_contents(f"{self} has suffered a serious wound!")
        if roller.outcome.effect == PERMANENT_WOUND:
            self.traits.create_wound(PERMANENT_WOUND)
            self.msg_location_or_contents(f"{self} has suffered a permanent wound!")
