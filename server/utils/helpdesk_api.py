"""
API file for interacting with the django-helpdesk system.
The real API for helpdesk requires POST requests but since
that took me about 20 hours of unsuccessfully getting it to
work, I'm just going to build and change the fucking models by hand
here.
"""
from django.conf import settings
from .arx_utils import inform_staff
from datetime import datetime
from web.helpdesk.models import Ticket, Queue, FollowUp, KBItem


def create_ticket(
    caller,
    message,
    priority=3,
    queue_slug=settings.REQUEST_QUEUE_SLUG,
    kb_category=None,
    send_email=True,
    optional_title=None,
    plot=None,
    beat=None,
    goal_update=None,
):
    """
    Creates a new ticket and returns it.
    """
    queue = Queue.objects.get(slug=queue_slug)
    email = None
    if send_email and caller.email != "dummy@dummy.com":
        email = caller.email
    if not optional_title:
        optional_title = message if len(message) <= 15 else "%s+" % message[:14]
    try:
        room = caller.char_ob.location
    except AttributeError:
        room = None
    # not a fan of emojis in tickets, tbh
    message = (
        message.rstrip(" ;)").rstrip(" :p").rstrip(" :P").rstrip(" ;P").rstrip(" ;p")
    )
    ticket = Ticket(
        title=optional_title,
        queue=queue,
        db_date_created=datetime.now(),
        submitter_email=email,
        submitting_player=caller,
        submitting_room=room,
        description=message,
        kb_category=kb_category,
        priority=priority,
        plot=plot,
        beat=beat,
        goal_update=goal_update,
    )
    if optional_title[:-1] in message:
        title = ""
    else:
        title = "{w[{n%s{w]{n " % optional_title
    ticket.save()
    staff_msg = "{w[%s]{n Ticket #%s by {c%s{n: %s%s" % (
        str(queue),
        ticket.id,
        caller,
        title,
        message,
    )
    inform_staff(staff_msg)
    # to do: mail player
    player_msg = "You have successfully created a new ticket.\n\n"
    player_msg += "{wTicket ID:{n %s\n" % ticket.id
    player_msg += "{wIssue:{n %s" % message
    caller.inform(player_msg, category="requests", append=False)
    return ticket


def add_followup(caller, ticket, message, mail_player=True):
    """
    Add comment/response to a ticket. Since this is not a method to
    resolve tickets, it usually is a private response indicating
    what steps may need to be taken to reach resolution. If private
    is set to True, the submitter is not emailed the response.
    """
    try:
        new_followup = FollowUp(
            user_id=caller.id,
            date=datetime.now(),
            ticket=ticket,
            comment=message,
            public=False,
        )
        new_followup.save()
    except Exception as err:
        inform_staff("ERROR when attempting to add followup to ticket: %s" % err)
        return False
    inform_staff(
        "{w[Requests]{n: %s has left a comment on ticket %s: %s"
        % (caller.key, ticket.id, message)
    )
    if mail_player:
        header = "New comment on your ticket by %s.\n\n" % caller.key
        mail_update(ticket, message, header)
    return True


def resolve_ticket(caller, ticket, message, by_submitter=False):
    """
    Closes ticket.
    """
    try:
        if by_submitter and ticket.submitting_player.id != caller.id:
            raise ValueError(
                "Attepmted to close a ticket that wasn't submitted by the caller"
            )

        if ticket.resolution:
            ticket.resolution += "\n\n" + message
        else:
            ticket.resolution = message
        ticket.assigned_to_id = caller.id
        ticket.modified = datetime.now()
        ticket.status = ticket.CLOSED_STATUS
        ticket.save()
    except Exception as err:
        inform_staff(f"ERROR: Error when attempting to close ticket: {err}")
        return False

    if ticket.queue.slug in ("Code", "Bugs", "Typo"):
        post = False
        subject = None
    else:
        subject = f"{ticket.queue.slug} {ticket.id} closed"
        post = f"|wPlayer:|n {ticket.submitting_player}\n{ticket.request_and_response_body()}"

    if not by_submitter:
        inform = (
            f"|w[Requests]|n: {caller.key} has closed ticket {ticket.id}: {message}"
        )
    else:
        inform = (
            f"|w[Requests]|n: ticket {ticket.id} was closed by submitter: {message}"
        )

    inform_staff(
        message=inform,
        post=post,
        subject=subject,
    )

    if by_submitter:
        return True

    header = f"Your ticket has been closed by {caller.key}.\n\n"
    mail_update(ticket, message, header)

    if ticket.kb_category:
        from typeclasses.bulletin_board.bboard import BBoard

        # get_or_create to allow closing ticket multiple times to 'edit' an entry
        item, created = KBItem.objects.get_or_create(title=ticket.title)
        item.category = ticket.kb_category
        item.question = ticket.description
        item.answer = ticket.resolution
        item.save()
        verb = "created" if created else "changed"
        inform_staff("Knowledge Base Item '%s' has been %s." % (item, verb))
        try:
            board = BBoard.objects.get(db_key__iexact="Theme Questions")
            board.bb_post(
                caller,
                item.display(),
                subject=item.title,
            )
        except BBoard.DoesNotExist:
            pass

        return item

    return True


def mail_update(ticket, comments, header="New ticket activity\n"):
    player = ticket.submitting_player
    msg = header
    msg += "{wTicket ID:{n %s\n" % ticket.id
    msg += "{wIssue:{n %s\n\n" % ticket.description
    msg += "{wGM comments:{n %s" % comments
    player.inform(msg, category="requests", append=False)
