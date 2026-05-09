from django.db import migrations, models
from django.db.models import Q


def normalize_single_active_entity_gst(apps, schema_editor):
    EntityGstRegistration = apps.get_model("entity", "EntityGstRegistration")

    entity_ids = (
        EntityGstRegistration.objects.filter(isactive=True)
        .values_list("entity_id", flat=True)
        .distinct()
    )
    for entity_id in entity_ids:
        rows = list(
            EntityGstRegistration.objects.filter(entity_id=entity_id, isactive=True).order_by("-is_primary", "-updated_at", "-id")
        )
        if len(rows) <= 1:
            if rows and not rows[0].is_primary:
                rows[0].is_primary = True
                rows[0].save(update_fields=["is_primary", "updated_at"])
            continue

        keeper = rows[0]
        if not keeper.is_primary:
            keeper.is_primary = True
            keeper.save(update_fields=["is_primary", "updated_at"])

        for row in rows[1:]:
            updates = []
            if row.is_primary:
                row.is_primary = False
                updates.append("is_primary")
            if row.isactive:
                row.isactive = False
                updates.append("isactive")
            if updates:
                updates.append("updated_at")
                row.save(update_fields=updates)


class Migration(migrations.Migration):

    dependencies = [
        ("entity", "0022_remove_entitygstregistration_credential_ref"),
    ]

    operations = [
        migrations.RunPython(normalize_single_active_entity_gst, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="entitygstregistration",
            name="uq_entity_gst_registration_entity_state_active",
        ),
        migrations.AddConstraint(
            model_name="entitygstregistration",
            constraint=models.UniqueConstraint(
                fields=("entity",),
                condition=Q(isactive=True),
                name="uq_entity_gst_registration_entity_active",
            ),
        ),
    ]
