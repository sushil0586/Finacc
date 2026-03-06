from decimal import Decimal
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("sales", "0018_enterprise_compliance_hardening"),
    ]

    operations = [
        migrations.AddField(
            model_name="salessettings",
            name="enforce_statutory_cancel_before_business_cancel",
            field=models.BooleanField(default=True),
        ),
        migrations.CreateModel(
            name="SalesComplianceActionLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action_type", models.CharField(choices=[("IRN_GENERATE", "IRN Generate"), ("IRN_CANCEL", "IRN Cancel"), ("EWB_GENERATE", "EWB Generate"), ("EWB_B2C_GENERATE", "EWB B2C Generate"), ("EWB_CANCEL", "EWB Cancel"), ("EWB_VEHICLE_UPDATE", "EWB Vehicle Update"), ("EWB_TRANSPORTER_UPDATE", "EWB Transporter Update"), ("EWB_EXTEND", "EWB Validity Extend"), ("INVOICE_CANCEL_BLOCKED", "Invoice Cancel Blocked")], db_index=True, max_length=32)),
                ("outcome", models.CharField(choices=[("SUCCESS", "Success"), ("FAILED", "Failed"), ("BLOCKED", "Blocked"), ("INFO", "Info")], db_index=True, max_length=16)),
                ("error_code", models.CharField(blank=True, max_length=64, null=True)),
                ("error_message", models.TextField(blank=True, null=True)),
                ("request_json", models.JSONField(blank=True, null=True)),
                ("response_json", models.JSONField(blank=True, null=True)),
                ("created_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now, editable=False)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sales_compliance_actions_created", to=settings.AUTH_USER_MODEL)),
                ("invoice", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="compliance_actions", to="sales.salesinvoiceheader")),
            ],
            options={
                "db_table": "sales_compliance_action_log",
            },
        ),
        migrations.CreateModel(
            name="SalesComplianceExceptionQueue",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("exception_type", models.CharField(choices=[("IRN_GENERATION_FAILED", "IRN Generation Failed"), ("EWB_GENERATION_FAILED", "EWB Generation Failed"), ("EWB_B2C_GENERATION_FAILED", "EWB B2C Generation Failed"), ("STATUTORY_CANCEL_REQUIRED", "Statutory Cancel Required")], db_index=True, max_length=40)),
                ("status", models.CharField(choices=[("OPEN", "Open"), ("IN_PROGRESS", "In Progress"), ("RESOLVED", "Resolved"), ("IGNORED", "Ignored")], db_index=True, default="OPEN", max_length=16)),
                ("severity", models.CharField(choices=[("LOW", "Low"), ("MEDIUM", "Medium"), ("HIGH", "High"), ("CRITICAL", "Critical")], db_index=True, default="HIGH", max_length=16)),
                ("error_code", models.CharField(blank=True, max_length=64, null=True)),
                ("error_message", models.TextField(blank=True, null=True)),
                ("payload_json", models.JSONField(blank=True, null=True)),
                ("retry_count", models.PositiveIntegerField(default=0)),
                ("next_retry_at", models.DateTimeField(blank=True, null=True)),
                ("first_seen_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("last_seen_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("invoice", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="compliance_exceptions", to="sales.salesinvoiceheader")),
                ("resolved_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sales_compliance_exceptions_resolved", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "sales_compliance_exception_queue",
            },
        ),
        migrations.AddIndex(
            model_name="salescomplianceactionlog",
            index=models.Index(fields=["invoice", "created_at"], name="idx_sales_cmp_act_inv_dt"),
        ),
        migrations.AddIndex(
            model_name="salescomplianceactionlog",
            index=models.Index(fields=["action_type", "outcome"], name="idx_sales_cmp_act_type_out"),
        ),
        migrations.AddIndex(
            model_name="salescomplianceexceptionqueue",
            index=models.Index(fields=["status", "severity", "next_retry_at"], name="idx_sales_cmp_exc_work"),
        ),
        migrations.AddIndex(
            model_name="salescomplianceexceptionqueue",
            index=models.Index(fields=["invoice", "exception_type"], name="idx_sales_cmp_exc_inv_type"),
        ),
        migrations.AddConstraint(
            model_name="salescomplianceexceptionqueue",
            constraint=models.UniqueConstraint(
                fields=("invoice", "exception_type", "status"),
                condition=Q(status__in=["OPEN", "IN_PROGRESS"]),
                name="uq_sales_cmp_exc_active_per_type",
            ),
        ),
    ]
