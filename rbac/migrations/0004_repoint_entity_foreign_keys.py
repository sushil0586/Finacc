from django.db import migrations


def repoint_entity_foreign_keys(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    constraint_updates = [
        (
            "rbac_role",
            "rbac_role_entity_id_08a85b57_fk_organization_entity_id",
            "rbac_role_entity_id_08a85b57_fk_entity_entity_id",
            "ALTER TABLE rbac_role ADD CONSTRAINT rbac_role_entity_id_08a85b57_fk_entity_entity_id "
            "FOREIGN KEY (entity_id) REFERENCES entity_entity(id) DEFERRABLE INITIALLY DEFERRED;",
        ),
        (
            "rbac_userroleassignment",
            "rbac_userroleassignm_entity_id_679ee746_fk_organizat",
            "rbac_userroleassignment_entity_id_fk_entity_entity",
            "ALTER TABLE rbac_userroleassignment ADD CONSTRAINT rbac_userroleassignment_entity_id_fk_entity_entity "
            "FOREIGN KEY (entity_id) REFERENCES entity_entity(id) DEFERRABLE INITIALLY DEFERRED;",
        ),
        (
            "rbac_userroleassignment",
            "rbac_userroleassignm_subentity_id_b3605565_fk_organizat",
            "rbac_userroleassignment_subentity_id_fk_entity_subentity",
            "ALTER TABLE rbac_userroleassignment ADD CONSTRAINT rbac_userroleassignment_subentity_id_fk_entity_subentity "
            "FOREIGN KEY (subentity_id) REFERENCES entity_subentity(id) DEFERRABLE INITIALLY DEFERRED;",
        ),
        (
            "rbac_dataaccesspolicy",
            "rbac_dataaccesspolic_entity_id_6a815bc1_fk_organizat",
            "rbac_dataaccesspolicy_entity_id_fk_entity_entity",
            "ALTER TABLE rbac_dataaccesspolicy ADD CONSTRAINT rbac_dataaccesspolicy_entity_id_fk_entity_entity "
            "FOREIGN KEY (entity_id) REFERENCES entity_entity(id) DEFERRABLE INITIALLY DEFERRED;",
        ),
    ]

    with schema_editor.connection.cursor() as cursor:
        for table_name, legacy_constraint, desired_constraint, add_statement in constraint_updates:
            cursor.execute(f"ALTER TABLE {table_name} DROP CONSTRAINT IF EXISTS {legacy_constraint};")
            cursor.execute(
                """
                SELECT 1
                FROM pg_constraint con
                JOIN pg_class rel ON rel.oid = con.conrelid
                WHERE rel.relname = %s
                  AND con.conname = %s
                """,
                [table_name, desired_constraint],
            )
            if cursor.fetchone():
                continue
            cursor.execute(add_statement)


class Migration(migrations.Migration):

    dependencies = [
        ("rbac", "0003_cleanup_orphaned_references"),
    ]

    operations = [
        migrations.RunPython(repoint_entity_foreign_keys, migrations.RunPython.noop),
    ]
