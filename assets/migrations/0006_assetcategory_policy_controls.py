import json

from django.db import migrations, models

import assets.models


TRACEABILITY_DEFAULT = {
    "serial_number_rule": "inherit",
    "manufacturer_rule": "inherit",
    "model_number_rule": "inherit",
    "vendor_account_rule": "inherit",
}

ACCOUNTING_DEFAULT = {
    "asset_ledger_rule": "inherit",
    "depreciation_ledgers_rule": "inherit",
    "impairment_ledgers_rule": "inherit",
    "disposal_ledgers_rule": "inherit",
    "cwip_ledger_rule": "inherit",
}


def _table_columns(schema_editor, table_name):
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        description = connection.introspection.get_table_description(cursor, table_name)
    return {column.name for column in description}


def add_policy_control_columns(apps, schema_editor):
    table_name = "assets_assetcategory"
    columns = _table_columns(schema_editor, table_name)
    vendor = schema_editor.connection.vendor
    traceability_default_sql = json.dumps(TRACEABILITY_DEFAULT).replace("'", "''")
    accounting_default_sql = json.dumps(ACCOUNTING_DEFAULT).replace("'", "''")

    if vendor == "postgresql":
        with schema_editor.connection.cursor() as cursor:
            if "traceability_controls" not in columns:
                cursor.execute(
                    """
                    ALTER TABLE assets_assetcategory
                    ADD COLUMN traceability_controls jsonb
                    DEFAULT %s::jsonb;
                    """,
                    [json.dumps(TRACEABILITY_DEFAULT)],
                )
            cursor.execute(
                """
                UPDATE assets_assetcategory
                SET traceability_controls = %s::jsonb
                WHERE traceability_controls IS NULL;
                """,
                [json.dumps(TRACEABILITY_DEFAULT)],
            )
            cursor.execute(
                """
                ALTER TABLE assets_assetcategory
                ALTER COLUMN traceability_controls SET DEFAULT %s::jsonb;
                """,
                [json.dumps(TRACEABILITY_DEFAULT)],
            )
            cursor.execute(
                """
                ALTER TABLE assets_assetcategory
                ALTER COLUMN traceability_controls SET NOT NULL;
                """
            )

            if "accounting_controls" not in columns:
                cursor.execute(
                    """
                    ALTER TABLE assets_assetcategory
                    ADD COLUMN accounting_controls jsonb
                    DEFAULT %s::jsonb;
                    """,
                    [json.dumps(ACCOUNTING_DEFAULT)],
                )
            cursor.execute(
                """
                UPDATE assets_assetcategory
                SET accounting_controls = %s::jsonb
                WHERE accounting_controls IS NULL;
                """,
                [json.dumps(ACCOUNTING_DEFAULT)],
            )
            cursor.execute(
                """
                ALTER TABLE assets_assetcategory
                ALTER COLUMN accounting_controls SET DEFAULT %s::jsonb;
                """,
                [json.dumps(ACCOUNTING_DEFAULT)],
            )
            cursor.execute(
                """
                ALTER TABLE assets_assetcategory
                ALTER COLUMN accounting_controls SET NOT NULL;
                """
            )
        return

    if vendor == "sqlite":
        with schema_editor.connection.cursor() as cursor:
            if "traceability_controls" not in columns:
                cursor.execute(
                    """
                    ALTER TABLE assets_assetcategory
                    ADD COLUMN traceability_controls text NOT NULL DEFAULT '%s';
                    """
                    % traceability_default_sql
                )
            else:
                cursor.execute(
                    """
                    UPDATE assets_assetcategory
                    SET traceability_controls = '%s'
                    WHERE traceability_controls IS NULL OR traceability_controls = '';
                    """
                    % traceability_default_sql
                )

            if "accounting_controls" not in columns:
                cursor.execute(
                    """
                    ALTER TABLE assets_assetcategory
                    ADD COLUMN accounting_controls text NOT NULL DEFAULT '%s';
                    """
                    % accounting_default_sql
                )
            else:
                cursor.execute(
                    """
                    UPDATE assets_assetcategory
                    SET accounting_controls = '%s'
                    WHERE accounting_controls IS NULL OR accounting_controls = '';
                    """
                    % accounting_default_sql
                )
        return


def drop_policy_control_columns(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            ALTER TABLE assets_assetcategory DROP COLUMN IF EXISTS traceability_controls;
            """
        )
        cursor.execute(
            """
            ALTER TABLE assets_assetcategory DROP COLUMN IF EXISTS accounting_controls;
            """
        )


class Migration(migrations.Migration):
    atomic = False

    replaces = [
        ("assets", "0006_assetcategory_traceability_controls"),
        ("assets", "0007_assetcategory_accounting_controls"),
    ]

    dependencies = [
        ("assets", "0005_assetbulkjob_committed_fields"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(add_policy_control_columns, drop_policy_control_columns),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="assetcategory",
                    name="traceability_controls",
                    field=models.JSONField(blank=True, default=assets.models.default_asset_category_traceability_controls),
                ),
                migrations.AddField(
                    model_name="assetcategory",
                    name="accounting_controls",
                    field=models.JSONField(blank=True, default=assets.models.default_asset_category_accounting_controls),
                ),
            ],
        ),
    ]
        
