# -*- coding: utf-8 -*-
# Generated by Django 1.11.8 on 2018-10-27 18:23
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("weather", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="weatheremit",
            name="weight",
            field=models.PositiveIntegerField(default=10, verbose_name=b"Weight"),
        ),
    ]
