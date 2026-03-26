from django.db import migrations, models
from django.db.models import Q


def backfill_primary_for_active_gst(apps, schema_editor):
    EntityGstRegistration = apps.get_model("entity", "EntityGstRegistration")

    # For entities that have active GST rows but no active primary row,
    # promote the latest active row as primary.
    entity_ids = (
        EntityGstRegistration.objects.filter(isactive=True)
        .values_list("entity_id", flat=True)
        .distinct()
    )
    for entity_id in entity_ids:
        has_primary = EntityGstRegistration.objects.filter(
            entity_id=entity_id,
            isactive=True,
            is_primary=True,
        ).exists()
        if has_primary:
            continue
        row = (
            EntityGstRegistration.objects.filter(entity_id=entity_id, isactive=True)
            .order_by("-updated_at", "-id")
            .first()
        )
        if row:
            row.is_primary = True
            row.save(update_fields=["is_primary", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("entity", "0012_alter_entitygstregistration_gstin_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_primary_for_active_gst, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="entitygstregistration",
            constraint=models.UniqueConstraint(
                fields=("entity", "state"),
                condition=Q(isactive=True, state__isnull=False),
                name="uq_entity_gst_registration_entity_state_active",
            ),
        ),
    ]

