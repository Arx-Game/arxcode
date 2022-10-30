from django.core.management.base import BaseCommand
from django.conf import settings
import subprocess


class Command(BaseCommand):
    """
    This implements backing up our database.

    Usage:
        evennia backup_db
    """
    default_name = "evennia_backup.db3"

    def add_arguments(self, parser):
        parser.add_argument('--db_name', type=str)

    def handle(self, *args, **options):
        if options["db_name"]:
            backup_name = options["db_name"]
        else:
            backup_name = self.default_name
        self.create_sqlite_backup(backup_name)

    def create_sqlite_backup(self, backup_name=""):
        """Runs sqlite3 backup command.

        Copying a sqlite database while it's under use will cause it to become
        malformed: to safely copy it, we need to use the sqlite '.backup' command.
        This requires that the sqlite3 utility is installed.

        Command that's run in a subprocess:
         Ex: sqlite3 evennia.db3 ".backup 'emergency_backup.db3'"
        """
        backup_name = backup_name or self.default_name
        sqlite_cmd = f".backup '{backup_name}'"
        db_name = settings.DATABASES["default"]["NAME"]
        self.stdout.write(f"Copying database {db_name} to {backup_name}.")
        subprocess.run(["sqlite3", db_name, f'{sqlite_cmd}'], shell=True)
        self.stdout.write("Copy complete.")
