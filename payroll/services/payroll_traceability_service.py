from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Count, Sum

from payroll.models import PayrollRun, PayrollRunActionLog, Payslip
from payroll.services.payroll_posting_verification_service import PayrollPostingVerificationService
from posting.models import Entry, TxnType

ZERO2 = Decimal("0.00")
Q2 = Decimal("0.01")


def q2(value) -> Decimal:
    try:
        return Decimal(value or 0).quantize(Q2, rounding=ROUND_HALF_UP)
    except Exception:
        return ZERO2


class PayrollTraceabilityService:
    EVENT_META = {
        PayrollRunActionLog.Action.CREATED: ("created", "lifecycle", "Payroll run created"),
        PayrollRunActionLog.Action.CALCULATED: ("calculated", "lifecycle", "Payroll calculated"),
        PayrollRunActionLog.Action.SUBMITTED: ("submitted", "approval", "Payroll submitted"),
        PayrollRunActionLog.Action.APPROVED: ("approved", "approval", "Payroll approved"),
        PayrollRunActionLog.Action.POSTED: ("posted", "posting", "Payroll posted"),
        PayrollRunActionLog.Action.PAYMENT_HANDED_OFF: ("payment_handoff", "payment", "Payroll handed off for payment"),
        PayrollRunActionLog.Action.PAYMENT_FAILED: ("payment_failed", "payment", "Payroll payment failed"),
        PayrollRunActionLog.Action.DISBURSED: ("payment_disbursed", "payment", "Payroll payment disbursed"),
        PayrollRunActionLog.Action.RECONCILED: ("payment_reconciled", "payment", "Payroll payment reconciled"),
        PayrollRunActionLog.Action.CANCELLED: ("cancelled", "lifecycle", "Payroll cancelled"),
        PayrollRunActionLog.Action.REVERSED: ("reversed", "reversal", "Payroll reversed"),
    }

    COMPONENT_CATEGORY_MAP = {
        "EARNING": "earning",
        "DEDUCTION": "deduction",
        "EMPLOYER_CONTRIBUTION": "employer_contribution",
    }

    @staticmethod
    def _user_ref(user):
        if not user:
            return None
        name = (
            getattr(user, "get_full_name", lambda: "")()  # type: ignore[misc]
            or getattr(user, "name", "")
            or getattr(user, "username", "")
            or getattr(user, "email", "")
            or str(user)
        )
        return {
            "user_id": user.id,
            "user_name": name,
        }

    @staticmethod
    def _run_reference(run: PayrollRun | None) -> str | None:
        if not run:
            return None
        return run.run_number or f"{run.doc_code}-{run.doc_no or run.id}"

    @staticmethod
    def _payload_alias(payload: dict | None, *keys: str):
        if not payload:
            return None
        for key in keys:
            value = payload.get(key)
            if value not in (None, "", []):
                return value
        return None

    @classmethod
    def _payment_actor(cls, run: PayrollRun):
        payment_log = (
            run.action_logs.filter(
                action__in=[
                    PayrollRunActionLog.Action.PAYMENT_HANDED_OFF,
                    PayrollRunActionLog.Action.PAYMENT_FAILED,
                    PayrollRunActionLog.Action.DISBURSED,
                    PayrollRunActionLog.Action.RECONCILED,
                ]
            )
            .select_related("acted_by")
            .order_by("-created_at", "-id")
            .first()
        )
        return cls._user_ref(payment_log.acted_by) if payment_log else None

    @staticmethod
    def _posting_entry(run: PayrollRun):
        if not run.posted_entry_id:
            return None
        return Entry.objects.filter(
            id=run.posted_entry_id,
            entity_id=run.entity_id,
            entityfin_id=run.entityfinid_id,
            subentity_id=run.subentity_id,
            txn_type=TxnType.PAYROLL,
        ).first()

    @staticmethod
    def _payment_verification_issues(run: PayrollRun) -> list[dict]:
        issues = []
        if run.payment_status == PayrollRun.PaymentStatus.HANDED_OFF and not run.payment_batch_ref:
            issues.append(
                {
                    "code": "PAYMENT_BATCH_REFERENCE_MISSING",
                    "severity": "warning",
                    "message": "Payroll was handed off to payments but batch reference is missing.",
                }
            )
        if run.payment_status in {PayrollRun.PaymentStatus.DISBURSED, PayrollRun.PaymentStatus.RECONCILED} and not run.payment_handed_off_at:
            issues.append(
                {
                    "code": "PAYMENT_HANDOFF_TIMESTAMP_MISSING",
                    "severity": "warning",
                    "message": "Payment status progressed beyond handoff but handoff timestamp is missing.",
                }
            )
        if run.payment_status == PayrollRun.PaymentStatus.RECONCILED and not run.payment_reconciled_at:
            issues.append(
                {
                    "code": "PAYMENT_RECONCILED_TIMESTAMP_MISSING",
                    "severity": "warning",
                    "message": "Payment is marked reconciled but reconciliation timestamp is missing.",
                }
            )
        return issues

    @classmethod
    def build_actor_summary(cls, *, run: PayrollRun) -> dict:
        action_logs = {log.action: log for log in run.action_logs.select_related("acted_by").all()}
        calculated_log = action_logs.get(PayrollRunActionLog.Action.CALCULATED)
        payment_log = (
            run.action_logs.filter(
                action__in=[
                    PayrollRunActionLog.Action.PAYMENT_HANDED_OFF,
                    PayrollRunActionLog.Action.PAYMENT_FAILED,
                    PayrollRunActionLog.Action.DISBURSED,
                    PayrollRunActionLog.Action.RECONCILED,
                ]
            )
            .select_related("acted_by")
            .order_by("-created_at", "-id")
            .first()
        )
        return {
            "created_by": cls._user_ref(run.created_by),
            "calculated_by": cls._user_ref(calculated_log.acted_by) if calculated_log else None,
            "submitted_by": cls._user_ref(run.submitted_by),
            "approved_by": cls._user_ref(run.approved_by),
            "posted_by": cls._user_ref(run.posted_by),
            "payment_processed_by": cls._user_ref(payment_log.acted_by) if payment_log else None,
            "reversed_by": cls._user_ref(run.reversed_by),
        }

    @classmethod
    def build_timeline(cls, *, run: PayrollRun) -> list[dict]:
        timeline = []
        for log in run.action_logs.select_related("acted_by").all().order_by("created_at", "id"):
            event_type, event_group, label = cls.EVENT_META.get(log.action, (log.action.lower(), "lifecycle", log.action.title()))
            reference = None
            if log.action == PayrollRunActionLog.Action.POSTED:
                reference = run.post_reference or cls._payload_alias(log.payload, "posting_reference", "voucher_reference")
            elif log.action == PayrollRunActionLog.Action.PAYMENT_HANDED_OFF:
                reference = run.payment_batch_ref or cls._payload_alias(run.payment_handoff_payload, "handoff_reference")
            elif log.action == PayrollRunActionLog.Action.REVERSED:
                reference = cls._run_reference(run.reversal_runs.order_by("-id").first())
            timeline.append(
                {
                    "event_type": event_type,
                    "event_group": event_group,
                    "label": label,
                    "occurred_at": log.created_at,
                    "actor": cls._user_ref(log.acted_by),
                    "reference": reference,
                    "notes": log.comment or None,
                }
            )
        return timeline

    @classmethod
    def build_component_totals(cls, *, run: PayrollRun) -> list[dict]:
        rows = (
            run.employee_runs.values(
                "components__component_id",
                "components__component_code",
                "components__component_name",
                "components__component_type",
            )
            .annotate(
                amount=Sum("components__amount"),
                employee_count=Count("employee_profile_id", distinct=True),
            )
            .order_by("components__component_code", "components__component_id")
        )
        totals = []
        for row in rows:
            if not row["components__component_code"]:
                continue
            totals.append(
                {
                    "component_id": row["components__component_id"],
                    "component_code": row["components__component_code"],
                    "component_name": row["components__component_name"],
                    "category": cls.COMPONENT_CATEGORY_MAP.get(row["components__component_type"]),
                    "amount": q2(row["amount"]),
                    "employee_count": row["employee_count"],
                }
            )
        return totals

    @classmethod
    def build_employee_issue_summary(cls, *, row) -> dict:
        warnings = []
        blockers = []

        if row.status in {row.Status.HOLD, row.Status.SKIPPED}:
            blockers.append("Employee row is not active for payroll processing.")
        if not row.salary_structure_version_id:
            blockers.append("Salary structure version snapshot is missing.")
        if not row.ledger_policy_version_id:
            blockers.append("Ledger policy snapshot is missing.")
        if not getattr(row.employee_profile, "payment_account_id", None):
            warnings.append("Payment account is missing on payroll profile.")

        missing_posting_count = sum(
            1 for component in row.components.all() if component.component_type != "MEMO_ONLY" and component.component_posting_version_id is None
        )
        if missing_posting_count:
            warnings.append(f"{missing_posting_count} payroll component rows do not have posting version snapshots.")
        if row.payment_status == PayrollRun.PaymentStatus.FAILED:
            warnings.append("Payment status is failed for this employee row.")

        return {
            "warning_count": len(warnings),
            "blocking_issue_count": len(blockers),
            "issue_messages": (blockers + warnings)[:5],
        }

    @classmethod
    def build_employee_rows(cls, *, run: PayrollRun) -> list[dict]:
        rows = []
        for row in run.employee_runs.select_related("employee_profile", "salary_structure").prefetch_related("components").all():
            issue_summary = cls.build_employee_issue_summary(row=row)
            rows.append(
                {
                    "id": row.id,
                    "payroll_profile_id": row.employee_profile_id,
                    "employee_id": getattr(row.employee_profile, "employee_user_id", None),
                    "employee_code": row.employee_profile.employee_code,
                    "employee_name": row.employee_profile.full_name,
                    "salary_structure_id": row.salary_structure_id,
                    "payment_status": row.payment_status,
                    "gross_amount": row.gross_amount,
                    "deduction_amount": row.deduction_amount,
                    "employer_contribution_amount": row.employer_contribution_amount,
                    "payable_amount": row.payable_amount,
                    **issue_summary,
                }
            )
        return rows

    @classmethod
    def build_traceability(cls, *, run: PayrollRun) -> dict:
        posting_entry = cls._posting_entry(run)
        posting_verification = PayrollPostingVerificationService.verify_run_posting(run=run)
        posting_issues = [
            {
                "code": issue.code.upper(),
                "severity": issue.severity.value,
                "message": issue.message,
            }
            for issue in posting_verification.issues
        ]
        payment_issues = cls._payment_verification_issues(run)
        reversing_run = run.reversal_runs.order_by("-id").first()
        original_run = run.reversed_run if run.reversed_run_id else None

        if original_run:
            reversal_status = "reversal_run"
        elif reversing_run or run.status == PayrollRun.Status.REVERSED:
            reversal_status = "reversed"
        else:
            reversal_status = "not_reversed"

        return {
            "run": {
                "run_id": run.id,
                "run_code": cls._run_reference(run),
                "entity_id": run.entity_id,
                "entity_name": getattr(run.entity, "entityname", "") if hasattr(run, "entity") else "",
                "financial_year_id": run.entityfinid_id,
                "financial_year_name": getattr(run.entityfinid, "desc", "") if hasattr(run, "entityfinid") else "",
                "period_id": run.payroll_period_id,
                "period_name": getattr(run.payroll_period, "code", "") if hasattr(run, "payroll_period") else "",
                "subentity_id": run.subentity_id,
                "subentity_name": getattr(run.subentity, "subentityname", "") if getattr(run, "subentity_id", None) else None,
            },
            "posting": {
                "status": "posted" if run.posted_entry_id else "not_posted",
                "posting_reference": run.post_reference or (posting_entry.voucher_no if posting_entry else None),
                "posting_entry_id": run.posted_entry_id,
                "voucher_reference": posting_entry.voucher_no if posting_entry else run.post_reference or None,
                "posted_at": run.posted_at or (posting_entry.posted_at if posting_entry else None),
                "posted_by": cls._user_ref(run.posted_by),
                "verification_issues": posting_issues,
            },
            "payment": {
                "status": run.payment_status.lower(),
                "handoff_reference": run.payment_batch_ref or cls._payload_alias(run.payment_handoff_payload, "handoff_reference", "batch_ref"),
                "reconciliation_reference": cls._payload_alias(
                    run.payment_handoff_payload,
                    "reconciliation_reference",
                    "reconciliation_reference_id",
                    "reconciliation_ref",
                ),
                "handoff_at": run.payment_handed_off_at,
                "reconciled_at": run.payment_reconciled_at,
                "processed_by": cls._payment_actor(run),
                "notes": [issue["message"] for issue in payment_issues],
                "verification_issues": payment_issues,
            },
            "reversal": {
                "status": reversal_status,
                "original_run_id": original_run.id if original_run else None,
                "original_run_reference": cls._run_reference(original_run),
                "reversing_run_id": reversing_run.id if reversing_run else None,
                "reversing_run_reference": cls._run_reference(reversing_run),
                "reversed_at": run.reversed_at or (original_run.reversed_at if original_run else None),
                "reversed_by": cls._user_ref(run.reversed_by or (original_run.reversed_by if original_run else None)),
                "reason": run.reversal_reason or (original_run.reversal_reason if original_run else None) or None,
                "reversal_posting_reference": (
                    (reversing_run.post_reference if reversing_run else None)
                    or (run.post_reference if original_run else None)
                ),
            },
        }

    @classmethod
    def build_payslip_sections(cls, *, payslip: Payslip) -> dict:
        row = payslip.payroll_run_employee
        earnings = []
        deductions = []
        employer_contributions = []

        for component in row.components.all():
            item = {
                "component_id": component.component_id,
                "component_code": component.component_code,
                "component_name": component.component_name,
                "amount": component.amount,
                "metadata": component.metadata,
            }
            if component.component_type in {"EARNING", "REIMBURSEMENT"}:
                earnings.append(item)
            elif component.component_type in {"DEDUCTION", "RECOVERY"}:
                deductions.append(item)
            elif component.component_type == "EMPLOYER_CONTRIBUTION":
                employer_contributions.append(item)

        return {
            "earnings": earnings,
            "deductions": deductions,
            "employer_contributions": employer_contributions,
            "section_totals": {
                "earnings": q2(sum((item["amount"] for item in earnings), ZERO2)),
                "deductions": q2(sum((item["amount"] for item in deductions), ZERO2)),
                "employer_contributions": q2(sum((item["amount"] for item in employer_contributions), ZERO2)),
            },
        }
