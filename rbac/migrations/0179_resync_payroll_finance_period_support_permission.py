from django.db import migrations


def forwards(apps, schema_editor):
    from entity.models import Entity
    from rbac.canonical_seeding import CanonicalRBACCatalogSeedService
    from rbac.seeding import RBACSeedService

    CanonicalRBACCatalogSeedService.seed_global_catalog()

    for entity in Entity.objects.filter(isactive=True).select_related("createdby"):
        actor = getattr(entity, "createdby", None)
        if actor is None:
            continue
        RBACSeedService.seed_entity(
            entity=entity,
            actor=actor,
            seed_default_roles=True,
            ensure_global_catalog=False,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0178_resync_visible_page_support_permissions_second_pass"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
