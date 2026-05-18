from django.db import migrations, models
from django.utils import timezone


def backfill_entityapprovalpolicy_updated_at(apps, schema_editor):
    EntityApprovalPolicy = apps.get_model("entity", "EntityApprovalPolicy")
    now = timezone.now()

    for row in EntityApprovalPolicy.objects.filter(updated_at__isnull=True).only("id", "created_at"):
        row.updated_at = row.created_at or now
        row.save(update_fields=["updated_at"])


class Migration(migrations.Migration):

    dependencies = [
        ("entity", "0027_entityapprovalpolicy"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="entityapprovalpolicy",
            new_name="entity_enti_entity__1a72b4_idx",
            old_name="entity_entit_entity__ecbab2_idx",
        ),
        migrations.RenameIndex(
            model_name="entityapprovalpolicy",
            new_name="entity_enti_entity__c7b0d6_idx",
            old_name="entity_entit_entity__cf8875_idx",
        ),
        migrations.RenameIndex(
            model_name="entityapprovalpolicy",
            new_name="entity_enti_entity__ea79d1_idx",
            old_name="entity_entit_entity__57d9e5_idx",
        ),
        migrations.RenameIndex(
            model_name="entityapprovalpolicy",
            new_name="entity_enti_entity__f5cc82_idx",
            old_name="entity_entit_entity__4c1d53_idx",
        ),
        migrations.RenameIndex(
            model_name="entityemploymentprofile",
            new_name="entity_enti_entity__a232e3_idx",
            old_name="entity_emplo_entity__62a40f_idx",
        ),
        migrations.RenameIndex(
            model_name="entityemploymentprofile",
            new_name="entity_enti_entity__4c0afa_idx",
            old_name="entity_emplo_entity__1edabc_idx",
        ),
        migrations.RenameIndex(
            model_name="entityemploymentprofile",
            new_name="entity_enti_entity__98dfeb_idx",
            old_name="entity_emplo_entity__5cf8e9_idx",
        ),
        migrations.RenameIndex(
            model_name="entityorgunit",
            new_name="entity_enti_entity__ab990a_idx",
            old_name="entity_entit_entity__eb654b_idx",
        ),
        migrations.RenameIndex(
            model_name="entityorgunit",
            new_name="entity_enti_entity__a8bb91_idx",
            old_name="entity_entit_entity__3624b9_idx",
        ),
        migrations.RenameIndex(
            model_name="entityorgunit",
            new_name="entity_enti_entity__129bcc_idx",
            old_name="entity_entit_entity__ce1b9d_idx",
        ),
        migrations.RunPython(
            backfill_entityapprovalpolicy_updated_at,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="entityapprovalpolicy",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
    ]
