# Generated by Django 4.1 on 2022-08-29 10:24

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('invoice', '0012_alter_salesoderheader_billcash_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='salesoderheader',
            name='totalweight',
        ),
        migrations.AddField(
            model_name='salesoderheader',
            name='tds194q1',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='TDS 194 @'),
        ),
        migrations.AddField(
            model_name='salesoderheader',
            name='totalgst',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='totalgst'),
        ),
        migrations.AddField(
            model_name='salesoderheader',
            name='totalquanity',
            field=models.DecimalField(blank=True, decimal_places=2, default=0, max_digits=10, verbose_name='totalquanity'),
        ),
        migrations.AlterField(
            model_name='salesoderheader',
            name='totalpieces',
            field=models.IntegerField(blank=True, default=0, verbose_name='totalpieces'),
        ),
    ]