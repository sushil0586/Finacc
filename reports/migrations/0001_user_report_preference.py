from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("entity", "0015_subentitygstregistration_nature_of_business_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserReportPreference",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("isactive", models.BooleanField(default=True)),
                ("report_code", models.CharField(max_length=120)),
                ("payload", models.JSONField(blank=True, default=dict)),
                (
                    "entity",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="report_preferences",
                        to="entity.entity",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="report_preferences",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("entity_id", "report_code", "-updated_at"),
                "indexes": [models.Index(fields=("user", "entity", "report_code"), name="rep_usr_ent_rep_idx")],
                "constraints": [
                    models.UniqueConstraint(fields=("user", "entity", "report_code"), name="reports_user_entity_report_unique")
                ],
            },
        ),
    ]
