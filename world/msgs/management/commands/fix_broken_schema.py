"""
During the python 2 to 3 conversion, I got this error a lot when I tried to do migrations:

django.db.utils.IntegrityError:
The row in table 'comms_msg_db_receivers_objects' with primary key '19035' has
an invalid foreign key: comms_msg_db_receivers_objects.msg_id contains a
value '198432' that does not have a corresponding value in comms_msg.id.

Basically, rows in join tables had invalid data - they should have been wiped
in CASCADE deletion when one of their FK references vanished, but didn't for
whatever reason. This command deletes them so migrations can run. Who knows
if the problem can recur, so I wanted a command in case it happens again.

Additionally, in the conversion of players_playerdb -> accounts_accountdb
tables, many foreignkeys were broken, but integrity errors weren't raised
until the newest version of django: specifying in django that they pointed
to the new table was enough to make them function properly. Now, however,
on any create/delete operation or attempting to run a migration, they'll
break. Since migrations can't fix it, this script has to do so.
"""
from django.core.management.base import BaseCommand
from django.db import connection


def fix_broken_msgs():
    from evennia.comms.models import Msg

    ReceiverObjects = Msg.db_receivers_objects.through
    ReceiverAccounts = Msg.db_receivers_accounts.through
    valid_ids = Msg.objects.values_list("id", flat=True)
    # get any Join table rows that don't have valid IDs
    querysets = [
        ReceiverObjects.objects.exclude(msg_id__in=valid_ids),
        ReceiverAccounts.objects.exclude(msg_id__in=valid_ids),
    ]
    for qs in querysets:
        ret = qs.delete()
        print("Deleted: ", ret)


def fix_missing_tables():
    """Adds inexplicably missing tables that Evennia migrations remove"""
    with connection.cursor() as cursor:
        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS comms_channeldb_db_subscriptions 
        (id integer PRIMARY KEY 
                       );
                       """
        )


def fix_broken_fks():
    """
    Fix broken foreign keys: find them in sqlite_master schema table, then do the
    standard sqlite switcheroo of creating a temp table (with fixed schema), copying
    shit over, dropping old table, making new table with old name (and fixed schema),
    copying shit over once more, drop temp table. Note these inserts aren't
    parameterized because it was causing syntax errors when django composed them and
    if we have sql injection in table names then I don't know what to tell you.
    """
    with connection.cursor() as cursor:
        # dump an unused table that would show up in the query
        cursor.execute("DROP TABLE IF EXISTS 'players_playerdb_db_liteattributes';")
        # get all the tables with broken foreignkeys
        cursor.execute(
            """
        SELECT tbl_name, sql FROM sqlite_master WHERE sql LIKE '%players_playerdb%';
        """
        )
        rows = cursor.fetchall()
        # disable foreign key integrity constraint checks so we can drop the tables
        cursor.execute("PRAGMA foreign_keys = OFF;")
        for name, sql in rows:
            print("Attempting to fix ", name)
            # replace the broken FK/fix schema
            sql = sql.replace("players_playerdb", "accounts_accountdb")

            # create temp table
            temp_name = name + "_temp"
            temp_sql = sql.replace(name, temp_name)
            cursor.execute(temp_sql)

            # copy data over to temp table
            insert = 'INSERT INTO "%s" SELECT * FROM "%s"' % (temp_name, name)
            cursor.execute(insert)

            # drop old table
            cursor.execute("DROP TABLE %s;" % name)

            # create old table with fixed schema
            cursor.execute(sql)

            # copy data to it from temp table
            insert = 'INSERT INTO "%s" SELECT * FROM "%s"' % (name, temp_name)
            cursor.execute(insert)

            # drop temp table
            cursor.execute("DROP TABLE %s;" % temp_name)
            print(name, " fixed.")
        cursor.execute("PRAGMA foreign_keys = ON;")
        # also change from WAL mode, write permission errors in new version
        cursor.execute("PRAGMA journal_mode = DELETE;")


class Command(BaseCommand):
    help = "Fix permissions for proxy models."

    def handle(self, *args, **options):
        fix_broken_msgs()
        fix_missing_tables()
        fix_broken_fks()
