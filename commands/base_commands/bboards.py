"""
Comsystem command module.

Comm commands are OOC commands and intended to be made available to
the Player at all times (they go into the PlayerCmdSet). So we
make sure to homogenize self.caller to always be the player object
for easy handling.

"""
from evennia.utils import create
from server.utils import prettytable
from server.utils.arx_utils import inform_staff
from commands.base import ArxCommand, ArxPlayerCommand
from typeclasses.bulletin_board.bboard import BBoard

# limit symbol import for API
__all__ = ("CmdBBReadOrPost", "CmdBBSub", "CmdBBUnsub",
           "CmdBBCreate", "get_boards")
BOARD_TYPECLASS = "typeclasses.bulletin_board.bboard.BBoard"


def get_boards(caller):
    """
    returns list of bulletin boards
    """
    bb_list = list(BBoard.objects.all())
    bb_list = [ob for ob in bb_list if ob.access(caller, 'read')]
    return bb_list
    

def list_bboards(caller, old=False):
    """
    Helper function for listing all boards a player is subscribed
    to in some pretty format.
    """
    bb_list = get_boards(caller)
    if not bb_list:
        return
    my_subs = [bb for bb in bb_list if bb.has_subscriber(caller)]
    # just display the subscribed bboards with no extra info
    if old:
        caller.msg("{cDisplaying only archived posts.{n")
    bbtable = prettytable.PrettyTable(["{wbb #",
                                       "{wName",
                                       "{wPosts{n",
                                      "{wSubscribed{n"])
    for bboard in bb_list:
        bb_number = bb_list.index(bboard)
        bb_name = bboard.key
        unread_num = bboard.num_of_unread_posts(caller, old)
        subbed = bboard in my_subs
        posts = bboard.archived_posts if old else bboard.posts
        if unread_num:
            unread_str = " {w(%s new){n" % unread_num
        else:
            unread_str = ""
        bbtable.add_row([bb_number, bb_name,
                         "%s%s" % (len(posts), unread_str), subbed])
    caller.msg("\n{w" + "="*60 + "{n\n%s" % bbtable)


def access_bboard(caller, args, request="read"):
    """
    Helper function for searching for a single bboard with
    some error handling.
    """
    bboards = get_boards(caller)
    if not bboards:
        return
    if args.isdigit():
        bb_num = int(args)
        if (bb_num < 0) or (bb_num >= len(bboards)):
            caller.msg("Invalid board number.")
            return
        board = bboards[bb_num]
    else:
        board_ids = [ob.id for ob in bboards]
        try:
            board = BBoard.objects.get(db_key__icontains=args, id__in=board_ids)
        except BBoard.DoesNotExist:
            caller.msg("Could not find a unique board by name %s." % args)
            return
        except BBoard.MultipleObjectsReturned:
            boards = BBoard.objects.filter(db_key__icontains=args, id__in=board_ids)
            caller.msg("Too many boards returned, please pick one: %s" % ", ".join(str(ob) for ob in boards))
            return
    if not board.access(caller, request):
        caller.msg("You do not have the required privileges to do that.")
        return
    # passed all checks, so return board
    return board


def list_messages(caller, board, board_num, old=False):
    """
    Helper function for printing all the posts on board
    to caller.
    """
    if not board:
        caller.msg("No bulletin board found.")
        return
    caller.msg("{w" + "="*60 + "\n{n")
    title = "{w**** %s ****{n" % board.key.capitalize()
    title = "{:^80}".format(title)
    caller.msg(title)
    posts = board.get_all_posts(old=old)
    msgnum = 0
    msgtable = prettytable.PrettyTable(["{wbb/msg",
                                        "{wSubject",
                                        "{wPostDate",
                                        "{wPosted By"])
    from world.msgs.models import Post
    read_posts = Post.objects.all_read_by(caller)
    for post in posts:
        unread = post not in read_posts
        msgnum += 1
        if str(board_num).isdigit():
            bbmsgnum = str(board_num) + "/" + str(msgnum)
        else:
            bbmsgnum = board.name.capitalize() + "/" + str(msgnum)
        # if unread message, make the message white-bold
        if unread:
            bbmsgnum = "{w" + "{0}".format(bbmsgnum)
        subject = post.db_header[:35]
        date = post.db_date_created.strftime("%x")
        poster = board.get_poster(post)[:10]
        # turn off white-bold color if unread message
        if unread:
            poster = "{0}".format(poster) + "{n"
        msgtable.add_row([bbmsgnum, subject, date, poster])
    caller.msg(msgtable) 
    pass


def get_unread_posts(caller):
    bb_list = get_boards(caller)
    if not bb_list:
        return
    my_subs = [bb for bb in bb_list if bb.has_subscriber(caller)]
    msg = "{wNew posts on bulletin boards:{n "
    unread = []
    for bb in my_subs:
        post = bb.get_latest_post()
        if not post:
            continue
        if not post.check_read(caller):
            unread.append(bb)
    if unread:
        msg += ", ".join(bb.key.capitalize() for bb in unread)
        caller.msg(msg)


class CmdBBNew(ArxPlayerCommand):
    """
    +bbnew - read an unread post from boards you are subscribed to

    Usage:
        +bbnew  - retrieve a single post
        +bbnew <number of posts>[=<board num>] - retrive posts
        +bbnew all[=<board num>] - retrieve all posts
        +bbnew/markread <number of posts or all>[=<board num>]

    +bbnew will retrieve unread messages. If an argument is passed,
    it will retrieve up to the number of messages specified.
        
    """
    key = "+bbnew"
    aliases = ["@bbnew", "bbnew"]
    help_category = "Comms"
    locks = "cmd:not pperm(bboard_banned)"

    def func(self):
        """Implement the command"""
        caller = self.caller
        args = self.lhs
        bb_list = get_boards(caller)
        my_subs = []
        if not bb_list:
            return
        if not self.rhs:
            my_subs = [bb for bb in bb_list if bb.has_subscriber(caller)]
        else:
            sub = access_bboard(caller, self.rhs)
            if sub:
                my_subs.append(sub)
        if not my_subs:
            caller.msg("Currently not subscribed to any boards.")
            return
        if not args:
            num_posts = 1
        elif "all" in args:
            num_posts = 500
        else:
            try:
                num_posts = int(args)
            except ValueError:
                caller.msg("Argument must either be 'all' or a number.")
                return
        found_posts = 0
        caller.msg("{wUnread posts:")
        caller.msg("{w" + "-"*60 + "{n")
        noread = "markread" in self.switches
        for bb in my_subs:
            posts = bb.get_unread_posts(caller)
            if not posts:
                continue
            caller.msg("{wBoard {c%s{n:" % bb.key)
            posts_on_board = 0
            for post in posts:
                if noread:
                    bb.mark_read(caller, post)
                else:
                    bb.read_post(caller, post)
                found_posts += 1
                posts_on_board += 1
                if found_posts >= num_posts:
                    return
            if noread:
                self.msg("You have marked %s posts as read." % posts_on_board)
        if not found_posts:
            self.msg("No new posts found on boards: %s." % ", ".join(str(sub) for sub in my_subs))


class CmdBBReadOrPost(ArxPlayerCommand):
    """
    @bb - read or post to boards you are subscribed to

    Usage:
       @bb - List all boards you are subscribed to
       @bb <board # or name> - List posts on board
       @bb <board # or name>/<post #> - read post on board
       @bb <board # or name>/u - read all unread posts for board
       @bb/read <board # or name>/<post #> - read post on board
       @bb/del  <board # or name>/<post #> - delete post on board
       @bb/archive <board # or name>/<post #>
       @bb/sticky <board # or name>/<post #>
       @bb/edit <board # or name>/<post #>=<message> - edit
       @bb/post <board # or name>/<title>=<message> - make a post
       @bb/catchup - alias for +bbnew/markread command
       @bb/new - alias for the +bbnew command


    Bulletin Boards are intended to be OOC discussion groups divided
    by topic for news announcements, requests for participants in
    stories, and more.

    To subscribe to a board, use '@bbsub'. To read the newest post on
    a board, use @bbnew.

    To mark all posts as read, use '+bbnew/markread all'. The /old
    switch may be chained to view archived posts.

    @bborgstance is used to set an organization's stance on a proclamation.
    """

    key = "@bb"
    aliases = ["+bb", "+bbread", "bb", "bbread", "@bbread"]
    help_category = "Comms"
    locks = "cmd:not pperm(bboard_banned)"

    def func(self):
        """Implement the command"""
        caller = self.caller
        args = self.args
        switches = self.switches
        old = "old" in switches
        if not args and not ('new' in switches or 'catchup' in switches):
            return list_bboards(caller, old)

        # first, "@bb <board #>" use case
        def board_check(reader, arguments):
            board_to_check = access_bboard(reader, arguments)
            if not board_to_check:
                return
            if not board_to_check.has_subscriber(reader):
                reader.msg("You are not yet a subscriber to {0}".format(board_to_check.key))
                reader.msg("Use {w@bbsub{n to subscribe to it.")
                return
            list_messages(reader, board_to_check, arguments, old)
            
        if not switches or old and len(switches) == 1:
            arglist = args.split("/")
            if len(arglist) < 2:
                board_check(caller, args)
                return
            else:
                if arglist[1] == 'u':
                    switches.append('new')
                    # build arguments for bbnew command
                    args = " all=%s" % arglist[0]
                else:
                    switches.append('read')              
        if 'new' in switches or 'catchup' in switches:
            if 'catchup' in switches:
                caller.execute_cmd("+bbnew/markread" + args)
                return
            caller.execute_cmd("+bbnew"+args)
            return               
        # both post/read share board #
        arglist = args.split("/")
        
        board = access_bboard(caller, arglist[0])
        if not board:
            return
        
        if 'read' in switches:          
            if len(arglist) < 2:
                board_check(caller, args)
                return
            postrange = [arg.strip() for arg in arglist[1].split("-")]
            if len(postrange) == 1:
                try:
                    post_num = int(arglist[1])
                except ValueError:
                    caller.msg("Invalid post number.")
                    return
                post = board.get_post(caller, post_num, old)
                if not post:
                    return
                board.read_post(caller, post, old)
                return
            num_read = 0
            try:
                for post_num in range(int(postrange[0]), int(postrange[1]) + 1):
                    try:
                        post = board.get_post(caller, int(post_num))
                        board.read_post(caller, post, old)
                        num_read += 1
                    except (TypeError, ValueError, AttributeError):
                        continue
            except (TypeError, ValueError, IndexError):
                caller.msg("Posts in the range must be numbers.")
                return
            if not num_read:
                caller.msg("No posts in range.")
            return
        if 'del' in switches or 'archive' in switches or 'sticky' in switches or 'delete' in switches:
            if "del" in switches or "delete" in switches:
                if board.tags.get("only_staff_delete") and not caller.check_permstring("builders"):
                    self.msg("Only builders may delete from that board.")
                    return
                switchname = "del"
                verb = "delete"
                method = "delete_post"
            elif "sticky" in switches:
                switchname = "sticky"
                verb = "sticky"
                method = "sticky_post"
            else:
                switchname = "archive"
                verb = "archive"
                method = "archive_post"
            if len(arglist) < 2:
                caller.msg("Usage: @bb/%s <board #>/<post #>" % switchname)
                return         
            try:
                post_num = int(arglist[1])
            except ValueError:
                caller.msg("Invalid post number.")
                return
            post = board.get_post(caller, post_num, old)
            if not post:
                return
            if caller not in post.db_sender_accounts.all() and not board.access(caller, "edit"):
                caller.msg("You cannot %s someone else's post, only your own." % verb)
                return
            if getattr(board, method)(post):
                caller.msg("Post %sd" % verb)
                inform_staff("%s has %sd post %s on board %s." % (caller, verb, post_num, board))
            else:
                caller.msg("Post %s failed for unknown reason." % verb)
            return
        if 'edit' in switches:
            lhs = self.lhs
            arglist = lhs.split("/")
            if len(arglist) < 2 or not self.rhs:
                self.msg("Usage: @bb/edit <board #>/<post #>")
                return
            try:
                post_num = int(arglist[1])
            except ValueError:
                self.msg("Invalid post number.")
                return
            board = access_bboard(caller, arglist[0], 'write')
            if not board:
                return
            post = board.get_post(caller, post_num)
            if not post:
                return
            if caller not in post.db_sender_accounts.all() and not board.access(caller, "edit"):
                caller.msg("You cannot edit someone else's post, only your own.")
                return
            if board.edit_post(self.caller, post, self.rhs):
                self.msg("Post edited.")
                inform_staff("%s has edited post %s on board %s." % (caller, post_num, board))
            return
        if 'post' in switches:        
            if not self.rhs:
                caller.msg("Usage: @bb/post <board #>/<subject> = <post message>")
                return
            lhs = self.lhs
            arglist = lhs.split("/")
            if len(arglist) < 2:
                subject = "No Subject"
            else:
                subject = arglist[1]
            board = access_bboard(caller, arglist[0], 'write')
            if not board:
                return
            board.bb_post(caller, self.rhs, subject)
            

class CmdOrgStance(ArxPlayerCommand):
    """
    @bborgstance - post an org's response to a Proclamation
    
    Usage:
        @bborgstance <post #>/<org>=<brief declaration>
        
    Declare your org's bold, nuanced political stance in response to a posted
    proclamation - in a svelte 280 characters or less.
    """
    key = "@bborgstance"
    aliases = ["bborgstance", "+bborgstance"]
    help_category = "Comms"
    locks = "cmd:not pperm(bboard_banned)"
    
    def func(self):
        lhs = self.lhs
        arglist = lhs.split("/")
        if len(arglist) < 2 or not self.rhs:
            self.msg("Usage: @bborgstance <post #>/<org>=<brief declaration>")
            return
        try:
            postnum = int(arglist[0])
        except ValueError:
            self.msg("Invalid post number.")
            return
        from django.core.exceptions import ObjectDoesNotExist
        try:
            org = self.caller.current_orgs.get(name__iexact=arglist[1])
        except ObjectDoesNotExist:
            self.msg("You are not a member of that Org.")
            return
        board = BBoard.objects.get(db_key__iexact="proclamations")
        board.bb_orgstance(self.caller, org, self.rhs, postnum)
        

class CmdBBSub(ArxPlayerCommand):
    """
    @bbsub - subscribe to a bulletin board

    Usage:
       @bbsub <board #>
       @bbsub/add <board #>=<player>

    Subscribes to a board of the given number.
    """

    key = "@bbsub"
    aliases = ["bbsub", "+bbsub"]
    help_category = "Comms"
    locks = "cmd:not pperm(bboard_banned)"

    def func(self):
        """Implement the command"""

        caller = self.caller
        args = self.lhs

        if not args:
            self.msg("Usage: @bbsub <board #>.")
            return

        bboard = access_bboard(caller, args)
        if not bboard:
            return

        # check permissions
        if not bboard.access(caller, 'read'):
            self.msg("%s: You are not allowed to listen to this bboard." % bboard.key)
            return
        if 'add' in self.switches:
            if not caller.check_permstring("builders"):
                caller.msg("You must be a builder or higher to use that switch.")
                return
            targ = caller.search(self.rhs)
        else:
            targ = caller
        if not targ:
            return
        if not bboard.subscribe_bboard(targ):
            if 'quiet' not in self.switches:
                caller.msg("%s is already subscribed to that board." % targ)
            return
        caller.msg("Successfully subscribed %s to %s" % (targ, bboard.key.capitalize()))


class CmdBBUnsub(ArxPlayerCommand):
    """
    bbunsub - unsubscribe from a bulletin board

    Usage:
       @bbunsub <board #>

    Removes a bulletin board from your list of
    subscriptions.
    """

    key = "@bbunsub"
    aliases = ["bbunsub, +bbunsub"]
    help_category = "Comms"
    locks = "cmd:not perm(bboard_banned)"

    def func(self):
        """Implementing the command. """

        caller = self.caller

        if not self.args:
            self.msg("Usage: @bbunsub <board #>")
            return
        args = self.args
        if not args:
            self.msg("Usage: @bbsub <board #>.")
            return
        bboard = access_bboard(caller, args)
        if not bboard:
            return
        if not bboard.has_subscriber(caller):
            caller.msg("You are not subscribed to that board.")
            return
        bboard.unsubscribe_bboard(caller)
        caller.msg("Unsubscribed from %s" % bboard.key)


class CmdBBCreate(ArxCommand):
    """
    @bbcreate
    bboardcreate
    Usage:
     @bbcreate <boardname> = description

    Creates a new bboard owned by you.
    """

    key = "@bbcreate"
    aliases = ["+bbcreate", "bboardcreate"]
    locks = "cmd:perm(bbcreate) or perm(Wizards)"
    help_category = "Comms"

    def func(self):
        """Implement the command"""

        caller = self.caller

        if not self.args:
            self.msg("Usage @bbcreate <boardname> = description")
            return

        description = "A bulletin board"

        if self.rhs:
            description = self.rhs
        lhs = self.lhs
        bboardname = lhs
        # Create and set the bboard up
        lockstring = "write:all();read:all();control:id(%s)" % caller.id

        typeclass = BOARD_TYPECLASS
        new_board = create.create_object(typeclass, bboardname, location=caller,
                                         home="#4", permissions=None,
                                         locks=lockstring, aliases=None, destination=None,
                                         report_to=None, nohome=False)
        new_board.desc = description
        self.msg("Created bboard %s." % new_board.key)
        new_board.subscribe_bboard(caller)
        new_board.save()
