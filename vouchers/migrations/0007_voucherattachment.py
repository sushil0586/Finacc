from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone

import vouchers.models.voucher_core


class Migration(migrations.Migration):

    dependencies = [
        ("vouchers", "0006_voucher_report_indexes"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="VoucherAttachment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("file", models.FileField(upload_to=vouchers.models.voucher_core._voucher_attachment_upload_to)),
                ("original_name", models.CharField(blank=True, max_length=255, null=True)),
                ("content_type", models.CharField(blank=True, max_length=100, null=True)),
                (
                    "header",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attachments",
                        to="vouchers.voucherheader",
                    ),
                ),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="voucher_attachments_uploaded",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "voucher_attachment",
            },
        ),
        migrations.AddIndex(
            model_name="voucherattachment",
            index=models.Index(fields=["header", "created_at"], name="ix_vchr_att_hdr_created"),
        ),
    ]
