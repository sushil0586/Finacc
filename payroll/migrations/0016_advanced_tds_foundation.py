from decimal import Decimal

from django.db import migrations, models


def backfill_tax_declaration_line_metadata(apps, schema_editor):
    ContractTaxDeclarationLine = apps.get_model("payroll", "ContractTaxDeclarationLine")
    section_to_category = {
        "HRA": "EXEMPTION",
    }
    section_to_code = {
        "80C": "DEDUCTION_80C",
        "80D": "DEDUCTION_80D",
        "HRA": "HRA_EXEMPTION",
        "LTA": "LTA_EXEMPTION",
        "HOME_LOAN_INTEREST": "HOME_LOAN_INTEREST",
    }
    for line in ContractTaxDeclarationLine.objects.all().iterator():
        section_code = str(getattr(line, "section_code", "") or "").upper()
        line.declaration_category = section_to_category.get(section_code, "DEDUCTION")
        line.declaration_code = section_to_code.get(section_code, "OTHER")
        line.save(update_fields=["declaration_category", "declaration_code"])


class Migration(migrations.Migration):

    dependencies = [
        ("payroll", "0015_fnfsettlement_fnfsettlementcomponent_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="contracttaxdeclaration",
            name="annual_deduction_total",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14),
        ),
        migrations.AddField(
            model_name="contracttaxdeclaration",
            name="annual_exemption_total",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14),
        ),
        migrations.AddField(
            model_name="contracttaxdeclaration",
            name="annual_gross_projection",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14),
        ),
        migrations.AddField(
            model_name="contracttaxdeclaration",
            name="annual_other_income",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14),
        ),
        migrations.AddField(
            model_name="contracttaxdeclaration",
            name="balance_tax",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14),
        ),
        migrations.AddField(
            model_name="contracttaxdeclaration",
            name="projected_annual_tax",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14),
        ),
        migrations.AddField(
            model_name="contracttaxdeclaration",
            name="projected_monthly_tds",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14),
        ),
        migrations.AddField(
            model_name="contracttaxdeclaration",
            name="projected_taxable_income",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14),
        ),
        migrations.AddField(
            model_name="contracttaxdeclaration",
            name="tax_already_deducted",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14),
        ),
        migrations.AddField(
            model_name="contracttaxdeclarationline",
            name="declaration_category",
            field=models.CharField(
                choices=[
                    ("DEDUCTION", "Deduction"),
                    ("EXEMPTION", "Exemption"),
                    ("OTHER_INCOME", "Other Income"),
                    ("INFORMATIONAL", "Informational"),
                ],
                default="DEDUCTION",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="contracttaxdeclarationline",
            name="declaration_code",
            field=models.CharField(blank=True, default="", max_length=60),
        ),
        migrations.AlterField(
            model_name="contractpayrollinputsnapshot",
            name="input_type",
            field=models.CharField(
                choices=[
                    ("TAX_PROJECTION", "Tax Projection"),
                    ("MONTHLY_TDS_PROJECTION", "Monthly TDS Projection"),
                    ("ATTENDANCE_SUMMARY", "Attendance Summary"),
                    ("MANUAL_PAYROLL_INPUT", "Manual Payroll Input"),
                ],
                max_length=30,
            ),
        ),
        migrations.RunPython(backfill_tax_declaration_line_metadata, migrations.RunPython.noop),
    ]
