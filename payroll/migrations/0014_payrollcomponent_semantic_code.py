from django.db import migrations, models


LEGACY_COMPONENT_SEMANTIC_MAP = {
    "BASIC": "BASIC_PAY",
    "HRA": "HRA",
    "SPECIAL_ALLOWANCE": "SPECIAL_ALLOWANCE",
    "OTHER_ALLOWANCE": "OTHER_EARNING",
    "BONUS": "OTHER_EARNING",
    "INCENTIVE": "OTHER_EARNING",
    "COMMISSION": "OTHER_EARNING",
    "ARREARS": "OTHER_EARNING",
    "OVERTIME": "OTHER_EARNING",
    "LEAVE_ENCASHMENT": "OTHER_EARNING",
    "REIMBURSEMENT": "REIMBURSEMENT",
    "LOAN_RECOVERY": "RECOVERY",
    "ADVANCE_RECOVERY": "RECOVERY",
    "PF_EMPLOYEE": "PF_EMPLOYEE",
    "PF_EMPLOYER": "PF_EMPLOYER",
    "PROFESSIONAL_TAX": "PT",
    "ESI_EMPLOYEE": "ESI_EMPLOYEE",
    "ESI_EMPLOYER": "ESI_EMPLOYER",
    "TDS": "TDS",
    "LWF_EMPLOYEE": "LWF_EMPLOYEE",
    "LWF_EMPLOYER": "LWF_EMPLOYER",
}


def backfill_payroll_component_semantic_codes(apps, schema_editor):
    PayrollComponent = apps.get_model("payroll", "PayrollComponent")
    for component in PayrollComponent.objects.filter(semantic_code="").iterator():
        semantic_code = LEGACY_COMPONENT_SEMANTIC_MAP.get((component.code or "").strip().upper())
        if not semantic_code:
            continue
        component.semantic_code = semantic_code
        component.save(update_fields=["semantic_code"])


def reverse_payroll_component_semantic_codes(apps, schema_editor):
    PayrollComponent = apps.get_model("payroll", "PayrollComponent")
    legacy_values = set(LEGACY_COMPONENT_SEMANTIC_MAP.values())
    PayrollComponent.objects.filter(semantic_code__in=legacy_values).update(semantic_code="")


class Migration(migrations.Migration):

    dependencies = [
        ("payroll", "0013_remove_payrollrunemployee_employee_profile_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="payrollcomponent",
            name="semantic_code",
            field=models.CharField(
                blank=True,
                choices=[
                    ("BASIC_PAY", "Basic Pay"),
                    ("HRA", "House Rent Allowance"),
                    ("SPECIAL_ALLOWANCE", "Special Allowance"),
                    ("GROSS_EARNING", "Gross Earning"),
                    ("PF_EMPLOYEE", "PF Employee"),
                    ("PF_EMPLOYER", "PF Employer"),
                    ("ESI_EMPLOYEE", "ESI Employee"),
                    ("ESI_EMPLOYER", "ESI Employer"),
                    ("PT", "Professional Tax"),
                    ("TDS", "Tax Deducted at Source"),
                    ("LWF_EMPLOYEE", "LWF Employee"),
                    ("LWF_EMPLOYER", "LWF Employer"),
                    ("OTHER_EARNING", "Other Earning"),
                    ("OTHER_DEDUCTION", "Other Deduction"),
                    ("REIMBURSEMENT", "Reimbursement"),
                    ("RECOVERY", "Recovery"),
                    ("OTHER_EMPLOYER_CONTRIBUTION", "Other Employer Contribution"),
                ],
                default="",
                max_length=40,
            ),
        ),
        migrations.RunPython(
            backfill_payroll_component_semantic_codes,
            reverse_payroll_component_semantic_codes,
        ),
    ]
