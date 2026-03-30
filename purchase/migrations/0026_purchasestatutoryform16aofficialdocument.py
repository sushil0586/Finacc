from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("purchase", "0025_purchaseinvoiceline_purchase_account"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PurchaseStatutoryForm16AOfficialDocument",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("issue_no", models.PositiveIntegerField(db_index=True)),
                ("source", models.CharField(default="TRACES", max_length=20)),
                ("certificate_no", models.CharField(blank=True, max_length=100, null=True)),
                ("remarks", models.CharField(blank=True, max_length=255, null=True)),
                ("document", models.FileField(upload_to="purchase/statutory/form16a/")),
                ("uploaded_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                (
                    "filing",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="form16a_official_documents",
                        to="purchase.purchasestatutoryreturn",
                    ),
                ),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="purchase_statutory_form16a_uploaded",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="purchasestatutoryform16aofficialdocument",
            index=models.Index(fields=["filing", "issue_no"], name="ix_pur_form16a_filing_issue"),
        ),
        migrations.AddConstraint(
            model_name="purchasestatutoryform16aofficialdocument",
            constraint=models.UniqueConstraint(fields=("filing", "issue_no"), name="uq_pur_form16a_official_filing_issue"),
        ),
    ]
