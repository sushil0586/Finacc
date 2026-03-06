from decimal import Decimal
import django.core.validators
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("sales", "0017_salesinvoiceheader_is_posting_reversed_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="salesinvoiceheader",
            name="compliance_override_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="salesinvoiceheader",
            name="compliance_override_reason",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="salesinvoiceheader",
            name="einvoice_applicable_manual",
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="salesinvoiceheader",
            name="eway_applicable_manual",
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="salesinvoiceheader",
            name="tcs_is_reversal",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="salesinvoiceheader",
            name="compliance_override_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="sales_compliance_overridden",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="salesinvoiceheader",
            name="customer_gstin",
            field=models.CharField(
                blank=True,
                default="",
                max_length=15,
                validators=[
                    django.core.validators.RegexValidator(
                        message="GSTIN must be 15 uppercase alphanumeric characters.",
                        regex="^[0-9A-Z]{15}$",
                    )
                ],
            ),
        ),
        migrations.AlterField(
            model_name="salesinvoiceheader",
            name="seller_gstin",
            field=models.CharField(
                blank=True,
                default="",
                max_length=15,
                validators=[
                    django.core.validators.RegexValidator(
                        message="GSTIN must be 15 uppercase alphanumeric characters.",
                        regex="^[0-9A-Z]{15}$",
                    )
                ],
            ),
        ),
        migrations.AddField(
            model_name="salessettings",
            name="compliance_applicability_mode",
            field=models.CharField(
                choices=[
                    ("AUTO_ONLY", "Auto Derive Only"),
                    ("AUTO_WITH_OVERRIDE", "Auto + Manual Override (Audited)"),
                ],
                default="AUTO_ONLY",
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="salessettings",
            name="einvoice_entity_applicable",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="salessettings",
            name="eway_value_threshold",
            field=models.DecimalField(decimal_places=2, default=Decimal("50000.00"), max_digits=14),
        ),
        migrations.AddField(
            model_name="salessettings",
            name="tcs_credit_note_policy",
            field=models.CharField(
                choices=[
                    ("DISALLOW", "Disallow TCS on Credit Note"),
                    ("ALLOW", "Allow TCS on Credit Note"),
                    ("REVERSE", "Reverse TCS on Credit Note"),
                ],
                default="REVERSE",
                max_length=12,
            ),
        ),
        migrations.AddConstraint(
            model_name="salesinvoiceline",
            constraint=models.CheckConstraint(
                check=(
                    Q(qty__gte=0)
                    & Q(free_qty__gte=0)
                    & Q(rate__gte=0)
                    & Q(discount_percent__gte=0)
                    & Q(discount_percent__lte=100)
                    & Q(discount_amount__gte=0)
                    & Q(gst_rate__gte=0)
                    & Q(gst_rate__lte=100)
                    & Q(cess_percent__gte=0)
                    & Q(cess_percent__lte=100)
                    & Q(taxable_value__gte=0)
                    & Q(cgst_amount__gte=0)
                    & Q(sgst_amount__gte=0)
                    & Q(igst_amount__gte=0)
                    & Q(cess_amount__gte=0)
                    & Q(line_total__gte=0)
                ),
                name="ck_sales_line_nonneg_and_rate",
            ),
        ),
        migrations.AddConstraint(
            model_name="salesinvoiceline",
            constraint=models.CheckConstraint(
                check=(Q(gst_rate=0) | Q(taxable_value=0) | ~Q(hsn_sac_code="")),
                name="ck_sales_line_hsn_required_when_gst",
            ),
        ),
        migrations.DeleteModel(name="SalesEWayEvent"),
        migrations.DeleteModel(name="SalesEWayBillDetails"),
        migrations.DeleteModel(name="SalesEInvoiceDetails"),
    ]
