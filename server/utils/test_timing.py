"""
Comparison of timing between one large query with iterative checks versus a
number of smaller queries against a non-indexed field. May add other timings
when needed for different tests.
"""

from timeit import Timer
from evennia.comms.models import Msg


def all_at_once():
    qs = list(Msg.objects.all())
    print("len of qs is %s" % len(qs))
    white = [ob for ob in qs if ob and ob.db_header and "white_journal" in ob.db_header]
    print("len of white is %s" % len(white))
    black = [ob for ob in qs if ob and ob.db_header and "black_journal" in ob.db_header]
    print("len of black is %s" % len(black))
    relationship = [
        ob for ob in qs if ob and ob.db_header and "relationship" in ob.db_header
    ]
    print("len of relationship is %s" % len(relationship))
    messenger = [ob for ob in qs if ob and ob.db_header and "messenger" in ob.db_header]
    print("len of messenger is %s" % len(messenger))


def by_filtering():
    qs = Msg.objects.all()
    white = list(qs.filter(db_header__icontains="white_journal"))
    print("len of white is %s" % len(white))
    black = list(qs.filter(db_header__icontains="black_journal"))
    print("len of black is %s" % len(black))
    relationship = list(qs.filter(db_header__icontains="relationship"))
    print("len of relationship is %s" % len(relationship))
    messenger = list(qs.filter(db_header__icontains="messenger"))
    print("len of messenger is %s" % len(messenger))


def time_all_at_once():
    t = Timer("all_at_once()", "from world.msgs.test_timing import all_at_once")
    print("Time is %s" % t.timeit(number=1))


def time_filters():
    t = Timer("by_filtering()", "from world.msgs.test_timing import by_filtering")
    print("Time is %s" % t.timeit(number=1))
