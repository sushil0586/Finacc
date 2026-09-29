from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("cfo", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="MonthClosePeriod",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("isactive", models.BooleanField(default=True)),
                ("period_start", models.DateField(db_index=True)),
                ("period_end", models.DateField(db_index=True)),
                ("status", models.CharField(choices=[("open", "Open"), ("locked", "Locked"), ("reopened", "Reopened")], db_index=True, default="open", max_length=20)),
                ("notes", models.TextField(blank=True, default="")),
                ("locked_at", models.DateTimeField(blank=True, null=True)),
                ("entity", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="cfo_month_close_periods", to="entity.entity")),
                ("entityfinid", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="entity.entityfinancialyear")),
                ("locked_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("subentity", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="entity.subentity")),
            ],
            options={
                "ordering": ("-period_end", "-id"),
            },
        ),
        migrations.CreateModel(
            name="MonthCloseTask",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("isactive", models.BooleanField(default=True)),
                ("task_code", models.CharField(db_index=True, max_length=80)),
                ("task_label", models.CharField(max_length=160)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("completed", "Completed"), ("reopened", "Reopened"), ("blocked", "Blocked")], db_index=True, default="pending", max_length=20)),
                ("blocker_reason", models.CharField(blank=True, default="", max_length=255)),
                ("evidence_route", models.CharField(blank=True, default="", max_length=160)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("reopened_at", models.DateTimeField(blank=True, null=True)),
                ("reason", models.TextField(blank=True, default="")),
                ("close_period", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tasks", to="cfo.monthcloseperiod")),
                ("completed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("reopened_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ("sort_order", "id"),
            },
        ),
        migrations.AddIndex(
            model_name="monthcloseperiod",
            index=models.Index(fields=["entity", "entityfinid", "subentity", "period_start", "period_end"], name="ix_cfo_close_scope_period"),
        ),
        migrations.AddIndex(
            model_name="monthcloseperiod",
            index=models.Index(fields=["entity", "status", "period_end"], name="ix_cfo_close_status"),
        ),
        migrations.AddIndex(
            model_name="monthclosetask",
            index=models.Index(fields=["close_period", "status"], name="ix_cfo_close_task_status"),
        ),
        migrations.AddConstraint(
            model_name="monthclosetask",
            constraint=models.UniqueConstraint(fields=("close_period", "task_code"), name="uq_cfo_close_task_code"),
        ),
    ]
