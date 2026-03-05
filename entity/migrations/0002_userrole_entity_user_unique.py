from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("entity", "0001_initial"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="userrole",
            constraint=models.UniqueConstraint(fields=("entity", "user"), name="uq_entity_user_role_once"),
        ),
    ]

