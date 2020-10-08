# -*- coding: utf-8 -*-
# Generated by Django 1.11.7 on 2018-08-04 21:15
from __future__ import unicode_literals

from django.db import migrations, models


def convert_modifiers_to_influence(apps, schema_editor):
    from django.db.models import F

    Organization = apps.get_model("dominion", "Organization")
    Organization.objects.update(
        economic_influence=3000 * F("economic_modifier") * F("economic_modifier"),
        social_influence=3000 * F("social_modifier") * F("social_modifier"),
        military_influence=3000 * F("military_modifier") * F("military_modifier"),
    )


class Migration(migrations.Migration):

    dependencies = [
        ("dominion", "0030_auto_20180804_1530"),
    ]

    operations = [
        migrations.AddField(
            model_name="member",
            name="investment_this_week",
            field=models.SmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="member",
            name="investment_total",
            field=models.SmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="organization",
            name="economic_influence",
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name="organization",
            name="military_influence",
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name="organization",
            name="social_influence",
            field=models.IntegerField(default=0),
        ),
        migrations.AlterField(
            model_name="organization",
            name="base_support_value",
            field=models.SmallIntegerField(default=5),
        ),
        migrations.AlterField(
            model_name="organization",
            name="member_support_multiplier",
            field=models.SmallIntegerField(default=5),
        ),
        migrations.RunPython(convert_modifiers_to_influence),
        migrations.RemoveField(
            model_name="organization",
            name="economic_modifier",
        ),
        migrations.RemoveField(
            model_name="organization",
            name="military_modifier",
        ),
        migrations.RemoveField(
            model_name="organization",
            name="social_modifier",
        ),
    ]
