from django.db import migrations


def drop_legacy_columns(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    statements = [
        "ALTER TABLE rbac_userroleassignment DROP COLUMN IF EXISTS active;",
        "ALTER TABLE rbac_dataaccesspolicy DROP COLUMN IF EXISTS active;",
        "ALTER TABLE rbac_dataaccesspolicy DROP COLUMN IF EXISTS role_id;",
    ]
    with schema_editor.connection.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0005_fix_entity_foreign_keys"),
    ]

    operations = [
        migrations.RunPython(drop_legacy_columns, migrations.RunPython.noop),
    ]

