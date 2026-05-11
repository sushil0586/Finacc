from decimal import Decimal

from django.db import migrations, models


def backfill_opening_stock_branch_godown(apps, schema_editor):
    OpeningStockByLocation = apps.get_model("catalog", "OpeningStockByLocation")
    Godown = apps.get_model("entity", "Godown")

    for row in OpeningStockByLocation.objects.all().iterator():
        qty = Decimal(str(row.openingqty or 0))
        rate = Decimal(str(row.openingrate or 0))
        updates = {"openingvalue": qty * rate}

        godown = None
        if row.branch_id:
            godown = (
                Godown.objects.filter(entity_id=row.entity_id, subentity_id=row.branch_id, is_active=True)
                .order_by("-is_default", "id")
                .first()
            )
        if godown is None:
            godown = (
                Godown.objects.filter(entity_id=row.entity_id, subentity__isnull=True, is_active=True)
                .order_by("-is_default", "id")
                .first()
            )
        if godown is None:
            godown = (
                Godown.objects.filter(entity_id=row.entity_id, is_active=True)
                .order_by("-is_default", "id")
                .first()
            )
        if godown is not None:
            updates["godown_id"] = godown.id

        OpeningStockByLocation.objects.filter(pk=row.pk).update(**updates)


class Migration(migrations.Migration):

    dependencies = [
        ("entity", "0018_entityconstitutionv2_account_preference_and_agreement_reference"),
        ("catalog", "0010_product_default_asset_category"),
    ]

    operations = [
        migrations.RenameField(
            model_name="openingstockbylocation",
            old_name="location",
            new_name="branch",
        ),
        migrations.AddField(
            model_name="openingstockbylocation",
            name="godown",
            field=models.ForeignKey(blank=True, null=True, on_delete=models.PROTECT, related_name="catalog_opening_stocks", to="entity.godown"),
        ),
        migrations.RemoveConstraint(
            model_name="openingstockbylocation",
            name="uq_openingstock_entity_product_location_date",
        ),
        migrations.RunPython(backfill_opening_stock_branch_godown, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="openingstockbylocation",
            constraint=models.UniqueConstraint(fields=("entity", "product", "branch", "godown", "as_of_date"), name="uq_openingstock_entity_product_branch_godown_date"),
        ),
    ]
