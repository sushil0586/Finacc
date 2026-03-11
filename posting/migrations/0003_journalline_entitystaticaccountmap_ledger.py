from django.db import migrations, models
import django.db.models.deletion


def backfill_posting_ledgers(apps, schema_editor):
    EntityStaticAccountMap = apps.get_model("posting", "EntityStaticAccountMap")
    JournalLine = apps.get_model("posting", "JournalLine")

    for mapping in EntityStaticAccountMap.objects.filter(account_id__isnull=False, ledger_id__isnull=True).select_related("account"):
        ledger_id = getattr(mapping.account, "ledger_id", None)
        if ledger_id:
            EntityStaticAccountMap.objects.filter(pk=mapping.pk).update(ledger_id=ledger_id)

    for line in JournalLine.objects.filter(account_id__isnull=False, ledger_id__isnull=True).select_related("account"):
        ledger_id = getattr(line.account, "ledger_id", None)
        if ledger_id:
            JournalLine.objects.filter(pk=line.pk).update(ledger_id=ledger_id)


def reverse_backfill_posting_ledgers(apps, schema_editor):
    EntityStaticAccountMap = apps.get_model("posting", "EntityStaticAccountMap")
    JournalLine = apps.get_model("posting", "JournalLine")

    EntityStaticAccountMap.objects.update(ledger_id=None)
    JournalLine.objects.update(ledger_id=None)


class Migration(migrations.Migration):

    dependencies = [
        ("financial", "0004_account_uq_account_entity_accountcode_present"),
        ("posting", "0002_alter_entry_txn_type_alter_inventorymove_txn_type_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="entitystaticaccountmap",
            name="ledger",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="financial.ledger"),
        ),
        migrations.AddField(
            model_name="journalline",
            name="ledger",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="financial.ledger"),
        ),
        migrations.AddIndex(
            model_name="entitystaticaccountmap",
            index=models.Index(fields=["entity", "ledger"], name="ix_esam_entity_ledger"),
        ),
        migrations.AddIndex(
            model_name="journalline",
            index=models.Index(fields=["ledger"], name="ix_jl_posting_ledger"),
        ),
        migrations.RunPython(backfill_posting_ledgers, reverse_backfill_posting_ledgers),
    ]
