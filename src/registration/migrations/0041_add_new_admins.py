# Generated by Django 2.2.11 on 2020-03-14 12:35

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('registration', '0040_delete_old_admins'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='admins',
            field=models.ManyToManyField(blank=True, through='registration.EventAdminRoles', to=settings.AUTH_USER_MODEL),
        ),
    ]