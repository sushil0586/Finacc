from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


DEFAULT_POLICY_CONTROLS = {
    "delete_policy": "draft_only",
    "confirm_lock_check": "hard",
    "require_lines_on_confirm": "hard",
    "itc_action_status_gate": "hard",
    "two_b_action_status_gate": "hard",
    "line_amount_mismatch": "hard",
    "invoice_match_mode": "off",
    "invoice_match_enforcement": "off",
    "settlement_mode": "off",
    "allocation_policy": "manual",
    "over_settlement_rule": "block",
    "auto_adjust_credit_notes": "off",
}


def _default_policy_controls():
    return dict(DEFAULT_POLICY_CONTROLS)


def backfill_policy_controls(apps, schema_editor):
    PurchaseSettings = apps.get_model("purchase", "PurchaseSettings")
    for row in PurchaseSettings.objects.all().only("id", "policy_controls"):
        raw = row.policy_controls if isinstance(row.policy_controls, dict) else {}
        merged = dict(DEFAULT_POLICY_CONTROLS)
        merged.update(raw)
        if merged != raw:
            row.policy_controls = merged
            row.save(update_fields=["policy_controls"])


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("purchase", "0011_purchaseinvoiceheader_match_hooks_and_policy_defaults"),
    ]

    operations = [
        migrations.CreateModel(
            name="VendorSettlement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("settlement_type", models.CharField(choices=[("payment", "Payment"), ("advance_adjustment", "Advance Adjustment"), ("credit_note_adjustment", "Credit Note Adjustment"), ("debit_note_adjustment", "Debit Note Adjustment"), ("writeoff", "Writeoff"), ("manual", "Manual")], default="payment", max_length=30)),
                ("settlement_date", models.DateField(db_index=True)),
                ("reference_no", models.CharField(blank=True, db_index=True, max_length=50, null=True)),
                ("external_voucher_no", models.CharField(blank=True, db_index=True, max_length=50, null=True)),
                ("remarks", models.CharField(blank=True, max_length=255, null=True)),
                ("total_amount", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("status", models.IntegerField(choices=[(1, "Draft"), (2, "Posted"), (9, "Cancelled")], db_index=True, default=1)),
                ("posted_at", models.DateTimeField(blank=True, null=True)),
                ("entity", models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.PROTECT, to="entity.entity")),
                ("entityfinid", models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.PROTECT, to="entity.entityfinancialyear")),
                ("posted_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="posted_vendor_settlements", to=settings.AUTH_USER_MODEL)),
                ("subentity", models.ForeignKey(blank=True, db_index=True, null=True, on_delete=django.db.models.deletion.PROTECT, to="entity.subentity")),
                ("vendor", models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.PROTECT, to="financial.account")),
            ],
            options={
                "indexes": [
                    models.Index(fields=["entity", "entityfinid", "vendor", "status"], name="ix_pur_settle_scope"),
                    models.Index(fields=["entity", "entityfinid", "settlement_date"], name="ix_pur_settle_date"),
                ],
            },
        ),
        migrations.CreateModel(
            name="VendorBillOpenItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("doc_type", models.IntegerField(db_index=True)),
                ("bill_date", models.DateField(db_index=True)),
                ("due_date", models.DateField(blank=True, db_index=True, null=True)),
                ("purchase_number", models.CharField(blank=True, max_length=50, null=True)),
                ("supplier_invoice_number", models.CharField(blank=True, max_length=50, null=True)),
                ("original_amount", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("settled_amount", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("outstanding_amount", models.DecimalField(db_index=True, decimal_places=2, default=0, max_digits=14)),
                ("is_open", models.BooleanField(db_index=True, default=True)),
                ("last_settled_at", models.DateTimeField(blank=True, null=True)),
                ("entity", models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.PROTECT, to="entity.entity")),
                ("entityfinid", models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.PROTECT, to="entity.entityfinancialyear")),
                ("header", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="ap_open_item", to="purchase.purchaseinvoiceheader")),
                ("subentity", models.ForeignKey(blank=True, db_index=True, null=True, on_delete=django.db.models.deletion.PROTECT, to="entity.subentity")),
                ("vendor", models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.PROTECT, to="financial.account")),
            ],
            options={
                "indexes": [
                    models.Index(fields=["entity", "entityfinid", "vendor", "is_open"], name="ix_pur_ap_open_scope"),
                    models.Index(fields=["entity", "entityfinid", "bill_date"], name="ix_pur_ap_open_billdt"),
                    models.Index(fields=["entity", "entityfinid", "due_date"], name="ix_pur_ap_open_duedt"),
                ],
            },
        ),
        migrations.CreateModel(
            name="VendorSettlementLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("amount", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("applied_amount_signed", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("note", models.CharField(blank=True, max_length=255, null=True)),
                ("open_item", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="settlement_lines", to="purchase.vendorbillopenitem")),
                ("settlement", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lines", to="purchase.vendorsettlement")),
            ],
            options={
                "indexes": [
                    models.Index(fields=["settlement"], name="ix_pur_settleline_settlement"),
                    models.Index(fields=["open_item"], name="ix_pur_settleline_openitem"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("settlement", "open_item"), name="uq_pur_settleline_settlement_openitem"),
                ],
            },
        ),
        migrations.AlterField(
            model_name="purchasesettings",
            name="policy_controls",
            field=models.JSONField(blank=True, default=_default_policy_controls),
        ),
        migrations.RunPython(backfill_policy_controls, migrations.RunPython.noop),
    ]
