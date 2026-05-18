from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("entity", "0026_entityemploymentprofile"),
        ("payroll", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="payrollemployeeprofile",
            name="employment_profile",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="payroll_profiles", to="entity.entityemploymentprofile"),
        ),
    ]
