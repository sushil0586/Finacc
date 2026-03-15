from __future__ import annotations


class LegacyPayrollImportService:
    """
    Placeholder for non-destructive legacy master import tooling.
    """

    @staticmethod
    def import_masters(*, entity_id: int, entityfinid_id: int, dry_run: bool = True) -> dict:
        return {
            "entity_id": entity_id,
            "entityfinid_id": entityfinid_id,
            "dry_run": dry_run,
            "created": 0,
            "updated": 0,
            "warnings": ["Legacy payroll import mapping is not implemented yet."],
        }
