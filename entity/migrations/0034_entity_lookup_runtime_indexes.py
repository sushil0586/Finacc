from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("entity", "0033_merge_20260602_0001"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="entity",
            index=models.Index(fields=["isactive", "entityname"], name="ix_entity_act_name"),
        ),
        migrations.AddIndex(
            model_name="entity",
            index=models.Index(fields=["createdby", "isactive"], name="ix_entity_creator_act"),
        ),
        migrations.AddIndex(
            model_name="subentity",
            index=models.Index(
                fields=["entity", "isactive", "is_head_office", "subentityname"],
                name="ix_subent_act_head_nm",
            ),
        ),
        migrations.AddIndex(
            model_name="entityfinancialyear",
            index=models.Index(fields=["entity", "isactive", "finstartyear"], name="ix_entfy_act_start"),
        ),
        migrations.AddIndex(
            model_name="entityfinancialyear",
            index=models.Index(
                fields=["entity", "isactive", "is_year_closed", "finstartyear"],
                name="ix_entfy_act_closed",
            ),
        ),
    ]
