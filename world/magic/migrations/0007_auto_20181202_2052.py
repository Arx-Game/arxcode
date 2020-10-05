# -*- coding: utf-8 -*-
# Generated by Django 1.11.15 on 2018-12-02 20:52
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("magic", "0006_auto_20181202_2018"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="condition",
            name="effect",
        ),
        migrations.AddField(
            model_name="condition",
            name="effects",
            field=models.ManyToManyField(
                related_name="_condition_effects_+", to="magic.Effect"
            ),
        ),
    ]
