from django.db import migrations


def _table_columns(schema_editor, table_name):
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        description = connection.introspection.get_table_description(cursor, table_name)
    return {column.name for column in description}


def reconcile_legacy_rbac_schema(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    table_names = set(schema_editor.connection.introspection.table_names())
    if "rbac_menu" not in table_names:
        return

    with schema_editor.connection.cursor() as cursor:
        menu_columns = _table_columns(schema_editor, "rbac_menu")
        if "route" in menu_columns and "route_path" not in menu_columns:
            cursor.execute("ALTER TABLE rbac_menu RENAME COLUMN route TO route_path;")
        if "is_active" in menu_columns and "is_system_menu" not in menu_columns:
            cursor.execute("ALTER TABLE rbac_menu RENAME COLUMN is_active TO is_system_menu;")
        cursor.execute(
            """
            ALTER TABLE rbac_menu
                ADD COLUMN IF NOT EXISTS menu_type varchar(20) NOT NULL DEFAULT 'screen',
                ADD COLUMN IF NOT EXISTS route_name varchar(150) NOT NULL DEFAULT '',
                ADD COLUMN IF NOT EXISTS depth smallint NOT NULL DEFAULT 0,
                ADD COLUMN IF NOT EXISTS metadata jsonb NOT NULL DEFAULT '{}'::jsonb;
            """
        )

        permission_columns = _table_columns(schema_editor, "rbac_permission")
        if "is_system" in permission_columns and "is_system_defined" not in permission_columns:
            cursor.execute("ALTER TABLE rbac_permission RENAME COLUMN is_system TO is_system_defined;")
        cursor.execute(
            """
            ALTER TABLE rbac_permission
                ADD COLUMN IF NOT EXISTS resource varchar(100) NOT NULL DEFAULT 'general',
                ADD COLUMN IF NOT EXISTS scope_type varchar(20) NOT NULL DEFAULT 'entity',
                ADD COLUMN IF NOT EXISTS metadata jsonb NOT NULL DEFAULT '{}'::jsonb;
            """
        )
        cursor.execute(
            """
            UPDATE rbac_permission
            SET resource = CASE
                WHEN position('.' in code) > 0 THEN split_part(code, '.', 2)
                ELSE 'general'
            END
            WHERE resource = 'general' OR resource = '';
            """
        )

        if "rbac_menupermission" in table_names:
            cursor.execute(
                """
                ALTER TABLE rbac_menupermission
                    ADD COLUMN IF NOT EXISTS relation_type varchar(20) NOT NULL DEFAULT 'visibility';
                """
            )

        role_columns = _table_columns(schema_editor, "rbac_role")
        if "active" in role_columns and "is_assignable" not in role_columns:
            cursor.execute("ALTER TABLE rbac_role RENAME COLUMN active TO is_assignable;")
        cursor.execute(
            """
            ALTER TABLE rbac_role
                ADD COLUMN IF NOT EXISTS role_level varchar(20) NOT NULL DEFAULT 'entity',
                ADD COLUMN IF NOT EXISTS priority integer NOT NULL DEFAULT 100,
                ADD COLUMN IF NOT EXISTS metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
                ADD COLUMN IF NOT EXISTS createdby_id bigint NULL;
            """
        )

        if "rbac_rolepermission" in table_names:
            cursor.execute(
                """
                ALTER TABLE rbac_rolepermission
                    ADD COLUMN IF NOT EXISTS effect varchar(10) NOT NULL DEFAULT 'allow',
                    ADD COLUMN IF NOT EXISTS metadata jsonb NOT NULL DEFAULT '{}'::jsonb;
                """
            )

        if "rbac_dataaccesspolicy" in table_names:
            policy_columns = _table_columns(schema_editor, "rbac_dataaccesspolicy")
            if "scope_type" in policy_columns and "policy_type" not in policy_columns:
                cursor.execute("ALTER TABLE rbac_dataaccesspolicy RENAME COLUMN scope_type TO policy_type;")
            if "rules_json" in policy_columns and "configuration" not in policy_columns:
                cursor.execute("ALTER TABLE rbac_dataaccesspolicy RENAME COLUMN rules_json TO configuration;")
            cursor.execute(
                """
                ALTER TABLE rbac_dataaccesspolicy
                    ADD COLUMN IF NOT EXISTS code varchar(100) NOT NULL DEFAULT '',
                    ADD COLUMN IF NOT EXISTS scope_mode varchar(20) NOT NULL DEFAULT 'allow_all',
                    ADD COLUMN IF NOT EXISTS is_system_defined boolean NOT NULL DEFAULT false;
                """
            )
            cursor.execute(
                """
                UPDATE rbac_dataaccesspolicy
                SET code = CONCAT('policy.', id)
                WHERE code = '';
                """
            )

        if "rbac_userroleassignment" in table_names:
            assignment_columns = _table_columns(schema_editor, "rbac_userroleassignment")
            if "scope_json" in assignment_columns and "scope_data" not in assignment_columns:
                cursor.execute("ALTER TABLE rbac_userroleassignment RENAME COLUMN scope_json TO scope_data;")
            cursor.execute(
                """
                ALTER TABLE rbac_userroleassignment
                    ADD COLUMN IF NOT EXISTS assigned_by_id bigint NULL,
                    ADD COLUMN IF NOT EXISTS is_primary boolean NOT NULL DEFAULT false;
                """
            )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS rbac_roledataaccesspolicy (
                id bigserial PRIMARY KEY,
                created_at timestamptz NULL,
                updated_at timestamptz NULL,
                isactive boolean NOT NULL DEFAULT true,
                role_id bigint NOT NULL REFERENCES rbac_role(id) DEFERRABLE INITIALLY DEFERRED,
                policy_id bigint NOT NULL REFERENCES rbac_dataaccesspolicy(id) DEFERRABLE INITIALLY DEFERRED
            );
            """
        )

        if "rbac_dataaccesspolicy" in table_names and "role_id" in _table_columns(schema_editor, "rbac_dataaccesspolicy"):
            cursor.execute(
                """
                INSERT INTO rbac_roledataaccesspolicy (created_at, updated_at, isactive, role_id, policy_id)
                SELECT NOW(), NOW(), true, dap.role_id, dap.id
                FROM rbac_dataaccesspolicy dap
                WHERE dap.role_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM rbac_roledataaccesspolicy rdp
                      WHERE rdp.role_id = dap.role_id
                        AND rdp.policy_id = dap.id
                  );
                """
            )


class Migration(migrations.Migration):

    dependencies = [
        ("rbac", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(reconcile_legacy_rbac_schema, migrations.RunPython.noop),
    ]

