from django.db import migrations, models
import re


GENERATED_CODE_RE = re.compile(r"^PRD-\d{6}-\d{6}$")


def backfill_barcode_source(apps, schema_editor):
    ProductBarcode = apps.get_model("catalog", "ProductBarcode")

    rows = []
    for row in ProductBarcode.objects.all().only("id", "barcode", "barcode_source"):
        barcode = (row.barcode or "").strip()
        if not barcode:
            row.barcode_source = "generated"
        elif GENERATED_CODE_RE.match(barcode):
            row.barcode_source = "generated"
        else:
            row.barcode_source = "manual"
        rows.append(row)

    if rows:
        ProductBarcode.objects.bulk_update(rows, ["barcode_source"], batch_size=500)


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0006_barcode_hardening_and_template_subentity"),
    ]

    operations = [
        migrations.AddField(
            model_name="productbarcode",
            name="barcode_source",
            field=models.CharField(blank=True, choices=[("manual", "Manual"), ("generated", "Generated"), ("imported", "Imported")], default="", max_length=20),
        ),
        migrations.RunPython(backfill_barcode_source, migrations.RunPython.noop),
    ]
