from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0004_product_expiry_warning_days_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="BarcodeLabelTemplate",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("createdon", models.DateTimeField(auto_now_add=True)),
                ("modifiedon", models.DateTimeField(auto_now=True)),
                ("isactive", models.BooleanField(default=True)),
                ("name", models.CharField(max_length=100)),
                (
                    "output_mode",
                    models.CharField(
                        choices=[("pdf", "PDF"), ("browser", "Browser")],
                        default="browser",
                        max_length=20,
                    ),
                ),
                ("pdf_layout", models.PositiveSmallIntegerField(blank=True, null=True)),
                (
                    "label_width_mm",
                    models.DecimalField(decimal_places=2, default=Decimal("25.00"), max_digits=6),
                ),
                (
                    "label_height_mm",
                    models.DecimalField(decimal_places=2, default=Decimal("15.00"), max_digits=6),
                ),
                (
                    "padding_mm",
                    models.DecimalField(decimal_places=2, default=Decimal("1.20"), max_digits=6),
                ),
                ("show_border", models.BooleanField(default=True)),
                ("special_text", models.TextField(blank=True)),
                ("print_fields", models.JSONField(blank=True, default=list)),
                ("attribute_ids", models.JSONField(blank=True, default=list)),
                ("copies", models.PositiveIntegerField(default=1)),
                ("isdefault", models.BooleanField(default=False)),
                (
                    "entity",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="catalog_%(class)s_set",
                        to="entity.entity",
                    ),
                ),
            ],
            options={
                "ordering": ["-isdefault", "name"],
            },
        ),
        migrations.AddConstraint(
            model_name="barcodelabeltemplate",
            constraint=models.UniqueConstraint(
                fields=("entity", "name"),
                name="uq_barcode_label_template_entity_name",
            ),
        ),
        migrations.AddConstraint(
            model_name="barcodelabeltemplate",
            constraint=models.UniqueConstraint(
                condition=models.Q(("isdefault", True)),
                fields=("entity",),
                name="uq_barcode_label_template_one_default",
            ),
        ),
    ]
