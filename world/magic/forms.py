from world.magic.formfields import *
from paxforms import fields, forms
from world.magic.models import Working


class WorkingForm(forms.Paxform):

    form_key = "workingform"
    form_purpose = "To fill out information about a magical working."
    form_description = '''
    This command allows you to fill out information about a magical working.
    '''

    name = fields.TextField(required=True, max_length=60, full_name="Name", priority=110)
    quiet = fields.ChoiceField(required=True, default=Working.QUIET_NONE, choices=Working.QUIET_TYPES, priority=105)
    template = fields.BooleanField(required=True, default=False, full_name="Use as Template", priority=104)
    intent = fields.TextField(required=False, full_name="Intentions", priority=100)
    spell = SpellField(required=False, full_name="Spell", priority=90)
    weave_effect = EffectField(required=False, full_name="Effect (Weave)", priority=87)
    weave_alignment = AlignmentField(required=False, full_name="Alignment (Weave)", priority=86)
    weave_affinity = AffinityField(required=False, full_name="Affinity (Weave)", priority=85)
    target = fields.TextField(full_name="Target", max_length=40, priority=83)
    tool = ToolField(required=False, full_name="Tool Used", priority=80)
    familiar = FamiliarField(required=False, full_name="Familiar Aiding", priority=75)

    # noinspection PyMethodMayBeStatic
    def _get_alignment_for_name(self, name):
        if not name:
            return None

        try:
            if isinstance(name, int):
                align = Alignment.objects.get(id=name)
            else:
                align = Alignment.objects.get(name__iexact=name)
            return align
        except Alignment.DoesNotExist:
            return None

    # noinspection PyMethodMayBeStatic
    def _get_affinity_for_name(self, name):
        if not name:
            return None

        try:
            if isinstance(name, int):
                affinity = Affinity.objects.get(id=name)
            else:
                affinity = Affinity.objects.get(name__iexact=name)
            return affinity
        except Affinity.DoesNotExist:
            return None

    # noinspection PyMethodMayBeStatic
    def _get_spell_for_name(self, name, caller=None):
        if not name:
            return None

        if not caller:
            return None

        if not caller.practitioner:
            return None

        try:
            if isinstance(name, int):
                spell = PractitionerSpell.objects.get(spell__id=name, practitioner=caller.practitioner)
            else:
                spell = PractitionerSpell.objects.get(spell__name__iexact=name, practitioner=caller.practitioner)
            return spell.spell
        except PractitionerSpell.DoesNotExist:
            return None

    # noinspection PyMethodMayBeStatic
    def _get_effect_for_name(self, name, caller=None):
        if not name:
            return None

        if not caller:
            return None

        if not caller.practitioner:
            return None

        try:
            if isinstance(name, int):
                effect = PractitionerEffect.objects.get(effect__id=name, practitioner=caller.practitioner)
            else:
                effect = PractitionerEffect.objects.get(effect__name__iexact=name, practitioner=caller.practitioner)
            return effect.effect
        except PractitionerEffect.DoesNotExist:
            return None

    # noinspection PyMethodMayBeStatic
    def _get_tool_for_name(self, name, caller=None):
        if not name:
            return None

        if not caller:
            return None

        if not caller.practitioner:
            return None

        try:
            if isinstance(name, int):
                attune = Attunement.objects.get(obj__id=name, practitioner=caller.practitioner)
            else:
                obj = caller.search(name)
                if not obj:
                    return None

                if obj.is_typeclass("typeclasses.characters.Character"):
                    return None

                attune = Attunement.objects.get(obj=obj, practitioner=caller.practitioner)
            return attune
        except Attunement.DoesNotExist:
            return None

    # noinspection PyMethodMayBeStatic
    def _get_familiar_for_name(self, name, caller=None):
        if not name:
            return None

        if not caller:
            return None

        if not caller.practitioner:
            return None

        try:
            if isinstance(name, int):
                attune = FamiliarAttunement.objects.get(familiar__id=name, practitioner=caller.practitioner)
            else:
                attune = FamiliarAttunement.objects.get(familiar__name__icontains=name, practitioner=caller.practitioner)
            return attune
        except FamiliarAttunement.DoesNotExist, FamiliarAttunement.MultipleObjectsReturned:
            return None

    # noinspection PyMethodMayBeStatic
    def validate(self, caller, values):
        if values.get('spell'):
            if values.get('weave_effect') or values.get('weave_alignment') or values.get('weave_affinity'):
                return "You cannot set both a spell and weave effect!"

        if not values.get('spell') and not values.get('weave_effect') and not values.get('intent'):
            return "You must provide either a spell, a weave effect, or a description of your intentions."

        if not values.get('spell') and not values.get('weave_effect') and values.get('template'):
            return "For a template, you must provide either a spell or a weave effect!"

        return None

    # noinspection PyMethodMayBeStatic
    def submit(self, caller, values):

        practitioner = caller.practitioner
        if not practitioner:
            caller.msg("Something has gone horribly wrong.  Are you actually a mage?")
            return

        name = values.get('name', None)
        quiet = values.get('quiet', Working.QUIET_NONE)
        template = values.get('template', False)
        intent = values.get('intent')
        alignment = self._get_alignment_for_name(values.get('weave_alignment'))
        affinity = self._get_affinity_for_name(values.get('weave_affinity'))
        effect = self._get_effect_for_name(values.get('weave_effect'), caller=caller)
        spell = self._get_spell_for_name(values.get('spell'), caller=caller)
        tool = self._get_tool_for_name(values.get('tool'), caller=caller)
        familiar = self._get_familiar_for_name(values.get('familiar'), caller=caller)
        target = values.get('target')

        working = Working.objects.create(lead=practitioner, quiet_level=quiet, template_name=name, template=template,
                                         intent=intent, weave_alignment=alignment, weave_affinity=affinity,
                                         weave_effect=effect, spell=spell, target_string=target)
        working.add_practitioner(practitioner, tool=tool, familiar=familiar, accepted=True)
        working.save()

        if template:
            caller.msg("Template named '{}' created; you can now use this with the 'cast' command.".format(name))
        else:
            caller.msg("Working created with ID {}.  You can use the 'working' command to invite others."
                       .format(working.id))
