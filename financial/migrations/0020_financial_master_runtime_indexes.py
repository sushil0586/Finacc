from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("financial", "0019_financial_lookup_indexes"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="financialmasterrule",
            index=models.Index(fields=["entity", "isactive", "priority"], name="ix_finrule_ent_actpri"),
        ),
        migrations.AddIndex(
            model_name="financialmasterrule",
            index=models.Index(fields=["template_code", "isactive", "priority"], name="ix_finrule_tpl_actpri"),
        ),
        migrations.AddIndex(
            model_name="financialcodeseries",
            index=models.Index(fields=["entity", "isactive", "priority"], name="ix_fincode_ent_actpri"),
        ),
        migrations.AddIndex(
            model_name="financialcodeseries",
            index=models.Index(fields=["template_code", "isactive", "priority"], name="ix_fincode_tpl_actpri"),
        ),
        migrations.AddIndex(
            model_name="account",
            index=models.Index(fields=["entity", "accountname", "id"], name="ix_account_ent_name_id"),
        ),
        migrations.AddIndex(
            model_name="accountaddress",
            index=models.Index(fields=["account", "isprimary", "isactive"], name="ix_accaddr_acc_prm_act"),
        ),
    ]
