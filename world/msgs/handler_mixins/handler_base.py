"""
Base class for the different handlers
"""


class MsgHandlerBase(object):
    def __init__(self, obj=None):
        """
        We'll be doing a series of delayed calls to set up the various
        attributes in the MessageHandler, since we can't have ObjectDB
        refer to Msg during the loading-up process.
        """
        # the ObjectDB instance
        self.obj = obj

    @staticmethod
    def parse_header(msg):
        return msg.parse_header()

    @staticmethod
    def get_date_from_header(msg):
        # type: (msg) -> Msg
        header = MsgHandlerBase.parse_header(msg)
        return header.get('date', None)

    def get_sender_name(self, msg):
        return msg.get_sender_name(self.obj)

    @staticmethod
    def create_date_header(icdate):
        return "date:%s" % icdate

    @staticmethod
    def get_event(msg):
        return msg.event

    def msg(self, *args, **kwargs):
        self.obj.msg(*args, **kwargs)

    def disp_entry(self, entry):
        date = self.get_date_from_header(entry)
        msg = "{wDate:{n %s\n" % date
        event = self.get_event(entry)
        if event:
            msg += "{wEvent:{n %s\n" % event.name
        msg += "{wOOC Date:{n %s\n\n" % entry.db_date_created.strftime("%x %X")
        msg += entry.db_message
        try:
            ob = self.obj.player_ob
            # don't bother to mark player receivers for a messenger
            if ob not in entry.receivers and "messenger" not in entry.tags.all():
                entry.receivers = ob
        except (AttributeError, TypeError):
            pass
        return msg
