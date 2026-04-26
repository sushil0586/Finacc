from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("sales", "0038_salessettings_invoice_printing"),
    ]

    operations = [
        migrations.CreateModel(
            name="SalesInvoiceTransportSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("transporter_id", models.CharField(blank=True, default="", max_length=32)),
                ("transporter_name", models.CharField(blank=True, default="", max_length=128)),
                ("transport_mode", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("vehicle_no", models.CharField(blank=True, default="", max_length=32)),
                ("vehicle_type", models.CharField(blank=True, default="", max_length=1)),
                ("lr_gr_no", models.CharField(blank=True, default="", max_length=32)),
                ("lr_gr_date", models.DateField(blank=True, null=True)),
                ("distance_km", models.PositiveIntegerField(blank=True, null=True)),
                ("dispatch_through", models.CharField(blank=True, default="", max_length=64)),
                ("driver_name", models.CharField(blank=True, default="", max_length=128)),
                ("driver_mobile", models.CharField(blank=True, default="", max_length=20)),
                ("remarks", models.CharField(blank=True, default="", max_length=255)),
                (
                    "source",
                    models.CharField(
                        choices=[("manual", "Manual"), ("eway_prefill", "E-Way Prefill"), ("copied", "Copied")],
                        db_index=True,
                        default="manual",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sales_transport_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "invoice",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="transport_snapshot",
                        related_query_name="transport_snapshot",
                        to="sales.salesinvoiceheader",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sales_transport_updated",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "sales_invoice_transport_snapshot",
            },
        ),
        migrations.AddIndex(
            model_name="salesinvoicetransportsnapshot",
            index=models.Index(fields=["transport_mode"], name="idx_sales_trn_mode"),
        ),
        migrations.AddIndex(
            model_name="salesinvoicetransportsnapshot",
            index=models.Index(fields=["vehicle_no"], name="idx_sales_trn_vehicle"),
        ),
        migrations.AddIndex(
            model_name="salesinvoicetransportsnapshot",
            index=models.Index(fields=["lr_gr_no"], name="idx_sales_trn_lrgr"),
        ),
        migrations.AddIndex(
            model_name="salesinvoicetransportsnapshot",
            index=models.Index(fields=["source"], name="idx_sales_trn_source"),
        ),
    ]
