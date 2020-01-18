import re
import django

from server.utils.arx_utils import commafy


class Paxfield(object):
    """
    This is the base class from which all Paxfields descend.
    """

    def __init__(self, key=None, full_name=None, default=None, required=False, help_text=None, priority=0):
        self._key = key
        self._full_name = full_name
        self._help_text = help_text
        self._default = default
        self._required = required
        self._priority = priority

    def set_key(self, key):
        self._key = key

    def serialize(self, serialization_dict):
        if self.get() is not None:
            serialization_dict[self.key] = self.get()

    def validate(self, caller=None):
        return False, "{} is a base field that should never have been added.".format(self.full_name)

    def set(self, value, caller=None):
        pass

    def get(self):
        return None

    def get_display(self):
        return self.get()

    @staticmethod
    def get_display_params():
        return "[value]"

    @property
    def key(self):
        return self._key

    @property
    def full_name(self):
        return self._full_name if self._full_name else self.key

    @property
    def help_text(self):
        return self._help_text

    @property
    def default(self):
        return self._default

    @property
    def required(self):
        return self._required

    def webform_field(self, caller=None):
        return None


class TextField(Paxfield):
    """
    This field contains text of a given potential maximum length, and
    a regex against which it can be validated
    """

    def __init__(self, max_length=None, regex=None, required=False, default=None, **kwargs):
        super(TextField, self).__init__(**kwargs)
        self._max_length = max_length
        self._validator = regex
        self._required = required
        self._default = default
        self._value = None

    def set(self, value, caller=None):
        if value is None:
            self._value = None
            return True, None

        self._value = str(value)
        return self.validate(caller=caller)

    def get(self):
        if self._value:
            return self._value
        else:
            return self.default

    def validate(self, caller=None):
        if self.required and not self.get():
            return False, "Required field {} was not provided.  {}".format(self.full_name, self.help_text or "")

        if self.get() and (self._max_length and len(self.get()) > self._max_length):
            return False, "{} was longer than {} characters.".format(self.full_name, self._max_length)

        if self._validator:
            result = re.match(self._validator, self.get())
            if not result:
                return False, "{} had an invalid value.  {}".format(self.full_name, self.help_text or "")

        return True, None

    def webform_field(self, caller=None):
        options = {'label': self.full_name}
        if self.required is not None:
            options['required'] = self.required
        if self._max_length is None or self._max_length > 120:
            return django.forms.CharField(widget=django.forms.Textarea, **options)
        else:
            return django.forms.CharField(**options)


class IntegerField(Paxfield):

    def __init__(self, min_value=None, max_value=None, **kwargs):
        super(IntegerField, self).__init__(**kwargs)
        self._min_value = min_value
        self._max_value = max_value
        self._value = None

    def get(self):
        if self._value:
            return self._value
        else:
            return self.default

    def set(self, value, caller=None):
        try:
            if value is None:
                self._value = None
                return True, None

            self._value = int(value)
            return self.validate(caller=caller)
        except ValueError:
            return False, "{} must be an integer value. {}".format(self.full_name, self.help_text or "")

    def validate(self, caller=None):
        if self.required and not self.get():
            return False, "Required field {} was not provided. {}".format(self.full_name, self.help_text)

        if self._min_value and self.get() < self._min_value:
            return False, "{} was below the minimum value of {}. {}".format(self.full_name, self._min_value, self.help_text or "")

        if self._max_value and self.get() > self._max_value:
            return False, "{} was above the maximum value of {}. {}".format(self.full_name, self._max_value, self.help_text or "")

        return True, None

    def webform_field(self, caller=None):
        options = {'label': self.full_name}
        if self.required is not None:
            options['required'] = self.required
        return django.forms.IntegerField(**options)


class BooleanField(Paxfield):

    def __init__(self, **kwargs):
        super(BooleanField, self).__init__(**kwargs)
        self._value = None

    def get(self):
        if self._value is not None:
            return self._value
        else:
            return self.default

    def set(self, value, caller=None):
        if value is None:
            self._value = None
            return True, None

        lower_value = str(value).lower().strip(" ")
        self._value = False
        if lower_value in ["yes", "true", "on", "1"]:
            self._value = True
            return True, None
        elif lower_value in ["no", "false", "off", "0"]:
            self._value = False
            return True, None
        else:
            return False, "{} must be a yes/no value. {}".format(self.full_name, self.help_text or "")

    @staticmethod
    def get_display_params():
        return "[yes||no||true||false||0||1]"

    def validate(self, caller=None):
        if self.required and self.get() is None:
            return False, "Required field {} was left blank. {}".format(self.full_name, self.help_text or "")

        return True, None

    def webform_field(self, caller=None):
        options = {'label': self.full_name, 'required': False}
        return django.forms.BooleanField(**options)


class ChoiceField(Paxfield):

    def __init__(self, choices=None, **kwargs):
        super(ChoiceField, self).__init__(**kwargs)
        self._choices = choices
        self._value = None

    def get(self):
        if self._value is not None:
            return self._value
        else:
            return self.default

    def set(self, value, caller=None):
        for p in self._choices:
            if p[1].lower() == str(value).lower():
                self._value = p[0]
                return True, None
            if str(p[0]).lower() == str(value).lower():
                self._value = p[0]
                return True, None

        choices = [str(c[1]) for c in self._choices]
        choice_list = ", ".join(choices)
        return False, "{} must be one of the following values: {}.  {}".format(self.full_name, choice_list, self.help_text or "")

    def get_display(self):
        if self.get() is None:
            return "None"

        for p in self._choices:
            if p[0] == self.get():
                return p[1]

        return "None"

    def get_display_params(self):
        choices = "||".join(str(p[1]) for p in self._choices)
        return "[" + choices + "]"

    def validate(self, caller=None):
        if self.required and self.get() is None:
            return False, "Required field {} was left blank. {}".format(self.full_name, self.help_text or "")

        return True, ""

    def webform_field(self, caller=None):
        options = {'label': self.full_name}
        if self.required is not None:
            options['required'] = self.required
        options['choices'] = self._choices
        return django.forms.ChoiceField(**options)


class CharacterListField(Paxfield):
    """
    This field contains a list of character objects.
    """

    def __init__(self, required=False, allow_npc=False, **kwargs):
        super(CharacterListField, self).__init__(**kwargs)
        self._required = required
        self._value = None
        self._allow_npc = allow_npc

    def _get_character(self, args):
        from typeclasses.characters import Character
        try:
            if self._allow_npc:
                return Character.objects.get(db_key__iexact=args)
            else:
                return Character.objects.get(db_key__iexact=args, roster__isnull=False)
        except Character.DoesNotExist:
            return self._get_character_by_id(args)

    def _get_character_by_id(self, args):
        from typeclasses.characters import Character
        try:
            key = int(args)
            if self._allow_npc:
                return Character.objects.get(pk=key)
            else:
                return Character.objects.get(pk=key, roster__isnull=False)
        except (Character.DoesNotExist, ValueError):
            return None

    def set(self, value, caller=None):

        if value is None:
            self._value = None
            return True, None

        if hasattr(value, 'split'):
            value_list = value.split(",")
        else:
            value_list = value

        chars = []
        for char_name in value_list:
            char_obj = self._get_character(char_name.strip())
            if not char_obj:
                return False, "Could not find a character named %s." % char_name
            chars.append(char_obj.key)

        self._value = chars
        return self.validate(caller=caller)

    def get(self):
        if self._value:
            return self._value
        else:
            return self.default

    def get_display(self):
        values = self.get()
        if not values or len(values) == 0:
            return "None"

        results = []
        for value in values:
            char_obj = self._get_character(value)
            results.append(char_obj.key)

        return commafy(results)

    def get_display_params(self):
        return "<character1>[,character2...]"

    def validate(self, caller=None):
        if self.required and not self.get():
            return False, "Required field {} was not provided.  {}".format(self.full_name, self.help_text or "")

        return True, None

    def webform_field(self, caller=None):
        options = {'label': self.full_name}
        if self.required is not None:
            options['required'] = self.required
        return django.forms.CharField(**options)
