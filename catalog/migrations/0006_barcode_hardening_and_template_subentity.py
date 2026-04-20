from django.db import migrations, models
from django.db.models import Count, Q
import django.db.models.deletion


def backfill_product_barcode_entity(apps, schema_editor):
    ProductBarcode = apps.get_model("catalog", "ProductBarcode")

    for row in ProductBarcode.objects.select_related("product").filter(entity__isnull=True):
        if row.product_id and getattr(row.product, "entity_id", None):
            ProductBarcode.objects.filter(pk=row.pk).update(entity_id=row.product.entity_id)

    duplicates = (
        ProductBarcode.objects
        .exclude(entity__isnull=True)
        .exclude(barcode__isnull=True)
        .exclude(barcode="")
        .values("entity_id", "barcode")
        .annotate(total=Count("id"))
        .filter(total__gt=1)
        .order_by("entity_id", "barcode")
    )
    if duplicates.exists():
        samples = ", ".join(
            f"entity={row['entity_id']} barcode={row['barcode']} count={row['total']}"
            for row in duplicates[:10]
        )
        raise RuntimeError(
            "Duplicate barcodes already exist within one entity. "
            f"Clean them before enabling the hard constraint. Samples: {samples}"
        )


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0005_barcodelabeltemplate"),
    ]

    operations = [
        migrations.AddField(
            model_name="productbarcode",
            name="entity",
            field=models.ForeignKey(
                blank=True,
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="catalog_product_barcodes",
                to="entity.entity",
            ),
        ),
        migrations.AddField(
            model_name="barcodelabeltemplate",
            name="subentity",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="barcode_label_templates",
                to="entity.subentity",
            ),
        ),
        migrations.RunPython(backfill_product_barcode_entity, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="barcodelabeltemplate",
            name="uq_barcode_label_template_entity_name",
        ),
        migrations.RemoveConstraint(
            model_name="barcodelabeltemplate",
            name="uq_barcode_label_template_one_default",
        ),
        migrations.AddConstraint(
            model_name="productbarcode",
            constraint=models.UniqueConstraint(
                condition=Q(entity__isnull=False) & Q(barcode__isnull=False) & ~Q(barcode=""),
                fields=("entity", "barcode"),
                name="uq_productbarcode_entity_barcode",
            ),
        ),
        migrations.AddConstraint(
            model_name="barcodelabeltemplate",
            constraint=models.UniqueConstraint(
                condition=Q(subentity__isnull=True),
                fields=("entity", "name"),
                name="uq_barcode_label_template_entity_name_global",
            ),
        ),
        migrations.AddConstraint(
            model_name="barcodelabeltemplate",
            constraint=models.UniqueConstraint(
                condition=Q(subentity__isnull=False),
                fields=("entity", "subentity", "name"),
                name="uq_barcode_label_template_subentity_name",
            ),
        ),
        migrations.AddConstraint(
            model_name="barcodelabeltemplate",
            constraint=models.UniqueConstraint(
                condition=Q(isdefault=True, subentity__isnull=True),
                fields=("entity",),
                name="uq_barcode_label_template_one_default",
            ),
        ),
        migrations.AddConstraint(
            model_name="barcodelabeltemplate",
            constraint=models.UniqueConstraint(
                condition=Q(isdefault=True, subentity__isnull=False),
                fields=("entity", "subentity"),
                name="uq_barcode_label_template_one_default_subentity",
            ),
        ),
    ]
