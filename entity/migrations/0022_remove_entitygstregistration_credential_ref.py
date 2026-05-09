from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("entity", "0021_alter_entitygstregistration_gstin_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="entitygstregistration",
            name="credential_ref",
        ),
    ]
