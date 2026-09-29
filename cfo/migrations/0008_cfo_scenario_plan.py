from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("cfo", "0007_cfo_insight_signal"),
    ]

    operations = [
        migrations.CreateModel(
            name="CfoScenarioPlan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("isactive", models.BooleanField(default=True)),
                ("period_start", models.DateField(db_index=True)),
                ("period_end", models.DateField(db_index=True)),
                ("title", models.CharField(max_length=180)),
                ("status", models.CharField(choices=[("draft", "Draft"), ("approved", "Approved"), ("archived", "Archived")], db_index=True, default="draft", max_length=20)),
                ("assumptions", models.JSONField(blank=True, default=dict)),
                ("result", models.JSONField(blank=True, default=dict)),
                ("notes", models.TextField(blank=True, default="")),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("approved_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("createdby", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("entity", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="cfo_scenario_plans", to="entity.entity")),
                ("entityfinid", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="entity.entityfinancialyear")),
                ("subentity", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="entity.subentity")),
            ],
            options={
                "ordering": ("-updated_at", "-id"),
            },
        ),
        migrations.AddIndex(
            model_name="cfoscenarioplan",
            index=models.Index(fields=["entity", "entityfinid", "subentity", "period_start", "period_end"], name="ix_cfo_scenario_scope"),
        ),
        migrations.AddIndex(
            model_name="cfoscenarioplan",
            index=models.Index(fields=["entity", "status", "period_end"], name="ix_cfo_scenario_status"),
        ),
    ]
