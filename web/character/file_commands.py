from .models import PlayerAccount, PlayerInfoEntry, PlayerSiteEntry, RosterEntry, AccountHistory
from commands.base import ArxCommand
from datetime import date


class CmdAdminFile(ArxCommand):
    """
    Manages a user's admin file.

    Usage:
      @file <character|email>[/entry]
      @file/search <character>
      @file/sitesearch <string>
      @file/add <character|email>[/type]=<text>

    This command accesses a given player account's overall file, for easy reference of
    all past data we've entered about them; past rulings, decisions, and suchnot.
    """
    key = "@file"
    locks = "cmd:perm(Admins)"

    @staticmethod
    def account_for_string(accountstring):
        # First we check if this is an email with an exact match
        try:
            account = PlayerAccount.objects.get(email__iexact=accountstring)
            return account
        except (PlayerAccount.DoesNotExist, PlayerAccount.MultipleObjectsReturned):
            pass

        try:
            character = RosterEntry.objects.get(character__db_key__iexact=accountstring)
            return character.current_account
        except(RosterEntry.DoesNotExist, RosterEntry.MultipleObjectsReturned):
            pass

        return None

    @staticmethod
    def past_accounts_for_character(accountstring):

        try:
            character = RosterEntry.objects.get(character__db_key__iexact=accountstring)
            result = list(character.previous_accounts.distinct().all())
            if character.current_account and character.current_account not in result:
                result.append(character.current_account)
            return result
        except(RosterEntry.DoesNotExist, RosterEntry.MultipleObjectsReturned):
            pass

        return None

    def func(self):

        if not self.switches:
            if not self.args:
                self.msg("You must provide a character name or email address!")
                return

            arglist = self.args.split("/")
            accountstring = arglist[0]

            entry_num = None
            if len(arglist) > 1:
                try:
                    entry_num = int(arglist[1])
                except ValueError:
                    self.msg("You need to provide an integer for an entry number!")
                    return

            account = self.account_for_string(accountstring)
            if not account:
                self.msg("No email address or currently-played character matched {}".format(accountstring))
                return

            self.msg("|/|wInformation for {}:|n".format(account.email))

            sites = PlayerSiteEntry.objects.filter(account=account).distinct().order_by('last_seen')
            addresses = [site.address for site in sites]
            addresses = ", ".join(addresses)

            self.msg("  Known Addresses: {}".format(addresses))

            history = AccountHistory.objects.filter(account=account).order_by('start_date')
            alts = []
            for entry in history:
                result = entry.entry.character.key
                if entry.entry.current_account != account \
                        or entry.entry.roster.name not in ["Active", "Unavailable"]:
                    result = "ex-" + result
                alts.append(result)
            alts = set(alts)
            alts = ", ".join(alts)

            self.msg("  Has played: {}". format(alts))
            self.msg("-------------")

            entries = PlayerInfoEntry.objects.filter(account=account).order_by('entry_date').distinct()
            counter = 1
            for entry in entries:
                if entry_num is not None and entry_num == counter:
                    self.msg("|wEntry #{}: on {} - {} by {}|n".format(counter, entry.entry_date.strftime("%Y/%m/%d"),
                                                                      entry.type_name,
                                                                      entry.author.key.capitalize() if entry.author
                                                                      else "Unknown"))
                    self.msg("{}|/".format(entry.text))
                    return
                elif entry_num is None:
                    self.msg("{}: {} - {} by {}".format(counter, entry.entry_date.strftime("%Y/%m/%d"), entry.type_name,
                                                        entry.author.key.capitalize() if entry.author else "Unknown"))
                counter += 1

            if entry_num is not None:
                self.msg("Could not find entry number {}!".format(entry_num))

            return

        elif "add" in self.switches:

            arglist = self.lhs.split("/")
            if len(arglist) != 2:
                self.msg("You must provide both an accountstring and an entry type.  Valid entry types are {}"
                         .format(", ".join(PlayerInfoEntry.valid_types())))
                return

            if not self.rhs or len(self.rhs) == 0:
                self.msg("You must provide text for the entry!")
                return

            accountstring = arglist[0]
            entry_type = PlayerInfoEntry.type_for_name(arglist[1])
            if entry_type is None:
                self.msg("You must provide both an accountstring and an entry type.  Valid entry types are {}"
                         .format(", ".join(PlayerInfoEntry.valid_types())))
                return

            account = self.account_for_string(accountstring)
            if not account:
                self.msg("Unable to find a player record matching '{}'!".format(accountstring))
                return

            entry = PlayerInfoEntry(account=account, entry_type=entry_type, entry_date=date.today(), author=self.account)
            entry.text = self.rhs
            entry.save()

            self.msg("{} entry added.".format(entry.type_name))
            return

        elif "search" in self.switches:
            if not self.args:
                self.msg("You must provide a character to search for!")
                return

            results = self.past_accounts_for_character(self.args)
            if not results or len(results) == 0:
                self.msg("Unable to find any past players for a character named '{}'!".format(self.args))
                return

            self.msg("|w{}|n has been played by:".format(self.args))
            for account in results:
                string = "  |w{}|n: ".format(account.email)
                entries = AccountHistory.objects.filter(account=account, entry__character__db_key__iexact=self.args).order_by('start_date')
                played_periods = []
                for entry in entries:
                    if not entry.start_date:
                        played_string = "from ??? to "
                    else:
                        played_string = "from {} to ".format(entry.start_date.strftime("%Y/%m/%d"))
                    if not entry.end_date:
                        played_string += "now"
                    else:
                        played_string += entry.end_date.strftime("%Y/%m/%d")
                    played_periods.append(played_string)
                string += ", ".join(played_periods)
                self.msg(string)

            return

        elif "sitesearch" in self.switches:

            if not self.args:
                self.msg("You must provide a string to look for in the sites!")
                return

            entries = PlayerSiteEntry.objects.filter(address__icontains=self.args)
            if entries.count() == 0:
                self.msg("No files have sites matching {}!".format(self.args))
                return

            self.msg("")
            account_entries = {}
            for entry in entries:
                account = entry.account
                sites = account_entries[account.email] if account.email in account_entries else []
                sites.append(entry.address)
                account_entries[account.email] = sites

            for email, sites in account_entries.items():
                self.msg("|w{}|n has connected from: {}".format(email, ", ".join(sites)))

            return

        self.msg("Unknown command.")
