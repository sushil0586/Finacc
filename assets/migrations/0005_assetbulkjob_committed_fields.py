from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("assets", "0004_assetbulkjob"),
    ]

    operations = [
        migrations.AddField(
            model_name="assetbulkjob",
            name="committed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="assetbulkjob",
            name="committed_import_job",
            field=models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name="validated_jobs", to="assets.assetbulkjob"),
        ),
    ]
