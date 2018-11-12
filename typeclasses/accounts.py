"""
Player

The Player represents the game "account" and each login has only one
Player object. A Player is what chats on default channels but has no
other in-game-world existance. Rather the Player puppets Objects (such
as Characters) in order to actually participate in the game world.


Guest

Guest players are simple low-level accounts that are created/deleted
on the fly and allows users to test the game without the committment
of a full registration. Guest accounts are deactivated by default; to
activate them, add the following line to your settings file:

    GUEST_ENABLED = True

You will also need to modify the connection screen to reflect the
possibility to connect with a guest account. The setting file accepts
several more options for customizing the Guest account system.

"""
from evennia import DefaultAccount
from typeclasses.mixins import MsgMixins, InformMixin
from web.character.models import PlayerSiteEntry


class Account(InformMixin, MsgMixins, DefaultAccount):

    """
    This class describes the actual OOC player (i.e. the user connecting
    to the MUD). It does NOT have visual appearance in the game world (that
    is handled by the character which is connected to this). Comm channels
    are attended/joined using this object.

    It can be useful e.g. for storing configuration options for your game, but
    should generally not hold any character-related info (that's best handled
    on the character level).

    Can be set using BASE_PLAYER_TYPECLASS.


    * available properties

     key (string) - name of player
     name (string)- wrapper for user.username
     aliases (list of strings) - aliases to the object. Will be saved to database as AliasDB entries
     but returned as strings.
     dbref (int, read-only) - unique #id-number. Also "id" can be used.
     date_created (string) - time stamp of object creation
     permissions (list of strings) - list of permission strings

     user (User, read-only) - django User authorization object
     obj (Object) - game object controlled by player. 'character' can also be used.
     sessions (list of Sessions) - sessions connected to this player
     is_superuser (bool, read-only) - if the connected user is a superuser

    * Handlers

     locks - lock-handler: use locks.add() to add new lock strings
     db - attribute-handler: store/retrieve database attributes on this self.db.myattr=val, val=self.db.myattr
     ndb - non-persistent attribute handler: same as db but does not create a database entry when storing data
     scripts - script-handler. Add new scripts to object with scripts.add()
     cmdset - cmdset-handler. Use cmdset.add() to add new cmdsets to object
     nicks - nick-handler. New nicks with nicks.add().

    * Helper methods

     msg(text=None, **kwargs)
     swap_character(new_character, delete_old_character=False)
     execute_cmd(raw_string, session=None)
     search(ostring, global_search=False, attribute_name=None, use_nicks=False, location=None, ignore_errors=False,
     player=False)
     is_typeclass(typeclass, exact=False)
     swap_typeclass(new_typeclass, clean_attributes=False, no_default=True)
     access(accessing_obj, access_type='read', default=False)
     check_permstring(permstring)

    * Hook methods (when re-implementation, remember methods need to have self as first arg)

     basetype_setup()
     at_player_creation()

     - note that the following hooks are also found on Objects and are
       usually handled on the character level:

     at_init()
     at_cmdset_get(**kwargs)
     at_first_login()
     at_post_login(session=None)
     at_disconnect()
     at_message_receive()
     at_message_send()
     at_server_reload()
     at_server_shutdown()

    """
    def __str__(self):
        return self.name

    def __unicode__(self):
        return self.name
    
    def at_account_creation(self):
        """
        This is called once, the very first time
        the player is created (i.e. first time they
        register with the game). It's a good place
        to store attributes all players should have,
        like configuration values etc.
        """
        # set an (empty) attribute holding the characters this player has
        lockstring = "attrread:perm(Wizards);attredit:perm(Wizards);attrcreate:perm(Wizards)"
        self.attributes.add("_playable_characters", [], lockstring=lockstring)
        self.db.mails = []
        self.db.readmails = set()

    # noinspection PyBroadException
    def at_post_login(self, session=None):
        """
        Called at the end of the login process, just before letting
        them loose. This is called before an eventual Character's
        at_post_login hook.
        :type self: AccountDB
        :type session: Session
        """
        self.db._last_puppet = self.char_ob or self.db._last_puppet
        super(Account, self).at_post_login(session)
        if self.tags.get("new_mail"):
            self.msg("{y*** You have new mail. ***{n")
        self.announce_informs()
        pending = self.db.pending_messages or []
        for msg in pending:
            self.msg(msg, options={'box': True})
        self.attributes.remove("pending_messages")
        if self.assigned_to.filter(status=1, priority__lte=5):
            self.msg("{yYou have unresolved tickets assigned to you. Use @job/mine to view them.{n")
        self.check_motd()
        self.check_petitions()
        # in this mode we should have only one character available. We
        # try to auto-connect to it by calling the @ic command
        # (this relies on player.db._last_puppet being set)
        self.execute_cmd("@bbsub/quiet story updates")

        address = self.sessions.all()[-1].address
        if isinstance(address, tuple):
            address = address[0]

        PlayerSiteEntry.add_site_for_player(self.char_ob, address)

        try:
            from commands.commands.bboards import get_unread_posts
            get_unread_posts(self)
        except Exception:
            pass
        try:
            if self.roster.frozen:
                self.roster.frozen = False
                self.roster.save()
            if self.roster.roster.name == "Inactive":
                from web.character.models import Roster
                try:
                    active = Roster.objects.get(name="Active")
                    self.roster.roster = active
                    self.roster.save()
                except Roster.DoesNotExist:
                    pass
            watched_by = self.char_ob.db.watched_by or []
            if self.sessions.count() == 1:
                if not self.db.hide_from_watch:
                    for watcher in watched_by:
                        watcher.msg("{wA player you are watching, {c%s{w, has connected.{n" % self)
                self.db.afk = ""
        except AttributeError:
            pass

    # noinspection PyBroadException
    def announce_informs(self):
        """Lets us know if we have unread informs"""
        msg = ""
        try:
            unread = self.informs.filter(read_by__isnull=True).count()
            if unread:
                msg += "{w*** You have %s unread informs. Use @informs to read them. ***{n\n" % unread
            for org in self.current_orgs:
                if not org.access(self, "informs"):
                    continue
                unread = org.informs.exclude(read_by=self).count()
                if unread:
                    msg += "{w*** You have %s unread informs for %s. ***{n\n" % (unread, org)
        except Exception:
            pass
        if msg:
            self.msg(msg)

    def is_guest(self):
        """
        Overload in guest object to return True
        """
        return False
    
    def at_first_login(self):
        """
        Only called once, the very first
        time the user logs in.
        """
        self.execute_cmd("addcom pub=public")
        pass

    def mail(self, message, subject=None, sender=None, receivers=None):
        """
        Sends a mail message to player.
        """
        from django.utils import timezone
        sentdate = timezone.now().strftime("%x %X")
        mail = (sender, subject, message, sentdate, receivers)
        if not self.db.mails:
            self.db.mails = []
        self.db.mails.append(mail)
        if sender:
            from_str = " from {c%s{y" % sender.capitalize()
        else:
            from_str = ""
        self.msg("{yYou have new mail%s. Use {w'mail %s' {yto read it.{n" % (from_str, len(self.db.mails)))
        self.tags.add("new_mail")

    def get_fancy_name(self):
        """Ensures that our name is capitalized"""
        return self.key.capitalize()

    # noinspection PyAttributeOutsideInit
    def set_name(self, value):
        self.key = value
    name = property(get_fancy_name, set_name)

    def send_or_queue_msg(self, message):
        """Sends a message to us if we're online or queues it for later"""
        if self.is_connected:
            self.msg(message, options={'box': True})
            return
        pending = self.db.pending_messages or []
        pending.append(message)
        self.db.pending_messages = pending

    def get_all_sessions(self):
        """Retrieves our connected sessions"""
        return self.sessions.all()

    @property
    def public_orgs(self):
        """
        Return public organizations we're in.
        """
        try:
            return self.Dominion.public_orgs
        except AttributeError:
            return []

    @property
    def current_orgs(self):
        """Returns our current organizations we're a member of"""
        try:
            return self.Dominion.current_orgs
        except AttributeError:
            return []

    @property
    def secret_orgs(self):
        """Returns any secret orgs we're a member of"""
        try:
            return self.Dominion.secret_orgs
        except AttributeError:
            return []

    @property
    def active_memberships(self):
        """Returns our active memberships"""
        try:
            return self.Dominion.memberships.filter(deguilded=False)
        except AttributeError:
            return []

    @property
    def assets(self):
        """Returns the holder for all our assets/prestige/etc"""
        return self.Dominion.assets

    def pay_resources(self, rtype, amt):
        """
        Attempt to pay resources. If we don't have enough,
        return False.
        """
        try:
            assets = self.assets
            current = getattr(assets, rtype)
            if current < amt:
                return False
            setattr(assets, rtype, current - amt)
            assets.save()
            return True
        except AttributeError:
            return False

    def gain_resources(self, rtype, amt):
        """
        Attempt to gain resources. If something goes wrong, we return 0. We call pay_resources with a negative
        amount, and if returns true, we return the amount to show what we gained.
        """
        if self.pay_resources(rtype, -amt):
            return amt
        return 0

    def pay_materials(self, material_type, amount):
        """
        Attempts to pay materials of the given type and amount
        Args:
            material_type (CraftingMaterialType): Material type we're paying with
            amount: amount we're spending

        Returns:
            False if we were able to spend, True otherwise
        """
        from django.core.exceptions import ObjectDoesNotExist
        assets = self.assets
        try:
            if amount < 0:
                material, _ = assets.materials.get_or_create(type=material_type)
            else:
                material = assets.materials.get(type=material_type)
            if material.amount < amount:
                return False
            material.amount -= amount
            material.save()
            return True
        except ObjectDoesNotExist:
            return False

    def gain_materials(self, material_type, amount):
        """Similar to gain_resources, call pay_materials with negative amount to gain it"""
        return self.pay_materials(material_type, -amount)

    def pay_action_points(self, amt, can_go_over_cap=False):
        """
        Attempt to pay action points. If we don't have enough,
        return False.
        """
        try:
            if self.roster.action_points != self.char_ob.roster.action_points:
                self.roster.refresh_from_db(fields=("action_points",))
                self.char_ob.roster.refresh_from_db(fields=("action_points",))
            if self.roster.action_points < amt:
                return False
            self.roster.action_points -= amt
            if self.roster.action_points > self.roster.max_action_points and not can_go_over_cap:
                self.roster.action_points = self.roster.max_action_points
            self.roster.save()
            if amt > 0:
                verb = "use"
            else:
                verb = "gain"
                amt = abs(amt)
            self.msg("{wYou %s %s action points and have %s remaining this week.{n" % (verb, amt,
                                                                                       self.roster.action_points))
            return True
        except AttributeError:
            return False

    @property
    def retainers(self):
        """Returns queryset of retainer agents"""
        try:
            return self.assets.agents.filter(unique=True)
        except AttributeError:
            return []

    @property
    def agents(self):
        """Returns queryset of any agents we own"""
        try:
            return self.assets.agents.all()
        except AttributeError:
            return []

    def get_absolute_url(self):
        """Returns our absolute URL for the webpage for our character"""
        try:
            return self.char_ob.get_absolute_url()
        except AttributeError:
            pass

    def at_post_disconnect(self):
        """Called after we disconnect"""
        if not self.sessions.all():
            watched_by = self.char_ob and self.char_ob.db.watched_by or []
            if watched_by and not self.db.hide_from_watch:
                for watcher in watched_by:
                    watcher.msg("{wA player you are watching, {c%s{w, has disconnected.{n" % self.key.capitalize())
            self.previous_log = self.current_log
            self.current_log = []
            self.db.lookingforrp = False
            temp_muted = self.db.temp_mute_list or []
            for channel in temp_muted:
                channel.unmute(self)
            self.attributes.remove('temp_mute_list')

    def log_message(self, from_obj, text):
        """Logs messages if we're not in private for this session"""
        from evennia.utils.utils import make_iter
        if not self.tags.get("private_mode"):
            text = text.strip()
            from_obj = make_iter(from_obj)[0]
            tup = (from_obj, text)
            if tup not in self.current_log and from_obj != self and from_obj != self.char_ob:
                self.current_log.append((from_obj, text))

    @property
    def current_log(self):
        """Temporary messages for this session"""
        if self.ndb.current_log is None:
            self.ndb.current_log = []
        return self.ndb.current_log

    @current_log.setter
    def current_log(self, val):
        self.ndb.current_log = val

    @property
    def previous_log(self):
        """Log of our past session"""
        if self.db.previous_log is None:
            self.db.previous_log = []
        return self.db.previous_log

    @previous_log.setter
    def previous_log(self, val):
        self.db.previous_log = val

    @property
    def flagged_log(self):
        """Messages flagged for GM notice"""
        if self.db.flagged_log is None:
            self.db.flagged_log = []
        return self.db.flagged_log

    @flagged_log.setter
    def flagged_log(self, val):
        self.db.flagged_log = val

    def report_player(self, player):
        """Reports a player for GM attention"""
        charob = player.char_ob
        log = []
        for line in (list(self.previous_log) + list(self.current_log)):
            if line[0] == charob or line[0] == player:
                log.append(line)
        self.flagged_log = log

    @property
    def allow_list(self):
        """List of players allowed to interact with us"""
        if self.db.allow_list is None:
            self.db.allow_list = []
        return self.db.allow_list
    
    @property
    def block_list(self):
        """List of players who should not be allowed to interact with us"""
        if self.db.block_list is None:
            self.db.block_list = []
        return self.db.block_list

    @property
    def clues_shared_modifier_seed(self):
        """Seed value for clue sharing costs"""
        from world.stats_and_skills import SOCIAL_SKILLS, SOCIAL_STATS
        seed = 0
        pc = self.char_ob
        for stat in SOCIAL_STATS:
            seed += pc.attributes.get(stat) or 0
        # do not be nervous. I love you. <3
        seed += sum([pc.skills.get(ob, 0) for ob in SOCIAL_SKILLS])
        seed += pc.skills.get("investigation", 0) * 3
        return seed

    @property
    def clue_cost(self):
        """Total cost for clues"""
        return int(100.0/float(self.clues_shared_modifier_seed + 1)) + 1

    @property
    def valid_actions(self):
        from world.dominion.models import CrisisAction
        from django.db.models import Q
        dompc = self.Dominion
        return CrisisAction.objects.filter(Q(dompc=dompc) | Q(assistants=dompc)).distinct()

    @property
    def participated_actions(self):
        """Actions we participated in"""
        from world.dominion.models import CrisisAction
        from django.db.models import Q
        dompc = self.Dominion
        return CrisisAction.objects.filter(Q(assistants=dompc) | Q(dompc=dompc)).distinct()

    @property
    def past_participated_actions(self):
        """Actions we participated in previously"""
        from world.dominion.models import CrisisAction
        return self.participated_actions.filter(status=CrisisAction.PUBLISHED).distinct()

    def show_online(self, caller, check_puppet=False):
        """
        Checks if we're online and caller has privileges to see that
        Args:
            caller: Player checking if we're online
            check_puppet: Whether to check if we're currently puppeting our character object

        Returns:
            True if they see us as online, False otherwise.
        """
        if not self.char_ob:
            return True
        return self.char_ob.show_online(caller, check_puppet)

    @property
    def player_ob(self):
        """Maybe this should return self? Will need to think about that. Inherited from mixins"""
        return None

    @property
    def char_ob(self):
        """Returns our character object if any"""
        try:
            return self.roster.character
        except AttributeError:
            pass

    @property
    def editable_theories(self):
        """Theories we have permission to edit"""
        ids = [ob.theory.id for ob in self.theory_permissions.filter(can_edit=True)]
        return self.known_theories.filter(id__in=ids)
        
    @property
    def past_actions(self):
        """Actions we created that have been finished in the past"""
        return self.Dominion.past_actions

    @property
    def recent_actions(self):
        """Actions we created that have submitted recently"""
        return self.Dominion.recent_actions

    @property
    def recent_assists(self):
        """Actions we assisted recently"""
        return self.Dominion.recent_assists

    def get_current_praises_and_condemns(self):
        """Current praises given by this player character"""
        from server.utils.arx_utils import get_week
        return self.Dominion.praises_given.filter(week=get_week())

    def check_motd(self):
        """Checks for a message of the day and sends it to us."""
        from evennia.server.models import ServerConfig
        motd = ServerConfig.objects.conf(key="MESSAGE_OF_THE_DAY")
        msg = ""
        if motd:
            msg += "|yServer Message of the Day:|n %s\n\n" % motd
        for membership in self.active_memberships:
            org = membership.organization
            if not membership.has_seen_motd and org.motd:
                msg += "|wMessage of the Day for %s:|n %s\n" % (org, org.motd)
                membership.has_seen_motd = True
                membership.save()
        self.msg(msg)

    def check_petitions(self):
        """Checks if we have any unread petition posts"""
        try:
            unread = self.Dominion.petitionparticipation_set.filter(unread_posts=True)
            if unread:
                unread_ids = [str(ob.petition.id) for ob in unread]
                self.msg("{wThe following petitions have unread messages:{n %s" % ", ".join(unread_ids))
        except AttributeError:
            pass
