

from server.utils import arx_more
from server.utils.prettytable import PrettyTable
from .models import Template, TemplateGrantee
from typeclasses.characters import Character

from paxforms.commands import PaxformCommand
from paxforms.forms import Paxform
from paxforms import fields


class TemplateForm(Paxform):

    form_key = "template_form"

    form_purpose = """Manages templates which are used to store ASCII or text details. Once
    a template is 'saved', the description is immutable. Access control to
    use the template can be managed after creation, however. Once created,
    the markup tag can be input into a description (for crafting or writing)
    and will evaluate to the description at hand.

    @study however, will only return the value of the markup tag!
    """

    form_description = """
    
    Non-form switches:
      +template/grant <template_id>=<playername to grant use of the template>
      +template/revoke <template_id>=<playername to remove use of the template from>
      +template/list 
      +template/grantees <id of template you want the list of grantees for>
      +template/markup <id of template you want markup for>
      +template <id of template you want details on>
    """

    desc = fields.TextField(required=True, full_name="Description", help_text="ASCII or description to map into the template.")
    access_level = fields.ChoiceField(choices=Template.ACCESS_LEVELS, full_name="Access Level", default='PR', required=True, help_text="""
            open: Anyone can use this template!
            restricted: Access to use the template has to be granted on a character by character basis
            private: Cannot grant access to this template. (When changing to this access level ALL extent permissions are cleared) 
    """)

    title = fields.TextField(max_length=255, required=True, full_name="Title", help_text="Brief description of the template to be shown")

    attribution = fields.TextField(max_length=60, required=True, full_name="Attribution", help_text="Name (or pseudonym, etc) to be used as the owner of the template.")

    apply_attribution = fields.BooleanField(required=True, default=False, full_name="Show Attribution", help_text="Whether or not to show attribution.")

    def submit(self, caller, values):

        template = Template(
            owner=caller.roster.current_account,
            title=values['title'],
            access_level=values['access_level'],
            apply_attribution=values['apply_attribution'],
            attribution=values['attribution'],
            desc=values['desc']
        )
        template.save()
        caller.msg("Created new template. Markup tag to use is: {}".format(template.markup()))


class CmdTemplateForm(PaxformCommand):
    key = "+template"
    alias = "template"
    locks = "cmd:all()"
    form_class = TemplateForm

    help_category = "crafting"

    def func(self):
        args = self.args

        if not self.switches:
            if not args:
                super(CmdTemplateForm, self).func()
            else:
                template = self.find_template(args)
                if template:
                    self.caller.msg(self.display(template))
        elif "list" in self.switches:
            self.list(self.caller)
        elif "grant" in self.switches:
            template, char = self.char_and_template_for_access()

            if not template or not char:
                return

            grantees = TemplateGrantee.objects.filter(grantee=char.roster, template=template)

            if grantees.exists():
                self.caller.msg("{} already has access to {}.".format(char.name, template.markup()))
            else:
                TemplateGrantee(grantee=char.roster, template=template).save()
                self.caller.msg("You have granted {} access to {}.".format(char.name, template.markup()))
        elif "revoke" in self.switches:
            template, char = self.char_and_template_for_access()

            if not template or not char:
                return

            grantees = TemplateGrantee.objects.filter(grantee=char.roster, template=template)

            if grantees.exists():
                grantees.first().delete()
                self.caller.msg("You have revoked {}'s access to {}.".format(char.name, template.markup()))
            else:
                self.caller.msg("{} does not have access to {}.".format(char.name, template.markup()))
        elif "change_access" in self.switches:
            access_level = self.parse_access_levels(self.rhs)

            if not access_level:
                self.caller.msg("{} is not a valid access level.".format(self.rhs))
                return

            template = self.find_template(self.lhs)

            if not template:
                return
            elif template.access_level == access_level:
                self.caller.msg("The template already has that access level.")
                return
            elif template.access_level == 'RS':
                template.grantees.clear()

            template.access_level = access_level
            template.save()

            self.caller.msg("You have changed the access level to {}.".format(self.rhs))
        elif "markup" in self.switches:
            if not args:
                self.caller.msg("Which template do you want markup for?")
            else:
                templates = Template.objects.accessible_by(self.caller).filter(id=args)
                if templates.exists():
                    self.caller.msg(templates.first().markup())
                else:
                    self.caller.msg("You do not have access to a template with that id.")
        elif "grantees" in self.switches:
            if not args:
                self.caller.msg("Which template do you want to get the list of grantees for?")
            else:
                template = self.find_template(args)
                if not template:
                    return
                if template.access_level == 'OP':
                    self.caller.msg("Everyone has access to this template. It has an OPEN access level.")
                elif template.access_level == 'PR':
                    self.caller.msg("No one but you has access to this template. It has a PRIVATE access level.")
                else:
                    self.caller.msg("Current grantees: {}".format(
                       ", ".join([entry.character.name for entry in template.grantees.all()])
                    ))

        elif "desc" in self.switches:
            if "[[TEMPLATE_" in args:
                self.caller.msg("Templates cannot be nested.")
                return
            super(CmdTemplateForm, self).func()
        else:
            super(CmdTemplateForm, self).func()

    def char_and_template_for_access(self):
        try:
            char = Character.objects.filter(db_key=self.lhs)[:1].get()
        except Character.DoesNotExist:
            self.caller.msg(self.lhs + " does not exist.")
            return [None, None]

        template = self.find_template(self.rhs)

        if template and template.access_level != 'RS':
            template = None
            self.caller.msg("Template must have access level of RESTRICTED to modify grantees.")

        return [template, char]

    def find_template(self, id):
        try:
            template = Template.objects.filter(id=id, owner=self.caller.roster.current_account)[:1].get()
        except (Template.DoesNotExist, ValueError):
            self.caller.msg("You do not own a template with that id.")
            template = None
        return template

    def list(self, caller):
        table = PrettyTable(["{wId{n", "{wName{n", "{wAttribution{n", "{wMarkup{n"])

        for template in Template.objects.accessible_by(self.caller):
            attribution = template.attribution if template.apply_attribution else ""
            table.add_row([template.id, template.title, attribution, template.markup()])
        arx_more.msg(caller, str(table), justify_kwargs=False)

    def display(self, template):
        """Returns string display of the template with ansi markup"""
        attribution = template.attribution if template.apply_attribution else ""
        msg = "{wCreator{n: %s\n" % attribution
        msg += "{wDesc{n: %s\n" % template.desc
        return msg

    def parse_access_levels(self, value):
        for var in Template.ACCESS_LEVELS:
            if value.strip().lower() == var[1].lower():
                return var[0]

