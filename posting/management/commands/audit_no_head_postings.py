from __future__ import annotations

import json
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError

from posting.services.no_head_audit import audit_no_head_postings


def _parse_date(value: str | None):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise CommandError(f"Invalid date '{value}'. Use YYYY-MM-DD.") from exc


class Command(BaseCommand):
    help = "Audit posted journal rows whose account-backed ledger has no report account head."

    def add_arguments(self, parser):
        parser.add_argument("--entity-id", type=int)
        parser.add_argument("--entityfin-id", type=int)
        parser.add_argument("--subentity-id", type=int)
        parser.add_argument("--txn-type", action="append", help="Limit to one or more posting txn types.")
        parser.add_argument("--from-date", help="Limit by posting_date >= YYYY-MM-DD.")
        parser.add_argument("--to-date", help="Limit by posting_date <= YYYY-MM-DD.")
        parser.add_argument("--include-draft", action="store_true", help="Include draft/reversed entries instead of posted only.")
        parser.add_argument("--sample-size", type=int, default=5)
        parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
        parser.add_argument("--fail-on-issues", action="store_true", help="Exit non-zero when issues are found.")

    def handle(self, *args, **options):
        issues = audit_no_head_postings(
            entity_id=options.get("entity_id"),
            entityfin_id=options.get("entityfin_id"),
            subentity_id=options.get("subentity_id"),
            txn_types=options.get("txn_type") or None,
            from_date=_parse_date(options.get("from_date")),
            to_date=_parse_date(options.get("to_date")),
            posted_only=not bool(options.get("include_draft")),
            sample_size=max(int(options.get("sample_size") or 0), 0),
        )

        if options.get("json"):
            self.stdout.write(json.dumps([issue.as_dict() for issue in issues], indent=2))
        elif not issues:
            self.stdout.write(self.style.SUCCESS("No no-head account-backed posting rows found."))
        else:
            self.stdout.write(self.style.WARNING(f"Found {len(issues)} no-head posting group(s)."))
            for issue in issues:
                self.stdout.write(
                    " | ".join(
                        [
                            f"module={issue.module}",
                            f"txn_type={issue.txn_type}",
                            f"ledger={issue.ledger_id or '-'} {issue.ledger_name}",
                            f"account={issue.account_id or '-'} {issue.account_name}",
                            f"rows={issue.row_count}",
                            f"debit={issue.debit}",
                            f"credit={issue.credit}",
                            f"net={issue.net}",
                            f"samples={issue.sample_txn_ids}",
                        ]
                    )
                )

        if issues and options.get("fail_on_issues"):
            raise CommandError(f"No-head posting audit failed with {len(issues)} issue group(s).")
