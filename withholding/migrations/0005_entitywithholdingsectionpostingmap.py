from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("entity", "0013_entitygstregistration_state_scope_and_primary_fix"),
        ("financial", "0014_financialsettings_reporting_policy"),
        ("withholding", "0004_withholdingsection_payable_account_ledger"),
    ]

    operations = [
        migrations.CreateModel(
            name="EntityWithholdingSectionPostingMap",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("effective_from", models.DateField(db_index=True, default=django.utils.timezone.localdate)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("entity", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="entity.entity")),
                ("payable_account", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="financial.account")),
                ("payable_ledger", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to="financial.ledger")),
                ("section", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="withholding.withholdingsection")),
                ("subentity", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to="entity.subentity")),
            ],
        ),
        migrations.AddConstraint(
            model_name="entitywithholdingsectionpostingmap",
            constraint=models.UniqueConstraint(fields=("entity", "subentity", "section", "effective_from"), name="uq_wh_sec_map_entity_sub_sec_eff"),
        ),
        migrations.AddIndex(
            model_name="entitywithholdingsectionpostingmap",
            index=models.Index(fields=["entity", "section", "subentity", "is_active"], name="ix_wh_sec_map_lookup"),
        ),
        migrations.AddIndex(
            model_name="entitywithholdingsectionpostingmap",
            index=models.Index(fields=["entity", "effective_from"], name="ix_wh_sec_map_eff"),
        ),
    ]
