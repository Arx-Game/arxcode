# -*- coding: utf-8 -*-
# Generated by Django 1.11.16 on 2018-11-11 16:21
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("character", "0026_playerinfoentry_playersiteentry"),
    ]

    operations = [
        migrations.AddField(
            model_name="playerinfoentry",
            name="entry_date",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
