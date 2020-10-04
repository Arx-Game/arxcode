# -*- coding: utf-8 -*-
# Generated by Django 1.11.16 on 2018-11-11 20:07
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("character", "0028_playerinfoentry_author"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="accounthistory",
            options={
                "verbose_name": "Played Character",
                "verbose_name_plural": "Played Characters",
            },
        ),
        migrations.AlterModelOptions(
            name="playerinfoentry",
            options={"verbose_name_plural": "Info Entries"},
        ),
        migrations.AlterModelOptions(
            name="playersiteentry",
            options={"verbose_name_plural": "Site Entries"},
        ),
    ]
