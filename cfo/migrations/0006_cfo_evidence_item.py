from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("cfo", "0005_cfo_management_pack_snapshot"),
    ]

    operations = [
        migrations.CreateModel(
            name="CfoEvidenceItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("isactive", models.BooleanField(default=True)),
                ("period_start", models.DateField(db_index=True)),
                ("period_end", models.DateField(db_index=True)),
                ("evidence_type", models.CharField(choices=[("management_pack", "Management Pack"), ("reconciliation", "Reconciliation"), ("variance_review", "Variance Review"), ("risk_review", "Risk Review"), ("close_evidence", "Close Evidence"), ("other", "Other")], db_index=True, default="other", max_length=40)),
                ("title", models.CharField(max_length=180)),
                ("description", models.TextField(blank=True, default="")),
                ("source_type", models.CharField(blank=True, db_index=True, default="", max_length=60)),
                ("source_id", models.CharField(blank=True, default="", max_length=80)),
                ("source_route", models.CharField(blank=True, default="", max_length=180)),
                ("status", models.CharField(choices=[("open", "Open"), ("reviewed", "Reviewed"), ("rejected", "Rejected"), ("archived", "Archived")], db_index=True, default="open", max_length=20)),
                ("owner", models.CharField(blank=True, default="", max_length=120)),
                ("due_date", models.DateField(blank=True, null=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("createdby", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("entity", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="cfo_evidence_items", to="entity.entity")),
                ("entityfinid", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="entity.entityfinancialyear")),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("subentity", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="entity.subentity")),
            ],
            options={
                "ordering": ("-updated_at", "-id"),
            },
        ),
        migrations.AddIndex(
            model_name="cfoevidenceitem",
            index=models.Index(fields=["entity", "entityfinid", "subentity", "period_start", "period_end"], name="ix_cfo_evid_scope_period"),
        ),
        migrations.AddIndex(
            model_name="cfoevidenceitem",
            index=models.Index(fields=["entity", "status", "evidence_type"], name="ix_cfo_evid_status_type"),
        ),
    ]
