from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("entity", "0035_approvalrequest_ix_appr_req_entity_flow_and_more"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="subentitygstregistration",
            name="uq_subentity_gst_registration_active_gstin",
        ),
    ]
