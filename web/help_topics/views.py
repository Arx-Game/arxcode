# Views for our help topics app

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import render, get_object_or_404
from evennia.help.models import HelpEntry
from world.dominion.models import (
    CraftingRecipe,
    CraftingMaterialType,
    Organization,
    Member,
)
from web.helpdesk.models import KBCategory


def topic(request, object_key):
    object_key = object_key.lower()
    topic_ob = get_object_or_404(HelpEntry, db_key__iexact=object_key)
    can_see = False
    try:
        can_see = topic_ob.access(request.user, "view", default=True)
    except AttributeError:
        pass
    if not can_see:
        raise PermissionDenied
    return render(
        request, "help_topics/topic.html", {"topic": topic_ob, "page_title": object_key}
    )


def command_help(request, cmd_key):
    from commands.default_cmdsets import AccountCmdSet, CharacterCmdSet
    from commands.cmdsets.situational import SituationalCmdSet

    user = request.user
    cmd_key = cmd_key.lower()
    matches = [
        ob
        for ob in AccountCmdSet()
        if ob.key.lower() == cmd_key and ob.access(user, "cmd")
    ]
    matches += [
        ob
        for ob in CharacterCmdSet()
        if ob.key.lower() == cmd_key and ob.access(user, "cmd")
    ]
    matches += [
        ob
        for ob in SituationalCmdSet()
        if ob.key.lower() == cmd_key and ob.access(user, "cmd")
    ]
    return render(
        request,
        "help_topics/command_help.html",
        {"matches": matches, "page_title": cmd_key},
    )


def list_topics(request):
    user = request.user
    try:
        all_topics = []
        for topic_ob in HelpEntry.objects.all():
            try:
                if topic_ob.access(user, "view", default=True):
                    all_topics.append(topic_ob)
            except AttributeError:
                continue
        all_topics = sorted(all_topics, key=lambda entry: entry.key.lower())
        all_categories = list(
            set(
                [
                    topic_ob.help_category.capitalize()
                    for topic_ob in all_topics
                    if topic_ob.access(user, "view")
                ]
            )
        )
        all_categories = sorted(all_categories)
    except IndexError:
        raise Http404("Error in compiling topic list.")
    # organizations also
    from django.db.models import Q

    all_orgs = (
        Organization.objects.filter(
            Q(secret=False)
            & Q(members__deguilded=False)
            & Q(members__player__player__isnull=False)
        )
        .distinct()
        .order_by("name")
    )
    secret_orgs = []
    # noinspection PyBroadException
    try:
        if user.is_staff or user.check_permstring("can_see_secret_orgs"):
            secret_orgs = Organization.objects.filter(secret=True)
        else:
            secret_orgs = Organization.objects.filter(
                Q(members__deguilded=False)
                & Q(secret=True)
                & Q(members__player__player=user)
            )
    except Exception:
        pass
    lore_categories = KBCategory.objects.filter(parent__isnull=True)
    return render(
        request,
        "help_topics/list.html",
        {
            "all_topics": all_topics,
            "all_categories": all_categories,
            "lore_categories": lore_categories,
            "all_orgs": all_orgs,
            "secret_orgs": secret_orgs,
            "page_title": "topics",
        },
    )


def list_recipes(request):
    user = request.user
    all_recipes = CraftingRecipe.objects.all().order_by("ability", "difficulty")
    if not user.is_staff:
        all_recipes = all_recipes.exclude(known_by__organization_owner__isnull=False)
    recipe_name = request.GET.get("recipe_name")
    if recipe_name:
        all_recipes = all_recipes.filter(name__icontains=recipe_name)
    ability = request.GET.get("ability")
    if ability:
        all_recipes = all_recipes.filter(ability__iexact=ability)
    difficulty = request.GET.get("difficulty")
    if difficulty:
        try:
            all_recipes = all_recipes.filter(difficulty__gte=difficulty)
        except (ValueError, TypeError):
            pass
    known_recipes = []
    materials = CraftingMaterialType.objects.all().order_by("value")
    try:
        known_recipes = user.Dominion.assets.recipes.all()
    except AttributeError:
        pass
    return render(
        request,
        "help_topics/recipes.html",
        {
            "all_recipes": all_recipes,
            "materials": materials,
            "known_recipes": known_recipes,
            "page_title": "recipes",
        },
    )


def display_org(request, object_id):
    user = request.user
    rank_display = 0
    show_secret = 0
    org = get_object_or_404(Organization, id=object_id)
    if not user.is_staff:
        if org.secret:
            try:
                if not org.members.filter(
                    deguilded=False, player__player__id=user.id
                ).exists():
                    raise PermissionDenied
                try:
                    rank_display = user.Dominion.memberships.get(
                        organization=org, deguilded=False
                    ).rank
                except (Member.DoesNotExist, AttributeError):
                    rank_display = 11
                show_secret = rank_display
            except (AttributeError, PermissionDenied):
                raise PermissionDenied
        else:
            try:
                show_secret = user.Dominion.memberships.get(
                    organization=org, deguilded=False
                ).rank
            except (Member.DoesNotExist, AttributeError):
                show_secret = 11
    try:
        show_money = org.assets.can_be_viewed_by(user)
    except AttributeError:
        show_money = False
    try:
        holdings = org.assets.estate.holdings.all()
    except AttributeError:
        holdings = []
    active_tab = request.GET.get("active_tab")
    if not active_tab or active_tab == "all":
        members = org.all_members.exclude(player__player__roster__roster__name="Gone")
        active_tab = "all"
    elif active_tab == "active":
        members = org.active_members
    elif active_tab == "available":
        members = org.all_members.filter(
            player__player__roster__roster__name="Available"
        )
    else:
        members = org.all_members.filter(player__player__roster__roster__name="Gone")

    return render(
        request,
        "help_topics/org.html",
        {
            "org": org,
            "members": members,
            "active_tab": active_tab,
            "holdings": holdings,
            "rank_display": rank_display,
            "show_secret": show_secret,
            "page_title": org,
            "show_money": show_money,
        },
    )


def list_commands(request):
    from commands.default_cmdsets import AccountCmdSet, CharacterCmdSet
    from commands.cmdsets.situational import SituationalCmdSet

    user = request.user

    def sort_name(cmd):
        cmdname = cmd.key.lower()
        cmdname = cmdname.lstrip("+").lstrip("@")
        return cmdname

    def check_cmd_access(cmdset):
        cmd_list = []
        for cmd in cmdset:
            try:
                if cmd.access(user, "cmd"):
                    cmd_list.append(cmd)
            except (AttributeError, ValueError, TypeError):
                continue
        return sorted(cmd_list, key=sort_name)

    player_cmds = check_cmd_access(AccountCmdSet())
    char_cmds = check_cmd_access(CharacterCmdSet())
    situational_cmds = check_cmd_access(SituationalCmdSet())
    return render(
        request,
        "help_topics/list_commands.html",
        {
            "player_cmds": player_cmds,
            "character_cmds": char_cmds,
            "situational_cmds": situational_cmds,
            "page_title": "commands",
        },
    )


def lore_categories(request, object_id):
    kb_cat = get_object_or_404(KBCategory, id=object_id)
    return render(
        request,
        "help_topics/lore_category.html",
        {
            "kb_cat": kb_cat,
            "kb_items": kb_cat.kb_items.all(),
            "kb_subs": kb_cat.subcategories.all(),
            "kb_parent": kb_cat.parent,
            "page_title": kb_cat,
        },
    )
