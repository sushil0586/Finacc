from __future__ import annotations

import csv
import io
import re
import uuid
from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from Authentication.models import User
from entity.approval_workflow_service import ApprovalWorkflowService
from entity.notification_service import NotificationService
from financial.models import account
from payroll.models import (
    FnFSettlement,
    PayrollPaymentBatch,
    PayrollPaymentBatchLine,
    PayrollPaymentFileExport,
    PayrollPaymentStatusLog,
    PayrollRun,
    PayrollRunEmployee,
)
from payroll.services.payroll_run_hardening_service import PayrollRunHardeningService

ZERO2 = Decimal("0.00")
IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")


@dataclass(frozen=True)
class PayrollPaymentExportResult:
    batch: PayrollPaymentBatch
    export_record: PayrollPaymentFileExport
    file_name: str
    content_type: str
    file_content: str


class PayrollPaymentBatchService:
    @staticmethod
    def _notification_users_for_batch(batch: PayrollPaymentBatch, *extra_user_ids: int | None):
        user_ids: set[int] = set()
        for field_name in (
            "requested_by_id",
            "approved_by_id",
            "rejected_by_id",
            "exported_by_id",
            "paid_by_id",
            "failed_by_id",
            "cancelled_by_id",
            "locked_by_id",
        ):
            value = getattr(batch, field_name, None)
            if value:
                user_ids.add(int(value))
        run = getattr(batch, "payroll_run", None)
        if run is not None:
            for field_name in ("created_by_id", "submitted_by_id", "approved_by_id"):
                value = getattr(run, field_name, None)
                if value:
                    user_ids.add(int(value))
        for value in extra_user_ids:
            if value:
                user_ids.add(int(value))
        return User.objects.filter(pk__in=sorted(user_ids))

    @staticmethod
    def _next_batch_number(*, entity_id: int) -> str:
        stamp = timezone.now().strftime("%Y%m%d%H%M%S")
        return f"PPB-{entity_id}-{stamp}-{uuid.uuid4().hex[:6].upper()}"

    @staticmethod
    def _normalize_text(value) -> str:
        return str(value or "").strip()

    @classmethod
    def _normalize_ifsc(cls, value) -> str:
        return cls._normalize_text(value).upper()

    @classmethod
    def _resolve_primary_bank_detail(cls, payment_account: account | None):
        if payment_account is None:
            return None
        return (
            payment_account.bank_details.filter(isprimary=True, isactive=True)
            .only("bankname", "banKAcno", "ifsc", "branch")
            .first()
            or payment_account.bank_details.filter(isactive=True).only("bankname", "banKAcno", "ifsc", "branch").first()
        )

    @classmethod
    def _resolve_payment_details(cls, *, profile, fallback_name: str) -> dict:
        payment_account = getattr(profile, "bank_account", None)
        profile_bank = getattr(profile, "bank_account_details", None) or {}
        primary_bank = cls._resolve_primary_bank_detail(payment_account)
        account_number = cls._normalize_text(
            profile_bank.get("account_number")
            or profile_bank.get("banKAcno")
            or getattr(primary_bank, "banKAcno", "")
        )
        ifsc_code = cls._normalize_ifsc(
            profile_bank.get("ifsc_code")
            or profile_bank.get("ifsc")
            or getattr(primary_bank, "ifsc", "")
        )
        bank_name = cls._normalize_text(
            profile_bank.get("bank_name")
            or profile_bank.get("bankname")
            or getattr(primary_bank, "bankname", "")
        )
        branch_name = cls._normalize_text(
            profile_bank.get("branch_name")
            or profile_bank.get("branch")
            or getattr(primary_bank, "branch", "")
        )
        account_holder_name = cls._normalize_text(profile_bank.get("account_holder_name")) or fallback_name
        return {
            "payment_account": payment_account,
            "account_holder_name": account_holder_name,
            "bank_name": bank_name,
            "branch_name": branch_name,
            "account_number": account_number,
            "ifsc_code": ifsc_code,
        }

    @classmethod
    def _line_narration_for_run(cls, *, run: PayrollRun, employee_name: str) -> str:
        reference = run.run_number or run.payroll_period.code or f"RUN-{run.id}"
        return f"Salary {reference} {employee_name}".strip()[:255]

    @classmethod
    def _line_narration_for_fnf(cls, *, settlement: FnFSettlement, employee_name: str) -> str:
        reference = settlement.settlement_number or f"FNF-{settlement.id}"
        return f"FnF {reference} {employee_name}".strip()[:255]

    @classmethod
    def _log_status(
        cls,
        *,
        batch: PayrollPaymentBatch,
        old_status: str,
        new_status: str,
        user_id: int | None,
        comment: str = "",
        payload: dict | None = None,
    ) -> None:
        PayrollPaymentStatusLog.objects.create(
            batch=batch,
            old_status=old_status,
            new_status=new_status,
            acted_by_id=user_id,
            comment=comment,
            payload=payload or {},
        )

    @classmethod
    def _refresh_batch_totals(cls, *, batch: PayrollPaymentBatch) -> PayrollPaymentBatch:
        aggregates = batch.lines.aggregate(
            total_lines=Count("id"),
            total_amount=Sum("amount"),
            payable_line_count=Count("id", filter=Q(line_status=PayrollPaymentBatchLine.LineStatus.VALID)),
            invalid_line_count=Count("id", filter=Q(line_status=PayrollPaymentBatchLine.LineStatus.INVALID)),
            warning_line_count=Count("id", filter=Q(has_duplicate_account_warning=True)),
        )
        batch.total_lines = int(aggregates.get("total_lines") or 0)
        batch.total_amount = aggregates.get("total_amount") or ZERO2
        batch.payable_line_count = int(aggregates.get("payable_line_count") or 0)
        batch.invalid_line_count = int(aggregates.get("invalid_line_count") or 0)
        batch.warning_line_count = int(aggregates.get("warning_line_count") or 0)
        batch.save(
            update_fields=[
                "total_lines",
                "total_amount",
                "payable_line_count",
                "invalid_line_count",
                "warning_line_count",
                "updated_at",
            ]
        )
        return batch

    @classmethod
    def _validate_line(cls, *, line: PayrollPaymentBatchLine, duplicate_keys: set[str]) -> tuple[list[str], list[str]]:
        errors: list[str] = []
        warnings: list[str] = []
        payment_account = line.payment_account
        if payment_account is None:
            errors.append("Missing bank account.")
        elif not getattr(payment_account, "isactive", True):
            errors.append("Bank account is inactive.")
        if not cls._normalize_text(line.account_number):
            errors.append("Missing account number.")
        if not cls._normalize_text(line.ifsc_code):
            errors.append("Missing IFSC.")
        elif not IFSC_RE.match(cls._normalize_ifsc(line.ifsc_code)):
            errors.append("Invalid IFSC format.")
        duplicate_key = f"{cls._normalize_text(line.account_number)}::{cls._normalize_ifsc(line.ifsc_code)}"
        if cls._normalize_text(line.account_number) and cls._normalize_ifsc(line.ifsc_code) and duplicate_key in duplicate_keys:
            warnings.append("Duplicate bank account detected within this batch.")
        return errors, warnings

    @classmethod
    def _apply_validation_results(cls, *, batch: PayrollPaymentBatch, duplicate_keys: set[str]) -> PayrollPaymentBatch:
        invalid_count = 0
        warning_count = 0
        for line in batch.lines.select_related("payment_account"):
            errors, warnings = cls._validate_line(line=line, duplicate_keys=duplicate_keys)
            line.validation_errors_json = errors
            line.validation_warnings_json = warnings
            line.has_duplicate_account_warning = any("Duplicate" in warning for warning in warnings)
            line.line_status = (
                PayrollPaymentBatchLine.LineStatus.INVALID if errors else PayrollPaymentBatchLine.LineStatus.VALID
            )
            if errors:
                invalid_count += 1
            if warnings:
                warning_count += 1
            line.save(
                update_fields=[
                    "validation_errors_json",
                    "validation_warnings_json",
                    "has_duplicate_account_warning",
                    "line_status",
                    "updated_at",
                ]
            )
        batch.invalid_line_count = invalid_count
        batch.warning_line_count = warning_count
        batch.validation_summary_json = {
            "validated_at": timezone.now().isoformat(),
            "invalid_line_count": invalid_count,
            "warning_line_count": warning_count,
        }
        cls._refresh_batch_totals(batch=batch)
        return batch

    @classmethod
    def _batch_duplicate_keys(cls, *, batch: PayrollPaymentBatch) -> set[str]:
        duplicate_values = (
            batch.lines.exclude(account_number="", ifsc_code="")
            .values("account_number", "ifsc_code")
            .annotate(count=Count("id"))
            .filter(count__gt=1)
        )
        return {
            f"{cls._normalize_text(item['account_number'])}::{cls._normalize_ifsc(item['ifsc_code'])}"
            for item in duplicate_values
        }

    @classmethod
    @transaction.atomic
    def create_from_payroll_run(
        cls,
        *,
        run: PayrollRun,
        user_id: int | None = None,
        batch_name: str = "",
        payout_date=None,
        allow_non_positive_amounts: bool = False,
        export_format: str = PayrollPaymentBatch.ExportFormat.GENERIC_CSV,
    ) -> PayrollPaymentBatch:
        if run.status not in {PayrollRun.Status.APPROVED, PayrollRun.Status.POSTED}:
            raise ValueError("Only approved or posted payroll runs can be converted to payment batches.")
        open_statuses = {
            PayrollPaymentBatch.Status.DRAFT,
            PayrollPaymentBatch.Status.VALIDATED,
            PayrollPaymentBatch.Status.APPROVED,
            PayrollPaymentBatch.Status.EXPORTED,
        }
        existing = PayrollPaymentBatch.objects.filter(payroll_run=run, status__in=open_statuses).first()
        if existing:
            raise ValueError("An active payment batch already exists for this payroll run.")
        batch = PayrollPaymentBatch.objects.create(
            entity=run.entity,
            entityfinid=run.entityfinid,
            subentity=run.subentity,
            source_type=PayrollPaymentBatch.SourceType.PAYROLL_RUN,
            payroll_run=run,
            batch_number=cls._next_batch_number(entity_id=run.entity_id),
            batch_name=batch_name or f"{run.run_number or run.payroll_period.code} Payments",
            payout_date=payout_date or run.payout_date,
            export_format=export_format,
            allow_non_positive_amounts=allow_non_positive_amounts,
            status=PayrollPaymentBatch.Status.DRAFT,
        )
        skipped_count = 0
        rows = run.employee_runs.select_related(
            "contract_payroll_profile__hrms_contract__employee",
            "contract_payroll_profile__bank_account",
        ).order_by("id")
        sequence = 10
        for row in rows:
            amount = row.payable_amount or ZERO2
            if amount <= ZERO2 and not allow_non_positive_amounts:
                skipped_count += 1
                continue
            profile = row.contract_payroll_profile
            payment_details = cls._resolve_payment_details(profile=profile, fallback_name=row.employee_name)
            PayrollPaymentBatchLine.objects.create(
                batch=batch,
                payroll_run_employee=row,
                contract_payroll_profile=profile,
                sequence=sequence,
                employee_code=row.employee_code,
                employee_name=row.employee_name,
                employee_user_id=row.employee_user_id,
                payment_account=payment_details["payment_account"],
                account_holder_name=payment_details["account_holder_name"],
                bank_name=payment_details["bank_name"],
                branch_name=payment_details["branch_name"],
                account_number=payment_details["account_number"],
                ifsc_code=payment_details["ifsc_code"],
                amount=amount,
                narration=cls._line_narration_for_run(run=run, employee_name=row.employee_name),
                line_status=PayrollPaymentBatchLine.LineStatus.PENDING,
                source_snapshot_json={
                    "payroll_run_employee_id": row.id,
                    "contract_payroll_profile_id": str(row.contract_payroll_profile_id) if row.contract_payroll_profile_id else None,
                    "payment_status": row.payment_status,
                    "payable_amount": str(amount),
                },
            )
            sequence += 10
        batch.skipped_line_count = skipped_count
        batch.save(update_fields=["skipped_line_count", "updated_at"])
        return cls._refresh_batch_totals(batch=batch)

    @classmethod
    @transaction.atomic
    def create_from_fnf_settlement(
        cls,
        *,
        settlement: FnFSettlement,
        user_id: int | None = None,
        batch_name: str = "",
        payout_date=None,
        allow_non_positive_amounts: bool = False,
        export_format: str = PayrollPaymentBatch.ExportFormat.GENERIC_CSV,
    ) -> PayrollPaymentBatch:
        if settlement.status not in {FnFSettlement.Status.APPROVED, FnFSettlement.Status.POSTED, FnFSettlement.Status.PAID}:
            raise ValueError("Only approved or posted FnF settlements can be converted to payment batches.")
        open_statuses = {
            PayrollPaymentBatch.Status.DRAFT,
            PayrollPaymentBatch.Status.VALIDATED,
            PayrollPaymentBatch.Status.APPROVED,
            PayrollPaymentBatch.Status.EXPORTED,
        }
        existing = PayrollPaymentBatch.objects.filter(fnf_settlement=settlement, status__in=open_statuses).first()
        if existing:
            raise ValueError("An active payment batch already exists for this FnF settlement.")
        batch = PayrollPaymentBatch.objects.create(
            entity=settlement.entity,
            entityfinid=settlement.entityfinid,
            subentity=settlement.subentity,
            source_type=PayrollPaymentBatch.SourceType.FNF_SETTLEMENT,
            fnf_settlement=settlement,
            batch_number=cls._next_batch_number(entity_id=settlement.entity_id),
            batch_name=batch_name or f"{settlement.settlement_number or f'FNF-{settlement.id}'} Payments",
            payout_date=payout_date or settlement.settlement_date,
            export_format=export_format,
            allow_non_positive_amounts=allow_non_positive_amounts,
            status=PayrollPaymentBatch.Status.DRAFT,
        )
        amount = settlement.net_payable_amount or ZERO2
        if amount <= ZERO2 and not allow_non_positive_amounts:
            batch.skipped_line_count = 1
            batch.save(update_fields=["skipped_line_count", "updated_at"])
            return batch
        profile = settlement.contract_payroll_profile
        payment_details = cls._resolve_payment_details(profile=profile, fallback_name=profile.employee_name)
        PayrollPaymentBatchLine.objects.create(
            batch=batch,
            fnf_settlement=settlement,
            contract_payroll_profile=profile,
            sequence=10,
            employee_code=profile.employee_code,
            employee_name=profile.employee_name,
            employee_user_id=profile.employee_user_id,
            payment_account=payment_details["payment_account"],
            account_holder_name=payment_details["account_holder_name"],
            bank_name=payment_details["bank_name"],
            branch_name=payment_details["branch_name"],
            account_number=payment_details["account_number"],
            ifsc_code=payment_details["ifsc_code"],
            amount=amount,
            narration=cls._line_narration_for_fnf(settlement=settlement, employee_name=profile.employee_name),
            line_status=PayrollPaymentBatchLine.LineStatus.PENDING,
            source_snapshot_json={
                "fnf_settlement_id": settlement.id,
                "contract_payroll_profile_id": str(profile.id),
                "settlement_status": settlement.status,
                "net_payable_amount": str(amount),
            },
        )
        return cls._refresh_batch_totals(batch=batch)

    @classmethod
    @transaction.atomic
    def validate_batch(cls, *, batch: PayrollPaymentBatch, user_id: int | None = None, comment: str = "") -> PayrollPaymentBatch:
        if batch.status in {
            PayrollPaymentBatch.Status.PAID,
            PayrollPaymentBatch.Status.FAILED,
            PayrollPaymentBatch.Status.CANCELLED,
        }:
            raise ValueError("Finalized payment batches cannot be revalidated.")
        duplicate_keys = cls._batch_duplicate_keys(batch=batch)
        cls._apply_validation_results(batch=batch, duplicate_keys=duplicate_keys)
        old_status = batch.status
        batch.status = PayrollPaymentBatch.Status.VALIDATED
        batch.save(update_fields=["status", "validation_summary_json", "updated_at"])
        cls._log_status(batch=batch, old_status=old_status, new_status=batch.status, user_id=user_id, comment=comment)
        return batch

    @classmethod
    @transaction.atomic
    def submit_batch(cls, *, batch: PayrollPaymentBatch, user_id: int | None = None, comment: str = "") -> PayrollPaymentBatch:
        if batch.status not in {PayrollPaymentBatch.Status.VALIDATED, PayrollPaymentBatch.Status.APPROVED}:
            raise ValueError("Only validated or approved payment batches can be submitted for approval.")
        ApprovalWorkflowService.submit_for_approval(
            instance=batch,
            workflow_key="payroll_payment_batch",
            actor_id=user_id,
            remarks=comment,
            title=batch.batch_number,
        )
        batch.requested_by_id = user_id
        batch.requested_at = timezone.now()
        batch.approval_remarks = comment or batch.approval_remarks
        batch.save(update_fields=["requested_by", "requested_at", "approval_remarks", "updated_at"])
        return batch

    @classmethod
    @transaction.atomic
    def approve_batch(cls, *, batch: PayrollPaymentBatch, user_id: int | None = None, comment: str = "") -> PayrollPaymentBatch:
        if batch.status not in {PayrollPaymentBatch.Status.VALIDATED, PayrollPaymentBatch.Status.APPROVED}:
            raise ValueError("Only validated payment batches can be approved.")
        if batch.approval_status == PayrollPaymentBatch.ApprovalStatus.DRAFT:
            cls.submit_batch(batch=batch, user_id=user_id, comment=comment)
        cls._refresh_batch_totals(batch=batch)
        if batch.invalid_line_count:
            raise ValueError("Payment batch approval is blocked until validation issues are resolved.")
        ApprovalWorkflowService.approve(
            instance=batch,
            workflow_key="payroll_payment_batch",
            actor_id=user_id,
            remarks=comment,
        )
        old_status = batch.status
        batch.status = PayrollPaymentBatch.Status.APPROVED
        batch.approved_by_id = user_id
        batch.approved_at = timezone.now()
        batch.approval_remarks = comment or batch.approval_remarks
        batch.save(update_fields=["status", "approved_by", "approved_at", "approval_remarks", "updated_at"])
        cls._log_status(batch=batch, old_status=old_status, new_status=batch.status, user_id=user_id, comment=comment)
        return batch

    @classmethod
    def _export_rows(cls, *, batch: PayrollPaymentBatch) -> list[dict]:
        rows: list[dict] = []
        for line in batch.lines.exclude(line_status=PayrollPaymentBatchLine.LineStatus.INVALID).order_by("sequence", "id"):
            rows.append(
                {
                    "employee_code": line.employee_code,
                    "employee_name": line.employee_name,
                    "account_holder_name": line.account_holder_name,
                    "account_number": line.account_number,
                    "ifsc_code": line.ifsc_code,
                    "bank_name": line.bank_name,
                    "branch_name": line.branch_name,
                    "amount": f"{line.amount:.2f}",
                    "narration": line.narration,
                }
            )
        return rows

    @classmethod
    def _render_csv(cls, *, rows: list[dict]) -> str:
        buffer = io.StringIO()
        writer = csv.DictWriter(
            buffer,
            fieldnames=["employee_code", "employee_name", "account_holder_name", "account_number", "ifsc_code", "amount", "narration"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "employee_code": row["employee_code"],
                    "employee_name": row["employee_name"],
                    "account_holder_name": row["account_holder_name"],
                    "account_number": row["account_number"],
                    "ifsc_code": row["ifsc_code"],
                    "amount": row["amount"],
                    "narration": row["narration"],
                }
            )
        return buffer.getvalue()

    @classmethod
    def _render_bank_placeholder_csv(cls, *, rows: list[dict]) -> str:
        buffer = io.StringIO()
        writer = csv.DictWriter(
            buffer,
            fieldnames=["employee_name", "account_number", "ifsc_code", "amount", "narration", "bank_name", "branch_name"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "employee_name": row["employee_name"],
                    "account_number": row["account_number"],
                    "ifsc_code": row["ifsc_code"],
                    "amount": row["amount"],
                    "narration": row["narration"],
                    "bank_name": row["bank_name"],
                    "branch_name": row["branch_name"],
                }
            )
        return buffer.getvalue()

    @classmethod
    @transaction.atomic
    def export_batch(
        cls,
        *,
        batch: PayrollPaymentBatch,
        user_id: int | None = None,
        export_format: str | None = None,
        comment: str = "",
    ) -> PayrollPaymentExportResult:
        if batch.status not in {PayrollPaymentBatch.Status.APPROVED, PayrollPaymentBatch.Status.EXPORTED}:
            raise ValueError("Only approved payment batches can be exported.")
        if batch.approval_status not in {
            PayrollPaymentBatch.ApprovalStatus.APPROVED,
            PayrollPaymentBatch.ApprovalStatus.LOCKED,
        }:
            raise ValueError("Payment batch must be approval-cleared before export.")
        if batch.source_type == PayrollPaymentBatch.SourceType.PAYROLL_RUN and batch.payroll_run_id:
            if batch.payroll_run.status != PayrollRun.Status.POSTED:
                raise ValueError("Payroll payment batches can be exported only after the source payroll run is posted.")
        export_format = export_format or batch.export_format or PayrollPaymentBatch.ExportFormat.GENERIC_CSV
        rows = cls._export_rows(batch=batch)
        if export_format == PayrollPaymentBatch.ExportFormat.BANK_UPLOAD_PLACEHOLDER:
            file_content = cls._render_bank_placeholder_csv(rows=rows)
        else:
            file_content = cls._render_csv(rows=rows)
        batch.export_format = export_format
        file_name = f"{batch.batch_number.lower()}-{export_format.lower()}.csv"
        export_record = PayrollPaymentFileExport.objects.create(
            batch=batch,
            export_format=export_format,
            file_name=file_name,
            content_type="text/csv",
            row_count=len(rows),
            file_content=file_content,
            export_metadata_json={
                "exported_at": timezone.now().isoformat(),
                "format": export_format,
            },
            exported_by_id=user_id,
            exported_at=timezone.now(),
        )
        old_status = batch.status
        batch.status = PayrollPaymentBatch.Status.EXPORTED
        batch.exported_by_id = user_id
        batch.exported_at = timezone.now()
        batch.export_reference = export_record.file_name
        batch.save(
            update_fields=[
                "status",
                "export_format",
                "exported_by",
                "exported_at",
                "export_reference",
                "updated_at",
            ]
        )
        if batch.source_type == PayrollPaymentBatch.SourceType.PAYROLL_RUN and batch.payroll_run_id:
            run = batch.payroll_run
            assert run is not None
            if run.payment_status != PayrollRun.PaymentStatus.HANDED_OFF:
                PayrollRunHardeningService.handoff_payment(
                    run,
                    user_id=user_id or 0,
                    batch_ref=batch.batch_number,
                    payload={
                        "payment_batch_id": str(batch.id),
                        "export_file_name": file_name,
                        "export_format": export_format,
                    },
                )
        cls._log_status(
            batch=batch,
            old_status=old_status,
            new_status=batch.status,
            user_id=user_id,
            comment=comment,
            payload={"export_file_name": file_name, "export_format": export_format},
        )
        NotificationService.emit(
            instance=batch,
            workflow_key="payroll_payment_batch",
            event_code="PAYMENT_BATCH_EXPORTED",
            title="Payment Batch Exported",
            message=f"Payment batch {batch.batch_number} was exported for payout processing.",
            users=cls._notification_users_for_batch(batch, user_id),
            actor=User.objects.filter(pk=user_id).first() if user_id else None,
            target_url=NotificationService.default_target_url(workflow_key="payroll_payment_batch", instance=batch),
            payload={"export_file_name": file_name, "export_format": export_format},
        )
        return PayrollPaymentExportResult(
            batch=batch,
            export_record=export_record,
            file_name=file_name,
            content_type="text/csv",
            file_content=file_content,
        )

    @classmethod
    @transaction.atomic
    def mark_paid(cls, *, batch: PayrollPaymentBatch, user_id: int | None = None, payment_reference: str = "", comment: str = "") -> PayrollPaymentBatch:
        if batch.status not in {PayrollPaymentBatch.Status.APPROVED, PayrollPaymentBatch.Status.EXPORTED, PayrollPaymentBatch.Status.FAILED}:
            raise ValueError("Only approved, exported, or failed payment batches can be marked paid.")
        old_status = batch.status
        batch.status = PayrollPaymentBatch.Status.PAID
        batch.paid_by_id = user_id
        batch.paid_at = timezone.now()
        batch.payment_reference = payment_reference
        batch.save(update_fields=["status", "paid_by", "paid_at", "payment_reference", "updated_at"])
        batch.lines.update(line_status=PayrollPaymentBatchLine.LineStatus.PAID)
        if batch.source_type == PayrollPaymentBatch.SourceType.PAYROLL_RUN and batch.payroll_run_id:
            PayrollRunHardeningService.reconcile_payment(
                batch.payroll_run,
                user_id=user_id or 0,
                payment_status=PayrollRun.PaymentStatus.DISBURSED,
                comment=comment or "Payment batch marked paid.",
            )
        cls._log_status(
            batch=batch,
            old_status=old_status,
            new_status=batch.status,
            user_id=user_id,
            comment=comment,
            payload={"payment_reference": payment_reference},
        )
        NotificationService.emit(
            instance=batch,
            workflow_key="payroll_payment_batch",
            event_code="PAYMENT_BATCH_PAID",
            title="Payment Batch Paid",
            message=f"Payment batch {batch.batch_number} was marked paid.",
            users=cls._notification_users_for_batch(batch, user_id),
            actor=User.objects.filter(pk=user_id).first() if user_id else None,
            target_url=NotificationService.default_target_url(workflow_key="payroll_payment_batch", instance=batch),
            payload={"payment_reference": payment_reference},
        )
        return batch

    @classmethod
    @transaction.atomic
    def mark_failed(cls, *, batch: PayrollPaymentBatch, user_id: int | None = None, failure_reason: str = "", comment: str = "") -> PayrollPaymentBatch:
        if batch.status not in {PayrollPaymentBatch.Status.APPROVED, PayrollPaymentBatch.Status.EXPORTED, PayrollPaymentBatch.Status.FAILED}:
            raise ValueError("Only approved or exported payment batches can be marked failed.")
        old_status = batch.status
        batch.status = PayrollPaymentBatch.Status.FAILED
        batch.failed_by_id = user_id
        batch.failed_at = timezone.now()
        batch.failure_reason = failure_reason
        batch.save(update_fields=["status", "failed_by", "failed_at", "failure_reason", "updated_at"])
        batch.lines.update(line_status=PayrollPaymentBatchLine.LineStatus.FAILED)
        if batch.source_type == PayrollPaymentBatch.SourceType.PAYROLL_RUN and batch.payroll_run_id:
            PayrollRunHardeningService.reconcile_payment(
                batch.payroll_run,
                user_id=user_id or 0,
                payment_status=PayrollRun.PaymentStatus.FAILED,
                comment=comment or failure_reason or "Payment batch failed.",
            )
        cls._log_status(
            batch=batch,
            old_status=old_status,
            new_status=batch.status,
            user_id=user_id,
            comment=comment,
            payload={"failure_reason": failure_reason},
        )
        return batch

    @classmethod
    @transaction.atomic
    def cancel_batch(cls, *, batch: PayrollPaymentBatch, user_id: int | None = None, cancellation_reason: str = "", comment: str = "") -> PayrollPaymentBatch:
        if batch.status not in {
            PayrollPaymentBatch.Status.DRAFT,
            PayrollPaymentBatch.Status.VALIDATED,
            PayrollPaymentBatch.Status.APPROVED,
        }:
            raise ValueError("Only draft, validated, or approved payment batches can be cancelled.")
        old_status = batch.status
        batch.status = PayrollPaymentBatch.Status.CANCELLED
        batch.cancelled_by_id = user_id
        batch.cancelled_at = timezone.now()
        batch.cancellation_reason = cancellation_reason
        batch.save(update_fields=["status", "cancelled_by", "cancelled_at", "cancellation_reason", "updated_at"])
        batch.lines.update(line_status=PayrollPaymentBatchLine.LineStatus.CANCELLED)
        cls._log_status(
            batch=batch,
            old_status=old_status,
            new_status=batch.status,
            user_id=user_id,
            comment=comment,
            payload={"cancellation_reason": cancellation_reason},
        )
        return batch
