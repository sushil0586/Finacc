from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0041_sales_compliance_artifact_provenance"),
    ]

    operations = [
        migrations.DeleteModel(
            name="SalesNICCredential",
        ),
        migrations.DeleteModel(
            name="MasterGSTToken",
        ),
    ]
