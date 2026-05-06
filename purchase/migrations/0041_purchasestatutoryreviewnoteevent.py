from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


class Migration(migrations.Migration):

    dependencies = [
        ("purchase", "0040_merge_20260505_0001"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PurchaseStatutoryReviewNoteEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("action", models.CharField(choices=[("CREATED", "Created"), ("UPDATED", "Updated"), ("CLEARED", "Cleared")], db_index=True, max_length=20)),
                ("reviewer_name", models.CharField(blank=True, max_length=120, null=True)),
                ("closure_status", models.CharField(choices=[("NOT_READY", "Not Ready"), ("IN_REVIEW", "In Review"), ("READY_TO_SIGN_OFF", "Ready To Sign Off")], db_index=True, default="NOT_READY", max_length=24)),
                ("review_summary", models.TextField(blank=True, null=True)),
                ("open_points", models.TextField(blank=True, null=True)),
                ("closure_comment", models.TextField(blank=True, null=True)),
                ("changed_at", models.DateTimeField(db_index=True, default=timezone.now)),
                ("changed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="purchase_statutory_review_note_events", to=settings.AUTH_USER_MODEL)),
                ("review_note", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="events", to="purchase.purchasestatutoryreviewnote")),
            ],
            options={
                "indexes": [
                    models.Index(fields=["review_note", "changed_at"], name="ix_pur_stat_review_evt_note"),
                    models.Index(fields=["action", "changed_at"], name="ix_pur_stat_review_evt_act"),
                ],
            },
        ),
    ]
