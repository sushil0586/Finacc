from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("bank_reconciliation", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BankReconciliationMatchAllocation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("isactive", models.BooleanField(default=True)),
                ("allocated_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("allocation_order", models.PositiveIntegerField(default=1)),
                ("notes", models.TextField(blank=True, default="")),
                ("metadata", models.JSONField(blank=True, default=dict)),
                (
                    "createdby",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL),
                ),
                (
                    "journal_line",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="+", to="posting.journalline"),
                ),
                (
                    "match",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="allocations", to="bank_reconciliation.bankreconciliationmatch"),
                ),
            ],
            options={
                "ordering": ("allocation_order", "id"),
                "indexes": [
                    models.Index(fields=["match", "allocation_order"], name="ix_bram_match_order"),
                    models.Index(fields=["journal_line"], name="ix_bram_journal_line"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("match", "journal_line"), name="uq_bank_reconciliation_match_allocation_line"),
                ],
            },
        ),
        migrations.CreateModel(
            name="BankReconciliationExceptionItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("isactive", models.BooleanField(default=True)),
                (
                    "exception_type",
                    models.CharField(
                        choices=[
                            ("bank_charge", "Bank Charge"),
                            ("bounced_cheque", "Bounced Cheque"),
                            ("interest", "Interest"),
                            ("unknown", "Unknown"),
                            ("duplicate", "Duplicate"),
                            ("other", "Other"),
                        ],
                        db_index=True,
                        max_length=30,
                    ),
                ),
                ("status", models.CharField(choices=[("open", "Open"), ("resolved", "Resolved"), ("ignored", "Ignored")], db_index=True, default="open", max_length=20)),
                ("amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("notes", models.TextField(blank=True, default="")),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                (
                    "createdby",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL),
                ),
                (
                    "resolvedby",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL),
                ),
                (
                    "session",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="exceptions", to="bank_reconciliation.bankreconciliationsession"),
                ),
                (
                    "statement_line",
                    models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="exception_item", to="bank_reconciliation.bankstatementline"),
                ),
            ],
            options={
                "ordering": ("-created_at", "-id"),
                "indexes": [
                    models.Index(fields=["session", "exception_type", "status"], name="ix_br_ex_session_type_status"),
                ],
            },
        ),
    ]
