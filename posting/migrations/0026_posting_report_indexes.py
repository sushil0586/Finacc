from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("posting", "0025_seed_static_account_master"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="entry",
            index=models.Index(
                fields=["entity", "entityfin", "subentity", "posting_date"],
                name="ix_entry_scope_postdt",
            ),
        ),
        migrations.AddIndex(
            model_name="entry",
            index=models.Index(
                fields=["entity", "status", "posting_date"],
                name="ix_entry_entity_statusdt",
            ),
        ),
        migrations.AddIndex(
            model_name="journalline",
            index=models.Index(
                fields=["entity", "entityfin", "subentity", "posting_date"],
                name="ix_jl_scope_postdt",
            ),
        ),
        migrations.AddIndex(
            model_name="journalline",
            index=models.Index(
                fields=["entity", "ledger", "posting_date"],
                name="ix_jl_ent_ledger_dt",
            ),
        ),
        migrations.AddIndex(
            model_name="journalline",
            index=models.Index(
                fields=["entity", "account", "posting_date"],
                name="ix_jl_ent_acct_dt",
            ),
        ),
        migrations.AddIndex(
            model_name="journalline",
            index=models.Index(
                fields=["entity", "accounthead", "posting_date"],
                name="ix_jl_ent_head_dt",
            ),
        ),
        migrations.AddIndex(
            model_name="inventorymove",
            index=models.Index(
                fields=["entity", "entityfin", "subentity", "posting_date"],
                name="ix_im_scope_postdt",
            ),
        ),
        migrations.AddIndex(
            model_name="inventorymove",
            index=models.Index(
                fields=["entity", "location", "product", "posting_date"],
                name="ix_im_ent_loc_prod_dt",
            ),
        ),
    ]
