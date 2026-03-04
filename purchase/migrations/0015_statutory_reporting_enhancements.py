from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("purchase", "0014_purchase_statutory_registers"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchasestatutorychallan",
            name="ack_document",
            field=models.FileField(blank=True, null=True, upload_to="purchase/statutory/challan/"),
        ),
        migrations.AddField(
            model_name="purchasestatutorychallan",
            name="cin_no",
            field=models.CharField(blank=True, db_index=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="purchasestatutorychallan",
            name="interest_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="purchasestatutorychallan",
            name="late_fee_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="purchasestatutorychallan",
            name="minor_head_code",
            field=models.CharField(blank=True, db_index=True, max_length=20, null=True),
        ),
        migrations.AddField(
            model_name="purchasestatutorychallan",
            name="payment_payload_json",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="purchasestatutorychallan",
            name="penalty_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddConstraint(
            model_name="purchasestatutorychallan",
            constraint=models.CheckConstraint(
                check=models.Q(interest_amount__gte=0),
                name="ck_pur_stat_challan_interest_nonneg",
            ),
        ),
        migrations.AddConstraint(
            model_name="purchasestatutorychallan",
            constraint=models.CheckConstraint(
                check=models.Q(late_fee_amount__gte=0),
                name="ck_pur_stat_challan_latefee_nonneg",
            ),
        ),
        migrations.AddConstraint(
            model_name="purchasestatutorychallan",
            constraint=models.CheckConstraint(
                check=models.Q(penalty_amount__gte=0),
                name="ck_pur_stat_challan_penalty_nonneg",
            ),
        ),
        migrations.AddField(
            model_name="purchasestatutoryreturn",
            name="ack_document",
            field=models.FileField(blank=True, null=True, upload_to="purchase/statutory/return/"),
        ),
        migrations.AddField(
            model_name="purchasestatutoryreturn",
            name="arn_no",
            field=models.CharField(blank=True, db_index=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="purchasestatutoryreturn",
            name="filed_payload_json",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="purchasestatutoryreturn",
            name="interest_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="purchasestatutoryreturn",
            name="late_fee_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="purchasestatutoryreturn",
            name="original_return",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="revisions", to="purchase.purchasestatutoryreturn"),
        ),
        migrations.AddField(
            model_name="purchasestatutoryreturn",
            name="penalty_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="purchasestatutoryreturn",
            name="revision_no",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddConstraint(
            model_name="purchasestatutoryreturn",
            constraint=models.CheckConstraint(
                check=models.Q(interest_amount__gte=0),
                name="ck_pur_stat_return_interest_nonneg",
            ),
        ),
        migrations.AddConstraint(
            model_name="purchasestatutoryreturn",
            constraint=models.CheckConstraint(
                check=models.Q(late_fee_amount__gte=0),
                name="ck_pur_stat_return_latefee_nonneg",
            ),
        ),
        migrations.AddConstraint(
            model_name="purchasestatutoryreturn",
            constraint=models.CheckConstraint(
                check=models.Q(penalty_amount__gte=0),
                name="ck_pur_stat_return_penalty_nonneg",
            ),
        ),
        migrations.AddField(
            model_name="purchasestatutoryreturnline",
            name="cin_snapshot",
            field=models.CharField(blank=True, db_index=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="purchasestatutoryreturnline",
            name="deductee_gstin_snapshot",
            field=models.CharField(blank=True, db_index=True, max_length=15, null=True),
        ),
        migrations.AddField(
            model_name="purchasestatutoryreturnline",
            name="deductee_pan_snapshot",
            field=models.CharField(blank=True, db_index=True, max_length=16, null=True),
        ),
        migrations.AddField(
            model_name="purchasestatutoryreturnline",
            name="metadata_json",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="purchasestatutoryreturnline",
            name="section_snapshot_code",
            field=models.CharField(blank=True, db_index=True, max_length=16, null=True),
        ),
        migrations.AddField(
            model_name="purchasestatutoryreturnline",
            name="section_snapshot_desc",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
