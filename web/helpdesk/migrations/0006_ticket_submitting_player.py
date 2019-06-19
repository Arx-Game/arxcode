# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('helpdesk', '0005_auto_20151214_0208'),
    ]

    operations = [
        migrations.AddField(
            model_name='ticket',
            name='submitting_player',
            field=models.ForeignKey(related_name='tickets',
                                    verbose_name='Player who opened this ticket',
                                    blank=True,
                                    to=settings.AUTH_USER_MODEL,
                                    null=True,
                                    on_delete=models.CASCADE),
        ),
    ]
