from django.db import migrations


def seed_manufacturing_variance_static_accounts(apps, schema_editor):
    StaticAccount = apps.get_model("posting", "StaticAccount")

    rows = [
        (
            "MANUFACTURING_MATERIAL_VARIANCE",
            "Manufacturing Material Variance",
            "MANUFACTURING",
            "Variance ledger for material over/under-consumption against standard manufacturing cost.",
        ),
        (
            "MANUFACTURING_YIELD_VARIANCE",
            "Manufacturing Yield Variance",
            "MANUFACTURING",
            "Variance ledger for manufacturing output/yield differences against standard cost expectation.",
        ),
    ]

    for code, name, group, description in rows:
        StaticAccount.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "group": group,
                "description": description,
                "is_active": True,
                "is_required": False,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("posting", "0018_add_manufacturing_static_account_group"),
    ]

    operations = [
        migrations.RunPython(seed_manufacturing_variance_static_accounts, migrations.RunPython.noop),
    ]
