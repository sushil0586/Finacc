# Generated by Django 4.1 on 2022-08-23 14:41

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('financial', '0001_initial'),
        ('invoice', '0006_alter_stocktransactions_saleinvoice'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='salesoderheader',
            name='tcs206c1ch3',
        ),
        migrations.AlterField(
            model_name='salesoderheader',
            name='broker',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='broker', to='financial.account'),
        ),
        migrations.AlterField(
            model_name='salesoderheader',
            name='shippedto',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='shippedto', to='financial.account'),
        ),
        migrations.AlterField(
            model_name='salesoderheader',
            name='transport',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='transport', to='financial.account'),
        ),
    ]