# Generated by Django 4.1 on 2022-09-07 05:48

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('Authentication', '0004_user_role'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='Role',
            new_name='userRole',
        ),
    ]
