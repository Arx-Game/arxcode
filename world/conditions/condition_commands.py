"""
Commands for the conditions app.
"""
from server.utils.arx_utils import ArxCommand
from world.conditions.models import RollModifier


class CmdModifiers(ArxCommand):
    """
    Adds modifiers to objects
    
    Usage:
        @modifiers <object>
        @modifiers/search <tag name>
        @modifiers/targetmod <object>=<value>,<tag name>,check
        @modifiers/usermod <object>=<value>,<tag name>,check
        
    Sets modifiers for the most common usages - an object providing a bonus
    against those with a particular tag (targetmod) for a given type of roll,
    or an object providing a bonus to a user if they have the given tag. For
    more complex modifiers (such as to specific skills, or combinations of
    requirements), use django admin.
    
    Rooms provide modifiers to those in the location, while weapons and armor
    must be wielded/worn respectively. Tags they check can be added to things
    with the @tag command using the category 'modifiers'.
    """
    key = "@modifiers"
    locks = "cmd: perm(builders)"
    help_category = "building"

    def display_mods(self):
        """Displays modifiers on target"""
        targ = self.caller.search(self.lhs)
        if not targ:
            return
        self.msg("Modifiers on %s: %s" % (targ, ", ".join(str(ob) for ob in targ.modifiers.all())))

    def add_mod(self):
        """Adds a modifier to target"""
        from server.utils.arx_utils import dict_from_choices_field
        choices = dict_from_choices_field(RollModifier, "CHECK_CHOICES")
        try:
            value = int(self.rhslist[0])
            tag_name = self.rhslist[1].lower()
            check = choices[self.rhslist[2].lower()]
        except (IndexError, AttributeError):
            self.msg("You must provide value, tag name, and the type of check.")
        except KeyError:
            self.msg("Not a valid check type: %s" % ", ".join(choices.keys()))
        else:
            targ = self.caller.search(self.lhs)
            if not targ:
                return
            if "targetmod" in self.switches:
                mod = targ.add_modifier(value, check_type=check, target_tag=tag_name)
            else:
                mod = targ.add_modifier(value, check_type=check, user_tag=tag_name)
            self.msg("You have added a modifier to %s: %s." % (targ, mod))

    def search_mods(self):
        """Searches for modifiers for/against a given tag"""
        from django.db.models import Q
        msg = "Modifiers for/against %s: " % self.args
        qs = RollModifier.objects.filter(Q(user_tag__iexact=self.args) | Q(target_tag__iexact=self.args))
        msg += ", ".join(str(ob) for ob in qs)
        self.msg(msg)

    def func(self):
        """Executes modifiers command"""
        if not self.switches:
            return self.display_mods()
        if "targetmod" in self.switches or "usermod" in self.switches:
            return self.add_mod()
        if "search" in self.switches:
            return self.search_mods()
