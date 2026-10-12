# Generated for Phase 2C final index-removal certification on 2026-10-12

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("posting", "0036_remove_plain_journalline_voucher_number_index"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="journalline",
            name="ix_jl_locator",
        ),
    ]
