from __future__ import unicode_literals
from mock import Mock
from evennia.commands.default.tests import CommandTest
from . import commands, forms, fields


class TestForm(forms.Paxform):

    form_key = "testform"
    form_purpose = "To test Paxforms."
    form_description = '''
    This command exists solely to test Paxforms and make certain they work.
    '''

    choice_list = [
        (1, 'Choice1'),
        (2, 'Choice2'),
        (3, 'Choice3')
    ]

    one = fields.TextField(max_length=20, required=True)
    two = fields.IntegerField(min_value=5, max_value=15, default=10, required=True)
    three = fields.ChoiceField(choices=choice_list, default=2, required=True)
    four = fields.BooleanField(required=True)

    def submit(self, caller, values):
        caller.msg("Submitted successfully!")


class CmdTestForm(commands.PaxformCommand):

    key = "@testform"
    locks = "cmd:all()"
    form_class = TestForm


class TestFormCommand(CommandTest):

    def test_form_command(self):
        self.call(CmdTestForm(), "", "No form in progress.  Please use @testform/create first!")
        self.call(CmdTestForm(), "/create",
                                 "Creating form...|"
                                 "one: None|"
                                 "two: 10|"
                                 "three: Choice2|"
                                 "four: None")
        self.call(CmdTestForm(), "/one 1234567890123456789012345", "one was longer than 20 characters.")
        self.call(CmdTestForm(), "/one Test Field", "one set to: Test Field")
        self.call(CmdTestForm(), "/two 10", "two set to: 10")
        self.call(CmdTestForm(), "/submit", "Required field four was left blank. ")
        self.call(CmdTestForm(), "/three Choice1", "three set to: Choice1")
        self.call(CmdTestForm(), "/four yes", "four set to: yes")
        self.call(CmdTestForm(), "/submit", "Submitted successfully!")
        cmd = CmdTestForm()
        docstring = cmd.__doc__
        assert (docstring == '''
    To test Paxforms.

    Usage:
      @testform/create
      @testform/one [value]
      @testform/two [value]
      @testform/three [Choice1||Choice2||Choice3]
      @testform/four [yes||no||true||false||0||1]
      @testform/cancel
      @testform/submit

    This command exists solely to test Paxforms and make certain they work.
    ''')
