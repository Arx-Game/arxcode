# -*- coding: utf-8 -*-
# Generated by Django 1.11.16 on 2018-11-15 22:18
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("exploration", "0028_auto_20181115_2119"),
    ]

    operations = [
        migrations.AddField(
            model_name="shardhavenobstacle",
            name="clue_success",
            field=models.TextField(blank=True, null=True),
        ),
    ]
