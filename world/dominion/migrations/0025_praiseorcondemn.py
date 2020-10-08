# -*- coding: utf-8 -*-
# Generated by Django 1.11.10 on 2018-03-10 09:58
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("dominion", "0024_charitabledonation"),
    ]

    operations = [
        migrations.CreateModel(
            name="PraiseOrCondemn",
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
                ("message", models.TextField(blank=True)),
                ("week", models.PositiveSmallIntegerField(blank=0, default=0)),
                ("db_date_created", models.DateTimeField(auto_now_add=True)),
                ("value", models.IntegerField(default=0)),
                (
                    "number_used",
                    models.PositiveSmallIntegerField(
                        default=1,
                        help_text=b"Number of praises/condemns used from weekly pool",
                    ),
                ),
                (
                    "praiser",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="praises_given",
                        to="dominion.PlayerOrNpc",
                    ),
                ),
                (
                    "target",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="praises_received",
                        to="dominion.PlayerOrNpc",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
    ]
