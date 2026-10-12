from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("posting", "0029_seed_profit_loss_appropriation_static_account"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="journalline",
            name="ix_jl_batch",
        ),
    ]
