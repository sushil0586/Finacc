import uuid
from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("payroll", "0003_salarystructureline_rule_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="GlobalPayrollComponentGroup",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("code", models.CharField(max_length=50)),
                ("name", models.CharField(max_length=120)),
                ("description", models.CharField(blank=True, default="", max_length=255)),
                ("group_type", models.CharField(choices=[("EARNINGS", "Earnings"), ("DEDUCTIONS", "Deductions"), ("EMPLOYER_CONTRIBUTIONS", "Employer Contributions"), ("REIMBURSEMENTS", "Reimbursements"), ("RECOVERIES", "Recoveries"), ("INFORMATIONAL", "Informational")], max_length=40)),
                ("sort_order", models.PositiveIntegerField(default=100)),
                ("is_system", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
            ],
            options={
                "ordering": ["sort_order", "code"],
                "constraints": [models.UniqueConstraint(fields=("code",), name="uq_global_payroll_component_group_code")],
                "indexes": [models.Index(fields=["group_type", "is_active"], name="ix_glb_pay_comp_group_type_act"), models.Index(fields=["sort_order"], name="ix_glb_pay_comp_group_sort")],
            },
        ),
        migrations.CreateModel(
            name="GlobalPayrollComponent",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("code", models.CharField(max_length=60)),
                ("name", models.CharField(max_length=140)),
                ("description", models.CharField(blank=True, default="", max_length=255)),
                ("component_type", models.CharField(choices=[("EARNING", "Earning"), ("DEDUCTION", "Deduction"), ("EMPLOYER_CONTRIBUTION", "Employer Contribution"), ("REIMBURSEMENT", "Reimbursement"), ("RECOVERY", "Recovery"), ("INFORMATIONAL", "Informational")], max_length=40)),
                ("calculation_type", models.CharField(choices=[("FIXED", "Fixed"), ("PERCENTAGE", "Percentage"), ("FORMULA", "Formula"), ("SLAB", "Slab"), ("MANUAL", "Manual"), ("DERIVED", "Derived")], max_length=20)),
                ("default_sequence", models.PositiveIntegerField(default=100)),
                ("default_formula", models.TextField(blank=True, default="")),
                ("default_rule_json", models.JSONField(blank=True, default=dict)),
                ("taxable", models.BooleanField(default=True)),
                ("affects_gross", models.BooleanField(default=True)),
                ("affects_net", models.BooleanField(default=True)),
                ("affects_ctc", models.BooleanField(default=True)),
                ("attendance_dependent", models.BooleanField(default=False)),
                ("lop_dependent", models.BooleanField(default=False)),
                ("overtime_dependent", models.BooleanField(default=False)),
                ("pro_rata", models.BooleanField(default=True)),
                ("statutory_code", models.CharField(blank=True, choices=[("PF", "PF"), ("ESI", "ESI"), ("PT", "PT"), ("TDS", "TDS"), ("LWF", "LWF"), ("BONUS", "Bonus"), ("GRATUITY", "Gratuity"), ("OTHER", "Other")], default="", max_length=20)),
                ("country_code", models.CharField(blank=True, default="", max_length=2)),
                ("state_code", models.CharField(blank=True, default="", max_length=10)),
                ("effective_from", models.DateField(default=django.utils.timezone.localdate)),
                ("effective_to", models.DateField(blank=True, null=True)),
                ("is_system", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("group", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="components", to="payroll.globalpayrollcomponentgroup")),
            ],
            options={
                "ordering": ["default_sequence", "code"],
                "constraints": [
                    models.UniqueConstraint(fields=("code",), name="uq_global_payroll_component_code"),
                    models.CheckConstraint(
                        condition=models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=models.F("effective_from")),
                        name="ck_global_pay_component_effective_dates",
                    ),
                ],
                "indexes": [
                    models.Index(fields=["component_type", "is_active"], name="ix_glb_pay_comp_type_act"),
                    models.Index(fields=["statutory_code", "is_active"], name="ix_glb_pay_comp_stat_act"),
                    models.Index(fields=["default_sequence"], name="ix_glb_pay_comp_seq"),
                    models.Index(fields=["effective_from", "effective_to"], name="ix_glb_pay_comp_eff"),
                ],
            },
        ),
        migrations.CreateModel(
            name="GlobalSalaryStructureTemplate",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("code", models.CharField(max_length=60)),
                ("name", models.CharField(max_length=160)),
                ("description", models.CharField(blank=True, default="", max_length=255)),
                ("template_type", models.CharField(choices=[("MONTHLY_STAFF", "Monthly Staff"), ("CTC_BASED", "CTC Based"), ("FACTORY_WORKER", "Factory Worker"), ("EXECUTIVE", "Executive"), ("SALES_INCENTIVE", "Sales Incentive"), ("CONTRACTOR", "Contractor"), ("INTERN_STIPEND", "Intern Stipend"), ("CUSTOM", "Custom")], max_length=40)),
                ("country_code", models.CharField(default="IN", max_length=2)),
                ("state_code", models.CharField(blank=True, default="", max_length=10)),
                ("industry_type", models.CharField(blank=True, default="", max_length=60)),
                ("pay_frequency", models.CharField(choices=[("MONTHLY", "Monthly"), ("WEEKLY", "Weekly"), ("FORTNIGHTLY", "Fortnightly"), ("BI_MONTHLY", "Bi-Monthly"), ("QUARTERLY", "Quarterly"), ("YEARLY", "Yearly")], default="MONTHLY", max_length=20)),
                ("is_default", models.BooleanField(default=False)),
                ("is_system", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                ("effective_from", models.DateField(default=django.utils.timezone.localdate)),
                ("effective_to", models.DateField(blank=True, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
            ],
            options={
                "ordering": ["code"],
                "constraints": [
                    models.UniqueConstraint(fields=("code",), name="uq_global_salary_template_code"),
                    models.CheckConstraint(
                        condition=models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=models.F("effective_from")),
                        name="ck_global_salary_template_effective_dates",
                    ),
                ],
                "indexes": [
                    models.Index(fields=["template_type", "is_active"], name="ix_glb_sal_tpl_type_act"),
                    models.Index(fields=["pay_frequency", "is_active"], name="ix_glb_sal_tpl_freq_act"),
                    models.Index(fields=["effective_from", "effective_to"], name="ix_glb_sal_tpl_eff"),
                ],
            },
        ),
        migrations.CreateModel(
            name="GlobalSalaryStructureTemplateLine",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("sequence", models.PositiveIntegerField(default=100)),
                ("calculation_type", models.CharField(choices=[("FIXED", "Fixed"), ("PERCENTAGE", "Percentage"), ("FORMULA", "Formula"), ("SLAB", "Slab"), ("MANUAL", "Manual"), ("DERIVED", "Derived")], max_length=20)),
                ("formula", models.TextField(blank=True, default="")),
                ("rule_json", models.JSONField(blank=True, default=dict)),
                ("amount_default", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("percentage_default", models.DecimalField(decimal_places=4, default=Decimal("0.00"), max_digits=9)),
                ("basis_components", models.JSONField(blank=True, default=list)),
                ("min_amount", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("max_amount", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("taxable_override", models.BooleanField(blank=True, null=True)),
                ("affects_gross_override", models.BooleanField(blank=True, null=True)),
                ("affects_net_override", models.BooleanField(blank=True, null=True)),
                ("affects_ctc_override", models.BooleanField(blank=True, null=True)),
                ("pro_rata", models.BooleanField(default=True)),
                ("attendance_dependent", models.BooleanField(default=False)),
                ("lop_dependent", models.BooleanField(default=False)),
                ("applicability_json", models.JSONField(blank=True, default=dict)),
                ("is_active", models.BooleanField(default=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("component", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="template_lines", to="payroll.globalpayrollcomponent")),
                ("template", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lines", to="payroll.globalsalarystructuretemplate")),
            ],
            options={
                "ordering": ["sequence", "created_at"],
                "constraints": [
                    models.UniqueConstraint(fields=("template", "component"), name="uq_global_salary_template_line_component"),
                ],
                "indexes": [
                    models.Index(fields=["template", "sequence"], name="ix_glb_sal_tpl_line_seq"),
                    models.Index(fields=["is_active"], name="ix_glb_sal_tpl_line_active"),
                ],
            },
        ),
    ]
