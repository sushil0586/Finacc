from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("entity", "0020_remove_entity_unittype"),
        ("posting", "0015_alter_entry_txn_type_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="BankReconciliationSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("isactive", models.BooleanField(default=True)),
                ("session_code", models.CharField(blank=True, db_index=True, max_length=32, unique=True)),
                ("status", models.CharField(choices=[("draft", "Draft"), ("imported", "Imported"), ("matching", "Matching"), ("needs_review", "Needs Review"), ("reconciled", "Reconciled"), ("locked", "Locked")], db_index=True, default="draft", max_length=20)),
                ("statement_label", models.CharField(blank=True, default="", max_length=255)),
                ("source_name", models.CharField(blank=True, default="", max_length=255)),
                ("source_format", models.CharField(blank=True, default="manual", max_length=20)),
                ("date_from", models.DateField(blank=True, db_index=True, null=True)),
                ("date_to", models.DateField(blank=True, db_index=True, null=True)),
                ("statement_opening_balance", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("statement_closing_balance", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("book_opening_balance", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("book_closing_balance", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("matched_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("unmatched_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("difference_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("imported_row_count", models.PositiveIntegerField(default=0)),
                ("matched_row_count", models.PositiveIntegerField(default=0)),
                ("reviewed_row_count", models.PositiveIntegerField(default=0)),
                ("exception_row_count", models.PositiveIntegerField(default=0)),
                ("notes", models.TextField(blank=True, default="")),
                ("metadata", models.JSONField(blank=True, default=dict)),
                (
                    "bank_account",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="bank_reconciliation_sessions", to="entity.entitybankaccountv2"),
                ),
                (
                    "createdby",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL),
                ),
                (
                    "entity",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="bank_reconciliation_sessions", to="entity.entity"),
                ),
                (
                    "entityfin",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="entity.entityfinancialyear"),
                ),
                (
                    "subentity",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="entity.subentity"),
                ),
            ],
            options={
                "ordering": ("-created_at", "-id"),
                "indexes": [
                    models.Index(fields=["entity", "status"], name="ix_brs_entity_status"),
                    models.Index(fields=["entity", "entityfin", "bank_account"], name="ix_brs_entity_fy_bank"),
                    models.Index(fields=["date_from", "date_to"], name="ix_brs_date_range"),
                ],
            },
        ),
        migrations.CreateModel(
            name="BankReconciliationRule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("isactive", models.BooleanField(default=True)),
                ("name", models.CharField(max_length=255)),
                ("rule_type", models.CharField(choices=[("exact", "Exact Match"), ("reference", "Reference Contains"), ("date_window", "Date Window"), ("amount_tolerance", "Amount Tolerance"), ("counterparty", "Counterparty Contains")], db_index=True, default="exact", max_length=30)),
                ("priority", models.PositiveIntegerField(default=100)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("amount_tolerance", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("date_window_days", models.PositiveIntegerField(default=0)),
                ("configuration", models.JSONField(blank=True, default=dict)),
                (
                    "createdby",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL),
                ),
                (
                    "entity",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="bank_reconciliation_rules", to="entity.entity"),
                ),
            ],
            options={
                "ordering": ("priority", "id"),
                "constraints": [
                    models.UniqueConstraint(fields=("entity", "name"), name="uq_bank_reconciliation_rule_entity_name"),
                ],
                "indexes": [
                    models.Index(fields=["entity", "rule_type", "is_active"], name="ix_brr_entity_rule_active"),
                    models.Index(fields=["entity", "priority"], name="ix_brr_entity_priority"),
                ],
            },
        ),
        migrations.CreateModel(
            name="BankStatementBatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("isactive", models.BooleanField(default=True)),
                ("batch_code", models.CharField(blank=True, db_index=True, max_length=32, unique=True)),
                ("source_name", models.CharField(blank=True, default="", max_length=255)),
                ("source_format", models.CharField(choices=[("manual", "Manual"), ("csv", "CSV"), ("excel", "Excel"), ("json", "JSON")], default="manual", max_length=20)),
                ("raw_payload", models.JSONField(blank=True, default=list)),
                ("imported_row_count", models.PositiveIntegerField(default=0)),
                ("duplicate_row_count", models.PositiveIntegerField(default=0)),
                ("notes", models.TextField(blank=True, default="")),
                ("metadata", models.JSONField(blank=True, default=dict)),
                (
                    "importedby",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL),
                ),
                (
                    "session",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="batches", to="bank_reconciliation.bankreconciliationsession"),
                ),
            ],
            options={
                "ordering": ("-created_at", "-id"),
                "indexes": [
                    models.Index(fields=["session", "source_format"], name="ix_bsb_session_format"),
                    models.Index(fields=["batch_code"], name="ix_bsb_batch_code"),
                ],
            },
        ),
        migrations.CreateModel(
            name="BankStatementLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("isactive", models.BooleanField(default=True)),
                ("line_no", models.PositiveIntegerField()),
                ("transaction_date", models.DateField(blank=True, db_index=True, null=True)),
                ("value_date", models.DateField(blank=True, db_index=True, null=True)),
                ("description", models.CharField(blank=True, default="", max_length=255)),
                ("reference_number", models.CharField(blank=True, default="", max_length=120)),
                ("counterparty", models.CharField(blank=True, default="", max_length=255)),
                ("debit_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("credit_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("balance_amount", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("currency", models.CharField(blank=True, default="INR", max_length=10)),
                ("external_id", models.CharField(blank=True, default="", max_length=120)),
                ("row_hash", models.CharField(db_index=True, max_length=40)),
                ("match_status", models.CharField(choices=[("unmatched", "Unmatched"), ("suggested", "Suggested"), ("matched", "Matched"), ("ignored", "Ignored"), ("exception", "Exception")], db_index=True, default="unmatched", max_length=20)),
                ("suggested_match_score", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=5)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                (
                    "batch",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lines", to="bank_reconciliation.bankstatementbatch"),
                ),
            ],
            options={
                "ordering": ("line_no", "id"),
                "indexes": [
                    models.Index(fields=["batch", "match_status"], name="ix_bsl_batch_status"),
                    models.Index(fields=["transaction_date", "reference_number"], name="ix_bsl_txn_ref"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("batch", "line_no"), name="uq_bank_statement_line_batch_line_no"),
                    models.UniqueConstraint(fields=("batch", "row_hash"), name="uq_bank_statement_line_batch_row_hash"),
                ],
            },
        ),
        migrations.CreateModel(
            name="BankReconciliationMatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("isactive", models.BooleanField(default=True)),
                ("match_kind", models.CharField(choices=[("exact", "Exact"), ("manual", "Manual"), ("rule", "Rule"), ("split", "Split")], default="exact", max_length=20)),
                ("matched_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("difference_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("confidence", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=5)),
                ("notes", models.TextField(blank=True, default="")),
                ("matched_at", models.DateTimeField(blank=True, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                (
                    "entry",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="posting.entry"),
                ),
                (
                    "journal_line",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="posting.journalline"),
                ),
                (
                    "matchedby",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL),
                ),
                (
                    "session",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="matches", to="bank_reconciliation.bankreconciliationsession"),
                ),
                (
                    "statement_line",
                    models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="match", to="bank_reconciliation.bankstatementline"),
                ),
            ],
            options={
                "ordering": ("-matched_at", "-id"),
                "indexes": [
                    models.Index(fields=["session", "match_kind"], name="ix_brm_session_kind"),
                    models.Index(fields=["entry"], name="ix_brm_entry"),
                    models.Index(fields=["journal_line"], name="ix_brm_journal_line"),
                ],
            },
        ),
        migrations.CreateModel(
            name="BankReconciliationAuditLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("isactive", models.BooleanField(default=True)),
                ("action", models.CharField(db_index=True, max_length=80)),
                ("payload", models.JSONField(blank=True, default=dict)),
                (
                    "actor",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL),
                ),
                (
                    "session",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="audit_logs", to="bank_reconciliation.bankreconciliationsession"),
                ),
            ],
            options={
                "ordering": ("-created_at", "-id"),
                "indexes": [
                    models.Index(fields=["session", "action"], name="ix_bral_session_action"),
                ],
            },
        ),
    ]
