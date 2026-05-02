from django.core.management.base import BaseCommand, CommandError

from rbac.models import UserRoleAssignment


class Command(BaseCommand):
    help = "Validate RBAC integrity and fail when active assignments reference inactive roles."

    def add_arguments(self, parser):
        parser.add_argument("--entity", type=int, help="Optional entity id to scope the audit")
        parser.add_argument(
            "--no-fail",
            action="store_true",
            help="Report findings but do not fail with a non-zero exit code.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="Maximum number of sample violations to print (default: 50).",
        )

    def handle(self, *args, **options):
        entity_id = options.get("entity")
        no_fail = bool(options.get("no_fail"))
        limit = max(1, int(options.get("limit") or 50))

        broken_qs = UserRoleAssignment.objects.filter(
            isactive=True,
            role__isactive=False,
        ).select_related("entity", "role", "user")
        if entity_id:
            broken_qs = broken_qs.filter(entity_id=entity_id)

        broken_count = broken_qs.count()
        if broken_count == 0:
            self.stdout.write(self.style.SUCCESS("RBAC integrity check passed. No broken active assignments found."))
            return

        self.stdout.write(
            self.style.ERROR(
                f"Found {broken_count} broken active assignment(s) that reference inactive roles."
            )
        )
        self.stdout.write("Sample findings:")
        for assignment in broken_qs.order_by("entity_id", "user_id", "id")[:limit]:
            self.stdout.write(
                f"- assignment_id={assignment.id} entity_id={assignment.entity_id} "
                f"entity='{getattr(assignment.entity, 'entityname', '')}' user_id={assignment.user_id} "
                f"user_email='{getattr(assignment.user, 'email', '')}' role_id={assignment.role_id} "
                f"role_code='{getattr(assignment.role, 'code', '')}'"
            )

        self.stdout.write(
            "Suggested fix: remap each assignment to an active role in the same entity before role deactivation."
        )
        if not no_fail:
            raise CommandError("RBAC integrity violations found.")
