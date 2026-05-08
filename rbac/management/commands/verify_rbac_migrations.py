from django.core.management.base import BaseCommand, CommandError
from django.db import DEFAULT_DB_ALIAS, connections
from django.db.migrations.executor import MigrationExecutor


class Command(BaseCommand):
    help = "Verify that all RBAC app migrations are applied."

    def add_arguments(self, parser):
        parser.add_argument(
            "--database",
            default=DEFAULT_DB_ALIAS,
            help=f"Database alias to inspect (default: {DEFAULT_DB_ALIAS}).",
        )
        parser.add_argument(
            "--no-fail",
            action="store_true",
            help="Report pending migrations but do not fail with a non-zero exit code.",
        )

    def handle(self, *args, **options):
        database = options["database"]
        no_fail = bool(options.get("no_fail"))
        connection = connections[database]
        executor = MigrationExecutor(connection)
        loader = executor.loader

        disk_nodes = sorted(node for node in loader.disk_migrations if node[0] == "rbac")
        applied_nodes = set(loader.applied_migrations)
        pending_nodes = [node for node in disk_nodes if node not in applied_nodes]

        if not pending_nodes:
            self.stdout.write(self.style.SUCCESS(f"RBAC migrations verified on '{database}'. All migrations are applied."))
            return

        self.stdout.write(self.style.ERROR(f"RBAC migrations pending on '{database}':"))
        for app_label, migration_name in pending_nodes:
            self.stdout.write(f"- {app_label}.{migration_name}")

        self.stdout.write("Run `python3 manage.py migrate rbac` to apply the pending RBAC migrations.")
        if not no_fail:
            raise CommandError("Pending RBAC migrations found.")
