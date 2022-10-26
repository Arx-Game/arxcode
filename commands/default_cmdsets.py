"""
Command sets

All commands in the game must be grouped in a cmdset.  A given command
can be part of any number of cmdsets and cmdsets can be added/removed
and merged onto entities at runtime.

To create new commands to populate the cmdset, see
`commands/command.py`.

This module wraps the default command sets of Evennia; overloads them
to add/remove commands from the default lineup. You can create your
own cmdsets by inheriting from them or directly from `evennia.CmdSet`.

"""
from functools import wraps

from evennia.commands.default import (
    cmdset_character,
    cmdset_account,
    cmdset_session,
    cmdset_unloggedin,
)

from commands.cmdsets import standard
from typeclasses.wearable import cmdset_wearable
from world.dominion import agent_commands


def check_errors(func):
    """
    Decorator for catching/printing out any errors in method calls. Designed for safer imports.
    Args:
        func: Function to decorate

    Returns:
        Wrapped function
    """
    # noinspection PyBroadException
    @wraps(func)
    def new_func(*args, **kwargs):
        """Wrapper around function with exception handling"""
        try:
            return func(*args, **kwargs)
        except Exception:
            import traceback

            traceback.print_exc()

    return new_func


class CharacterCmdSet(cmdset_character.CharacterCmdSet):
    """
    The `CharacterCmdSet` contains general in-game commands like `look`,
    `get`, etc available on in-game Character objects. It is merged with
    the `PlayerCmdSet` when a Player puppets a Character.
    """

    key = "DefaultCharacter"
    priority = 101

    def at_cmdset_creation(self):
        """
        Populates the cmdset
        """
        # super(CharacterCmdSet, self).at_cmdset_creation()
        #
        # any commands you add below will overload the default ones.
        #
        self.add_standard_cmdsets()
        self.add_other_cmdsets()

    @check_errors
    def add_standard_cmdsets(self):
        """Add different command sets that all characters should have"""
        self.add(standard.StateIndependentCmdSet)
        self.add(standard.MobileCmdSet)
        self.add(standard.OOCCmdSet)
        self.add(standard.StaffCmdSet)

    @check_errors
    def add_other_cmdsets(self):
        """Miscellaneous command sets"""
        self.add(cmdset_wearable.WearCmdSet)


class AccountCmdSet(cmdset_account.AccountCmdSet):
    """
    This is the cmdset available to the Player at all times. It is
    combined with the `CharacterCmdSet` when the Player puppets a
    Character. It holds game-account-specific commands, channel
    commands, etc.
    """

    key = "DefaultPlayer"
    priority = 101

    def at_cmdset_creation(self):
        """
        Populates the cmdset
        """
        self.add_default_commands()
        self.add_overridden_commands()
        self.add_general_commands()
        self.add_bboard_commands()
        self.add_roster_commands()
        self.add_jobs_commands()
        self.add_dominion_commands()
        self.add_social_commands()
        self.add_staff_commands()
        self.add_investigation_commands()
        self.add_scene_commands()
        self.add_gming_actions_commands()
        self.add_lore_commands()

    @check_errors
    def add_default_commands(self):
        """Add selected Evennia built-in commands"""
        from evennia.commands.default import account, building, system, admin, comms
        from commands.base_commands import overrides

        # Player-specific commands
        self.add(account.CmdOOCLook())
        self.add(account.CmdIC())
        self.add(overrides.CmdArxOOC())
        self.add(account.CmdOption())
        self.add(account.CmdQuit())
        self.add(account.CmdPassword())
        self.add(account.CmdColorTest())
        self.add(account.CmdQuell())
        self.add(building.CmdExamine())
        # system commands
        self.add(system.CmdReset())
        self.add(system.CmdShutdown())
        self.add(system.CmdPy())
        self.add(system.CmdAccounts())
        self.add(system.CmdAbout())
        # Admin commands
        self.add(admin.CmdNewPassword())
        # Comm commands
        self.add(comms.CmdAddCom())
        self.add(comms.CmdDelCom())
        self.add(comms.CmdCemit())
        self.add(comms.CmdIRC2Chan())
        self.add(comms.CmdRSS2Chan())

    @check_errors
    def add_overridden_commands(self):
        """Add arx overrides of Evennia commands"""
        from commands.base_commands import help, overrides

        self.add(help.CmdHelp())
        self.add(overrides.CmdWho())
        self.add(overrides.CmdArxSetAttribute())
        self.add(overrides.CmdArxCdestroy())
        self.add(overrides.CmdArxChannelCreate())
        self.add(overrides.CmdArxClock())
        self.add(overrides.CmdArxCBoot())
        self.add(overrides.CmdArxCdesc())
        self.add(overrides.CmdArxAllCom())
        self.add(overrides.CmdArxChannels())
        self.add(overrides.CmdArxCWho())
        self.add(overrides.CmdArxReload())

    @check_errors
    def add_general_commands(self):
        """Add general/misc commands"""
        from commands.base_commands import general

        self.add(general.CmdPage())
        self.add(general.CmdMail())
        self.add(general.CmdGradient())
        self.add(general.CmdInform())
        self.add(general.CmdGameSettings())

    @check_errors
    def add_bboard_commands(self):
        """Add commands for bulletin boards"""
        from commands.base_commands import bboards

        self.add(bboards.CmdBBReadOrPost())
        self.add(bboards.CmdBBSub())
        self.add(bboards.CmdBBUnsub())
        self.add(bboards.CmdBBCreate())
        self.add(bboards.CmdBBNew())
        self.add(bboards.CmdOrgStance())

    @check_errors
    def add_roster_commands(self):
        """Add commands around roster viewing or management"""
        from commands.base_commands import roster

        self.add(roster.CmdRosterList())
        self.add(roster.CmdAdminRoster())
        self.add(roster.CmdSheet())
        self.add(roster.CmdRelationship())
        self.add(roster.CmdDelComment())
        self.add(roster.CmdAdmRelationship())

    @check_errors
    def add_jobs_commands(self):
        """Add commands for interacting with helpdesk"""
        from commands.base_commands import jobs

        self.add(jobs.CmdJob())
        self.add(jobs.CmdRequest())
        self.add(jobs.CmdApp())

    @check_errors
    def add_dominion_commands(self):
        """Add commands related to Dominion, the offscreen estate-management game"""
        from world.dominion import general_dominion_commands as domcommands

        self.add(domcommands.CmdAdmDomain())
        self.add(domcommands.CmdAdmArmy())
        self.add(domcommands.CmdAdmCastle())
        self.add(domcommands.CmdAdmAssets())
        self.add(domcommands.CmdAdmFamily())
        self.add(domcommands.CmdAdmOrganization())
        self.add(domcommands.CmdDomain())
        self.add(domcommands.CmdFamily())
        self.add(domcommands.CmdOrganization())
        self.add(domcommands.CmdArmy())
        self.add(agent_commands.CmdAgents())
        self.add(domcommands.CmdPatronage())
        self.add(agent_commands.CmdRetainers())

    @check_errors
    def add_social_commands(self):
        """Add commands for social RP"""
        from commands.base_commands import social

        self.add(social.CmdFinger())
        self.add(social.CmdWatch())
        self.add(social.CmdCalendar())
        self.add(social.CmdAFK())
        self.add(social.CmdWhere())
        self.add(social.CmdCensus())
        self.add(social.CmdIAmHelping())
        self.add(social.CmdRPHooks())

    @check_errors
    def add_staff_commands(self):
        """Add commands for staff players"""
        from commands.base_commands import staff_commands

        # more recently implemented staff commands
        self.add(staff_commands.CmdRestore())
        self.add(staff_commands.CmdSendVision())
        self.add(staff_commands.CmdAskStaff())
        self.add(staff_commands.CmdListStaff())
        self.add(staff_commands.CmdPurgeJunk())
        self.add(staff_commands.CmdAdjustReputation())
        self.add(staff_commands.CmdViewLog())
        self.add(staff_commands.CmdSetLanguages())
        self.add(staff_commands.CmdGMNotes())
        self.add(staff_commands.CmdJournalAdminForDummies())
        self.add(staff_commands.CmdTransferKeys())
        self.add(staff_commands.CmdAdminTitles())
        self.add(staff_commands.CmdAdminWrit())
        self.add(staff_commands.CmdAdminBreak())
        self.add(staff_commands.CmdSetServerConfig())
        from commands.cmdsets import starting_gear

        self.add(starting_gear.CmdSetupGear())
        from world.fashion import fashion_commands

        self.add(fashion_commands.CmdAdminFashion())
        from web.character import file_commands

        self.add(file_commands.CmdAdminFile)

    @check_errors
    def add_investigation_commands(self):
        """Add commands based on investigations/clus"""
        from web.character import investigation

        self.add(investigation.CmdAdminInvestigations())
        self.add(investigation.CmdListClues())
        self.add(investigation.CmdTheories())
        self.add(investigation.CmdListRevelations())
        self.add(investigation.CmdPRPClue())
        self.add(investigation.CmdPRPRevelation())

    @check_errors
    def add_scene_commands(self):
        """Commands for flashbacks"""
        from web.character import scene_commands

        self.add(scene_commands.CmdFlashback())

    @check_errors
    def add_gming_actions_commands(self):
        """Add commands for interacting with crises and GMing"""
        from world.dominion import crisis_commands

        self.add(crisis_commands.CmdViewCrisis())
        self.add(crisis_commands.CmdGMCrisis())
        from commands.base_commands import story_actions

        self.add(story_actions.CmdGMAction)

    @check_errors
    def add_lore_commands(self):
        """Add commands for using lore knowledge base"""
        from web.helpdesk import lore_commands

        self.add(lore_commands.CmdLoreSearch())


class UnloggedinCmdSet(cmdset_unloggedin.UnloggedinCmdSet):
    """
    Command set available to the Session before being logged in.  This
    holds commands like creating a new account, logging in, etc.
    """

    key = "DefaultUnloggedin"

    def at_cmdset_creation(self):
        """
        Populates the cmdset
        """
        # super(UnloggedinCmdSet, self).at_cmdset_creation()
        #
        # any commands you add below will overload the default ones.
        #

        try:
            from evennia.commands.default import unloggedin as default_unloggedin

            self.add(default_unloggedin.CmdUnconnectedConnect())
            self.add(default_unloggedin.CmdUnconnectedQuit())
            self.add(default_unloggedin.CmdUnconnectedLook())
            self.add(default_unloggedin.CmdUnconnectedEncoding())
            self.add(default_unloggedin.CmdUnconnectedScreenreader())
            from commands.base_commands import unloggedin

            self.add(unloggedin.CmdGuestConnect())
            self.add(unloggedin.CmdUnconnectedHelp())
        except Exception as err:
            print("<<ERROR>>: Error encountered in loading Unlogged cmdset: %s" % err)


class SessionCmdSet(cmdset_session.SessionCmdSet):
    """
    This cmdset is made available on Session level once logged in. It
    is empty by default.
    """

    key = "DefaultSession"

    def at_cmdset_creation(self):
        """
        This is the only method defined in a cmdset, called during
        its creation. It should populate the set with command instances.

        As and example we just add the empty base `Command` object.
        It prints some info.
        """
        super(SessionCmdSet, self).at_cmdset_creation()
        #
        # any commands you add below will overload the default ones.
        #
