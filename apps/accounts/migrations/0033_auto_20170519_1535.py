# -*- coding: utf-8 -*-
# Generated by Django 1.9.5 on 2017-05-19 15:35
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0032_auto_20170519_1322'),
    ]

    operations = [
        migrations.AddField(
            model_name='userregistercode',
            name='valid',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='requestinvite',
            name='first_name',
            field=models.CharField(default='', max_length=150),
        ),
        migrations.AlterField(
            model_name='requestinvite',
            name='last_name',
            field=models.CharField(default='', max_length=150),
        ),
        migrations.AlterField(
            model_name='userregistercode',
            name='code',
            field=models.CharField(db_index=True, max_length=30),
        ),
    ]
