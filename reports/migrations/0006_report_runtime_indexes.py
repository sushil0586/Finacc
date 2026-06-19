from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0005_reportfilingrun_portal_provider"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="userreportpreference",
            index=models.Index(
                fields=["user", "entity", "isactive", "report_code"],
                name="ix_rpt_pref_active",
            ),
        ),
        migrations.AddIndex(
            model_name="reportfreezesnapshot",
            index=models.Index(
                fields=["report_code", "entity", "entityfinid", "subentity", "created_at"],
                name="ix_rpt_frz_latest",
            ),
        ),
        migrations.AddIndex(
            model_name="reportfilingrun",
            index=models.Index(
                fields=["report_code", "entity", "entityfinid", "subentity", "created_at"],
                name="ix_rpt_filing_scope",
            ),
        ),
    ]
