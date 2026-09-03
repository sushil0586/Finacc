from __future__ import annotations

import json as json_module
from collections import defaultdict

from django.core.management.base import BaseCommand

from numbering.models import DocumentNumberSeries


class Command(BaseCommand):
    help = "Audit active document numbering rows that can generate duplicate display numbers across scopes."

    def add_arguments(self, parser):
        parser.add_argument("--entity", type=int, action="append", default=[], help="Entity ID. Repeat to include multiple entities.")
        parser.add_argument("--entity-name", action="append", default=[], help="Entity name filter. Repeat to include multiple names.")
        parser.add_argument("--entityfinid", type=int, action="append", default=[], help="Entity financial year ID. Repeat to include multiple years.")
        parser.add_argument("--module", action="append", default=[], help="Document module filter, e.g. sales or purchase. Repeatable.")
        parser.add_argument("--doc-code", action="append", default=[], help="Document code filter, e.g. SINV or PINV. Repeatable.")
        parser.add_argument("--issued-only", action="store_true", help="Only show conflict groups where at least one row has issued numbers.")
        parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")

    def handle(self, *args, **options):
        rows = self._collect_conflicts(options)
        if options["json"]:
            self.stdout.write(json_module.dumps({"conflict_count": len(rows), "conflicts": rows}, indent=2, default=str))
            return

        if not rows:
            self.stdout.write(self.style.SUCCESS("No active duplicate numbering patterns found for the selected scope."))
            return

        self.stdout.write(self.style.WARNING(f"Found {len(rows)} active duplicate numbering pattern group(s)."))
        for conflict in rows:
            self.stdout.write(
                f"- {conflict['module']}/{conflict['doc_key']} {conflict['doc_code']} "
                f"entity={conflict['entity_id']} fin={conflict['entityfinid_id']} "
                f"status={conflict['status']}"
            )
            for series in conflict["series"]:
                self.stdout.write(
                    f"  series={series['series_id']} scope={series['scope_label']} "
                    f"start={series['starting_number']} current={series['current_number']} issued={series['issued']}"
                )
            self.stdout.write(f"  recommendation: {conflict['recommendation']}")

    def _collect_conflicts(self, options) -> list[dict]:
        qs = DocumentNumberSeries.objects.select_related("entity", "entityfinid", "subentity", "doc_type").filter(is_active=True)

        entity_ids = [int(value) for value in options.get("entity") or []]
        if entity_ids:
            qs = qs.filter(entity_id__in=entity_ids)

        entity_names = [str(value).strip() for value in options.get("entity_name") or [] if str(value).strip()]
        if entity_names:
            qs = qs.filter(entity__entityname__in=entity_names)

        entityfin_ids = [int(value) for value in options.get("entityfinid") or []]
        if entityfin_ids:
            qs = qs.filter(entityfinid_id__in=entityfin_ids)

        modules = [str(value).strip().lower() for value in options.get("module") or [] if str(value).strip()]
        if modules:
            qs = qs.filter(doc_type__module__in=modules)

        doc_codes = [str(value).strip().upper() for value in options.get("doc_code") or [] if str(value).strip()]
        if doc_codes:
            qs = qs.filter(doc_code__in=doc_codes)

        grouped: dict[tuple, list[DocumentNumberSeries]] = defaultdict(list)
        for series in qs.order_by("entity_id", "entityfinid_id", "doc_type_id", "doc_code", "subentity_id", "id"):
            key = (
                series.entity_id,
                series.entityfinid_id,
                series.doc_type_id,
                series.doc_code,
                series.prefix,
                series.suffix,
                series.number_padding,
                series.separator,
                series.include_year,
                series.include_month,
                series.custom_format,
            )
            grouped[key].append(series)

        conflicts = []
        for series_group in grouped.values():
            if len(series_group) < 2:
                continue
            conflict = self._build_conflict_payload(series_group)
            if options.get("issued_only") and not conflict["has_issued"]:
                continue
            conflicts.append(conflict)
        return conflicts

    @staticmethod
    def _build_conflict_payload(series_group: list[DocumentNumberSeries]) -> dict:
        first = series_group[0]
        series_payload = []
        has_issued = False
        for series in series_group:
            issued = int(series.current_number or 0) > int(series.starting_number or 0)
            has_issued = has_issued or issued
            subentity = getattr(series, "subentity", None)
            series_payload.append(
                {
                    "series_id": series.id,
                    "subentity_id": series.subentity_id,
                    "scope_label": getattr(subentity, "subentityname", None) or "Entity default",
                    "is_head_office": bool(getattr(subentity, "is_head_office", False)),
                    "starting_number": series.starting_number,
                    "current_number": series.current_number,
                    "issued": issued,
                }
            )

        return {
            "entity_id": first.entity_id,
            "entity_name": getattr(first.entity, "entityname", ""),
            "entityfinid_id": first.entityfinid_id,
            "financial_year": getattr(first.entityfinid, "desc", ""),
            "module": getattr(first.doc_type, "module", ""),
            "doc_key": getattr(first.doc_type, "doc_key", ""),
            "doc_code": first.doc_code,
            "pattern": {
                "prefix": first.prefix,
                "suffix": first.suffix,
                "number_padding": first.number_padding,
                "separator": first.separator,
                "include_year": first.include_year,
                "include_month": first.include_month,
                "custom_format": first.custom_format,
            },
            "has_issued": has_issued,
            "status": "requires_business_decision" if has_issued else "safe_to_cleanup_unissued_rows",
            "recommendation": (
                "Issued counters exist. Do not auto-delete; decide whether to keep branch-specific numbering or run a supervised counter merge."
                if has_issued
                else "No numbers issued from the duplicate rows. A settings save or manual cleanup can safely remove branch-generated duplicates."
            ),
            "series": series_payload,
        }
