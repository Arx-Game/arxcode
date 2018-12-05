from .forms import Paxform
from commands.base import ArxCommand


class PaxformCommand(ArxCommand):

    form_class = None

    def __init__(self):
        super(ArxCommand, self).__init__()
        self._form = self.__class__.form_class()
        if not self.__doc__ or len(self.__doc__) == 0:
            self.__doc__ = self.__docstring
        self._extras = None

    @property
    def form(self):
        if not self._form:
            self._form = self.__class__.form_class()
        return self._form

    @property
    def __docstring(self):
        cls = self.__class__
        form = self._form
        if form is None or not isinstance(form, Paxform):
            return "Something has gone horribly wrong with this command, and we cannot generate a helpfile."
        result = "\n    "
        result += form.form_purpose or "A useful command."
        result += "\n\n"
        result += "    Usage:\n"
        result += "      {}/create\n".format(cls.key)
        result += "      {}/check\n".format(cls.key)
        for f in form.fields:
            result += "      {}/{} {}\n".format(cls.key, f.key, f.get_display_params())
        result += "      {}/cancel\n".format(cls.key)
        result += "      {}/submit\n".format(cls.key)
        result += "{}".format(form.form_description)
        return result

    def at_pre_cmd(self):
        form = self.form
        values = self.caller.attributes.get(form.key, default=None)
        self._extras = form.deserialize(values, caller=self.caller)

    def set_extra_field(self, key, value):
        if not key:
            raise ValueError
        form = self.form
        values = self.caller.attributes.get(form.key, default=None)
        if not value:
            del values[key]
        else:
            values[key] = value
        self.caller.attributes.add(form.key, values)

    def get_extra_field(self, key, default=None):
        if not key:
            raise ValueError

        values = self.caller.attributes.get(self.form.key, default=None)
        if key in values:
            return values[key]
        else:
            return default

    def display_extra_fields(self):
        pass

    def func(self):
        form = self.form
        values = self.caller.attributes.get(form.key, default=None)

        if form is None or not isinstance(form, Paxform):
            self.msg("Form not provided to command!  Please contact your administrator.")
            return

        if "create" in self.switches:
            self.msg("Creating form...")
            self.caller.attributes.add(form.key, {})
            result = ""
            for f in form.fields:
                if f.get() is not None or f.required:
                    result += "\n|w{}:|n {}".format(f.full_name, str(f.get_display()))
            if len(result):
                self.msg(result)
            return

        if values is None:
            self.msg("No form in progress.  Please use {}/create first!".format(self.cmdstring))
            return

        if "cancel" in self.switches:
            if self.caller.attributes.get(form.key) is None:
                self.msg("No {} session was in progress to cancel.".format(self.cmdstring))
                return
            self.msg("Cancelled.")
            self.caller.attributes.remove(form.key)
            return

        if "submit" in self.switches or "check" in self.switches:
            for f in form.fields:
                valid, reason = f.validate()
                if not valid:
                    self.msg(reason)
                    return

            validate_msg = form.validate(self.caller, values)
            if validate_msg:
                self.msg(validate_msg)
                return

            if "submit" in self.switches:
                form.submit(self.caller, values)
                self.caller.attributes.remove(form.key)
            return

        if len(self.switches) > 0:
            f = form.field_for_key(self.switches[0])
            if not f:
                self.msg("Unknown switch {}".format(self.switches[0]))
                return

            if not self.args:
                f.set(None, caller=self.caller)
                self.msg("{} cleared.".format(f.full_name))
            else:
                valid, reason = f.set(self.args, caller=self.caller)
                if not valid:
                    self.msg(reason)
                    return
                self.msg("{} set to: {}".format(f.full_name, f.get_display()))

            new_values = form.serialize()
            if self._extras:
                new_values.update(self._extras)
            self.caller.attributes.add(form.key, new_values)

        else:
            string = ""
            for f in form.fields:
                if f.get() is not None or f.required:
                    string += "\n|w{}:|n {}".format(f.full_name, str(f.get_display()))
            if string == "":
                self.msg("Your form appears to be empty!")
            else:
                self.msg(string)
                self.display_extra_fields()
            return
