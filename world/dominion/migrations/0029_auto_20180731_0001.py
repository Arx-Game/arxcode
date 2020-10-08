# -*- coding: utf-8 -*-
# Generated by Django 1.11.7 on 2018-07-31 00:01
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("dominion", "0028_auto_20180728_0224"),
    ]

    operations = [
        migrations.CreateModel(
            name="Fealty",
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
                ("name", models.CharField(max_length=200, unique=True)),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.AddField(
            model_name="organization",
            name="fealty",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="orgs",
                to="dominion.Fealty",
            ),
        ),
    ]
