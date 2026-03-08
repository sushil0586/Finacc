from django.db import migrations


def fix_entity_foreign_keys(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    desired = {
        "rbac_role": {
            "entity_id": ("entity_entity", "rbac_role_entity_id_fk_entity_entity"),
        },
        "rbac_userroleassignment": {
            "entity_id": ("entity_entity", "rbac_userroleassignment_entity_id_fk_entity_entity"),
            "subentity_id": ("entity_subentity", "rbac_userroleassignment_subentity_id_fk_entity_subentity"),
        },
        "rbac_dataaccesspolicy": {
            "entity_id": ("entity_entity", "rbac_dataaccesspolicy_entity_id_fk_entity_entity"),
        },
    }

    with schema_editor.connection.cursor() as cursor:
        for table_name, columns in desired.items():
            cursor.execute(
                """
                SELECT con.conname, a.attname, pg_get_constraintdef(con.oid)
                FROM pg_constraint con
                JOIN pg_class rel ON rel.oid = con.conrelid
                JOIN unnest(con.conkey) WITH ORDINALITY AS cols(attnum, ord) ON true
                JOIN pg_attribute a ON a.attrelid = rel.oid AND a.attnum = cols.attnum
                WHERE rel.relname = %s AND con.contype = 'f'
                """,
                [table_name],
            )
            existing = cursor.fetchall()
            for constraint_name, column_name, definition in existing:
                target = columns.get(column_name)
                if target and target[0] not in definition:
                    cursor.execute(f'ALTER TABLE "{table_name}" DROP CONSTRAINT IF EXISTS "{constraint_name}"')

            for column_name, (target_table, constraint_name) in columns.items():
                cursor.execute(
                    """
                    SELECT 1
                    FROM pg_constraint con
                    JOIN pg_class rel ON rel.oid = con.conrelid
                    JOIN unnest(con.conkey) WITH ORDINALITY AS cols(attnum, ord) ON true
                    JOIN pg_attribute a ON a.attrelid = rel.oid AND a.attnum = cols.attnum
                    WHERE rel.relname = %s
                      AND con.contype = 'f'
                      AND a.attname = %s
                      AND pg_get_constraintdef(con.oid) ILIKE %s
                    """,
                    [table_name, column_name, f"%REFERENCES {target_table}(id)%"],
                )
                if cursor.fetchone():
                    continue
                cursor.execute(
                    f'ALTER TABLE "{table_name}" ADD CONSTRAINT "{constraint_name}" '
                    f'FOREIGN KEY ("{column_name}") REFERENCES "{target_table}"(id) DEFERRABLE INITIALLY DEFERRED'
                )


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0004_repoint_entity_foreign_keys"),
    ]

    operations = [
        migrations.RunPython(fix_entity_foreign_keys, migrations.RunPython.noop),
    ]
