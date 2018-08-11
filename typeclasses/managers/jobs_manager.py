"""
Manager for staff jobs
"""

from typeclasses.objects import Object
from datetime import datetime


class JobsManager(Object):
    """
    Class to store and manage the roster
    """           

    def at_object_creation(self):
        """
        Run at RosterManager creation.
        """
        self.db.closed_list = []
        self.db.open_list = []
        self.db.jobs_manager = True
        self.db.num_tickets = 0
        self.at_init()

    def close_ticket(self, ticket_num, caller, gm_notes):
        """
        Mark open ticket as closed.
        ticket = [ticket_id, playob, request_string, date_submit, gm_ob, gm_notes, date_answer]
        """
        myticket = None
        curr_index = 0
        list_copy = self.db.open_list[:]
        for ticket in self.db.open_list:
            #You might be wondering why we're using a counter here. That's a very good question
            #The answer is that something causes list.remove(value) to always fail when passed
            #a reference to value. I assume it's due to automatic pickling/serialization of
            #values. In any case, the only way to reliably remove a serialized object from a
            #list is to save the index it was stored at and then pop that index.
            if ticket[0] == ticket_num:
                myticket = ticket
                del list_copy[curr_index]
                break
            curr_index += 1
        # It is necessary to delete the old attribute before reassigning it,
        # otherwise the caching prevents variable assignment. It'll pop back up
        # even after assignment, totally unaltered, like a horror movie villain.
        del self.db.open_list
        self.db.open_list = list_copy
        # did not find a match
        if not myticket:
            return False
        #found a match, now we add info then put it in closed
        myticket[4] = caller
        myticket[5] = gm_notes
        myticket[6] = datetime.today().strftime("%x %X")
        self.db.closed_list.append(myticket)
        self.save()
        responsemsg = "{wIn response to your request of:{n\n%s{w\n%s wrote:{n\n%s" % (myticket[2], caller.key.capitalize(), gm_notes)
        caller.execute_cmd("@mail/quick %s/Response to request=%s" % (myticket[1].key, responsemsg))
        return True

    def new_ticket(self, caller, request, optional_title=None):
        """
        Create a new ticket.
        """
        if not caller or not request:
            return False
        self.db.num_tickets += 1
        ticket_id = self.db.num_tickets
        date = datetime.today().strftime("%x %X")
        ticket = [ticket_id, caller, request, date, None, "None", "None", optional_title]
        self.db.open_list.append(ticket)
        return True

    def get_closed_ticket(self, ticket_num):
        """
        returns a closed ticket
        ticket = [ticket_id, playob, request_string, date_submit, gm_ob, gm_notes, date_answer, optional_title]
        """
        for ticket in self.db.closed_list:
            if ticket[0] == ticket_num:
                return ticket
        pass
    

    def get_open_ticket(self, ticket_num):
        """
        returns an open ticket
        ticket = [ticket_id, playob, request_string, date_submit, gm_ob, gm_notes, date_answer, optional_title]
        """
        for ticket in self.db.open_list:
            if ticket[0] == ticket_num:
                return ticket
        pass

    def get_open_list(self):
        """
        all open tickets
        """
        return self.db.open_list

    def get_closed_list(self):
        """
        all closed tickets
        """
        return self.db.closed_list

    def is_jobs_manager(self):
        """
        Identifier method. All managers from object typeclass
        will have some version of this for object searches.
        """
        return True
