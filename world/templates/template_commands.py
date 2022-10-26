from server.utils import arx_more
from server.utils.prettytable import PrettyTable
from world.templates.models import Template, TemplateGrantee
from typeclasses.characters import Character

from paxforms.paxform_commands import PaxformCommand
from paxforms.forms import Paxform
from paxforms import fields


class TemplateForm(Paxform):

    form_key = "template_form"

    form_purpose = """
    Manages templates which store ASCII or text details. Once a template
    has been submitted, the description is immutable. By default, only the
    template creator can see their template (or use them). However, each
    of the access settings, however, they may grant access to individuals,
    as long as access control is set to 'RESTRICTED' and everyone can
    see templates with 'OPEN' access control. When changing from 'RESTRICTED'
    to 'OPEN' or 'PRIVATE' all previous grantees of the template are removed.

    The markup tag, of the form [[TEMPLATE_<id>]] can be inserted into a
    description (if you have access to it). Attempting to do so without
    access (or if it does not exist) will raise an error.

    When an object with a markup tag is looked at, the markup resolves
    to the description associated with template.
    
    Once a template has been created, it cannot be changed. A template
    can be deleted, however, if it has not been applied to an object.

    The @study command, however, will NOT resolve the template markup.
    """

    form_description = """
    
    Non-form switches:
      +template/grant <playername to grant use of the template>=<template_id>
      +template/revoke <playername to remove use of the template from>=<template_id>
      +template/list 
      +template/grantees <id of template you want the list of grantees for>
      +template/markup <id of template you want markup for>
      +template/change_access <id of template to change>=<[PRIVATE||RESTRICTED||OPEN]>
      +template/delete <id of template to delete>
      +template <id of template you want details on>
    """

    desc = fields.TextField(
        required=True,
        full_name="Description",
        help_text="ASCII or description to map into the template.",
    )
    access_level = fields.ChoiceField(
        choices=Template.ACCESS_LEVELS,
        full_name="Access Level",
        default="PR",
        required=True,
        help_text="""
            open: Anyone can use this template!
            restricted: Access to use the template has to be granted on a character by character basis
            private: Cannot grant access to this template. (When changing to this access level ALL extent permissions are cleared) 
    """,
    )

    title = fields.TextField(
        max_length=255,
        required=True,
        full_name="Title",
        help_text="Brief description of the template to be shown",
    )

    attribution = fields.TextField(
        max_length=60,
        required=True,
        full_name="Attribution",
        help_text="Name (or pseudonym, etc) to be used as the owner of the template.",
    )

    apply_attribution = fields.BooleanField(
        required=True,
        default=False,
        full_name="Show Attribution",
        help_text="Whether or not to show attribution.",
    )

    def submit(self, caller, values):
        template = Template(
            owner=caller.roster.current_account,
            title=values["title"],
            access_level=values["access_level"],
            apply_attribution=values["apply_attribution"],
            attribution=values["attribution"],
            desc=values["desc"],
        )
        template.save()
        caller.msg(
            "Created new template. Markup tag to use is: {}".format(template.markup())
        )


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
                try:
                    template = Template.objects.filter(id=args)[:1].get()

                    if template.is_accessible_by(self.caller):
                        self.msg(self.display(template))
                    else:
                        self.msg("You do not have access to a template with that id.")
                except (Template.DoesNotExist, ValueError):
                    self.msg("You do not have access to a template with that id.")
        elif "list" in self.switches:
            self.list(self.caller)
        elif "delete" in self.switches:
            template = self.find_template(args)

            if not template:
                return
            elif template.in_use():
                self.msg("You cannot delete a template that is in use!")
            else:
                id = template.id
                template.delete()
                self.msg("Deleted template {}".format(id))
        elif "grant" in self.switches:
            template, char = self.char_and_template_for_access()

            if not template or not char:
                return

            if char == self.caller:
                self.msg("You cannot grant yourself access to a template.")
                return

            grantees = TemplateGrantee.objects.filter(
                grantee=char.roster, template=template
            )

            if grantees.exists():
                self.msg(
                    "{} already has access to {}.".format(char.name, template.markup())
                )
            else:
                TemplateGrantee(grantee=char.roster, template=template).save()
                self.msg(
                    "You have granted {} access to {}.".format(
                        char.name, template.markup()
                    )
                )
        elif "revoke" in self.switches:
            template, char = self.char_and_template_for_access()

            if not template or not char:
                return

            grantees = TemplateGrantee.objects.filter(
                grantee=char.roster, template=template
            )

            if grantees.exists():
                grantees.first().delete()
                self.msg(
                    "You have revoked {}'s access to {}.".format(
                        char.name, template.markup()
                    )
                )
            else:
                self.msg(
                    "{} does not have access to {}.".format(
                        char.name, template.markup()
                    )
                )
        elif "change_access" in self.switches:
            access_level = self.parse_access_levels(self.rhs)

            if not access_level:
                self.msg("{} is not a valid access level.".format(self.rhs))
                return

            template = self.find_template(self.lhs)

            if not template:
                return
            elif template.access_level == access_level:
                self.msg("The template already has that access level.")
                return
            elif template.access_level == "RS":
                template.grantees.clear()

            template.access_level = access_level
            template.save()

            self.msg("You have changed the access level to {}.".format(self.rhs))
        elif "markup" in self.switches:
            if not args:
                self.msg("Which template do you want markup for?")
            else:
                templates = Template.objects.accessible_by(self.caller).filter(id=args)
                if templates.exists():
                    self.msg(templates.first().markup())
                else:
                    self.msg("You do not have access to a template with that id.")
        elif "grantees" in self.switches:
            if not args:
                self.msg("Which template do you want to get the list of grantees for?")
            else:
                template = self.find_template(args)
                if not template:
                    return
                if template.access_level == "OP":
                    self.msg(
                        "Everyone has access to this template. It has an OPEN access level."
                    )
                elif template.access_level == "PR":
                    self.msg(
                        "No one but you has access to this template. It has a PRIVATE access level."
                    )
                else:
                    self.msg(
                        "Current grantees: {}".format(
                            ", ".join(
                                [
                                    entry.character.name
                                    for entry in template.grantees.all()
                                ]
                            )
                        )
                    )

        elif "desc" in self.switches:
            if "[[TEMPLATE_" in args:
                self.msg("Templates cannot be nested.")
                return
            super(CmdTemplateForm, self).func()
        else:
            super(CmdTemplateForm, self).func()

    def char_and_template_for_access(self):
        try:
            char = Character.objects.filter(db_key=self.lhs)[:1].get()
        except Character.DoesNotExist:
            self.msg(self.lhs + " does not exist.")
            return [None, None]

        template = self.find_template(self.rhs)

        if template and template.access_level != "RS":
            template = None
            self.msg(
                "Template must have access level of RESTRICTED to modify grantees."
            )

        return [template, char]

    def find_template(self, id):
        try:
            template = Template.objects.filter(
                id=id, owner=self.caller.roster.current_account
            )[:1].get()
        except (Template.DoesNotExist, ValueError):
            self.msg("You do not own a template with that id.")
            template = None
        return template

    def list(self, caller):
        table = PrettyTable(
            [
                "{wId{n",
                "{wName{n",
                "{wAttribution{n",
                "{wMarkup{n",
                "{wAccess Level{n",
                "{wIn Use{n",
            ]
        )

        for template in Template.objects.accessible_by(self.caller):
            attribution = template.attribution if template.apply_attribution else ""

            in_use = "TRUE" if template.in_use() else "FALSE"

            if template.owner != self.caller.roster.current_account:
                in_use = ""

            access_level = ""

            for var in Template.ACCESS_LEVELS:
                if template.access_level == var[0]:
                    access_level = var[1]

            table.add_row(
                [
                    template.id,
                    template.title,
                    attribution,
                    template.markup(),
                    access_level,
                    in_use,
                ]
            )
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
