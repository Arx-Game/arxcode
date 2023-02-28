"""
Script for characters healing.
"""

from typeclasses.scripts.scripts import Script
from server.utils.arx_utils import CachedProperty
from datetime import datetime


class Recovery(Script):
    """
    This script repeatedly saves server times so
    it can be retrieved after server downtime.
    """

    # noinspection PyAttributeOutsideInit
    def at_script_creation(self):
        """
        Setup the script
        """
        self.key = "Recovery"
        self.desc = "Healing over time"
        self.interval = 60
        self.persistent = True
        self.start_delay = True

    @CachedProperty
    def runner(self):
        try:
            return self.recovery_runner
        except AttributeError:
            from world.conditions.models import RecoveryRunner

            return RecoveryRunner.objects.create(script=self)

    def at_repeat(self):
        """
        Called every 8 hours until we're all better.
        """
        if self.recovery_checks_due:
            self.runner.run_recovery_checks()
        if self.revive_checks_due:
            self.runner.run_revive_checks()

    @property
    def recovery_checks_due(self):
        return self.check_timer("recovery")

    @property
    def revive_checks_due(self):
        return self.check_timer("revive")

    def check_timer(self, attribute):
        """Checks the timer for fields that store the last run timestamp in a field
        called <name>_last_run, with a specified interval in seconds stored in a field
        called <name>_interval.
        """
        last = getattr(self.runner, f"{attribute}_last_run")
        if not last:
            return True
        now = datetime.now()
        return (now - last).total_seconds() >= getattr(
            self.runner, f"{attribute}_interval"
        )
