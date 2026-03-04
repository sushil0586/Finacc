from django.db import migrations, models


DEFAULT_POLICY_CONTROLS = {
    "delete_policy": "draft_only",
    "confirm_lock_check": "hard",
    "require_lines_on_confirm": "hard",
    "itc_action_status_gate": "hard",
    "two_b_action_status_gate": "hard",
    "line_amount_mismatch": "hard",
    "invoice_match_mode": "off",
    "invoice_match_enforcement": "off",
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
        ("purchase", "0010_backfill_policy_controls_defaults"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchaseinvoiceheader",
            name="grn_reference_no",
            field=models.CharField(blank=True, db_index=True, max_length=50, null=True),
        ),
        migrations.AddField(
            model_name="purchaseinvoiceheader",
            name="match_notes",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="purchaseinvoiceheader",
            name="match_status",
            field=models.CharField(
                choices=[
                    ("na", "Not Applicable"),
                    ("passed", "Passed"),
                    ("warn", "Warning"),
                    ("failed", "Failed"),
                ],
                db_index=True,
                default="na",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="purchaseinvoiceheader",
            name="po_reference_no",
            field=models.CharField(blank=True, db_index=True, max_length=50, null=True),
        ),
        migrations.AlterField(
            model_name="purchasesettings",
            name="policy_controls",
            field=models.JSONField(blank=True, default=_default_policy_controls),
        ),
        migrations.RunPython(backfill_policy_controls, migrations.RunPython.noop),
    ]

