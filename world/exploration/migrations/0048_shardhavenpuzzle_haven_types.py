# -*- coding: utf-8 -*-
# Generated by Django 1.11.15 on 2018-11-22 23:22
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("exploration", "0047_auto_20181122_2250"),
    ]

    operations = [
        migrations.AddField(
            model_name="shardhavenpuzzle",
            name="haven_types",
            field=models.ManyToManyField(
                related_name="denizens", to="exploration.ShardhavenType"
            ),
        ),
    ]
