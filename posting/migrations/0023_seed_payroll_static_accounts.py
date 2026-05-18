from django.db import migrations


PAYROLL_STATIC_ACCOUNTS = [
    (
        "PAYROLL_SALARY_PAYABLE",
        "Payroll Salary Payable",
        "OTHER",
        True,
        "Default salary payable ledger for payroll posting when entity policy mapping is not configured.",
    ),
    (
        "PAYROLL_REIMBURSEMENT_PAYABLE",
        "Payroll Reimbursement Payable",
        "OTHER",
        False,
        "Default reimbursement payable ledger for payroll posting when entity policy mapping is not configured.",
    ),
    (
        "PAYROLL_EMPLOYER_CONTRIBUTION_PAYABLE",
        "Payroll Employer Contribution Payable",
        "OTHER",
        False,
        "Default employer contribution payable ledger for payroll posting when component-level liability mapping is not configured.",
    ),
    (
        "PAYROLL_PF_PAYABLE",
        "Payroll PF Payable",
        "OTHER",
        False,
        "Default provident-fund payable ledger for payroll and FnF statutory posting.",
    ),
    (
        "PAYROLL_ESI_PAYABLE",
        "Payroll ESI Payable",
        "OTHER",
        False,
        "Default ESI payable ledger for payroll and FnF statutory posting.",
    ),
    (
        "PAYROLL_PT_PAYABLE",
        "Payroll PT Payable",
        "OTHER",
        False,
        "Default professional-tax payable ledger for payroll and FnF statutory posting.",
    ),
    (
        "PAYROLL_LWF_PAYABLE",
        "Payroll LWF Payable",
        "OTHER",
        False,
        "Default labour-welfare-fund payable ledger for payroll and FnF statutory posting.",
    ),
    (
        "PAYROLL_FNF_PAYABLE",
        "Payroll FnF Payable",
        "OTHER",
        False,
        "Default final-settlement payable ledger for FnF posting.",
    ),
    (
        "PAYROLL_FNF_RECOVERABLE",
        "Payroll FnF Recoverable",
        "OTHER",
        False,
        "Default final-settlement recoverable ledger for FnF posting.",
    ),
]


def seed_payroll_static_accounts(apps, schema_editor):
    StaticAccount = apps.get_model("posting", "StaticAccount")
    for code, name, group, is_required, description in PAYROLL_STATIC_ACCOUNTS:
        StaticAccount.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "group": group,
                "is_required": is_required,
                "is_active": True,
                "description": description,
            },
        )


def noop(apps, schema_editor):
    return


class Migration(migrations.Migration):

    dependencies = [
        ("posting", "0022_alter_entry_txn_type_alter_inventorymove_txn_type_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_payroll_static_accounts, noop),
    ]
