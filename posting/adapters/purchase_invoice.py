# posting/adapters/purchase_invoice.py
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Optional

from django.db import transaction

from posting.services.posting_service import PostingService, JLInput, IMInput
from posting.models import TxnType
from posting.common.static_accounts import StaticAccountCodes, StaticAccountResolver
from posting.common.product_accounts import ProductAccountResolver


# =========================
# Decimal helpers
# =========================
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


# =========================
# Adapter config (policy switches)
# =========================
@dataclass(frozen=True)
class PurchaseInvoicePostingConfig:
    """
    Keep adapter stable and move policy decisions into config.
    Later you can store these per entity.
    """
    # If True -> header charges get capitalized into inventory (goods only).
    # If False -> header charges are Dr PURCHASE_MISC_EXPENSE.
    capitalize_header_expenses_to_inventory: bool = False

    # When ITC is blocked, taxes go to ITC_BLOCKED_EXPENSE (fallback to PURCHASE_MISC_EXPENSE if unmapped).
    post_blocked_itc_tax_to_expense: bool = True

    # Tolerance for header grand_total vs computed vendor balancing amount.
    totals_tolerance: Decimal = Decimal("0.05")

    # If True: include free_qty in unit_cost spreading (recommended)
    spread_cost_across_free_qty: bool = True

    # RCM: whether supplier invoice includes GST (usually False for RCM supplies)
    rcm_supplier_includes_tax: bool = False


# =========================
# Purchase Document Adapter (Invoice / CN / DN)
# =========================
class PurchaseInvoicePostingAdapter:
    """
    Supports:
      - Purchase Invoice (DocType=1)
      - Purchase Credit Note (DocType=2)
      - Purchase Debit Note (DocType=3)

    Assumptions (as per your purchase_core enums):
      DocType: 1=Invoice, 2=Credit Note, 3=Debit Note

    Inventory policy:
      - Invoice => IN (goods lines)
      - Credit Note => OUT only if header.affects_inventory=True
      - Debit Note => default no inventory (financial adjustment)
    """

    @staticmethod
    @transaction.atomic
    def post_purchase_invoice(
        *,
        header: Any,
        lines: Iterable[Any],
        user_id: Optional[int],
        config: Optional[PurchaseInvoicePostingConfig] = None,
    ):
        cfg = config or PurchaseInvoicePostingConfig()

        # ---- scope ----
        entity_id = int(header.entity_id)
        entityfin_id = getattr(header, "entityfinid_id", None) or getattr(header, "entityfinid", None)
        subentity_id = getattr(header, "subentity_id", None)
        txn_id = int(header.id)

        bill_date = getattr(header, "bill_date", None)
        if not bill_date:
            raise ValueError("Purchase header.bill_date is required for posting.")
        posting_date = getattr(header, "posting_date", None) or bill_date

        # ---- vendor ledger account id (must exist) ----
        supplier_account_id = (
            getattr(header, "vendor_id", None)
            or getattr(header, "vendor_account_id", None)
        )
        if not supplier_account_id:
            raise ValueError("Header must have vendor_id/vendor_account_id (ledger account id for vendor).")
        supplier_account_id = int(supplier_account_id)

        # ---- doc type policy ----
        doc_type = int(getattr(header, "doc_type", 1))
        is_credit_note = (doc_type == 2)
        is_debit_note = (doc_type == 3)

        # polarity: invoice/DN = +1, CN = -1
        sign = Decimal("-1") if is_credit_note else Decimal("1")

        # TxnType must be distinct to avoid locator collisions.
        # Ensure these enums exist in posting.models.TxnType
        if is_credit_note:
            txn_type = TxnType.PURCHASE_CREDIT_NOTE
        elif is_debit_note:
            txn_type = TxnType.PURCHASE_DEBIT_NOTE
        else:
            txn_type = TxnType.PURCHASE

        # ---- voucher no (for reporting only) ----
        voucher_no = (
            getattr(header, "purchase_number", None)
            or getattr(header, "display_no", None)
            or getattr(header, "doc_no", None)
        )
        voucher_no = str(voucher_no) if voucher_no is not None else None

        doc_label = "Purchase Invoice"
        if is_credit_note:
            doc_label = "Purchase Credit Note"
        elif is_debit_note:
            doc_label = "Purchase Debit Note"

        narration = f"{doc_label} {voucher_no or txn_id}"

        # ---- header totals ----
        header_grand_total = q2(getattr(header, "grand_total", None) or ZERO2)
        header_roundoff = q2(getattr(header, "roundoff", None) or ZERO2)
        header_expenses = q2(
            getattr(header, "total_expenses", None)
            or getattr(header, "expenses_total", None)
            or getattr(header, "misc_expenses", None)
            or ZERO2
        )
        is_rcm = bool(getattr(header, "is_reverse_charge", False))

        # ---- inventory policy ----
        affects_inventory = bool(getattr(header, "affects_inventory", False))
        post_inventory = True
        inventory_move_type = "IN"
        if is_credit_note:
            post_inventory = affects_inventory
            inventory_move_type = "OUT"
        elif is_debit_note:
            post_inventory = False  # default DN is financial only

        # ---- static accounts ----
        resolver = StaticAccountResolver(entity_id)

        misc_exp_ac = int(resolver.get_account_id(StaticAccountCodes.PURCHASE_MISC_EXPENSE, required=True))
        ro_income_ac = int(resolver.get_account_id(StaticAccountCodes.ROUND_OFF_INCOME, required=True))
        ro_exp_ac = int(resolver.get_account_id(StaticAccountCodes.ROUND_OFF_EXPENSE, required=True))

        itc_blocked_ac = resolver.get_account_id(StaticAccountCodes.ITC_BLOCKED_EXPENSE, required=False)
        itc_blocked_ac = int(itc_blocked_ac) if itc_blocked_ac else misc_exp_ac

        in_cgst = resolver.get_account_id(StaticAccountCodes.INPUT_CGST, required=False)
        in_sgst = resolver.get_account_id(StaticAccountCodes.INPUT_SGST, required=False)
        in_igst = resolver.get_account_id(StaticAccountCodes.INPUT_IGST, required=False)
        in_cess = resolver.get_account_id(StaticAccountCodes.INPUT_CESS, required=False)

        rcm_cgst = resolver.get_account_id(StaticAccountCodes.RCM_CGST_PAYABLE, required=False)
        rcm_sgst = resolver.get_account_id(StaticAccountCodes.RCM_SGST_PAYABLE, required=False)
        rcm_igst = resolver.get_account_id(StaticAccountCodes.RCM_IGST_PAYABLE, required=False)
        rcm_cess = resolver.get_account_id(StaticAccountCodes.RCM_CESS_PAYABLE, required=False)

        # Optional default purchase account (fallback if product has no purchase account)
        default_purchase_ac = resolver.get_account_id(StaticAccountCodes.PURCHASE_DEFAULT, required=False)
        default_purchase_ac = int(default_purchase_ac) if default_purchase_ac else misc_exp_ac

        # ---- ensure lines list ----
        lines_list = list(lines or [])
        if not lines_list:
            raise ValueError("Cannot post Purchase document: no lines found.")

        # per-product account resolver (no N+1)
        product_ids = [int(ln.product_id) for ln in lines_list if getattr(ln, "product_id", None)]
        prod_resolver = ProductAccountResolver(product_ids)

        # =========================
        # 1) Build Journal Lines
        # =========================
        jl: List[JLInput] = []

        # for capitalization allocation (goods only)
        total_goods_taxable = ZERO2

        eligible_tax = {"cgst": ZERO2, "sgst": ZERO2, "igst": ZERO2, "cess": ZERO2}
        blocked_tax = {"cgst": ZERO2, "sgst": ZERO2, "igst": ZERO2, "cess": ZERO2}
        rcm_tax = {"cgst": ZERO2, "sgst": ZERO2, "igst": ZERO2, "cess": ZERO2}

        # tax polarity controls
        input_tax_is_debit = not is_credit_note          # invoice/DN Dr input; CN Cr input
        blocked_tax_is_debit = not is_credit_note        # invoice/DN Dr blocked; CN Cr blocked
        rcm_payable_is_debit = is_credit_note            # invoice/DN Cr payable; CN Dr payable

        # 1A) Base per line (per-product purchase account)
        for ln in lines_list:
            base = q2(getattr(ln, "taxable_value", None) or ZERO2)
            if base <= ZERO2:
                continue

            pid = getattr(ln, "product_id", None)
            purchase_ac = prod_resolver.purchase_account_id(pid) or default_purchase_ac or misc_exp_ac
            purchase_ac = int(purchase_ac)

            # base polarity: invoice/DN Dr, CN Cr
            base_is_debit = (sign > 0)

            jl.append(JLInput(
                account_id=purchase_ac,
                drcr=base_is_debit,
                amount=q2(base.copy_abs()),
                description=f"{narration} (line {getattr(ln, 'line_no', '-')})",
                detail_id=int(getattr(ln, "id", 0) or 0) or None,
            ))

            if not bool(getattr(ln, "is_service", False)):
                total_goods_taxable = q2(total_goods_taxable + base)

            t_cgst = q2(getattr(ln, "cgst_amount", None) or ZERO2)
            t_sgst = q2(getattr(ln, "sgst_amount", None) or ZERO2)
            t_igst = q2(getattr(ln, "igst_amount", None) or ZERO2)
            t_cess = q2(getattr(ln, "cess_amount", None) or ZERO2)

            if is_rcm:
                rcm_tax["cgst"] = q2(rcm_tax["cgst"] + t_cgst)
                rcm_tax["sgst"] = q2(rcm_tax["sgst"] + t_sgst)
                rcm_tax["igst"] = q2(rcm_tax["igst"] + t_igst)
                rcm_tax["cess"] = q2(rcm_tax["cess"] + t_cess)
            else:
                if bool(getattr(ln, "is_itc_eligible", False)):
                    eligible_tax["cgst"] = q2(eligible_tax["cgst"] + t_cgst)
                    eligible_tax["sgst"] = q2(eligible_tax["sgst"] + t_sgst)
                    eligible_tax["igst"] = q2(eligible_tax["igst"] + t_igst)
                    eligible_tax["cess"] = q2(eligible_tax["cess"] + t_cess)
                else:
                    blocked_tax["cgst"] = q2(blocked_tax["cgst"] + t_cgst)
                    blocked_tax["sgst"] = q2(blocked_tax["sgst"] + t_sgst)
                    blocked_tax["igst"] = q2(blocked_tax["igst"] + t_igst)
                    blocked_tax["cess"] = q2(blocked_tax["cess"] + t_cess)

        # 1B) Header expenses (expense GL unless capitalized)
        if header_expenses > ZERO2 and not cfg.capitalize_header_expenses_to_inventory:
            jl.append(JLInput(
                account_id=misc_exp_ac,
                drcr=not is_credit_note,  # invoice/DN Dr, CN Cr
                amount=header_expenses,
                description=f"{narration} (header expenses)",
            ))

        # 1C) Tax postings
        if is_rcm:
            # RCM payable: invoice/DN Cr, CN Dr
            def _add_rcm(acct_id: Optional[int], amt: Decimal, label: str):
                if amt <= ZERO2:
                    return
                if not acct_id:
                    raise ValueError(f"{label} static account not mapped.")
                jl.append(JLInput(
                    account_id=int(acct_id),
                    drcr=rcm_payable_is_debit,
                    amount=amt,
                    description=f"{narration} ({label})",
                ))

            _add_rcm(rcm_cgst, rcm_tax["cgst"], "RCM CGST")
            _add_rcm(rcm_sgst, rcm_tax["sgst"], "RCM SGST")
            _add_rcm(rcm_igst, rcm_tax["igst"], "RCM IGST")
            _add_rcm(rcm_cess, rcm_tax["cess"], "RCM CESS")

        else:
            # Input GST (eligible): invoice/DN Dr, CN Cr
            def _add_input(acct_id: Optional[int], amt: Decimal, label: str):
                if amt <= ZERO2:
                    return
                if not acct_id:
                    raise ValueError(f"{label} not mapped.")
                jl.append(JLInput(
                    account_id=int(acct_id),
                    drcr=input_tax_is_debit,
                    amount=amt,
                    description=f"{narration} ({label})",
                ))

            _add_input(in_cgst, eligible_tax["cgst"], "Input CGST")
            _add_input(in_sgst, eligible_tax["sgst"], "Input SGST")
            _add_input(in_igst, eligible_tax["igst"], "Input IGST")
            _add_input(in_cess, eligible_tax["cess"], "Input CESS")

            # Blocked ITC tax -> expense (or reversed on CN)
            blocked_total = q2(blocked_tax["cgst"] + blocked_tax["sgst"] + blocked_tax["igst"] + blocked_tax["cess"])
            if blocked_total > ZERO2 and cfg.post_blocked_itc_tax_to_expense:
                jl.append(JLInput(
                    account_id=itc_blocked_ac,
                    drcr=blocked_tax_is_debit,
                    amount=blocked_total,
                    description=f"{narration} (Blocked ITC tax)",
                ))

        # 1D) Round-off (reverse on CN)
        # Original semantics:
        #   roundoff > 0 => Dr expense, < 0 => Cr income
        # For CN, flip direction.
        if header_roundoff != ZERO2:
            if header_roundoff > ZERO2:
                jl.append(JLInput(
                    account_id=ro_exp_ac,
                    drcr=not is_credit_note,  # invoice/DN Dr, CN Cr
                    amount=header_roundoff,
                    description=f"{narration} (Round-off expense)",
                ))
            else:
                jl.append(JLInput(
                    account_id=ro_income_ac,
                    drcr=is_credit_note,  # invoice/DN Cr, CN Dr
                    amount=abs(header_roundoff),
                    description=f"{narration} (Round-off income)",
                ))

        ZERO2 = Decimal("0.00")

        tds = q2(getattr(header, "tds_amount", None) or ZERO2)
        if tds > ZERO2:
            tds_payable_ac = resolver.get_account_id(StaticAccountCodes.TDS_PAYABLE, required=True)

            # Dr Vendor Payable (reduce vendor liability)
            jl.append(JLInput(
                account_id=int(header.vendor_id),
                drcr=True,  # DR
                amount=tds,
                description=f"{narration} (TDS deducted)",
            ))

            # Cr TDS Payable
            jl.append(JLInput(
                account_id=int(tds_payable_ac),
                drcr=False,  # CR
                amount=tds,
                description=f"{narration} (TDS payable)",
            ))

        # 1E) Vendor balancing line (works for Invoice/CN/DN)
        dr_sum = q2(sum(x.amount for x in jl if x.drcr))
        cr_sum = q2(sum(x.amount for x in jl if not x.drcr))
        net = q2(dr_sum - cr_sum)

        if net == ZERO2:
            raise ValueError("Net is zero; nothing to balance to vendor.")

        vendor_amt = abs(net)
        vendor_is_debit = (net < ZERO2)  # CN typically results in vendor debit

        jl.append(JLInput(
            account_id=supplier_account_id,
            drcr=vendor_is_debit,
            amount=vendor_amt,
            description=f"{narration} ({'Vendor reversal' if vendor_is_debit else 'Vendor payable'})",
        ))

        # strict total check vs header totals (compare absolute vendor amount)
        expected_vendor_amt = header_grand_total

        # optional RCM special-case (if your header stores base-only separately)
        if is_rcm and not cfg.rcm_supplier_includes_tax:
            base_only = getattr(header, "total_taxable_value", None)
            if base_only is not None:
                expected_vendor_amt = q2(base_only)

        if expected_vendor_amt > ZERO2:
            if (vendor_amt - expected_vendor_amt).copy_abs() > cfg.totals_tolerance:
                raise ValueError(
                    f"Grand total mismatch: expected={expected_vendor_amt} "
                    f"but computed vendor_amount={vendor_amt}. "
                    f"Fix Purchase totals computation before posting."
                )

        # =========================
        # 2) Inventory Moves
        # =========================
        im: List[IMInput] = []

        extra_cap = header_expenses if (header_expenses > ZERO2 and cfg.capitalize_header_expenses_to_inventory) else ZERO2

        if post_inventory:
            for ln in lines_list:
                if bool(getattr(ln, "is_service", False)):
                    continue
                if not getattr(ln, "product_id", None):
                    continue

                qty = q4(getattr(ln, "qty", None) or ZERO4)
                free_qty = q4(getattr(ln, "free_qty", None) or ZERO4)

                qty_for_cost = q4(qty + free_qty) if cfg.spread_cost_across_free_qty else qty
                if qty_for_cost == ZERO4:
                    continue

                base = q2(getattr(ln, "taxable_value", None) or ZERO2)

                cap_share = ZERO2
                if extra_cap > ZERO2 and total_goods_taxable > ZERO2 and base > ZERO2:
                    cap_share = q2(extra_cap * (base / total_goods_taxable))

                unit_cost = q4((base + cap_share) / qty_for_cost)

                im.append(IMInput(
                    product_id=int(getattr(ln, "product_id")),
                    qty=qty_for_cost,  # qty positive; move_type controls IN vs OUT
                    uom_id=int(getattr(ln, "uom_id")) if getattr(ln, "uom_id", None) else None,
                    uom_factor=Decimal("1"),
                    unit_cost=unit_cost,
                    move_type=inventory_move_type,  # IN for invoice, OUT for CN return
                    cost_source="PURCHASE",
                    cost_meta={
                        "doc_type": doc_type,
                        "line_no": getattr(ln, "line_no", None),
                        "qty": str(qty),
                        "free_qty": str(free_qty),
                        "qty_for_cost": str(qty_for_cost),
                        "taxable_value": str(base),
                        "cap_share": str(cap_share),
                        "spread_cost_across_free_qty": cfg.spread_cost_across_free_qty,
                        "affects_inventory": affects_inventory,
                    },
                    detail_id=int(getattr(ln, "id", 0) or 0) or None,
                    location_id=int(getattr(header, "godown_id", None) or getattr(header, "location_id", None) or 0) or None,
                ))

        # =========================
        # 3) Post via PostingService
        # =========================
        svc = PostingService(
            entity_id=entity_id,
            entityfin_id=int(entityfin_id) if entityfin_id else None,
            subentity_id=int(subentity_id) if subentity_id else None,
            user_id=int(user_id) if user_id else None,
        )

        entry = svc.post(
            txn_type=txn_type,
            txn_id=txn_id,
            voucher_no=voucher_no,
            voucher_date=bill_date,
            posting_date=posting_date,
            narration=narration,
            jl_inputs=jl,
            im_inputs=im,
            use_advisory_lock=True,
            mark_posted=True,
        )

        return entry
