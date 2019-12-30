# -*- coding: utf-8 -*-
# Generated by Django 1.9.9 on 2017-05-16 04:58
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('dominion', '0010_auto_20170511_0645'),
        ('character', '0010_auto_20170514_0639'),
    ]

    operations = [
        migrations.CreateModel(
            name='LoreTopic',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255, unique=True)),
                ('desc', models.TextField(blank=True, verbose_name='GM Notes about this Lore Topic')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='SearchTag',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255, unique=True)),
                ('topic', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='character.LoreTopic')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.RemoveField(
            model_name='clue',
            name='investigation_tags',
        ),
        migrations.AddField(
            model_name='clue',
            name='allow_sharing',
            field=models.BooleanField(default=True, help_text='Can be shared'),
        ),
        migrations.AddField(
            model_name='clue',
            name='event',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='clues', to='dominion.RPEvent'),
        ),
        migrations.AlterField(
            model_name='cluediscovery',
            name='discovery_method',
            field=models.CharField(blank=True, help_text='How this was discovered - exploration, trauma, etc', max_length=255),
        ),
        migrations.AddField(
            model_name='clue',
            name='search_tags',
            field=models.ManyToManyField(blank=True, db_index=True, null=True, to='character.SearchTag'),
        ),
    ]
