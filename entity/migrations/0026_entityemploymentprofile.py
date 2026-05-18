from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ("entity", "0025_entityorgunit"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="EntityEmploymentProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("isactive", models.BooleanField(default=True)),
                ("employee_code", models.CharField(max_length=40)),
                ("full_name", models.CharField(max_length=200)),
                ("work_email", models.EmailField(blank=True, default="", max_length=254)),
                ("employment_type", models.CharField(choices=[("full_time", "Full Time"), ("part_time", "Part Time"), ("contract", "Contract"), ("consultant", "Consultant"), ("intern", "Intern"), ("apprentice", "Apprentice"), ("temporary", "Temporary")], default="full_time", max_length=20)),
                ("work_type", models.CharField(choices=[("onsite", "Onsite"), ("remote", "Remote"), ("hybrid", "Hybrid"), ("field", "Field")], default="onsite", max_length=20)),
                ("status", models.CharField(choices=[("active", "Active"), ("probation", "Probation"), ("notice", "Notice Period"), ("hold", "Hold"), ("exited", "Exited")], default="active", max_length=20)),
                ("effective_from", models.DateField()),
                ("effective_to", models.DateField(blank=True, null=True)),
                ("date_of_joining", models.DateField()),
                ("probation_end", models.DateField(blank=True, null=True)),
                ("confirmation_date", models.DateField(blank=True, null=True)),
                ("last_working_day", models.DateField(blank=True, null=True)),
                ("separation_reason", models.CharField(blank=True, max_length=255, null=True)),
                ("exit_status", models.CharField(blank=True, choices=[("resigned", "Resigned"), ("terminated", "Terminated"), ("retired", "Retired"), ("absconded", "Absconded"), ("separated", "Separated")], max_length=20, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("business_unit", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="employment_business_units", to="entity.entityorgunit")),
                ("cost_center", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="employment_cost_centers", to="entity.entityorgunit")),
                ("createdby", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("department", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="employment_departments", to="entity.entityorgunit")),
                ("designation", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="employment_designations", to="entity.entityorgunit")),
                ("employee_user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="employment_profiles", to=settings.AUTH_USER_MODEL)),
                ("entity", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="employment_profiles", to="entity.entity")),
                ("grade", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="employment_grades", to="entity.entityorgunit")),
                ("manager_user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="managed_employment_profiles", to=settings.AUTH_USER_MODEL)),
                ("subentity", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="employment_profiles", to="entity.subentity")),
                ("work_location", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="employment_work_locations", to="entity.entityorgunit")),
            ],
            options={
                "ordering": ["entity_id", "employee_code", "-effective_from", "-id"],
            },
        ),
        migrations.AddConstraint(
            model_name="entityemploymentprofile",
            constraint=models.UniqueConstraint(
                condition=Q(isactive=True),
                fields=("entity", "employee_user", "effective_from"),
                name="uq_entity_employment_profile_effective_from",
            ),
        ),
        migrations.AddIndex(
            model_name="entityemploymentprofile",
            index=models.Index(fields=["entity", "employee_user", "isactive"], name="entity_emplo_entity__62a40f_idx"),
        ),
        migrations.AddIndex(
            model_name="entityemploymentprofile",
            index=models.Index(fields=["entity", "subentity", "status"], name="entity_emplo_entity__1edabc_idx"),
        ),
        migrations.AddIndex(
            model_name="entityemploymentprofile",
            index=models.Index(fields=["entity", "effective_from"], name="entity_emplo_entity__5cf8e9_idx"),
        ),
    ]
