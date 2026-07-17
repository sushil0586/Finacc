from __future__ import annotations

from dataclasses import dataclass
from django.db.models import Max, Q
from django.db.models import Sum
import re


from typing import Any

from datetime import date, timedelta
from rest_framework.exceptions import ValidationError
from django.core.exceptions import ValidationError as DjangoValidationError
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
from numbering.models import DocumentType
from numbering.services.document_number_service import DocumentNumberService
from sales.services.sales_withholding_service import SalesWithholdingService
from sales.services.compliance_audit_service import ComplianceAuditService
from withholding.services import WithholdingResult, upsert_tcs_computation
from financial.models import ShippingDetails, account
from financial.profile_access import account_gstno, account_partytype, account_region_state
from catalog.models import Product
from catalog.lot_tracking import resolve_tracked_lot_number
from catalog.taxability import resolve_product_default_taxability
from catalog.uom_helpers import resolve_product_uom
from sales.models.sales_core import SalesInvoiceShipToSnapshot
from sales.services.profile_resolvers import entity_primary_gstin, entity_primary_state
from posting.adapters.sales_invoice import SalesInvoicePostingAdapter, SalesInvoicePostingConfig
from posting.models import TxnType, Entry, EntryStatus, JournalLine, InventoryMove
from posting.common.location_resolver import resolve_posting_location_id
from posting.services.posting_service import PostingService, JLInput, IMInput





from django.db import transaction
from django.utils import timezone

from sales.models import (
    SalesInvoiceHeader,
    SalesInvoiceLine,
    SalesChargeLine,
    SalesChargeType,
    SalesTaxSummary,
    SalesSettings,
    SalesLockPeriod,
)
from sales.services.sales_ar_service import SalesArService
from sales.services.sales_settings_service import SalesSettingsService
from sales.services.sales_stock_policy_service import ResolvedSalesStockPolicy

ZERO2 = Decimal("0.00")
ZERO4 = Decimal("0.0000")
Q2 = Decimal("0.01")
Q4 = Decimal("0.0001")
GSTIN_RE = re.compile(r"^[0-9A-Z]{15}$")
SALES_POLICY_DEFAULTS = {
    "allow_edit_confirmed": "on",
    "allow_unpost_posted": "on",
    "confirm_lock_check": "hard",
    "require_lines_on_confirm": "hard",
    "auto_compliance_failure_mode": "warn",
}


def q2(x) -> Decimal:
    try:
        return Decimal(x or 0).quantize(Q2, rounding=ROUND_HALF_UP)
    except Exception:
        return ZERO2


def q4(x) -> Decimal:
    try:
        return Decimal(x or 0).quantize(Q4, rounding=ROUND_HALF_UP)
    except Exception:
        return ZERO4


@dataclass
class ChargeComputed:
    taxable_value: Decimal = ZERO2
    cgst_amount: Decimal = ZERO2
    sgst_amount: Decimal = ZERO2
    igst_amount: Decimal = ZERO2
    total_value: Decimal = ZERO2


@dataclass
class Totals:
    total_taxable: Decimal = ZERO2
    total_cgst: Decimal = ZERO2
    total_sgst: Decimal = ZERO2
    total_igst: Decimal = ZERO2
    total_cess: Decimal = ZERO2
    total_discount: Decimal = ZERO2
    total_other_charges: Decimal = ZERO2
    round_off: Decimal = ZERO2
    grand_total: Decimal = ZERO2


class SalesInvoiceService:
    _BACKEND_CONTROLLED_HEADER_FIELDS = {
        "status",
        "doc_no",
        "invoice_number",
        "posting_date",
        "due_date",
        "tax_regime",
        "is_igst",
        "gst_compliance_mode",
        "is_einvoice_applicable",
        "is_eway_applicable",
        "total_taxable_value",
        "total_cgst",
        "total_sgst",
        "total_igst",
        "total_cess",
        "total_discount",
        "total_other_charges",
        "round_off",
        "grand_total",
        "settled_amount",
        "outstanding_amount",
        "settlement_status",
        "reversed_at",
        "reversed_by",
        "reverse_reason",
        "is_posting_reversed",
    }

    @classmethod
    def _sanitize_header_data_inputs(cls, header_data: dict) -> dict:
        clean = dict(header_data or {})
        for field in cls._BACKEND_CONTROLLED_HEADER_FIELDS:
            clean.pop(field, None)
        return clean

    @staticmethod
    def _set_tcs_runtime_snapshot(
        *,
        header: SalesInvoiceHeader,
        mode: str,
        enabled: bool,
        reason: str | None,
        reason_code: str | None,
    ) -> None:
        flags = dict(getattr(header, "legacy_behavior_flags", {}) or {})
        if not enabled:
            flags.pop("tcs_runtime_result", None)
            header.legacy_behavior_flags = flags
            return

        section = getattr(header, "tcs_section", None)
        amount = q2(getattr(header, "tcs_amount", ZERO2) or ZERO2)
        base_amount = q2(getattr(header, "tcs_base_amount", ZERO2) or ZERO2)
        rate = q4(getattr(header, "tcs_rate", ZERO4) or ZERO4)

        flags["tcs_runtime_result"] = {
            "enabled": True,
            "mode": str(mode or "AUTO").upper().strip(),
            "section_id": getattr(section, "id", None) if section is not None else None,
            "section_code": str(getattr(section, "section_code", "") or "").strip().upper() or None,
            "rate": str(rate),
            "base_amount": str(base_amount),
            "amount": str(amount),
            "reason": (str(reason or "").strip() or None),
            "reason_code": (str(reason_code or "").strip().upper() or None),
            "collection_status": "COLLECTED" if amount > ZERO2 else "NOT_COLLECTED",
            "zero_collection": bool(amount <= ZERO2),
            "user_selected_add_tcs": bool(getattr(header, "withholding_enabled", False)),
        }
        header.legacy_behavior_flags = flags

    @staticmethod
    def _policy_controls(header: SalesInvoiceHeader) -> dict:
        settings_obj = SalesInvoiceService.get_settings(
            header.entity_id,
            header.subentity_id,
            entityfinid_id=getattr(header, "entityfinid_id", None),
        )
        raw = getattr(settings_obj, "policy_controls", None) or {}
        merged = dict(SALES_POLICY_DEFAULTS)
        if isinstance(raw, dict):
            merged.update(raw)
        return merged

    @staticmethod
    def _policy_level(controls: dict, key: str, default: str = "hard") -> str:
        val = str(controls.get(key, default)).lower().strip()
        return val if val in {"off", "warn", "hard"} else default

    @staticmethod
    def _stock_policy(header: SalesInvoiceHeader) -> ResolvedSalesStockPolicy:
        return SalesSettingsService.get_stock_policy(
            entity_id=header.entity_id,
            subentity_id=header.subentity_id,
            entityfinid_id=getattr(header, "entityfinid_id", None),
        )

    @staticmethod
    def _inventory_move_type_for_header(header: SalesInvoiceHeader) -> str | None:
        doc_type = int(getattr(header, "doc_type", SalesInvoiceHeader.DocType.TAX_INVOICE))
        if doc_type == int(SalesInvoiceHeader.DocType.DEBIT_NOTE):
            return None
        if doc_type == int(SalesInvoiceHeader.DocType.CREDIT_NOTE):
            return InventoryMove.MoveType.IN_
        return InventoryMove.MoveType.OUT

    @staticmethod
    def _stock_issue_qty(line: SalesInvoiceLine, *, product=None) -> Decimal:
        qty = q4(getattr(line, "qty", None) or ZERO4)
        free_qty = q4(getattr(line, "free_qty", None) or ZERO4)
        entered_qty = q4(qty + free_qty)
        if entered_qty <= ZERO4 or product is None:
            return entered_qty
        _, factor_to_base = resolve_product_uom(
            product=product,
            raw_uom_id=getattr(line, "uom_id", None),
        )
        return q4(entered_qty * q4(factor_to_base))

    @staticmethod
    def _normalize_batch_number(value: object) -> str:
        batch = str(value or "").strip()
        if not batch:
            return ""
        if batch.isdigit():
            return str(int(batch))
        return batch

    @classmethod
    def _build_stock_balance_maps(
        cls,
        *,
        header: SalesInvoiceHeader,
        product_ids: list[int],
        location_id: int | None,
    ) -> tuple[dict[tuple[int, str, int | None], Decimal], dict[tuple[int, str, int | None, object], Decimal]]:
        if not product_ids:
            return {}, {}

        qs = InventoryMove.objects.filter(
            entity_id=header.entity_id,
            posting_date__lte=header.bill_date,
            product_id__in=product_ids,
            product__is_service=False,
        )
        if getattr(header, "entityfinid_id", None):
            qs = qs.filter(entityfin_id=header.entityfinid_id)
        if header.subentity_id is not None:
            qs = qs.filter(subentity_id=header.subentity_id)
        if location_id is not None:
            qs = qs.filter(location_id=location_id)

        rows = qs.values(
            "product_id",
            "batch_number",
            "expiry_date",
            "move_type",
            "base_qty",
            "location_id",
        )

        by_product_batch: dict[tuple[int, str, int | None], Decimal] = defaultdict(lambda: ZERO4)
        by_product_batch_expiry: dict[tuple[int, str, int | None, object], Decimal] = defaultdict(lambda: ZERO4)
        for row in rows:
            product_id = int(row["product_id"])
            batch_number = cls._normalize_batch_number(row.get("batch_number"))
            expiry_date = row.get("expiry_date")
            row_location_id = row.get("location_id")
            base_qty = q4(row.get("base_qty") or ZERO4)
            move_type = str(row.get("move_type") or "").upper()
            signed_qty = -abs(base_qty) if move_type == InventoryMove.MoveType.OUT else abs(base_qty)
            key = (product_id, batch_number, row_location_id)
            by_product_batch[key] = q4(by_product_batch[key] + signed_qty)
            expiry_key = (product_id, batch_number, row_location_id, expiry_date)
            by_product_batch_expiry[expiry_key] = q4(by_product_batch_expiry[expiry_key] + signed_qty)

        return by_product_batch, by_product_batch_expiry

    @classmethod
    def _allocate_batches_for_post(
        cls,
        *,
        header: SalesInvoiceHeader,
        lines: list[SalesInvoiceLine],
    ) -> None:
        policy = cls._stock_policy(header)
        move_type = cls._inventory_move_type_for_header(header)
        if move_type != InventoryMove.MoveType.OUT:
            return

        mode = str(getattr(policy, "mode", "") or "").upper()
        enforce_expiry = mode == "STRICT" or bool(policy.expiry_validation_required)
        enforce_fefo = mode == "STRICT" or bool(policy.fefo_required)
        require_batch_for_sales = bool(policy.batch_required_for_sales) or mode == "STRICT"

        location_id = resolve_posting_location_id(
            entity_id=header.entity_id,
            subentity_id=header.subentity_id,
            godown_id=getattr(header, "godown_id", None),
            location_id=getattr(header, "location_id", None),
        )

        product_ids = sorted({
            int(getattr(line, "product_id", 0) or 0)
            for line in lines
            if getattr(line, "product_id", None)
        })
        if not product_ids:
            return

        products = {
            product.id: product
            for product in Product.objects.filter(id__in=product_ids)
            .select_related("base_uom")
            .prefetch_related("uom_conversions__from_uom", "uom_conversions__to_uom")
            .only("id", "productname", "is_batch_managed", "is_expiry_tracked", "is_service", "base_uom")
        }
        available_by_key, available_by_expiry = cls._build_stock_balance_maps(
            header=header,
            product_ids=product_ids,
            location_id=location_id,
        )

        earliest_batch: dict[tuple[int, int | None], tuple[object, str, Decimal]] = {}

        def _best_batch_for_product(product_id: int) -> tuple[object, str, Decimal] | None:
            candidate_key = (product_id, location_id)
            candidate = earliest_batch.get(candidate_key)
            if candidate is not None:
                return candidate
            candidates = []
            for (pid, batch, loc_id, exp_date), balance in available_by_expiry.items():
                if pid != product_id or loc_id != location_id:
                    continue
                if q4(balance) <= ZERO4 or not batch:
                    continue
                candidates.append((exp_date or date.max, batch, q4(balance)))
            if not candidates:
                return None
            candidates.sort(key=lambda item: (item[0], item[1]))
            candidate = candidates[0]
            earliest_batch[candidate_key] = candidate
            return candidate

        def _available_expiry_for_batch(product_id: int, batch_number: str) -> object | None:
            expiries = []
            for (pid, batch, loc_id, exp_date), balance in available_by_expiry.items():
                if pid != product_id or loc_id != location_id or batch != batch_number:
                    continue
                if q4(balance) <= ZERO4:
                    continue
                expiries.append(exp_date)
            if not expiries:
                return None
            non_null = sorted([d for d in expiries if d is not None])
            if non_null:
                return non_null[0]
            return None

        for line in lines:
            product_id = int(getattr(line, "product_id", 0) or 0)
            if not product_id:
                continue
            product = products.get(product_id)
            if not product or bool(getattr(product, "is_service", False)):
                continue

            is_batch_managed = bool(getattr(product, "is_batch_managed", False))
            is_expiry_tracked = bool(getattr(product, "is_expiry_tracked", False))
            if not (is_batch_managed or is_expiry_tracked or require_batch_for_sales):
                continue

            issue_qty = cls._stock_issue_qty(line, product=product)
            if issue_qty <= ZERO4:
                continue

            batch_number = resolve_tracked_lot_number(
                product=product,
                batch_number=getattr(line, "batch_number", ""),
                expiry_date=getattr(line, "expiry_date", None),
            )
            expiry_date = getattr(line, "expiry_date", None)
            line_no = int(getattr(line, "line_no", 0) or 0) or 0

            candidate = _best_batch_for_product(product_id) if (enforce_fefo or not batch_number) else None
            if not batch_number:
                if candidate is None:
                    raise ValidationError({
                        "lines": [f"Line {line_no or '-'}: no available batch found for {getattr(product, 'productname', product_id)}."]
                    })
                candidate_expiry, candidate_batch, _ = candidate
                line.batch_number = candidate_batch
                if expiry_date is None and candidate_expiry not in (None, ""):
                    line.expiry_date = candidate_expiry
                if getattr(line, "manufacture_date", None) is None and candidate_expiry not in (None, ""):
                    # leave manufacture date blank; it is not derivable from expiry.
                    pass
                if hasattr(line, "updated_by"):
                    pass
                line.save(update_fields=["batch_number", "expiry_date", "updated_at"])
                batch_number = cls._normalize_batch_number(candidate_batch)
                expiry_date = getattr(line, "expiry_date", None)

            available_qty = q4(available_by_key.get((product_id, batch_number, location_id), ZERO4))
            if available_qty <= ZERO4:
                can_infer_location = not bool(getattr(header, "location_id", None)) and not bool(getattr(header, "godown_id", None))
                if can_infer_location:
                    batch_locations = [
                        (loc_id, q4(balance))
                        for (pid, batch, loc_id), balance in available_by_key.items()
                        if pid == product_id and batch == batch_number and q4(balance) > ZERO4 and loc_id is not None
                    ]
                    unique_locations = sorted({loc_id for loc_id, _ in batch_locations})
                    if len(unique_locations) == 1:
                        inferred_location_id = unique_locations[0]
                        header.location_id = inferred_location_id
                        header.save(update_fields=["location_id", "updated_at"])
                        location_id = inferred_location_id
                        available_qty = q4(available_by_key.get((product_id, batch_number, location_id), ZERO4))

            if available_qty <= ZERO4:
                raise ValidationError({
                    "lines": [
                        f"Line {line_no or '-'}: batch '{batch_number}' is not available for {getattr(product, 'productname', product_id)}."
                    ]
                })
            if issue_qty > available_qty:
                raise ValidationError({
                    "lines": [
                        f"Line {line_no or '-'}: batch '{batch_number}' has insufficient stock for {getattr(product, 'productname', product_id)}. "
                        f"Required {issue_qty}, available {available_qty}."
                    ]
                })

            if enforce_expiry:
                if expiry_date is None:
                    expiry_date = _available_expiry_for_batch(product_id, batch_number)
                    if expiry_date is not None:
                        line.expiry_date = expiry_date
                        line.save(update_fields=["expiry_date", "updated_at"])
                if expiry_date is None:
                    raise ValidationError({
                        "lines": [
                            f"Line {line_no or '-'}: expiry date is required for batch '{batch_number}'."
                        ]
                    })
                if expiry_date < header.bill_date:
                    raise ValidationError({
                        "lines": [
                            f"Line {line_no or '-'}: batch '{batch_number}' is expired and cannot be sold."
                        ]
                    })

            if enforce_fefo and not bool(policy.allow_manual_batch_override):
                candidate = _best_batch_for_product(product_id)
                if candidate is not None:
                    candidate_expiry, candidate_batch, _ = candidate
                    if batch_number != candidate_batch:
                        expiry_text = f" ({candidate_expiry.isoformat()})" if hasattr(candidate_expiry, "isoformat") else ""
                        raise ValidationError({
                            "lines": [
                                f"Line {line_no or '-'}: FEFO requires batch '{candidate_batch}'{expiry_text}."
                            ]
                        })

    @classmethod
    def _validate_stock_policy_on_post(cls, *, header: SalesInvoiceHeader, lines: list[SalesInvoiceLine]) -> None:
        move_type = cls._inventory_move_type_for_header(header)
        if move_type != InventoryMove.MoveType.OUT:
            return

        policy = cls._stock_policy(header)
        mode = str(getattr(policy, "mode", "") or "").upper()
        enforce_negative = mode == "STRICT" or not bool(policy.allow_negative_stock)

        location_id = resolve_posting_location_id(
            entity_id=header.entity_id,
            subentity_id=header.subentity_id,
            godown_id=getattr(header, "godown_id", None),
            location_id=getattr(header, "location_id", None),
        )

        product_ids = sorted({
            int(getattr(line, "product_id", 0) or 0)
            for line in lines
            if getattr(line, "product_id", None)
        })
        if not product_ids:
            return

        products = {
            product.id: product
            for product in Product.objects.filter(id__in=product_ids)
            .select_related("base_uom")
            .prefetch_related("uom_conversions__from_uom", "uom_conversions__to_uom")
            .only("id", "productname", "is_batch_managed", "is_expiry_tracked", "is_service", "base_uom")
        }
        available_by_key, available_by_expiry = cls._build_stock_balance_maps(
            header=header,
            product_ids=product_ids,
            location_id=location_id,
        )

        requested_by_key: dict[tuple[int, str, int | None], Decimal] = defaultdict(lambda: ZERO4)
        line_refs: dict[tuple[int, str, int | None], list[int]] = defaultdict(list)
        earliest_batch: dict[tuple[int, int | None], tuple[object, str, Decimal]] = {}

        for line in lines:
            product_id = int(getattr(line, "product_id", 0) or 0)
            if not product_id:
                continue
            product = products.get(product_id)
            if not product or bool(getattr(product, "is_service", False)):
                continue

            issue_qty = cls._stock_issue_qty(line, product=product)
            if issue_qty <= ZERO4:
                continue

            batch_number = cls._normalize_batch_number(getattr(line, "batch_number", ""))
            expiry_date = getattr(line, "expiry_date", None)
            line_no = int(getattr(line, "line_no", 0) or 0) or 0
            key = (product_id, batch_number, location_id)
            requested_by_key[key] = q4(requested_by_key[key] + issue_qty)
            if line_no > 0:
                line_refs[key].append(line_no)

            if bool(getattr(product, "is_expiry_tracked", False)):
                if expiry_date is None:
                    raise ValidationError({"lines": [f"Line {line_no or '-'}: expiry date is required for expiry-tracked products."]})
                if expiry_date < header.bill_date:
                    raise ValidationError({"lines": [f"Line {line_no or '-'}: expired stock cannot be sold."]})

            if bool(getattr(product, "is_batch_managed", False)):
                candidate_key = (product_id, location_id)
                candidate = earliest_batch.get(candidate_key)
                if candidate is None:
                    candidates = []
                    for (pid, batch, loc_id, exp_date), balance in available_by_expiry.items():
                        if pid != product_id or loc_id != location_id:
                            continue
                        if q4(balance) <= ZERO4 or not batch:
                            continue
                        candidates.append((exp_date or date.max, batch, q4(balance)))
                    if candidates:
                        candidates.sort(key=lambda item: (item[0], item[1]))
                        candidate = candidates[0]
                        earliest_batch[candidate_key] = candidate
                if candidate and not bool(policy.allow_manual_batch_override):
                    candidate_expiry, candidate_batch, _ = candidate
                    if batch_number and batch_number != candidate_batch:
                        expiry_text = f" ({candidate_expiry.isoformat()})" if hasattr(candidate_expiry, "isoformat") else ""
                        raise ValidationError({
                            "lines": [
                                f"Line {line_no or '-'}: FEFO requires batch '{candidate_batch}'{expiry_text}."
                            ]
                        })

        if not enforce_negative:
            return

        shortages = []
        for key, requested_qty in requested_by_key.items():
            product_id, batch_number, _ = key
            available_qty = q4(available_by_key.get(key, ZERO4))
            if requested_qty <= available_qty:
                continue
            product = products.get(product_id)
            product_name = getattr(product, "productname", f"Product {product_id}") if product else f"Product {product_id}"
            batch_text = f", batch '{batch_number}'" if batch_number else ""
            refs = ",".join(str(x) for x in sorted(set(line_refs.get(key, [])))) if line_refs.get(key) else "-"
            shortages.append(
                f"Line(s) {refs}: insufficient stock for {product_name}{batch_text}. "
                f"Required {requested_qty}, available {available_qty}."
            )

        if shortages:
            raise ValidationError({"lines": shortages})

    @staticmethod
    def _resolve_customer_ledger_id(customer_id: Optional[int]) -> Optional[int]:
        if not customer_id:
            return None
        customer = (
            account.objects.filter(id=customer_id)
            .only("id", "isactive", "ledger_id")
            .first()
        )
        if not customer:
            raise ValueError("Selected customer account does not exist.")
        if not bool(getattr(customer, "isactive", True)):
            raise ValueError("Selected customer account is inactive.")
        if not getattr(customer, "ledger_id", None):
            raise ValueError("Selected customer account does not have a linked ledger.")
        return int(customer.ledger_id)

    """
    Mirrors PurchaseInvoiceService patterns:
      - create_with_lines / update_with_lines
      - apply_dates (posting_date, due_date)
      - derive_tax_regime
      - upsert_lines (insert/update/delete)
      - rebuild_tax_summary
      - compute header totals
      - backend-controlled status transitions
    """

    # -------------------------
    # Settings / Lock validation
    # -------------------------

    @classmethod
    def _run_auto_compliance(cls, *, header: SalesInvoiceHeader, user, stage: str) -> None:
        """
        Auto compliance hook controlled by SalesSettings.
        stage: "confirm" | "post"
        """
        settings_obj = cls.get_settings(header.entity_id, header.subentity_id, entityfinid_id=getattr(header, "entityfinid_id", None))
        from sales.services.sales_compliance_service import SalesComplianceService

        controls = cls._policy_controls(header)
        failure_mode = str(controls.get("auto_compliance_failure_mode", "warn")).lower().strip()
        if failure_mode not in {"warn", "hard"}:
            failure_mode = "warn"

        svc = SalesComplianceService(invoice=header, user=user)
        try:
            svc.ensure_rows()
        except Exception as exc:
            ComplianceAuditService.log_action(
                invoice=header,
                action_type="AUTO_COMPLIANCE",
                outcome="FAILED",
                user=user,
                error_code="AUTO_COMPLIANCE_ENSURE_FAILED",
                error_message=str(exc),
                request_json={"stage": stage, "step": "ensure_rows"},
            )
            if failure_mode == "hard":
                raise

        auto_irn = (
            bool(getattr(settings_obj, "auto_generate_einvoice_on_confirm", False))
            if stage == "confirm"
            else bool(getattr(settings_obj, "auto_generate_einvoice_on_post", False))
        )
        auto_eway = (
            bool(getattr(settings_obj, "auto_generate_eway_on_confirm", False))
            if stage == "confirm"
            else bool(getattr(settings_obj, "auto_generate_eway_on_post", False))
        )

        seller_gstin = str(getattr(header, "seller_gstin", "") or "").strip()
        customer_gstin = str(getattr(header, "customer_gstin", "") or "").strip()
        is_b2c = int(getattr(header, "supply_category", 0) or 0) == int(SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2C)
        effective_einvoice_applicable = bool(
            getattr(header, "is_einvoice_applicable", False)
            or ((not is_b2c) and len(seller_gstin) == 15 and len(customer_gstin) == 15)
        )

        if bool(getattr(settings_obj, "enable_einvoice", True)) and auto_irn and effective_einvoice_applicable:
            try:
                svc.generate_irn()
            except Exception as exc:
                ComplianceAuditService.log_action(
                    invoice=header,
                    action_type="AUTO_COMPLIANCE",
                    outcome="FAILED",
                    user=user,
                    error_code="AUTO_COMPLIANCE_IRN_FAILED",
                    error_message=str(exc),
                    request_json={"stage": stage, "step": "generate_irn"},
                )
                if failure_mode == "hard":
                    raise

        if not (bool(getattr(settings_obj, "enable_eway", True)) and auto_eway and bool(header.is_eway_applicable)):
            return

        # B2C direct E-Way
        if int(getattr(header, "supply_category", 0) or 0) == int(SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2C):
            try:
                out = svc.eway_generate_b2c(header, user=user)
                if out.get("status") != "SUCCESS":
                    raise ValueError(out.get("error_message") or "Auto E-Way(B2C) generation failed.")
            except Exception as exc:
                ComplianceAuditService.log_action(
                    invoice=header,
                    action_type="AUTO_COMPLIANCE",
                    outcome="FAILED",
                    user=user,
                    error_code="AUTO_COMPLIANCE_EWAY_B2C_FAILED",
                    error_message=str(exc),
                    request_json={"stage": stage, "step": "eway_generate_b2c"},
                )
                if failure_mode == "hard":
                    raise
            return

        # B2B/IRN-based E-Way needs transport info.
        # If details are missing, do not attempt API call. UI should collect these via popup.
        art = getattr(header, "eway_artifact", None)
        if not art:
            ComplianceAuditService.log_action(
                invoice=header,
                action_type="AUTO_COMPLIANCE",
                outcome="SKIPPED",
                user=user,
                error_code="AUTO_COMPLIANCE_EWAY_INPUT_REQUIRED",
                error_message="Auto E-Way skipped because transport details are not available.",
                request_json={"stage": stage, "step": "generate_eway", "reason": "eway_artifact_missing"},
            )
            return

        if not getattr(art, "distance_km", None):
            ComplianceAuditService.log_action(
                invoice=header,
                action_type="AUTO_COMPLIANCE",
                outcome="SKIPPED",
                user=user,
                error_code="AUTO_COMPLIANCE_EWAY_INPUT_REQUIRED",
                error_message="Auto E-Way skipped because distance_km is missing.",
                request_json={"stage": stage, "step": "generate_eway", "reason": "distance_km_missing"},
            )
            return
        if not getattr(art, "transport_mode", None):
            ComplianceAuditService.log_action(
                invoice=header,
                action_type="AUTO_COMPLIANCE",
                outcome="SKIPPED",
                user=user,
                error_code="AUTO_COMPLIANCE_EWAY_INPUT_REQUIRED",
                error_message="Auto E-Way skipped because transport_mode is missing.",
                request_json={"stage": stage, "step": "generate_eway", "reason": "transport_mode_missing"},
            )
            return

        req = {
            "distance_km": int(art.distance_km),
            "trans_mode": str(art.transport_mode),
            "transporter_id": art.transporter_id or "",
            "transporter_name": art.transporter_name or "",
            "trans_doc_no": art.doc_no or "",
            "trans_doc_date": art.doc_date,
            "vehicle_no": art.vehicle_no,
            "vehicle_type": art.vehicle_type,
            "disp_dtls": art.disp_dtls_json or None,
            "exp_ship_dtls": art.exp_ship_dtls_json or None,
        }
        try:
            out = SalesComplianceService.generate_eway(
                inv=header,
                entity=header.entity,
                req=req,
                created_by=user,
            )
            if out.get("status") != "SUCCESS":
                raise ValueError(out.get("error_message") or "Auto E-Way generation failed.")
        except Exception as exc:
            ComplianceAuditService.log_action(
                invoice=header,
                action_type="AUTO_COMPLIANCE",
                outcome="FAILED",
                user=user,
                error_code="AUTO_COMPLIANCE_EWAY_FAILED",
                error_message=str(exc),
                request_json={"stage": stage, "step": "generate_eway"},
            )
            if failure_mode == "hard":
                raise

    @classmethod
    def _apply_tcs(cls, *, header: SalesInvoiceHeader, user) -> None:
        """
        Enforce: only ONE TCS section at a time (tcs_section FK).
        Compute TCS AFTER totals are available.
        """

        # If not enabled => clear everything
        if not getattr(header, "withholding_enabled", False):
            preview = WithholdingResult(
                enabled=False,
                section=None,
                rate=Decimal("0.0000"),
                base_amount=ZERO2,
                amount=ZERO2,
                reason="Withholding disabled",
                reason_code="DISABLED",
            )
            header.tcs_section = None
            header.tcs_rate = Decimal("0.0000")
            header.tcs_base_amount = ZERO2
            header.tcs_amount = ZERO2
            header.tcs_reason = None
            header.tcs_is_reversal = False
            cls._set_tcs_runtime_snapshot(
                header=header,
                mode="AUTO",
                enabled=False,
                reason=None,
                reason_code=None,
            )
            header.updated_by = user
            header.save(update_fields=[
                "tcs_section", "tcs_rate", "tcs_base_amount", "tcs_amount", "tcs_reason",
                "tcs_is_reversal", "legacy_behavior_flags", "updated_by"
            ])
            cls._sync_tcs_computation(header=header, preview=preview, user=user, status="REVERSED")
            return

        settings_obj = cls.get_settings(header.entity_id, header.subentity_id, entityfinid_id=getattr(header, "entityfinid_id", None))
        is_credit_note = int(header.doc_type or 0) == int(SalesInvoiceHeader.DocType.CREDIT_NOTE)
        credit_note_policy = (getattr(settings_obj, "tcs_credit_note_policy", "REVERSE") or "REVERSE").upper()

        if is_credit_note and credit_note_policy == "DISALLOW":
            preview = WithholdingResult(
                enabled=True,
                section=None,
                rate=Decimal("0.0000"),
                base_amount=ZERO2,
                amount=ZERO2,
                reason="TCS on credit note disallowed by policy.",
                reason_code="CREDIT_NOTE_POLICY_DISALLOW",
            )
            header.tcs_section = None
            header.tcs_rate = Decimal("0.0000")
            header.tcs_base_amount = ZERO2
            header.tcs_amount = ZERO2
            header.tcs_reason = "TCS on credit note disallowed by policy."
            header.tcs_is_reversal = False
            cls._set_tcs_runtime_snapshot(
                header=header,
                mode="AUTO",
                enabled=True,
                reason=preview.reason,
                reason_code=preview.reason_code,
            )
            header.updated_by = user
            header.save(update_fields=[
                "tcs_section", "tcs_rate", "tcs_base_amount", "tcs_amount",
                "tcs_reason", "tcs_is_reversal", "legacy_behavior_flags", "updated_by",
            ])
            cls._sync_tcs_computation(header=header, preview=preview, user=user, status="REVERSED")
            return

        # Enabled => section must be selected (one at a time)
        if not header.tcs_section_id:
            raise ValueError("TCS section is required when withholding_enabled is true (only one allowed).")

        # Compute using authoritative totals (AFTER compute_and_persist_totals)
        res = SalesWithholdingService.compute_tcs(
            header=header,
            customer_account_id=header.customer_id,
            invoice_date=header.bill_date or timezone.localdate(),
            taxable_total=q2(
                getattr(header, "total_taxable_value", None)
                or getattr(header, "total_taxable", None)
                or ZERO2
            ),
            gross_total=q2(getattr(header, "grand_total", ZERO2) or ZERO2),
        )

        header.tcs_section = res.section  # still one FK
        header.tcs_rate = res.rate
        header.tcs_base_amount = res.base_amount
        header.tcs_amount = res.amount
        header.tcs_reason = res.reason
        header.tcs_is_reversal = bool(is_credit_note and credit_note_policy == "REVERSE" and q2(res.amount) > ZERO2)
        cls._set_tcs_runtime_snapshot(
            header=header,
            mode="AUTO",
            enabled=True,
            reason=res.reason,
            reason_code=res.reason_code,
        )
        header.updated_by = user

        # OPTIONAL: if you have receivable_total field
        if hasattr(header, "customer_receivable"):
            header.customer_receivable = q2((header.grand_total or ZERO2) + (header.tcs_amount or ZERO2))
            header.save(update_fields=[
                "tcs_section", "tcs_rate", "tcs_base_amount", "tcs_amount", "tcs_reason",
                "tcs_is_reversal",
                "legacy_behavior_flags",
                "customer_receivable",
                "updated_by",
            ])
        else:
            header.save(update_fields=[
                "tcs_section", "tcs_rate", "tcs_base_amount", "tcs_amount", "tcs_reason",
                "tcs_is_reversal", "legacy_behavior_flags", "updated_by"
            ])

        status = "REVERSED" if bool(header.tcs_is_reversal) else "CONFIRMED"
        cls._sync_tcs_computation(header=header, preview=res, user=user, status=status)

    @classmethod
    def _sync_tcs_computation(cls, *, header: SalesInvoiceHeader, preview: WithholdingResult, user, status: str) -> None:
        if not getattr(header, "id", None):
            return
        if not getattr(header, "entity_id", None) or not getattr(header, "entityfinid_id", None):
            return

        doc_type_map = {
            int(SalesInvoiceHeader.DocType.TAX_INVOICE): "invoice",
            int(SalesInvoiceHeader.DocType.CREDIT_NOTE): "credit_note",
            int(SalesInvoiceHeader.DocType.DEBIT_NOTE): "debit_note",
        }
        document_type = doc_type_map.get(int(header.doc_type or 0), "invoice")
        document_no = (header.invoice_number or "").strip() or str(header.doc_no or "")

        upsert_tcs_computation(
            module_name="sales",
            document_type=document_type,
            document_id=int(header.id),
            document_no=document_no,
            doc_date=(header.bill_date or timezone.localdate()),
            entity_id=int(header.entity_id),
            entityfin_id=int(header.entityfinid_id),
            subentity_id=header.subentity_id,
            party_account_id=header.customer_id,
            preview=preview,
            status=status,
            trigger_basis="INVOICE",
            override_reason=(header.tcs_reason or "") if preview.amount == ZERO2 else "",
            overridden_by=user,
        )

    @staticmethod
    def _normalize_gstin(gstin: Optional[str]) -> str:
        return (gstin or "").strip().upper()

    @classmethod
    def _is_valid_gstin(cls, gstin: Optional[str]) -> bool:
        g = cls._normalize_gstin(gstin)
        return bool(GSTIN_RE.fullmatch(g))

    @staticmethod
    def _state_code_from_state_obj(state_obj) -> str:
        if not state_obj:
            return ""
        code = (
            getattr(state_obj, "gst_state_code", None)
            or getattr(state_obj, "statecode", None)
            or getattr(state_obj, "code", None)
            or ""
        )
        s = str(code).strip()
        return s.zfill(2) if s.isdigit() and s else s

    @classmethod
    def _refresh_party_snapshots(cls, *, header: SalesInvoiceHeader) -> None:
        """
        Keep GST-critical snapshot fields aligned from master records if missing.
        """
        cust = getattr(header, "customer", None)
        ent = getattr(header, "entity", None)
        if cust:
            if not (header.customer_name or "").strip():
                header.customer_name = (getattr(cust, "legalname", None) or getattr(cust, "accountname", None) or "").strip()
            if not cls._is_valid_gstin(header.customer_gstin):
                header.customer_gstin = cls._normalize_gstin(account_gstno(cust))
            if not (header.customer_state_code or "").strip():
                header.customer_state_code = cls._state_code_from_state_obj(account_region_state(cust))

        if ent:
            if not cls._is_valid_gstin(header.seller_gstin):
                header.seller_gstin = cls._normalize_gstin(entity_primary_gstin(ent))
            if not (header.seller_state_code or "").strip():
                header.seller_state_code = cls._state_code_from_state_obj(entity_primary_state(ent))

        # Derive POS from bill-to/ship-to/customer when missing.
        if not (header.place_of_supply_state_code or "").strip():
            header.place_of_supply_state_code = (
                (header.bill_to_state_code or "").strip()
                or (header.customer_state_code or "").strip()
            )

    @classmethod
    def _align_note_tax_scope_from_original_invoice(cls, *, header_data: dict, original_invoice: SalesInvoiceHeader) -> None:
        """
        Credit/Debit notes should inherit the original invoice tax scope.
        This keeps tax regime derivation and downstream caps aligned with the
        source invoice instead of letting the note drift to a different state
        combination.
        """
        header_data["seller_gstin"] = (original_invoice.seller_gstin or "").strip()
        header_data["seller_state_code"] = (original_invoice.seller_state_code or "").strip()
        header_data["place_of_supply_state_code"] = (original_invoice.place_of_supply_state_code or "").strip()

    @classmethod
    def _derive_compliance_flags(cls, *, header: SalesInvoiceHeader, settings_obj: SalesSettings, user=None) -> None:
        is_b2c = int(header.supply_category or 0) == int(SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2C)
        seller_gstin_ok = cls._is_valid_gstin(header.seller_gstin)
        customer_gstin_ok = cls._is_valid_gstin(header.customer_gstin)

        auto_einvoice = bool(
            getattr(settings_obj, "enable_einvoice", True)
            and getattr(settings_obj, "einvoice_entity_applicable", False)
            and not is_b2c
            and seller_gstin_ok
            and customer_gstin_ok
        )
        auto_eway = bool(
            getattr(settings_obj, "enable_eway", True)
            and q2(getattr(header, "grand_total", ZERO2) or ZERO2) >= q2(getattr(settings_obj, "eway_value_threshold", Decimal("50000.00")))
        )

        mode = getattr(settings_obj, "compliance_applicability_mode", "AUTO_ONLY")
        manual_override_enabled = (mode == SalesSettings.ComplianceApplicabilityMode.AUTO_WITH_OVERRIDE)
        man_einv = getattr(header, "einvoice_applicable_manual", None)
        man_eway = getattr(header, "eway_applicable_manual", None)

        if manual_override_enabled and (man_einv is not None or man_eway is not None):
            if not (header.compliance_override_reason or "").strip():
                raise ValueError("compliance_override_reason is required for manual compliance override.")
            header.compliance_override_at = timezone.now()
            header.compliance_override_by = user
            final_einv = auto_einvoice if man_einv is None else bool(man_einv)
            final_eway = auto_eway if man_eway is None else bool(man_eway)
        else:
            if manual_override_enabled:
                header.compliance_override_reason = ""
                header.compliance_override_at = None
                header.compliance_override_by = None
            if not manual_override_enabled:
                header.einvoice_applicable_manual = None
                header.eway_applicable_manual = None
                header.compliance_override_reason = ""
                header.compliance_override_at = None
                header.compliance_override_by = None
            final_einv = auto_einvoice
            final_eway = auto_eway

        header.is_einvoice_applicable = bool(final_einv)
        header.is_eway_applicable = bool(final_eway)
        if header.is_einvoice_applicable and header.is_eway_applicable:
            header.gst_compliance_mode = SalesInvoiceHeader.GstComplianceMode.EINVOICE_AND_EWAY
        elif header.is_einvoice_applicable:
            header.gst_compliance_mode = SalesInvoiceHeader.GstComplianceMode.EINVOICE_ONLY
        elif header.is_eway_applicable:
            header.gst_compliance_mode = SalesInvoiceHeader.GstComplianceMode.EWAY_ONLY
        else:
            header.gst_compliance_mode = SalesInvoiceHeader.GstComplianceMode.NONE

    @classmethod
    def _validate_b2b_gstin_requirements(cls, *, header: SalesInvoiceHeader) -> None:
        is_b2c = int(header.supply_category or 0) == int(SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2C)
        if is_b2c:
            return
        if not cls._is_valid_gstin(header.seller_gstin):
            raise ValueError("Valid seller_gstin is required for non-B2C invoices.")
        if not cls._is_valid_gstin(header.customer_gstin):
            raise ValueError("Valid customer_gstin is required for non-B2C invoices.")

    @classmethod
    def _validate_invoice_uniqueness_per_gstin(cls, *, header: SalesInvoiceHeader) -> None:
        """
        Enforce invoice uniqueness at GSTIN scope (not subentity scope):
        (seller_gstin, entityfinid, doc_type, invoice_number) must be unique.
        """
        invoice_number = (header.invoice_number or "").strip()
        if not invoice_number:
            return

        seller_gstin = cls._normalize_gstin(getattr(header, "seller_gstin", ""))
        if not seller_gstin:
            return

        qs = SalesInvoiceHeader.objects.filter(
            entity_id=header.entity_id,
            entityfinid_id=header.entityfinid_id,
            doc_type=header.doc_type,
            seller_gstin__iexact=seller_gstin,
            invoice_number__iexact=invoice_number,
        )
        if header.id:
            qs = qs.exclude(id=header.id)

        if qs.exists():
            raise ValueError(
                f"Duplicate invoice_number '{invoice_number}' for seller GSTIN '{seller_gstin}' in the same financial year."
            )

    @staticmethod
    def _validate_shipping_detail_for_customer(*, customer_id: Optional[int], shipping_detail_id: Optional[int]) -> None:
        if not shipping_detail_id:
            return
        if not customer_id:
            raise ValueError("Customer must be set before selecting shipping_detail.")

        ok = ShippingDetails.objects.filter(id=shipping_detail_id, account_id=customer_id).exists()
        if not ok:
            raise ValueError("Shipping detail does not belong to selected customer.")

    @staticmethod
    def _resolve_default_shipping_detail_id(*, customer_id: Optional[int]) -> Optional[int]:
        """
        Optional convenience: pick customer's primary shipping detail.
        """
        if not customer_id:
            return None
        sd = (
            ShippingDetails.objects
            .filter(account_id=customer_id, isprimary=True)
            .only("id")
            .first()
        )
        return sd.id if sd else None

    @staticmethod
    def freeze_ship_to_snapshot(*, header: SalesInvoiceHeader) -> None:
        """
        Freeze ship-to address into snapshot for audit/printing.
        Call on CONFIRM / POST (idempotent).
        """
        sd = header.shipping_detail
        if not sd:
            return

        state_code = ""
        if sd.state_id:
            state_code = (
                getattr(sd.state, "gst_state_code", None)
                or getattr(sd.state, "code", None)
                or ""
            )

        SalesInvoiceShipToSnapshot.objects.update_or_create(
            header=header,
            defaults=dict(
                # âœ… include scope if your snapshot is EntityScopedModel
                entity_id=header.entity_id,
                entityfinid_id=header.entityfinid_id,
                subentity_id=header.subentity_id,

                address1=sd.address1 or "",
                address2=sd.address2 or "",
                city=(sd.city.cityname if sd.city_id else "") or "",
                state_code=state_code or "",
                pincode=(sd.pincode or "")[:10],
                full_name=sd.full_name or "",
                phone=sd.phoneno or "",
                email=sd.emailid or "",
            ),
        )

    @staticmethod
    def _doc_key_for_doc_type(doc_type: int) -> str:
        if int(doc_type) == int(SalesInvoiceHeader.DocType.CREDIT_NOTE):
            return "sales_credit_note"
        if int(doc_type) == int(SalesInvoiceHeader.DocType.DEBIT_NOTE):
            return "sales_debit_note"
        return "sales_invoice"

    @staticmethod
    def _build_invoice_number(doc_type: int, doc_code: str, doc_no: int) -> str:
        if int(doc_type) == int(SalesInvoiceHeader.DocType.CREDIT_NOTE):
            prefix = "SCN"
        elif int(doc_type) == int(SalesInvoiceHeader.DocType.DEBIT_NOTE):
            prefix = "SDN"
        else:
            prefix = "SI"
        return f"{prefix}-{doc_code}-{doc_no}"

    @classmethod
    def ensure_doc_number(cls, *, header: SalesInvoiceHeader, user=None) -> None:
        """
        Allocate doc_no + invoice_number ONLY when confirming/posting.
        Safe to call multiple times (idempotent if doc_no already exists).
        """
        if header.doc_no:
            return

        # Default doc_code from settings if missing
        settings_obj = cls.get_settings(header.entity_id, header.subentity_id, entityfinid_id=getattr(header, "entityfinid_id", None))

        if not header.doc_code:
            if int(header.doc_type) == int(SalesInvoiceHeader.DocType.CREDIT_NOTE):
                header.doc_code = settings_obj.default_doc_code_cn
            elif int(header.doc_type) == int(SalesInvoiceHeader.DocType.DEBIT_NOTE):
                header.doc_code = settings_obj.default_doc_code_dn
            else:
                header.doc_code = settings_obj.default_doc_code_invoice

        doc_key = cls._doc_key_for_doc_type(int(header.doc_type))
        dt = (
            DocumentType.objects.filter(module="sales", doc_key=doc_key, is_active=True)
            .only("id")
            .first()
        )
        if not dt:
            raise ValueError(f"DocumentType not found: sales/{doc_key}")

        # âœ… consumes number (thread-safe) ONLY now
        res = DocumentNumberService.allocate_final(
            entity_id=header.entity_id,
            entityfinid_id=header.entityfinid_id,
            subentity_id=header.subentity_id,
            doc_type_id=dt.id,
            doc_code=header.doc_code,
            on_date=header.bill_date,  # keep numbering date aligned to bill date
        )

        header.doc_no = int(res.doc_no)
        # You can use res.display_no if you want formatted number
        # header.invoice_number = res.display_no
        header.invoice_number = cls._build_invoice_number(
            int(header.doc_type), header.doc_code, int(header.doc_no)
        )
    @staticmethod
    def get_settings(entity_id: int, subentity_id: Optional[int], entityfinid_id: Optional[int] = None) -> SalesSettings:
        obj = (
            SalesSettings.objects.filter(entity_id=entity_id, subentity_id=subentity_id).first()
            or SalesSettings.objects.filter(entity_id=entity_id, subentity__isnull=True).first()
        )
        if obj:
            return obj

        if not entityfinid_id:
            return SalesSettings(
                entity_id=entity_id,
                subentity_id=subentity_id,
                default_doc_code_invoice="SINV",
                default_doc_code_cn="SCN",
                default_doc_code_dn="SDN",
                enable_round_off=True,
                round_grand_total_to=2,
            )

        return SalesSettings.objects.create(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            default_doc_code_invoice="SINV",
            default_doc_code_cn="SCN",
            default_doc_code_dn="SDN",
            enable_round_off=True,
            round_grand_total_to=2,
        )

    @staticmethod
    def assert_not_locked(*, entity_id: int, subentity_id: Optional[int], bill_date):
        lock = (
            SalesLockPeriod.objects.filter(entity_id=entity_id, subentity_id=subentity_id, lock_date__gte=bill_date)
            .order_by("-lock_date")
            .first()
        )
        # If entity+subentity lock not found, check entity-only lock
        if not lock:
            lock = (
                SalesLockPeriod.objects.filter(entity_id=entity_id, subentity__isnull=True, lock_date__gte=bill_date)
                .order_by("-lock_date")
                .first()
            )
        if lock:
            raise ValueError(f"Period is locked up to {lock.lock_date}. {lock.reason or ''}".strip())

    @staticmethod
    def _validate_doc_linkage(*, doc_type: int, original_invoice, entity_id: int, entityfinid_id: int, subentity_id: Optional[int], customer_id: Optional[int]) -> None:
        if int(doc_type) in (
            int(SalesInvoiceHeader.DocType.CREDIT_NOTE),
            int(SalesInvoiceHeader.DocType.DEBIT_NOTE),
        ):
            if not original_invoice:
                raise ValueError("original_invoice is required for Credit Note / Debit Note.")
            if int(original_invoice.entity_id) != int(entity_id) or int(original_invoice.entityfinid_id) != int(entityfinid_id):
                raise ValueError("original_invoice must belong to same entity and financial year.")
            if (original_invoice.subentity_id or None) != (subentity_id or None):
                raise ValueError("original_invoice must belong to same subentity scope.")
            if customer_id and int(original_invoice.customer_id or 0) != int(customer_id):
                raise ValueError("original_invoice customer must match current invoice customer.")
        else:
            if original_invoice is not None:
                raise ValueError("original_invoice is allowed only for Credit Note / Debit Note.")

    @staticmethod
    def _resolve_original_invoice_from_reference(
        *,
        reference: Optional[str],
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        customer_id: Optional[int],
    ):
        ref = (reference or "").strip()
        if not ref:
            return None

        qs = SalesInvoiceHeader.objects.filter(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            doc_type=SalesInvoiceHeader.DocType.TAX_INVOICE,
        )
        if subentity_id is None:
            qs = qs.filter(subentity__isnull=True)
        else:
            qs = qs.filter(subentity_id=subentity_id)
        if customer_id:
            qs = qs.filter(customer_id=customer_id)

        matches = []
        if ref.isdigit():
            nref = int(ref)
            # Support legacy UI behavior where reference may carry source invoice id.
            matches.extend(list(qs.filter(id=nref)[:3]))
            matches.extend(list(qs.filter(doc_no=nref)[:3]))
        if not matches:
            matches.extend(list(qs.filter(invoice_number__iexact=ref)[:3]))

        uniq = []
        seen = set()
        for row in matches:
            if row.id not in seen:
                seen.add(row.id)
                uniq.append(row)

        if len(uniq) > 1:
            raise ValueError(
                f"Reference '{ref}' matches multiple invoices. Please pass explicit original_invoice id."
            )
        return uniq[0] if uniq else None

    @staticmethod
    def _aggregate_adjustment_totals(*, original_invoice_id: int, doc_type: int, exclude_header_id: Optional[int] = None) -> dict:
        qs = SalesInvoiceHeader.objects.filter(
            original_invoice_id=original_invoice_id,
            doc_type=doc_type,
        ).exclude(status=SalesInvoiceHeader.Status.CANCELLED)
        if exclude_header_id:
            qs = qs.exclude(id=exclude_header_id)

        agg = qs.aggregate(
            taxable=Sum("total_taxable_value"),
            cgst=Sum("total_cgst"),
            sgst=Sum("total_sgst"),
            igst=Sum("total_igst"),
            cess=Sum("total_cess"),
            grand=Sum("grand_total"),
        )
        return {
            "total_taxable_value": q2(agg.get("taxable") or ZERO2),
            "total_cgst": q2(agg.get("cgst") or ZERO2),
            "total_sgst": q2(agg.get("sgst") or ZERO2),
            "total_igst": q2(agg.get("igst") or ZERO2),
            "total_cess": q2(agg.get("cess") or ZERO2),
            "grand_total": q2(agg.get("grand") or ZERO2),
        }

    @classmethod
    def _validate_adjustment_caps(cls, *, header: SalesInvoiceHeader) -> None:
        doc_type = int(header.doc_type or 0)
        if doc_type not in (
            int(SalesInvoiceHeader.DocType.CREDIT_NOTE),
            int(SalesInvoiceHeader.DocType.DEBIT_NOTE),
        ):
            return
        if not header.original_invoice_id:
            raise ValueError("original_invoice is required for Credit Note / Debit Note.")

        original = header.original_invoice
        previous = cls._aggregate_adjustment_totals(
            original_invoice_id=original.id,
            doc_type=doc_type,
            exclude_header_id=header.id,
        )
        tol = Decimal("0.05")
        checks = [
            "total_taxable_value",
            "total_cgst",
            "total_sgst",
            "total_igst",
            "total_cess",
            "grand_total",
        ]
        for f in checks:
            cumulative = q2(previous[f] + q2(getattr(header, f, ZERO2) or ZERO2))
            cap = q2(getattr(original, f, ZERO2) or ZERO2)
            if cumulative - cap > tol:
                kind = "Credit Note" if doc_type == int(SalesInvoiceHeader.DocType.CREDIT_NOTE) else "Debit Note"
                raise ValueError(
                    f"{kind} cumulative {f} exceeds original invoice cap. "
                    f"Allowed={cap}, cumulative={cumulative}."
                )

    @staticmethod
    def _gross_receivable(header: SalesInvoiceHeader) -> Decimal:
        return q2((header.grand_total or ZERO2) + (header.tcs_amount or ZERO2))

    @staticmethod
    def _correction_audit_reason(correction: SalesInvoiceHeader) -> Optional[str]:
        remarks = str(getattr(correction, "remarks", "") or "").strip()
        if remarks:
            return remarks
        reference = str(getattr(correction, "reference", "") or "").strip()
        if reference:
            return reference
        try:
            label = correction.get_note_reason_display()
        except Exception:
            label = None
        return str(label).strip() or None if label else None

    @staticmethod
    def append_correction_audit_event(
        *,
        original: SalesInvoiceHeader,
        correction: SalesInvoiceHeader,
        user_id: Optional[int],
    ) -> None:
        event = {
            "original_invoice_id": original.id,
            "correction_document_id": correction.id,
            "user_id": user_id,
            "timestamp": timezone.now().isoformat(),
            "reason": SalesInvoiceService._correction_audit_reason(correction),
            "correction_type": (
                "credit_note"
                if int(getattr(correction, "doc_type", 0) or 0) == int(SalesInvoiceHeader.DocType.CREDIT_NOTE)
                else "debit_note"
            ),
            "gst_period_impact": correction.bill_date.strftime("%Y-%m") if getattr(correction, "bill_date", None) else None,
            "old_value": {
                "bill_date": original.bill_date.isoformat() if getattr(original, "bill_date", None) else None,
                "posting_date": original.posting_date.isoformat() if getattr(original, "posting_date", None) else None,
                "grand_total": str(q2(getattr(original, "grand_total", ZERO2) or ZERO2)),
            },
            "new_value": {
                "bill_date": correction.bill_date.isoformat() if getattr(correction, "bill_date", None) else None,
                "posting_date": correction.posting_date.isoformat() if getattr(correction, "posting_date", None) else None,
                "grand_total": str(q2(getattr(correction, "grand_total", ZERO2) or ZERO2)),
            },
        }

        original_notes = dict(getattr(original, "custom_fields_json", None) or {})
        correction_history = list(original_notes.get("correction_history") or [])
        correction_history.append(event)
        original_notes["correction_history"] = correction_history
        original.custom_fields_json = original_notes
        original.save(update_fields=["custom_fields_json", "updated_at"])

        correction_notes = dict(getattr(correction, "custom_fields_json", None) or {})
        correction_notes["correction_origin"] = event
        correction.custom_fields_json = correction_notes
        correction.save(update_fields=["custom_fields_json", "updated_at"])

    @classmethod
    def requires_current_period_correction(cls, *, header: SalesInvoiceHeader) -> bool:
        if int(getattr(header, "doc_type", 0) or 0) != int(SalesInvoiceHeader.DocType.TAX_INVOICE):
            return False
        if int(getattr(header, "status", 0) or 0) != int(SalesInvoiceHeader.Status.POSTED):
            return False
        try:
            cls.assert_not_locked(
                entity_id=header.entity_id,
                subentity_id=header.subentity_id,
                bill_date=header.bill_date,
            )
        except ValueError:
            return True
        return False

    @classmethod
    def next_open_correction_date(cls, *, header: SalesInvoiceHeader) -> date:
        candidate = max(getattr(header, "bill_date", None) or timezone.localdate(), timezone.localdate())
        for _ in range(370):
            locked, _ = SalesSettingsService.is_locked(header.entity_id, header.subentity_id, candidate)
            if not locked:
                return candidate
            candidate = candidate + timedelta(days=1)
        raise ValueError("Unable to resolve an open correction date for sales amendment.")

    @staticmethod
    def _note_line_payload_from_original(line: SalesInvoiceLine) -> dict:
        return {
            "line_no": int(getattr(line, "line_no", 0) or 0),
            "product": getattr(line, "product", None),
            "productDesc": getattr(line, "productDesc", ""),
            "batch_number": getattr(line, "batch_number", ""),
            "manufacture_date": getattr(line, "manufacture_date", None),
            "expiry_date": getattr(line, "expiry_date", None),
            "uom": getattr(line, "uom", None),
            "hsn_sac_code": getattr(line, "hsn_sac_code", ""),
            "is_service": bool(getattr(line, "is_service", False)),
            "qty": f"{Decimal(getattr(line, 'qty', ZERO4) or ZERO4):.3f}",
            "free_qty": f"{Decimal(getattr(line, 'free_qty', ZERO4) or ZERO4):.3f}",
            "rate": str(q4(getattr(line, "rate", ZERO4))),
            "is_rate_inclusive_of_tax": bool(getattr(line, "is_rate_inclusive_of_tax", False)),
            "discount_type": int(getattr(line, "discount_type", 0) or 0),
            "discount_percent": str(q4(getattr(line, "discount_percent", ZERO4))),
            "discount_amount": str(q2(getattr(line, "discount_amount", ZERO2))),
            "taxability": int(getattr(line, "taxability", SalesInvoiceHeader.Taxability.TAXABLE) or SalesInvoiceHeader.Taxability.TAXABLE),
            "gst_rate": f"{Decimal(getattr(line, 'gst_rate', ZERO2) or ZERO2):.2f}",
            "cess_percent": f"{Decimal(getattr(line, 'cess_percent', ZERO2) or ZERO2):.2f}",
            "cess_amount": str(q2(getattr(line, "cess_amount", ZERO2))),
            "sales_account": getattr(line, "sales_account", None),
        }

    @staticmethod
    def _note_charge_payload_from_original(charge: SalesChargeLine) -> dict:
        return {
            "line_no": int(getattr(charge, "line_no", 0) or 0),
            "charge_type": getattr(charge, "charge_type", SalesChargeLine.ChargeType.OTHER),
            "description": getattr(charge, "description", ""),
            "taxability": int(getattr(charge, "taxability", SalesInvoiceHeader.Taxability.TAXABLE) or SalesInvoiceHeader.Taxability.TAXABLE),
            "is_service": bool(getattr(charge, "is_service", True)),
            "hsn_sac_code": getattr(charge, "hsn_sac_code", ""),
            "is_rate_inclusive_of_tax": bool(getattr(charge, "is_rate_inclusive_of_tax", False)),
            "taxable_value": str(q2(getattr(charge, "taxable_value", ZERO2))),
            "gst_rate": str(q2(getattr(charge, "gst_rate", ZERO2))),
            "revenue_account": getattr(charge, "revenue_account", None),
        }

    @classmethod
    def create_current_period_reversal_credit_note(
        cls,
        *,
        original: SalesInvoiceHeader,
        user,
        reason: str = "",
    ) -> SalesInvoiceHeader:
        correction_date = cls.next_open_correction_date(header=original)
        lines = [
            cls._note_line_payload_from_original(line)
            for line in original.lines.all().order_by("line_no", "id")
        ]
        charges = [
            cls._note_charge_payload_from_original(charge)
            for charge in original.charges.all().order_by("line_no", "id")
        ]
        note = cls.create_with_lines(
            entity_id=original.entity_id,
            entityfinid_id=original.entityfinid_id,
            subentity_id=original.subentity_id,
            header_data={
                "doc_type": int(SalesInvoiceHeader.DocType.CREDIT_NOTE),
                "bill_date": correction_date,
                "posting_date": correction_date,
                "doc_code": "SCN",
                "customer_id": original.customer_id,
                "customer_name": getattr(original, "customer_name", ""),
                "customer_gstin": getattr(original, "customer_gstin", ""),
                "customer_state_code": getattr(original, "customer_state_code", ""),
                "seller_gstin": getattr(original, "seller_gstin", ""),
                "seller_state_code": getattr(original, "seller_state_code", ""),
                "place_of_supply_state_code": getattr(original, "place_of_supply_state_code", ""),
                "supply_category": int(getattr(original, "supply_category", SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B) or SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B),
                "taxability": int(getattr(original, "taxability", SalesInvoiceHeader.Taxability.TAXABLE) or SalesInvoiceHeader.Taxability.TAXABLE),
                "reference": getattr(original, "invoice_number", "") or getattr(original, "reference", ""),
                "remarks": (reason or "").strip() or "Locked-period cancellation reversal",
                "original_invoice": original,
                "note_reason": SalesInvoiceHeader.NoteReason.OTHER,
                "affects_inventory": False,
                "is_bill_to_ship_to_same": bool(getattr(original, "is_bill_to_ship_to_same", True)),
                "shipping_detail_id": getattr(original, "shipping_detail_id", None),
            },
            lines_data=lines,
            charges_data=charges,
            user=user,
        )
        note = cls.confirm(header=note, user=user)
        note = cls.post(header=note, user=user)
        return note

    @staticmethod
    def recompute_settlement_fields(*, header: SalesInvoiceHeader) -> None:
        gross = SalesInvoiceService._gross_receivable(header)
        settled = q2(getattr(header, "settled_amount", ZERO2) or ZERO2)
        if settled < ZERO2:
            settled = ZERO2
        if settled > gross:
            settled = gross

        outstanding = q2(gross - settled)
        if outstanding <= ZERO2:
            status = SalesInvoiceHeader.SettlementStatus.SETTLED
            outstanding = ZERO2
        elif settled > ZERO2:
            status = SalesInvoiceHeader.SettlementStatus.PARTIAL
        else:
            status = SalesInvoiceHeader.SettlementStatus.OPEN

        header.settled_amount = settled
        header.outstanding_amount = outstanding
        header.settlement_status = int(status)

    @staticmethod
    def apply_product_line_defaults(*, header_taxability: int, lines_data: list[dict]) -> None:
        for row in lines_data or []:
            if row.get("taxability") not in (None, ""):
                continue
            product = row.get("product")
            if product not in (None, "", 0):
                row["taxability"] = resolve_product_default_taxability(
                    product=product if hasattr(product, "_meta") else None,
                    product_id=getattr(product, "pk", product),
                    fallback=header_taxability,
                )
            else:
                row["taxability"] = int(header_taxability)

    # -------------------------
    # Public API: Create/Update
    # -------------------------
    @classmethod
    @transaction.atomic
    def create_with_lines(
        cls,
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        header_data: dict,
        lines_data: list,
        charges_data: Optional[list],
        user,
    ) -> SalesInvoiceHeader:
        round_off_explicit = "round_off" in (header_data or {})
        grand_total_hint = (header_data or {}).get("grand_total") if "grand_total" in (header_data or {}) else None
        header_data = cls._sanitize_header_data_inputs(header_data)
        bill_date = header_data.get("bill_date") or timezone.localdate()
        cls.assert_not_locked(entity_id=entity_id, subentity_id=subentity_id, bill_date=bill_date)

        # ---- resolve customer_id ----
        customer_id: Optional[int] = None
        if header_data.get("customer_id"):
            customer_id = int(header_data["customer_id"])
        elif header_data.get("customer"):
            customer_id = int(header_data["customer"].id)

        customer_ledger_id = cls._resolve_customer_ledger_id(customer_id)

        # ---- resolve shipping_detail_id ----
        shipping_detail_id: Optional[int] = None
        if "shipping_detail_id" in header_data:
            shipping_detail_id = int(header_data.get("shipping_detail_id") or 0) or None
        elif header_data.get("shipping_detail"):
            shipping_detail_id = int(header_data["shipping_detail"].id)

        is_same = bool(header_data.get("is_bill_to_ship_to_same", True))

        # auto-pick primary if same and not provided
        if is_same and not shipping_detail_id:
            shipping_detail_id = cls._resolve_default_shipping_detail_id(customer_id=customer_id)

        cls._validate_shipping_detail_for_customer(
            customer_id=customer_id,
            shipping_detail_id=shipping_detail_id,
        )

        doc_type = int(header_data.get("doc_type") or SalesInvoiceHeader.DocType.TAX_INVOICE)
        original_invoice = header_data.get("original_invoice")
        if (
            original_invoice is None
            and doc_type in (int(SalesInvoiceHeader.DocType.CREDIT_NOTE), int(SalesInvoiceHeader.DocType.DEBIT_NOTE))
        ):
            original_invoice = cls._resolve_original_invoice_from_reference(
                reference=header_data.get("reference"),
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=subentity_id,
                customer_id=customer_id,
            )
            if original_invoice is not None:
                header_data["original_invoice"] = original_invoice
        if original_invoice is not None and doc_type in (int(SalesInvoiceHeader.DocType.CREDIT_NOTE), int(SalesInvoiceHeader.DocType.DEBIT_NOTE)):
            cls._align_note_tax_scope_from_original_invoice(header_data=header_data, original_invoice=original_invoice)
        cls._validate_doc_linkage(
            doc_type=doc_type,
            original_invoice=original_invoice,
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            customer_id=customer_id,
        )

        # ---- remove model instances from header_data ----
        header_data = dict(header_data)
        header_data.pop("customer", None)
        header_data.pop("shipping_detail", None)
        # keep ids only
        if customer_id is not None:
            header_data["customer_id"] = customer_id
        header_data["customer_ledger_id"] = customer_ledger_id
        header_data["shipping_detail_id"] = shipping_detail_id  # can be None

        header = SalesInvoiceHeader(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            created_by=user,
            updated_by=user,
            **header_data,
        )

        header.status = SalesInvoiceHeader.Status.DRAFT

        cls._prepare_header_for_persistence(header=header)

        header.full_clean(exclude=None)
        header.save()

        cls.apply_product_line_defaults(
            header_taxability=int(getattr(header, "taxability", SalesInvoiceHeader.Taxability.TAXABLE)),
            lines_data=lines_data,
        )
        cls.upsert_lines(header=header, incoming_lines=lines_data, user=user, allow_delete=True)
        cls.validate_charges(header=header, charges=charges_data or [])
        cls.upsert_charges(header=header, incoming_charges=charges_data or [], user=user, allow_delete=True)
        cls._recompute_invoice_state(
            header=header,
            user=user,
            round_off_explicit=round_off_explicit,
            grand_total_hint=grand_total_hint,
        )
        header.save(update_fields=[
            "gst_compliance_mode",
            "is_einvoice_applicable",
            "is_eway_applicable",
            "einvoice_applicable_manual",
            "eway_applicable_manual",
            "compliance_override_reason",
            "compliance_override_at",
            "compliance_override_by",
            "settled_amount",
            "outstanding_amount",
            "settlement_status",
            "updated_at",
        ])

        if original_invoice is not None and doc_type in (
            int(SalesInvoiceHeader.DocType.CREDIT_NOTE),
            int(SalesInvoiceHeader.DocType.DEBIT_NOTE),
        ):
            cls.append_correction_audit_event(
                original=original_invoice,
                correction=header,
                user_id=getattr(user, "id", None),
            )

        return header

    @classmethod
    @transaction.atomic
    def update_with_lines(
        cls,
        *,
        header: SalesInvoiceHeader,
        header_data: dict,
        lines_data: Optional[list],
        charges_data: Optional[list],
        user,
    ) -> SalesInvoiceHeader:
        round_off_explicit = "round_off" in (header_data or {})
        grand_total_hint = (header_data or {}).get("grand_total") if "grand_total" in (header_data or {}) else None
        header_data = cls._sanitize_header_data_inputs(header_data)
        if header.status in (SalesInvoiceHeader.Status.POSTED, SalesInvoiceHeader.Status.CANCELLED):
            raise ValueError("Posted/Cancelled invoices cannot be edited.")
        if int(header.status) == int(SalesInvoiceHeader.Status.CONFIRMED):
            controls = cls._policy_controls(header)
            allow_edit_confirmed = str(controls.get("allow_edit_confirmed", "on")).lower().strip()
            if allow_edit_confirmed == "off":
                raise ValueError("Confirmed invoice editing is disabled by sales policy.")

        bill_date = header_data.get("bill_date") or header.bill_date
        cls.assert_not_locked(entity_id=header.entity_id, subentity_id=header.subentity_id, bill_date=bill_date)

        header_data = dict(header_data)

        # ---- resolve customer_id ----
        customer_id = header.customer_id
        if header_data.get("customer_id"):
            customer_id = int(header_data["customer_id"])
        elif header_data.get("customer"):
            customer_id = int(header_data["customer"].id)

        customer_ledger_id = cls._resolve_customer_ledger_id(customer_id)

        # ---- resolve shipping_detail_id ----
        shipping_detail_id = header.shipping_detail_id
        shipping_detail_changed = ("shipping_detail_id" in header_data) or ("shipping_detail" in header_data)

        if "shipping_detail_id" in header_data:
            shipping_detail_id = int(header_data.get("shipping_detail_id") or 0) or None
        elif "shipping_detail" in header_data:
            sd_obj = header_data.get("shipping_detail")
            shipping_detail_id = int(sd_obj.id) if sd_obj else None

        is_same = bool(header_data.get("is_bill_to_ship_to_same", header.is_bill_to_ship_to_same))

        if is_same and not shipping_detail_id:
            shipping_detail_id = cls._resolve_default_shipping_detail_id(customer_id=customer_id)

        customer_changed = ("customer_id" in header_data) or ("customer" in header_data)
        if customer_changed or shipping_detail_changed:
            cls._validate_shipping_detail_for_customer(
                customer_id=customer_id,
                shipping_detail_id=shipping_detail_id,
            )

        doc_type = int(header_data.get("doc_type", header.doc_type))
        original_invoice = header_data.get("original_invoice", header.original_invoice)
        if (
            original_invoice is None
            and doc_type in (int(SalesInvoiceHeader.DocType.CREDIT_NOTE), int(SalesInvoiceHeader.DocType.DEBIT_NOTE))
        ):
            original_invoice = cls._resolve_original_invoice_from_reference(
                reference=header_data.get("reference", header.reference),
                entity_id=header.entity_id,
                entityfinid_id=header.entityfinid_id,
                subentity_id=header.subentity_id,
                customer_id=customer_id,
            )
            if original_invoice is not None:
                header_data["original_invoice"] = original_invoice
        if original_invoice is not None and doc_type in (int(SalesInvoiceHeader.DocType.CREDIT_NOTE), int(SalesInvoiceHeader.DocType.DEBIT_NOTE)):
            cls._align_note_tax_scope_from_original_invoice(header_data=header_data, original_invoice=original_invoice)
        cls._validate_doc_linkage(
            doc_type=doc_type,
            original_invoice=original_invoice,
            entity_id=header.entity_id,
            entityfinid_id=header.entityfinid_id,
            subentity_id=header.subentity_id,
            customer_id=customer_id,
        )

        # ---- strip instances + assign ids ----
        header_data.pop("customer", None)
        header_data.pop("shipping_detail", None)
        header_data["customer_id"] = customer_id
        header_data["customer_ledger_id"] = customer_ledger_id
        header_data["shipping_detail_id"] = shipping_detail_id

        # ---- apply fields ----
        for k, v in header_data.items():
            setattr(header, k, v)

        header.updated_by = user

        cls._prepare_header_for_persistence(header=header)

        header.full_clean(exclude=None)
        header.save()

        if lines_data is not None:
            cls.apply_product_line_defaults(
                header_taxability=int(getattr(header, "taxability", SalesInvoiceHeader.Taxability.TAXABLE)),
                lines_data=lines_data,
            )
            cls.upsert_lines(header=header, incoming_lines=lines_data, user=user, allow_delete=True)
        if charges_data is not None:
            cls.validate_charges(header=header, charges=charges_data)
            cls.upsert_charges(header=header, incoming_charges=charges_data, user=user, allow_delete=True)
        cls._recompute_invoice_state(
            header=header,
            user=user,
            round_off_explicit=round_off_explicit,
            grand_total_hint=grand_total_hint,
        )
        header.save(update_fields=[
            "gst_compliance_mode",
            "is_einvoice_applicable",
            "is_eway_applicable",
            "einvoice_applicable_manual",
            "eway_applicable_manual",
            "compliance_override_reason",
            "compliance_override_at",
            "compliance_override_by",
            "settled_amount",
            "outstanding_amount",
            "settlement_status",
            "updated_at",
        ])


        return header

    # -------------------------
    # Dates / regime
    # -------------------------
    @staticmethod
    def apply_dates(header: SalesInvoiceHeader):
        """
        Your rule:
          - posting_date defaults to bill_date
          - due_date = bill_date + credit_days (>= bill_date)
        """
        if not header.posting_date:
            header.posting_date = header.bill_date
        credit_days = int(header.credit_days or 0)
        due = header.bill_date + timezone.timedelta(days=credit_days)
        if due < header.bill_date:
            due = header.bill_date
        header.due_date = due

    @staticmethod
    def derive_tax_regime(header: SalesInvoiceHeader):
        """
        If seller_state != place_of_supply => IGST, else CGST+SGST.
        """
        seller = (header.seller_state_code or "").strip()
        pos = (header.place_of_supply_state_code or "").strip()
        if seller and pos and seller != pos:
            header.tax_regime = SalesInvoiceHeader.TaxRegime.INTER_STATE
            header.is_igst = True
        else:
            header.tax_regime = SalesInvoiceHeader.TaxRegime.INTRA_STATE
            header.is_igst = False

    # -------------------------
    # Lines upsert + compute
    # -------------------------
    @staticmethod
    def upsert_lines(*, header, incoming_lines, user, allow_delete: bool) -> None:
        incoming_lines = incoming_lines or []

        # âœ… Always compute max from DB (ignores any deferred manager weirdness)
        max_ln = int(header.lines.aggregate(m=Max("line_no")).get("m") or 0)

        # âœ… Build existing maps from DB (no .only(), no defers)
        existing_rows = list(header.lines.all().values("id", "line_no"))
        existing_by_id = {int(r["id"]): int(r["line_no"] or 0) for r in existing_rows}
        existing_by_lineno = {int(r["line_no"]): int(r["id"]) for r in existing_rows if r["line_no"]}

        # ---- validate duplicate line_no in payload itself ----
        payload_linenos = []
        for r in incoming_lines:
            ln = r.get("line_no", None)
            if ln is not None:
                try:
                    payload_linenos.append(int(ln))
                except Exception:
                    pass
        dupes = {x for x in payload_linenos if x > 0 and payload_linenos.count(x) > 1}
        if dupes:
            raise ValidationError({"lines": [f"Duplicate line_no in payload: {sorted(dupes)}"]})

        retained_ids = set()
        for row in incoming_lines:
            row_id = int(row.get("id") or 0)
            row_ln = int(row.get("line_no") or 0)
            if row_id and row_id in existing_by_id:
                retained_ids.add(row_id)
                continue
            if row_id == 0 and row_ln > 0 and row_ln in existing_by_lineno:
                retained_ids.add(existing_by_lineno[row_ln])

        if allow_delete:
            # Delete rows dropped from the payload before inserts so newly created
            # lines can reuse the freed line_no within the same invoice.
            to_delete = [lid for lid in existing_by_id.keys() if lid not in retained_ids]
            if to_delete:
                SalesInvoiceLine.objects.filter(header=header, id__in=to_delete).delete()
                existing_rows = [r for r in existing_rows if int(r["id"]) not in to_delete]
                existing_by_id = {int(r["id"]): int(r["line_no"] or 0) for r in existing_rows}
                existing_by_lineno = {int(r["line_no"]): int(r["id"]) for r in existing_rows if r["line_no"]}
                max_ln = int(header.lines.aggregate(m=Max("line_no")).get("m") or 0)

        seen_ids = set()

        for row in incoming_lines:
            row_id = int(row.get("id") or 0)
            row_ln = int(row.get("line_no") or 0)

            # âœ… If UI forgot id but line_no matches existing, treat as UPDATE
            if row_id == 0 and row_ln > 0 and row_ln in existing_by_lineno:
                row_id = existing_by_lineno[row_ln]

            # --------------------------
            # UPDATE
            # --------------------------
            if row_id and row_id in existing_by_id:
                line = SalesInvoiceLine.objects.get(id=row_id, header=header)
                seen_ids.add(row_id)

                SalesInvoiceService.apply_line_inputs(line, row, default_taxability=int(header.taxability or SalesInvoiceHeader.Taxability.TAXABLE))

                # allow changing line_no safely
                if row_ln > 0 and row_ln != int(line.line_no):
                    if row_ln in existing_by_lineno and existing_by_lineno[row_ln] != row_id:
                        raise ValidationError({"lines": [f"line_no {row_ln} already exists for this invoice."]})
                    line.line_no = row_ln

                line.updated_by = user
                SalesInvoiceService.compute_line_amounts(header, line)

                try:
                    line.full_clean()
                except DjangoValidationError as e:
                    raise ValidationError(e.message_dict)

                line.save()
                continue

            # If id provided but not found under this header -> reject
            if row_id and row_id not in existing_by_id:
                raise ValidationError({"lines": [f"Line id={row_id} not found for this invoice."]})

            # --------------------------
            # CREATE
            # --------------------------
            desired_ln = row_ln
            if desired_ln <= 0:
                max_ln += 1
                desired_ln = max_ln

            # If line_no exists, it's an update case; but we already resolved above.
            if desired_ln in existing_by_lineno:
                raise ValidationError({"lines": [f"line_no {desired_ln} already exists; send its id to update it."]})

            line = SalesInvoiceLine(
                header=header,
                entity_id=header.entity_id,
                entityfinid_id=header.entityfinid_id,
                subentity_id=header.subentity_id,
                line_no=desired_ln,
                created_by=user,
                updated_by=user,
            )

            SalesInvoiceService.apply_line_inputs(line, row, default_taxability=int(header.taxability or SalesInvoiceHeader.Taxability.TAXABLE))
            SalesInvoiceService.compute_line_amounts(header, line)

            try:
                line.full_clean()
            except DjangoValidationError as e:
                raise ValidationError(e.message_dict)

            line.save()

        # --------------------------
        # DELETE missing rows
        # --------------------------
        # Rows omitted from the payload were already deleted before inserts.

    @staticmethod
    def apply_line_inputs(line: SalesInvoiceLine, row: dict, *, default_taxability: int) -> None:
        """
        IMPORTANT: line_no is intentionally NOT set here.
        That prevents accidental overwrite during create and avoids unique collisions.
        """
        for fld in [
            "product",
            "productDesc",
            "batch_number",
            "manufacture_date",
            "expiry_date",
            "uom",
            "hsn_sac_code",
            "is_service",
            "qty",
            "free_qty",
            "rate",
            "is_rate_inclusive_of_tax",
            "discount_type",
            "discount_percent",
            "discount_amount",
            "taxability",
            "gst_rate",
            "cess_percent",
            "cess_amount",
            "sales_account",
        ]:
            if fld in row:
                setattr(line, fld, row.get(fld))

        if getattr(line, "taxability", None) in (None, ""):
            product = getattr(line, "product", None)
            if product is not None:
                line.taxability = resolve_product_default_taxability(
                    product=product,
                    product_id=getattr(product, "pk", None),
                    fallback=default_taxability,
                )
            else:
                line.taxability = int(default_taxability)

    @staticmethod
    def compute_line_amounts(header: SalesInvoiceHeader, line: SalesInvoiceLine):
        """
        Compute:
          - taxable_value
          - gst split
          - cess
          - line_total
        Inputs expected from UI: qty, rate, discount, gst_rate, cess
        """
        qty = q4(line.qty)
        free_qty = q4(line.free_qty)
        bill_qty = qty  # taxable usually on billed qty (not free)
        rate = q4(line.rate)
        gst_rate = q4(line.gst_rate)
        taxability = int(getattr(line, "taxability", SalesInvoiceHeader.Taxability.TAXABLE) or SalesInvoiceHeader.Taxability.TAXABLE)
        hsn = (line.hsn_sac_code or "").strip()

        if qty < ZERO4 or free_qty < ZERO4:
            raise ValidationError({"lines": [f"Line {line.line_no}: qty/free_qty cannot be negative."]})
        if rate < ZERO4:
            raise ValidationError({"lines": [f"Line {line.line_no}: rate cannot be negative."]})
        if gst_rate < ZERO4 or gst_rate > Decimal("100.0000"):
            raise ValidationError({"lines": [f"Line {line.line_no}: gst_rate must be between 0 and 100."]})
        if taxability != int(SalesInvoiceHeader.Taxability.TAXABLE):
            gst_rate = ZERO4
            line.gst_rate = ZERO2
            line.cess_percent = ZERO2
            line.cess_amount = ZERO2
        if gst_rate > ZERO4 and bill_qty > ZERO4 and not hsn:
            raise ValidationError({"lines": [f"Line {line.line_no}: HSN/SAC is required when GST applies."]})

        gross = q2(bill_qty * rate)

        # discount
        disc = ZERO2
        if int(line.discount_type or 0) == SalesInvoiceLine.DiscountType.PERCENT:
            disc = q2(gross * q4(line.discount_percent) / Decimal("100"))
        elif int(line.discount_type or 0) == SalesInvoiceLine.DiscountType.AMOUNT:
            disc = q2(line.discount_amount)

        if disc < ZERO2:
            disc = ZERO2
        if disc > gross:
            disc = gross

        net = q2(gross - disc)

        # If rate is inclusive of tax, back-calculate taxable
        taxable = net
        cgst = sgst = igst = ZERO2
        tax_total = ZERO2

        if line.is_rate_inclusive_of_tax and gst_rate > ZERO4:
            # taxable = net / (1 + gst_rate/100)
            taxable = q2(net / (Decimal("1.0") + (gst_rate / Decimal("100"))))
            tax_total = q2(net - taxable)
        elif gst_rate > ZERO4:
            tax_total = q2(taxable * gst_rate / Decimal("100"))

        # Align with purchase + UI preview behavior:
        # ad-valorem cess should be derived from the taxable base, not the
        # gross inclusive amount, otherwise inclusive-GST invoices can post a
        # different total than the user saw on screen.
        if taxability == int(SalesInvoiceHeader.Taxability.TAXABLE) and q4(line.cess_percent) > ZERO4:
            cess_amt = q2(taxable * q4(line.cess_percent) / Decimal("100"))
        else:
            cess_amt = ZERO2 if taxability != int(SalesInvoiceHeader.Taxability.TAXABLE) else q2(line.cess_amount)

        # Reverse-charge invoices should not carry GST/CESS amounts on invoice lines.
        if bool(getattr(header, "is_reverse_charge", False)):
            tax_total = ZERO2
            cess_amt = ZERO2

        if header.is_igst:
            igst = tax_total
        else:
            # split equally (service can later support uneven split if needed)
            cgst = q2(tax_total / Decimal("2"))
            sgst = q2(tax_total - cgst)

        line.taxable_value = taxable
        line.cgst_amount = cgst
        line.sgst_amount = sgst
        line.igst_amount = igst
        line.cess_amount = cess_amt
        line.discount_amount = disc  # normalize

        line.line_total = q2(taxable + cgst + sgst + igst + cess_amt)

    @staticmethod
    def compute_charge_amounts(*, header: SalesInvoiceHeader, row: dict) -> ChargeComputed:
        taxability = int(row.get("taxability") or SalesInvoiceHeader.Taxability.TAXABLE)
        gst_rate = q4(row.get("gst_rate") or ZERO2)
        taxable = q2(row.get("taxable_value") or ZERO2)
        inclusive = bool(row.get("is_rate_inclusive_of_tax") or False)

        # RCM normalization: charge GST must stay zero when invoice is reverse-charge.
        if bool(getattr(header, "is_reverse_charge", False)):
            taxable2 = q2(taxable)
            return ChargeComputed(
                taxable_value=taxable2,
                cgst_amount=ZERO2,
                sgst_amount=ZERO2,
                igst_amount=ZERO2,
                total_value=taxable2,
            )

        if taxability != int(SalesInvoiceHeader.Taxability.TAXABLE) or gst_rate <= ZERO2 or taxable <= ZERO2:
            taxable2 = q2(taxable)
            return ChargeComputed(
                taxable_value=taxable2,
                cgst_amount=ZERO2,
                sgst_amount=ZERO2,
                igst_amount=ZERO2,
                total_value=taxable2,
            )

        if inclusive:
            gross = q2(taxable)
            taxable = q2(gross / (Decimal("1.00") + (gst_rate / Decimal("100.00"))))

        taxable2 = q2(taxable)
        gst_amt = q2(taxable2 * gst_rate / Decimal("100.00"))
        cgst = sgst = igst = ZERO2
        if int(getattr(header, "tax_regime", int(SalesInvoiceHeader.TaxRegime.INTRA_STATE))) == int(SalesInvoiceHeader.TaxRegime.INTRA_STATE):
            cgst = q2(gst_amt / Decimal("2.00"))
            sgst = q2(gst_amt - cgst)
        else:
            igst = gst_amt
        total = q2(taxable2 + cgst + sgst + igst)
        return ChargeComputed(
            taxable_value=taxable2,
            cgst_amount=cgst,
            sgst_amount=sgst,
            igst_amount=igst,
            total_value=total,
        )

    @staticmethod
    def _resolve_charge_master(*, header: SalesInvoiceHeader, row: dict) -> dict:
        data = dict(row or {})
        raw_id = data.pop("charge_type_id", None)
        raw_type = data.get("charge_type")
        master = None

        qs = (
            SalesChargeType.objects.filter(is_active=True)
            .filter(Q(entity_id=header.entity_id) | Q(entity__isnull=True))
            .order_by("-entity_id", "id")
        )

        if raw_id not in (None, ""):
            try:
                master = qs.filter(id=int(raw_id)).first()
            except (TypeError, ValueError):
                raise ValidationError({"charges": [f"Invalid charge_type_id '{raw_id}'."]})
            if not master:
                raise ValidationError({"charges": [f"Charge type id {raw_id} not found for this entity."]})
        elif raw_type not in (None, ""):
            raw = str(raw_type).strip()
            normalized = raw.upper().replace("-", "_").replace(" ", "_")
            valid_enum_map = {str(value): value for value, _label in SalesChargeLine.ChargeType.choices}
            valid_enum_map.update(
                {
                    str(label).upper().replace("-", "_").replace(" ", "_"): value
                    for value, label in SalesChargeLine.ChargeType.choices
                }
            )

            if normalized in valid_enum_map:
                data["charge_type"] = valid_enum_map[normalized]
            else:
                master = qs.filter(code__iexact=raw).first() or qs.filter(name__iexact=raw).first()
                if not master:
                    raise ValidationError(
                        {
                            "charges": [
                                f"Invalid charge_type '{raw}'. Provide charge_type_id or a valid charge type code/name."
                            ]
                        }
                    )

        if master:
            base_map = {
                SalesChargeType.BaseCategory.FREIGHT: SalesChargeLine.ChargeType.FREIGHT,
                SalesChargeType.BaseCategory.PACKING: SalesChargeLine.ChargeType.PACKING,
                SalesChargeType.BaseCategory.INSURANCE: SalesChargeLine.ChargeType.INSURANCE,
                SalesChargeType.BaseCategory.OTHER: SalesChargeLine.ChargeType.OTHER,
            }
            data["charge_type"] = base_map.get(master.base_category, SalesChargeLine.ChargeType.OTHER)
            if not (data.get("description") or "").strip():
                data["description"] = master.name or master.description or ""
            if data.get("is_service") in (None, ""):
                data["is_service"] = bool(master.is_service)
            if not (data.get("hsn_sac_code") or "").strip():
                data["hsn_sac_code"] = (master.hsn_sac_code_default or "").strip()
            if data.get("gst_rate") in (None, ""):
                data["gst_rate"] = q4(master.gst_rate_default or ZERO2)
            if data.get("revenue_account") in (None, "") and getattr(master, "revenue_account_id", None):
                data["revenue_account"] = master.revenue_account

        if data.get("charge_type") in (None, ""):
            data["charge_type"] = SalesChargeLine.ChargeType.OTHER

        raw_taxability = data.get("taxability")
        if raw_taxability not in (None, "") and not isinstance(raw_taxability, int):
            txt = str(raw_taxability).strip()
            if txt.isdigit():
                data["taxability"] = int(txt)
            else:
                by_name = {
                    name.upper(): int(value)
                    for name, value in SalesInvoiceHeader.Taxability.__members__.items()
                }
                by_label = {
                    str(label).strip().upper(): int(value)
                    for value, label in SalesInvoiceHeader.Taxability.choices
                }
                lookup = txt.upper()
                if lookup in by_name:
                    data["taxability"] = by_name[lookup]
                elif lookup in by_label:
                    data["taxability"] = by_label[lookup]
        return data

    @staticmethod
    def validate_charges(*, header: SalesInvoiceHeader, charges: list[dict]) -> None:
        seen_line_no: set[int] = set()
        for i, row in enumerate(charges or [], start=1):
            row = SalesInvoiceService._resolve_charge_master(header=header, row=row)
            charges[i - 1] = row
            line_no_raw = row.get("line_no")
            if line_no_raw not in (None, ""):
                try:
                    line_no = int(line_no_raw)
                except (TypeError, ValueError):
                    raise ValidationError({"charges": [f"Charge row {i}: line_no must be integer."]})
                if line_no <= 0:
                    raise ValidationError({"charges": [f"Charge row {i}: line_no must be > 0."]})
                if line_no in seen_line_no:
                    raise ValidationError({"charges": [f"Charge row {i}: duplicate line_no {line_no}."]})
                seen_line_no.add(line_no)

            taxable = q2(row.get("taxable_value") or ZERO2)
            gst_rate = q2(row.get("gst_rate") or ZERO2)
            taxability = int(row.get("taxability") or SalesInvoiceHeader.Taxability.TAXABLE)
            hsn = (row.get("hsn_sac_code") or "").strip()

            if taxable < ZERO2:
                raise ValidationError({"charges": [f"Charge row {i}: taxable_value must be >= 0."]})
            if gst_rate < ZERO2 or gst_rate > Decimal("100.00"):
                raise ValidationError({"charges": [f"Charge row {i}: gst_rate must be 0..100."]})
            if taxability != int(SalesInvoiceHeader.Taxability.TAXABLE) and gst_rate > ZERO2:
                raise ValidationError({"charges": [f"Charge row {i}: gst_rate must be 0 for non-taxable charge."]})
            if gst_rate > ZERO2 and taxable > ZERO2 and not hsn:
                raise ValidationError({"charges": [f"Charge row {i}: HSN/SAC required when GST applied."]})

    @staticmethod
    def upsert_charges(*, header: SalesInvoiceHeader, incoming_charges: list[dict], user, allow_delete: bool) -> None:
        incoming_charges = incoming_charges or []
        max_ln = int(header.charges.aggregate(m=Max("line_no")).get("m") or 0)
        existing_rows = list(header.charges.all().values("id", "line_no"))
        existing_by_id = {int(r["id"]): int(r["line_no"] or 0) for r in existing_rows}
        existing_by_lineno = {int(r["line_no"]): int(r["id"]) for r in existing_rows if r["line_no"]}

        seen_ids = set()
        for row in incoming_charges:
            row = SalesInvoiceService._resolve_charge_master(header=header, row=row)
            row_id = int(row.get("id") or 0)
            row_ln = int(row.get("line_no") or 0)
            if row_id == 0 and row_ln > 0 and row_ln in existing_by_lineno:
                row_id = existing_by_lineno[row_ln]

            comp = SalesInvoiceService.compute_charge_amounts(header=header, row=row)
            row["gst_rate"] = q2(row.get("gst_rate") or ZERO2)
            row["taxable_value"] = comp.taxable_value
            row["cgst_amount"] = comp.cgst_amount
            row["sgst_amount"] = comp.sgst_amount
            row["igst_amount"] = comp.igst_amount
            row["total_value"] = comp.total_value

            if row_id and row_id in existing_by_id:
                obj = SalesChargeLine.objects.get(id=row_id, header=header)
                seen_ids.add(row_id)

                if row_ln > 0 and row_ln != int(obj.line_no):
                    if row_ln in existing_by_lineno and existing_by_lineno[row_ln] != row_id:
                        raise ValidationError({"charges": [f"line_no {row_ln} already exists."]})
                    obj.line_no = row_ln

                for f in [
                    "charge_type",
                    "description",
                    "taxability",
                    "is_service",
                    "hsn_sac_code",
                    "is_rate_inclusive_of_tax",
                    "taxable_value",
                    "gst_rate",
                    "cgst_amount",
                    "sgst_amount",
                    "igst_amount",
                    "total_value",
                    "revenue_account",
                ]:
                    if f in row:
                        setattr(obj, f, row.get(f))
                obj.updated_by = user
                obj.save()
                continue

            if row_id and row_id not in existing_by_id:
                raise ValidationError({"charges": [f"Charge id={row_id} not found for this invoice."]})

            if row_ln <= 0:
                max_ln += 1
                row_ln = max_ln
            if row_ln in existing_by_lineno:
                raise ValidationError({"charges": [f"line_no {row_ln} already exists; pass id to update."]})

            obj = SalesChargeLine(
                header=header,
                line_no=row_ln,
                charge_type=row.get("charge_type") or SalesChargeLine.ChargeType.OTHER,
                description=(row.get("description") or "").strip(),
                taxability=int(row.get("taxability") or SalesInvoiceHeader.Taxability.TAXABLE),
                is_service=bool(row.get("is_service", True)),
                hsn_sac_code=(row.get("hsn_sac_code") or "").strip(),
                is_rate_inclusive_of_tax=bool(row.get("is_rate_inclusive_of_tax", False)),
                taxable_value=row["taxable_value"],
                gst_rate=row["gst_rate"],
                cgst_amount=row["cgst_amount"],
                sgst_amount=row["sgst_amount"],
                igst_amount=row["igst_amount"],
                total_value=row["total_value"],
                revenue_account=row.get("revenue_account"),
                created_by=user,
                updated_by=user,
            )
            obj.full_clean()
            obj.save()

        if allow_delete:
            to_delete = [lid for lid in existing_by_id.keys() if lid not in seen_ids]
            if to_delete:
                SalesChargeLine.objects.filter(header=header, id__in=to_delete).delete()

    # -------------------------
    # Tax summary rebuild
    # -------------------------
    @classmethod
    def _load_invoice_rows(
        cls,
        *,
        header: SalesInvoiceHeader,
        lines: Optional[list[SalesInvoiceLine]] = None,
        charges: Optional[list[SalesChargeLine]] = None,
    ) -> tuple[list[SalesInvoiceLine], list[SalesChargeLine]]:
        return (
            lines if lines is not None else list(header.lines.all()),
            charges if charges is not None else list(header.charges.all()),
        )

    @classmethod
    def _prepare_header_for_persistence(cls, *, header: SalesInvoiceHeader) -> None:
        cls.apply_dates(header)
        cls._refresh_party_snapshots(header=header)
        cls.derive_tax_regime(header)
        cls._validate_invoice_uniqueness_per_gstin(header=header)

    @classmethod
    def rebuild_tax_summary(
        cls,
        header: SalesInvoiceHeader,
        *,
        lines: Optional[list[SalesInvoiceLine]] = None,
        charges: Optional[list[SalesChargeLine]] = None,
    ):
        SalesTaxSummary.objects.filter(header=header).delete()
        lines, charges = cls._load_invoice_rows(header=header, lines=lines, charges=charges)

        buckets: Dict[Tuple[int, str, bool, str, bool], SalesTaxSummary] = {}

        for line in lines:
            key = (
                int(getattr(line, "taxability", header.taxability or SalesInvoiceHeader.Taxability.TAXABLE) or SalesInvoiceHeader.Taxability.TAXABLE),
                (line.hsn_sac_code or "").strip(),
                bool(line.is_service),
                str(q4(line.gst_rate)),
                bool(header.is_reverse_charge),
            )
            b = buckets.get(key)
            if not b:
                b = SalesTaxSummary(
                    header=header,
                    entity_id=header.entity_id,
                    entityfinid_id=header.entityfinid_id,
                    subentity_id=header.subentity_id,
                    taxability=key[0],
                    hsn_sac_code=key[1],
                    is_service=key[2],
                    gst_rate=q4(line.gst_rate),
                    is_reverse_charge=key[4],
                    taxable_value=ZERO2,
                    cgst_amount=ZERO2,
                    sgst_amount=ZERO2,
                    igst_amount=ZERO2,
                    cess_amount=ZERO2,
                )
                buckets[key] = b

            b.taxable_value = q2(b.taxable_value + q2(line.taxable_value))
            b.cgst_amount = q2(b.cgst_amount + q2(line.cgst_amount))
            b.sgst_amount = q2(b.sgst_amount + q2(line.sgst_amount))
            b.igst_amount = q2(b.igst_amount + q2(line.igst_amount))
            b.cess_amount = q2(b.cess_amount + q2(line.cess_amount))

        for charge in charges:
            key = (
                int(charge.taxability or SalesInvoiceHeader.Taxability.TAXABLE),
                (charge.hsn_sac_code or "").strip(),
                bool(charge.is_service),
                str(q4(charge.gst_rate)),
                bool(header.is_reverse_charge),
            )
            b = buckets.get(key)
            if not b:
                b = SalesTaxSummary(
                    header=header,
                    entity_id=header.entity_id,
                    entityfinid_id=header.entityfinid_id,
                    subentity_id=header.subentity_id,
                    taxability=key[0],
                    hsn_sac_code=key[1],
                    is_service=key[2],
                    gst_rate=q4(charge.gst_rate),
                    is_reverse_charge=key[4],
                    taxable_value=ZERO2,
                    cgst_amount=ZERO2,
                    sgst_amount=ZERO2,
                    igst_amount=ZERO2,
                    cess_amount=ZERO2,
                )
                buckets[key] = b

            b.taxable_value = q2(b.taxable_value + q2(charge.taxable_value))
            b.cgst_amount = q2(b.cgst_amount + q2(charge.cgst_amount))
            b.sgst_amount = q2(b.sgst_amount + q2(charge.sgst_amount))
            b.igst_amount = q2(b.igst_amount + q2(charge.igst_amount))

        if buckets:
            SalesTaxSummary.objects.bulk_create(list(buckets.values()))

    # -------------------------
    # Totals compute
    # -------------------------
    @classmethod
    def compute_and_persist_totals(
        cls,
        header: SalesInvoiceHeader,
        *,
        user,
        settings_obj=None,
        lines: Optional[list[SalesInvoiceLine]] = None,
        charges: Optional[list[SalesChargeLine]] = None,
        round_off_explicit: bool = False,
        grand_total_hint: Optional[Decimal] = None,
    ):
        settings_obj = settings_obj or cls.get_settings(
            header.entity_id,
            header.subentity_id,
            entityfinid_id=getattr(header, "entityfinid_id", None),
        )
        lines, charges = cls._load_invoice_rows(header=header, lines=lines, charges=charges)

        totals = Totals()
        for line in lines:
            totals.total_taxable = q2(totals.total_taxable + q2(line.taxable_value))
            totals.total_cgst = q2(totals.total_cgst + q2(line.cgst_amount))
            totals.total_sgst = q2(totals.total_sgst + q2(line.sgst_amount))
            totals.total_igst = q2(totals.total_igst + q2(line.igst_amount))
            totals.total_cess = q2(totals.total_cess + q2(line.cess_amount))
            totals.total_discount = q2(totals.total_discount + q2(line.discount_amount))

        charge_taxable = ZERO2
        for charge in charges:
            charge_taxable = q2(charge_taxable + q2(charge.taxable_value))
            totals.total_taxable = q2(totals.total_taxable + q2(charge.taxable_value))
            totals.total_cgst = q2(totals.total_cgst + q2(charge.cgst_amount))
            totals.total_sgst = q2(totals.total_sgst + q2(charge.sgst_amount))
            totals.total_igst = q2(totals.total_igst + q2(charge.igst_amount))

        # Keep this as informational (base amount of charge lines) for UI/reporting compatibility.
        totals.total_other_charges = q2(charge_taxable)

        # raw grand total (before rounding)
        raw = q2(
            totals.total_taxable
            + totals.total_cgst
            + totals.total_sgst
            + totals.total_igst
            + totals.total_cess
        )

        round_off = ZERO2
        if round_off_explicit:
            round_off = q2(getattr(header, "round_off", ZERO2) or ZERO2)
            totals.grand_total = q2(raw + round_off)
        elif grand_total_hint is not None:
            hinted_grand_total = q2(grand_total_hint)
            round_off = q2(hinted_grand_total - raw)
            totals.grand_total = hinted_grand_total
        elif bool(getattr(settings_obj, "enable_round_off", True)):
            decimals_raw = getattr(settings_obj, "round_grand_total_to", 2)
            decimals = 2 if decimals_raw is None else int(decimals_raw)
            quant = Decimal("1") if decimals == 0 else Decimal("1").scaleb(-decimals)  # 10^-decimals
            rounded = raw.quantize(quant, rounding=ROUND_HALF_UP)
            round_off = q2(rounded - raw)
            totals.grand_total = q2(rounded)
        else:
            totals.grand_total = raw

        totals.round_off = round_off

        header.total_taxable_value = totals.total_taxable
        header.total_cgst = totals.total_cgst
        header.total_sgst = totals.total_sgst
        header.total_igst = totals.total_igst
        header.total_cess = totals.total_cess
        header.total_discount = totals.total_discount
        header.total_other_charges = totals.total_other_charges
        header.round_off = totals.round_off
        header.grand_total = totals.grand_total
        header.updated_by = user
        header.save(
            update_fields=[
                "total_taxable_value",
                "total_cgst",
                "total_sgst",
                "total_igst",
                "total_cess",
                "total_discount",
                "total_other_charges",
                "round_off",
                "grand_total",
                "updated_by",
                "updated_at",
            ]
        )

    @classmethod
    def _recompute_invoice_state(
        cls,
        *,
        header: SalesInvoiceHeader,
        user,
        settings_obj=None,
        lines: Optional[list[SalesInvoiceLine]] = None,
        charges: Optional[list[SalesChargeLine]] = None,
        round_off_explicit: bool = False,
        grand_total_hint: Optional[Decimal] = None,
    ) -> tuple[list[SalesInvoiceLine], list[SalesChargeLine]]:
        settings_obj = settings_obj or cls.get_settings(
            header.entity_id,
            header.subentity_id,
            entityfinid_id=getattr(header, "entityfinid_id", None),
        )
        lines, charges = cls._load_invoice_rows(header=header, lines=lines, charges=charges)
        cls.rebuild_tax_summary(header, lines=lines, charges=charges)
        cls.compute_and_persist_totals(
            header,
            user=user,
            settings_obj=settings_obj,
            lines=lines,
            charges=charges,
            round_off_explicit=round_off_explicit,
            grand_total_hint=grand_total_hint,
        )
        cls._derive_compliance_flags(
            header=header,
            settings_obj=settings_obj,
            user=user,
        )
        cls._validate_adjustment_caps(header=header)
        cls._apply_tcs(header=header, user=user)
        cls.recompute_settlement_fields(header=header)
        return lines, charges

    # -------------------------
    # Status transitions
    # -------------------------
    @classmethod
    @transaction.atomic
    def confirm(cls, *, header: SalesInvoiceHeader, user) -> SalesInvoiceHeader:
        if header.status == SalesInvoiceHeader.Status.POSTED:
            return header
        if header.status == SalesInvoiceHeader.Status.CONFIRMED:
            cls.ensure_doc_number(header=header, user=user)
            return header
        if header.status == SalesInvoiceHeader.Status.CANCELLED:
            raise ValueError("Only Draft invoices can be confirmed.")
        if header.status != SalesInvoiceHeader.Status.DRAFT:
            raise ValueError("Only Draft invoices can be confirmed.")

        controls = cls._policy_controls(header)
        cls.freeze_ship_to_snapshot(header=header)
        lock_level = cls._policy_level(controls, "confirm_lock_check", default="hard")
        if lock_level == "hard":
            cls.assert_not_locked(entity_id=header.entity_id, subentity_id=header.subentity_id, bill_date=header.bill_date)
        require_lines_level = cls._policy_level(controls, "require_lines_on_confirm", default="hard")
        lines, charges = cls._load_invoice_rows(header=header)
        if require_lines_level == "hard" and not lines:
            raise ValueError("At least one invoice line is required before confirm.")

        settings_obj = cls.get_settings(
            header.entity_id,
            header.subentity_id,
            entityfinid_id=getattr(header, "entityfinid_id", None),
        )
        cls._prepare_header_for_persistence(header=header)
        lines, charges = cls._recompute_invoice_state(
            header=header,
            user=user,
            settings_obj=settings_obj,
            lines=lines,
            charges=charges,
        )
        cls._validate_b2b_gstin_requirements(header=header)
        if header.is_eway_applicable and not header.shipping_detail_id:
            raise ValueError("Shipping detail is required when E-Way is applicable.")
        cls._allocate_batches_for_post(header=header, lines=lines)
        cls._validate_stock_policy_on_post(header=header, lines=lines)
        

        # âœ… issue doc_no ONLY NOW
        cls.ensure_doc_number(header=header, user=user)
        cls._validate_invoice_uniqueness_per_gstin(header=header)
        # Re-run TCS sync after final invoice numbering so statutory search/drilldowns
        # always persist the same document_no the user sees on the confirmed invoice.
        if (
            bool(getattr(header, "withholding_enabled", False))
            or getattr(header, "tcs_section", None) is not None
            or q2(getattr(header, "tcs_base_amount", ZERO2) or ZERO2) > ZERO2
            or q2(getattr(header, "tcs_amount", ZERO2) or ZERO2) > ZERO2
        ):
            cls._apply_tcs(header=header, user=user)

        header.status = SalesInvoiceHeader.Status.CONFIRMED
        header.confirmed_at = timezone.now()
        header.confirmed_by = user
        header.updated_by = user
        header.save(update_fields=[
            "doc_code", "doc_no", "invoice_number",
            "status", "confirmed_at", "confirmed_by",
            "updated_by", "updated_at",
            "posting_date", "due_date", "tax_regime", "is_igst",
            "gst_compliance_mode", "is_einvoice_applicable", "is_eway_applicable",
            "einvoice_applicable_manual", "eway_applicable_manual",
            "compliance_override_reason", "compliance_override_at", "compliance_override_by",
            "total_taxable_value", "total_cgst", "total_sgst", "total_igst", "total_cess",
            "total_discount", "round_off", "grand_total",
            "tcs_rate", "tcs_base_amount", "tcs_amount", "tcs_reason", "tcs_is_reversal",
            "settled_amount", "outstanding_amount", "settlement_status",
        ])

        cls._run_auto_compliance(header=header, user=user, stage="confirm")
        return header


    @classmethod
    @transaction.atomic
    def post(cls, *, header: SalesInvoiceHeader, user) -> SalesInvoiceHeader:
        """
        Mirrors Purchase post hook:
          - auto-confirms valid drafts before posting
          - assert_not_locked
          - freeze ship-to snapshot (idempotent)
          - ensure doc number (idempotent)
          - rebuild tax summary + recompute totals (safety)
          - call posting adapter (GL/Stock)
          - set POSTED
        """
        # ---- hard gates ----
        if int(header.status) == int(SalesInvoiceHeader.Status.CANCELLED):
            raise ValueError("Cannot post: document is cancelled.")
        if int(header.status) == int(SalesInvoiceHeader.Status.POSTED):
            return header
        if int(header.status) == int(SalesInvoiceHeader.Status.DRAFT):
            header = cls.confirm(header=header, user=user)
        if int(header.status) != int(SalesInvoiceHeader.Status.CONFIRMED):
            raise ValueError("Only Draft or Confirmed invoices can be posted.")

        # ---- lock-period validation ----
        controls = cls._policy_controls(header)
        lock_level = cls._policy_level(controls, "confirm_lock_check", default="hard")
        if lock_level == "hard":
            cls.assert_not_locked(entity_id=header.entity_id, subentity_id=header.subentity_id, bill_date=header.bill_date)

        # ---- snapshot (idempotent) ----
        cls.freeze_ship_to_snapshot(header=header)

        # ---- safety: if someone bypassed confirm, ensure doc number exists ----
        cls.ensure_doc_number(header=header, user=user)
        cls._validate_invoice_uniqueness_per_gstin(header=header)

        settings_obj = cls.get_settings(
            header.entity_id,
            header.subentity_id,
            entityfinid_id=getattr(header, "entityfinid_id", None),
        )
        lines, charges = cls._load_invoice_rows(header=header)
        cls._prepare_header_for_persistence(header=header)
        lines, charges = cls._recompute_invoice_state(
            header=header,
            user=user,
            settings_obj=settings_obj,
            lines=lines,
            charges=charges,
        )
        cls._validate_b2b_gstin_requirements(header=header)
        if header.is_eway_applicable and not header.shipping_detail_id:
            raise ValueError("Shipping detail is required when E-Way is applicable.")
        cls._allocate_batches_for_post(header=header, lines=lines)
        cls._validate_stock_policy_on_post(header=header, lines=lines)

        # ---- GL/Stock Posting (same as purchase adapter call) ----
        SalesInvoicePostingAdapter.post_sales_invoice(
            header=header,
            lines=lines,
            user_id=getattr(user, "id", None),
            config=SalesInvoicePostingConfig(
                totals_tolerance=Decimal("0.05"),
                spread_cost_across_free_qty=True,
                post_inventory=True,
            ),
        )

        # ---- mark posted ----
        header.status = SalesInvoiceHeader.Status.POSTED
        header.is_posting_reversed = False
        header.reversed_at = None
        header.reversed_by = None
        header.reverse_reason = ""
        header.posted_at = timezone.now()
        header.posted_by = user
        header.updated_by = user
        header.save(update_fields=[
            "status",
            "is_posting_reversed",
            "reversed_at",
            "reversed_by",
            "reverse_reason",
            "posted_at",
            "posted_by",
            "updated_by",
            "updated_at",
            "gst_compliance_mode",
            "is_einvoice_applicable",
            "is_eway_applicable",
            "einvoice_applicable_manual",
            "eway_applicable_manual",
            "compliance_override_reason",
            "compliance_override_at",
            "compliance_override_by",
            "tcs_rate",
            "tcs_base_amount",
            "tcs_amount",
            "tcs_reason",
            "tcs_is_reversal",
            "settled_amount",
            "outstanding_amount",
            "settlement_status",
        ])
        SalesArService.sync_open_item_for_header(header)

        cls._run_auto_compliance(header=header, user=user, stage="post")
        return header

    @staticmethod
    def _txn_type_for_header(header: SalesInvoiceHeader) -> str:
        doc_type = int(getattr(header, "doc_type", SalesInvoiceHeader.DocType.TAX_INVOICE))
        if doc_type == int(SalesInvoiceHeader.DocType.CREDIT_NOTE):
            return TxnType.SALES_CREDIT_NOTE
        if doc_type == int(SalesInvoiceHeader.DocType.DEBIT_NOTE):
            return TxnType.SALES_DEBIT_NOTE
        return TxnType.SALES

    @staticmethod
    def _reverse_move_type(move_type: str) -> str:
        mv = (move_type or "").upper()
        if mv == "IN":
            return "OUT"
        if mv == "OUT":
            return "IN"
        return "REV"

    @classmethod
    @transaction.atomic
    def reverse_posting(cls, *, header: SalesInvoiceHeader, user, reason: str = "") -> SalesInvoiceHeader:
        if int(header.status) != int(SalesInvoiceHeader.Status.POSTED):
            raise ValueError("Only posted invoices can be reversed.")
        controls = cls._policy_controls(header)
        allow_unpost = str(controls.get("allow_unpost_posted", "on")).lower().strip()
        if allow_unpost == "off":
            raise ValueError("Unpost after posting is disabled by sales policy.")
        try:
            cls.assert_not_locked(
                entity_id=header.entity_id,
                subentity_id=header.subentity_id,
                bill_date=header.bill_date,
            )
        except ValueError as exc:
            raise ValueError(
                "Posted sales invoice belongs to a locked/filed period and cannot be unposted. "
                "Create a current-period correction document instead."
            ) from exc

        txn_type = cls._txn_type_for_header(header)
        entry = (
            Entry.objects.select_for_update()
            .filter(
                entity_id=header.entity_id,
                entityfin_id=header.entityfinid_id,
                subentity_id=header.subentity_id,
                txn_type=txn_type,
                txn_id=header.id,
            )
            .first()
        )
        if not entry:
            raise ValueError("Posted ledger entry not found for this invoice.")

        old_jls = list(
            JournalLine.objects.filter(
                entity_id=header.entity_id,
                entityfin_id=header.entityfinid_id,
                subentity_id=header.subentity_id,
                txn_type=txn_type,
                txn_id=header.id,
            )
        )

        jl_inputs: list[JLInput] = []
        for jl in old_jls:
            jl_inputs.append(
                JLInput(
                    account_id=jl.account_id,
                    accounthead_id=jl.accounthead_id,
                    drcr=(not bool(jl.drcr)),
                    amount=q2(jl.amount),
                    description=f"Reversal: {jl.description or ''}".strip(),
                    detail_id=jl.detail_id,
                )
            )

        PostingService(
            entity_id=header.entity_id,
            entityfin_id=header.entityfinid_id,
            subentity_id=header.subentity_id,
            user_id=getattr(user, "id", None),
        ).post(
            txn_type=txn_type,
            txn_id=header.id,
            voucher_no=str(header.invoice_number or header.doc_no or header.id),
            voucher_date=header.bill_date,
            posting_date=header.posting_date or header.bill_date,
            narration=f"Reversal for {header.invoice_number or header.id}",
            jl_inputs=jl_inputs,
            # Unpost should clear prior inventory impact for this transaction.
            # PostingService deletes existing rows by txn locator before inserting fresh rows.
            # Keeping this empty prevents net stock drift after unpost.
            im_inputs=[],
            use_advisory_lock=True,
            mark_posted=True,
        )

        Entry.objects.filter(
            entity_id=header.entity_id,
            entityfin_id=header.entityfinid_id,
            subentity_id=header.subentity_id,
            txn_type=txn_type,
            txn_id=header.id,
        ).update(
            status=EntryStatus.REVERSED,
            narration=f"Reversed: {reason}".strip(),
        )

        header.status = SalesInvoiceHeader.Status.CONFIRMED
        header.is_posting_reversed = True
        header.reversed_at = timezone.now()
        header.reversed_by = user
        header.reverse_reason = (reason or "").strip()
        header.posted_at = None
        header.posted_by = None
        header.updated_by = user
        header.save(
            update_fields=[
                "status",
                "is_posting_reversed",
                "reversed_at",
                "reversed_by",
                "reverse_reason",
                "posted_at",
                "posted_by",
                "updated_by",
                "updated_at",
            ]
        )
        SalesArService.close_open_item_for_header(header)
        return header

    @classmethod
    @transaction.atomic
    def apply_settlement(cls, *, header: SalesInvoiceHeader, user, settled_amount: Decimal, note: str = "") -> SalesInvoiceHeader:
        if settled_amount < ZERO2:
            raise ValueError("settled_amount must be >= 0.")
        header.settled_amount = q2(settled_amount)
        cls.recompute_settlement_fields(header=header)
        if note:
            header.remarks = ((header.remarks or "").strip() + f"\nSettlement: {note.strip()}").strip()
        header.updated_by = user
        header.save(update_fields=["settled_amount", "outstanding_amount", "settlement_status", "remarks", "updated_by", "updated_at"])
        return header


    @classmethod
    @transaction.atomic
    def cancel(cls, *, header: SalesInvoiceHeader, user, reason: str = "") -> SalesInvoiceHeader:
        if header.status == SalesInvoiceHeader.Status.CANCELLED:
            return header
        settings_obj = cls.get_settings(header.entity_id, header.subentity_id, entityfinid_id=getattr(header, "entityfinid_id", None))
        if bool(getattr(settings_obj, "enforce_statutory_cancel_before_business_cancel", True)):
            einv = getattr(header, "einvoice_artifact", None)
            ewb = getattr(header, "eway_artifact", None)
            blocked_reasons = []
            if einv and int(getattr(einv, "status", 0) or 0) == 2 and getattr(einv, "irn", None):
                blocked_reasons.append("IRN is generated but not cancelled.")
            if ewb and int(getattr(ewb, "status", 0) or 0) == 2 and getattr(ewb, "ewb_no", None):
                blocked_reasons.append("E-Way Bill is generated but not cancelled.")
            if blocked_reasons:
                msg = " ".join(blocked_reasons)
                ComplianceAuditService.log_action(
                    invoice=header,
                    action_type="INVOICE_CANCEL_BLOCKED",
                    outcome="BLOCKED",
                    user=user,
                    error_code="STATUTORY_CANCEL_REQUIRED",
                    error_message=msg,
                )
                ComplianceAuditService.open_exception(
                    invoice=header,
                    exception_type="STATUTORY_CANCEL_REQUIRED",
                    error_code="STATUTORY_CANCEL_REQUIRED",
                    error_message=msg,
                )
                raise ValueError(msg)

        if cls.requires_current_period_correction(header=header):
            return cls.create_current_period_reversal_credit_note(
                original=header,
                user=user,
                reason=reason,
            )

        if header.status == SalesInvoiceHeader.Status.POSTED:
            cls.reverse_posting(header=header, user=user, reason=reason or "Cancelled")

        header.status = SalesInvoiceHeader.Status.CANCELLED
        header.cancelled_at = timezone.now()
        header.cancelled_by = user
        header.remarks = (header.remarks or "").strip()
        if reason:
            header.remarks = (header.remarks + "\n" + f"Cancelled: {reason}").strip()
        header.updated_by = user
        header.save(update_fields=["status", "cancelled_at", "cancelled_by", "remarks", "updated_by", "updated_at"])
        SalesArService.close_open_item_for_header(header)
        return header
