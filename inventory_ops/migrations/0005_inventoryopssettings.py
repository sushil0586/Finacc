from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("entity", "0020_remove_entity_unittype"),
        ("inventory_ops", "0004_inventory_line_batch_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="InventoryOpsSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("isactive", models.BooleanField(default=True)),
                ("default_doc_code_transfer", models.CharField(default="ITF", max_length=10)),
                ("default_doc_code_adjustment", models.CharField(default="IAD", max_length=10)),
                ("default_workflow_action", models.CharField(choices=[("draft", "Save as Draft"), ("confirm", "Auto Confirm on Save"), ("post", "Auto Post on Save")], db_index=True, default="draft", max_length=10)),
                ("policy_controls", models.JSONField(blank=True, default=dict)),
                ("entity", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="inventory_ops_settings", to="entity.entity")),
                ("subentity", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="inventory_ops_settings", to="entity.subentity")),
            ],
            options={
                "ordering": ("created_at",),
            },
        ),
        migrations.AddIndex(
            model_name="inventoryopssettings",
            index=models.Index(fields=["entity"], name="ix_inv_ops_settings_entity"),
        ),
        migrations.AddConstraint(
            model_name="inventoryopssettings",
            constraint=models.UniqueConstraint(fields=("entity", "subentity"), name="uq_inventory_ops_settings_entity_subentity"),
        ),
    ]
