# -*- coding: utf-8 -*-
# Generated by Django 1.9.9 on 2016-11-02 02:55
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("objects", "0005_auto_20150403_2339"),
        ("character", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="InvestigationAssistant",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "currently_helping",
                    models.BooleanField(
                        default=True, help_text=b"Whether they're currently helping out"
                    ),
                ),
                (
                    "stat_used",
                    models.CharField(
                        blank=True,
                        default="perception",
                        help_text="The stat the player chose to use",
                        max_length=80,
                    ),
                ),
                (
                    "skill_used",
                    models.CharField(
                        blank=True,
                        default="investigation",
                        help_text="The skill the player chose to use",
                        max_length=80,
                    ),
                ),
                (
                    "actions",
                    models.TextField(
                        blank=True,
                        help_text="The writeup the player submits of their actions, used for GMing.",
                    ),
                ),
                (
                    "char",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="assisted_investigations",
                        to="objects.ObjectDB",
                    ),
                ),
                (
                    "investigation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="assistants",
                        to="character.Investigation",
                    ),
                ),
            ],
        ),
    ]
