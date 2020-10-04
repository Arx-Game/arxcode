from commands.base import ArxCommand
from evennia.commands.cmdset import CmdSet
from evennia.utils import evtable
from .models import (
    SkillNode,
    SkillNodeResonance,
    Working,
    WorkingParticipant,
    Practitioner,
    Attunement,
    FamiliarAttunement,
    PractitionerSpell,
    PractitionerEffect,
    Effect,
)
from server.utils.arx_utils import commafy, inform_staff
from server.utils.exceptions import CommandError
from evennia.utils.ansi import strip_ansi
from paxforms.paxform_commands import PaxformCommand
from world.magic.forms import WorkingForm
from django.utils import timezone


class CmdMagemit(ArxCommand):
    """
    Emit text to practitioners in a room, or to everyone if it's mundane.

    Usage:
      @magemit[/guaranteed] <strength>=<text>
      @magemit/mundane <text>

    The first form of the command will emit something that can be perceived by
    practitioners.  The strength is used to adjust the difficulty of the roll; the higher
    the strength, the more likely practitioners will see it.  If the /guaranteed switch
    is provided, everyone will see it regardless of the strength.

    The second form of this command will emit something mundane to everyone in the room,
    but will prepend the person's individual magicword so they know it isn't spoofed by
    someone else.  This is unlikely to be necessary often.
    """

    key = "@magemit"
    locks = "cmd:perm(Admins) or tag(story_npc)"

    def func(self):
        if "mundane" in self.switches:
            self.caller.location.msg_contents_magic(self.args, mundane=True)
            return

        if not self.rhs:
            self.msg("You need to provide a strength and an emit!")
            return

        try:
            strength = int(self.lhs)
        except ValueError:
            self.msg("You need to provide an integer value for the strength!")
            return

        self.caller.location.msg_contents_magic(
            self.rhs, strength=strength, guaranteed="guaranteed" in self.switches
        )


class CmdMagicWord(ArxCommand):
    """
    Sets your anti-spoofing word for the magic system.

    Usage:
      @magicword
      @magicword <word>

    This will set a personal 'magic word' which will be prepended to any magic
    system emits, so that you know someone wasn't just using @emit to fake you
    out.

    The first form of the command will show your current magic word.  The second
    will set a new magic word.
    """

    key = "@magicword"
    locks = "cmd:all()"

    def func(self):
        if not self.args:
            self.msg("Your magic word is: " + self.caller.magic_word)
            return

        self.caller.db.magic_word = self.args
        self.msg("Your magic word is now: " + self.args)


class CmdMagic(ArxCommand):
    """
    Accesses your practitioner record in the magic system.

    Usage:
      magic

      magic/nodes
      magic/spells
      magic/effects
      magic/conditions
      magic/stories <working ID>

      magic/teachnode <target>=<node>
      magic/teachspell <target>=<spell>
      magic/teacheffect <target>=<effect>

      magic/practice [node[,node2[,node3...]]]

      magic/drain <object>

      magic/gesture [description]
      magic/verb [verb]
      magic/language [language]
      magic/animaritual <spell>=<customized message>
      magic/checkemit

    This command allows you to interact with the magic system for everything
    except actually performing magic; for that, you'll want the 'cast' command.

    With no parameters, magic will tell you a little about your current magical
    state.

    The first set of switches -- /nodes, /spells, and /effects -- will show you
    the nodes, spells, and effects you know, respectively. (For more information
    on these terms, please check the Guide to Magic.)

    The second set of switches will allow you to instruct someone else in a node
    (opening it for them if they don't already know it) so that their practice
    might go faster, or to teach them a spell or effect (which is instantaneous).

    The /practice switch will allow you to put time and energy towards practicing
    one or more nodes on your magic system skill tree.

    The last switches will let you adjust how you perform magic -- the verb for
    how you perform magic ('chants', 'sings', etc.), the language in which you
    do so, and a short description of how you move when you do.  The /checkemit
    switch will return what your current emit string is -- what the room will
    see every time you perform magic if you don't choose to pay the cost to
    perform it quietly. /animaritual allows you to set a custom message for an
    anima ritual that your character knows, which tend to be unique to each
    individual caster.
    """

    key = "magic"
    locks = "cmd:practitioner() or perm(Admin)"

    def magic_state(self, practitioner):
        string = ""
        string += "---------------------------------------------------------------------------\n"
        string += "|wMAGIC STATUS FOR " + str(practitioner).upper() + "|n\n"
        string += "---------------------------------------------------------------------------\n"
        string += " |wStatus:|n " + practitioner.magic_state + "\n"

        nodes = SkillNodeResonance.objects.filter(
            practitioner=practitioner, practicing=True
        )
        nodestring = "Nothing"
        if nodes.count() > 0:
            nodestring = commafy([node.node.name for node in nodes.all()])

        string += " |wStudying:|n " + nodestring + "\n"

        nodes = SkillNodeResonance.objects.filter(
            practitioner=practitioner, teaching_multiplier__isnull=False
        )
        if nodes.count() > 0:
            table = evtable.EvTable(border=None)
            table.add_column(valign="t")
            sublines = []
            for node in nodes.all():
                sublines.append("%s, taught by %s" % (node.node.name, node.taught_by))
            table.add_row("|wTeaching Bonus:|n", "\n".join(sublines))
            string += str(table)

        tool_list = []
        coven_list = []
        for bond in practitioner.attunements.all():
            if bond.obj.is_typeclass("typeclasses.characters.Character"):
                coven_list.append(bond.obj)
            else:
                tool_list.append(bond.obj)

        if len(coven_list):
            string += (
                " |wCoven bonds:|n "
                + commafy(sorted([obj.name for obj in coven_list]))
                + "\n"
            )

        if len(tool_list):
            string += (
                " |wTools:|n " + commafy(sorted([obj.name for obj in tool_list])) + "\n"
            )

        familiar_list = sorted(
            [bond.familiar.name for bond in practitioner.familiars.all()]
        )
        if len(familiar_list):
            string += " |wFamiliars:|n " + commafy(familiar_list)

        if string[-1] != "\n":
            string += "\n"

        string += "---------------------------------------------------------------------------\n"

        return string

    def practitioner_for_string(self, practitioner_name):

        character = self.caller.search(
            practitioner_name, exact=True, typeclass="typeclasses.characters.Character"
        )
        if not character:
            return None

        return character.practitioner

    def func(self):
        practitioner = self.caller.practitioner

        admin = self.caller.player.check_permstring("admin")
        if admin and self.args and (not self.switches or "checkemit" in self.switches):
            practitioner = self.practitioner_for_string(self.args)
            if not practitioner:
                self.msg(
                    "Couldn't find a practitioner by that name.  Are they maybe not a mage yet?"
                )
                return

        if not practitioner:
            self.msg("No valid practitioner.")
            return

        if not self.switches:
            self.msg(self.magic_state(practitioner))
            return

        if "checkemit" in self.switches:
            name = "Your"
            if practitioner.character != self.caller:
                name = practitioner.character.name + "'s"
            self.msg(
                "{} current emit looks like: ".format(name) + practitioner.casting_emit
            )
            return

        if "gesture" in self.switches:
            if not self.args:
                self.msg("Your current gesture description is: " + practitioner.gesture)
                return

            practitioner.gesture = self.args
            self.msg("Your new gesture description is: " + practitioner.gesture)
            return

        if "language" in self.switches:
            if not self.args:
                self.msg(
                    "Your current casting language is {}.".format(
                        practitioner.language.capitalize()
                    )
                )
                return

            if not self.caller.tags.get(self.args, category="languages"):
                self.msg("You don't seem to know any language by that name!")
                return

            practitioner.language = self.args
            self.msg(
                "Your new casting language is {}.".format(
                    practitioner.language.capitalize()
                )
            )
            return

        if "verb" in self.switches:
            if not self.args:
                self.msg("Your current casting verb is: " + practitioner.verb)
                return

            practitioner.verb = self.args
            self.msg("Your new casting verb is: " + practitioner.verb.lower())
            return

        if "animaritual" in self.switches:
            success_msg = self.rhs or ""
            if len(success_msg) < 10:
                self.msg(
                    "Please write a longer description of what happens when your character does their anima "
                    "ritual. Strange things happening in the room based on their affinity, anything others "
                    "might notice about your character momentarily looking different, and so on."
                )
                return
            try:
                ritual = (
                    practitioner.spell_discoveries.filter(
                        effects__coded_effect=Effect.CODED_ANIMA_RITUAL
                    )
                    .distinct()
                    .get(spell_id=self.lhs)
                )
                ritual.success_msg = success_msg
                ritual.save()
            except (PractitionerSpell.DoesNotExist, ValueError):
                self.msg("No anima ritual by that ID.")
            return

        if "nodes" in self.switches:
            nodes = {}
            max_width = 10
            for node in practitioner.nodes.all():
                nodes[node.name] = node.description or ""
                if len(node.name) > max_width:
                    max_width = len(node.name)

            sorted_names = sorted(list(nodes.keys()))

            if len(sorted_names):
                table = evtable.EvTable(width=78, border="cells")
                table.add_column("|wNode|n", width=max_width + 4)
                table.add_column("|wDescription|n")
                for nodename in sorted_names:
                    table.add_row(nodename, nodes[nodename])

                self.msg(table)
            else:
                self.msg("You don't seem to know any nodes!")
            return

        if "spells" in self.switches:
            spells = {}
            max_width = 10
            for spell in practitioner.spells.all():
                spells[spell.name] = spell.description or ""
                if len(spell.name) > max_width:
                    max_width = len(spell.name)

            sorted_names = sorted(list(spells.keys()))

            if len(sorted_names):
                table = evtable.EvTable(width=78, border="cells")
                table.add_column("|wSpell|n", width=max_width + 4)
                table.add_column("|wDescription|n")
                for spellname in sorted_names:
                    table.add_row(spellname, spells[spellname])

                self.msg(table)
            else:
                self.msg("You don't seem to know any spells!")
            return

        if "effects" in self.switches:
            effects = {}
            max_width = 10
            for effect in practitioner.effects.all():
                effects[effect.name] = effect.description or ""
                if len(effect.name) > max_width:
                    max_width = len(effect.name)

            sorted_names = sorted(list(effects.keys()))

            if len(sorted_names):
                table = evtable.EvTable(width=78, border="cells")
                table.add_column("|wEffect|n", width=max_width + 4)
                table.add_column("|wDescription|n")
                for effectname in sorted_names:
                    table.add_row(effectname, effects[effectname])

                self.msg(table)
            else:
                self.msg("You don't seem to know any effects!")
            return

        if "conditions" in self.switches:
            conditions = {}
            max_width = 10
            for condition in practitioner.conditions.all():
                conditions[condition.condition.name] = (
                    condition.condition.description or ""
                )
                if len(condition.condition.name) > max_width:
                    max_width = len(condition.condition.name)

            sorted_names = sorted(list(conditions.keys()))

            if len(sorted_names):
                table = evtable.EvTable(width=78, border="cells")
                table.add_column("|Condition|n", width=max_width + 4)
                table.add_column("|wDescription|n")
                for conditionname in sorted_names:
                    table.add_row(conditionname, conditions[conditionname])

                self.msg(table)
            else:
                self.msg("You don't seem to have any conditions!")
            return

        if "stories" in self.switches:
            rituals = practitioner.anima_rituals

            if self.rhs:
                try:
                    ritual = rituals.get(id=self.rhs)
                except (Working.DoesNotExist, ValueError):
                    self.msg("No working by that ID.")
                    return
                self.msg(
                    "Story: %s"
                    % "\n".join(
                        ob.story
                        for ob in ritual.effect_handlers
                        if hasattr(ob, "story")
                    )
                )
                return
            self.msg("IDs of anima rituals: %s" % ", ".join(ob.id for ob in rituals))
            return

        if "teachnode" in self.switches:

            if not self.lhs or not self.rhs:
                self.msg("You need to provide all the arguments.")
                return

            student = self.practitioner_for_string(self.lhs)
            if not student:
                self.msg(
                    "I don't know what practitioner you mean.  You may need to contact staff to make sure your "
                    "student is set up as a practitioner."
                )
                return

            try:
                source_node = SkillNodeResonance.objects.get(
                    practitioner=practitioner, node__name__iexact=self.rhs
                )
            except SkillNodeResonance.DoesNotExist:
                self.msg("You don't know of any skill node named %s" % self.rhs)
                return

            try:
                target_node = SkillNodeResonance.objects.get(
                    practitioner=student, node__name__iexact=self.rhs
                )
                if source_node.resonance < target_node.resonance:
                    # You can't teach someone who knows more than you.
                    return
            except SkillNodeResonance.DoesNotExist:
                target_node = None
                if source_node.node.parent_node:
                    try:
                        parent_node = SkillNodeResonance.objects.get(
                            practitioner=student, node=source_node.node.parent_node
                        )
                    except SkillNodeResonance.DoesNotExist:
                        # We don't know the necessary parent node.
                        self.msg(
                            "They lack the knowledge required to learn that skill node."
                        )
                        return

            self.msg("Trying to teach %s to %s." % (source_node.node.name, student))

            multiplier = max(int(source_node.resonance ** (1 / 10.0)), 1)
            if not target_node:
                target_node = student.open_node(
                    source_node.node,
                    SkillNodeResonance.LEARN_TAUGHT,
                    "Taught by %s" % str(practitioner),
                )

            if not target_node:
                return

            inform_staff(
                "|y%s|n just taught skill node '%s' to |y%s|n."
                % (practitioner, source_node.node.name, student)
            )

            student.send_inform(
                "You have a temporary bonus to studying %s thanks to %s's teaching."
                % (source_node.node.name, practitioner)
            )

            target_node.teaching_multiplier = multiplier
            target_node.taught_by = str(practitioner)
            target_node.taught_on = timezone.now()
            target_node.save()
            return

        if "teachspell" in self.switches:

            if not self.lhs or not self.rhs:
                self.msg("You need to provide all the arguments.")
                return

            student = self.practitioner_for_string(self.lhs)
            if not student:
                self.msg(
                    "I don't know what practitioner you mean.  You may need to contact staff to make sure your "
                    "student is set up as a practitioner."
                )
                return

            try:
                source_spell = PractitionerSpell.objects.get(
                    practitioner=practitioner, spell__name__iexact=self.rhs
                )
            except PractitionerSpell.DoesNotExist:
                self.msg("You don't know of any spell named %s" % self.rhs)
                return

            try:
                target_spell = PractitionerSpell.objects.get(
                    practitioner=student, spell__name__iexact=self.rhs
                )
                # We can't teach them if they already know.
                return
            except PractitionerSpell.DoesNotExist:
                pass

            if not student.can_learn_spell(source_spell.spell):
                self.msg(
                    "They don't have the knowledge necessary to understand this spell."
                )
                return

            self.msg("Trying to teach %s to %s." % (source_spell.spell.name, student))

            inform_staff(
                "|y%s|n just taught spell '%s' to |y%s|n."
                % (practitioner, source_spell.spell.name, student)
            )

            student.learn_spell(
                source_spell.spell,
                PractitionerSpell.LEARN_TAUGHT,
                "Taught by %s" % str(practitioner),
            )
            return

        if "teacheffect" in self.switches:

            if not self.lhs or not self.rhs:
                self.msg("You need to provide all the arguments.")
                return

            student = self.practitioner_for_string(self.lhs)
            if not student:
                self.msg(
                    "I don't know what practitioner you mean.  You may need to contact staff to make sure your "
                    "student is set up as a practitioner."
                )
                return

            try:
                source_effect = PractitionerEffect.objects.get(
                    practitioner=practitioner, effect__name__iexact=self.rhs
                )
            except PractitionerEffect.DoesNotExist:
                self.msg("You don't know of any effect named %s" % self.rhs)
                return

            try:
                target_effect = PractitionerEffect.objects.get(
                    practitioner=student, effect__name__iexact=self.rhs
                )
                # We can't teach them if they already know.
                return
            except PractitionerEffect.DoesNotExist:
                pass

            self.msg("Trying to teach %s to %s." % (source_effect.effect.name, student))

            inform_staff(
                "|y%s|n just taught effect '%s' to |y%s|n."
                % (practitioner, source_effect.effect.name, student)
            )

            student.learn_effect(
                source_effect.effect,
                PractitionerEffect.LEARN_TAUGHT,
                "Taught by %s" % str(practitioner),
            )
            return

        if "practice" in self.switches:

            if not self.args:
                SkillNodeResonance.objects.filter(
                    practitioner=practitioner, practicing=True
                ).update(practicing=False)
                self.msg("You are no longer practicing/studying anything.")
                return

            nodes = []
            for nodename in self.lhslist:
                try:
                    node = SkillNodeResonance.objects.get(
                        practitioner=practitioner, node__name__iexact=nodename
                    )
                    nodes.append(node)
                except SkillNodeResonance.DoesNotExist:
                    self.msg("You don't know any node named %s." % nodename)
                    return

            SkillNodeResonance.objects.filter(
                practitioner=practitioner, practicing=True
            ).update(practicing=False)
            for node in nodes:
                node.practicing = True
                node.save()

            self.msg(
                "You are now practicing/studying %s."
                % commafy([node.node.name for node in nodes])
            )
            return

        if "drain" in self.switches:

            if not self.args:
                self.msg(
                    "You must provide an object in your inventory to try to drain."
                )
                return

            obj = self.caller.search(self.args)
            if not obj:
                return
            else:
                if obj.location != self.caller:
                    self.msg("The object must be in your inventory.")
                    return
                if not obj.valid_sacrifice:
                    self.msg(
                        "That object isn't something you can sacrifice for primum."
                    )
                    return

                max_primum = min(
                    obj.primum, practitioner.potential - practitioner.anima
                )
                self.msg("Draining primum from %s." % obj.name)
                obj.drain_primum(max_primum)
                practitioner.anima = practitioner.anima + max_primum
                practitioner.save()
                return

        self.msg("Unknown switches!")
        return


class CmdAdminMagic(ArxCommand):
    """
    Administers practitioner records in the magic system.

    Usage:
      @adminmagic <player>
      @adminmagic/open <player>=<node>
      @adminmagic/adjust <player>/<node>=<amount>
      @adminmagic/addresonance <player>=<amount>
      @adminmagic/addpotential <player>=<amount>
      @adminmagic/stories <player>

      @adminmagic/viewobject <obj>

      @adminmagic/working <working ID>
      @adminmagic/gm_difficulty <working ID>=<difficulty>
      @adminmagic/gm_cost <working ID>=<base primum cost>
      @adminmagic/gm_strength <working ID>=<magic strength>
      @adminmagic/calculate <working ID>
      @adminmagic/finalize <working ID>

    The first form of this command will display raw practitioner data for
    a practitioner.

    The second form will open a node on the practitioner's skill tree,
    while the third will adjust the resonance on an open node.

    The remaining command switches are for managing workings that are tied
    to an action for GM'ing.
    """

    key = "@adminmagic"
    locks = "cmd:perm(Admins)"

    # noinspections PyMethodMayBeStatic
    def working_for_string(self, string_id):
        if not string_id:
            return None

        try:
            id_num = int(string_id)
            working = Working.objects.get(id=id_num)
            return working
        except (ValueError, Working.DoesNotExist):
            return None

    def practitioner_for_string(self, practitioner_name):

        character = self.caller.search(
            practitioner_name,
            exact=True,
            global_search=True,
            typeclass="typeclasses.characters.Character",
        )
        if not character:
            return None

        return character.practitioner

    # noinspection PyMethodMayBeStatic
    def node_for_string(self, node_name):
        try:
            node = SkillNode.objects.get(name__iexact=node_name)
        except SkillNode.DoesNotExist:
            return None

        return node

    def func(self):

        if not self.switches:
            practitioner = self.practitioner_for_string(self.args)
            if not practitioner:
                self.msg(
                    "Couldn't find a practitioner by that name.  "
                    "The player may not yet be a practitioner."
                )
                return

            table = evtable.EvTable(border=None)
            table.add_column(valign="t")
            table.add_column()
            table.add_row("|wName:|n", str(practitioner))
            table.add_row("|wPotential:|n", practitioner.potential)
            table.add_row("|wAnima:|n", practitioner.anima)
            table.add_row("|wUnspent Resonance:|n", practitioner.unspent_resonance)

            if practitioner.alignments.count():
                subtable = evtable.EvTable(border=None)
                for align_record in practitioner.alignments.all():
                    subtable.add_row(str(align_record.alignment), align_record.value)
                table.add_row("|wAlignments:|n ", str(subtable))

            if practitioner.favored_by.count():
                subtable = evtable.EvTable(border=None)
                for favor_record in practitioner.favored_by.all():
                    subtable.add_row(str(favor_record.alignment), favor_record.value)
                table.add_row("|wFavor:|n", str(subtable))

            node_names = sorted(
                [
                    "|w{}|n".format(noderes.node.name)
                    for noderes in practitioner.node_resonances.all()
                ]
            )
            if len(node_names):
                table.add_row("|wNodes:|n", commafy(node_names))

            spell_names = sorted(
                [
                    "|w{}|n".format(spellrecord.spell.name)
                    for spellrecord in practitioner.spell_discoveries.all()
                ]
            )
            if len(spell_names):
                table.add_row("|wSpells:|n", commafy(spell_names))

            effect_names = sorted(
                [
                    "|w{}|n".format(effectrecord.effect.name)
                    for effectrecord in practitioner.effect_discoveries.all()
                ]
            )
            if len(effect_names):
                table.add_row("|wEffects:|n", commafy(effect_names))

            if practitioner.attunements.count():
                tool_records = []
                coven_records = []
                for attune_record in practitioner.attunements.all():
                    if attune_record.obj.is_typeclass(
                        "typeclasses.characters.Character"
                    ):
                        coven_records.append(attune_record)
                    else:
                        tool_records.append(attune_record)

                if len(coven_records):
                    subtable = evtable.EvTable(border=None)
                    subtable.add_column(width=30, valign="t")
                    subtable.add_column()
                    for record in coven_records:
                        subtable.add_row(
                            strip_ansi(record.obj.name), record.attunement_level
                        )
                    table.add_row("|wCoven Bonds:|n", str(subtable))

                if len(tool_records):
                    subtable = evtable.EvTable(border=None)
                    subtable.add_column(width=30, valign="t")
                    subtable.add_column()
                    for record in tool_records:
                        subtable.add_row(
                            strip_ansi(record.obj.name), record.attunement_level
                        )
                    table.add_row("|wAttunments:|n", str(subtable))

            if practitioner.familiars.count():
                subtable = evtable.EvTable(border=None)
                subtable.add_column(width=30, valign="t")
                subtable.add_column()
                for familiar in practitioner.familiars.all():
                    subtable.add_row(
                        strip_ansi(familiar.familiar.name), familiar.attunement_level
                    )
                table.add_row("|wFamiliars:|n", str(subtable))

            self.msg("\n" + str(table))
            return

        if "open" in self.switches:

            practitioner = self.practitioner_for_string(self.lhs)
            if not practitioner:
                self.msg(
                    "Couldn't find a practitioner by that name.  "
                    "The player may not yet be a practitioner."
                )
                return

            rhs_args = self.rhs.split("/")

            node = self.node_for_string(rhs_args[0])
            if not node:
                self.msg("Couldn't find a node by that name.")
                return

            if practitioner.knows_node(node):
                self.msg("They already have opened that node!")
                return

            reason = rhs_args[1] if len(rhs_args) > 1 else None

            inform_staff(
                "{} opened |y{}|n's |y{}|n node.".format(
                    self.caller.name, str(practitioner), node.name
                )
            )

            practitioner.open_node(node, SkillNodeResonance.LEARN_FIAT, reason)
            self.msg("Node opened!")
            return

        if "adjust" in self.switches:

            lhs_args = self.lhs.split("/")
            if len(lhs_args) != 2:
                self.msg("Something's wrong with those arguments.")
                return

            practitioner = self.practitioner_for_string(lhs_args[0])
            if not practitioner:
                self.msg(
                    "Couldn't find a practitioner by that name.  "
                    "The player may not yet be a practitioner."
                )
                return

            node = self.node_for_string(lhs_args[1])
            if not node:
                self.msg("Couldn't find a node by that name.")
                return

            try:
                amount = float(self.rhs)
            except ValueError:
                self.msg("That doesn't seem to be a valid amount.")
                return

            if not practitioner.knows_node(node):
                self.msg("That practitioner hasn't yet opened that node.")

            inform_staff(
                "{} adjusted |y{}|n's |y{}|n resonance by {}".format(
                    self.caller.name, str(practitioner), node.name, amount
                )
            )

            self.msg(
                "Adding {} resonance to {}'s {} node.".format(
                    amount, practitioner, node
                )
            )
            practitioner.add_resonance_to_node(node, amount)
            return

        if "adjustpotential" in self.switches:

            practitioner = self.practitioner_for_string(self.lhs)
            if not practitioner:
                self.msg(
                    "Couldn't find a practitioner by that name.  "
                    "The player may not yet be a practitioner."
                )
                return

            try:
                amount = int(self.rhs)
            except ValueError:
                self.msg("You must provide a valid integer value.")
                return

            practitioner.potential = practitioner.potential + amount
            practitioner.save()
            self.msg("Potential added.")
            inform_staff(
                "|y{}|n just added {} aionic potential to |y{}|n, for a total of {}.".format(
                    self.caller.name, amount, practitioner, practitioner.potential
                )
            )
            return

        if "adjustresonance" in self.switches:

            practitioner = self.practitioner_for_string(self.lhs)
            if not practitioner:
                self.msg(
                    "Couldn't find a practitioner by that name.  "
                    "The player may not yet be a practitioner."
                )
                return

            try:
                amount = float(self.rhs)
            except ValueError:
                self.msg("You must provide a valid floating point value.")
                return

            practitioner.unspent_resonance = min(
                practitioner.potential, practitioner.unspent_resonance + amount
            )
            practitioner.save()
            self.msg("Resonance added.")
            inform_staff(
                "|y{}|n just added {} resonance to |y{}|n, for a total of {}.".format(
                    self.caller.name,
                    amount,
                    practitioner,
                    practitioner.unspent_resonance,
                )
            )
            return

        if "stories" in self.switches:
            practitioner = self.practitioner_for_string(self.lhs)
            if not practitioner:
                self.msg(
                    "Couldn't find a practitioner by that name.  "
                    "The player may not yet be a practitioner."
                )
                return
            self.msg(
                "IDs of anima rituals for %s: %s"
                % (practitioner, ", ".join(ob.id for ob in practitioner.anima_rituals))
            )
            return

        if "working" in self.switches:

            if not self.args:
                self.msg("You must provide a working number to view!")
                return

            working = self.working_for_string(self.args)
            if not working:
                self.msg("That doesn't seem to be a valid working ID!")
                return

            self.msg(working.description_string())
            return

        if (
            "gm_difficulty" in self.switches
            or "gm_cost" in self.switches
            or "gm_strength" in self.switches
        ):

            working = self.working_for_string(self.lhs)
            if not working:
                self.msg("You need to provide a valid working ID!")
                return

            if working.finalized:
                self.msg("That working is already completed!")
                return

            if not working.intent:
                self.msg(
                    "This doesn't seem to be a GM'd working.  Are you sure you entered the number right?"
                )
                return

            try:
                value = int(self.rhs)
            except ValueError:
                self.msg("You must provide a valid integer for this switch!")
                return

            if "gm_difficulty" in self.switches:
                working.gm_difficulty = value
                self.msg("Difficulty for working set to {}.".format(value))
            elif "gm_cost" in self.switches:
                working.gm_cost = value
                self.msg("Base primum cost for working set to {}.".format(value))
            else:
                working.gm_strength = value
                self.msg("Base magic strength for working set to {}.".format(value))

            working.save()
            return

        if "calculate" in self.switches:

            working = self.working_for_string(self.args)
            if not working:
                self.msg("You need to provide a valid working ID!")
                return

            if working.finalized:
                self.msg("That working is already completed!")
                return

            if working.calculated:
                self.msg("Warning: Recalculating a calculated working.")

            result = working.validation_error(gm_override=True)
            if result:
                self.msg(result)
                return

            result = working.perform(gm_override=True, unsafe=True)
            if result:
                resultstring = "Working has been performed, with the following results:"
                resultstring += "\n|wSuccesses:|n %d" % working.successes
                resultstring += "\n|wTarget:|n %d" % working.successes_to_beat
                if working.effects_description:
                    resultstring += "\n|wResults:|n " + working.effects_description
                resultstring += (
                    "\n|wConsequence:|n " + working.consequence_description
                    or "No consequence (whew!)"
                )
                resultstring += (
                    "\n\nDo |w@adminmagic/finalize %d|n to finalize these results."
                    % working.id
                )
                self.msg(resultstring)
            else:
                self.msg("Working could not be performed.  Talk to Pax?")

            return

        if "finalize" in self.switches:

            working = self.working_for_string(self.args)
            if not working:
                self.msg("You need to provide a valid working ID!")
                return

            if working.finalized:
                self.msg("That working is already completed!")
                return

            if not working.calculated:
                self.msg("The results of that working haven't been calculated yet!")
                return

            working.finalize(gm_override=True)
            self.msg("Working results applied!")
            return

        if "run_advancement" in self.switches:
            from world.magic.advancement import magic_advancement_script

            script = magic_advancement_script()
            if not script:
                self.msg("The magic advancement script doesn't appear to be running!")
                return

            self.msg("Running weekly magic advancement manually.")
            script.perform_weekly_magic()
            return

        if "viewobject" in self.switches:

            if not self.args:
                self.msg("You must provide an object to view!")
                return

            obj = self.caller.search(self.args)
            if not obj:
                return

            table = evtable.EvTable(border="cells")
            table.add_column(valign="t")
            table.add_column()
            table.add_row("|wName|n", obj.name)
            table.add_row("|wAlignment|n", obj.alignment)
            table.add_row("|wAffinity|n", obj.affinity)
            table.add_row("|wPrimum|n", "%d of %d" % (obj.primum, obj.potential))
            table.add_row("|wMagic Desc|n", obj.magic_description)
            table.add_row("|wMagic Desc Advanced|n", obj.magic_description_advanced)
            self.msg(str(table))
            return

        self.msg("Unknown switches!")
        return


class WorkingDisplayMixin(object):

    # noinspection PyMethodMayBeStatic
    def string_for_working(self, working, practitioner):
        table = evtable.EvTable(border="cells")
        table.add_column(valign="t")
        table.add_column()

        table.add_row("|wWorking ID:|n", working.id)
        if working.action:
            table.add_row("|wAction:|n", working.action.id)
        table.add_row("|wDescription:|n", working.short_description)
        table.add_row("|wParticipants:|n", working.draft_participant_string)

        if working.quiet_level != Working.QUIET_NONE:
            if working.quiet_level == Working.QUIET_MUNDANE:
                table.add_row("|wQuiet to:|n", "Mundane Perception")
            elif working.quiet_level == Working.QUIET_TOTAL:
                table.add_row("|wQuiet to:|n", "Mundane and Magical Perception")

        if working.alignment:
            table.add_row("|wAlignment:|n", working.alignment)
        if working.affinity:
            table.add_row("|wAffinity:|n", working.affinity)
        if working.spell:
            table.add_row("|wSpell:|n", working.spell.name)
        elif working.weave_effect:
            table.add_row("|wWeave Effect:|n", working.weave_effect.name)

        if working.target_string:
            table.add_row("|wTarget:|n", working.target_string)

        record = working.practitioner_record(practitioner)
        if record.tool:
            table.add_row("|wYour Tool:|n", record.tool.obj.name)
        if record.familiar:
            table.add_row("|wYour Familiar:|n", record.familiar.familiar.name)

        if record.drained.count():
            names = [obj.name for obj in record.drained.all()]
            table.add_row("|wYour Sacrifices:|n", commafy(names))

        if working.econ:
            table.add_row("|wEcon Resources:|n", working.econ)

        if working.cost:
            current_danger_level = working.calculate_danger_level(draft=False)
            table.add_row(
                "|wCurrent Risk:|n", Working.danger_level_string(current_danger_level)
            )
        else:
            table.add_row(
                "|wCurrent Risk:|n ", "Cannot be calculated until GM intervention."
            )

        if working.has_pending:
            draft_danger_level = working.calculate_danger_level(draft=True)
            table.add_row(
                "|wIf Everyone Joins:|n",
                Working.danger_level_string(draft_danger_level),
            )

        result = str(table)
        if working.has_pending:
            result += "\nParticipants with a |r*|n next to their name have not yet accepted the invite."

        return result


class CmdWorking(PaxformCommand, WorkingDisplayMixin):
    """
    To fill out information about a magical working.

    FILLING OUT THE FORM
    Usage to manage form:
      working/create
      working/cancel
      working/submit
      working/check
    Usage for general workings:
      working/name [value]
      working/quiet [None||Mundane||Total]
      working/target [value]
      working/tool [tool name]
      working/familiar [familiar name]
      working/template [yes||no||true||false||0||1]
    Usage for GM'd workings:
      working/intent [value]
    Usage for spells:
      working/spell [spell name]
    Usage for weaves:
      working/weave_effect [effect name]
      working/weave_alignment [Primal||Elysian||Abyssal]
      working/weave_affinity [affinity name]

    MANAGING A DEFINED WORKING
    Usage:
      working/list
      working <id>
      working/familiar <id>=[familiar name]
      working/tool <id>=[tool name]
      working/invite <id>=player[,player2[,player3]]
      working/accept <id>
      working/decline <id>
      working/add_econ <id>=<amount>
      working/add_sacrifice <id>=<object>
      working/rm_sacrifice <id>=<object>
      working/perform[/unsafe] <id>
      working/action <id>=<action ID>

    NOTE: It is highly recommended you read the magic system tutorial before using
    this command!

    This command allows you to define and interact with magic workings. A working
    can have a spell (i.e., a specific known sequence of magic), a weave (which is
    working entirely without a net and making it up as you go, but more flexible),
    or an intent (which is a description of what you're trying, if the working will
    be handled by GMs).

    Workings can be actual workings (i.e. things you will perform, and can invite
    people to) or can be templates (i.e. things you will use later with the 'cast'
    spell and might do repeatedly).

    The first set of command switches will set up a form to define a working.  For
    a template, you must provide the name, and either a spell or weave effect,
    affinity, and alignment if you're trying something that isn't encapsulated in
    a spell.  The tool switch will set what of your magic focii you plan to use to
    aid you in this, and the familiar switch will set what familiar of yours you
    want to assist you in the working.  If you plan to perform the working not as
    a template, you may also need to provide a target.

    Once you've defined a working, you can /perform it -- you may need to use the
    /unsafe switch if it's calculated that the working would be riskier than
    usual.  You can also change out your familiar, tool, and add or remove
    objects to be drained of primum.  Right now, these must be trinkets from
    shardhavens, or weapons that have a significant amount of primum invested
    in them.  You can also add econ resources to be sacrificed.

    You can also invite other people to participate in a working; working together
    can decrease the relative danger of a working.
    """

    key = "working"
    locks = "cmd:practitioner()"
    form_class = WorkingForm

    # noinspection PyMethodMayBeStatic
    def working_for_id(self, id, practitioner):
        try:
            id = int(id)
            working = Working.objects.get(
                id=id, practitioners__in=[practitioner], finalized=False
            )
            return working
        except (ValueError, Working.DoesNotExist):
            return None

    def func(self):

        practitioner = self.caller.practitioner

        if self.args and not self.switches:

            working = self.working_for_id(self.args, practitioner)
            if not working:
                self.msg("That doesn't seem to be one of your valid workings!")
                return

            self.msg(self.string_for_working(working, practitioner))
            return

        if "invite" in self.switches:
            working = self.working_for_id(self.lhs, practitioner)
            if not working:
                self.msg("That doesn't seem to be one of your valid workings!")
                return

            if working.lead != practitioner:
                self.msg("Only the lead practitioner can invite someone to a working!")
                return

            targets = []
            player_list = self.rhs.split(",")
            for name in player_list:
                try:
                    obj = self.character_search(name, allow_npc=True)
                except CommandError as ce:
                    self.msg(ce)
                    return
                targets.append(obj)

            practitioners = []
            for obj in targets:
                target_practitioner = Practitioner.practitioner_for_character(obj)
                if not target_practitioner or not target_practitioner.eyes_open:
                    self.msg(
                        "One or more of these participants are not set up for the magic system.  "
                        "Contact staff if you think this is an error!"
                    )
                    return
                practitioners.append(target_practitioner)

            for target in practitioners:
                if working.practitioner_record(target):
                    self.msg(
                        "{} has already been invited to this working!".format(target)
                    )
                    return

            inform_string = (
                "|w{}|n has invited you to be a participant in a magical working to {}!\n\n"
                "For more information, you can do |wworking {}|n -- to accept, do |wworking/accept {}|n "
                "or to decline do |wworking/decline {}|n.".format(
                    self.caller.name,
                    working.short_description,
                    working.id,
                    working.id,
                    working.id,
                )
            )

            for target in practitioners:
                working.add_practitioner(target)
                target.send_inform(inform_string)
                self.msg("Invited {} to the working.".format(target))

            return

        if "accept" in self.switches or "decline" in self.switches:
            working = self.working_for_id(self.args, practitioner)
            if not working:
                self.msg("That doesn't seem to be one of your valid workings!")
                return

            try:
                participant_record = WorkingParticipant.objects.get(
                    working=working, practitioner=practitioner
                )
            except WorkingParticipant.DoesNotExist:
                self.msg(
                    "Something has gone terribly wrong.  Please contact staff with this working ID."
                )
                return

            if participant_record.accepted:
                self.msg(
                    "You're already part of that working; you can't change your invite status now!"
                )
                return

            if "accept" in self.switches:
                working.accept_practitioner(practitioner)
                self.msg("You've accepted the invitation to be part of the working.")
            else:
                working.decline_practitioner(practitioner)
                self.msg("You've declined the invitation to be part of the working.")
            return

        if "tool" in self.switches and "=" in self.args:

            working = self.working_for_id(self.lhs, practitioner)
            if not working:
                self.msg("That doesn't seem to be one of your valid workings!")
                return

            tool = None
            obj = None
            if len(self.rhs):
                try:
                    obj = self.search(self.rhs)
                except CommandError as ce:
                    self.msg(ce)
                    return

                try:
                    tool = Attunement.objects.get(practitioner=practitioner, obj=obj)
                except Attunement.DoesNotExist:
                    self.msg("You haven't attuned {}.".format(obj.name))
                    return

            record = working.practitioner_record(practitioner)
            record.tool = tool
            record.save()

            if tool:
                self.msg("Tool has been set to {}.".format(obj.name))
            else:
                self.msg("Tool has been cleared.")

            return

        if "familiar" in self.switches and "=" in self.args:

            working = self.working_for_id(self.lhs, practitioner)
            if not working:
                self.msg("That doesn't seem to be one of your valid workings!")
                return

            familiar = None
            if len(self.rhs):
                familiars = FamiliarAttunement.objects.filter(
                    practitioner=practitioner, familiar__name__istartswith=self.rhs
                )
                if familiars.count() > 1:
                    self.msg("I don't know which one you mean!")
                    return
                if familiars.count() == 0:
                    self.msg("You don't seem to have a familiar by that name.")
                    return
                familiar = familiars.all()[0]

            record = working.practitioner_record(practitioner)
            record.familiar = familiar
            record.save()

            if familiar:
                self.msg("Familiar has been set to {}.".format(familiar.familiar.name))
            else:
                self.msg("Familiar has been cleared.")

            return

        if "perform" in self.switches:

            working = self.working_for_id(self.lhs, practitioner)
            if not working:
                self.msg("That doesn't seem to be one of your valid workings!")
                return

            if working.lead != practitioner:
                self.msg("Only the lead practitioner can do the /perform switch!")
                return
            # if we're in combat, we route to there
            if self.caller.combat.state:
                self.caller.combat.state.set_queued_action(
                    "casting", working=working, unsafe="unsafe" in self.switches
                )
                return
            if working.perform(unsafe="unsafe" in self.switches):
                working.finalize()
            return

        if "add_econ" in self.switches:

            working = self.working_for_id(self.lhs, practitioner)
            if not working:
                self.msg("That doesn't seem to be one of your valid workings!")
                return

            try:
                amount = int(self.rhs)
            except ValueError:
                self.msg("You have to provide a value amount of econ to add!")
                return

            player = self.caller.player
            if not player:
                self.msg("Something has gone horribly wrong.")
                return

            if not hasattr(player, "Dominion") or not hasattr(
                player.Dominion, "assets"
            ):
                self.msg("You don't seem to be set up as an asset owner.")
                return

            assets = player.Dominion.assets
            econ = assets.economic

            if amount > econ:
                self.msg(
                    "You tried to add {} econ, but you only have {}!".format(
                        amount, econ
                    )
                )
                return

            econ -= amount
            assets.economic = econ
            assets.save()
            if working.econ:
                working.econ = working.econ + amount
            else:
                working.econ = amount

            working.save()
            self.msg("Added {} economic resources to the working.".format(amount))
            return

        if "add_sacrifice" in self.switches or "rm_sacrifice" in self.switches:

            working = self.working_for_id(self.lhs, practitioner)
            if not working:
                self.msg("That doesn't seem to be one of your valid workings!")
                return

            if not self.rhs:
                self.msg("You have to provide an object name!")
                return

            try:
                obj = self.search(self.rhs)
            except CommandError as ce:
                self.msg(ce)
                return

            if not obj.valid_sacrifice:
                self.msg("{} isn't something you can sacrifice!".format(obj.name))
                return

            record = working.practitioner_record(practitioner)
            if not record:
                self.msg("Something has gone horribly wrong.")
                return

            if "add_sacrifice" in self.switches:
                if record.has_drain(obj):
                    self.msg("{} is already being sacrificed!".format(obj.name))
                    return

                record.add_drain(obj)
                self.msg("Added {} as a sacrifice to the working.".format(obj.name))
                return
            else:
                if not record.has_drain(obj):
                    self.msg("{} is not being sacrificed!".format(obj.name))
                    return

                record.add_drain(obj)
                self.msg("Added {} as a sacrifice to the working.".format(obj.name))
                return

        if "action" in self.switches:
            from world.dominion.models import PlotAction

            working = self.working_for_id(self.lhs, practitioner)
            if not working:
                self.msg("That doesn't seem to be one of your valid workings!")
                return

            if not self.rhs:
                self.msg("You need to provide an action ID as well!")
                return

            try:
                from django.db.models import Q

                plotid = int(self.rhs)
                action = PlotAction.objects.get(
                    Q(id=plotid)
                    & (
                        Q(dompc=practitioner.character.dompc)
                        | Q(assistants=practitioner.character.dompc)
                    )
                    & Q(status=PlotAction.DRAFT)
                )
            except ValueError:
                self.msg("You need to provide a number for the action ID!")
                return
            except PlotAction.DoesNotExist:
                self.msg("That doesn't seem to be one of your actions.")
                return

            action.working = working
            action.save()
            self.msg(
                "Working %d has been attached to action %d." % (working.id, action.id)
            )
            return

        if "list" in self.switches:
            workings = Working.objects.filter(
                calculated=False, template=False, practitioners__in=[practitioner]
            )
            if workings.count() == 0:
                self.msg("You don't have any pending workings!")
                return

            table = evtable.EvTable(width=78, border="cells")
            table.add_column(align="r", width=7)
            table.add_column("|wPractitioners|n")
            table.add_column("|wDescription|n")
            for ritual in workings.all():
                practitioners = ritual.draft_participant_string

                participant_record = ritual.practitioner_record(practitioner)

                id_string = str(ritual.id)
                if not participant_record.accepted:
                    id_string += "|r*|n"
                else:
                    id_string += " "

                table.add_row(id_string, practitioners, ritual.short_description)

            self.msg(str(table))
            self.msg(
                "Any workings with a |r*|n next to their ID are ones you have been invited to but have not "
                "yet accepted.  Any participants with a |r*|n next to their name have been invited but not "
                "yet accepted."
            )
            return

        super(CmdWorking, self).func()


class CmdCast(ArxCommand, WorkingDisplayMixin):
    """
    To cast a pre-prepared template for a working.

    Usage:
      cast[/unsafe] <template>[=target]
      cast/view <template>
      cast/list

    This command will view your templated workings, and potentially cast one.
    The first form will actually cast a template (with an optional target
    for those workings that require one). If the working would be unsafe to
    perform in your present situation, it will prompt you and force you to
    use the /unsafe switch before it will actually perform the magic.

    The second form will view a template, along with the current calculated
    danger level.

    The third form will list all your templated workings.

    Working templates are defined using the 'working' command.
    """

    key = "cast"
    locks = "cmd:practitioner()"

    # noinspection PyMethodMayBeStatic
    def working_for_id(self, working_id, practitioner):
        try:
            working_id = int(working_id)
            working = Working.objects.get(
                id=working_id, lead=practitioner, template=True
            )
            return working
        except (ValueError, Working.DoesNotExist):
            return None

    def working_for_name(self, name, practitioner):
        workings = Working.objects.filter(
            template_name__iexact=name, lead=practitioner, template=True
        )
        if workings.count() == 0:
            return None
        if workings.count() > 1:
            self.msg("That matches too many templates!  Use the ID instead.")
            return None
        return workings.all()[0]

    def func(self):

        practitioner = self.caller.practitioner
        if not practitioner:
            self.msg(
                "Something horrible has happened. Are you set up for the magic system?"
            )
            return

        if "list" in self.switches:
            workings = Working.objects.filter(template=True, lead=practitioner)
            if workings.count() == 0:
                self.msg("You don't seem to have any saved templates!")
                return

            table = evtable.EvTable(border="cells")
            table.add_column("", width=7, valign="t")
            table.add_column("|wName|n", width=25)
            table.add_column("|wDescription|n")

            for working in workings.all():
                table.add_row(
                    working.id, working.template_name or "", working.short_description
                )

            self.msg(str(table))
            return

        if "view" in self.switches:

            if not self.args:
                self.msg("You must provide a working to view!")
                return

            working = self.working_for_id(self.args, practitioner)
            if not working:
                working = self.working_for_name(self.args, practitioner)

            if not working:
                self.msg("Could not find the working to view.")
                return

            self.msg(self.string_for_working(working, practitioner))
            return

        if not self.args:
            self.msg("You must provide a working to cast!")
            return

        working = self.working_for_id(self.lhs, practitioner)
        if not working:
            working = self.working_for_name(self.lhs, practitioner)

        if not working:
            self.msg("Could not find the working to cast.")
            return

        validation_err = working.validation_error(target_string=self.rhs)
        if validation_err:
            self.msg(validation_err)
            return

        real_cast = working.performable_copy(target=self.rhs)
        # if we're in combat, we route to there
        if self.caller.combat.state:
            self.caller.combat.state.set_queued_action(
                "casting",
                working=real_cast,
                unsafe="unsafe" in self.switches,
                delete_on_fail=True,
            )
            return

        if real_cast.perform(unsafe="unsafe" in self.switches):
            real_cast.finalize()
        else:
            real_cast.delete()


class MagicCmdSet(CmdSet):
    def at_cmdset_creation(self):
        self.add(CmdMagemit())
        self.add(CmdMagicWord())
        self.add(CmdMagic())
        self.add(CmdAdminMagic())
        self.add(CmdWorking())
        self.add(CmdCast())
