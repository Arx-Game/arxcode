"""
Commands for flashbacks and other scene management stuff in the Character app.
Flashbacks are for the Arx equivalent of play-by-post: players can create a
flashback of a scene that happened in the past with a clear summary and end-goal
in mind, and then invite others to RP about it.
"""
from django.db.models import Q

from commands.base import ArxPlayerCommand
from commands.mixins import RewardRPToolUseMixin
from web.character.models import Flashback


class CmdFlashback(RewardRPToolUseMixin, ArxPlayerCommand):
    """
    Create, read, or participate in a flashback.
    Usage:
        flashback
        flashback <ID #>[=<number of last posts to display]
        flashback/catchup <ID #>
        flashback/create <title>[=<summary>]
        flashback/conclude <ID #>
        flashback/title <ID #>=<new title>
        flashback/summary <ID #>=<new summary>
        flashback/invite[/retro] <ID #>[=<player>]
        flashback/uninvite <ID #>[=<player>]
        flashback/allow <ID #>=<player>[,<number of last posts or 'all'>]
        flashback/post <ID #>=<message>
        flashback/check[/flub] <ID>=<stat>[+<skill>][ at <difficulty #>]

    Flashbacks are roleplay scenes that occur in the past, visible to staff
    and invited players. Players are informed of new posts, but if you no
    longer wish to be informed or participate, you may uninvite yourself. The
    /catchup switch shows unread posts. Posts can also be made from your
    character webpage via the flashbacks link. Players will see posts made
    after they were invited, but inviting with /retro reveals back-posts.
    Partial visibility is achieved with /allow, once they have been invited
    normally. Use /invite without a name to see who has access. Use /check
    similar to @oldcheck - the result will prefix your next post.
    """

    key = "flashback"
    aliases = ["flashbacks"]
    locks = "cmd:all()"
    help_category = "Story"
    invite_switches = ("invite", "uninvite", "allow")
    change_switches = ("title", "summary", "conclude")
    requires_owner = (
        "invite",
        "allow",
    ) + change_switches
    requires_unconcluded = ("post", "roll", "check", "conclude")

    @property
    def roster_entry(self):
        return self.caller.roster

    def func(self):
        if not self.switches and not self.args:
            self.list_flashbacks()
        elif "create" in self.switches:
            self.create_flashback()
        else:
            flashback = self.get_flashback()
            if not flashback:
                return
            if not self.switches:
                self.view_flashback(flashback)
            elif "catchup" in self.switches:
                self.read_new_posts(flashback)
            elif "post" in self.switches:
                self.post_message(flashback)
            elif self.check_switches(("check", "roll")):
                self.make_flashback_roll(flashback)
            else:
                if not self.check_can_use_switch(flashback):
                    return
                if self.check_switches(self.invite_switches):
                    self.manage_invites(flashback)
                elif self.check_switches(self.change_switches):
                    self.update_flashback(flashback)
                else:
                    self.msg("Invalid switch.")
                    return
        self.mark_command_used()

    def list_flashbacks(self):
        from evennia.utils.evtable import EvTable

        roster = self.roster_entry
        flashbacks = roster.flashbacks.all()
        if not flashbacks:
            self.msg("No flashbacks available to list. Why not create one?")
            return
        table = EvTable(
            "ID", "Flashback", "Owner", "New Posts", width=78, border="cells"
        )
        for flashback in flashbacks:
            new_posts = str(flashback.get_new_posts(roster).count())
            color = "|g" if flashback.posts_allowed_by(self.caller) else ""
            fb_id = "%s%s|n" % (color, flashback.id)
            table.add_row(fb_id, flashback.title, flashback.owner, new_posts)
        self.msg(str(table))

    def create_flashback(self):
        title = self.lhs
        summary = self.rhs if self.rhs else ""
        flashback, created = Flashback.objects.get_or_create(title=title)
        if not created:
            self.msg(
                "There is already a flashback with that title. Please choose another."
            )
            return
        flashback.summary = summary
        flashback.save()
        flashback.invite_roster(self.roster_entry, owner=True)
        self.msg("You have created a new flashback with the ID of #%s." % flashback.id)

    def get_flashback(self):
        try:
            if self.check_switches(self.requires_unconcluded):
                fb = self.roster_entry.postable_flashbacks
            else:
                fb = self.roster_entry.flashbacks.all()
            return fb.get(id=int(self.lhs))
        except (Flashback.DoesNotExist, ValueError):
            self.msg("No ongoing flashback by that ID number.")
            self.list_flashbacks()

    def view_flashback(self, flashback):
        """Displays details and posts with possible post-limit."""
        try:
            post_limit = int(self.rhs)
        except (TypeError, ValueError):
            post_limit = None
        self.msg(flashback.display(post_limit=post_limit, reader=self.caller))

    def read_new_posts(self, flashback):
        """Displays unread posts and then marks them read."""
        roster = self.roster_entry
        perms = (
            roster.flashback_post_permissions.filter(post__flashback=flashback)
            .exclude(is_read=True)
            .distinct()
        )
        perms_list = list(perms)
        new_posts = flashback.posts.filter(flashback_post_permissions__in=perms_list)
        if not new_posts:
            self.msg("No new posts for #%s." % flashback.id)
            return
        msg = "|w%s|n (#%s) - New Posts!" % (flashback, flashback.id)
        div = flashback.STRING_DIV
        for post in new_posts:
            msg += "%s\n%s" % (div, post.display())
            perm = [ob for ob in perms_list if ob.post_id == post.id]
            if perm:
                perm[0].is_read = True  # cache-safe is cache money
        perms.update(is_read=True)  # update skips cached objects
        self.msg(msg)

    def manage_invites(self, flashback):
        """Redirects to invite, uninvite, or allowing visible back-posts."""
        if self.rhs:
            targ = self.caller.search(self.rhslist[0])
            if not targ:
                return
        elif "invite" in self.switches:
            msg = flashback.display_involvement()
            self.msg(msg)
            return
        else:
            targ = self.caller
        inv = flashback.get_involvement(targ.roster)
        if "invite" in self.switches:
            self.invite_target(flashback, targ, inv)
        elif "allow" in self.switches:
            self.mark_readable_posts(flashback, targ, inv)
        else:
            self.uninvite_target(flashback, targ, inv)

    def invite_target(self, flashback, target, inv=None):
        """Calls method to create an involvement or change it from 'retired' status."""
        if inv and inv.status >= inv.CONTRIBUTOR:
            self.msg("They are already invited to this flashback.")
            return
        retro = "retro" in self.switches
        retro_msg = " with all previous posts visible" if retro else ""
        flashback.invite_roster(target.roster, retro=retro)
        self.msg(
            "You have invited %s to participate in flashback #%s%s."
            % (target, flashback.id, retro_msg)
        )

    def uninvite_target(self, flashback, target, inv=None):
        """Calls method to change contributor to 'retired', or delete non-contributor involvement."""
        if not inv or inv.status == inv.RETIRED:
            return self.msg(
                "They are %s in this flashback already."
                % ("marked as retired" if inv else "not involved")
            )
        owners = list(flashback.owners)
        if target.roster in owners:
            return self.msg("Cannot remove an owner of the flashback.")
        elif target != self.caller and self.roster_entry not in owners:
            return self.msg("Only the flashback's owner can uninvite other players.")
        flashback.uninvite_involvement(inv)
        self.msg("You have uninvited %s from flashback #%s." % (target, flashback.id))
        if target != self.caller:
            target.inform(
                "You have been retired from flashback #%s." % flashback.id,
                category="Flashbacks",
            )

    def mark_readable_posts(self, flashback, target, inv=None):
        """Allows a number of back-posts to be readable by target."""
        if not inv:
            self.msg("%s needs to be invited to that flashback first." % target)
            return
        amount = None
        if len(self.rhslist) < 2:
            self.rhslist.append("all")
        if self.rhslist[1] != "all":
            try:
                amount = int(self.rhslist[1].strip("-"))
            except (TypeError, ValueError):
                self.msg(
                    "Specify a number to allow a number of visible back-posts, or 'all'."
                )
                return
        flashback.allow_back_read(target.roster, amount=amount)
        self.msg(
            "%s can see %s previous post(s) in flashback #%s."
            % (target, self.rhslist[1], flashback.id)
        )

    def post_message(self, flashback):
        """Add a new post. Requires confirmation if this will 'consume' a waiting dice roll."""
        if not self.rhs:
            return self.msg("You must include a message.")
        roster = self.roster_entry
        inv = flashback.get_involvement(roster)
        if inv.roll:
            prompt = (
                "|wThis roll will accompany the new post:|n %s\n"
                "|yPlease repeat command to confirm and continue.|n" % inv.roll
            )
            if not self.confirm_command(
                "flashback_%s_post" % flashback.id, self.rhs, prompt
            ):
                return
        flashback.add_post(self.rhs, roster)
        self.msg("You have posted to |w%s|n: %s" % (flashback, self.rhs))

    def check_can_use_switch(self, flashback):
        if not self.check_switches(self.requires_owner):
            return True
        elif not self.roster_entry in flashback.owners:
            self.msg("Only the flashback's owner may use that switch.")
            return False
        return True

    def update_flashback(self, flashback):
        """Sets a field for the flashback, or concludes it."""
        if "conclude" in self.switches:
            self.msg("Flashback #%s is concluding." % flashback.id)
            flashback.end_scene(self.roster_entry)
            return
        elif "title" in self.switches:
            field = "title"
        else:
            field = "summary"
        setattr(flashback, field, self.rhs)
        flashback.save()
        self.msg("%s set to: %s" % (field.capitalize(), self.rhs))

    def make_flashback_roll(self, flashback):
        """Prints reminder of participant's existing dice result, or saves new one."""
        inv = flashback.get_involvement(self.roster_entry)
        reminder = "Your next post in flashback #%s will use this roll" % flashback.id
        if inv.roll:
            return self.msg("%s: %s" % (reminder, inv.roll))
        elif not self.rhs:
            return self.msg("|wMissing:|n <stat>[+<skill>][ at <difficulty number>]")
        elif inv.make_dice_roll(self.rhs, flub="flub" in self.switches):
            self.msg("%s." % reminder)
