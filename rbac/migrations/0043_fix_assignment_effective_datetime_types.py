import datetime

from django.db import migrations
from django.utils import timezone


ALTER_EFFECTIVE_FROM_SQL = """
ALTER TABLE rbac_userroleassignment
ALTER COLUMN effective_from TYPE timestamptz
USING CASE
    WHEN effective_from IS NULL THEN NULL
    ELSE effective_from::timestamp AT TIME ZONE 'UTC'
END;
"""


ALTER_EFFECTIVE_TO_SQL = """
ALTER TABLE rbac_userroleassignment
ALTER COLUMN effective_to TYPE timestamptz
USING CASE
    WHEN effective_to IS NULL THEN NULL
    ELSE effective_to::timestamp AT TIME ZONE 'UTC'
END;
"""


def apply_postgres_datetime_type_change(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(ALTER_EFFECTIVE_FROM_SQL)
        cursor.execute(ALTER_EFFECTIVE_TO_SQL)


def forwards_normalize_datetimes(apps, schema_editor):
    UserRoleAssignment = apps.get_model("rbac", "UserRoleAssignment")

    for assignment in UserRoleAssignment.objects.exclude(effective_from__isnull=True):
        value = assignment.effective_from
        if isinstance(value, datetime.date) and not isinstance(value, datetime.datetime):
            assignment.effective_from = timezone.make_aware(
                datetime.datetime.combine(value, datetime.time.min),
                timezone=datetime.timezone.utc,
            )
            assignment.save(update_fields=["effective_from"])

    for assignment in UserRoleAssignment.objects.exclude(effective_to__isnull=True):
        value = assignment.effective_to
        if isinstance(value, datetime.date) and not isinstance(value, datetime.datetime):
            assignment.effective_to = timezone.make_aware(
                datetime.datetime.combine(value, datetime.time.max),
                timezone=datetime.timezone.utc,
            )
            assignment.save(update_fields=["effective_to"])


def backwards(apps, schema_editor):
    # The runtime model expects timezone-aware datetimes. Reverting to date
    # columns would reintroduce admin/runtime errors, so this is intentionally
    # left as a no-op.
    return


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0042_deactivate_legacy_roles"),
    ]

    operations = [
        migrations.RunPython(apply_postgres_datetime_type_change, migrations.RunPython.noop),
        migrations.RunPython(forwards_normalize_datetimes, backwards),
    ]
