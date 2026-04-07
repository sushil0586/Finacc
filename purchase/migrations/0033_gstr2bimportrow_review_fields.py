from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("purchase", "0032_alter_purchaseattachment_file"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="gstr2bimportrow",
            name="match_review_comment",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="gstr2bimportrow",
            name="match_reviewed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="gstr2bimportrow",
            name="match_reviewed_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL),
        ),
    ]
