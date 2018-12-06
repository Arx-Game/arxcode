from .fields import Paxfield
import django


class Paxform(object):

    def __init__(self):
        if self.__class__.form_key is None:
            raise ValueError

        for k, v in self.__class__.__dict__.iteritems():
            if isinstance(v, Paxfield):
                v.set_key(k)
                setattr(self, k, v)

    @property
    def key(self):
        return "paxform_" + self.__class__.form_key

    @property
    def fields(self):
        result = []
        for k, v in self.__dict__.iteritems():
            if isinstance(v, Paxfield):
                result.append(v)

        result.sort(key=lambda f: f._priority, reverse=True)
        return result

    @property
    def keys(self):
        fields = self.fields
        return [f.key for f in fields]

    def field_for_key(self, key):
        for k, v in self.__dict__.iteritems():
            if isinstance(v, Paxfield):
                if v.key == key:
                    return v

        return None

    def set(self, key=None, value=None, caller=None):
        if not key:
            return False

        f = self.field_for_key(key)
        if not f:
            return False

        return f.set(value, caller=caller)

    def serialize(self):
        serialized = {}
        for k, v in self.__dict__.iteritems():
            if isinstance(v, Paxfield):
                v.serialize(serialized)

        return serialized

    def deserialize(self, serialized, caller=None):
        for f in self.fields:
            f.set(None, caller=caller)

        extras = {}
        if serialized:
            extras = dict(serialized)
            for k, v in serialized.iteritems():
                f = self.field_for_key(k)
                if f is not None:
                    f.set(v, caller=caller)
                    del extras[k]

        return extras

    def validate(self, caller, values):
        return None

    def submit(self, caller, values):
        pass

    @property
    def web_form(self, caller=None):
        web_fields = {}
        for f in self.fields:
            web_fields[f.key] = f.webform_field(caller=caller)

        new_class = type("PaxWebform_" + self.key, (django.forms.Form,), web_fields)
        return new_class

    def from_web_form(self, webform, caller=None):
        for f in self.fields:
            value = webform.cleaned_data[f.key]
            valid, message = f.set(value, caller=caller)
            if not valid:
                return False, message
        return True, None
