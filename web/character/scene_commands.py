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
        flashback/invite[/retro] [<ID #>=<player>]
        flashback/uninvite <ID #>=<player>
        flashback/allow <ID #>=<player>,<number of last posts or 'all'>
        flashback/post <ID #>=<message>
        flashback/check[/flub] <ID>=<stat>[+<skill>][ at <difficulty #>]

    Flashbacks are roleplay scenes that happened in the past. They are
    private to invited players and staff. Involved players are informed of
    new posts. If you no longer wish to be informed or post, you may uninvite
    yourself. Catchup shows unread posts. Posts can also be made from your
    character webpage's Flashbacks link. Players can see posts made after
    they were invited, but adding /retro to an invitation reveals all
    back-posts. Partial visibility is achieved with /allow, after they have
    been invited normally. Use /invite sans args to see who has access. Using
    /check is like @check and the result will prefix your next post.
    """
    key = "flashback"
    aliases = ["flashbacks"]
    locks = "cmd:all()"
    help_category = "Story"
    invite_switches = ("invite", "uninvite", "allow")
    change_switches = ("title", "summary")
    requires_owner = ("invite", "allow",) + change_switches
    requires_unconcluded = ("post", "roll", "check")

    # TODO:
    # flashback/conclude <ID #>
    # Consider weird user states in migration. Posters who are uninvited, etc.
    # Use role_played in Involvement?

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
        table = EvTable("ID", "Title", "Owner", "New Posts", width=78, border="cells")
        for flashback in self.roster_entry.flashbacks.all():
            table.add_row(flashback.id, flashback.title, flashback.owner,
                          str(len(flashback.get_new_posts(self.roster_entry))))
        self.msg(str(table))

    def create_flashback(self):
        title = self.lhs
        summary = self.rhs or ""
        if Flashback.objects.filter(title__iexact=title).exists():
            self.msg("There is already a flashback with that title. Please choose another.")
            return
        flashback = self.roster_entry.created_flashbacks.create(title=title, summary=summary)
        self.msg("You have created a new flashback with the ID of #%s." % flashback.id)

    def get_flashback(self):
        try:
            if self.check_switches(self.requires_unconcluded):
                fb = self.roster_entry.postable_flashbacks
            else:
                fb = self.roster_entry.flashbacks.all()
            return fb.get(id=int(self.lhs))
        except (Flashback.DoesNotExist, ValueError):
            self.msg("No open flashback by that ID number.")
            self.list_flashbacks()

    def view_flashback(self, flashback):
        try:
            post_limit = int(self.rhs)
        except (TypeError, ValueError):
            post_limit = None
        self.msg(flashback.display(post_limit=post_limit, reader=self.roster_entry))

    def read_new_posts(self, flashback):
        new_posts = flashback.get_new_posts(self.roster_entry)
        if not new_posts:
            msg = "No new posts for #%s." % flashback.id
        else:
            msg = "|w%s|n - (#%s) New Posts!\n" % (flashback, flashback.id)
            for post in new_posts:
                msg += "%s\n" % post.display()
                post.read_by.add(self.roster_entry)
        self.msg(msg)

    def manage_invites(self, flashback):
        """Redirects to invite, uninvite, or allowing visible back-posts."""
        if not self.rhs and "invite" in self.switches:
            return flashback.display_involvement()
        targ = self.caller.search(self.rhslist[0])
        if not targ:
            return
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
        retro_msg = ", with all previous posts visible" if retro else ""
        flashback.invite_roster(target.roster, retro=retro)
        self.msg("You have invited %s to participate in this flashback%s." % (target, retro_msg))
        target.inform("You have been invited by %s to participate in flashback #%s: '%s'." %
                      (self.caller, flashback.id, flashback), category="Flashbacks")

    def uninvite_target(self, flashback, target, inv=None):
        """Calls method to change contributor to 'retired', or delete non-contributor involvement."""
        if not inv or inv.status == inv.RETIRED:
            self.msg("They are %s in this flashback already." % ("marked as retired" if inv else "not involved"))
            return
        if target.roster in flashback.owners:
            self.msg("Cannot remove an owner of the flashback.")
            return
        flashback.uninvite_roster(target.roster)
        self.msg("You have uninvited %s from this flashback." % target)
        if target != self.caller:
            target.inform("You have been retired from flashback #%s." % flashback.id,
                          category="Flashbacks")

    def mark_readable_posts(self, flashback, target, inv=None):
        """Allows a number of back-posts to be readable by target."""
        if not inv:
            self.msg("%s needs to be invited to that flashback first." % target)
            return
        amount = None
        if len(self.rhslist) > 1 and self.rhslist[1] != "all":
            try:
                amount = int(self.rhslist[1].strip('-'))
            except (TypeError, ValueError):
                self.msg("To allow visible back-posts, specify a <number> or <all>.")
                return
            amount = int(self.rhslist[1])
        flashback.allow_back_read(target.roster, amount=amount)
        self.msg("%s can see %s previous posts in flashback #%s." % (target, self.rhslist[1], flashback.id))

    def post_message(self, flashback):
        if not self.rhs:
            return self.msg("You must include a message.")
        inv = flashback.get_involvement(self.roster_entry)
        if inv.roll:
            prompt = ("|wThis roll will accompany the new post:|n %s\n"
                      "|yPlease repeat command to confirm and continue.|n" % inv.roll)
            if not self.confirm_command("flashback_%s_post" % flashback.id, self.rhs, prompt):
                return
        flashback.add_post(self.rhs, self.roster_entry)
        self.msg("You have posted to |w%s|n: %s" % (flashback, self.rhs))

    def check_can_use_switch(self, flashback):
        if not self.check_switches(self.requires_owner):
            return True
        elif self.roster_entry != flashback.owner:
            self.msg("Only the flashback's owner may use that switch.")
            return False
        return True

    def update_flashback(self, flashback):
        if "title" in self.switches:
            field = "title"
        else:
            field = "summary"
        setattr(flashback, field, self.rhs)
        flashback.save()
        self.msg("%s set to: %s." % (field.capitalize(), self.rhs))

    def make_flashback_roll(self, flashback):
        """Prints reminder of participant's existing dice result, or saves new one."""
        inv = flashback.get_involvement(self.roster_entry)
        reminder = "Your next post in flashback #%s will use this roll" % flashback.id
        if inv.roll:
            return self.msg("%s: %s" % (reminder, inv.roll))
        elif not self.rhs:
            return self.msg("|wMissing:|n <stat>[+<skill>][ at <difficulty number>]")
        else:
            if inv.make_dice_roll(self.rhs, flub="flub" in self.switches):
                self.msg("%s." % reminder)
