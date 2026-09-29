from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("cfo", "0002_month_close"),
    ]

    operations = [
        migrations.CreateModel(
            name="BudgetLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("isactive", models.BooleanField(default=True)),
                ("period_start", models.DateField(db_index=True)),
                ("period_end", models.DateField(db_index=True)),
                ("category", models.CharField(choices=[("revenue", "Revenue"), ("purchase_expense", "Purchase Expense"), ("gross_snapshot", "Gross Snapshot"), ("statutory_payable", "Statutory Payable")], db_index=True, max_length=40)),
                ("budget_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("notes", models.CharField(blank=True, default="", max_length=255)),
                ("createdby", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("entity", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="cfo_budget_lines", to="entity.entity")),
                ("entityfinid", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="entity.entityfinancialyear")),
                ("subentity", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="entity.subentity")),
            ],
            options={
                "ordering": ("period_start", "category", "id"),
            },
        ),
        migrations.CreateModel(
            name="BudgetVarianceReview",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("isactive", models.BooleanField(default=True)),
                ("period_start", models.DateField(db_index=True)),
                ("period_end", models.DateField(db_index=True)),
                ("category", models.CharField(choices=[("revenue", "Revenue"), ("purchase_expense", "Purchase Expense"), ("gross_snapshot", "Gross Snapshot"), ("statutory_payable", "Statutory Payable")], db_index=True, max_length=40)),
                ("status", models.CharField(choices=[("open", "Open"), ("explained", "Explained"), ("accepted", "Accepted"), ("action_required", "Action Required")], db_index=True, default="open", max_length=30)),
                ("explanation", models.TextField(blank=True, default="")),
                ("action_owner", models.CharField(blank=True, default="", max_length=120)),
                ("due_date", models.DateField(blank=True, null=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("entity", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="cfo_budget_variance_reviews", to="entity.entity")),
                ("entityfinid", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="entity.entityfinancialyear")),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("subentity", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="entity.subentity")),
            ],
            options={
                "ordering": ("period_start", "category", "id"),
            },
        ),
        migrations.AddIndex(
            model_name="budgetline",
            index=models.Index(fields=["entity", "entityfinid", "subentity", "period_start", "period_end"], name="ix_cfo_budget_scope_period"),
        ),
        migrations.AddIndex(
            model_name="budgetline",
            index=models.Index(fields=["entity", "category", "isactive"], name="ix_cfo_budget_category"),
        ),
        migrations.AddIndex(
            model_name="budgetvariancereview",
            index=models.Index(fields=["entity", "status", "period_end"], name="ix_cfo_budget_review_status"),
        ),
        migrations.AddConstraint(
            model_name="budgetline",
            constraint=models.UniqueConstraint(fields=("entity", "entityfinid", "subentity", "period_start", "period_end", "category"), name="uq_cfo_budget_scope_cat"),
        ),
        migrations.AddConstraint(
            model_name="budgetvariancereview",
            constraint=models.UniqueConstraint(fields=("entity", "entityfinid", "subentity", "period_start", "period_end", "category"), name="uq_cfo_budget_review_scope_cat"),
        ),
    ]
