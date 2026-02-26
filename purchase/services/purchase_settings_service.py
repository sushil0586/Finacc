from __future__ import annotations
from typing import Optional, Dict, Any

from dataclasses import dataclass
from datetime import date
from typing import Optional, Dict, Tuple
from numbering.models import DocumentType, DocumentNumberSeries

from purchase.models.purchase_core import PurchaseInvoiceHeader, DocType

from django.db.models import Q
from numbering.models import DocumentType
from numbering.services.document_number_service import DocumentNumberService  # adjust import

from purchase.models.purchase_config import (
    PurchaseSettings,
    PurchaseLockPeriod,
    PurchaseChoiceOverride,
)


@dataclass(frozen=True)
class PurchasePolicy:
    settings: PurchaseSettings

    @property
    def default_action(self) -> str:
        return self.settings.default_workflow_action

    @property
    def round_decimals(self) -> int:
        return int(self.settings.round_grand_total_to or 2)

    @property
    def enable_round_off(self) -> bool:
        return bool(self.settings.enable_round_off)

    @property
    def allow_mixed_taxability(self) -> bool:
        return bool(self.settings.allow_mixed_taxability_in_one_bill)

    @property
    def enforce_2b_before_itc_claim(self) -> bool:
        return bool(self.settings.enforce_2b_before_itc_claim)

    @property
    def auto_derive_tax_regime(self) -> bool:
        return bool(self.settings.auto_derive_tax_regime)


class PurchaseSettingsService:

    @staticmethod
    def _purchase_doc_type_from_doc_key(doc_key: str) -> int:
        """
        Map DocumentType.doc_key to PurchaseInvoiceHeader.DocType
        """
        k = (doc_key or "").upper()
        if "CREDIT" in k:
            return int(DocType.CREDIT_NOTE)
        if "DEBIT" in k:
            return int(DocType.DEBIT_NOTE)
        return int(DocType.TAX_INVOICE)

    @staticmethod
    def get_current_doc_no(
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        doc_key: str,
        doc_code: str,
    ) -> Dict[str, Any]:
        """
        - current_number: preview (next-to-issue) from numbering series (uses doc_code)
        - previous_*: last saved invoice by ID for given entity + FY + subentity + doc_type
                     (ignores doc_code and status)
        """

        # 1) Find DocumentType row (for numbering preview)
        doc_type_row = (
            DocumentType.objects.filter(
                module="purchase",
                doc_key=doc_key,
                is_active=True,
            )
            .only("id")
            .first()
        )

        if not doc_type_row:
            return {
                "enabled": False,
                "reason": f"DocumentType not found: purchase/{doc_key}",
                "doc_type_id": None,
                "current_number": None,
                "previous_number": None,
                "previous_invoice_id": None,
                "previous_purchase_number": None,
                "previous_status": None,
                "previous_bill_date": None,
            }

        # 2) Peek current (next-to-issue) number (still uses doc_code)
        try:
            res = DocumentNumberService.peek_preview(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=subentity_id,
                doc_type_id=doc_type_row.id,
                doc_code=doc_code,
            )
            current_no = int(res.doc_no)
        except Exception as e:
            return {
                "enabled": False,
                "reason": str(e),
                "doc_type_id": doc_type_row.id,
                "current_number": None,
                "previous_number": None,
                "previous_invoice_id": None,
                "previous_purchase_number": None,
                "previous_status": None,
                "previous_bill_date": None,
            }

        # 3) Get PurchaseInvoiceHeader doc_type enum value from doc_key
        purchase_doc_type = PurchaseSettingsService._purchase_doc_type_from_doc_key(doc_key)

        # 4) Previous = last saved row by id (scope: entity, FY, subentity, doc_type ONLY)
        inv_filters = dict(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            doc_type=purchase_doc_type,
        )
        if subentity_id is None:
            inv_filters["subentity__isnull"] = True
        else:
            inv_filters["subentity_id"] = subentity_id

        prev_doc = (
            PurchaseInvoiceHeader.objects.filter(**inv_filters)
            .only("id", "purchase_number", "doc_no", "status", "bill_date")
            .order_by("-id")
            .first()
        )

        return {
            "enabled": True,
            "doc_type_id": doc_type_row.id,
            "current_number": current_no,

            # ✅ previous from last saved record (any status)
            "previous_number": int(prev_doc.doc_no) if (prev_doc and prev_doc.doc_no is not None) else None,
            "previous_invoice_id": prev_doc.id if prev_doc else None,
            "previous_purchase_number": prev_doc.purchase_number if prev_doc else None,
            "previous_status": int(prev_doc.status) if prev_doc else None,
            "previous_bill_date": prev_doc.bill_date if prev_doc else None,
        }
    @staticmethod
    def get_settings(entity_id: int, subentity_id: Optional[int]) -> PurchaseSettings:
        """
        Prefer entity+subentity row. Fallback to entity-only row (subentity NULL).
        """
        s = PurchaseSettings.objects.filter(
            entity_id=entity_id, subentity_id=subentity_id
        ).first()
        if s:
            return s

        s = PurchaseSettings.objects.filter(
            entity_id=entity_id, subentity__isnull=True
        ).first()
        if s:
            return s

        # Create default row (optional) OR raise. I suggest auto-create default.
        return PurchaseSettings.objects.create(entity_id=entity_id, subentity_id=subentity_id)

    @staticmethod
    def get_policy(entity_id: int, subentity_id: Optional[int]) -> PurchasePolicy:
        return PurchasePolicy(settings=PurchaseSettingsService.get_settings(entity_id, subentity_id))

    # ----------------------------
    # Lock period enforcement
    # ----------------------------
    @staticmethod
    def is_locked(entity_id: int, subentity_id: Optional[int], bill_date: date) -> Tuple[bool, Optional[str]]:
        """
        Locked if there is any lock_date >=? rule:
          - if bill_date <= lock_date => locked
        Prefer subentity-specific lock, else entity-level lock.
        """
        lock = (
            PurchaseLockPeriod.objects
            .filter(entity_id=entity_id, subentity_id=subentity_id, lock_date__gte=bill_date)
            .order_by("-lock_date")
            .first()
        )
        if lock:
            return True, (lock.reason or f"Locked up to {lock.lock_date}")

        lock = (
            PurchaseLockPeriod.objects
            .filter(entity_id=entity_id, subentity__isnull=True, lock_date__gte=bill_date)
            .order_by("-lock_date")
            .first()
        )
        if lock:
            return True, (lock.reason or f"Locked up to {lock.lock_date}")

        return False, None

    # ----------------------------
    # Choice override helpers
    # ----------------------------
    @staticmethod
    def get_choice_overrides(entity_id: int, subentity_id: Optional[int]) -> Dict[str, Dict[str, dict]]:
        """
        Return:
          {
            "SupplyCategory": {
               "SEZ": {"is_enabled": false, "override_label": "SEZ Purchase (Disabled)"}
            }
          }
        """
        qs = PurchaseChoiceOverride.objects.filter(
            entity_id=entity_id
        ).filter(
            Q(subentity_id=subentity_id) | Q(subentity__isnull=True)
        )

        out: Dict[str, Dict[str, dict]] = {}
        for r in qs:
            out.setdefault(r.choice_group, {})
            out[r.choice_group][r.choice_key] = {
                "is_enabled": bool(r.is_enabled),
                "override_label": r.override_label,
            }
        return out
