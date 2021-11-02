"""
Exits

Exits are connectors between Rooms. An exit always has a destination property
set and has a single command defined on itself with the same name as its key,
for allowing Characters to traverse the exit to its destination.

"""
from evennia import DefaultExit
from typeclasses.mixins import ObjectMixins, NameMixins, LockMixins, BaseObjectMixins
from evennia.commands import command, cmdset
from world.exploration.models import ShardhavenLayoutExit, ShardhavenObstacle, Monster
from server.utils.arx_utils import commafy, a_or_an
from commands.mixins import RewardRPToolUseMixin


class Exit(LockMixins, ObjectMixins, DefaultExit):
    """
    Exits are connectors between rooms. Exits are normal Objects except
    they defines the `destination` property. It also does work in the
    following methods:

     basetype_setup() - sets default exit locks (to change, use `at_object_creation` instead).
     at_cmdset_get(**kwargs) - this is called when the cmdset is accessed and should
                              rebuild the Exit cmdset along with a command matching the name
                              of the Exit object. Conventionally, a kwarg `force_init`
                              should force a rebuild of the cmdset, this is triggered
                              by the `@alias` command when aliases are changed.
     at_failed_traverse() - gives a default error message ("You cannot
                            go there") if exit traversal fails and an
                            attribute `err_traverse` is not defined.

    Relevant hooks to overload (compared to other types of Objects):
        at_traverse(traveller, target_loc) - called to do the actual traversal and calling of the other hooks.
                                            If overloading this, consider using super() to use the default
                                            movement implementation (and hook-calling).
        at_after_traverse(traveller, source_loc) - called by at_traverse just after traversing.
        at_failed_traverse(traveller) - called by at_traverse if traversal failed for some reason. Will
                                        not be called if the attribute `err_traverse` is
                                        defined, in which case that will simply be echoed.
    """

    def can_traverse(self, character):
        if self.destination.check_banned(character):
            character.msg("You have been banned from entering there.")
            return
        if self.destination.pets_banned and character.has_pets:
            pet_fail = "Pets are not allowed there. "
            if character not in self.destination.pets_allow_list:
                character.msg(f"{pet_fail}(Try 'guards/dismiss' first)")
                return
            elif character.fakename:
                character.msg(
                    f"{pet_fail}Yours would normally be an exception, but you are not recognized in disguise."
                )
                return
        if self.access(character, "traverse"):
            # we may traverse the exit.
            return True
        elif character.db.bypass_locked_doors:
            msg = character.db.bypass_locked_doors or "You ignore the locked door."
            character.msg(msg)
            return True
        else:
            # exit is locked
            if self.db.err_traverse:
                # if exit has a better error message, let's use it.
                character.msg(self.db.err_traverse)
            else:
                # No shorthand error message. Call hook.
                self.at_failed_traverse(character)

    def create_exit_cmdset(self, exidbobj):
        """
        Helper function for creating an exit command set + command.

        The command of this cmdset has the same name as the Exit object
        and allows the exit to react when the player enter the exit's name,
        triggering the movement between rooms.

        Note that exitdbobj is an ObjectDB instance. This is necessary
        for handling reloads and avoid tracebacks if this is called while
        the typeclass system is rebooting.
        """
        exitkey = exidbobj.db_key.strip().lower()
        exitaliases = list(exidbobj.aliases.all())

        # noinspection PyUnresolvedReferences
        class ExitCommand(command.Command):
            """
            This is a command that simply cause the caller
            to traverse the object it is attached to.
            """

            obj = None

            def func(self):
                """Default exit traverse if no syscommand is defined."""
                if self.obj.password:
                    # get our number of password_failures for this caller
                    yikes = 10
                    failures = self.obj.password_failures.get(self.caller, 0)
                    # return if we had too many failures
                    if failures > yikes:
                        msg = "Attempting this password AGAIN would result in Privacy Disturbance "
                        msg += "Citation 47c, as per Decree 332 Appendix M of Queen Alaricetta the "
                        msg += "Prudent. Best not to try it."
                        self.msg(msg)
                        return
                    attempt = yield self.obj.password_question
                    if attempt != self.obj.password:
                        self.obj.at_password_fail(self.caller)
                        return
                if self.obj.can_traverse(self.caller):
                    self.obj.at_traverse(self.caller, self.obj.destination)

        # noinspection PyUnresolvedReferences
        class PassExit(command.Command):
            def func(self):
                # TODO: Figure out way to make this DRY
                if self.obj.password:
                    # get our number of password_failures for this caller
                    yikes = 10
                    failures = self.obj.password_failures.get(self.caller, 0)
                    # return if we had too many failures
                    if failures > yikes:
                        msg = "Attempting this password AGAIN would result in Privacy Disturbance "
                        msg += "Citation 47c, as per Decree 332 Appendix M of Queen Alaricetta the "
                        msg += "Prudent. Best not to try it."
                        self.caller.msg(msg)
                        return
                    attempt = yield self.obj.password_question
                    if attempt != self.obj.password:
                        self.obj.at_password_fail(self.caller)
                        return
                # iff locked, then we can pass through it if we have a key
                if self.obj.item_data.is_locked:
                    if not self.obj.access(self.caller, "usekey"):
                        self.caller.msg("You don't have a key to this exit.")
                        return
                    else:
                        self.obj.at_traverse(self.caller, self.obj.destination)
                        return
                # normal checks for non-locked doors
                if self.obj.can_traverse(self.caller):
                    self.obj.at_traverse(self.caller, self.obj.destination)

        # noinspection PyUnresolvedReferences
        class KnockExit(RewardRPToolUseMixin, command.Command):
            simplified_key = "knock"

            def func(self):
                self.caller.msg("You knocked on the door.")
                self.obj.destination.msg_contents(
                    "{wThere is a knock coming from %s." % self.obj.reverse_exit
                )
                self.mark_command_used()

        # create an exit command. We give the properties here,
        # to always trigger metaclass preparations
        exitcmd = ExitCommand(
            key=exitkey,
            aliases=exitaliases,
            locks=str(exidbobj.locks),
            auto_help=False,
            destination=exidbobj.db_destination,
            arg_regex=r"$",
            is_exit=True,
            obj=exidbobj,
        )
        passaliases = ["pass %s" % alias for alias in exitaliases]
        passcmd = PassExit(
            key="pass %s" % exitkey,
            aliases=passaliases,
            is_exit=True,
            auto_help=False,
            obj=exidbobj,
        )
        knockaliases = ["knock %s" % alias for alias in exitaliases]
        knockcmd = KnockExit(
            key="knock %s" % exitkey,
            aliases=knockaliases,
            is_exit=True,
            auto_help=False,
            obj=exidbobj,
        )
        # create a cmdset
        exit_cmdset = cmdset.CmdSet(None)
        exit_cmdset.key = "_exitset"
        exit_cmdset.priority = 101  # equal to channel priority
        exit_cmdset.duplicates = True
        # add command to cmdset
        exit_cmdset.add(exitcmd)
        exit_cmdset.add(passcmd)
        exit_cmdset.add(knockcmd)
        return exit_cmdset

    def check_banned(self, character):
        return self.destination.check_banned(character)

    def at_traverse(
        self,
        traversing_object,
        target_location,
        key_message=True,
        special_entrance=None,
        quiet=False,
        allow_follow=True,
    ):
        """
        This implements the actual traversal. The traverse lock has already been
        checked (in the Exit command) at this point.
        """
        source_location = traversing_object.location
        secret = self.tags.get("secret")
        mapping = {"secret": secret}
        if traversing_object.move_to(target_location, quiet=quiet, mapping=mapping):
            # if the door was locked, send a message about it unless we were following
            if key_message and self.item_data.is_locked:
                msg = (
                    special_entrance
                    or self.db.success_traverse
                    or "You unlock the locked door, then close and lock it behind you."
                )
                traversing_object.msg(msg)
            self.at_after_traverse(traversing_object, source_location)
            # move followers
            if traversing_object and traversing_object.ndb.followers and allow_follow:
                invalid_followers = []
                valid_followers = []
                leader = None
                for follower in traversing_object.ndb.followers:
                    # only move followers who are conscious
                    if not follower.conscious:
                        invalid_followers.append(follower)
                        continue
                    # only move followers who were in same square
                    if follower.location == source_location:
                        fname = follower.ndb.following
                        if follower.ndb.followers and fname in follower.ndb.followers:
                            # this would be an infinite loop
                            invalid_followers.append(follower)
                            continue
                        if fname == traversing_object:
                            follower.msg("You follow %s." % fname.name)
                        else:  # not marked as following us
                            invalid_followers.append(follower)
                            continue
                        # followers won't see the message about the door being locked
                        self.at_traverse(
                            follower, self.destination, key_message=False, quiet=True
                        )
                        valid_followers.append(follower.name)
                        leader = fname
                    else:
                        invalid_followers.append(follower)
                # make all characters who could not follow stop following us
                for invalid in invalid_followers:
                    if invalid.ndb.following == traversing_object:
                        invalid.stop_follow()
                    else:
                        traversing_object.ndb.followers.remove(invalid)
                if valid_followers:
                    verb = "arrive" if len(valid_followers) > 1 else "arrives"
                    fol_msg = "%s %s, following %s." % (
                        ", ".join(valid_followers),
                        verb,
                        leader.name,
                    )
                    leave_msg = fol_msg.replace("arrive", "leave")
                    self.destination.msg_contents(fol_msg)
                    self.location.msg_contents(leave_msg)
        else:
            if self.db.err_traverse:
                # if exit has a better error message, let's use it.
                self.caller.msg(self.db.err_traverse)
            else:
                # No shorthand error message. Call hook.
                self.at_failed_traverse(traversing_object)

    # noinspection PyMethodMayBeStatic
    def at_failed_traverse(self, traversing_object):
        """
        This is called if an object fails to traverse this object for some
        reason. It will not be called if the attribute "err_traverse" is
        defined, that attribute will then be echoed back instead as a
        convenient shortcut.

        (See also hooks at_before_traverse and at_after_traverse).
        """
        traversing_object.msg("That way is locked.")

    def msg(self, text=None, from_obj=None, options=None, **kwargs):
        options = options or {}
        if options.get("shout", False):
            other_options = options.copy()
            from_dir = options.get("from_dir", "from nearby")
            new_from_dir = "from the %s" % str(self.reverse_exit)
            if not isinstance(text, str):
                text = text[0]
            text = text.replace(from_dir, new_from_dir)
            del other_options["shout"]
            other_options["from_dir"] = new_from_dir
            self.destination.msg_contents(
                text, exclude=None, from_obj=from_obj, options=other_options, **kwargs
            )

    @property
    def is_exit(self):
        return True

    @property
    def reverse_exit(self):
        entrances = [
            ob for ob in self.destination.exits if ob.destination == self.location
        ]
        if not entrances:
            return "nowhere"
        return entrances[0]

    # noinspection PyAttributeOutsideInit
    def relocate(self, new_room):
        """Moves this exit to a new location.

        Sets our location to new_room, and sets our reverse_exit to have a destination
        of our new location.

        Args:
            new_room: The room we'll be moved to

        """
        reverse = self.reverse_exit
        if reverse:
            reverse.destination = new_room
        self.location = new_room

    def lock_exit(self, caller=None):
        """
        Lock exit will lock an exit -and- the reverse exit
        """
        if (
            str(self.destination.id) not in self.locks.all()
            or str(self.location.id) not in self.locks.all()
        ):
            self.locks.add(
                "usekey: perm(builders) or roomkey(%s) or roomkey(%s)"
                % (self.destination.id, self.location.id)
            )
        self.lock(caller)
        try:
            self.reverse_exit.lock(caller)
            if (
                str(self.destination.id) not in self.reverse_exit.locks.all()
                or str(self.location.id) not in self.reverse_exit.locks.all()
            ):
                self.reverse_exit.locks.add(
                    "usekey: perm(builders) or roomkey(%s) or roomkey(%s)"
                    % (self.destination.id, self.location.id)
                )
        except AttributeError:
            pass

    def unlock_exit(self, caller=None):
        """
        As above
        """
        if (
            str(self.destination.id) not in self.locks.all()
            or str(self.location.id) not in self.locks.all()
        ):
            self.locks.add(
                "usekey: perm(builders) or roomkey(%s) or roomkey(%s)"
                % (self.destination.id, self.location.id)
            )
        self.unlock(caller)
        try:
            self.reverse_exit.unlock(caller)
            if (
                str(self.destination.id) not in self.reverse_exit.locks.all()
                or str(self.location.id) not in self.reverse_exit.locks.all()
            ):
                self.reverse_exit.locks.add(
                    "usekey: perm(builders) or roomkey(%s) or roomkey(%s)"
                    % (self.destination.id, self.location.id)
                )
        except AttributeError:
            pass

    @property
    def password(self):
        return self.db.password

    @property
    def password_question(self):
        if not self.db.password_question:
            return (
                "From the entrance of %s a voice asks for the password."
                % self.destination
            )
        return self.db.password_question

    @property
    def password_failmsg(self):
        if not self.db.password_failmsg:
            return "The voice informs you that is not the correct password."
        return self.db.password_failmsg

    @property
    def password_failures(self):
        if self.ndb.password_failures is None:
            self.ndb.password_failures = {}
        return self.ndb.password_failures

    def at_password_fail(self, caller):
        """
        Called when caller fails to give correct password.

            Args:
                caller (ObjectDB): The character trying to enter

        We inform the caller that they failed. We then add them to
        a dict of people with how many times they failed, to stop
        people from trying after X failed attempts.
        """
        caller.msg(self.password_failmsg)
        # Add them to dict of shame
        failures = self.password_failures.get(caller, 0)
        failures += 1
        self.password_failures[caller] = failures


class ShardhavenInstanceExit(DefaultExit, BaseObjectMixins):
    """
    Class to hold obstacles and other data for an exit in a Shardhaven instance.
    """

    @property
    def is_exit(self):
        return True

    @property
    def is_character(self):
        return False

    @property
    def reverse_exit(self):
        entrances = [
            ob for ob in self.destination.exits if ob.destination == self.location
        ]
        if not entrances:
            return "nowhere"
        return entrances[0]

    def msg(self, text=None, from_obj=None, options=None, **kwargs):
        options = options or {}
        if options.get("shout", False):
            other_options = options.copy()
            from_dir = options.get("from_dir", "from nearby")
            new_from_dir = "from the %s" % str(self.reverse_exit)
            if not isinstance(text, str):
                text = text[0]
            text = text.replace(from_dir, new_from_dir)
            del other_options["shout"]
            other_options["from_dir"] = new_from_dir
            self.destination.msg_contents(
                text, exclude=None, from_obj=from_obj, options=other_options, **kwargs
            )

    @property
    def haven_exit(self):
        if not self.db.haven_exit_id:
            return None

        try:
            haven_exit = ShardhavenLayoutExit.objects.get(id=self.db.haven_exit_id)
        except (
            ShardhavenLayoutExit.DoesNotExist,
            ShardhavenLayoutExit.MultipleObjectsReturned,
        ):
            return None

        return haven_exit

    def see_through_contents(self):

        other_room = self.destination
        haven_square = None
        if hasattr(other_room, "shardhaven_square"):
            haven_square = other_room.shardhaven_square

        characters = []
        character_string = None

        for testobj in other_room.contents:
            if testobj.has_account or (
                hasattr(testobj, "is_character") and testobj.is_character
            ):
                characters.append(testobj.name)

        if len(characters):
            character_string = commafy(characters)
        elif haven_square and haven_square.monster:
            if haven_square.monster.npc_type == Monster.MOOKS:
                character_string = haven_square.monster.plural_name
            else:
                character_string = haven_square.monster.name

        puzzle_string = None
        if haven_square and haven_square.puzzle and not haven_square.puzzle_solved:
            puzzle_string = haven_square.puzzle.display_name

        result = "You see nothing of note in the next room."
        if character_string:
            result = "In the next room, you see " + character_string + "."
            if puzzle_string:
                puzzle_part = a_or_an(puzzle_string)
                result += "  And {} {}.".format(puzzle_part, puzzle_string)
        elif puzzle_string:
            puzzle_part = a_or_an(puzzle_string)
            result = "In the next room, you see {} {}.".format(
                puzzle_part, puzzle_string
            )

        return result

    def return_appearance(
        self, pobject, detailed=False, format_desc=False, show_contents=True
    ):

        result = "|c" + self.key + "|n|/|/"

        see_through = False

        if self.haven_exit and self.haven_exit.obstacle:
            result += self.haven_exit.obstacle.description

            see_through = self.haven_exit.can_see_past(pobject)

            if self.haven_exit.obstacle.clues.count() > 0:
                result += "|/|/This obstacle can be passed by those who have the correct knowledge."
                if self.haven_exit.obstacle.can_pass_with_clue(pobject):
                    result += " |w(Which you have!)|n"

            if pobject.check_permstring("builders"):
                result += "|/" + self.haven_exit.obstacle.options_description(self)
                result += "|/|/(However, being staff, you can just pass through without a check.)"
            else:
                if self.passable(pobject):
                    result += "|/|/However, this obstacle has been addressed, and you may pass."
                else:
                    result += "|/" + self.haven_exit.obstacle.options_description(self)

        else:
            result += "The way seems clear ahead."
            see_through = True

        if see_through:
            other_room_contents = self.see_through_contents()
            if other_room_contents:
                result += "|/|/" + other_room_contents
        else:
            result += (
                "|/|/The "
                + self.haven_exit.obstacle_name
                + " blocks your view of the next room!"
            )

        return result + "|/"

    def passable(self, traversing_object):
        if not self.haven_exit or not self.haven_exit.obstacle:
            return True

        if self.haven_exit.override:
            return True

        if traversing_object.check_permstring("builders"):
            return True

        obstacle = self.haven_exit.obstacle
        if obstacle.pass_type == ShardhavenObstacle.INDIVIDUAL:
            return traversing_object in self.haven_exit.passed_by.all()
        if obstacle.pass_type == ShardhavenObstacle.EVERY_TIME:
            return False
        if obstacle.pass_type == ShardhavenObstacle.ANYONE:
            return self.haven_exit.passed_by.count() > 0

    def create_exit_cmdset(self, exidbobj):
        class ShardhavenExitCommand(command.Command):
            def func(self):
                if self.obj.can_traverse(self.caller):
                    self.obj.at_traverse(
                        self.caller, self.obj.destination, arguments=self.args
                    )

        exitkey = exidbobj.db_key.strip().lower()
        exitaliases = list(exidbobj.aliases.all())
        exitcmd = ShardhavenExitCommand(
            key=exitkey,
            aliases=exitaliases,
            locks=str(exidbobj.locks),
            auto_help=False,
            destination=exidbobj.db_destination,
            is_exit=True,
            obj=exidbobj,
        )
        exit_cmdset = cmdset.CmdSet(None)
        exit_cmdset.key = "_exitset"
        exit_cmdset.priority = 101  # equal to channel priority
        exit_cmdset.duplicates = True
        exit_cmdset.add(exitcmd)
        return exit_cmdset

    # noinspection PyMethodMayBeStatic
    def can_traverse(self, character):
        import time

        if character.location.ndb.combat_manager:
            cscript = character.location.ndb.combat_manager
            if cscript.ndb.combatants:
                if cscript.check_character_is_combatant(character):
                    character.msg(
                        "You're in combat, and cannot move rooms again unless you flee!"
                    )
                    return False

        if character.ndb.followers and len(character.ndb.followers) > 0:
            if not self.passable(character):
                character.msg(
                    "You can't have people follow you through an obstacle that you haven't tried yet!"
                )
                return False

            can_pass = True
            for follower in character.ndb.followers:
                if not self.passable(follower):
                    can_pass = False
            if not can_pass:
                character.msg(
                    "At least one of your followers hasn't passed this obstacle!"
                )
                return False

        if not self.passable(character):
            attempts = self.db.attempts or {}
            if character.id not in attempts:
                return True

            timestamp = attempts[character.id]
            delta = time.time() - timestamp
            if delta < 180:
                from math import trunc

                character.msg(
                    "You can't attempt to pass this obstacle again for {} seconds.".format(
                        trunc(180 - delta)
                    )
                )
                return False

        return True

    @property
    def direction_name(self):
        first = self.key.split(" ")[0]
        return first.lower()

    def at_traverse(
        self,
        traversing_object,
        target_location,
        key_message=True,
        special_entrance=None,
        quiet=False,
        allow_follow=True,
        arguments=None,
    ):

        if not self.passable(traversing_object):
            import time

            (
                result,
                override_obstacle,
                attempted,
                instant,
            ) = self.haven_exit.obstacle.handle_obstacle(
                traversing_object, self, self.haven_exit, args=arguments
            )
            if attempted:
                attempts = self.db.attempts or {}
                attempts[traversing_object.id] = time.time()
                self.db.attempts = attempts

            if result:
                self.haven_exit.passed_by.add(traversing_object)
                if override_obstacle:
                    self.haven_exit.override = True
                    self.haven_exit.save()
                if not instant:
                    return
            else:
                return

        self.location.msg_contents(
            "{} heads {}.".format(traversing_object.name, self.direction_name)
        )

        super(ShardhavenInstanceExit, self).at_traverse(
            traversing_object,
            target_location,
            key_message=key_message,
            special_entrance=special_entrance,
            quiet=quiet,
            allow_follow=allow_follow,
        )

        if traversing_object and traversing_object.ndb.followers and allow_follow:
            invalid_followers = []
            valid_followers = []
            leader = None
            for follower in traversing_object.ndb.followers:
                # only move followers who are conscious
                if not follower.conscious:
                    invalid_followers.append(follower)
                    continue
                # only move followers who were in same square
                if follower.location == self.location:
                    fname = follower.ndb.following
                    if follower.ndb.followers and fname in follower.ndb.followers:
                        # this would be an infinite loop
                        invalid_followers.append(follower)
                        continue
                    if fname == traversing_object:
                        follower.msg("You follow %s." % fname.name)
                    else:  # not marked as following us
                        invalid_followers.append(follower)
                        continue
                    # followers won't see the message about the door being locked
                    self.at_traverse(
                        follower, self.destination, key_message=False, quiet=True
                    )
                    valid_followers.append(follower.name)
                    leader = fname
                else:
                    invalid_followers.append(follower)
            # make all characters who could not follow stop following us
            for invalid in invalid_followers:
                if invalid.ndb.following == traversing_object:
                    invalid.stop_follow()
                else:
                    traversing_object.ndb.followers.remove(invalid)
            if valid_followers:
                verb = "arrive" if len(valid_followers) > 1 else "arrives"
                fol_msg = "%s %s, following %s." % (
                    ", ".join(valid_followers),
                    verb,
                    leader.name,
                )
                leave_msg = fol_msg.replace("arrive", "leave")
                self.destination.msg_contents(fol_msg)
                self.location.msg_contents(leave_msg)
