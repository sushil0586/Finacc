from django.db import migrations, models

import assets.models


class Migration(migrations.Migration):

    dependencies = [
        ("assets", "0005_assetbulkjob_committed_fields"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="""
                    ALTER TABLE assets_assetcategory
                    ADD COLUMN IF NOT EXISTS traceability_controls jsonb;
                    ALTER TABLE assets_assetcategory
                    ALTER COLUMN traceability_controls SET DEFAULT '{"serial_number_rule":"inherit","manufacturer_rule":"inherit","model_number_rule":"inherit","vendor_account_rule":"inherit"}'::jsonb;
                    UPDATE assets_assetcategory
                    SET traceability_controls = '{"serial_number_rule":"inherit","manufacturer_rule":"inherit","model_number_rule":"inherit","vendor_account_rule":"inherit"}'::jsonb
                    WHERE traceability_controls IS NULL;
                    ALTER TABLE assets_assetcategory
                    ALTER COLUMN traceability_controls SET NOT NULL;

                    ALTER TABLE assets_assetcategory
                    ADD COLUMN IF NOT EXISTS accounting_controls jsonb;
                    ALTER TABLE assets_assetcategory
                    ALTER COLUMN accounting_controls SET DEFAULT '{"asset_ledger_rule":"inherit","depreciation_ledgers_rule":"inherit","impairment_ledgers_rule":"inherit","disposal_ledgers_rule":"inherit","cwip_ledger_rule":"inherit"}'::jsonb;
                    UPDATE assets_assetcategory
                    SET accounting_controls = '{"asset_ledger_rule":"inherit","depreciation_ledgers_rule":"inherit","impairment_ledgers_rule":"inherit","disposal_ledgers_rule":"inherit","cwip_ledger_rule":"inherit"}'::jsonb
                    WHERE accounting_controls IS NULL;
                    ALTER TABLE assets_assetcategory
                    ALTER COLUMN accounting_controls SET NOT NULL;
                    """,
                    reverse_sql="""
                    ALTER TABLE assets_assetcategory DROP COLUMN IF EXISTS accounting_controls;
                    ALTER TABLE assets_assetcategory DROP COLUMN IF EXISTS traceability_controls;
                    """,
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="assetcategory",
                    name="traceability_controls",
                    field=models.JSONField(blank=True, default=assets.models.default_asset_traceability_controls),
                ),
                migrations.AddField(
                    model_name="assetcategory",
                    name="accounting_controls",
                    field=models.JSONField(blank=True, default=assets.models.default_asset_accounting_controls),
                ),
            ],
        ),
    ]
