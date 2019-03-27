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
        flashback/title <ID #>=<new title>
        flashback/summary <ID #>=<new summary>
        flashback/invite <ID #>=<player>
        flashback/uninvite <ID #>=<player>
        flashback/post <ID #>=<message>

    Flashbacks are roleplay scenes that happened in the past. They are
    private to invited players and staff. Involved players are informed of
    new posts. If you no longer wish to be informed or post, you can uninvite
    yourself. Catchup will summarize unread posts. Posts can also be made
    from the Flashback link on your character webpage. Players are able to
    see posts made while they are involved, but adding the /retro switch to
    invite reveals the entire Flashback. Partial visibility is achieved with
    /allow, after a regular invitation.
    """
    key = "flashback"
    aliases = ["flashbacks"]
    locks = "cmd:all()"
    help_category = "Story"
    invite_switches = ("invite", "uninvite")
    change_switches = ("title", "summary")
    requires_owner = ("invite",) + change_switches
    requires_unconcluded = ("post", "roll", "check")

    # TODO:
    # flashback/invite[/retro] <ID #>=<player>
    # flashback/allow <ID #>=<player>,<number of last posts or 'all'>
    # flashback/check[/flub] <ID#>=<stat>[+<skill>][ at <difficulty number>]
    # flashback/conclude <ID #>

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
            if not flashback or not self.check_conclusion(flashback):
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
        for flashback in self.roster_entry.valid_flashbacks:
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
            return self.roster_entry.valid_flashbacks.get(id=int(self.lhs))
        except (Flashback.DoesNotExist, ValueError):
            self.msg("No flashback by that ID number.")
            self.list_flashbacks()

    def get_involvement(self, flashback):
        return flashback.flashback_involvements.get(participant=self.roster_entry)

    def view_flashback(self, flashback):
        try:
            post_limit = int(self.rhs)
        except (TypeError, ValueError):
            post_limit = None
        self.msg(flashback.display(post_limit=post_limit))

    def read_new_posts(self, flashback):
        new_posts = flashback.get_new_posts(self.roster_entry)
        if not new_posts:
            msg = "No new posts for #%s." % flashback.id
        else:
            msg = "New posts for #%s %s\n" % (flashback.id, flashback)
            for post in new_posts:
                msg += "%s\n" % post.display()
                post.read_by.add(self.roster_entry)
        self.msg(msg)

    def manage_invites(self, flashback):
        targ = self.caller.search(self.rhs)
        if not targ:
            return
        if "invite" in self.switches:
            self.invite_target(flashback, targ)
        else:  # uninvite
            self.uninvite_target(flashback, targ)

    def invite_target(self, flashback, target):
        if flashback.allowed.filter(id=target.roster.id).exists():
            self.msg("They are already invited to this flashback.")
            return
        self.msg("You have invited %s to participate in this flashback." % target)
        flashback.allowed.add(target.roster)
        target.inform("You have been invited by %s to participate in flashback #%s: '%s'." %
                      (self.caller, flashback.id, flashback), category="Flashbacks")

    def uninvite_target(self, flashback, target):
        if not flashback.allowed.filter(id=target.roster.id).exists():
            self.msg("They are already not invited to this flashback.")
            return
        self.msg("You have uninvited %s from this flashback." % target)
        flashback.allowed.remove(target.roster)
        target.inform("You have been removed from flashback #%s." % flashback.id,
                      category="Flashbacks")

    def post_message(self, flashback):
        inv = self.get_involvement(flashback)
        if not self.rhs:
            self.msg("You must include a message.")
            return
        elif inv.roll:
            # TODO: confirmation details!
            if not self.confirm_command():
                return
            else:
                # TODO: delete roll from flashback
                pass
        flashback.add_post(self.rhs, self.roster_entry)
        self.msg("You have posted a new message to %s: %s" % (flashback, self.rhs))

    def check_can_use_switch(self, flashback):
        if not self.check_switches(self.requires_owner):
            return True
        elif self.roster_entry != flashback.owner:
            self.msg("Only the flashback's owner may use that switch.")
            return False
        return True

    def check_conclusion(self, flashback):
        if self.check_switches(self.requires_unconcluded) and flashback.concluded:
            self.msg("That flashback has reached its conclusion.")
            return False
        return True

    def update_flashback(self, flashback):
        if "title" in self.switches:
            field = "title"
        else:
            field = "summary"
        setattr(flashback, field, self.rhs)
        flashback.save()
        self.msg("%s set to: %s." % (field, self.rhs))

    def make_flashback_roll(self, flashback):
        """Prints reminder of participant's existing dice result, or saves new one."""
        inv = self.get_involvement(flashback)
        reminder = "Your next post in flashback #%s will use this roll" % flashback.id
        if inv.roll:
            return self.msg("%s: %s" % (reminder, inv.roll))
        elif not self.rhs:
            return self.msg("|wMissing:|n <stat>[+<skill>][ at <difficulty number>]")
        # no flashback roll for caller is waiting on a post, so make new one:
        if inv.make_dice_roll(self.rhs, flub="flub" in self.switches):
            self.msg("%s." % reminder)
