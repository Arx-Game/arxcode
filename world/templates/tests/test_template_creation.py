"""
Tests for Conditions app
"""
# -*- coding: utf-8 -*-
from mock import Mock

from world.templates.models import Template, TemplateGrantee
from world.templates.template_commands import CmdTemplateForm
from web.character.models import PlayerAccount

from server.utils.prettytable import PrettyTable
from server.utils.test_utils import ArxCommandTest

from world.templates.mixins import TemplateMixins


class TemplateTests(ArxCommandTest, TemplateMixins):
    paccount1 = None
    paccount2 = None
    c1_template = None
    c2_template = None

    def setUp(self):
        super(ArxCommandTest, self).setUp()
        self.paccount1 = PlayerAccount.objects.create(email="myawesome_email@test.org")
        self.paccount2 = PlayerAccount.objects.create(
            email="myawesome_email_2@test.org"
        )

        self.char1.roster.current_account = self.paccount1
        self.char1.roster.save()

        self.char2.roster.current_account = self.paccount2
        self.char2.roster.save()

        self.char2.sessions.add(self.session)

        self.c1_template = self.create_template_for(
            self.paccount1, title="My Test Template"
        )
        self.c1_template.save()

        self.c2_template = self.create_template_for(
            self.paccount1,
            title="My Restricted Template",
            access_level="RS",
            apply_attribution=True,
        )
        self.c2_template.save()

    def test_owner_can_see_their_templates(self):
        self.setup_cmd(CmdTemplateForm, self.char1)
        self.call_cmd(
            "/list", self.create_table_view([self.c1_template, self.c2_template])
        )

    def test_other_player_cannot_see_private_templates(self):
        self.setup_cmd(CmdTemplateForm, self.char2)
        self.call_cmd("/list", self.create_table_view([]))

    def test_other_player_cannot_see_restricted_templates_where_they_do_not_have_access(
        self,
    ):
        restricted = self.create_template_for(
            self.paccount1, title="Other Template", access_level="RS"
        )
        restricted.save()

        self.setup_cmd(CmdTemplateForm, self.char2)
        self.call_cmd("/list", self.create_table_view([]))

        TemplateGrantee(grantee=self.char2.roster, template=restricted).save()
        restricted.save()

        self.setup_cmd(CmdTemplateForm, self.char2)
        self.call_cmd("/list", self.create_table_view([restricted]))

    def test_anyone_can_see_open_templates(self):
        open = self.create_template_for(
            self.paccount1, "Other Template", access_level="OP"
        )
        open.save()

        self.setup_cmd(CmdTemplateForm, self.char2)
        self.call_cmd("/list", self.create_table_view([open]))

    def test_can_create_a_template(self):
        self.setup_cmd(CmdTemplateForm, self.char2)
        self.call_cmd("/create", None)
        self.call_cmd("/title My Awesome Title", None)
        self.call_cmd("/desc My Awesome Desc", None)
        self.call_cmd("/attribution Bob", None)
        self.call_cmd("/access_level OPEN", None)
        self.call_cmd("/submit", None)

        template = Template.objects.filter(owner=self.paccount2)[0]

        self.assertEqual(template.access_level, "OP")
        self.assertEqual(template.desc, "My Awesome Desc")
        self.assertEqual(template.title, "My Awesome Title")
        self.assertEqual(template.attribution, "Bob")

    def test_cannot_nest_templates(self):
        self.setup_cmd(CmdTemplateForm, self.char2)
        self.call_cmd("/create", None)
        self.call_cmd(
            "/desc This is so awesome [[TEMPLATE_", "Templates cannot be nested."
        )

    def test_can_get_markup(self):
        self.setup_cmd(CmdTemplateForm, self.char1)
        self.call_cmd(
            "/markup {}".format(self.c1_template.id),
            "[[TEMPLATE_{}]]".format(self.c1_template.id),
        )
        self.setup_cmd(CmdTemplateForm, self.char1)
        self.call_cmd(
            "/markup 131".format(self.c1_template.id),
            "You do not have access to a template with that id.",
        )

    def test_can_grant_access_to_a_template(self):
        self.setup_cmd(CmdTemplateForm, self.char1)
        self.call_cmd(
            "/grant {}={}".format(self.char2.name, self.c2_template.id),
            "You have granted {} access to [[TEMPLATE_{}]].".format(
                self.char2.name, self.c2_template.id
            ),
        )
        self.call_cmd(
            "/grant {}={}".format(self.char1.name, self.c2_template.id),
            "You cannot grant yourself access to a template.",
        )
        self.call_cmd(
            "/grant {}={}".format(self.char2.name, self.c2_template.id),
            "{} already has access to [[TEMPLATE_{}]].".format(
                self.char2.name, self.c2_template.id
            ),
        )

        self.call_cmd(
            "/grant {}={}".format(self.char2.name, self.c1_template.id),
            "Template must have access level of RESTRICTED to modify grantees.",
        )

        self.setup_cmd(CmdTemplateForm, self.char2)
        self.call_cmd("/list", self.create_table_view([self.c2_template]))

        self.call_cmd(
            "/grant Char2=12312312312", "You do not own a template with that id."
        )
        self.call_cmd(
            "/grant Char-1={}".format(self.c2_template.id), "Char-1 does not exist."
        )

    def test_can_revoke_access_to_a_template(self):
        TemplateGrantee(grantee=self.char2.roster, template=self.c2_template).save()

        self.setup_cmd(CmdTemplateForm, self.char1)
        self.call_cmd(
            "/revoke {}={}".format(self.char2.name, self.c2_template.id),
            "You have revoked {}'s access to [[TEMPLATE_{}]].".format(
                self.char2.name, self.c2_template.id
            ),
        )

        self.call_cmd(
            "/grant {}={}".format(self.char2.name, self.c1_template.id),
            "Template must have access level of RESTRICTED to modify grantees.",
        )

        self.setup_cmd(CmdTemplateForm, self.char1)
        self.call_cmd(
            "/revoke {}={}".format(self.char2.name, self.c2_template.id),
            "{} does not have access to [[TEMPLATE_{}]].".format(
                self.char2.name, self.c2_template.id
            ),
        )

        self.setup_cmd(CmdTemplateForm, self.char2)
        self.call_cmd("/list", self.create_table_view([]))

        self.call_cmd(
            "/revoke Char2=12312312312", "You do not own a template with that id."
        )
        self.call_cmd(
            "/revoke Char-1={}".format(self.c2_template.id), "Char-1 does not exist."
        )

    def test_changing_access_from_restricted_to_private_clears_grantees(self):
        TemplateGrantee(grantee=self.char2.roster, template=self.c2_template).save()

        self.assertEqual(self.c2_template.grantees.count(), 1)

        self.setup_cmd(CmdTemplateForm, self.char1)
        self.call_cmd(
            "/change_access {}={}".format(self.c2_template.id, "PRIVATE"),
            "You have changed the access level to PRIVATE.",
        )

        self.assertEqual(self.c2_template.grantees.count(), 0)

        self.setup_cmd(CmdTemplateForm, self.char1)
        self.call_cmd(
            "/change_access {}={}".format(self.c2_template.id, "RESTRICTED"),
            "You have changed the access level to RESTRICTED.",
        )

        TemplateGrantee(grantee=self.char2.roster, template=self.c2_template).save()

        self.assertEqual(self.c2_template.grantees.count(), 1)

        self.setup_cmd(CmdTemplateForm, self.char1)
        self.call_cmd(
            "/change_access {}={}".format(self.c2_template.id, "OPEN"),
            "You have changed the access level to OPEN.",
        )

        self.assertEqual(self.c2_template.grantees.count(), 0)

    def test_can_get_list_of_grantees(self):
        self.setup_cmd(CmdTemplateForm, self.char1)
        self.call_cmd(
            "/grantees {}".format(self.c1_template.id),
            "No one but you has access to this template. It has a PRIVATE access level.",
        )

        self.c1_template.access_level = "OP"
        self.c1_template.save()

        self.call_cmd(
            "/grantees {}".format(self.c1_template.id),
            "Everyone has access to this template. It has an OPEN access level.",
        )

        self.c1_template.access_level = "RS"
        self.c1_template.save()

        TemplateGrantee(grantee=self.char2.roster, template=self.c1_template).save()

        self.call_cmd(
            "/grantees {}".format(self.c1_template.id),
            "Current grantees: {}".format(self.char2.name),
        )

        self.call_cmd(
            "/grantees", "Which template do you want to get the list of grantees for?"
        )

    def test_can_describe_template(self):
        self.setup_cmd(CmdTemplateForm, self.char1)
        self.call_cmd(
            "{}".format(self.c2_template.id),
            "Creator: {}\nDesc: {}".format(
                self.c2_template.attribution, self.c2_template.desc
            ),
        )

        self.setup_cmd(CmdTemplateForm, self.char2)
        self.call_cmd(
            "{}".format(self.c2_template.id),
            "You do not have access to a template with that id.",
        )

        TemplateGrantee(grantee=self.char2.roster, template=self.c2_template).save()

        self.call_cmd(
            "{}".format(self.c2_template.id),
            "Creator: {}\nDesc: {}".format(
                self.c2_template.attribution, self.c2_template.desc
            ),
        )

    def test_find_template_ids(self):
        template_1 = "[[TEMPLATE_1]]"
        template_2 = "[[TEMPLATE_21]]"
        string = "This is awesome. {}. We should see more values! Like {}.".format(
            template_1, template_2
        )

        self.assertEquals(
            set(self.find_templates(string)), set([template_2, template_1])
        )
        self.assertEquals(set(self.find_template_ids(string)), set(["1", "21"]))

    def test_find_templates_from_desc(self):
        desc = "this is my awesome desc! It has {} as well as {} in it!".format(
            self.c1_template.markup(), self.c2_template.markup()
        )

        self.assertEqual(
            set(Template.objects.in_list(self.find_template_ids(desc)).all()),
            set([self.c1_template, self.c2_template]),
        )

    def test_replace_desc(self):
        desc = "this is my awesome desc! It has {} as well as {} in it!".format(
            self.c1_template.markup(), self.c2_template.markup()
        )

        parsed_desc = "this is my awesome desc! It has {} as well as {} in it!".format(
            self.c1_template.desc, self.c2_template.desc
        )

        self.assertEqual(
            self.replace_template_values(
                desc, Template.objects.in_list(self.find_template_ids(desc)).all()
            ),
            parsed_desc,
        )

    def test_can_delete_if_not_in_use(self):
        other_template = self.create_template_for(
            self.paccount1,
            title="My Restricted Template",
            access_level="RS",
            apply_attribution=True,
        )
        other_template.save()

        id = other_template.id

        self.setup_cmd(CmdTemplateForm, self.char2)
        self.call_cmd(
            "/delete {}".format(id), "You do not own a template with that id."
        )

        self.assertEquals(Template.objects.filter(id=id).get(), other_template)

        self.setup_cmd(CmdTemplateForm, self.char1)
        self.call_cmd("/delete {}".format(id), "Deleted template {}".format(id))

        self.assertEquals(Template.objects.filter(id=id).count(), 0)

    def test_cannot_delete_if_in_use(self):
        other_template = self.create_template_for(
            self.paccount1,
            title="My Restricted Template",
            access_level="RS",
            apply_attribution=True,
        )
        other_template.save()

        id = other_template.id

        from evennia.utils import create

        typeclass = "typeclasses.readable.readable.Readable"

        book1 = create.create_object(
            typeclass=typeclass, key="book1", location=self.char1, home=self.char1
        )

        other_template.applied_to.add(book1)

        self.assertEquals(Template.objects.filter(id=id).get(), other_template)

        self.setup_cmd(CmdTemplateForm, self.char1)
        self.call_cmd(
            "/delete {}".format(id), "You cannot delete a template that is in use!"
        )

        self.assertEquals(Template.objects.filter(id=id).get(), other_template)

    def create_template_for(
        self,
        account,
        title="My Test Template",
        access_level="PR",
        apply_attribution=False,
    ):
        return Template(
            owner=account,
            desc="This is a templated description! It is so awesome",
            attribution="freddy",
            apply_attribution=apply_attribution,
            title=title,
            access_level=access_level,
        )

    def create_table_view(self, templates):
        table = PrettyTable(
            ["Id", "Name", "Attribution", "Markup", "Access Level", "In Use"]
        )
        for template in templates:
            attribution = template.attribution if template.apply_attribution else ""

            access_level = ""

            for var in Template.ACCESS_LEVELS:
                if template.access_level == var[0]:
                    access_level = var[1]

            in_use = "TRUE" if template.in_use() else "FALSE"

            if template.owner != self.caller.roster.current_account:
                in_use = ""

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
        return ArxCommandTest.format_returned_msg([str(table)], True)
