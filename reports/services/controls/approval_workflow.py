from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
from typing import Any

from auditlogger.models import AuditLog
from financial.models import FinancialSettings
from reports.services.financial.reporting_policy import FINANCIAL_REPORTING_POLICY_DEFAULTS, _deep_merge, _sanitize


def resolve_approval_workflow_policy(entity_id: int) -> dict[str, Any]:
    settings = FinancialSettings.objects.filter(entity_id=entity_id).only("reporting_policy").first()
    configured = bool(getattr(settings, "reporting_policy", None) and "approval_workflow" in (settings.reporting_policy or {}))
    merged = _deep_merge(FINANCIAL_REPORTING_POLICY_DEFAULTS, getattr(settings, "reporting_policy", None) or {})
    policy = _sanitize(merged).get("approval_workflow", {})
    policy["_configured"] = configured
    return policy


def _approval_queue_counts(entity_id: int) -> dict[str, int]:
    from payments.models import PaymentVoucherHeader
    from receipts.models import ReceiptVoucherHeader
    from vouchers.models import VoucherHeader

    models = (VoucherHeader, PaymentVoucherHeader, ReceiptVoucherHeader)
    counts = {"pending": 0, "rejected": 0}
    for model in models:
        for payload in model.objects.filter(entity_id=entity_id).exclude(workflow_payload={}).values_list("workflow_payload", flat=True):
            state = (payload or {}).get("_approval_state") or {}
            status = str(state.get("status") or "").upper()
            if status == "SUBMITTED":
                counts["pending"] += 1
            elif status == "REJECTED":
                counts["rejected"] += 1
    return counts


def _workflow_state(payload: dict[str, Any] | None) -> dict[str, Any]:
    return (payload or {}).get("_approval_state") or {}


def _voucher_action(document_type: str, row_id: int, status: str) -> dict[str, Any]:
    routes = {
        "journal": "/journalvoucher",
        "cash": "/cashvoucher",
        "bank": "/bankvoucher",
        "payment": "/paymentvoucher",
        "receipt": "/receiptvoucher",
    }
    return {
        "label": "Review Voucher" if status == "SUBMITTED" else "Fix Rejected",
        "route": routes.get(document_type, "/journalvoucher"),
        "params": {"voucher_id": row_id, "approval_status": status.lower()},
    }


def build_approval_queue(entity_id: int, *, limit: int = 10) -> list[dict[str, Any]]:
    from payments.models import PaymentVoucherHeader
    from receipts.models import ReceiptVoucherHeader
    from vouchers.models import VoucherHeader

    rows: list[dict[str, Any]] = []
    sources = [
        (VoucherHeader, "journal", "Journal Voucher", "total_debit_amount"),
        (PaymentVoucherHeader, "payment", "Payment Voucher", "settlement_effective_amount"),
        (ReceiptVoucherHeader, "receipt", "Receipt Voucher", "settlement_effective_amount"),
    ]
    for model, document_type, label, amount_field in sources:
        queryset = model.objects.filter(entity_id=entity_id).exclude(workflow_payload={}).order_by("-updated_at", "-id")[:limit]
        for row in queryset:
            state = _workflow_state(row.workflow_payload)
            status = str(state.get("status") or "").upper()
            if status not in {"SUBMITTED", "REJECTED"}:
                continue
            rows.append(
                {
                    "id": row.id,
                    "document_type": document_type,
                    "document_label": label,
                    "document_no": getattr(row, "voucher_code", None) or f"{getattr(row, 'doc_code', '')}-{getattr(row, 'doc_no', '')}".strip("-") or str(row.id),
                    "status": status.lower(),
                    "submitted_by": state.get("submitted_by"),
                    "approved_by": state.get("approved_by"),
                    "rejected_by": state.get("rejected_by"),
                    "submitted_at": state.get("submitted_at"),
                    "rejected_at": state.get("rejected_at"),
                    "approver_role": state.get("approver_role"),
                    "required_approvals": state.get("required_approvals") or 1,
                    "threshold_name": state.get("threshold_name"),
                    "amount": str(_to_decimal(getattr(row, amount_field, None))),
                    "detail": state.get("remarks") or ("Waiting for approval." if status == "SUBMITTED" else "Rejected voucher needs correction."),
                    "action": _voucher_action(document_type, row.id, status),
                }
            )
    priority = {"rejected": 0, "submitted": 1}
    rows.sort(key=lambda item: (priority.get(item["status"], 2), item.get("submitted_at") or item.get("rejected_at") or ""), reverse=False)
    return rows[:limit]


def summarize_approval_workflow_policy(policy: dict[str, Any], *, entity_id: int | None = None) -> list[dict[str, Any]]:
    docs = policy.get("document_types") or {}
    enabled_docs = sum(1 for value in docs.values() if value)
    thresholds = policy.get("thresholds") or []
    queue_counts = _approval_queue_counts(entity_id) if entity_id else {"pending": 0, "rejected": 0}
    return [
        {"label": "Mode", "value": policy.get("mode") or "maker_checker", "note": "Approval enforcement mode.", "tone": "neutral"},
        {"label": "Pending", "value": queue_counts["pending"], "note": "Submitted vouchers waiting for approval.", "tone": "warning" if queue_counts["pending"] else "accent"},
        {"label": "Rejected", "value": queue_counts["rejected"], "note": "Rejected vouchers needing correction.", "tone": "warning" if queue_counts["rejected"] else "neutral"},
        {"label": "Documents", "value": enabled_docs, "note": "Document types covered by approval.", "tone": "accent" if enabled_docs else "warning"},
        {"label": "Thresholds", "value": len(thresholds), "note": "Amount bands configured.", "tone": "neutral"},
        {"label": "Approver role", "value": policy.get("default_approver_role") or "finance_manager", "note": "Fallback reviewer role.", "tone": "neutral"},
        {"label": "Reject comment", "value": "Required" if policy.get("require_comment_on_reject") else "Optional", "note": "Controls rejection audit quality.", "tone": "neutral"},
    ]


def _to_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0.00"))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0.00")


def _document_enabled(policy: dict[str, Any], document_type: str) -> bool:
    if not policy.get("_configured", False):
        return False
    if not policy.get("enabled", True) or policy.get("mode") == "none":
        return False
    return bool((policy.get("document_types") or {}).get(document_type, False))


def _amount_for_header(header: Any, document_type: str) -> Decimal:
    if document_type in {"journal", "cash", "bank"}:
        return _to_decimal(getattr(header, "total_debit_amount", None) or getattr(header, "total_credit_amount", None))
    if document_type == "payment":
        return _to_decimal(getattr(header, "settlement_effective_amount", None) or getattr(header, "cash_paid_amount", None))
    if document_type == "receipt":
        return _to_decimal(getattr(header, "settlement_effective_amount", None) or getattr(header, "cash_received_amount", None))
    return Decimal("0.00")


def _threshold_for_amount(policy: dict[str, Any], amount: Decimal) -> dict[str, Any] | None:
    for threshold in policy.get("thresholds") or []:
        amount_from = _to_decimal(threshold.get("amount_from"))
        amount_to = threshold.get("amount_to")
        upper = _to_decimal(amount_to) if amount_to not in (None, "") else None
        if amount >= amount_from and (upper is None or amount <= upper):
            return threshold
    return None


def approval_submission_metadata(*, entity_id: int, document_type: str, amount: Any) -> dict[str, Any]:
    policy = resolve_approval_workflow_policy(entity_id)
    if not _document_enabled(policy, document_type):
        return {"approval_required": False}
    threshold = _threshold_for_amount(policy, _to_decimal(amount)) if policy.get("mode") == "threshold" else None
    return {
        "approval_required": True,
        "approval_mode": policy.get("mode") or "maker_checker",
        "approver_role": (threshold or {}).get("approver_role") or policy.get("default_approver_role") or "finance_manager",
        "required_approvals": int((threshold or {}).get("required_approvals") or 1),
        "threshold_name": (threshold or {}).get("name"),
    }


def record_approval_workflow_event(
    *,
    entity_id: int,
    entityfin_id: int | None = None,
    subentity_id: int | None = None,
    document_type: str,
    document_id: int,
    action: str,
    actor_id: int | None = None,
    workflow_state: dict[str, Any] | None = None,
    remarks: str | None = None,
) -> None:
    AuditLog.objects.create(
        user_id=actor_id,
        method="SYSTEM",
        path=(
            f"/controls/approval-workflow/{document_type}/{document_id}/"
            f"?entity={entity_id}&entityfinid={entityfin_id or ''}&subentity={subentity_id or ''}"
        ),
        action=f"approval_workflow.{action}",
        new_data={
            "entity": entity_id,
            "entityfinid": entityfin_id,
            "subentity": subentity_id,
            "document_type": document_type,
            "document_id": document_id,
            "workflow_state": workflow_state or {},
            "remarks": remarks,
        },
    )


def enforce_approval_before_approve(*, header: Any, document_type: str, workflow_state: dict[str, Any], approved_by_id: int | None) -> None:
    policy = resolve_approval_workflow_policy(header.entity_id)
    if not _document_enabled(policy, document_type):
        return
    if workflow_state.get("status") != "SUBMITTED":
        raise ValueError("Voucher must be submitted before approval by approval workflow policy.")
    submitted_by = workflow_state.get("submitted_by")
    if submitted_by and approved_by_id and int(submitted_by) == int(approved_by_id):
        raise ValueError("Approver must be different from submitter by approval workflow policy.")


def enforce_approval_before_reject(*, header: Any, document_type: str, remarks: str | None) -> None:
    policy = resolve_approval_workflow_policy(header.entity_id)
    if not _document_enabled(policy, document_type):
        return
    if policy.get("require_comment_on_reject", True) and not str(remarks or "").strip():
        raise ValueError("Rejection comment is required by approval workflow policy.")


def enforce_approval_before_posting(*, header: Any, document_type: str, workflow_state: dict[str, Any]) -> None:
    policy = resolve_approval_workflow_policy(header.entity_id)
    if not _document_enabled(policy, document_type):
        return
    if workflow_state.get("status") != "APPROVED":
        raise ValueError("Voucher must be approved before posting by approval workflow policy.")


def build_approval_workflow_readiness(entity_id: int) -> dict[str, Any]:
    policy = resolve_approval_workflow_policy(entity_id)
    docs = policy.get("document_types") or {}
    enabled_docs = sum(1 for value in docs.values() if value)
    queue_counts = _approval_queue_counts(entity_id)
    if not policy.get("enabled", True) or policy.get("mode") == "none":
        status = "review"
        status_label = "Disabled"
    elif not enabled_docs:
        status = "blocked"
        status_label = "No Documents"
    elif queue_counts["rejected"]:
        status = "blocked"
        status_label = "Rejected Items"
    elif queue_counts["pending"]:
        status = "review"
        status_label = "Pending Approval"
    elif policy.get("mode") == "threshold" and not policy.get("thresholds"):
        status = "review"
        status_label = "Thresholds Needed"
    else:
        status = "ready"
        status_label = "Configured"
    return {
        "status": status,
        "status_label": status_label,
        "summary_cards": summarize_approval_workflow_policy(policy, entity_id=entity_id),
        "policy": policy,
        "queue": build_approval_queue(entity_id),
        "actions": [{"label": "Review Approval Workflow", "route": "/reports/controls/phase-one", "params": {}}],
    }


def update_approval_workflow_policy(*, entity_id: int, updates: dict[str, Any], created_by=None) -> dict[str, Any]:
    settings, _ = FinancialSettings.objects.get_or_create(
        entity_id=entity_id,
        defaults={"createdby": created_by, "reporting_policy": deepcopy(FINANCIAL_REPORTING_POLICY_DEFAULTS)},
    )
    policy = deepcopy(settings.reporting_policy or {})
    approval = dict(policy.get("approval_workflow") or {})
    for key in ("enabled", "require_comment_on_reject"):
        if key in updates:
            approval[key] = bool(updates.get(key))
    for key in ("mode", "default_approver_role"):
        if key in updates:
            approval[key] = str(updates.get(key) or "").strip().lower()
    if "document_types" in updates and isinstance(updates.get("document_types"), dict):
        approval["document_types"] = updates.get("document_types")
    if "thresholds" in updates and isinstance(updates.get("thresholds"), list):
        approval["thresholds"] = updates.get("thresholds")
    policy["approval_workflow"] = approval
    settings.reporting_policy = _sanitize(policy)
    if not getattr(settings, "createdby_id", None) and created_by is not None:
        settings.createdby = created_by
    settings.save(update_fields=["reporting_policy", "updated_at"] if hasattr(settings, "updated_at") else ["reporting_policy"])
    return resolve_approval_workflow_policy(entity_id)
