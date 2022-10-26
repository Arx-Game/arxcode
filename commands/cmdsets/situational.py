import typeclasses.readable.readable_commands
from evennia.commands.cmdset import CmdSet
from commands.cmdsets import bank, combat, home, market, rumor, starting_gear
from typeclasses.wearable import cmdset_wearable, cmdset_wieldable
from typeclasses.places import cmdset_places
from typeclasses.containers import container


class SituationalCmdSet(CmdSet):
    """
    A collection of all situational cmdsets we want players to see
    in this collection.
    """

    key = "SituationalCommands"

    def at_cmdset_creation(self):
        self.add(bank.BankCmdSet())
        self.add(combat.CombatCmdSet())
        self.add(home.HomeCmdSet())
        self.add(home.ShopCmdSet())
        self.add(market.MarketCmdSet())
        self.add(rumor.RumorCmdSet())
        self.add(starting_gear.StartingGearCmdSet())
        self.add(cmdset_wearable.DefaultCmdSet())
        self.add(cmdset_wieldable.WeaponCmdSet())
        self.add(cmdset_places.DefaultCmdSet())
        self.add(cmdset_places.SittingCmdSet())
        self.add(typeclasses.readable.readable_commands.SignCmdSet())
        self.add(container.CmdChestKey())
