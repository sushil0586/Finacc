from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_date

from manufacturing.report_correctness_audit import audit_manufacturing_report_correctness


class Command(BaseCommand):
    help = "Audit manufacturing report correctness against work-order source lines, journal lines, and inventory moves."

    def add_arguments(self, parser):
        parser.add_argument("--entity-id", type=int, required=True)
        parser.add_argument("--entityfin-id", type=int)
        parser.add_argument("--subentity-id", type=int)
        parser.add_argument("--from-date")
        parser.add_argument("--to-date")
        parser.add_argument("--limit", type=int)
        parser.add_argument("--fail-on-issues", action="store_true")

    def handle(self, *args, **options):
        from_date = parse_date(options["from_date"]) if options.get("from_date") else None
        to_date = parse_date(options["to_date"]) if options.get("to_date") else None
        issues = audit_manufacturing_report_correctness(
            entity_id=options["entity_id"],
            entityfin_id=options.get("entityfin_id"),
            subentity_id=options.get("subentity_id"),
            from_date=from_date,
            to_date=to_date,
            limit=options.get("limit"),
        )

        if not issues:
            self.stdout.write(self.style.SUCCESS("Manufacturing report correctness audit passed."))
            return

        self.stdout.write(self.style.ERROR(f"Manufacturing report correctness audit found {len(issues)} issue(s)."))
        for issue in issues:
            self.stdout.write(
                f"- WO {issue.work_order_no} ({issue.work_order_id}) "
                f"{issue.area}.{issue.field}: expected={issue.expected} actual={issue.actual}; {issue.message}"
            )

        if options["fail_on_issues"]:
            raise CommandError("Manufacturing report correctness audit failed.")
