from __future__ import annotations

from dataclasses import dataclass

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from entity.models import Entity, SubEntity
from hrms.models import (
    AttendanceApproval,
    AttendanceDeviceLog,
    AttendanceImportBatch,
    AttendanceMonthlyClose,
    ContractLeaveBalanceSnapshot,
    ContractLeaveLedgerEntry,
    DailyAttendance,
    LeaveApplication,
)


@dataclass(frozen=True)
class CleanupSpec:
    label: str
    model: type


class Command(BaseCommand):
    help = (
        "Delete HRMS transactional/runtime data for an entity. "
        "Employees, contracts, org units, leave policies, shifts, calendars, "
        "and other setup records are preserved."
    )

    def add_arguments(self, parser):
        parser.add_argument("--entity", type=int, required=True, help="Entity ID")
        parser.add_argument(
            "--subentity",
            type=int,
            help=(
                "Optional subentity ID. If omitted, deletes HRMS transactional data "
                "for the full entity. Use 0 for root-scoped records where subentity is null."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview how many rows will be deleted without making changes.",
        )

    def handle(self, *args, **options):
        entity_id = int(options["entity"])
        dry_run = bool(options["dry_run"])
        raw_subentity_id = options.get("subentity")
        scoped_to_subentity = raw_subentity_id is not None
        subentity_id = None if raw_subentity_id in (None, 0) else int(raw_subentity_id)

        entity = Entity.objects.filter(pk=entity_id).only("id", "entityname").first()
        if not entity:
            raise CommandError(f"Entity {entity_id} does not exist.")

        if subentity_id is not None:
            subentity = SubEntity.objects.filter(pk=subentity_id, entity_id=entity_id).only("id").first()
            if not subentity:
                raise CommandError(f"SubEntity {subentity_id} does not belong to entity {entity_id}.")

        specs = self._build_specs()
        previews: list[tuple[CleanupSpec, int]] = []

        for spec in specs:
            qs = self._scoped_queryset(spec, entity_id, scoped_to_subentity, subentity_id)
            previews.append((spec, qs.count()))

        total_rows = sum(count for _, count in previews)

        self.stdout.write("")
        self.stdout.write(self.style.WARNING("HRMS transactional data reset scope"))
        self.stdout.write(f"- Entity: {entity_id} ({getattr(entity, 'entityname', '')})")
        if not scoped_to_subentity:
            self.stdout.write("- Subentity: all")
        else:
            self.stdout.write(f"- Subentity: {'root/null' if subentity_id is None else subentity_id}")
        self.stdout.write("")

        for spec, count in previews:
            self.stdout.write(f"{spec.label}: {count}")

        self.stdout.write("")
        self.stdout.write(self.style.WARNING(f"Total rows matched: {total_rows}"))

        if dry_run:
            self.stdout.write(self.style.SUCCESS("Dry run complete. No HRMS data was deleted."))
            return

        with transaction.atomic():
            for spec, count in previews:
                if count == 0:
                    continue
                qs = self._scoped_queryset(spec, entity_id, scoped_to_subentity, subentity_id)
                deleted, _ = qs.delete()
                self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} rows from {spec.label}"))

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("HRMS transactional data reset completed successfully."))

    def _build_specs(self) -> list[CleanupSpec]:
        return [
            CleanupSpec("Attendance device logs", AttendanceDeviceLog),
            CleanupSpec("Daily attendance entries", DailyAttendance),
            CleanupSpec("Attendance approvals", AttendanceApproval),
            CleanupSpec("Attendance monthly closes", AttendanceMonthlyClose),
            CleanupSpec("Attendance import batches", AttendanceImportBatch),
            CleanupSpec("Leave applications", LeaveApplication),
            CleanupSpec("Leave ledger entries", ContractLeaveLedgerEntry),
            CleanupSpec("Leave balance snapshots", ContractLeaveBalanceSnapshot),
        ]

    def _scoped_queryset(
        self,
        spec: CleanupSpec,
        entity_id: int,
        scoped_to_subentity: bool,
        subentity_id: int | None,
    ):
        manager = getattr(spec.model, "all_objects", spec.model._default_manager)
        queryset = manager.filter(entity_id=entity_id)
        if scoped_to_subentity:
            if subentity_id is None:
                queryset = queryset.filter(subentity__isnull=True)
            else:
                queryset = queryset.filter(subentity_id=subentity_id)
        return queryset
