from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("Authentication", "0002_user_token_version_authauditlog_authsession"),
    ]

    operations = [
        migrations.AddField(
            model_name="authsession",
            name="refresh_expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="authsession",
            name="refresh_token_hash",
            field=models.CharField(blank=True, max_length=128, null=True, unique=True),
        ),
        migrations.CreateModel(
            name="AuthOTP",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("isactive", models.BooleanField(default=True)),
                ("email", models.EmailField(db_index=True, max_length=254)),
                ("purpose", models.CharField(choices=[("password_reset", "Password Reset"), ("email_verification", "Email Verification")], max_length=32)),
                ("code", models.CharField(max_length=6)),
                ("expires_at", models.DateTimeField()),
                ("consumed_at", models.DateTimeField(blank=True, null=True)),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="auth_otps", to="Authentication.user")),
            ],
            options={"ordering": ("-created_at",)},
        ),
    ]
