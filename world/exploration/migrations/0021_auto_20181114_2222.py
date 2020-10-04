# -*- coding: utf-8 -*-
# Generated by Django 1.11.16 on 2018-11-14 22:22
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("exploration", "0020_auto_20181114_2113"),
    ]

    operations = [
        migrations.AlterField(
            model_name="generatedlootfragment",
            name="fragment_type",
            field=models.PositiveSmallIntegerField(
                choices=[
                    (0, b"Adjective"),
                    (1, b"Bauble Material"),
                    (2, b"Type of Item"),
                    (3, b"Name fragment (first)"),
                    (4, b"Name fragment (second)"),
                    (5, b"Name fragment (prefix)"),
                    (6, b"Small Weapon Type"),
                    (7, b"Medium Weapon Type"),
                    (8, b"Huge Weapon Type"),
                    (9, b"Archery Weapon Type"),
                    (10, b"Weapon Descriptor"),
                    (11, b"Weapon Decoration"),
                    (12, b"Weapon Element"),
                ],
                default=0,
            ),
        ),
    ]
