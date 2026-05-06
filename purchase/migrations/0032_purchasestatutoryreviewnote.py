from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ("purchase", "0031_alter_purchasestatutoryform16acertificatedocument_document_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PurchaseStatutoryReviewNote",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tax_type", models.CharField(blank=True, choices=[("IT_TDS", "Income-tax TDS"), ("GST_TDS", "GST-TDS")], db_index=True, max_length=10, null=True)),
                ("period_from", models.DateField(db_index=True)),
                ("period_to", models.DateField(db_index=True)),
                ("reviewer_name", models.CharField(blank=True, max_length=120, null=True)),
                ("closure_status", models.CharField(choices=[("NOT_READY", "Not Ready"), ("IN_REVIEW", "In Review"), ("READY_TO_SIGN_OFF", "Ready To Sign Off")], db_index=True, default="NOT_READY", max_length=24)),
                ("review_summary", models.TextField(blank=True, null=True)),
                ("open_points", models.TextField(blank=True, null=True)),
                ("closure_comment", models.TextField(blank=True, null=True)),
                ("reviewed_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("entity", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="entity.entity")),
                ("entityfinid", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="entity.entityfinancialyear")),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="purchase_statutory_review_notes", to=settings.AUTH_USER_MODEL)),
                ("subentity", models.ForeignKey(blank=True, db_index=True, null=True, on_delete=django.db.models.deletion.PROTECT, to="entity.subentity")),
            ],
            options={
                "indexes": [
                    models.Index(fields=["entity", "entityfinid", "period_from", "period_to"], name="ix_pur_stat_review_period"),
                    models.Index(fields=["reviewed_at"], name="ix_pur_stat_review_reviewed"),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="purchasestatutoryreviewnote",
            constraint=models.UniqueConstraint(
                fields=("entity", "entityfinid", "subentity", "tax_type", "period_from", "period_to"),
                condition=Q(subentity__isnull=False, tax_type__isnull=False),
                name="uq_pur_stat_review_scope_sub_tax",
            ),
        ),
        migrations.AddConstraint(
            model_name="purchasestatutoryreviewnote",
            constraint=models.UniqueConstraint(
                fields=("entity", "entityfinid", "subentity", "period_from", "period_to"),
                condition=Q(subentity__isnull=False, tax_type__isnull=True),
                name="uq_pur_stat_review_scope_sub_alltax",
            ),
        ),
        migrations.AddConstraint(
            model_name="purchasestatutoryreviewnote",
            constraint=models.UniqueConstraint(
                fields=("entity", "entityfinid", "tax_type", "period_from", "period_to"),
                condition=Q(subentity__isnull=True, tax_type__isnull=False),
                name="uq_pur_stat_review_scope_nsub_tax",
            ),
        ),
        migrations.AddConstraint(
            model_name="purchasestatutoryreviewnote",
            constraint=models.UniqueConstraint(
                fields=("entity", "entityfinid", "period_from", "period_to"),
                condition=Q(subentity__isnull=True, tax_type__isnull=True),
                name="uq_pur_stat_review_scope_nsub_alltax",
            ),
        ),
    ]
