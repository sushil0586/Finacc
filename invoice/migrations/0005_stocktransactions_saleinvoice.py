# Generated by Django 4.1 on 2022-08-14 07:55

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('invoice', '0004_alter_stocktransactions_debitamount'),
    ]

    operations = [
        migrations.AddField(
            model_name='stocktransactions',
            name='saleinvoice',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='invoice.salesoderheader', verbose_name='salesorder'),
        ),
    ]