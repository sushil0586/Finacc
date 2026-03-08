from django.db import migrations


def cleanup_orphaned_references(apps, schema_editor):
    Entity = apps.get_model("entity", "Entity")
    SubEntity = apps.get_model("entity", "SubEntity")
    User = apps.get_model("Authentication", "User")
    Role = apps.get_model("rbac", "Role")
    DataAccessPolicy = apps.get_model("rbac", "DataAccessPolicy")
    RoleDataAccessPolicy = apps.get_model("rbac", "RoleDataAccessPolicy")
    UserRoleAssignment = apps.get_model("rbac", "UserRoleAssignment")
    Menu = apps.get_model("rbac", "Menu")

    valid_entity_ids = set(Entity.objects.values_list("id", flat=True))
    valid_subentity_ids = set(SubEntity.objects.values_list("id", flat=True))
    valid_user_ids = set(User.objects.values_list("id", flat=True))

    Role.objects.exclude(entity_id__isnull=True).exclude(entity_id__in=valid_entity_ids).update(entity_id=None)
    Role.objects.exclude(createdby_id__isnull=True).exclude(createdby_id__in=valid_user_ids).update(createdby_id=None)

    valid_role_ids = set(Role.objects.values_list("id", flat=True))

    DataAccessPolicy.objects.exclude(entity_id__isnull=True).exclude(entity_id__in=valid_entity_ids).update(entity_id=None)

    RoleDataAccessPolicy.objects.exclude(role_id__in=valid_role_ids).delete()
    valid_policy_ids = set(DataAccessPolicy.objects.values_list("id", flat=True))
    RoleDataAccessPolicy.objects.exclude(policy_id__in=valid_policy_ids).delete()

    UserRoleAssignment.objects.exclude(subentity_id__isnull=True).exclude(subentity_id__in=valid_subentity_ids).update(subentity_id=None)
    UserRoleAssignment.objects.exclude(entity_id__in=valid_entity_ids).delete()
    UserRoleAssignment.objects.exclude(user_id__in=valid_user_ids).delete()
    UserRoleAssignment.objects.exclude(role_id__in=valid_role_ids).delete()

    valid_menu_ids = set(Menu.objects.values_list("id", flat=True))
    Menu.objects.exclude(parent_id__isnull=True).exclude(parent_id__in=valid_menu_ids).update(parent_id=None)


class Migration(migrations.Migration):

    dependencies = [
        ("rbac", "0002_reconcile_legacy_rbac_schema"),
    ]

    operations = [
        migrations.RunPython(cleanup_orphaned_references, migrations.RunPython.noop),
    ]

