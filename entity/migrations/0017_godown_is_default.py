from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("entity", "0016_godown_entity_godown_subentity_alter_godown_code_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="godown",
            name="is_default",
            field=models.BooleanField(db_index=True, default=False),
        ),
    ]
