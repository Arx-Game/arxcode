#!/usr/bin/python
"""
Jutda Helpdesk - A Django powered ticket tracker for small enterprise.

(c) Copyright 2008 Jutda. All Rights Reserved. See LICENSE for details.

scripts/get_email.py - Designed to be run from cron, this script checks the
                       POP and IMAP boxes defined for the queues within a
                       helpdesk, creating tickets from the new messages (or
                       adding to existing tickets if needed)
"""

import email
import imaplib
import mimetypes
import poplib
import re
import socket

from datetime import timedelta
from email.header import decode_header
from email.Utils import parseaddr, collapse_rfc2231_value
from optparse import make_option

from email_reply_parser import EmailReplyParser

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils.translation import ugettext as _
from web.helpdesk import settings

try:
    from django.utils import timezone
except ImportError:
    from datetime import datetime as timezone

from web.helpdesk.lib import send_templated_mail, safe_template_context
from web.helpdesk.models import Queue, Ticket, FollowUp, Attachment, IgnoreEmail


class Command(BaseCommand):
    def __init__(self):
        BaseCommand.__init__(self)

        self.option_list += (
            make_option(
                "--quiet",
                "-q",
                default=False,
                action="store_true",
                help="Hide details about each queue/message as they are processed",
            ),
        )

    help = "Process Jutda Helpdesk queues and process e-mails via POP3/IMAP as required, feeding them into the helpdesk."

    def handle(self, *args, **options):
        quiet = options.get("quiet", False)
        process_email(quiet=quiet)


def process_email(quiet=False):
    for q in Queue.objects.filter(
        email_box_type__isnull=False, allow_email_submission=True
    ):

        if not q.email_box_last_check:
            q.email_box_last_check = timezone.now() - timedelta(minutes=30)

        if not q.email_box_interval:
            q.email_box_interval = 0

        queue_time_delta = timedelta(minutes=q.email_box_interval)

        if (q.email_box_last_check + queue_time_delta) > timezone.now():
            continue

        process_queue(q, quiet=quiet)

        q.email_box_last_check = timezone.now()
        q.save()


def process_queue(q, quiet=False):
    if not quiet:
        print "Processing: %s" % q

    if q.socks_proxy_type and q.socks_proxy_host and q.socks_proxy_port:
        try:
            import socks
        except ImportError:
            raise ImportError(
                "Queue has been configured with proxy settings, but no socks library was installed. Try to install PySocks via pypi."
            )

        proxy_type = {
            "socks4": socks.SOCKS4,
            "socks5": socks.SOCKS5,
        }.get(q.socks_proxy_type)

        socks.set_default_proxy(
            proxy_type=proxy_type, addr=q.socks_proxy_host, port=q.socks_proxy_port
        )
        socket.socket = socks.socksocket
    else:
        socket.socket = socket._socketobject

    email_box_type = (
        settings.QUEUE_EMAIL_BOX_TYPE
        if settings.QUEUE_EMAIL_BOX_TYPE
        else q.email_box_type
    )

    if email_box_type == "pop3":

        if q.email_box_ssl or settings.QUEUE_EMAIL_BOX_SSL:
            if not q.email_box_port:
                q.email_box_port = 995
            server = poplib.POP3_SSL(
                q.email_box_host or settings.QUEUE_EMAIL_BOX_HOST, int(q.email_box_port)
            )
        else:
            if not q.email_box_port:
                q.email_box_port = 110
            server = poplib.POP3(
                q.email_box_host or settings.QUEUE_EMAIL_BOX_HOST, int(q.email_box_port)
            )

        server.getwelcome()
        server.user(q.email_box_user or settings.QUEUE_EMAIL_BOX_USER)
        server.pass_(q.email_box_pass or settings.QUEUE_EMAIL_BOX_PASSWORD)

        messagesInfo = server.list()[1]

        for msg in messagesInfo:
            msgNum = msg.split(" ")[0]
            msgSize = msg.split(" ")[1]

            full_message = "\n".join(server.retr(msgNum)[1])
            ticket = ticket_from_message(message=full_message, queue=q, quiet=quiet)

            if ticket:
                server.dele(msgNum)

        server.quit()

    elif email_box_type == "imap":
        if q.email_box_ssl or settings.QUEUE_EMAIL_BOX_SSL:
            if not q.email_box_port:
                q.email_box_port = 993
            server = imaplib.IMAP4_SSL(
                q.email_box_host or settings.QUEUE_EMAIL_BOX_HOST, int(q.email_box_port)
            )
        else:
            if not q.email_box_port:
                q.email_box_port = 143
            server = imaplib.IMAP4(
                q.email_box_host or settings.QUEUE_EMAIL_BOX_HOST, int(q.email_box_port)
            )

        server.login(
            q.email_box_user or settings.QUEUE_EMAIL_BOX_USER,
            q.email_box_pass or settings.QUEUE_EMAIL_BOX_PASSWORD,
        )
        server.select(q.email_box_imap_folder)

        status, data = server.search(None, "NOT", "DELETED")
        if data:
            msgnums = data[0].split()
            for num in msgnums:
                status, data = server.fetch(num, "(RFC822)")
                ticket = ticket_from_message(message=data[0][1], queue=q, quiet=quiet)
                if ticket:
                    server.store(num, "+FLAGS", "\\Deleted")

        server.expunge()
        server.close()
        server.logout()


def decodeUnknown(charset, string):
    if not charset:
        try:
            return string.decode("utf-8", "ignore")
        except:
            return string.decode("iso8859-1", "ignore")
    return unicode(string, charset)


def decode_mail_headers(string):
    decoded = decode_header(string)
    return u" ".join([unicode(msg, charset or "utf-8") for msg, charset in decoded])


def ticket_from_message(message, queue, quiet):
    # 'message' must be an RFC822 formatted message.
    msg = message
    message = email.message_from_string(msg)
    subject = message.get("subject", _("Created from e-mail"))
    subject = decode_mail_headers(decodeUnknown(message.get_charset(), subject))
    subject = (
        subject.replace("Re: ", "")
        .replace("Fw: ", "")
        .replace("RE: ", "")
        .replace("FW: ", "")
        .replace("Automatic reply: ", "")
        .strip()
    )

    sender = message.get("from", _("Unknown Sender"))
    sender = decode_mail_headers(decodeUnknown(message.get_charset(), sender))

    sender_email = parseaddr(sender)[1]

    body_plain, body_html = "", ""

    for ignore in IgnoreEmail.objects.filter(Q(queues=queue) | Q(queues__isnull=True)):
        if ignore.test(sender_email):
            if ignore.keep_in_mailbox:
                # By returning 'False' the message will be kept in the mailbox,
                # and the 'True' will cause the message to be deleted.
                return False
            return True

    matchobj = re.match(r".*\[" + queue.slug + "-(?P<id>\d+)\]", subject)
    if matchobj:
        # This is a reply or forward.
        ticket = matchobj.group("id")
    else:
        ticket = None

    counter = 0
    files = []

    for part in message.walk():
        if part.get_content_maintype() == "multipart":
            continue

        name = part.get_param("name")
        if name:
            name = collapse_rfc2231_value(name)

        if part.get_content_maintype() == "text" and name == None:
            if part.get_content_subtype() == "plain":
                body_plain = EmailReplyParser.parse_reply(
                    decodeUnknown(
                        part.get_content_charset(), part.get_payload(decode=True)
                    )
                )
            else:
                body_html = part.get_payload(decode=True)
        else:
            if not name:
                ext = mimetypes.guess_extension(part.get_content_type())
                name = "part-%i%s" % (counter, ext)

            files.append(
                {
                    "filename": name,
                    "content": part.get_payload(decode=True),
                    "type": part.get_content_type(),
                },
            )

        counter += 1

    if body_plain:
        body = body_plain
    else:
        body = _(
            "No plain-text email body available. Please see attachment email_html_body.html."
        )

    if body_html:
        files.append(
            {
                "filename": _("email_html_body.html"),
                "content": body_html,
                "type": "text/html",
            }
        )

    now = timezone.now()

    if ticket:
        try:
            t = Ticket.objects.get(id=ticket)
            new = False
        except Ticket.DoesNotExist:
            ticket = None

    priority = 3

    smtp_priority = message.get("priority", "")
    smtp_importance = message.get("importance", "")

    high_priority_types = ("high", "important", "1", "urgent")

    if smtp_priority in high_priority_types or smtp_importance in high_priority_types:
        priority = 2

    if ticket == None:
        t = Ticket(
            title=subject,
            queue=queue,
            submitter_email=sender_email,
            created=now,
            description=body,
            priority=priority,
        )
        t.save()
        new = True
        update = ""

    elif t.status == Ticket.CLOSED_STATUS:
        t.status = Ticket.REOPENED_STATUS
        t.save()

    f = FollowUp(
        ticket=t,
        title=_(
            "E-Mail Received from %(sender_email)s" % {"sender_email": sender_email}
        ),
        date=timezone.now(),
        public=True,
        comment=body,
    )

    if t.status == Ticket.REOPENED_STATUS:
        f.new_status = Ticket.REOPENED_STATUS
        f.title = _(
            "Ticket Re-Opened by E-Mail Received from %(sender_email)s"
            % {"sender_email": sender_email}
        )

    f.save()

    if not quiet:
        print (
            " [%s-%s] %s"
            % (
                t.queue.slug,
                t.id,
                t.title,
            )
        ).encode("ascii", "replace")

    for file in files:
        if file["content"]:
            filename = file["filename"].encode("ascii", "replace").replace(" ", "_")
            filename = re.sub("[^a-zA-Z0-9._-]+", "", filename)
            a = Attachment(
                followup=f,
                filename=filename,
                mime_type=file["type"],
                size=len(file["content"]),
            )
            a.file.save(filename, ContentFile(file["content"]), save=False)
            a.save()
            if not quiet:
                print "    - %s" % filename

    context = safe_template_context(t)

    if new:

        if sender_email:
            send_templated_mail(
                "newticket_submitter",
                context,
                recipients=sender_email,
                sender=queue.from_address,
                fail_silently=True,
            )

        if queue.new_ticket_cc:
            send_templated_mail(
                "newticket_cc",
                context,
                recipients=queue.new_ticket_cc,
                sender=queue.from_address,
                fail_silently=True,
            )

        if queue.updated_ticket_cc and queue.updated_ticket_cc != queue.new_ticket_cc:
            send_templated_mail(
                "newticket_cc",
                context,
                recipients=queue.updated_ticket_cc,
                sender=queue.from_address,
                fail_silently=True,
            )

    else:
        context.update(comment=f.comment)

        if t.status == Ticket.REOPENED_STATUS:
            update = _(" (Reopened)")
        else:
            update = _(" (Updated)")

        if t.assigned_to:
            send_templated_mail(
                "updated_owner",
                context,
                recipients=t.assigned_to.email,
                sender=queue.from_address,
                fail_silently=True,
            )

        if queue.updated_ticket_cc:
            send_templated_mail(
                "updated_cc",
                context,
                recipients=queue.updated_ticket_cc,
                sender=queue.from_address,
                fail_silently=True,
            )

    return t


if __name__ == "__main__":
    process_email()
