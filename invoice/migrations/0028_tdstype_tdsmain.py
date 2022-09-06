# Generated by Django 4.1 on 2022-09-06 06:09

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('entity', '0001_initial'),
        ('financial', '0001_initial'),
        ('invoice', '0027_purchasetaxtype'),
    ]

    operations = [
        migrations.CreateModel(
            name='tdstype',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tdstypename', models.CharField(max_length=255, verbose_name='Tds Type')),
                ('tdstypecode', models.CharField(max_length=255, verbose_name='Tds Type Code')),
                ('createdby', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('entity', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='entity.entity')),
            ],
            options={
                'ordering': ('created_at',),
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='tdsmain',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('voucherdate', models.DateField(auto_now_add=True, verbose_name='Vocucher Date')),
                ('voucherno', models.IntegerField(verbose_name='Voucher No')),
                ('creditdesc', models.CharField(max_length=255, verbose_name='Credit Acc desc')),
                ('debitdesc', models.CharField(max_length=255, verbose_name='Debit Acc desc')),
                ('tdsdesc', models.CharField(max_length=255, verbose_name='Tds Acc desc')),
                ('creditamount', models.DecimalField(decimal_places=2, max_digits=10, null=True, verbose_name='Credit Amount')),
                ('debitamount', models.DecimalField(decimal_places=2, max_digits=10, null=True, verbose_name='debit Amount')),
                ('otherexpenses', models.DecimalField(decimal_places=2, max_digits=10, null=True, verbose_name='other expenses')),
                ('tdsrate', models.DecimalField(decimal_places=2, max_digits=10, null=True, verbose_name='tds rate')),
                ('tdsvalue', models.DecimalField(decimal_places=2, max_digits=10, null=True, verbose_name='tds Value')),
                ('surchargerate', models.DecimalField(decimal_places=2, max_digits=10, null=True, verbose_name='Surcharge rate')),
                ('surchargevalue', models.DecimalField(decimal_places=2, max_digits=10, null=True, verbose_name='Surcharge Value')),
                ('cessrate', models.DecimalField(decimal_places=2, max_digits=10, null=True, verbose_name='Cess rate')),
                ('cessvalue', models.DecimalField(decimal_places=2, max_digits=10, null=True, verbose_name='Cess Value')),
                ('hecessrate', models.DecimalField(decimal_places=2, max_digits=10, null=True, verbose_name='HE Cess rate')),
                ('hecessvalue', models.DecimalField(decimal_places=2, max_digits=10, null=True, verbose_name='HE Cess Value')),
                ('grandttal', models.DecimalField(decimal_places=2, max_digits=10, null=True, verbose_name='Grand Total')),
                ('tdsreturndesc', models.CharField(max_length=255, verbose_name='tds return Acc desc')),
                ('vehicleno', models.CharField(max_length=20, verbose_name='vehicle no')),
                ('grno', models.CharField(max_length=20, verbose_name='GR No')),
                ('invoiceno', models.CharField(max_length=20, verbose_name='Invoice No')),
                ('grdate', models.DateField(auto_now_add=True, verbose_name='GR Date')),
                ('invoicedate', models.DateField(auto_now_add=True, verbose_name='Invoice Date')),
                ('weight', models.DecimalField(decimal_places=2, max_digits=10, null=True, verbose_name='weight')),
                ('createdby', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('creditaccount', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='tdscreditaccount', to='financial.account', verbose_name='Credit Account Name')),
                ('debitaccount', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='tdsdebitaccount', to='financial.account', verbose_name='debit Account Name')),
                ('entity', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='entity.entity')),
                ('tdsaccount', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='tdsaccount1', to='financial.account', verbose_name='Tds Account Name')),
                ('tdsreturnccount', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='tdsreturnaccount1', to='financial.account', verbose_name='debit Account Name')),
                ('tdstype', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='tdstype', to='invoice.tdstype', verbose_name='Tds Type')),
            ],
            options={
                'ordering': ('created_at',),
                'abstract': False,
            },
        ),
    ]