from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("cfo", "0003_budget_variance"),
    ]

    operations = [
        migrations.CreateModel(
            name="CfoRiskReview",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("isactive", models.BooleanField(default=True)),
                ("item_key", models.CharField(db_index=True, max_length=180, unique=True)),
                ("risk_type", models.CharField(db_index=True, max_length=60)),
                ("source_type", models.CharField(db_index=True, max_length=60)),
                ("source_id", models.CharField(blank=True, default="", max_length=80)),
                ("status", models.CharField(choices=[("open", "Open"), ("acknowledged", "Acknowledged"), ("resolved", "Resolved"), ("dismissed", "Dismissed")], db_index=True, default="open", max_length=30)),
                ("note", models.TextField(blank=True, default="")),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("entity", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="cfo_risk_reviews", to="entity.entity")),
                ("entityfinid", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="entity.entityfinancialyear")),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("subentity", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="entity.subentity")),
            ],
            options={
                "ordering": ("-updated_at", "-id"),
            },
        ),
        migrations.AddIndex(
            model_name="cforiskreview",
            index=models.Index(fields=["entity", "status", "risk_type"], name="ix_cfo_risk_status_type"),
        ),
        migrations.AddIndex(
            model_name="cforiskreview",
            index=models.Index(fields=["entity", "entityfinid", "subentity", "status"], name="ix_cfo_risk_scope_status"),
        ),
    ]
