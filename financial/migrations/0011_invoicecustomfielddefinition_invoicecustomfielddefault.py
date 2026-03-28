# Generated manually for invoice custom fields phase-1

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("financial", "0010_remove_account_address1_remove_account_address2_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="InvoiceCustomFieldDefinition",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("isactive", models.BooleanField(default=True)),
                ("module", models.CharField(choices=[("sales_invoice", "Sales Invoice"), ("purchase_invoice", "Purchase Invoice")], max_length=30)),
                ("key", models.CharField(max_length=64)),
                ("label", models.CharField(max_length=120)),
                ("field_type", models.CharField(choices=[("text", "Text"), ("number", "Number"), ("date", "Date"), ("boolean", "Boolean"), ("select", "Select"), ("multiselect", "Multi Select")], default="text", max_length=20)),
                ("is_required", models.BooleanField(default=False)),
                ("order_no", models.PositiveIntegerField(default=0)),
                ("help_text", models.CharField(blank=True, default="", max_length=255)),
                ("options_json", models.JSONField(blank=True, default=list)),
                ("applies_to_account", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="invoice_custom_field_defs", to="financial.account")),
                ("entity", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="invoice_custom_field_defs", to="entity.entity")),
                ("subentity", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="invoice_custom_field_defs", to="entity.subentity")),
            ],
            options={
                "ordering": ("created_at",),
            },
        ),
        migrations.CreateModel(
            name="InvoiceCustomFieldDefault",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("isactive", models.BooleanField(default=True)),
                ("default_value", models.JSONField(blank=True, null=True)),
                ("definition", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="defaults", to="financial.invoicecustomfielddefinition")),
                ("party_account", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="invoice_custom_field_defaults", to="financial.account")),
            ],
            options={
                "ordering": ("created_at",),
            },
        ),
        migrations.AddConstraint(
            model_name="invoicecustomfielddefault",
            constraint=models.UniqueConstraint(fields=("definition", "party_account"), name="uq_icfdefault_definition_party"),
        ),
        migrations.AddIndex(
            model_name="invoicecustomfielddefinition",
            index=models.Index(fields=["entity", "module", "isactive"], name="ix_icfdef_ent_mod_act"),
        ),
        migrations.AddIndex(
            model_name="invoicecustomfielddefinition",
            index=models.Index(fields=["entity", "subentity", "module"], name="ix_icfdef_ent_sub_mod"),
        ),
        migrations.AddIndex(
            model_name="invoicecustomfielddefinition",
            index=models.Index(fields=["entity", "module", "key"], name="ix_icfdef_ent_mod_key"),
        ),
        migrations.AddIndex(
            model_name="invoicecustomfielddefinition",
            index=models.Index(fields=["entity", "module", "applies_to_account"], name="ix_icfdef_ent_mod_acc"),
        ),
        migrations.AddIndex(
            model_name="invoicecustomfielddefault",
            index=models.Index(fields=["definition", "party_account"], name="ix_icfdefault_def_party"),
        ),
    ]
