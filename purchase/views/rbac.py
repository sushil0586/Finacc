from __future__ import annotations

from typing import Iterable, Optional

from rest_framework.exceptions import PermissionDenied, ValidationError

from purchase.models.purchase_core import DocType
from rbac.services import EffectivePermissionService


DOC_PERMISSION_FAMILY = {
    int(DocType.TAX_INVOICE): "purchase.invoice",
    int(DocType.CREDIT_NOTE): "purchase.credit_note",
    int(DocType.DEBIT_NOTE): "purchase.debit_note",
}


def normalize_purchase_doc_type(raw_value) -> int:
    if raw_value in (None, "", "null"):
        return int(DocType.TAX_INVOICE)
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValidationError({"detail": "doc_type must be an integer."}) from exc
    if value not in DOC_PERMISSION_FAMILY:
        raise ValidationError({"detail": "Unsupported purchase document type."})
    return value


def purchase_permission_family(doc_type: int) -> str:
    normalized = normalize_purchase_doc_type(doc_type)
    return DOC_PERMISSION_FAMILY[normalized]


def purchase_permission_codes(doc_type: int, action: str) -> list[str]:
    family = purchase_permission_family(doc_type)
    if action == "view":
        return [f"{family}.view", f"{family}.read", f"{family}.list"]
    if action == "create":
        return [f"{family}.create"]
    if action == "update":
        return [f"{family}.update", f"{family}.edit"]
    if action == "delete":
        return [f"{family}.delete"]
    if action == "post":
        return [f"{family}.post", f"{family}.confirm"]
    if action == "unpost":
        return [f"{family}.unpost"]
    if action == "cancel":
        return [f"{family}.cancel", f"{family}.update", f"{family}.edit"]
    if action in {"rebuild_tax_summary", "itc", "gstr2b"}:
        return [f"{family}.update", f"{family}.edit"]
    raise ValueError(f"Unsupported purchase permission action: {action}")


def _has_any_code(available_codes: Iterable[str], required_codes: Iterable[str]) -> bool:
    available = set(available_codes)
    return any(code in available for code in required_codes)


def require_purchase_scope_permission(*, user, entity_id: int, doc_type: int, action: str) -> None:
    entity = EffectivePermissionService.entity_for_user(user, entity_id)
    if entity is None:
        raise PermissionDenied("You do not have access to this entity.")

    required_codes = purchase_permission_codes(doc_type, action)
    available_codes = EffectivePermissionService.permission_codes_for_user(user, entity.id)
    if _has_any_code(available_codes, required_codes):
        return

    raise PermissionDenied(
        f"Missing permission for {purchase_permission_family(doc_type)} {action.replace('_', ' ')}."
    )


def require_purchase_request_permission(
    *,
    user,
    entity_id: int,
    doc_type: Optional[int],
    action: str,
) -> int:
    normalized_doc_type = normalize_purchase_doc_type(doc_type)
    require_purchase_scope_permission(
        user=user,
        entity_id=entity_id,
        doc_type=normalized_doc_type,
        action=action,
    )
    return normalized_doc_type
