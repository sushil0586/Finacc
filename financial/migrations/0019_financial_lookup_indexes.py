from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("financial", "0018_alter_financialcodeseries_options_and_more"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="ledger",
            index=models.Index(
                fields=["entity", "isactive", "name"],
                name="ix_ledger_ent_act_name",
            ),
        ),
        migrations.AddIndex(
            model_name="ledger",
            index=models.Index(
                fields=["entity", "accounthead"],
                name="ix_ledger_ent_head",
            ),
        ),
        migrations.AddIndex(
            model_name="account",
            index=models.Index(
                fields=["entity", "isactive", "accountname"],
                name="ix_account_ent_act_name",
            ),
        ),
        migrations.AddIndex(
            model_name="account",
            index=models.Index(
                fields=["entity", "isactive", "ledger"],
                name="ix_account_ent_act_ledg",
            ),
        ),
        migrations.AddIndex(
            model_name="accountcommercialprofile",
            index=models.Index(
                fields=["entity", "partytype", "agent"],
                name="ix_acccom_ent_partyagt",
            ),
        ),
    ]
