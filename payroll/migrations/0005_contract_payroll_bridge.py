import uuid
from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("hrms", "0001_initial"),
        ("payroll", "0004_global_payroll_catalog"),
    ]

    operations = [
        migrations.CreateModel(
            name="ContractPayrollProfile",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("pay_frequency", models.CharField(default="MONTHLY", max_length=20)),
                ("payroll_status", models.CharField(choices=[("DRAFT", "Draft"), ("ACTIVE", "Active"), ("HOLD", "Hold"), ("ENDED", "Ended")], default="DRAFT", max_length=20)),
                ("tax_regime", models.CharField(blank=True, choices=[("OLD", "Old Regime"), ("NEW", "New Regime"), ("", "Not Set")], default="", max_length=20)),
                ("payment_mode", models.CharField(blank=True, default="", max_length=30)),
                ("bank_account_details", models.JSONField(blank=True, default=dict)),
                ("payroll_start_date", models.DateField(default=django.utils.timezone.localdate)),
                ("payroll_end_date", models.DateField(blank=True, null=True)),
                ("pf_applicable", models.BooleanField(default=False)),
                ("esi_applicable", models.BooleanField(default=False)),
                ("pt_applicable", models.BooleanField(default=False)),
                ("tds_applicable", models.BooleanField(default=False)),
                ("lwf_applicable", models.BooleanField(default=False)),
                ("overtime_eligible", models.BooleanField(default=False)),
                ("attendance_required", models.BooleanField(default=False)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("is_active", models.BooleanField(default=True)),
                ("bank_account", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="contract_payroll_profiles", to="financial.account")),
                ("entity", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="contract_payroll_profiles", to="entity.entity")),
                ("hrms_contract", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="payroll_profiles", to="hrms.hremploymentcontract")),
            ],
            options={
                "ordering": ["entity_id", "hrms_contract_id", "-payroll_start_date"],
                "indexes": [
                    models.Index(fields=["entity", "payroll_status"], name="ix_cpp_status"),
                    models.Index(fields=["entity", "is_active"], name="ix_cpp_active"),
                    models.Index(fields=["hrms_contract", "payroll_start_date"], name="ix_cpp_contract"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("hrms_contract",), condition=models.Q(is_active=True), name="uq_contract_payroll_profile_active_contract"),
                    models.CheckConstraint(condition=models.Q(payroll_end_date__isnull=True) | models.Q(payroll_end_date__gte=models.F("payroll_start_date")), name="ck_contract_payroll_profile_dates"),
                ],
            },
        ),
        migrations.CreateModel(
            name="ContractSalaryStructureAssignment",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("effective_from", models.DateField(default=django.utils.timezone.localdate)),
                ("effective_to", models.DateField(blank=True, null=True)),
                ("assignment_status", models.CharField(choices=[("DRAFT", "Draft"), ("ACTIVE", "Active"), ("SUPERSEDED", "Superseded"), ("ENDED", "Ended")], default="ACTIVE", max_length=20)),
                ("ctc_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("gross_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("is_active", models.BooleanField(default=True)),
                ("contract_payroll_profile", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="salary_assignments", to="payroll.contractpayrollprofile")),
                ("salary_structure", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="contract_salary_assignments", to="payroll.salarystructure")),
                ("salary_structure_version", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="contract_salary_assignments", to="payroll.salarystructureversion")),
            ],
            options={
                "ordering": ["contract_payroll_profile_id", "-effective_from", "-id"],
                "indexes": [
                    models.Index(fields=["contract_payroll_profile", "effective_from"], name="ix_csa_eff"),
                    models.Index(fields=["contract_payroll_profile", "is_active"], name="ix_csa_active"),
                    models.Index(fields=["salary_structure", "salary_structure_version"], name="ix_csa_struct"),
                ],
                "constraints": [
                    models.CheckConstraint(condition=models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=models.F("effective_from")), name="ck_contract_salary_assignment_dates"),
                ],
            },
        ),
    ]
