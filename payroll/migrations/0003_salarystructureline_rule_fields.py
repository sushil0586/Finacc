from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payroll", "0002_payrollemployeeprofile_employment_profile"),
    ]

    operations = [
        migrations.AddField(
            model_name="salarystructureline",
            name="compensation_bucket",
            field=models.CharField(
                choices=[
                    ("FIXED_PAY", "Fixed Pay"),
                    ("VARIABLE_PAY", "Variable Pay"),
                    ("EMPLOYER_COST", "Employer Cost"),
                    ("REIMBURSEMENT", "Reimbursement"),
                    ("RECOVERY", "Recovery"),
                    ("STATUTORY", "Statutory"),
                ],
                default="FIXED_PAY",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="salarystructureline",
            name="ctc_treatment",
            field=models.CharField(
                choices=[
                    ("INCLUDED", "Included In CTC"),
                    ("EXCLUDED", "Excluded From CTC"),
                    ("TARGET_ONLY", "Target Variable In CTC"),
                ],
                default="INCLUDED",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="salarystructureline",
            name="gross_treatment",
            field=models.CharField(
                choices=[
                    ("INCLUDED", "Included In Gross"),
                    ("EXCLUDED", "Excluded From Gross"),
                ],
                default="INCLUDED",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="salarystructureline",
            name="recurrence_frequency",
            field=models.CharField(
                choices=[
                    ("MONTHLY", "Monthly"),
                    ("QUARTERLY", "Quarterly"),
                    ("HALF_YEARLY", "Half-Yearly"),
                    ("YEARLY", "Yearly"),
                    ("ONE_TIME", "One-Time"),
                    ("OFF_CYCLE", "Off-Cycle"),
                ],
                default="MONTHLY",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="salarystructureline",
            name="rule_json",
            field=models.JSONField(blank=True, default=None, null=True),
        ),
        migrations.AddField(
            model_name="salarystructureline",
            name="rule_mode",
            field=models.CharField(
                choices=[
                    ("STANDARD", "Standard"),
                    ("CUSTOM_FORMULA", "Custom Formula"),
                ],
                default="STANDARD",
                max_length=30,
            ),
        ),
    ]
