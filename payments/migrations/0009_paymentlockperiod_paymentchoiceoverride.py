from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0008_payment_ledger_native_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="PaymentLockPeriod",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("lock_date", models.DateField()),
                ("reason", models.CharField(blank=True, max_length=200, null=True)),
                ("entity", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="entity.entity")),
                ("subentity", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to="entity.subentity")),
            ],
            options={
                "indexes": [models.Index(fields=["entity", "subentity", "lock_date"], name="ix_payment_lock_period")],
            },
        ),
        migrations.CreateModel(
            name="PaymentChoiceOverride",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("choice_group", models.CharField(max_length=50)),
                ("choice_key", models.CharField(max_length=50)),
                ("is_enabled", models.BooleanField(default=True)),
                ("override_label", models.CharField(blank=True, max_length=200, null=True)),
                ("entity", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="entity.entity")),
                ("subentity", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to="entity.subentity")),
            ],
            options={
                "indexes": [models.Index(fields=["entity", "subentity", "choice_group"], name="ix_pay_choice_override_scope")],
                "constraints": [
                    models.UniqueConstraint(fields=("entity", "subentity", "choice_group", "choice_key"), name="uq_payment_choice_override_scope"),
                    models.CheckConstraint(check=Q(choice_group__isnull=False) & Q(choice_key__isnull=False), name="ck_payment_choice_override_group_key_nn"),
                ],
            },
        ),
    ]
