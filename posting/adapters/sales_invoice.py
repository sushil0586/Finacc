# posting/adapters/sales_invoice.py
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable, List, Optional

from django.db import transaction

from posting.common.location_resolver import resolve_posting_location_id
from posting.services.posting_service import PostingService, JLInput, IMInput
from posting.models import InventoryMove, TxnType
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
class SalesInvoicePostingConfig:
    """
    Keep adapter stable and move policy decisions into config.
    Later you can store these per entity.
    """
    # Tolerance for header grand_total vs computed customer balancing amount.
    totals_tolerance: Decimal = Decimal("0.05")

    # If True: include free_qty in cost spreading (same as purchase)
    spread_cost_across_free_qty: bool = True

    # If True: post inventory moves for goods lines (Invoice OUT, CN IN when affects_inventory)
    post_inventory: bool = True


# =========================
# Sales Document Adapter (Invoice / CN / DN)
# =========================
class SalesInvoicePostingAdapter:
    """
    Supports:
      - Sales Invoice (DocType=1)
      - Sales Credit Note (DocType=2)
      - Sales Debit Note (DocType=3)

    Assumptions (same shape as purchase):
      DocType: 1=Invoice, 2=Credit Note, 3=Debit Note

    Inventory policy (mirror of purchase, but opposite direction):
      - Invoice => OUT (goods lines)
      - Credit Note => IN only if header.affects_inventory=True (sales return)
      - Debit Note => default no inventory (financial adjustment)
    """

    @staticmethod
    @transaction.atomic
    def post_sales_invoice(
        *,
        header: Any,
        lines: Iterable[Any],
        user_id: Optional[int],
        config: Optional[SalesInvoicePostingConfig] = None,
    ):
        cfg = config or SalesInvoicePostingConfig()

        # ---- scope ----
        entity_id = int(header.entity_id)
        entityfin_id = getattr(header, "entityfinid_id", None) or getattr(header, "entityfinid", None)
        subentity_id = getattr(header, "subentity_id", None)
        txn_id = int(header.id)

        bill_date = getattr(header, "bill_date", None)
        if not bill_date:
            raise ValueError("Sales header.bill_date is required for posting.")
        posting_date = getattr(header, "posting_date", None) or bill_date

        # ---- customer account id for posting + ledger validation ----
        customer_ledger_id = (
            getattr(header, "customer_ledger_id", None)
            or getattr(getattr(header, "customer", None), "ledger_id", None)
        )
        if not customer_ledger_id:
            raise ValueError("Header must have customer_ledger_id/customer.ledger_id.")

        customer_account_id = (
            getattr(header, "customer_id", None)
            or getattr(header, "customer_account_id", None)
            or getattr(header, "party_id", None)
            or getattr(header, "account_id", None)
        )
        if not customer_account_id:
            raise ValueError("Header must have customer_id/customer_account_id (ledger account id for customer).")
        customer_account_id = int(customer_account_id)

        # ---- doc type policy ----
        doc_type = int(getattr(header, "doc_type", 1))
        is_credit_note = (doc_type == 2)
        is_debit_note = (doc_type == 3)

        # polarity: invoice/DN = +1, CN = -1
        sign = Decimal("-1") if is_credit_note else Decimal("1")

        # TxnType must be distinct to avoid locator collisions.
        # Ensure these enums exist in posting.models.TxnType
        if is_credit_note:
            txn_type = TxnType.SALES_CREDIT_NOTE
        elif is_debit_note:
            txn_type = TxnType.SALES_DEBIT_NOTE
        else:
            txn_type = TxnType.SALES

        # ---- voucher no (for reporting only) ----
        voucher_no = (
            getattr(header, "sales_number", None)
            or getattr(header, "invoice_number", None)
            or getattr(header, "display_no", None)
            or getattr(header, "doc_no", None)
        )
        voucher_no = str(voucher_no) if voucher_no is not None else None

        doc_label = "Sales Invoice"
        if is_credit_note:
            doc_label = "Sales Credit Note"
        elif is_debit_note:
            doc_label = "Sales Debit Note"

        narration = f"{doc_label} {voucher_no or txn_id}"

        # ---- header totals ----
        header_grand_total = q2(getattr(header, "grand_total", None) or ZERO2)
        header_roundoff = q2(getattr(header, "roundoff", None) or getattr(header, "round_off", None) or ZERO2)

        # ---- inventory policy ----
        affects_inventory = bool(getattr(header, "affects_inventory", False))
        post_inventory = bool(cfg.post_inventory)

        inventory_move_type = "OUT"   # Invoice => OUT
        if is_credit_note:
            # CN => IN only if affects_inventory (sales return)
            post_inventory = post_inventory and affects_inventory
            inventory_move_type = "IN"
        elif is_debit_note:
            post_inventory = False  # default DN is financial only

        # ---- static accounts ----
        resolver = StaticAccountResolver(entity_id)

        ro_income_ac = int(resolver.get_account_id(StaticAccountCodes.ROUND_OFF_INCOME, required=True))
        ro_income_ledger = int(resolver.get_ledger_id(StaticAccountCodes.ROUND_OFF_INCOME, required=True))
        ro_exp_ac = int(resolver.get_account_id(StaticAccountCodes.ROUND_OFF_EXPENSE, required=True))
        ro_exp_ledger = int(resolver.get_ledger_id(StaticAccountCodes.ROUND_OFF_EXPENSE, required=True))

        # Output GST payable accounts
        out_cgst = resolver.get_account_id(StaticAccountCodes.OUTPUT_CGST, required=False)
        out_cgst_ledger = resolver.get_ledger_id(StaticAccountCodes.OUTPUT_CGST, required=False)
        out_sgst = resolver.get_account_id(StaticAccountCodes.OUTPUT_SGST, required=False)
        out_sgst_ledger = resolver.get_ledger_id(StaticAccountCodes.OUTPUT_SGST, required=False)
        out_igst = resolver.get_account_id(StaticAccountCodes.OUTPUT_IGST, required=False)
        out_igst_ledger = resolver.get_ledger_id(StaticAccountCodes.OUTPUT_IGST, required=False)
        out_cess = resolver.get_account_id(StaticAccountCodes.OUTPUT_CESS, required=False)
        out_cess_ledger = resolver.get_ledger_id(StaticAccountCodes.OUTPUT_CESS, required=False)
        

        # Revenue fallback (if product has no sales account)
        default_sales_ac = resolver.get_account_id(StaticAccountCodes.SALES_DEFAULT, required=False)
        if not default_sales_ac:
            # You can map SALES_REVENUE or SALES_MISC_INCOME instead depending on your codebase
            default_sales_ac = resolver.get_account_id(StaticAccountCodes.SALES_REVENUE, required=False)

        if not default_sales_ac:
            raise ValueError("Sales default revenue static account not mapped (SALES_DEFAULT/SALES_REVENUE).")
        default_sales_ac = int(default_sales_ac)

        # ---- ensure lines list ----
        lines_list = list(lines or [])
        if not lines_list:
            raise ValueError("Cannot post Sales document: no lines found.")
        charges_list = list(getattr(header, "charges", []).all() if hasattr(getattr(header, "charges", None), "all") else [])

        # per-product account resolver (no N+1)
        product_ids = [int(ln.product_id) for ln in lines_list if getattr(ln, "product_id", None)]
        prod_resolver = ProductAccountResolver(product_ids)

        # =========================
        # 1) Build Journal Lines
        # =========================
        jl: List[JLInput] = []

        output_tax = {"cgst": ZERO2, "sgst": ZERO2, "igst": ZERO2, "cess": ZERO2}

        # Tax polarity controls:
        # Sales Invoice/DN => Output GST payable is CREDIT
        # Sales CN         => Output GST payable is DEBIT (reversal)
        output_tax_is_debit = is_credit_note

        # 1A) Revenue per line (per-product sales account)
        for ln in lines_list:
            base = q2(getattr(ln, "taxable_value", None) or ZERO2)
            if base <= ZERO2:
                continue

            pid = getattr(ln, "product_id", None)
            line_sales_ac = getattr(ln, "sales_account_id", None)

            # IMPORTANT:
            # Your ProductAccountResolver currently has purchase_account_id(pid).
            # For sales, we expect sales_account_id(pid).
            # If you don't have it yet, implement similarly in product_accounts.py.
            sales_ac = None
            # For service invoices/CN/DN, prefer line-level sales_account.
            if line_sales_ac:
                sales_ac = int(line_sales_ac)
            if hasattr(prod_resolver, "sales_account_id"):
                sales_ac = sales_ac or prod_resolver.sales_account_id(pid)
            sales_ac = sales_ac or default_sales_ac
            sales_ac = int(sales_ac)

            # Revenue polarity: invoice/DN => CREDIT, CN => DEBIT
            revenue_is_debit = (sign < 0)

            jl.append(JLInput(
                account_id=sales_ac,
                drcr=revenue_is_debit,
                amount=q2(base.copy_abs()),
                description=f"{narration} (line {getattr(ln, 'line_no', '-')})",
                detail_id=int(getattr(ln, "id", 0) or 0) or None,
            ))

            # taxes accumulate
            output_tax["cgst"] = q2(output_tax["cgst"] + q2(getattr(ln, "cgst_amount", None) or ZERO2))
            output_tax["sgst"] = q2(output_tax["sgst"] + q2(getattr(ln, "sgst_amount", None) or ZERO2))
            output_tax["igst"] = q2(output_tax["igst"] + q2(getattr(ln, "igst_amount", None) or ZERO2))
            output_tax["cess"] = q2(output_tax["cess"] + q2(getattr(ln, "cess_amount", None) or ZERO2))

        # 1A2) Header charge lines (other income + output GST)
        other_income_code = getattr(StaticAccountCodes, "SALES_OTHER_CHARGES_INCOME", None)
        default_charge_income_ac = None
        if other_income_code:
            default_charge_income_ac = resolver.get_account_id(other_income_code, required=False)

        for ch in charges_list:
            c_base = q2(getattr(ch, "taxable_value", None) or ZERO2)
            if c_base > ZERO2:
                charge_ac = getattr(ch, "revenue_account_id", None) or default_charge_income_ac or default_sales_ac
                jl.append(JLInput(
                    account_id=int(charge_ac),
                    drcr=(sign < 0),  # invoice/DN => credit, CN => debit
                    amount=q2(c_base.copy_abs()),
                    description=f"{narration} (charge {getattr(ch, 'line_no', '-')})",
                    detail_id=int(getattr(ch, "id", 0) or 0) or None,
                ))

            output_tax["cgst"] = q2(output_tax["cgst"] + q2(getattr(ch, "cgst_amount", None) or ZERO2))
            output_tax["sgst"] = q2(output_tax["sgst"] + q2(getattr(ch, "sgst_amount", None) or ZERO2))
            output_tax["igst"] = q2(output_tax["igst"] + q2(getattr(ch, "igst_amount", None) or ZERO2))

        # 1B) Output GST payable (credit on invoice/DN; debit on CN)
        def _add_out(acct_id: Optional[int], ledger_id: Optional[int], amt: Decimal, label: str):
            if amt <= ZERO2:
                return
            if not acct_id:
                raise ValueError(f"{label} not mapped.")
            jl.append(JLInput(
                account_id=int(acct_id),
                ledger_id=int(ledger_id) if ledger_id else None,
                drcr=output_tax_is_debit,
                amount=amt,
                description=f"{narration} ({label})",
            ))




        _add_out(out_cgst, out_cgst_ledger, output_tax["cgst"], "Output CGST")
        _add_out(out_sgst, out_sgst_ledger, output_tax["sgst"], "Output SGST")
        _add_out(out_igst, out_igst_ledger, output_tax["igst"], "Output IGST")
        _add_out(out_cess, out_cess_ledger, output_tax["cess"], "Output CESS")

        # 1C) Round-off (same semantics as purchase)
        # Original semantics:
        #   roundoff > 0 => Dr expense, < 0 => Cr income
        # For CN, flip direction.
        if header_roundoff != ZERO2:
            if header_roundoff > ZERO2:
                jl.append(JLInput(
                    account_id=ro_exp_ac,
                    ledger_id=ro_exp_ledger,
                    drcr=not is_credit_note,  # invoice/DN Dr, CN Cr
                    amount=header_roundoff,
                    description=f"{narration} (Round-off expense)",
                ))
            else:
                jl.append(JLInput(
                    account_id=ro_income_ac,
                    ledger_id=ro_income_ledger,
                    drcr=is_credit_note,  # invoice/DN Cr, CN Dr
                    amount=abs(header_roundoff),
                    description=f"{narration} (Round-off income)",
                ))

        # Legacy fallback for old payloads that still use header.total_other_charges without charge lines.
        other_charges = q2(getattr(header, "total_other_charges", None) or ZERO2)
        if other_charges > ZERO2 and not charges_list:
            if not other_income_code:
                raise ValueError("StaticAccountCodes.SALES_OTHER_CHARGES_INCOME missing.")
            other_income_ac = resolver.get_account_id(other_income_code, required=True)
            jl.append(JLInput(
                account_id=int(other_income_ac),
                ledger_id=resolver.get_ledger_id(other_income_code, required=True) if other_income_code else None,
                drcr=is_credit_note,  # True for CN (debit), False for invoice (credit)
                amount=other_charges,
                description=f"{narration} (Other charges)",
            ))

        tcs = q2(getattr(header, "tcs_amount", None) or ZERO2)
        tcs_is_reversal = bool(getattr(header, "tcs_is_reversal", False))
        if tcs > ZERO2:
            tcs_payable_ac = resolver.get_account_id(StaticAccountCodes.TCS_PAYABLE, required=True)
            tcs_payable_ledger = resolver.get_ledger_id(StaticAccountCodes.TCS_PAYABLE, required=True)
            if tcs_is_reversal:
                # Credit-note reversal style: reduce TCS payable and increase customer credit.
                jl.append(JLInput(
                    account_id=int(tcs_payable_ac),
                    ledger_id=int(tcs_payable_ledger),
                    drcr=True,  # DR
                    amount=tcs,
                    description=f"{narration} (TCS reversal)",
                ))
                jl.append(JLInput(
                    account_id=int(header.customer_id),
                    ledger_id=int(customer_ledger_id),
                    drcr=False,  # CR
                    amount=tcs,
                    description=f"{narration} (Customer TCS reversal)",
                ))
            else:
                # Standard collection style.
                jl.append(JLInput(
                    account_id=int(header.customer_id),
                    ledger_id=int(customer_ledger_id),
                    drcr=True,  # DR
                    amount=tcs,
                    description=f"{narration} (TCS collected)",
                ))
                jl.append(JLInput(
                    account_id=int(tcs_payable_ac),
                    ledger_id=int(tcs_payable_ledger),
                    drcr=False,  # CR
                    amount=tcs,
                    description=f"{narration} (TCS payable)",
                ))


        # 1D) Customer balancing line (works for Invoice/CN/DN)
        dr_sum = q2(sum(x.amount for x in jl if x.drcr))
        cr_sum = q2(sum(x.amount for x in jl if not x.drcr))
        net = q2(dr_sum - cr_sum)

        if net == ZERO2:
            raise ValueError("Net is zero; nothing to balance to customer.")

        customer_amt = abs(net)

        # If net is negative => more credits => customer must be DEBIT (invoice)
        # If net is positive => more debits  => customer must be CREDIT (credit note)
        customer_is_debit = (net < ZERO2)

        jl.append(JLInput(
            account_id=customer_account_id,
            ledger_id=int(customer_ledger_id),
            drcr=customer_is_debit,
            amount=customer_amt,
            description=f"{narration} ({'Customer receivable' if customer_is_debit else 'Customer reversal'})",
        ))

        # strict total check vs header totals (compare absolute customer amount)
        expected_customer_amt = header_grand_total
        if expected_customer_amt > ZERO2:
            if (customer_amt - expected_customer_amt).copy_abs() > cfg.totals_tolerance:
                raise ValueError(
                    f"Grand total mismatch: expected={expected_customer_amt} "
                    f"but computed customer_amount={customer_amt}. "
                    f"Fix Sales totals computation before posting."
                )

        # =========================
        # 2) Inventory Moves
        # =========================
        im: List[IMInput] = []

        # NOTE:
        # For Sales, true unit_cost should come from valuation engine (FIFO/WA),
        # but you're explicitly asking to keep it same style as purchase.
        # So we compute unit_cost from taxable_value/qty_for_cost (like purchase).
        # We can later replace with valuation-derived cost without changing PostingService contract.

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
                unit_cost = q4(base / qty_for_cost)
                location_id = resolve_posting_location_id(
                    entity_id=entity_id,
                    subentity_id=int(subentity_id) if subentity_id else None,
                    godown_id=getattr(header, "godown_id", None),
                    location_id=getattr(header, "location_id", None),
                )

                im.append(IMInput(
                    product_id=int(getattr(ln, "product_id")),
                    qty=qty_for_cost,  # qty positive; move_type controls IN vs OUT
                    uom_id=int(getattr(ln, "uom_id")) if getattr(ln, "uom_id", None) else None,
                    uom_factor=Decimal("1"),
                    unit_cost=unit_cost,
                    move_type=inventory_move_type,  # OUT for invoice, IN for CN return
                    cost_source="SALES",
                    movement_nature=InventoryMove.MovementNature.SALE if inventory_move_type == InventoryMove.MoveType.OUT else InventoryMove.MovementNature.RETURN,
                    movement_reason=str(doc_type or "sale"),
                    cost_meta={
                        "doc_type": doc_type,
                        "line_no": getattr(ln, "line_no", None),
                        "qty": str(qty),
                        "free_qty": str(free_qty),
                        "qty_for_cost": str(qty_for_cost),
                        "taxable_value": str(base),
                        "spread_cost_across_free_qty": cfg.spread_cost_across_free_qty,
                        "affects_inventory": affects_inventory,
                    },
                    detail_id=int(getattr(ln, "id", 0) or 0) or None,
                    location_id=location_id,
                    source_location_id=location_id if inventory_move_type == InventoryMove.MoveType.OUT else None,
                    destination_location_id=location_id if inventory_move_type != InventoryMove.MoveType.OUT else None,
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
