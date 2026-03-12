from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


DEFAULT_PAYMENT_POLICY_CONTROLS = {
    "require_allocation_on_post": "hard",
    "allow_advance_without_allocation": "on",
    "sync_ap_settlement_on_post": "on",
    "allocation_policy": "manual",
    "over_settlement_rule": "block",
}


def default_payment_policy_controls():
    return dict(DEFAULT_PAYMENT_POLICY_CONTROLS)


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("purchase", "0012_vendor_ap_models_and_policy_settlement_defaults"),
    ]

    operations = [
        migrations.CreateModel(
            name="PaymentSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("default_doc_code_payment", models.CharField(default="PPV", max_length=10)),
                ("default_workflow_action", models.CharField(choices=[("draft", "Save as Draft"), ("confirm", "Auto Confirm on Save"), ("post", "Auto Post on Save")], db_index=True, default="draft", max_length=10)),
                ("policy_controls", models.JSONField(blank=True, default=default_payment_policy_controls)),
                ("entity", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="payment_settings", to="entity.entity")),
                ("subentity", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="payment_settings", to="entity.subentity")),
            ],
            options={
                "indexes": [models.Index(fields=["entity"], name="ix_payment_settings_entity")],
                "constraints": [models.UniqueConstraint(fields=("entity", "subentity"), name="uq_payment_settings_entity_subentity")],
            },
        ),
        migrations.CreateModel(
            name="PaymentVoucherHeader",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("voucher_date", models.DateField(db_index=True, default=django.utils.timezone.localdate)),
                ("doc_code", models.CharField(default="PPV", max_length=10)),
                ("doc_no", models.PositiveIntegerField(blank=True, null=True)),
                ("voucher_code", models.CharField(blank=True, max_length=50, null=True)),
                ("payment_type", models.CharField(choices=[("AGAINST_BILL", "Against Bill"), ("ADVANCE", "Advance Payment"), ("ON_ACCOUNT", "On Account")], default="AGAINST_BILL", max_length=20)),
                ("supply_type", models.CharField(choices=[("GOODS", "Goods"), ("SERVICES", "Services"), ("MIXED", "Mixed/Unknown")], default="SERVICES", max_length=10)),
                ("cash_paid_amount", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("total_adjustment_amount", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("settlement_effective_amount", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("reference_number", models.CharField(blank=True, max_length=100, null=True)),
                ("narration", models.TextField(blank=True, null=True)),
                ("instrument_bank_name", models.CharField(blank=True, max_length=100, null=True)),
                ("instrument_no", models.CharField(blank=True, max_length=50, null=True)),
                ("instrument_date", models.DateField(blank=True, null=True)),
                ("vendor_gstin", models.CharField(blank=True, max_length=15, null=True)),
                ("advance_taxable_value", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("advance_cgst", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("advance_sgst", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("advance_igst", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("advance_cess", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("status", models.IntegerField(choices=[(1, "Draft"), (2, "Confirmed"), (3, "Posted"), (9, "Cancelled")], db_index=True, default=1)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("is_cancelled", models.BooleanField(default=False)),
                ("cancelled_at", models.DateTimeField(blank=True, null=True)),
                ("cancel_reason", models.CharField(blank=True, max_length=255, null=True)),
                ("ap_settlement", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="payment_voucher", to="purchase.vendorsettlement")),
                ("approved_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="new_pv_approved", to=settings.AUTH_USER_MODEL)),
                ("cancelled_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="new_payment_vouchers_cancelled", related_query_name="new_payment_voucher_cancelled", to=settings.AUTH_USER_MODEL)),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="new_pv_created", to=settings.AUTH_USER_MODEL)),
                ("entity", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="entity.entity")),
                ("entityfinid", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="entity.entityfinancialyear")),
                ("paid_from", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="new_pv_paid_from", to="financial.account")),
                ("paid_to", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="new_pv_paid_to", to="financial.account")),
                ("place_of_supply_state", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="geography.state")),
                ("subentity", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to="entity.subentity")),
            ],
            options={
                "indexes": [
                    models.Index(fields=["entity", "entityfinid", "voucher_date"], name="ix_pay_ent_fin_date"),
                    models.Index(fields=["entity", "entityfinid", "paid_to"], name="ix_pay_ent_fin_vendor"),
                    models.Index(fields=["entity", "entityfinid", "status"], name="ix_pay_ent_fin_status"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("entity", "entityfinid", "doc_code", "doc_no"), name="uq_payment_voucher_entity_fin_code_no"),
                    models.CheckConstraint(check=models.Q(cash_paid_amount__gte=0), name="ck_payment_cash_nonneg"),
                ],
            },
        ),
        migrations.CreateModel(
            name="PaymentVoucherAllocation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("settled_amount", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("is_full_settlement", models.BooleanField(default=False)),
                ("is_advance_adjustment", models.BooleanField(default=False)),
                ("open_item", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="payment_allocations", to="purchase.vendorbillopenitem")),
                ("payment_voucher", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="allocations", to="payments.paymentvoucherheader")),
            ],
            options={
                "indexes": [
                    models.Index(fields=["payment_voucher"], name="ix_payment_alloc_voucher"),
                    models.Index(fields=["open_item"], name="ix_payment_alloc_openitem"),
                ],
                "constraints": [
                    models.CheckConstraint(check=models.Q(settled_amount__gte=0), name="ck_payment_alloc_amt_nonneg"),
                    models.UniqueConstraint(fields=("payment_voucher", "open_item"), name="uq_payment_alloc_voucher_openitem"),
                ],
            },
        ),
        migrations.CreateModel(
            name="PaymentVoucherAdjustment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("adj_type", models.CharField(choices=[("TDS", "TDS"), ("TCS", "TCS"), ("DISCOUNT_RCVD", "Discount Received"), ("BANK_CHARGES", "Bank Charges"), ("ROUND_OFF", "Round Off"), ("WRITE_OFF", "Write Off"), ("FX_DIFF", "Forex Difference"), ("OTHER", "Other")], max_length=20)),
                ("amount", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("settlement_effect", models.CharField(choices=[("PLUS", "Plus"), ("MINUS", "Minus")], default="PLUS", max_length=5)),
                ("remarks", models.CharField(blank=True, max_length=200, null=True)),
                ("allocation", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="adjustments", to="payments.paymentvoucherallocation")),
                ("ledger_account", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="new_payment_adjustment_ledgers", to="financial.account")),
                ("payment_voucher", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="adjustments", to="payments.paymentvoucherheader")),
            ],
            options={
                "constraints": [
                    models.CheckConstraint(check=models.Q(amount__gte=0), name="ck_payment_adj_amt_nonneg"),
                ],
            },
        ),
    ]
