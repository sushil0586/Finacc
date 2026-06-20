from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone

import sales.models.sales_addons


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0044_sales_gstr_runtime_indexes"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SalesAttachment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="%(class)s_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="%(class)s_updated",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("file", models.FileField(upload_to=sales.models.sales_addons._sales_attachment_upload_to)),
                ("original_name", models.CharField(blank=True, max_length=255, null=True)),
                ("content_type", models.CharField(blank=True, max_length=100, null=True)),
                (
                    "header",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attachments",
                        to="sales.salesinvoiceheader",
                    ),
                ),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sales_attachments_uploaded",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "sales_attachment",
            },
        ),
        migrations.AddIndex(
            model_name="salesattachment",
            index=models.Index(fields=["header", "created_at"], name="ix_sales_att_hdr_created"),
        ),
    ]
