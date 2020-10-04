# -*- coding: utf-8 -*-
# Generated by Django 1.11.15 on 2018-11-23 01:05
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("exploration", "0048_shardhavenpuzzle_haven_types"),
    ]

    operations = [
        migrations.AlterField(
            model_name="shardhavenpuzzle",
            name="haven_types",
            field=models.ManyToManyField(
                related_name="puzzles", to="exploration.ShardhavenType"
            ),
        ),
    ]
