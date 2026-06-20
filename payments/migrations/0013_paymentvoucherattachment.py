from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone

import payments.models.payment_core


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0012_payment_report_indexes"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PaymentVoucherAttachment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("file", models.FileField(upload_to=payments.models.payment_core._payment_attachment_upload_to)),
                ("original_name", models.CharField(blank=True, max_length=255, null=True)),
                ("content_type", models.CharField(blank=True, max_length=100, null=True)),
                (
                    "payment_voucher",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attachments",
                        to="payments.paymentvoucherheader",
                    ),
                ),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="payment_attachments_uploaded",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "payment_voucher_attachment",
            },
        ),
        migrations.AddIndex(
            model_name="paymentvoucherattachment",
            index=models.Index(fields=["payment_voucher", "created_at"], name="ix_pay_att_vchr_created"),
        ),
    ]
