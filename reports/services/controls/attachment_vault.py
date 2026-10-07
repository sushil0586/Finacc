from __future__ import annotations

from copy import deepcopy
from typing import Any

from auditlogger.models import AuditLog
from financial.models import FinancialSettings
from payments.models import PaymentVoucherAttachment
from receipts.models import ReceiptVoucherAttachment
from reports.models import GstComplianceTaskAttachment
from reports.services.financial.reporting_policy import FINANCIAL_REPORTING_POLICY_DEFAULTS, _deep_merge, _sanitize
from vouchers.models import VoucherAttachment


def resolve_attachment_vault_policy(entity_id: int) -> dict[str, Any]:
    settings = FinancialSettings.objects.filter(entity_id=entity_id).only("reporting_policy").first()
    merged = _deep_merge(FINANCIAL_REPORTING_POLICY_DEFAULTS, getattr(settings, "reporting_policy", None) or {})
    return _sanitize(merged).get("attachment_vault", {})


def enforce_voucher_attachment_before_posting(header, *, message: str = "Voucher attachment is required before posting by attachment vault policy.") -> None:
    policy = resolve_attachment_vault_policy(header.entity_id)
    required_documents = policy.get("required_documents") or {}
    if not policy.get("enabled", True):
        return
    if not policy.get("require_for_posting", False):
        return
    if not required_documents.get("vouchers", False):
        return
    if not header.attachments.exists():
        raise ValueError(message)


def enforce_posted_attachment_delete_policy(header) -> None:
    policy = resolve_attachment_vault_policy(header.entity_id)
    if not policy.get("enabled", True):
        return
    if policy.get("allow_delete_after_posting", False):
        return
    if int(getattr(header, "status", 0) or 0) == 3:
        raise ValueError("Posted voucher attachments cannot be deleted by attachment vault policy.")


def record_attachment_vault_event(
    *,
    request,
    entity_id: int,
    entityfin_id: int | None = None,
    subentity_id: int | None = None,
    document_type: str,
    document_id: int,
    action: str,
    attachment_ids: list[int] | None = None,
    attachment_names: list[str] | None = None,
) -> None:
    AuditLog.objects.create(
        user=getattr(request, "user", None) if request is not None else None,
        method=getattr(request, "method", action.upper()) if request is not None else action.upper(),
        path=(
            f"/controls/attachment-vault/{document_type}/{document_id}/"
            f"?entity={entity_id}&entityfinid={entityfin_id or ''}&subentity={subentity_id or ''}"
        ),
        action=f"attachment_vault.{action}",
        new_data={
            "entity": entity_id,
            "entityfinid": entityfin_id,
            "subentity": subentity_id,
            "document_type": document_type,
            "document_id": document_id,
            "attachment_ids": attachment_ids or [],
            "attachment_names": attachment_names or [],
        },
    )


def _attachment_counts(entity_id: int) -> dict[str, int]:
    journal_count = VoucherAttachment.objects.filter(header__entity_id=entity_id).count()
    payment_count = PaymentVoucherAttachment.objects.filter(payment_voucher__entity_id=entity_id).count()
    receipt_count = ReceiptVoucherAttachment.objects.filter(receipt_voucher__entity_id=entity_id).count()
    gst_count = GstComplianceTaskAttachment.objects.filter(task__entity_id=entity_id).count()
    return {
        "journal_vouchers": journal_count,
        "payment_vouchers": payment_count,
        "receipt_vouchers": receipt_count,
        "voucher_files": journal_count + payment_count + receipt_count,
        "statutory_tasks": gst_count,
        "bank_reconciliation": 0,
        "year_end_close": 0,
        "total": journal_count + payment_count + receipt_count + gst_count,
    }


def build_missing_attachment_evidence(policy: dict[str, Any], *, entity_id: int | None = None) -> list[dict[str, Any]]:
    counts = _attachment_counts(entity_id) if entity_id else {
        "voucher_files": 0,
        "bank_reconciliation": 0,
        "year_end_close": 0,
        "statutory_tasks": 0,
    }
    required_docs = policy.get("required_documents") or {}
    checks = [
        (
            "vouchers",
            "Voucher evidence",
            counts["voucher_files"],
            "Upload at least one journal, payment, or receipt voucher attachment.",
            {"label": "Open Vouchers", "route": "/journalvoucher", "params": {"entity": entity_id, "evidence": "missing"}},
        ),
        (
            "bank_reconciliation",
            "Bank reconciliation evidence",
            counts["bank_reconciliation"],
            "Attach the bank reconciliation close evidence.",
            {"label": "Open Bank Reconciliation", "route": "/bank-reco/workspace", "params": {"entity": entity_id, "evidence": "missing"}},
        ),
        (
            "year_end_close",
            "Year-end close evidence",
            counts["year_end_close"],
            "Attach close checklist and approval evidence.",
            {"label": "Open Year-End Close", "route": "/reports/controls/year-end-close", "params": {"entity": entity_id, "focus": "evidence"}},
        ),
        (
            "statutory",
            "Statutory evidence",
            counts["statutory_tasks"],
            "Attach statutory compliance task evidence.",
            {"label": "Open GST Center", "route": "/reports/compliance/gst-compliance-center", "params": {"entity": entity_id, "evidence": "missing"}},
        ),
    ]
    return [
        {
            "key": key,
            "label": label,
            "status": "missing",
            "required": True,
            "available_count": count,
            "detail": detail,
            "action": action,
        }
        for key, label, count, detail, action in checks
        if required_docs.get(key, False) and int(count or 0) == 0
    ]


def summarize_attachment_vault_policy(policy: dict[str, Any], *, entity_id: int | None = None) -> list[dict[str, Any]]:
    counts = _attachment_counts(entity_id) if entity_id else {"total": 0, "voucher_files": 0, "receipt_vouchers": 0, "statutory_tasks": 0}
    required_docs = policy.get("required_documents") or {}
    required_count = sum(1 for value in required_docs.values() if value)
    return [
        {"label": "Attachments", "value": counts["total"], "note": "Indexed control attachments.", "tone": "accent" if counts["total"] else "warning"},
        {"label": "Voucher files", "value": counts["voucher_files"], "note": "Journal, payment, and receipt evidence files.", "tone": "accent" if counts["voucher_files"] else "warning"},
        {"label": "Receipt files", "value": counts["receipt_vouchers"], "note": "Receipt voucher evidence files.", "tone": "neutral"},
        {"label": "Statutory files", "value": counts["statutory_tasks"], "note": "GST compliance task files.", "tone": "neutral"},
        {"label": "Required docs", "value": required_count, "note": "Document classes required by policy.", "tone": "accent" if required_count else "warning"},
        {"label": "Max file MB", "value": policy.get("max_file_mb") or 10, "note": "Per-file upload control.", "tone": "neutral"},
    ]


def build_attachment_vault_readiness(entity_id: int) -> dict[str, Any]:
    policy = resolve_attachment_vault_policy(entity_id)
    summary_cards = summarize_attachment_vault_policy(policy, entity_id=entity_id)
    missing_evidence = build_missing_attachment_evidence(policy, entity_id=entity_id)
    attachment_count = int(summary_cards[0]["value"] or 0)
    required_count = int(next((card["value"] for card in summary_cards if card["label"] == "Required docs"), 0) or 0)
    if not policy.get("enabled", True):
        status = "review"
        status_label = "Disabled"
    elif required_count == 0:
        status = "blocked"
        status_label = "No Required Docs"
    elif missing_evidence:
        status = "blocked"
        status_label = "Evidence Missing"
    elif attachment_count == 0:
        status = "review"
        status_label = "No Files"
    else:
        status = "ready"
        status_label = "Indexed"
    return {
        "status": status,
        "status_label": status_label,
        "summary_cards": summary_cards,
        "policy": policy,
        "missing_evidence": missing_evidence,
        "actions": [{"label": "Review Attachment Vault", "route": "/reports/controls/phase-one", "params": {}}],
    }


def update_attachment_vault_policy(*, entity_id: int, updates: dict[str, Any], created_by=None) -> dict[str, Any]:
    settings, _ = FinancialSettings.objects.get_or_create(
        entity_id=entity_id,
        defaults={"createdby": created_by, "reporting_policy": deepcopy(FINANCIAL_REPORTING_POLICY_DEFAULTS)},
    )
    policy = deepcopy(settings.reporting_policy or {})
    attachments = dict(policy.get("attachment_vault") or {})
    for key in ("enabled", "require_for_posting", "allow_delete_after_posting"):
        if key in updates:
            attachments[key] = bool(updates.get(key))
    if "max_file_mb" in updates:
        attachments["max_file_mb"] = updates.get("max_file_mb")
    if "required_documents" in updates and isinstance(updates.get("required_documents"), dict):
        attachments["required_documents"] = updates.get("required_documents")
    policy["attachment_vault"] = attachments
    settings.reporting_policy = _sanitize(policy)
    if not getattr(settings, "createdby_id", None) and created_by is not None:
        settings.createdby = created_by
    settings.save(update_fields=["reporting_policy", "updated_at"] if hasattr(settings, "updated_at") else ["reporting_policy"])
    return resolve_attachment_vault_policy(entity_id)
