"""
Views for msg app - Msg proxy models, boards, etc
"""
import json

from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponseRedirect, HttpResponse, Http404
from django.shortcuts import render, get_object_or_404
from django.views.generic import ListView
from django.contrib.auth import get_user_model

from evennia.utils import ansi

from commands.base_commands.bboards import get_boards
from .forms import (JournalMarkAllReadForm, JournalWriteForm, JournalMarkOneReadForm, JournalMarkFavorite,
                    JournalRemoveFavorite)
from server.utils.view_mixins import LimitPageMixin
from typeclasses.bulletin_board.bboard import BBoard, Post
from world.msgs.models import Journal


# Create your views here.


class JournalListView(LimitPageMixin, ListView):
    """View for listing journals."""
    model = Journal
    template_name = 'msgs/journal_list.html'
    paginate_by = 20

    def search_filters(self, queryset):
        """Filters the queryset based on what's passed along in GET as search options"""
        get = self.request.GET
        if not get:
            return queryset
        senders = get.get('sender_name', "").split()
        if senders:
            exclude_senders = [ob[1:] for ob in senders if ob.startswith("-")]
            senders = [ob for ob in senders if not ob.startswith("-")]
            sender_filter = Q()
            for sender in senders:
                sender_filter |= Q(db_sender_objects__db_key__iexact=sender)
            queryset = queryset.filter(sender_filter)
            sender_filter = Q()
            for sender in exclude_senders:
                sender_filter |= Q(db_sender_objects__db_key__iexact=sender)
            queryset = queryset.exclude(sender_filter)
        receivers = get.get('receiver_name', "").split()
        if receivers:
            exclude_receivers = [ob[1:] for ob in receivers if ob.startswith("-")]
            receivers = [ob for ob in receivers if not ob.startswith("-")]
            receiver_filter = Q()
            for receiver in receivers:
                receiver_filter |= Q(db_receivers_objects__db_key__iexact=receiver)
            queryset = queryset.filter(receiver_filter)
            receiver_filter = Q()
            for receiver in exclude_receivers:
                receiver_filter |= Q(db_receivers_objects__db_key__iexact=receiver)
            queryset = queryset.exclude(receiver_filter)
        text = get.get('search_text', None)
        if text:
            queryset = queryset.filter(db_message__icontains=text)
        if self.request.user and self.request.user.is_authenticated():
            favtag = "pid_%s_favorite" % self.request.user.id
            favorites = get.get('favorites', None)
            if favorites:
                queryset = queryset.filter(db_tags__db_key=favtag)
        return queryset

    def get_queryset(self):
        """Gets our queryset based on user privileges"""
        user = self.request.user
        if not user or not user.is_authenticated() or not user.char_ob:
            qs = Journal.white_journals.order_by('-db_date_created')
        else:
            qs = Journal.objects.all_permitted_journals(user).all_unread_by(user).order_by('-db_date_created')
        return self.search_filters(qs)

    def get_context_data(self, **kwargs):
        """Gets our context - do special stuff to preserve search tags through pagination"""
        context = super(JournalListView, self).get_context_data(**kwargs)
        # paginating our read journals as well as unread
        search_tags = ""
        sender = self.request.GET.get('sender_name', None)
        if sender:
            search_tags += "&sender_name=%s" % sender
        receiver = self.request.GET.get('receiver_name', None)
        if receiver:
            search_tags += "&receiver_name=%s" % receiver
        search_text = self.request.GET.get('search_text', None)
        if search_text:
            search_tags += "&search_text=%s" % search_text
        favorites = self.request.GET.get('favorites', None)
        if favorites:
            search_tags += "&favorites=True"
        context['search_tags'] = search_tags
        context['write_journal_form'] = JournalWriteForm()
        context['page_title'] = 'Journals'
        if self.request.user and self.request.user.is_authenticated():
            context['fav_tag'] = "pid_%s_favorite" % self.request.user.id
        else:
            context['fav_tag'] = None
        return context

    # noinspection PyUnusedLocal
    def post(self, request, *args, **kwargs):
        """Handle POST requests: marking journals read or as favorites"""
        if "mark_all_read" in request.POST:
            form = JournalMarkAllReadForm(request.POST)
            if form.is_valid():
                for msg in form.cleaned_data['choices']:
                    msg.db_receivers_accounts.add(self.request.user)
            else:
                raise Http404(form.errors)
        if "mark_one_read" in request.POST:
            form = JournalMarkOneReadForm(request.POST)
            if form.is_valid():
                msg = form.cleaned_data['choice']
                msg.db_receivers_accounts.add(self.request.user)
            else:
                raise Http404(form.errors)
        if "mark_favorite" in request.POST:
            form = JournalMarkFavorite(request.POST)
            if form.is_valid():
                form.tag_msg(self.request.user.char_ob)
        if "remove_favorite" in request.POST:
            form = JournalRemoveFavorite(request.POST)
            if form.is_valid():
                form.untag_msg(self.request.user.char_ob)
        if "write_journal" in request.POST:
            form = JournalWriteForm(request.POST)
            if form.is_valid():
                # write journal
                form.create_journal(self.request.user.char_ob)
            else:
                raise Http404(form.errors)
        return HttpResponseRedirect(reverse('msgs:list_journals'))


class JournalListReadView(JournalListView):
    """Version of journal list for journals the user has already read"""
    template_name = 'msgs/journal_list_read.html'

    def get_queryset(self):
        """Get queryset based on permissions. Reject outright if they're not logged in."""
        user = self.request.user
        if not user or not user.is_authenticated() or not user.char_ob:
            raise PermissionDenied("You must be logged in.")
        qs = Journal.objects.all_permitted_journals(user).all_read_by(user).order_by('-db_date_created')
        return self.search_filters(qs)


API_CACHE = None


def journal_list_json(request):
    """Return json list of journals for API request"""
    def get_fullname(char):
        """Auto-generate last names for people who don't have em. Poor bastards. Literally!"""
        commoner_names = {
            'Velenosa': 'Masque',
            'Valardin': 'Honor',
            'Crownsworn': 'Crown',
            'Redrain': 'Frost',
            'Grayson': 'Crucible',
            'Thrax': 'Waters'
        }
        last = commoner_names.get(char.db.fealty, "") if char.db.family == "None" else char.db.family
        return "{0} {1}".format(char.key, last)

    def get_response(entry):
        """
        Helper function for getting json for each object
        Args:
            entry (Msg): Message object

        Returns:
            dict to convert to json
        """
        try:
            sender = entry.senders[0]
        except IndexError:
            sender = None
        try:
            target = entry.db_receivers_objects.all()[0]
        except IndexError:
            target = None
        from world.msgs.messagehandler import MessageHandler
        ic_date = MessageHandler.get_date_from_header(entry)
        return {
            'id': entry.id,
            'sender': get_fullname(sender) if sender else "",
            'target': get_fullname(target) if target else "",
            'message': entry.db_message,
            'ic_date': ic_date
        }

    try:
        timestamp = request.GET.get('timestamp', 0)
        import datetime
        timestamp = datetime.datetime.fromtimestamp(float(timestamp))
    except (AttributeError, ValueError, TypeError):
        timestamp = None
    global API_CACHE
    if timestamp:
        ret = map(get_response, Journal.white_journals.filter(db_date_created__gt=timestamp
                                                              ).order_by('-db_date_created'))
        return HttpResponse(json.dumps(ret), content_type='application/json')
    if not API_CACHE:  # cache the list of all of them
        ret = map(get_response, Journal.white_journals.order_by('-db_date_created'))
        API_CACHE = json.dumps(ret)
    return HttpResponse(API_CACHE, content_type='application/json')


def board_list(request):
    """View for getting list of boards"""

    def map_board(board):
        """Helper function for getting dict of information for each board to add to context"""
        last_post = board.posts.last()
        last_date = ""
        if last_post:
            last_date = last_post.db_date_created.strftime("%x")

        if request.user.is_authenticated():
            unread = board.num_of_unread_posts(user, old=False)
        else:
            unread = board.posts.count()

        return {
            'id': board.id,
            'name': board.key,
            'unread': unread,
            'last_date': last_date
        }

    unread_only = None

    save_unread = request.GET.get("save_unread")
    if save_unread is None:
        if not request.user or not request.user.is_authenticated():
            unread_only = False
        else:
            unread_only = request.user.tags.get('web_boards_only_unread', category='boards')

    if unread_only is None:
        unread_only = False

    request_unread = request.GET.get("unread_only")

    if request_unread:
        if request_unread == "1" or request_unread == "on":
            unread_only = True
        else:
            unread_only = False

    if save_unread and request.user.is_authenticated():
        if unread_only:
            request.user.tags.add('web_boards_only_unread', category='boards')
        else:
            request.user.tags.remove('web_boards_only_unread', category='boards')

    user = request.user
    if not user or not user.is_authenticated():
        Account = get_user_model()
        try:
            user = Account.objects.get(username__iexact="Guest1")
        except (Account.DoesNotExist, Account.MultipleObjectsReturned):
            raise Http404

    raw_boards = get_boards(user)
    boards = map(lambda board: map_board(board), raw_boards)
    if unread_only:
        boards = filter(lambda board: board['unread'] > 0, boards)

    context = {
        'boards': boards,
        'page_title': 'Boards',
        'unread_only': "checked" if unread_only else ""
    }
    return render(request, 'msgs/board_list.html', context)


def board_for_request(request, board_id):
    """Check if we can get a board by the given ID. 404 if we don't have privileges"""
    board = get_object_or_404(BBoard, id=board_id)
    user = request.user
    if not user or not user.is_authenticated:
        Account = get_user_model()
        try:
            user = Account.objects.get(username__iexact="Guest1")
        except (Account.DoesNotExist, Account.MultipleObjectsReturned):
            raise Http404

    character = user.char_ob
    if not board.access(character):
        raise Http404
    return board


def posts_for_request(board):
    """Get all posts from the board in reverse order"""
    return list(board.get_all_posts(old=False))[::-1]


def posts_for_request_all(board):
    """Get all posts from the board in reverse order"""
    current_posts = list(board.get_all_posts(old=False))[::-1]
    old_posts = list(board.get_all_posts(old=True))[::-1]
    return current_posts + old_posts


def posts_for_request_all_search(board, searchstring):
    """Get all posts from the board in reverse order"""
    current_posts = list(board.get_all_posts(old=False).filter(db_message__icontains=searchstring))[::-1]
    old_posts = list(board.get_all_posts(old=True).filter(db_message__icontains=searchstring))[::-1]
    return current_posts + old_posts


def posts_for_request_all_search_global(user, searchstring):
    """Get all posts from all boards for this user, containing the searchstring"""
    # raw_boards = get_boards(user)
    # result = None
    # for board in raw_boards:
    #     current_posts = list(board.get_all_posts(old=False).filter(db_message__icontains=searchstring))
    #     old_posts = list(board.get_all_posts(old=True).filter(db_message__icontains=searchstring))
    #     if result is None:
    #         result = current_posts
    #     else:
    #         result = result + current_posts
    #     result = result + old_posts
    #
    # result.sort(key=lambda x: x.db_date_created, reverse=True)
    # return result

    posts = list(Post.objects.filter(db_message__icontains=searchstring).order_by('-db_date_created'))
    return filter(lambda x: x.bulletin_board.access(user, 'read'), posts)


def post_list(request, board_id):
    """View for getting list of posts for a given board"""
    def post_map(post, bulletin_board, read_posts_list):
        """Helper function to get dict of post information to add to context per post"""
        return {
            'id': post.id,
            'poster': bulletin_board.get_poster(post),
            'subject': ansi.strip_ansi(post.db_header),
            'date': post.db_date_created.strftime("%x"),
            'unread': post not in read_posts_list
        }

    board = board_for_request(request, board_id)

    search = request.GET.get("search")
    if search and search != "":
        raw_posts = posts_for_request_all_search(board, search)
    else:
        raw_posts = posts_for_request_all(board)

    # force list so it's not generating a query in each map run
    if not request.user or not request.user.is_authenticated():
        read_posts = []
    else:
        read_posts = list(Post.objects.all_read_by(request.user))
    posts = map(lambda post: post_map(post, board, read_posts), raw_posts)
    return render(request, 'msgs/post_list.html', {'board': board, 'page_title': board.key, 'posts': posts})


def post_list_global_search(request):
    """View for getting list of posts for a given board"""
    def post_map(post, read_posts_list):
        """Helper function to get dict of post information to add to context per post"""
        return {
            'id': post.id,
            'poster': post.bulletin_board.get_poster(post),
            'subject': post.bulletin_board.key + ": " + ansi.strip_ansi(post.db_header),
            'date': post.db_date_created.strftime("%x"),
            'unread': post not in read_posts_list,
            'board': post.bulletin_board
        }


    user = request.user
    if not user or not user.is_authenticated():
        read_posts = []
        Account = get_user_model()
        try:
            user = Account.objects.get(username__iexact="Guest1")
        except (Account.DoesNotExist, Account.MultipleObjectsReturned):
            raise Http404
    else:
        read_posts = list(Post.objects.all_read_by(user))

    search = request.GET.get("search")
    if search and search != "":
        raw_posts = posts_for_request_all_search_global(user, search)
    else:
        raw_posts = []

    posts = map(lambda post: post_map(post, read_posts), raw_posts)
    return render(request, 'msgs/post_list_search.html', {'page_title': 'Search Results', 'posts': posts})


def post_view_all(request, board_id):
    """View for seeing all posts at once. It'll mark them all read."""
    def post_map(post, bulletin_board, read_posts_list):
        """Returns dict of information about each individual post to add to context"""
        return {
            'id': post.id,
            'poster': bulletin_board.get_poster(post),
            'subject': ansi.strip_ansi(post.db_header),
            'date': post.db_date_created.strftime("%x"),
            'unread': post not in read_posts_list,
            'text': ansi.strip_ansi(post.db_message)
        }

    board = board_for_request(request, board_id)
    raw_posts = posts_for_request(board)
    if not request.user or not request.user.is_authenticated():
        read_posts = []
    else:
        read_posts = list(Post.objects.all_read_by(request.user))

    if request.user.is_authenticated():
        alts = []
        if request.user.db.bbaltread:
            try:
                alts = [ob.player for ob in request.user.roster.alts]
            except AttributeError:
                pass
        accounts = [request.user]
        accounts.extend(alts)
        ReadPostModel = Post.db_receivers_accounts.through
        bulk_list = []
        for post in raw_posts:
            if post not in read_posts:
                for account in accounts:
                    bulk_list.append(ReadPostModel(accountdb=account, msg=post))
                    # They've read everything, clear out their unread cache count
                    board.zero_unread_cache(account)
        ReadPostModel.objects.bulk_create(bulk_list)

    posts = map(lambda post: post_map(post, board, read_posts), raw_posts)
    return render(request, 'msgs/post_view_all.html', {'board': board, 'page_title': board.key + " - Posts",
                                                       'posts': posts})


def post_view_unread_board(request, board_id):
    """View for seeing all posts at once. It'll mark them all read."""
    def post_map(post, bulletin_board):
        """Returns dict of information about each individual post to add to context"""
        return {
            'id': post.id,
            'poster': bulletin_board.get_poster(post),
            'subject': ansi.strip_ansi(post.db_header),
            'date': post.db_date_created.strftime("%x"),
            'text': ansi.strip_ansi(post.db_message)
        }

    board = board_for_request(request, board_id)
    unread_posts = []

    if request.user.is_authenticated():
        unread_posts = Post.objects.all_unread_by(request.user).filter(db_receivers_objects=board)
        alts = []
        if request.user.db.bbaltread:
            alts = [ob.player for ob in request.user.roster.alts]
        accounts = [request.user]
        accounts.extend(alts)
        ReadPostModel = Post.db_receivers_accounts.through
        bulk_list = []

        for post in unread_posts:
            for account in accounts:
                bulk_list.append(ReadPostModel(accountdb=account, msg=post))
                # They've read everything, clear out their unread cache count
                board.zero_unread_cache(account)
        ReadPostModel.objects.bulk_create(bulk_list)

    posts = map(lambda post: post_map(post, board), unread_posts)
    return render(request, 'msgs/post_view_all.html', {'board': board, 'page_title': board.key + " - Unread Posts",
                                                       'posts': posts})


def post_view_unread(request):
    """View for seeing all posts at once. It'll mark them all read."""

    def post_map(post):
        """Returns dict of information about each individual post to add to context"""
        return {
            'id': post.id,
            'board': post.bulletin_board.key,
            'poster': post.poster_name,
            'subject': ansi.strip_ansi(post.db_header),
            'date': post.db_date_created.strftime("%x"),
            'text': ansi.strip_ansi(post.db_message)
        }

    raw_boards = get_boards(request.user)
    unread_posts = Post.objects.all_unread_by(request.user).filter(db_receivers_objects__in=raw_boards
                                                                   ).order_by('db_receivers_objects')

    if request.user.is_authenticated():
        alts = []
        alt_unread_posts = []
        if request.user.db.bbaltread:
            try:
                alts = [ob.player for ob in request.user.roster.alts]
            except AttributeError:
                pass
            if alts:
                alt_unread_posts = list(unread_posts.exclude(db_receivers_accounts__in=alts))
        ReadPostModel = Post.db_receivers_accounts.through
        bulk_list = []

        mapped_posts = []

        for unread_post in unread_posts:
            mapped_posts.append(post_map(unread_post))
            bulk_list.append(ReadPostModel(accountdb=request.user, msg=unread_post))
            for alt in alts:
                if unread_post in alt_unread_posts:
                    bulk_list.append(ReadPostModel(accountdb=alt, msg=unread_post))

        # They've read everything, clear out their unread cache count
        accounts = [request.user] + alts
        for board in raw_boards:
            for account in accounts:
                board.zero_unread_cache(account)

        ReadPostModel.objects.bulk_create(bulk_list)

    return render(request, 'msgs/post_view_unread.html', {'page_title': 'All Unread Posts',
                                                          'posts': mapped_posts})


def post_view(request, board_id, post_id):
    """View for seeing an individual post"""
    board = board_for_request(request, board_id)
    try:
        post = board.posts.get(id=post_id)
    except (Post.DoesNotExist, ValueError):
        try:
            post = board.archived_posts.get(id=post_id)
        except (Post.DoesNotExist, ValueError):
            raise Http404

    if request.user.is_authenticated():
        board.mark_read(request.user, post)

    context = {
        'id': post.id,
        'poster': board.get_poster(post),
        'subject': ansi.strip_ansi(post.db_header),
        'date': post.db_date_created.strftime("%x"),
        'text': post.db_message,
        'page_title': board.key + " - " + post.db_header
    }
    return render(request, 'msgs/post_view.html', context)
