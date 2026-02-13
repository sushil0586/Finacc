from __future__ import annotations

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
    ) -> dict:
        doc_type = DocumentType.objects.filter(
            module="purchase",
            doc_key=doc_key,
            is_active=True,
        ).only("id").first()

        if not doc_type:
            return {
                "enabled": False,
                "reason": f"DocumentType not found: purchase/{doc_key}",
                "doc_type_id": None,
                "current_number": None,
                "previous_number": None,
            }

        # 1) Peek current (next-to-issue) number
        try:
            res = DocumentNumberService.peek_preview(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=subentity_id,
                doc_type_id=doc_type.id,
                doc_code=doc_code,
            )
            current_no = int(res.doc_no)
        except Exception as e:
            return {
                "enabled": False,
                "reason": str(e),
                "doc_type_id": doc_type.id,
                "current_number": None,
                "previous_number": None,
            }

        # 2) Find starting_number for bounds
        series = (
            DocumentNumberSeries.objects.filter(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=subentity_id,
                doc_type_id=doc_type.id,
                doc_code=doc_code,
                is_active=True,
            )
            .only("starting_number")
            .first()
        )
        starting_number = int(getattr(series, "starting_number", 1) or 1)

        prev_candidate = current_no - 1
        previous_number = None
        previous_invoice_id = None
        previous_purchase_number = None

        # 3) Return previous only if within bounds AND invoice exists
        if prev_candidate >= starting_number:
            purchase_doc_type = PurchaseSettingsService._purchase_doc_type_from_doc_key(doc_key)

            prev_doc = (
                PurchaseInvoiceHeader.objects.filter(
                    entity_id=entity_id,
                    entityfinid_id=entityfinid_id,
                    subentity_id=subentity_id,
                    doc_type=purchase_doc_type,
                    doc_code=doc_code,
                    doc_no=prev_candidate,
                )
                .only("id", "purchase_number", "doc_no")
                .first()
            )

            if prev_doc:
                previous_number = int(prev_doc.doc_no)
                previous_invoice_id = prev_doc.id
                previous_purchase_number = prev_doc.purchase_number

        return {
            "enabled": True,
            "doc_type_id": doc_type.id,
            "current_number": current_no,

            # ✅ new
            "previous_number": previous_number,
            "previous_invoice_id": previous_invoice_id,
            "previous_purchase_number": previous_purchase_number,
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
