from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("auditlogger", "0002_auditlog_ix_auditlog_method_ts_and_more"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(fields=["action", "timestamp"], name="ix_auditlog_action_ts"),
        ),
    ]
