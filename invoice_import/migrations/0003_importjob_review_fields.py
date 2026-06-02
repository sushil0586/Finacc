from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("invoice_import", "0002_importjob_profile_snapshot_importprofile_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="importjob",
            name="review_note",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="importjob",
            name="review_required",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="importjob",
            name="reviewed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="importjob",
            name="reviewed_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL),
        ),
    ]
