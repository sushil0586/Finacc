from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("entity", "0026_entityemploymentprofile"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="EntityApprovalPolicy",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True, null=True)),
                ("isactive", models.BooleanField(default=True)),
                ("policy_key", models.CharField(choices=[("payroll_run", "Payroll Run Approval"), ("payroll_adjustment", "Payroll Adjustment Approval"), ("payroll_payment_handoff", "Payroll Payment Handoff"), ("payroll_posting", "Payroll Posting Approval"), ("employment_change", "Employment Change Approval")], max_length=40)),
                ("code", models.CharField(max_length=50)),
                ("name", models.CharField(max_length=150)),
                ("approval_mode", models.CharField(choices=[("none", "No Approval"), ("manager_chain", "Manager Chain"), ("fixed_users", "Fixed Users"), ("permission_based", "Permission Based"), ("mixed", "Mixed")], default="manager_chain", max_length=30)),
                ("manager_levels", models.PositiveIntegerField(default=1)),
                ("min_approvers", models.PositiveIntegerField(default=1)),
                ("approver_roles", models.JSONField(blank=True, default=list)),
                ("approver_permissions", models.JSONField(blank=True, default=list)),
                ("fallback_manager_required", models.BooleanField(default=False)),
                ("status", models.CharField(choices=[("active", "Active"), ("inactive", "Inactive"), ("archived", "Archived")], default="active", max_length=20)),
                ("effective_from", models.DateField(blank=True, null=True)),
                ("effective_to", models.DateField(blank=True, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("createdby", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("entity", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="approval_policies", to="entity.entity")),
                ("org_unit", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="approval_policies", to="entity.entityorgunit")),
                ("subentity", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="approval_policies", to="entity.subentity")),
            ],
            options={
                "ordering": ["entity_id", "policy_key", "subentity_id", "org_unit_id", "name", "id"],
                "indexes": [
                    models.Index(fields=["entity", "policy_key", "isactive"], name="entity_entit_entity__ecbab2_idx"),
                    models.Index(fields=["entity", "subentity", "policy_key"], name="entity_entit_entity__cf8875_idx"),
                    models.Index(fields=["entity", "org_unit", "policy_key"], name="entity_entit_entity__57d9e5_idx"),
                    models.Index(fields=["entity", "status"], name="entity_entit_entity__4c1d53_idx"),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="entityapprovalpolicy",
            constraint=models.UniqueConstraint(condition=models.Q(("isactive", True)), fields=("entity", "code"), name="uq_entity_approval_policy_code_active"),
        ),
    ]
