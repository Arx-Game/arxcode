# Generated by Django 2.2.9 on 2019-12-28 14:17

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('msgs', '0008_auto_20181207_1843'),
    ]

    operations = [
        migrations.AlterField(
            model_name='inform',
            name='message',
            field=models.TextField(verbose_name='Information sent to player or org'),
        ),
    ]
