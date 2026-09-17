from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("treasury", "0002_payment_batch_payment_instrument"),
    ]

    operations = [
        migrations.CreateModel(
            name="TreasuryPaymentInstrument",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("isactive", models.BooleanField(default=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "instrument_type",
                    models.CharField(
                        choices=[
                            ("CHEQUE", "Cheque"),
                            ("UPI", "UPI"),
                            ("NEFT", "NEFT"),
                            ("RTGS", "RTGS"),
                            ("IMPS", "IMPS"),
                            ("CASH", "Cash"),
                            ("BANK_TRANSFER", "Bank Transfer"),
                            ("CARD", "Card"),
                            ("GATEWAY", "Payment Gateway"),
                            ("OTHER", "Other"),
                        ],
                        default="OTHER",
                        max_length=30,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PREPARED", "Prepared"),
                            ("EXPORTED", "Exported"),
                            ("SENT_TO_BANK", "Sent To Bank"),
                            ("CLEARED", "Cleared"),
                            ("FAILED", "Failed"),
                            ("CANCELLED", "Cancelled"),
                            ("BOUNCED", "Bounced"),
                            ("STALE", "Stale"),
                            ("REVERSED", "Reversed"),
                        ],
                        default="PREPARED",
                        max_length=30,
                    ),
                ),
                ("reference_no", models.CharField(blank=True, default="", max_length=120)),
                ("instrument_no", models.CharField(blank=True, default="", max_length=50)),
                ("instrument_date", models.DateField(blank=True, null=True)),
                ("bank_name", models.CharField(blank=True, default="", max_length=100)),
                ("amount", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("status_reason", models.CharField(blank=True, default="", max_length=255)),
                ("cleared_at", models.DateTimeField(blank=True, null=True)),
                ("failed_at", models.DateTimeField(blank=True, null=True)),
                ("cancelled_at", models.DateTimeField(blank=True, null=True)),
                ("metadata_json", models.JSONField(blank=True, default=dict)),
                (
                    "batch",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="instruments", to="treasury.treasurypaymentbatch"),
                ),
                (
                    "payment_mode",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="treasury_payment_instruments",
                        to="payments.paymentmode",
                    ),
                ),
                (
                    "source_account",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="treasury_payment_instruments",
                        to="financial.account",
                    ),
                ),
            ],
            options={
                "ordering": ["created_at", "id"],
                "indexes": [
                    models.Index(fields=["batch", "status"], name="ix_treas_instr_batch_status"),
                    models.Index(fields=["source_account", "status"], name="ix_treas_instr_source_status"),
                    models.Index(fields=["reference_no"], name="ix_treas_instr_reference"),
                ],
            },
        ),
    ]
