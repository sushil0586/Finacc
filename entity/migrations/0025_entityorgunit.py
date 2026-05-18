from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ("entity", "0024_alter_entitygstregistration_gstin_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="EntityOrgUnit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("isactive", models.BooleanField(default=True)),
                ("unit_type", models.CharField(choices=[("department", "Department"), ("designation", "Designation"), ("grade", "Grade"), ("business_unit", "Business Unit"), ("cost_center", "Cost Center"), ("work_location", "Work Location")], max_length=30)),
                ("code", models.CharField(max_length=40)),
                ("name", models.CharField(max_length=150)),
                ("short_name", models.CharField(blank=True, max_length=80, null=True)),
                ("description", models.CharField(blank=True, max_length=255, null=True)),
                ("manager_title", models.CharField(blank=True, max_length=100, null=True)),
                ("status", models.CharField(choices=[("active", "Active"), ("inactive", "Inactive"), ("archived", "Archived")], default="active", max_length=20)),
                ("effective_from", models.DateField(blank=True, null=True)),
                ("effective_to", models.DateField(blank=True, null=True)),
                ("sort_order", models.PositiveIntegerField(default=100)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("createdby", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("entity", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="org_units", to="entity.entity")),
                ("parent", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="children", to="entity.entityorgunit")),
                ("subentity", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="org_units", to="entity.subentity")),
            ],
            options={
                "ordering": ["entity_id", "unit_type", "sort_order", "name", "id"],
            },
        ),
        migrations.AddConstraint(
            model_name="entityorgunit",
            constraint=models.UniqueConstraint(
                condition=Q(isactive=True, subentity__isnull=True),
                fields=("entity", "unit_type", "code"),
                name="uq_entity_org_unit_shared_code_active",
            ),
        ),
        migrations.AddConstraint(
            model_name="entityorgunit",
            constraint=models.UniqueConstraint(
                condition=Q(isactive=True, subentity__isnull=False),
                fields=("entity", "subentity", "unit_type", "code"),
                name="uq_entity_org_unit_subentity_code_active",
            ),
        ),
        migrations.AddIndex(
            model_name="entityorgunit",
            index=models.Index(fields=["entity", "unit_type", "isactive"], name="entity_entit_entity__eb654b_idx"),
        ),
        migrations.AddIndex(
            model_name="entityorgunit",
            index=models.Index(fields=["entity", "subentity", "unit_type"], name="entity_entit_entity__3624b9_idx"),
        ),
        migrations.AddIndex(
            model_name="entityorgunit",
            index=models.Index(fields=["entity", "status"], name="entity_entit_entity__ce1b9d_idx"),
        ),
    ]
