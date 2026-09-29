from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("entity", "0036_allow_shared_subentity_gstin_per_entity"),
    ]

    operations = [
        migrations.CreateModel(
            name="CashFlowForecastAdjustment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("isactive", models.BooleanField(default=True)),
                ("scenario", models.CharField(choices=[("base", "Base"), ("conservative", "Conservative"), ("optimistic", "Optimistic")], db_index=True, default="base", max_length=20)),
                ("adjustment_date", models.DateField(db_index=True)),
                ("direction", models.CharField(choices=[("inflow", "Inflow"), ("outflow", "Outflow")], db_index=True, max_length=10)),
                ("category", models.CharField(db_index=True, default="manual_adjustment", max_length=80)),
                ("description", models.CharField(blank=True, default="", max_length=255)),
                ("amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("createdby", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("entity", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="cfo_cash_flow_adjustments", to="entity.entity")),
                ("entityfinid", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="entity.entityfinancialyear")),
                ("subentity", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="entity.subentity")),
            ],
            options={
                "ordering": ("adjustment_date", "id"),
            },
        ),
        migrations.AddIndex(
            model_name="cashflowforecastadjustment",
            index=models.Index(fields=["entity", "entityfinid", "subentity", "scenario", "adjustment_date"], name="ix_cfo_cf_adj_scope_dt"),
        ),
        migrations.AddIndex(
            model_name="cashflowforecastadjustment",
            index=models.Index(fields=["entity", "scenario", "isactive"], name="ix_cfo_cf_adj_active"),
        ),
    ]
