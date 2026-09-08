from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("platform_ops", "0016_alter_platformauditevent_actor")]
    operations = [
        migrations.AlterField(
            model_name="platformoperationapproval",
            name="operation",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="approvals",
                to="platform_ops.platformoperationrequest",
            ),
        ),
        migrations.AddConstraint(
            model_name="platformoperationapproval",
            constraint=models.UniqueConstraint(
                fields=("operation", "decided_by"),
                name="uq_platform_approval_approver",
            ),
        ),
    ]
