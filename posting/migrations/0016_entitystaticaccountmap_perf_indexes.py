from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("posting", "0015_alter_entry_txn_type_and_more"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="entitystaticaccountmap",
            index=models.Index(
                fields=["entity", "is_active", "sub_entity", "effective_from"],
                name="ix_esam_scope_eff",
            ),
        ),
        migrations.AddIndex(
            model_name="entitystaticaccountmap",
            index=models.Index(
                fields=["entity", "is_active", "sub_entity", "static_account"],
                name="ix_esam_scope_static",
            ),
        ),
    ]

