from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Tuple
from numbering.models import DocumentType
from numbering.services.document_number_service import DocumentNumberService

from django.db import transaction
from django.utils import timezone

from sales.models import (
    SalesInvoiceHeader,
    SalesInvoiceLine,
    SalesTaxSummary,
    SalesSettings,
    SalesLockPeriod,
)

ZERO2 = Decimal("0.00")
ZERO4 = Decimal("0.0000")
Q2 = Decimal("0.01")
Q4 = Decimal("0.0001")


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
        settings_obj = cls.get_settings(header.entity_id, header.subentity_id)

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

        # ✅ consumes number (thread-safe) ONLY now
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
    def get_settings(entity_id: int, subentity_id: Optional[int]) -> SalesSettings:
        obj = (
            SalesSettings.objects.filter(entity_id=entity_id, subentity_id=subentity_id).first()
            or SalesSettings.objects.filter(entity_id=entity_id, subentity__isnull=True).first()
        )
        if not obj:
            # fallback default object-like behavior
            obj = SalesSettings(
                entity_id=entity_id,
                subentity_id=subentity_id,
                default_doc_code_invoice="SINV",
                default_doc_code_cn="SCN",
                default_doc_code_dn="SDN",
                enable_round_off=True,
                round_grand_total_to=2,
            )
        return obj

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
        user,
    ) -> SalesInvoiceHeader:
        # ensure locked check early
        bill_date = header_data.get("bill_date") or timezone.localdate()
        cls.assert_not_locked(entity_id=entity_id, subentity_id=subentity_id, bill_date=bill_date)

        header = SalesInvoiceHeader(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            created_by=user,
            updated_by=user,
            **header_data,
        )

        # backend controls status
        header.status = SalesInvoiceHeader.Status.DRAFT

        # apply derived fields
        cls.apply_dates(header)
        cls.derive_tax_regime(header)

        header.full_clean(exclude=None)
        header.save()

        cls.upsert_lines(header=header, incoming_lines=lines_data, user=user, allow_delete=True)
        cls.rebuild_tax_summary(header)
        cls.compute_and_persist_totals(header, user=user)

        return header

    @classmethod
    @transaction.atomic
    def update_with_lines(
        cls,
        *,
        header: SalesInvoiceHeader,
        header_data: dict,
        lines_data: list,
        user,
    ) -> SalesInvoiceHeader:
        # editing policy
        if header.status in (SalesInvoiceHeader.Status.POSTED, SalesInvoiceHeader.Status.CANCELLED):
            raise ValueError("Posted/Cancelled invoices cannot be edited.")

        # lock check
        bill_date = header_data.get("bill_date") or header.bill_date
        cls.assert_not_locked(entity_id=header.entity_id, subentity_id=header.subentity_id, bill_date=bill_date)

        for k, v in header_data.items():
            setattr(header, k, v)

        header.updated_by = user

        cls.apply_dates(header)
        cls.derive_tax_regime(header)

        header.full_clean(exclude=None)
        header.save()

        cls.upsert_lines(header=header, incoming_lines=lines_data, user=user, allow_delete=True)
        cls.rebuild_tax_summary(header)
        cls.compute_and_persist_totals(header, user=user)

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
    @classmethod
    def upsert_lines(
        cls,
        *,
        header: SalesInvoiceHeader,
        incoming_lines: list,
        user,
        allow_delete: bool,
    ):
        """
        Same behavior as your Purchase nested update:
          - if id is 0 / missing => create
          - if id exists => update
          - if existing not present => delete (if allow_delete)
        """
        existing = {l.id: l for l in header.lines.all()}
        seen_ids = set()

        # Determine next line_no if not provided
        max_line_no = 0
        for l in existing.values():
            max_line_no = max(max_line_no, l.line_no or 0)

        for row in incoming_lines or []:
            row_id = int(row.get("id") or 0)
            if row_id and row_id in existing:
                line = existing[row_id]
                seen_ids.add(row_id)
                cls.apply_line_inputs(line, row)
                line.updated_by = user
                cls.compute_line_amounts(header, line)
                line.full_clean(exclude=None)
                line.save()
            else:
                max_line_no += 1
                line = SalesInvoiceLine(
                    header=header,
                    entity_id=header.entity_id,
                    entityfinid_id=header.entityfinid_id,
                    subentity_id=header.subentity_id,
                    line_no=int(row.get("line_no") or max_line_no),
                    created_by=user,
                    updated_by=user,
                )
                cls.apply_line_inputs(line, row)
                cls.compute_line_amounts(header, line)
                line.full_clean(exclude=None)
                line.save()

        if allow_delete:
            to_delete = [lid for lid in existing.keys() if lid not in seen_ids]
            if to_delete:
                SalesInvoiceLine.objects.filter(id__in=to_delete).delete()

    @staticmethod
    def apply_line_inputs(line: SalesInvoiceLine, row: dict):
        # required
        for fld in [
            "product",
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
            "gst_rate",
            "cess_percent",
            "cess_amount",
            "sales_account",
            "line_no",
        ]:
            if fld in row:
                setattr(line, fld, row.get(fld))

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

        gst_rate = q4(line.gst_rate)
        cess_amt = ZERO2

        # If cess percent used (most cases): cess = net * percent
        if q4(line.cess_percent) > ZERO4:
            cess_amt = q2(net * q4(line.cess_percent) / Decimal("100"))
        else:
            cess_amt = q2(line.cess_amount)

        # If rate is inclusive of tax, back-calculate taxable
        taxable = net
        cgst = sgst = igst = ZERO2

        if line.is_rate_inclusive_of_tax and gst_rate > ZERO4:
            # taxable = net / (1 + gst_rate/100)
            taxable = q2(net / (Decimal("1.0") + (gst_rate / Decimal("100"))))
            tax_total = q2(net - taxable)
        else:
            tax_total = q2(taxable * gst_rate / Decimal("100"))

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

    # -------------------------
    # Tax summary rebuild
    # -------------------------
    @classmethod
    def rebuild_tax_summary(cls, header: SalesInvoiceHeader):
        SalesTaxSummary.objects.filter(header=header).delete()

        buckets: Dict[Tuple[int, str, bool, str, bool], SalesTaxSummary] = {}

        for line in header.lines.all():
            key = (
                int(header.taxability or SalesInvoiceHeader.Taxability.TAXABLE),
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

        if buckets:
            SalesTaxSummary.objects.bulk_create(list(buckets.values()))

    # -------------------------
    # Totals compute
    # -------------------------
    @classmethod
    def compute_and_persist_totals(cls, header: SalesInvoiceHeader, *, user):
        settings_obj = cls.get_settings(header.entity_id, header.subentity_id)

        totals = Totals()
        for line in header.lines.all():
            totals.total_taxable = q2(totals.total_taxable + q2(line.taxable_value))
            totals.total_cgst = q2(totals.total_cgst + q2(line.cgst_amount))
            totals.total_sgst = q2(totals.total_sgst + q2(line.sgst_amount))
            totals.total_igst = q2(totals.total_igst + q2(line.igst_amount))
            totals.total_cess = q2(totals.total_cess + q2(line.cess_amount))
            totals.total_discount = q2(totals.total_discount + q2(line.discount_amount))

        totals.total_other_charges = q2(header.total_other_charges)

        # raw grand total (before rounding)
        raw = q2(
            totals.total_taxable
            + totals.total_cgst
            + totals.total_sgst
            + totals.total_igst
            + totals.total_cess
            + totals.total_other_charges
        )

        round_off = ZERO2
        if bool(getattr(settings_obj, "enable_round_off", True)):
            decimals = int(getattr(settings_obj, "round_grand_total_to", 2) or 2)
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

    # -------------------------
    # Status transitions
    # -------------------------
    @classmethod
    @transaction.atomic
    def confirm(cls, *, header: SalesInvoiceHeader, user) -> SalesInvoiceHeader:
        if header.status != SalesInvoiceHeader.Status.DRAFT:
            raise ValueError("Only Draft invoices can be confirmed.")

        cls.assert_not_locked(entity_id=header.entity_id, subentity_id=header.subentity_id, bill_date=header.bill_date)

        # ✅ recompute everything first
        cls.apply_dates(header)
        cls.derive_tax_regime(header)
        cls.rebuild_tax_summary(header)
        cls.compute_and_persist_totals(header, user=user)

        # ✅ issue doc_no ONLY NOW
        cls.ensure_doc_number(header=header, user=user)

        header.status = SalesInvoiceHeader.Status.CONFIRMED
        header.confirmed_at = timezone.now()
        header.confirmed_by = user
        header.updated_by = user
        header.save(update_fields=[
            "doc_code", "doc_no", "invoice_number",
            "status", "confirmed_at", "confirmed_by",
            "updated_by", "updated_at",
            "posting_date", "due_date", "tax_regime", "is_igst",
            "total_taxable_value", "total_cgst", "total_sgst", "total_igst", "total_cess",
            "total_discount", "round_off", "grand_total",
        ])
        return header


    @classmethod
    @transaction.atomic
    def post(cls, *, header: SalesInvoiceHeader, user) -> SalesInvoiceHeader:
        if header.status != SalesInvoiceHeader.Status.CONFIRMED:
            raise ValueError("Only Confirmed invoices can be posted.")

        # safety
        cls.ensure_doc_number(header=header, user=user)


        # Posting hook here...
        header.status = SalesInvoiceHeader.Status.POSTED
        header.posted_at = timezone.now()
        header.posted_by = user
        header.updated_by = user
        header.save(update_fields=["status", "posted_at", "posted_by", "updated_by", "updated_at"])
        return header


    @classmethod
    @transaction.atomic
    def cancel(cls, *, header: SalesInvoiceHeader, user, reason: str = "") -> SalesInvoiceHeader:
        if header.status == SalesInvoiceHeader.Status.CANCELLED:
            return header
        if header.status == SalesInvoiceHeader.Status.POSTED:
            raise ValueError("Posted invoices cannot be cancelled directly (implement reversal).")

        header.status = SalesInvoiceHeader.Status.CANCELLED
        header.cancelled_at = timezone.now()
        header.cancelled_by = user
        header.remarks = (header.remarks or "").strip()
        if reason:
            header.remarks = (header.remarks + "\n" + f"Cancelled: {reason}").strip()
        header.updated_by = user
        header.save(update_fields=["status", "cancelled_at", "cancelled_by", "remarks", "updated_by", "updated_at"])
        return header
