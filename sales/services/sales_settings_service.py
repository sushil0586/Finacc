from __future__ import annotations

from dataclasses import dataclass
from entity.models import Entity, SubEntity  # adjust import paths

from datetime import date
from typing import Optional, Dict, Any, Tuple

from django.db.models import Q

from numbering.models import DocumentType
from numbering.services.document_number_service import DocumentNumberService  # adjust import

from sales.models.sales_core import SalesInvoiceHeader
from sales.models.sales_settings import (
    SalesSettings,
    SalesLockPeriod,
    SalesChoiceOverride,
)


@dataclass(frozen=True)
class SalesPolicy:
    settings: SalesSettings

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
        return bool(self.settings.allow_mixed_taxability_in_one_invoice)

    @property
    def auto_derive_tax_regime(self) -> bool:
        return bool(self.settings.auto_derive_tax_regime)

    # Compliance governance
    @property
    def enable_einvoice(self) -> bool:
        return bool(self.settings.enable_einvoice)

    @property
    def enable_eway(self) -> bool:
        return bool(self.settings.enable_eway)

    @property
    def auto_generate_einvoice_on_confirm(self) -> bool:
        return bool(self.settings.auto_generate_einvoice_on_confirm)

    @property
    def auto_generate_einvoice_on_post(self) -> bool:
        return bool(self.settings.auto_generate_einvoice_on_post)

    @property
    def auto_generate_eway_on_confirm(self) -> bool:
        return bool(self.settings.auto_generate_eway_on_confirm)

    @property
    def auto_generate_eway_on_post(self) -> bool:
        return bool(self.settings.auto_generate_eway_on_post)

    @property
    def prefer_irp_generate_einvoice_and_eway_together(self) -> bool:
        return bool(self.settings.prefer_irp_generate_einvoice_and_eway_together)


class SalesSettingsService:


    @staticmethod
    def get_seller_profile(*, entity_id: int, subentity_id: int | None) -> dict:
        entity = (
            Entity.objects
            .select_related("state", "country", "district", "city")
            .get(id=entity_id)
        )

        se = None
        if subentity_id:
            se = (
                SubEntity.objects
                .select_related("state", "country", "district", "city")
                .get(id=subentity_id, entity_id=entity_id)
            )

        # ✅ state preference: SubEntity.state > Entity.state
        seller_state_id = (se.state_id if se and se.state_id else entity.state_id)

        return {
            "entity_id": entity.id,
            "subentity_id": se.id if se else None,

            # ✅ GST always from Entity (since SubEntity has no gstno field)
            "gstno": entity.gstno,

            "state_id": seller_state_id,

            # optional info for print/einvoice payloads
            "entityname": entity.entityname,
            "legalname": entity.legalname,
            "address": (se.address if se and se.address else entity.address),
            "address2": (getattr(se, "address2", None) if se else entity.address2),  # SubEntity doesn't have address2; safe
            "pincode": (se.pincode if se and se.pincode else entity.pincode),

            "country_id": (se.country_id if se and se.country_id else entity.country_id),
            "district_id": (se.district_id if se and se.district_id else entity.district_id),
            "city_id": (se.city_id if se and se.city_id else entity.city_id),

            "phoneoffice": (se.phoneoffice if se and se.phoneoffice else entity.phoneoffice),
            "email": (se.email if se and se.email else entity.email),
        }

    @staticmethod
    def _sales_doc_type_from_doc_key(doc_key: str) -> int:
        """
        Map DocumentType.doc_key to SalesInvoiceHeader.DocType
        Mirrors Purchase behavior.
        """
        k = (doc_key or "").upper()
        if "CREDIT" in k:
            return int(SalesInvoiceHeader.DocType.CREDIT_NOTE)
        if "DEBIT" in k:
            return int(SalesInvoiceHeader.DocType.DEBIT_NOTE)
        return int(SalesInvoiceHeader.DocType.TAX_INVOICE)

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
                module="sales",
                doc_key=doc_key,
                is_active=True,
            )
            .only("id")
            .first()
        )

        if not doc_type_row:
            return {
                "enabled": False,
                "reason": f"DocumentType not found: sales/{doc_key}",
                "doc_type_id": None,
                "current_number": None,
                "previous_number": None,
                "previous_invoice_id": None,
                "previous_invoice_number": None,
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
                "previous_invoice_number": None,
                "previous_status": None,
                "previous_bill_date": None,
            }

        # 3) Get SalesInvoiceHeader doc_type enum value from doc_key
        sales_doc_type = SalesSettingsService._sales_doc_type_from_doc_key(doc_key)

        # 4) Previous = last saved row by id (scope: entity, FY, subentity, doc_type ONLY)
        inv_filters = dict(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            doc_type=sales_doc_type,
        )
        if subentity_id is None:
            inv_filters["subentity__isnull"] = True
        else:
            inv_filters["subentity_id"] = subentity_id

        prev_doc = (
            SalesInvoiceHeader.objects.filter(**inv_filters)
            .only("id", "invoice_number", "doc_no", "status", "bill_date")
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
            "previous_invoice_number": prev_doc.invoice_number if prev_doc else None,
            "previous_status": int(prev_doc.status) if prev_doc else None,
            "previous_bill_date": prev_doc.bill_date if prev_doc else None,
        }

    # ----------------------------
    # Settings / Policy
    # ----------------------------
    @staticmethod
    def get_settings(entity_id: int, subentity_id: Optional[int]) -> SalesSettings:
        """
        Prefer entity+subentity row. Fallback to entity-only row (subentity NULL).
        Auto-create default row if missing (same suggestion as Purchase).
        """
        s = SalesSettings.objects.filter(entity_id=entity_id, subentity_id=subentity_id).first()
        if s:
            return s

        s = SalesSettings.objects.filter(entity_id=entity_id, subentity__isnull=True).first()
        if s:
            return s

        return SalesSettings.objects.create(entity_id=entity_id, subentity_id=subentity_id)

    @staticmethod
    def get_policy(entity_id: int, subentity_id: Optional[int]) -> SalesPolicy:
        return SalesPolicy(settings=SalesSettingsService.get_settings(entity_id, subentity_id))

    # ----------------------------
    # Lock period enforcement
    # ----------------------------
    @staticmethod
    def is_locked(entity_id: int, subentity_id: Optional[int], bill_date: date) -> Tuple[bool, Optional[str]]:
        """
        Locked if:
          - bill_date <= lock_date (implemented as lock_date__gte=bill_date)
        Prefer subentity-specific lock, else entity-level lock.
        """
        lock = (
            SalesLockPeriod.objects
            .filter(entity_id=entity_id, subentity_id=subentity_id, lock_date__gte=bill_date)
            .order_by("-lock_date")
            .first()
        )
        if lock:
            return True, (lock.reason or f"Locked up to {lock.lock_date}")

        lock = (
            SalesLockPeriod.objects
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
               "EXPORT_WITHOUT_IGST": {"is_enabled": false, "override_label": "Export w/o IGST (Disabled)"}
            }
          }
        """
        qs = SalesChoiceOverride.objects.filter(entity_id=entity_id).filter(
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
