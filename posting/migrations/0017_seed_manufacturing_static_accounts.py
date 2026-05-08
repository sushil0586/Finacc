from django.db import migrations


def seed_manufacturing_static_accounts(apps, schema_editor):
    StaticAccount = apps.get_model("posting", "StaticAccount")

    rows = [
        (
            "MANUFACTURING_WIP",
            "Manufacturing WIP",
            "OTHER",
            "Work-in-progress clearing ledger for manufacturing posting.",
        ),
        (
            "MANUFACTURING_CONSUMPTION",
            "Manufacturing Consumption",
            "OTHER",
            "Consumption/issue ledger for manufacturing material usage.",
        ),
        (
            "MANUFACTURING_OVERHEAD_ABSORPTION",
            "Manufacturing Overhead Absorption",
            "OTHER",
            "Offset ledger for additional production cost absorption.",
        ),
        (
            "MANUFACTURING_FINISHED_GOODS",
            "Manufacturing Finished Goods",
            "OTHER",
            "Finished goods / byproduct inventory capitalization ledger for manufacturing posting.",
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
        ("posting", "0016_entitystaticaccountmap_perf_indexes"),
    ]

    operations = [
        migrations.RunPython(seed_manufacturing_static_accounts, migrations.RunPython.noop),
    ]
