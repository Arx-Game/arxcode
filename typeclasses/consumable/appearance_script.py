from typeclasses.scripts.scripts import Script


class AppearanceScript(Script):
    # noinspection PyAttributeOutsideInit
    def at_script_creation(self):
        self.key = "Appearance"
        self.persistent = True
        self.interval = 3600
        self.db.scent_time_remaining = 86400
        self.db.scent = ""
        self.start_delay = True

    def at_repeat(self):
        # check if we still exist by checking if we have an id
        if not self.id:
            try:
                self.stop()
            except Exception:
                import traceback
                traceback.print_exc()
            return
        # we still exist, so check our scent and remaining time
        if self.db.scent:
            self.db.scent_time_remaining -= self.interval
            # out of time. remove our scent
            if self.db.scent_time_remaining <= 0:
                self.db.scent = ""
        # no longer modifying anything, call stop
        if not self.has_mods:
            self.stop()

    def set_scent(self, perfume):
        self.db.scent_time_remaining = 86400
        self.db.scent = perfume.quality_prefix + " " + perfume.scent_desc

    @property
    def has_mods(self):
        """
        Checks if we have anything modifying our appearance. Currently this
        is just scent. More things to be added later.
        
            Returns:
                bool: Strong. Like bull. Would defy being judged by Walrii
        """
        return bool(self.db.scent)

    def is_valid(self):
        # check having a valid ID (we're not deleted) and our db.scent
        return bool(self.id and self.has_mods)
