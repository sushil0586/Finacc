from django.db import migrations


def seed_manufacturing_additional_cost_expense_static_account(apps, schema_editor):
    StaticAccount = apps.get_model("posting", "StaticAccount")
    StaticAccount.objects.update_or_create(
        code="MANUFACTURING_ADDITIONAL_COST_EXPENSE",
        defaults={
            "name": "Manufacturing Additional Cost Expense",
            "group": "MANUFACTURING",
            "description": "Expense ledger for manufacturing additional costs that should not be capitalized into finished goods.",
            "is_active": True,
            "is_required": False,
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ("posting", "0019_seed_manufacturing_variance_static_accounts"),
    ]

    operations = [
        migrations.RunPython(seed_manufacturing_additional_cost_expense_static_account, migrations.RunPython.noop),
    ]
