# -*- coding: utf-8 -*-
# Generated by Django 1.11.7 on 2017-11-18 02:12
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("character", "0020_auto_20171109_2244"),
    ]

    operations = [
        migrations.CreateModel(
            name="Flashback",
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
                ("title", models.CharField(max_length=250, unique=True)),
                ("summary", models.TextField(blank=True)),
                ("db_date_created", models.DateTimeField(blank=True, null=True)),
                (
                    "allowed",
                    models.ManyToManyField(
                        blank=True,
                        related_name="allowed_flashbacks",
                        to="character.RosterEntry",
                    ),
                ),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="created_flashbacks",
                        to="character.RosterEntry",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="FlashbackPost",
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
                    "actions",
                    models.TextField(
                        blank=True,
                        help_text=b"The body of the post for your character's actions",
                    ),
                ),
                ("db_date_created", models.DateTimeField(blank=True, null=True)),
                (
                    "flashback",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="posts",
                        to="character.Flashback",
                    ),
                ),
                (
                    "poster",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="flashback_posts",
                        to="character.RosterEntry",
                    ),
                ),
                (
                    "read_by",
                    models.ManyToManyField(
                        blank=True,
                        related_name="read_flashback_posts",
                        to="character.RosterEntry",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
    ]
