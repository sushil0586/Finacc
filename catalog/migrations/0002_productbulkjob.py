from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("entity", "0013_entitygstregistration_state_scope_and_primary_fix"),
        ("Authentication", "0004_remove_submenu_mainmenu_remove_authotp_code_and_more"),
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductBulkJob",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("createdon", models.DateTimeField(auto_now_add=True)),
                ("modifiedon", models.DateTimeField(auto_now=True)),
                ("isactive", models.BooleanField(default=True)),
                ("job_type", models.CharField(choices=[("validate", "Validate"), ("import", "Import"), ("export", "Export")], db_index=True, default="validate", max_length=20)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("completed", "Completed"), ("failed", "Failed")], db_index=True, default="pending", max_length=20)),
                ("file_format", models.CharField(choices=[("xlsx", "XLSX"), ("csv", "CSV")], default="xlsx", max_length=10)),
                ("upsert_mode", models.CharField(choices=[("create_only", "Create only"), ("update_only", "Update only"), ("upsert", "Upsert")], default="upsert", max_length=20)),
                ("duplicate_strategy", models.CharField(choices=[("fail", "Fail"), ("skip", "Skip"), ("overwrite", "Overwrite")], default="fail", max_length=20)),
                ("validation_token", models.CharField(blank=True, db_index=True, max_length=64, null=True)),
                ("input_filename", models.CharField(blank=True, max_length=255, null=True)),
                ("summary", models.JSONField(blank=True, default=dict)),
                ("errors", models.JSONField(blank=True, default=list)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="Authentication.user")),
                ("entity", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="catalog_bulk_jobs", to="entity.entity")),
            ],
        ),
        migrations.AddIndex(
            model_name="productbulkjob",
            index=models.Index(fields=["entity", "job_type", "status"], name="catalog_pro_entity__73af6c_idx"),
        ),
        migrations.AddIndex(
            model_name="productbulkjob",
            index=models.Index(fields=["entity", "validation_token"], name="catalog_pro_entity__db9f7a_idx"),
        ),
    ]
