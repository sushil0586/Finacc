from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("purchase", "0013_alter_purchasesettings_policy_controls"),
    ]

    operations = [
        migrations.CreateModel(
            name="PurchaseStatutoryChallan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tax_type", models.CharField(choices=[("IT_TDS", "Income-tax TDS"), ("GST_TDS", "GST-TDS")], db_index=True, max_length=10)),
                ("challan_no", models.CharField(db_index=True, max_length=50)),
                ("challan_date", models.DateField(db_index=True, default=django.utils.timezone.localdate)),
                ("period_from", models.DateField(blank=True, db_index=True, null=True)),
                ("period_to", models.DateField(blank=True, db_index=True, null=True)),
                ("amount", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("bank_ref_no", models.CharField(blank=True, db_index=True, max_length=100, null=True)),
                ("bsr_code", models.CharField(blank=True, db_index=True, max_length=20, null=True)),
                ("status", models.IntegerField(choices=[(1, "Draft"), (2, "Deposited"), (9, "Cancelled")], db_index=True, default=1)),
                ("deposited_on", models.DateField(blank=True, db_index=True, null=True)),
                ("deposited_at", models.DateTimeField(blank=True, null=True)),
                ("remarks", models.CharField(blank=True, max_length=255, null=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="purchase_statutory_challans_created", to=settings.AUTH_USER_MODEL)),
                ("deposited_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="purchase_statutory_challans_deposited", to=settings.AUTH_USER_MODEL)),
                ("entity", models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.PROTECT, to="entity.entity")),
                ("entityfinid", models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.PROTECT, to="entity.entityfinancialyear")),
                ("subentity", models.ForeignKey(blank=True, db_index=True, null=True, on_delete=django.db.models.deletion.PROTECT, to="entity.subentity")),
            ],
            options={
                "indexes": [
                    models.Index(fields=["entity", "entityfinid", "tax_type", "status"], name="ix_pur_stat_challan_scope"),
                    models.Index(fields=["entity", "entityfinid", "challan_date"], name="ix_pur_stat_challan_date"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("entity", "entityfinid", "subentity", "tax_type", "challan_no"), name="uq_pur_stat_challan_scope_type_no"),
                    models.CheckConstraint(check=models.Q(amount__gte=0), name="ck_pur_stat_challan_amount_nonneg"),
                ],
            },
        ),
        migrations.CreateModel(
            name="PurchaseStatutoryReturn",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tax_type", models.CharField(choices=[("IT_TDS", "Income-tax TDS"), ("GST_TDS", "GST-TDS")], db_index=True, max_length=10)),
                ("return_code", models.CharField(db_index=True, max_length=30)),
                ("period_from", models.DateField(db_index=True)),
                ("period_to", models.DateField(db_index=True)),
                ("amount", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("status", models.IntegerField(choices=[(1, "Draft"), (2, "Filed"), (3, "Revised"), (9, "Cancelled")], db_index=True, default=1)),
                ("filed_on", models.DateField(blank=True, db_index=True, null=True)),
                ("filed_at", models.DateTimeField(blank=True, null=True)),
                ("ack_no", models.CharField(blank=True, db_index=True, max_length=100, null=True)),
                ("remarks", models.CharField(blank=True, max_length=255, null=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="purchase_statutory_returns_created", to=settings.AUTH_USER_MODEL)),
                ("entity", models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.PROTECT, to="entity.entity")),
                ("entityfinid", models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.PROTECT, to="entity.entityfinancialyear")),
                ("filed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="purchase_statutory_returns_filed", to=settings.AUTH_USER_MODEL)),
                ("subentity", models.ForeignKey(blank=True, db_index=True, null=True, on_delete=django.db.models.deletion.PROTECT, to="entity.subentity")),
            ],
            options={
                "indexes": [
                    models.Index(fields=["entity", "entityfinid", "tax_type", "status"], name="ix_pur_stat_return_scope"),
                    models.Index(fields=["entity", "entityfinid", "period_from", "period_to"], name="ix_pur_stat_return_period"),
                ],
                "constraints": [
                    models.CheckConstraint(check=models.Q(amount__gte=0), name="ck_pur_stat_return_amount_nonneg"),
                ],
            },
        ),
        migrations.CreateModel(
            name="PurchaseStatutoryReturnLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("amount", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("challan", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="return_lines", to="purchase.purchasestatutorychallan")),
                ("filing", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lines", to="purchase.purchasestatutoryreturn")),
                ("header", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="statutory_return_lines", to="purchase.purchaseinvoiceheader")),
            ],
            options={
                "indexes": [
                    models.Index(fields=["filing"], name="ix_pur_stat_return_line_filing"),
                    models.Index(fields=["header"], name="ix_pur_stat_return_line_header"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("filing", "header"), name="uq_pur_stat_return_line_filing_header"),
                    models.CheckConstraint(check=models.Q(amount__gt=0), name="ck_pur_stat_return_line_amount_pos"),
                ],
            },
        ),
        migrations.CreateModel(
            name="PurchaseStatutoryChallanLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("amount", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("challan", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lines", to="purchase.purchasestatutorychallan")),
                ("header", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="statutory_challan_lines", to="purchase.purchaseinvoiceheader")),
                ("section", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="purchase_statutory_challan_lines", to="withholding.withholdingsection")),
            ],
            options={
                "indexes": [
                    models.Index(fields=["challan"], name="ix_pur_stcl_challan"),
                    models.Index(fields=["header"], name="ix_pur_stcl_header"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("challan", "header"), name="uq_pur_stat_challan_line_challan_header"),
                    models.CheckConstraint(check=models.Q(amount__gt=0), name="ck_pur_stat_challan_line_amount_pos"),
                ],
            },
        ),
    ]
