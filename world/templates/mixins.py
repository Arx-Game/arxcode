"""
This class provides utilities for working with templates.
"""

import re
from world.templates.models import Template


class TemplateMixins(object):
    template_regex_obj = re.compile("(\[\[TEMPLATE_\d+\]\])")
    template_id_regex_obj = re.compile("\[\[TEMPLATE_(\d+)\]\]")

    def find_templates(self, string):
        return re.findall(self.template_regex_obj, string)

    def find_template_ids(self, string):
        return re.findall(self.template_id_regex_obj, string)

    def replace_template_values(self, string, templates):
        escape = lambda e: "".join("\\" + c if c in "\\" or c == "\\" else c for c in e)
        work_string = string
        for template in templates:
            work_string = re.sub(re.escape(template.markup()), escape(template.desc), work_string)
        return work_string

    def can_apply_templates(self, caller, desc):
        template_ids = self.find_template_ids(desc)

        if len(template_ids) > 0:
            templates = Template.objects.in_list(self.find_template_ids(desc))

            unusable_templates = filter(lambda t: not t.is_accessible_by(caller), templates)
            unusable_templates = list(map(lambda t: t.markup(), unusable_templates))

            if unusable_templates:
                err_msg = "You attempted to add the following templates that you do not have access to: "
                err_msg += ", ".join(unusable_templates)
                err_msg += " to your desc."
                caller.msg(err_msg)
                return False
        return True

    def apply_templates_to(self, obj):
        template_ids = self.find_template_ids(obj.desc)

        if len(template_ids) > 0:
            templates = Template.objects.in_list(template_ids)

            for template in templates:
                template.applied_to.add(obj)

