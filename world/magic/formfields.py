from paxforms.fields import Paxfield
from world.magic.models import Affinity, Alignment, Attunement, FamiliarAttunement, \
    PractitionerEffect, PractitionerSpell
from server.utils.arx_utils import a_or_an
import django.forms


class AlignmentField(Paxfield):

    def __init__(self, **kwargs):
        super(AlignmentField, self).__init__(**kwargs)
        self._alignment = None
        self._value = None

    # noinspection PyMethodMayBeStatic
    def _get_alignment_for_name(self, name):
        try:
            if isinstance(name, int):
                align = Alignment.objects.get(id=name)
            else:
                align = Alignment.objects.get(name__iexact=name)
            return align
        except Alignment.DoesNotExist:
            return None

    def get(self):
        if self._alignment:
            return self._alignment.id

        return None

    def set(self, value, caller=None):
        if not value or value == -1:
            self._value = None
            return True, None

        align = self._get_alignment_for_name(value)
        if not align:
            return False, "{} is not a valid alignment!".format(value)

        self._alignment = align
        return True, None

    def get_display(self):
        return self._alignment.name

    def get_display_params(self):
        return "<Primal||Elysian||Abyssal>"

    def validate(self, caller=None):
        return True, ""

    def webform_field(self, caller=None):
        options = {'label': self.full_name}
        if self.required is not None:
            options['required'] = self.required

        choices = (
            (-1, '----'),
            (Alignment.PRIMAL.id, "Primal"),
            (Alignment.ELYSIAN.id, "Elysian"),
            (Alignment.ABYSSAL.id, "Abyssal")
        )

        options['choices'] = choices
        return django.forms.ChoiceField(**options)


class AffinityField(Paxfield):

    def __init__(self, **kwargs):
        super(AffinityField, self).__init__(**kwargs)
        self._affinity = None

    # noinspection PyMethodMayBeStatic
    def _get_affinity_for_name(self, name):
        try:
            if isinstance(name, int):
                affinity = Affinity.objects.get(id=name)
            else:
                affinity = Affinity.objects.get(name__iexact=name)
            return affinity
        except Affinity.DoesNotExist:
            return None

    def get(self):
        if not self._affinity:
            return None

        return self._affinity.id

    def set(self, value, caller=None):
        if not value or value == -1:
            self._affinity = None
            return True, None

        affinity = self._get_affinity_for_name(value)
        if not affinity:
            return False, "{} is not a valid affinity!".format(value)

        self._affinity = affinity
        return True, None

    def get_display(self):
        return self._affinity.name

    def get_display_params(self):
        return "<affinity name>"

    def validate(self, caller=None):
        if self._required and not self._affinity:
            return False, "Required field {} wasn't filled out!  {}".format(self.full_name, self.help_text or "")
        return True, ""

    def webform_field(self, caller=None):
        options = {'label': self.full_name}
        if self.required is not None:
            options['required'] = self.required

        choices = [(-1, "----")]
        for affinity in Affinity.objects.all():
            choices.append((affinity.id, affinity.name))

        options['choices'] = choices
        return django.forms.ChoiceField(**options)


class PractitionerDependentField(Paxfield):

    term = "field"

    def __init__(self, **kwargs):
        super(PractitionerDependentField, self).__init__(**kwargs)
        self._value = None

    def _get_value_for_name(self, name, caller=None):
        return None

    def get(self):
        if not self._value:
            return None

        return self._value.id

    def set(self, value, caller=None):
        if not value or value == -1:
            self._value = None
            return True, None

        final_value = self._get_value_for_name(value, caller)
        if not final_value:
            term = self.__class__.term
            termpart = a_or_an(term)
            return False, "You don't seem to know {} {} named '{}'!".format(termpart, term, value)

        self._value = final_value
        return True, None

    def get_display(self):
        if self._value:
            return self._value.name
        return None

    def get_display_params(self):
        return "<{} name>".format(self.__class__.term)

    def validate(self, caller=None):
        if self._required and not self._value:
            return False, "Required field {} wasn't filled out!  {}".format(self.full_name, self.help_text or "")
        return True, ""

    def webform_field(self, caller=None):
        return None


class SpellField(PractitionerDependentField):

    term = "spell"

    def _get_value_for_name(self, name, caller=None):
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

    def webform_field(self, caller=None):
        options = {'label': self.full_name}
        if self.required is not None:
            options['required'] = self.required

        choices = []
        if not self.required:
            choices.append((-1, '----'))

        if caller and caller.practitioner:
            spells = {}
            for spell_record in PractitionerSpell.objects.filter(practitioner=caller.practitioner).all():
                spells[spell_record.spell.name] = spell_record.spell.id
            for key in sorted(spells.keys()):
                choices.append((spells[key], key))

        options['choices'] = choices
        return django.forms.ChoiceField(**options)


class EffectField(PractitionerDependentField):

    term = "effect"

    def _get_value_for_name(self, name, caller=None):
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

    def webform_field(self, caller=None):
        options = {'label': self.full_name}
        if self.required is not None:
            options['required'] = self.required

        choices = []
        if not self.required:
            choices.append((-1, '----'))

        if caller and caller.practitioner:
            effects = {}
            for effect_record in PractitionerEffect.objects.filter(practitioner=caller.practitioner).all():
                effects[effect_record.effect.name] = effect_record.effect.id
            for key in sorted(effects.keys()):
                choices.append((effects[key], key))

        options['choices'] = choices
        return django.forms.ChoiceField(**options)


class ToolField(PractitionerDependentField):

    term = "tool"

    def _get_value_for_name(self, name, caller=None):
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
            return attune.obj
        except Attunement.DoesNotExist:
            return None

    def webform_field(self, caller=None):
        options = {'label': self.full_name}
        if self.required is not None:
            options['required'] = self.required

        choices = []
        if not self.required:
            choices.append((-1, '----'))

        if caller and caller.practitioner:
            attunements = {}
            for attunement in Attunement.objects.filter(practitioner=caller.practitioner).all():
                attunements[attunement.obj.name] = attunement.obj.id
            for key in sorted(attunements.keys()):
                choices.append((attunements[key], key))

        options['choices'] = choices
        return django.forms.ChoiceField(**options)


class FamiliarField(PractitionerDependentField):
    term = "familiar"

    def _get_value_for_name(self, name, caller=None):
        if not caller:
            return None

        if not caller.practitioner:
            return None

        try:
            if isinstance(name, int):
                attune = FamiliarAttunement.objects.get(familiar__id=name, practitioner=caller.practitioner)
            else:
                attune = FamiliarAttunement.objects.get(familiar__name__icontains=name, practitioner=caller.practitioner)
            return attune.familiar
        except (FamiliarAttunement.DoesNotExist, FamiliarAttunement.MultipleObjectsReturned):
            return None

    def webform_field(self, caller=None):
        options = {'label': self.full_name}
        if self.required is not None:
            options['required'] = self.required

        choices = []
        if not self.required:
            choices.append((-1, '----'))

        if caller and caller.practitioner:
            attunements = {}
            for attunement in FamiliarAttunement.objects.filter(practitioner=caller.practitioner).all():
                attunements[attunement.familiar.name] = attunement.familiar.id
            for key in sorted(attunements.keys()):
                choices.append((attunements[key], key))

        options['choices'] = choices
        return django.forms.ChoiceField(**options)


