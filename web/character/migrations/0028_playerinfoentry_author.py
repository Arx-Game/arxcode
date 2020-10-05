# -*- coding: utf-8 -*-
# Generated by Django 1.11.16 on 2018-11-11 16:47
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("character", "0027_playerinfoentry_entry_date"),
    ]

    operations = [
        migrations.AddField(
            model_name="playerinfoentry",
            name="author",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
