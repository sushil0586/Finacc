from django.db import migrations


def forwards(apps, schema_editor):
    ReceiptSettings = apps.get_model("receipts", "ReceiptSettings")
    for row in ReceiptSettings.objects.all().only("id", "policy_controls"):
        controls = row.policy_controls or {}
        if not isinstance(controls, dict):
            continue
        if "sync_ap_settlement_on_post" in controls:
            if "sync_ar_settlement_on_post" not in controls:
                controls["sync_ar_settlement_on_post"] = controls.get("sync_ap_settlement_on_post")
            controls.pop("sync_ap_settlement_on_post", None)
            row.policy_controls = controls
            row.save(update_fields=["policy_controls", "updated_at"])


def backwards(apps, schema_editor):
    ReceiptSettings = apps.get_model("receipts", "ReceiptSettings")
    for row in ReceiptSettings.objects.all().only("id", "policy_controls"):
        controls = row.policy_controls or {}
        if not isinstance(controls, dict):
            continue
        if "sync_ar_settlement_on_post" in controls:
            if "sync_ap_settlement_on_post" not in controls:
                controls["sync_ap_settlement_on_post"] = controls.get("sync_ar_settlement_on_post")
            controls.pop("sync_ar_settlement_on_post", None)
            row.policy_controls = controls
            row.save(update_fields=["policy_controls", "updated_at"])


class Migration(migrations.Migration):

    dependencies = [
        ("receipts", "0004_receiptchoiceoverride_receiptlockperiod"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
