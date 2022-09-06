# Generated by Django 4.0.4 on 2022-08-06 13:47

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Authentication', '0004_remove_rolepriv_mainmenu_rolepriv_mainmenu_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='rolepriv',
            name='mainmenu',
        ),
        migrations.AddField(
            model_name='rolepriv',
            name='mainmenu',
            field=models.ManyToManyField(null=True, related_name='mainmenus', to='Authentication.mainmenu'),
        ),
    ]