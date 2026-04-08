from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("subscriptions", "0003_alter_customeraccount_created_at_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="customeraccount",
            name="billing_contact_name",
            field=models.CharField(blank=True, max_length=150, null=True),
        ),
        migrations.AddField(
            model_name="customeraccount",
            name="billing_contact_phone",
            field=models.CharField(blank=True, max_length=30, null=True),
        ),
        migrations.AddField(
            model_name="customeraccount",
            name="legal_name",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="customeraccount",
            name="primary_contact_email",
            field=models.EmailField(blank=True, max_length=254, null=True),
        ),
        migrations.AddField(
            model_name="customeraccount",
            name="primary_contact_name",
            field=models.CharField(blank=True, max_length=150, null=True),
        ),
        migrations.AddField(
            model_name="customeraccount",
            name="primary_contact_phone",
            field=models.CharField(blank=True, max_length=30, null=True),
        ),
        migrations.AddField(
            model_name="customeraccount",
            name="status_notes",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="customeraccount",
            name="status_reason",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="customeraccount",
            name="support_email",
            field=models.EmailField(blank=True, max_length=254, null=True),
        ),
        migrations.AddField(
            model_name="customeraccount",
            name="trade_name",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
