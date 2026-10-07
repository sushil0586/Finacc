from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0011_gstcomplianceperiodlifecycle_and_more"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="reportfreezesnapshot",
            index=models.Index(
                fields=["report_code", "entity", "entityfinid", "subentity", "isactive", "version"],
                name="ix_rpt_frz_ctrl_ver",
            ),
        ),
    ]
