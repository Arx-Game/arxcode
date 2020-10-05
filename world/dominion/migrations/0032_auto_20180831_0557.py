# -*- coding: utf-8 -*-
# Generated by Django 1.11.7 on 2018-08-31 05:57
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dominion", "0031_auto_20180804_2115"),
    ]

    operations = [
        migrations.AddField(
            model_name="reputation",
            name="date_gossip_set",
            field=models.DateTimeField(null=True),
        ),
        migrations.AddField(
            model_name="reputation",
            name="favor",
            field=models.IntegerField(
                default=0,
                help_text=b"A percentage of the org's prestige applied to player's propriety.",
            ),
        ),
        migrations.AddField(
            model_name="reputation",
            name="npc_gossip",
            field=models.TextField(blank=True),
        ),
    ]
