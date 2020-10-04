# -*- coding: utf-8 -*-
# Generated by Django 1.11.15 on 2018-11-20 18:22
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dominion", "0035_auto_20180831_0922"),
        ("character", "0031_auto_20181116_1219"),
    ]

    operations = [
        migrations.AddField(
            model_name="theory",
            name="plots",
            field=models.ManyToManyField(
                blank=True, related_name="theories", to="dominion.Plot"
            ),
        ),
    ]
