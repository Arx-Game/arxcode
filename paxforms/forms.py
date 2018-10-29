from .fields import Paxfield


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

        # Reverse our field order
        return result[::-1]

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

    def set(self, key=None, value=None):
        if not key:
            return False

        f = self.field_for_key(key)
        if not f:
            return False

        return f.set(value)

    def serialize(self):
        serialized = {}
        for k, v in self.__dict__.iteritems():
            if isinstance(v, Paxfield):
                v.serialize(serialized)

        return serialized

    def deserialize(self, serialized):
        for f in self.fields:
            f.set(None)

        extras = dict(serialized)
        if serialized:
            for k, v in serialized.iteritems():
                f = self.field_for_key(k)
                if f is not None:
                    f.set(v)
                    del extras[k]

        return extras

    def submit(self, caller, values):
        pass

