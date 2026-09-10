from django.db import migrations


def forwards(apps, schema_editor):
    StaticAccount = apps.get_model("posting", "StaticAccount")
    StaticAccount.objects.update_or_create(
        code="PROFIT_LOSS_APPROPRIATION",
        defaults={
            "name": "Profit and Loss Appropriation",
            "group": "EQUITY",
            "description": "Clearing ledger for owner and partner remuneration, interest, and residual profit or loss allocation.",
            "is_active": True,
            "is_required": False,
        },
    )


def backwards(apps, schema_editor):
    StaticAccount = apps.get_model("posting", "StaticAccount")
    StaticAccount.objects.filter(code="PROFIT_LOSS_APPROPRIATION").delete()


class Migration(migrations.Migration):
    dependencies = [("posting", "0028_alter_entry_txn_type_alter_inventorymove_txn_type_and_more")]
    operations = [migrations.RunPython(forwards, backwards)]
