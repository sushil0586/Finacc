# Generated by Django 4.1 on 2022-09-07 04:21

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('financial', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('entity', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Album',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('album_name', models.CharField(max_length=100)),
                ('artist', models.CharField(max_length=100)),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='gsttype',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('gsttypename', models.CharField(max_length=255, verbose_name='Gst type Name')),
                ('gsttypecode', models.CharField(max_length=255, verbose_name='Gst Type Code')),
                ('createdby', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('entity', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='entity.entity')),
            ],
            options={
                'ordering': ('created_at',),
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='UnitofMeasurement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('unitname', models.CharField(max_length=255, verbose_name='UOM calculate')),
                ('unitcode', models.CharField(max_length=255, verbose_name='UOM calculate')),
                ('createdby', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('entity', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='entity.entity')),
            ],
            options={
                'ordering': ('created_at',),
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='typeofgoods',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('goodstype', models.CharField(max_length=255, verbose_name='Goods Type')),
                ('goodscode', models.CharField(max_length=255, verbose_name='Goods Code')),
                ('createdby', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('entity', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='entity.entity')),
            ],
            options={
                'ordering': ('created_at',),
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Track',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order', models.IntegerField()),
                ('title', models.CharField(max_length=100)),
                ('duration', models.IntegerField()),
                ('album', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='tracks', to='inventory.album')),
            ],
            options={
                'ordering': ['order'],
            },
        ),
        migrations.CreateModel(
            name='stkvaluationby',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('valuationby', models.CharField(max_length=255, verbose_name='Valuation By')),
                ('valuationcode', models.CharField(max_length=255, verbose_name='valuation code')),
                ('createdby', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('entity', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='entity.entity')),
            ],
            options={
                'ordering': ('created_at',),
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='stkcalculateby',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('unitname', models.CharField(max_length=255, verbose_name='UOM calculate')),
                ('unitcode', models.CharField(max_length=255, verbose_name='UOM calculate')),
                ('createdby', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('entity', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='entity.entity')),
            ],
            options={
                'ordering': ('created_at',),
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Ratecalculate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('rname', models.CharField(max_length=255, verbose_name='Rate calc Name')),
                ('rcode', models.CharField(max_length=255, verbose_name='Rate Calc Code')),
                ('createdby', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('entity', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='entity.entity')),
            ],
            options={
                'ordering': ('created_at',),
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='ProductCategory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('pcategoryname', models.CharField(max_length=50, verbose_name='Product Category')),
                ('createdby', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('entity', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='entity.entity')),
                ('maincategory', models.ForeignKey(blank=True, default=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='inventory.productcategory', verbose_name='Main category')),
            ],
            options={
                'ordering': ('created_at',),
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Product',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('productname', models.CharField(max_length=50, verbose_name='Product Name')),
                ('productcode', models.IntegerField(blank=True, null=True, verbose_name='Product Code')),
                ('productdesc', models.CharField(max_length=100, null=True, verbose_name='product desc')),
                ('is_pieces', models.BooleanField(default=True)),
                ('openingstockqty', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('openingstockboxqty', models.IntegerField(blank=True, null=True, verbose_name='Box/Pcs')),
                ('openingstockvalue', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('purchaserate', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Purchase Rate')),
                ('prlesspercentage', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('mrp', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('mrpless', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('salesprice', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('totalgst', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('cgst', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('cgstcess', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('sgst', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('sgstcess', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('igst', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('igstcess', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('is_product', models.BooleanField(default=True)),
                ('hsn', models.IntegerField(blank=True, default=1001, verbose_name='Hsn Code')),
                ('createdby', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('entity', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='entity.entity')),
                ('gsttype', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='inventory.gsttype', verbose_name='Gst Type')),
                ('productcategory', models.ForeignKey(blank=True, on_delete=django.db.models.deletion.CASCADE, to='inventory.productcategory', verbose_name='Product Category')),
                ('purchaseaccount', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='purchaseaccount', to='financial.account')),
                ('ratecalculate', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='inventory.ratecalculate', verbose_name='Rate calculate')),
                ('saleaccount', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='financial.account')),
                ('stkcalculateby', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='inventory.stkcalculateby', verbose_name='Stock Calculated By')),
                ('stkvaluationby', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='inventory.stkvaluationby', verbose_name='Stock valuation by')),
                ('typeofgoods', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='inventory.typeofgoods', verbose_name='Type of goods')),
                ('unitofmeasurement', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='inventory.unitofmeasurement', verbose_name='Unit of Measurement')),
            ],
            options={
                'ordering': ('created_at',),
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='GstRate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('CSGT', models.DecimalField(blank=True, decimal_places=2, default=True, max_digits=10)),
                ('SGST', models.DecimalField(blank=True, decimal_places=2, default=True, max_digits=10)),
                ('IGST', models.DecimalField(blank=True, decimal_places=2, default=True, max_digits=10)),
                ('createdby', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('entity', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='entity.entity')),
            ],
            options={
                'ordering': ('created_at',),
                'abstract': False,
            },
        ),
    ]