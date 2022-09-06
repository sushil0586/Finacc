# Generated by Django 4.1 on 2022-08-23 14:56

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('invoice', '0008_salesoderheader_tcs206c1ch3'),
    ]

    operations = [
        migrations.AlterField(
            model_name='stocktransactions',
            name='creditamount',
            field=models.DecimalField(decimal_places=2, max_digits=10, null=True, verbose_name='Credit Amount'),
        ),
        migrations.AlterField(
            model_name='stocktransactions',
            name='debitamount',
            field=models.DecimalField(decimal_places=2, max_digits=10, null=True, verbose_name='Debit Amount'),
        ),
    ]