"""
Script for characters healing.
"""

from .scripts import Script


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
        self.interval = 28800
        self.persistent = True
        self.start_delay = True
        self.db.highest_heal = 0

    def at_repeat(self):
        """
        Called every 8 hours until we're all better.
        """
        # slowly reduce the impact of the highest heal we've gotten
        self.db.highest_heal = (self.db.highest_heal or 0)/2
        if not self.obj:
            self.stop()
            return
        # RIP in pepperinos
        try:
            if self.obj.dead:
                self.stop()
                return
        except AttributeError:
            self.stop()
            return
        if self.obj.db.damage and self.obj.db.damage > 0:
            self.obj.recovery_test(diff_mod=15 - self.db.highest_heal)
        else:
            self.stop()

    def is_valid(self):
        try:
            if self.obj and self.obj.db.damage > 0:
                return True
        except (AttributeError, TypeError, ValueError):
            return False
        return False
        
    def attempt_heal(self, amt=0, healer=None):
        """
        Attempt to heal the character. If amt is less than the current max heal
        amount, then it does nothing. If it's greater, then we use the difference
        between the new high and previous to either give them a recovery test or
        just heal them straight up by that value.
        
            Args:
                amt (int): Heal amount
                healer (ObjectDB): Healing character
        """
        from datetime import datetime, timedelta
        max_heal = self.db.highest_heal or 0
        if amt < max_heal:
            if healer:
                healer.msg("They have received better care already. You can't help them.")
                self.obj.msg("You have received better care already. %s isn't able to help you." % healer)
            return
        # get difference, record new high
        diff = amt - self.db.highest_heal
        self.db.highest_heal = amt
        # check our heal time to see if we can do another recovery test
        last_healed = self.db.last_healed
        if last_healed and last_healed > (datetime.now() - timedelta(hours=8)):
            # not enough time has passed so we'll just increase their health by the difference
            if healer:
                healer.msg("They have been healed recently, but you're able to improve them somewhat.")
            self.obj.change_health(diff)
            return
        # enough time has passed, so we give them a full recovery test
        self.db.last_healed = datetime.now()
        self.obj.recovery_test(diff_mod=-diff)
