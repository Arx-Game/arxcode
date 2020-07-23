"""
Basic starting cmdsets for characters. Each of these
cmdsets attempts to represent some aspect of how
characters function, so that different conditions
on characters can extend/modify/remove functionality
from them without explicitly calling individual commands.

"""
import traceback

from commands.base_commands import exchanges

try:
    from evennia.commands.default import help, admin, system, building, batchprocess
except Exception as err:
    traceback.print_exc()
    print("<<ERROR>>: Error encountered in loading default commands: %s" % err)
try:
    from evennia.commands.default import general as default_general
except Exception as err:
    traceback.print_exc()
    print("<<ERROR>>: Error encountered in loading default.general commands: %s" % err)
try:
    from commands.base_commands import staff_commands
except Exception as err:
    traceback.print_exc()
    print("<<ERROR>>: Error encountered in loading staff_commands: %s" % err)
try:
    from commands.base_commands import roster
except Exception as err:
    traceback.print_exc()
    print("<<ERROR>>: Error encountered in loading roster commands: %s" % err)
try:
    from commands.base_commands import general
except Exception as err:
    traceback.print_exc()
    print("<<ERROR>>: Error encountered in loading general commands: %s" % err)
try:
    from typeclasses import rooms as extended_room
except Exception as err:
    traceback.print_exc()
    print("<<ERROR>>: Error encountered in loading extended_room: %s" % err)
try:
    from commands.base_commands import social
except Exception as err:
    traceback.print_exc()
    print("<<ERROR>>: Error encountered in loading social commands: %s" % err)
try:
    from commands.base_commands import xp
except Exception as err:
    traceback.print_exc()
    print("<<ERROR>>: Error encountered in loading xp commands: %s" % err)
try:
    from commands.base_commands import maps
except Exception as err:
    traceback.print_exc()
    print("<<ERROR>>: Error encountered in loading maps commands: %s" % err)
try:
    from typeclasses.places import cmdset_places
except Exception as err:
    traceback.print_exc()
    print("<<ERROR>>: Error encountered in loading places commands: %s" % err)
try:
    from commands.cmdsets import combat
except Exception as err:
    traceback.print_exc()
    print("<<ERROR>>: Error encountered in loading combat commands: %s" % err)
try:
    from world.dominion import general_dominion_commands as domcommands
except Exception as err:
    traceback.print_exc()
    print("<<ERROR>>: Error encountered in loading dominion commands: %s" % err)
try:
    from world.dominion import agent_commands
except Exception as err:
    traceback.print_exc()
    print("<<ERROR>>: Error encountered in loading agent commands: %s" % err)
try:
    from commands.base_commands import crafting
except Exception as err:
    traceback.print_exc()
    print("<<ERROR>>: Error encountered in loading crafting commands: %s" % err)
try:
    from commands.cmdsets import home
except Exception as err:
    traceback.print_exc()
    print("<<ERROR>>: Error encountered in loading home commands: %s" % err)
try:
    from web.character import investigation
except Exception as err:
    traceback.print_exc()
    print("<<ERROR>>: Error encountered in loading investigation commands: %s" % err)
try:
    from commands.base_commands import overrides
except Exception as err:
    traceback.print_exc()
    print("<<ERROR>>: Error encountered in override commands: %s" % err)
try:
    from typeclasses.consumable.use_commands import CmdApplyConsumable
except Exception as err:
    traceback.print_exc()
    print("<<ERROR>>: Error encountered in consumable commands: %s" % err)
try:
    from typeclasses.gambling import cmdset_gambling as gambling
except Exception as err:
    traceback.print_exc()
    print("<<ERROR>>: Error encountered in gambling commands: %s" % err)
try:
    from commands.base_commands import rolling
except Exception as err:
    traceback.print_exc()
    print("<<ERROR>>: Error encountered in roll commands: %s" % err)
try:
    from commands.base_commands import story_actions
except Exception as err:
    traceback.print_exc()
    print("<<ERROR>>: Error encountered in storyaction commands: %s" % err)
try:
    from world.conditions import condition_commands
except Exception as err:
    traceback.print_exc()
    print("<<ERROR>>: Error encountered in condition commands: %s" % err)
try:
    from world.fashion import fashion_commands
except Exception as err:
    traceback.print_exc()
    print("<<ERROR>>: Error encountered in fashion commands: %s" % err)
try:
    from world.petitions import petitions_commands
except Exception as err:
    traceback.print_exc()
    print("<<ERROR>>: Error encountered in petition commands: %s" % err)
try:
    from typeclasses.containers.container import CmdRoot
except Exception as err:
    print("<<ERROR>>: Error encountered in container commands: %s" % err)
try:
    from world.weather import weather_commands
except Exception as err:
    print("<<ERROR>>: Error encountered in weather commands: %s" % err)
try:
    from world.templates.template_commands import CmdTemplateForm
except Exception as err:
    print("<<ERROR>>: Error encountered in container commands: %s" % err)
try:
    from world.exploration import exploration_commands
except Exception as err:
    print("<<ERROR>>: Error encountered in exploration commands: %s" % err)
try:
    from world.dominion.plots import plot_commands
except Exception as err:
    print("<<ERROR>>: Error encountered in plot commands: %s" % err)
try:
    from web.character import goal_commands
except Exception as err:
    print("<<ERROR>>: Error encountered in goal commands: %s" % err)
try:
    from world.magic import magic_commands
except Exception as err:
    print("<<ERROR>>: Error encountered in magic commands: %s" % err)

from evennia.commands.cmdset import CmdSet


class OOCCmdSet(CmdSet):
    """Character-specific OOC commands. Most OOC commands defined in player."""
    key = "OOCCmdSet"

    def at_cmdset_creation(self):
        """
        This is the only method defined in a cmdset, called during
        its creation. It should populate the set with command instances.

        Note that it can also take other cmdsets as arguments, which will
        be used by the character default cmdset to add all of these onto
        the internal cmdset stack. They will then be able to removed or
        replaced as needed.
        """
        self.add(overrides.CmdInventory())
        self.add(default_general.CmdNick())
        self.add(default_general.CmdAccess())
        self.add(rolling.CmdDiceString())
        self.add(rolling.CmdDiceCheck())
        self.add(rolling.CmdSpoofCheck())
        self.add(general.CmdBriefMode())
        self.add(general.CmdTidyUp())
        self.add(extended_room.CmdGameTime())
        self.add(extended_room.CmdSetGameTimescale())
        self.add(extended_room.CmdStudyRawAnsi())
        self.add(xp.CmdVoteXP())
        self.add(social.CmdPosebreak())
        self.add(social.CmdSocialNotable())
        self.add(social.CmdSocialNominate())
        self.add(social.CmdSocialReview())
        # self.add(social.CmdFavor())
        self.add(overrides.SystemNoMatch())
        self.add(weather_commands.CmdAdminWeather())
        self.add(roster.CmdPropriety())

        # Exploration!
        self.add(exploration_commands.CmdExplorationCmdSet())


class StateIndependentCmdSet(CmdSet):
    """
    Character commands that will always exist, regardless of character state.
    Poses and emits, for example, should be allowed even when a character is
    dead, because they might be posing something about the corpse, etc.
    """
    key = "StateIndependentCmdSet"

    def at_cmdset_creation(self):
        self.add(overrides.CmdPose())
        # emit was originally an admin command. Replaced those with gemit
        self.add(overrides.CmdEmit())
        self.add(overrides.CmdArxTime())
        self.add(general.CmdOOCSay())
        self.add(general.CmdDirections())
        self.add(general.CmdKeyring())
        self.add(general.CmdGlance())
        # sorta IC commands, since information is interpretted by the
        # character and may not be strictly accurate.
        self.add(extended_room.CmdExtendedLook())
        self.add(roster.CmdHere())
        self.add(social.CmdHangouts())
        self.add(social.CmdWhere())
        self.add(social.CmdJournal())
        self.add(social.CmdMessenger())
        self.add(social.CmdRoomHistory())
        self.add(social.CmdRoomMood())
        self.add(social.CmdRandomScene())
        self.add(social.CmdRoomTitle())
        self.add(social.CmdTempDesc())
        self.add(social.CmdLanguages())
        self.add(maps.CmdMap())
        self.add(story_actions.CmdAction())
        self.add(plot_commands.CmdPlots())
        self.add(goal_commands.CmdGoals())
        self.add(combat.CmdHeal())

        # Magic!
        self.add(magic_commands.MagicCmdSet())


class MobileCmdSet(CmdSet):
    """
    Commands that should only be allowed if the character is able to move.
    Thought about making a 'living' cmdset, but there honestly aren't any
    current commands that could be executed while a player is alive but
    unable to move. The sets are just equal.
    """
    key = "MobileCmdSet"

    def at_cmdset_creation(self):
        self.add(overrides.CmdGet())
        self.add(overrides.CmdDrop())
        self.add(exchanges.CmdGive())
        self.add(exchanges.CmdTrade())
        self.add(overrides.CmdArxSay())
        self.add(general.CmdWhisper())
        self.add(general.CmdFollow())
        self.add(general.CmdDitch())
        self.add(general.CmdShout())
        self.add(general.CmdPut())
        self.add(general.CmdLockObject())
        self.add(xp.CmdTrain())
        self.add(xp.CmdUseXP())
        self.add(cmdset_places.CmdListPlaces())
        self.add(combat.CmdStartCombat())
        self.add(combat.CmdProtect())
        self.add(combat.CmdAutoattack())
        self.add(combat.CmdCombatStats())
        self.add(combat.CmdHarm())
        self.add(combat.CmdFightStatus())
        self.add(agent_commands.CmdGuards())
        self.add(domcommands.CmdPlotRoom())
        # self.add(domcommands.CmdTask())
        # self.add(domcommands.CmdSupport())
        self.add(domcommands.CmdWork())
        self.add(domcommands.CmdCleanupDomain())
        self.add(crafting.CmdCraft())
        self.add(crafting.CmdRecipes())
        self.add(crafting.CmdJunk())
        self.add(social.CmdPraise())
        # self.add(social.CmdCondemn())
        self.add(social.CmdThink())
        self.add(social.CmdFeel())
        self.add(social.CmdDonate())
        self.add(social.CmdFirstImpression())
        self.add(social.CmdGetInLine())
        self.add(investigation.CmdInvestigate())
        self.add(investigation.CmdAssistInvestigation())
        self.add(general.CmdDump())
        self.add(CmdApplyConsumable())
        self.add(gambling.CmdRoll())
        self.add(fashion_commands.CmdFashionModel())
        self.add(fashion_commands.CmdFashionOutfit())
        self.add(petitions_commands.CmdPetition())
        self.add(condition_commands.CmdKnacks())


class StaffCmdSet(CmdSet):
    """OOC staff and building commands. Character-based due to interacting with game world."""
    key = "StaffCmdSet"

    def at_cmdset_creation(self):
        # The help system
        self.add(help.CmdSetHelp())
        # System commands
        self.add(overrides.CmdArxScripts())
        self.add(system.CmdObjects())
        self.add(system.CmdAccounts())
        self.add(system.CmdService())
        self.add(system.CmdAbout())
        self.add(system.CmdServerLoad())
        # Admin commands
        self.add(admin.CmdBoot())
        self.add(admin.CmdBan())
        self.add(admin.CmdUnban())
        self.add(admin.CmdPerm())
        self.add(admin.CmdWall())
        # Building and world manipulation
        self.add(overrides.CmdTeleport())
        self.add(building.CmdSetObjAlias())
        self.add(building.CmdListCmdSets())
        self.add(building.CmdWipe())
        self.add(building.CmdName())
        self.add(building.CmdCpAttr())
        self.add(building.CmdMvAttr())
        self.add(building.CmdCopy())
        self.add(building.CmdFind())
        self.add(building.CmdOpen())
        self.add(building.CmdLink())
        self.add(building.CmdUnLink())
        self.add(building.CmdCreate())
        self.add(overrides.CmdDig())
        self.add(building.CmdTunnel())
        self.add(overrides.CmdArxDestroy())
        self.add(overrides.CmdArxExamine())
        self.add(building.CmdTypeclass())
        self.add(overrides.CmdArxLock())
        self.add(building.CmdScript())
        self.add(building.CmdSetHome())
        self.add(overrides.CmdArxTag())
        # Batchprocessor commands
        self.add(batchprocess.CmdBatchCommands())
        self.add(batchprocess.CmdBatchCode())
        # more recently implemented staff commands
        self.add(staff_commands.CmdGemit())
        self.add(staff_commands.CmdWall())
        self.add(staff_commands.CmdHome())
        self.add(staff_commands.CmdResurrect())
        self.add(staff_commands.CmdKill())
        self.add(staff_commands.CmdForce())
        self.add(staff_commands.CmdCcolor())
        self.add(staff_commands.CmdGMDisguise())
        self.add(staff_commands.CmdGMEvent())
        self.add(staff_commands.CmdRelocateExit())
        self.add(staff_commands.CmdAdminKey())
        self.add(staff_commands.CmdAdminPropriety())
        self.add(staff_commands.CmdAdjustFame())
        self.add(plot_commands.CmdGMPlots())
        self.add(plot_commands.CmdStoryCoordinators())
        self.add(goal_commands.CmdGMGoals())
        self.add(extended_room.CmdExtendedDesc())
        self.add(xp.CmdAdjustSkill())
        self.add(xp.CmdAwardXP())
        self.add(maps.CmdMapCreate())
        self.add(maps.CmdMapRoom())
        self.add(combat.CmdObserveCombat())
        self.add(combat.CmdAdminCombat())
        self.add(combat.CmdCreateAntagonist())
        self.add(combat.CmdStandYoAssUp())
        self.add(domcommands.CmdSetRoom())
        self.add(condition_commands.CmdModifiers())
        # home commands
        self.add(home.CmdAllowBuilding())
        self.add(home.CmdBuildRoom())
        self.add(home.CmdManageRoom())
        self.add(CmdRoot())

        # still pending implementation of additional details
        self.add(CmdTemplateForm())
