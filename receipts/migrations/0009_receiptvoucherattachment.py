from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone

import receipts.models.receipt_core


class Migration(migrations.Migration):

    dependencies = [
        ("receipts", "0008_receipt_report_indexes"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ReceiptVoucherAttachment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("file", models.FileField(upload_to=receipts.models.receipt_core._receipt_attachment_upload_to)),
                ("original_name", models.CharField(blank=True, max_length=255, null=True)),
                ("content_type", models.CharField(blank=True, max_length=100, null=True)),
                (
                    "receipt_voucher",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attachments",
                        to="receipts.receiptvoucherheader",
                    ),
                ),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="receipt_attachments_uploaded",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "receipt_voucher_attachment",
            },
        ),
        migrations.AddIndex(
            model_name="receiptvoucherattachment",
            index=models.Index(fields=["receipt_voucher", "created_at"], name="ix_rcpt_att_vchr_created"),
        ),
    ]
