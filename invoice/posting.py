# posting.py
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, List, Optional
from django.db.models import Q

from django.db import transaction, models
from django.db.models import Sum
from django.utils.timezone import now
from .models import DetailKind
from .services.config import EffectivePostingConfig

from invoice.models import (
    JournalLine, InventoryMove, salesOrderdetails, tdsmain,PostingConfig,TxnType,VoucherType
)
from .stocktransconstant import stocktransconstant

from .accounts import (
    get_sales_account_for_product,
    get_purchase_account_for_product,
    get_tax_accounts,
    get_input_tax_accounts,
    get_roundoff_accounts,
    get_cash_account,
    get_tcs_accounts,
    get_tds_accounts,
    get_expense_recovery_account,
    get_purchase_misc_expense_account,
)

# ---------- rounding helpers ----------
ZERO2 = Decimal("0.00")
ZERO4 = Decimal("0.0000")
Q2    = Decimal("0.01")
Q4    = Decimal("0.0001")

def q2(x):
    try:
        return Decimal(x or 0).quantize(Q2, rounding=ROUND_HALF_UP)
    except Exception:
        return ZERO2

def q4(x):
    try:
        return Decimal(x or 0).quantize(Q4, rounding=ROUND_HALF_UP)
    except Exception:
        return ZERO4

def apply_roundoff_to_total(gtotal, roundoff):
    """
    gtotal: base (pre-round) total
    roundoff > 0  => subtract from final total
    roundoff < 0  => add abs(roundoff) to final total
    """
    if roundoff > ZERO2:
        return q2(gtotal - roundoff)
    elif roundoff < ZERO2:
        return q2(gtotal + abs(roundoff))
    return q2(gtotal)

def _sum_taxes_from_detail_objs(details) -> dict:
    igst = cgst = sgst = cess = ZERO2
    for d in details or []:
        igst += q2(getattr(d, "igst", ZERO2))
        cgst += q2(getattr(d, "cgst", ZERO2))
        sgst += q2(getattr(d, "sgst", ZERO2))
        cess += q2(getattr(d, "cess", ZERO2))
    return {"igst": igst, "cgst": cgst, "sgst": sgst, "cess": cess}

def _derive_sales_taxes(header, details) -> dict:
    """
    1) Use header component fields if > 0
    2) Else sum from details
    3) Else if header.totalgst > 0, allocate by scheme (IGST vs CGST/SGST)
    """
    sums = _sum_taxes_from_detail_objs(details)
    igst = q2(getattr(header, "igst", ZERO2)) or sums["igst"]
    cgst = q2(getattr(header, "cgst", ZERO2)) or sums["cgst"]
    sgst = q2(getattr(header, "sgst", ZERO2)) or sums["sgst"]
    cess = q2(getattr(header, "cess", ZERO2)) or sums["cess"]

    if igst == ZERO2 and cgst == ZERO2 and sgst == ZERO2:
        totalgst = q2(getattr(header, "totalgst", ZERO2))
        if totalgst > ZERO2:
            if bool(getattr(header, "isigst", False)):
                igst = totalgst
            else:
                half = q2(totalgst / Decimal("2"))
                cgst = half
                sgst = totalgst - half
    return {"igst": igst, "cgst": cgst, "sgst": sgst, "cess": cess}

def _derive_purchase_taxes(header, details) -> dict:
    """
    1) Use header component fields if > 0
    2) Else sum from details
    3) Else if header.totalgst > 0, allocate IGST if any line is IGST; else split to CGST/SGST
    """
    igst = q2(getattr(header, "igst", ZERO2))
    cgst = q2(getattr(header, "cgst", ZERO2))
    sgst = q2(getattr(header, "sgst", ZERO2))
    cess = q2(getattr(header, "cess", ZERO2))
    if igst > ZERO2 or cgst > ZERO2 or sgst > ZERO2 or cess > ZERO2:
        return {"igst": igst, "cgst": cgst, "sgst": sgst, "cess": cess}

    sums = {"igst": ZERO2, "cgst": ZERO2, "sgst": ZERO2, "cess": ZERO2}
    any_isigst = False
    any_igst_pct = False
    for d in (details or []):
        sums["igst"] += q2(getattr(d, "igst", ZERO2))
        sums["cgst"] += q2(getattr(d, "cgst", ZERO2))
        sums["sgst"] += q2(getattr(d, "sgst", ZERO2))
        sums["cess"] += q2(getattr(d, "cess", ZERO2))
        any_isigst = any_isigst or bool(getattr(d, "isigst", False))
        any_igst_pct = any_igst_pct or (q2(getattr(d, "igstpercent", ZERO2)) > ZERO2)

    if any(v > ZERO2 for v in sums.values()):
        return sums

    totalgst = q2(getattr(header, "totalgst", ZERO2))
    if totalgst > ZERO2:
        if any_isigst or any_igst_pct:
            return {"igst": totalgst, "cgst": ZERO2, "sgst": ZERO2, "cess": ZERO2}
        half = q2(totalgst / Decimal("2"))
        return {"igst": ZERO2, "cgst": half, "sgst": totalgst - half, "cess": ZERO2}

    return {"igst": ZERO2, "cgst": ZERO2, "sgst": ZERO2, "cess": ZERO2}

# ======================================================
# Poster: GL + Inventory
# ======================================================
class Poster:
    def __init__(self, entry, entity, user, transactiontype, transactionid, voucherno, entrydate, entrydt):
        self.entry = entry
        # Accept either an entity object or a raw id
        self.entity = entity
        self.entity_id = getattr(entity, "id", entity)
        if not self.entity_id:
            raise ValueError("Poster: entity/entity_id is required")

        self.user = user
        self.txntype = transactiontype
        self.txnid = transactionid
        self.voucherno = str(voucherno) if voucherno is not None else None

        # JournalLine typically has `entrydate` (date) and `entrydatetime` (datetime)
        self.entrydate = getattr(entrydate, "date", lambda: entrydate)()
        self.entrydt = entrydt

    # ---------- stamping ----------
    def _stamp_jl(self, jl: JournalLine) -> JournalLine:
        if hasattr(jl, "entry"):            jl.entry = self.entry
        if hasattr(jl, "entity"):           jl.entity = self.entity
        if hasattr(jl, "transactiontype"):  jl.transactiontype = self.txntype
        if hasattr(jl, "transactionid"):    jl.transactionid = self.txnid
        if hasattr(jl, "voucherno"):        jl.voucherno = self.voucherno
        if hasattr(jl, "entrydate"):        jl.entrydate = self.entrydate
        if hasattr(jl, "entrydt"):          jl.entrydt   = self.entrydt
        if hasattr(jl, "createdby"):        jl.createdby = getattr(self, "header", None) and getattr(self.header, "createdby", None)
        return jl

    # ---------- builders ----------
    def _account_head(self, account, is_debit: bool):
        """
        Safer AccountHead resolution:
        - Prefer side-specific head (debitaccounthead / creditaccounthead)
        - If missing OR wrong, fall back to the other side head
        - Else fall back to accounthead
        """
        if account is None:
            return None

        debit_head  = getattr(account, "debitaccounthead", None)
        credit_head = getattr(account, "creditaccounthead", None)
        base_head   = getattr(account, "accounthead", None)

        # normal preference
        preferred = debit_head if is_debit else credit_head
        if preferred:
            return preferred

        # fallback to the other side head (this fixes your SR case)
        other = credit_head if is_debit else debit_head
        if other:
            return other

        return base_head

    def _jl(self, *, account, desc="", dr=None, cr=None, accounthead=None, detailid=None):
        amt_dr = q2(dr or ZERO2)
        amt_cr = q2(cr or ZERO2)
        if amt_dr > ZERO2 and amt_cr > ZERO2:
            raise ValueError("Give only one of dr/cr")
        if amt_dr == ZERO2 and amt_cr == ZERO2:
            return None

        if accounthead is None:
            accounthead = self._account_head(account, is_debit=(amt_dr > ZERO2))

        return JournalLine(
            entry=self.entry,
            entity_id=getattr(self.entity, "id", self.entity),
            transactiontype=self.txntype,
            transactionid=self.txnid,
            voucherno=self.voucherno,
            entrydate=self.entrydate,
            entrydatetime=self.entrydt,
            createdby=self.user,

            account=account,
            accounthead=accounthead,
            drcr=(amt_dr > ZERO2),
            amount=(amt_dr if amt_dr > ZERO2 else amt_cr),
            desc=desc,
            detailid=detailid,
        )
    
    def _im(self, *, product, qty, unit_cost=ZERO4, move_type="OUT", detailid=None, location=None, uom=None):
        qty = q4(qty)
        return InventoryMove(
            # <<< voucher keys — set at creation >>>
            entry=self.entry,
            entity_id=self.entity_id,
            transactiontype=self.txntype,
            transactionid=self.txnid,
            voucherno=self.voucherno,
            entrydate=self.entrydate,
            entrydatetime=self.entrydt,
            createdby=self.user,

            # business fields
            product=product,
            location=location,
            uom=uom,
            detailid=detailid,
            qty=qty,
            unit_cost=q4(unit_cost),
            ext_cost=q2(abs(qty) * q4(unit_cost)),
            move_type=move_type,
        )

    def _fresh_details(self, header, passed):
        """
        Return a complete, saved list of details for this header.
        Reload from DB if 'passed' is empty, has unsaved items, or looks partial.
        """
        try:
            items = list(passed or [])
            if (not items) or any(getattr(d, "pk", None) is None for d in items):
                raise ValueError("unsaved/empty")
            db_count = salesOrderdetails.objects.filter(salesorderheader=header).count()
            if len(items) < db_count:
                raise ValueError("partial")
            return items
        except Exception:
            return list(
                salesOrderdetails.objects
                .filter(salesorderheader=header)
                .select_related("product", "product__sales_account", "product__purchase_account")
                .prefetch_related("otherchargesdetail")
            )

    # ---------- cleanup ----------
    def _build_delete_filter(self, Model):
        """
        Only delete rows that belong to THIS voucher.
        Prefer (entity, transactiontype, transactionid).
        Fallback to (entity, source_type/source_id) or (entity, voucherno[, entry]) if needed.
        """
        f = {}
        if hasattr(Model, "entity"):          f["entity"] = self.entity
        if hasattr(Model, "transactiontype"): f["transactiontype"] = self.txntype
        if hasattr(Model, "transactionid"):   f["transactionid"] = self.txnid
        if all(k in f for k in ("entity", "transactiontype", "transactionid")):
            return f

        f2 = {}
        if hasattr(Model, "entity"):      f2["entity"] = self.entity
        if hasattr(Model, "source_type"): f2["source_type"] = "S"
        if hasattr(Model, "source_id"):   f2["source_id"] = self.txnid
        if len(f2) >= 3:
            return f2

        f3 = {}
        if hasattr(Model, "entity"):     f3["entity"] = self.entity
        if hasattr(Model, "voucherno"):  f3["voucherno"] = self.voucherno
        if hasattr(Model, "entry"):      f3["entry"] = self.entry
        if "entity" in f3 and "voucherno" in f3:
            return f3

        return {}

    def _journal_type_bucket(self):
        return [TxnType.JOURNAL, TxnType.JOURNAL_CASH, TxnType.JOURNAL_BANK]

    def clear_existing(self):
        """
        JOURNAL family: delete strictly by (entity, transactionid) so updates are idempotent
        and different vouchers sharing the same voucherno never touch each other.

        OPTIONAL legacy cleanup by voucherno runs ONLY for truly legacy rows
        (transactionid NULL or 0) and is constrained to the current transactiontype.
        """

        if getattr(self, "txntype", None) in self._journal_type_bucket():
            # --- primary, safe delete: only THIS header
            jl_q = Q(entity=self.entity, transactionid=self.txnid,
                    transactiontype__in=self._journal_type_bucket())
            JournalLine.objects.filter(jl_q).delete()

            # --- OPTIONAL: extremely narrow legacy cleanup ---
            # Run only if you want to purge ancient rows that were saved without transactionid.
            # Comment this block out entirely if you don't need it.
            if getattr(self, "voucherno", None):
                legacy_q = (
                    Q(entity=self.entity, voucherno=self.voucherno)
                    & Q(transactiontype=self.txntype)  # <-- only current subtype (no family)
                    & (Q(transactionid__isnull=True) | Q(transactionid=0))  # <-- true legacy only
                )
                JournalLine.objects.filter(legacy_q).delete()

            # Inventory moves (if any for journals) — scope strictly to this header
            im_q = Q(entity=self.entity, transactionid=self.txnid)
            InventoryMove.objects.filter(im_q).delete()

        else:
            # --- keep your existing non-journal behavior unchanged ---
            jl_q = Q()
            if hasattr(JournalLine, "entity"):
                jl_q &= Q(entity=self.entity)
            if hasattr(JournalLine, "transactiontype"):
                jl_q &= Q(transactiontype=self.txntype)

            if hasattr(JournalLine, "voucherno") and self.voucherno is not None:
                jl_q &= Q(voucherno=self.voucherno)
            elif hasattr(JournalLine, "transactionid"):
                jl_q &= Q(transactionid=self.txnid)
            else:
                jl_q = None

            if jl_q is not None:
                JournalLine.objects.filter(jl_q).delete()

            im_q = Q()
            if hasattr(InventoryMove, "entity"):
                im_q &= Q(entity=self.entity)
            if hasattr(InventoryMove, "transactiontype"):
                im_q &= Q(transactiontype=self.txntype)

            if hasattr(InventoryMove, "voucherno") and self.voucherno is not None:
                im_q &= Q(voucherno=self.voucherno)
            elif hasattr(InventoryMove, "transactionid"):
                im_q &= Q(transactionid=self.txnid)
            elif hasattr(InventoryMove, "source_type") and hasattr(InventoryMove, "source_id"):
                im_q &= Q(source_type="S", source_id=self.txnid)
            else:
                im_q = None

            if im_q is not None:
                InventoryMove.objects.filter(im_q).delete()

    # ======================================================
    # SALES
    # ======================================================
    def _issue_unit_cost(self, detail) -> Decimal:
        """
        Choose issue cost:
        product.cost/avg/std -> last PO rate -> (amount - othercharges)/qty -> ratebefdiscount -> rate -> 0.00
        """
        product = getattr(detail, "product", None)
        if product is not None:
            for attr in ("costprice", "avgcost", "average_cost", "standard_cost", "std_cost"):
                v = getattr(product, attr, None)
                if v is not None and q2(v) > ZERO2:
                    return q2(v)
            # last PO rate (optional)
            try:
                from purchases.models import PurchaseOrderDetail
                last_rate = (
                    PurchaseOrderDetail.objects
                    .filter(product=product)
                    .order_by("-id")
                    .values_list("rate", flat=True)
                    .first()
                )
                if last_rate:
                    return q2(last_rate)
            except Exception:
                pass

        qty = q4(getattr(detail, "orderqty", ZERO4) or ZERO4)
        if qty == ZERO4:
            qty = q4(getattr(detail, "pieces", ZERO4) or ZERO4)
        if qty > ZERO4:
            base = q2(getattr(detail, "amount", ZERO2)) - q2(getattr(detail, "othercharges", ZERO2))
            if base > ZERO2:
                return q2(base / qty)

        for attr in ("ratebefdiscount", "rate"):
            v = getattr(detail, attr, None)
            if v is not None and q2(v) > ZERO2:
                return q2(v)
        return ZERO2

    def _assign_move_detail_and_links(self, mv, header, detail):
        if hasattr(mv, "detailid"):             mv.detailid = detail.id
        elif hasattr(mv, "detail_id"):          mv.detail_id = detail.id
        elif hasattr(mv, "detail"):             setattr(mv, "detail_id", detail.id)
        elif hasattr(mv, "salesorderdetail_id"): mv.salesorderdetail_id = detail.id
        elif hasattr(mv, "salesorderdetail"):   setattr(mv, "salesorderdetail_id", detail.id)

        if hasattr(mv, "transactiontype"): mv.transactiontype = self.txntype
        if hasattr(mv, "transactionid"):   mv.transactionid   = self.txnid
        if hasattr(mv, "source_type"):     mv.source_type     = "S"
        if hasattr(mv, "source_id"):       mv.source_id       = self.txnid
        if hasattr(mv, "entity"):          mv.entity          = self.entity

    def _ensure_move_costs(self, mv, qty, unit_cost):
        if hasattr(mv, "unit_cost"):
            mv.unit_cost = q2(unit_cost)
            u = mv.unit_cost
        elif hasattr(mv, "unitcost"):
            mv.unitcost = q2(unit_cost)
            u = mv.unitcost
        else:
            setattr(mv, "unit_cost", q2(unit_cost))
            u = mv.unit_cost

        qty_abs = abs(q4(qty))
        ext_val = q2(qty_abs * u)
        if hasattr(mv, "ext_cost"):
            mv.ext_cost = ext_val
        elif hasattr(mv, "extcost"):
            mv.extcost = ext_val
        else:
            setattr(mv, "ext_cost", ext_val)


        # ======================================================
    # PURCHASE RETURN
    # ======================================================
    @transaction.atomic
    def post_purchase_return(self, header, details, extra_charges_map: Optional[dict] = None):
        """
        Purchase Return posting (PR) = reverse of Purchase:
        - Cr Purchase/Expense (reverse purchase)
        - Cr Input GST (reverse ITC) ONLY if reversecharge=False
          ✅ UPDATE-PROOF: if header tax fields are 0, fallback to sum(detail taxes)
        - Cr other charges reversal (reverse of purchase other-charge debits)
        - Dr Supplier/Cash (debit note / refund)
        - Inventory OUT
        """
        self.header = header
        self.clear_existing()

        jl: List[JournalLine] = []
        im: List[InventoryMove] = []

        # -----------------------------
        # 1) Ensure we have saved PR details
        # -----------------------------
        try:
            details = list(details or [])
            if (not details) or any(getattr(d, "pk", None) is None for d in details):
                raise ValueError("unsaved/empty")
        except Exception:
            # If your purchase return uses a different related_name, change this:
            details = list(
                getattr(header, "purchasereturndetails")
                .select_related("product", "product__sales_account", "product__purchase_account")
                .prefetch_related("otherchargesdetail")
                .all()
            )

        if not details:
            return

        cash_acct = get_cash_account(self.entity)
        tax_in    = get_input_tax_accounts(self.entity)  # {"igst":..,"cgst":..,"sgst":..,"cess":..}
        ro_income, ro_expense = get_roundoff_accounts(self.entity)

        # fallback account if other-charge has no account
        misc_exp_acct = get_purchase_misc_expense_account(self.entity)

        gtotal_base = q2(getattr(header, "gtotal", ZERO2))
        roundoff    = q2(getattr(header, "roundOff", ZERO2))
        expenses    = q2(getattr(header, "expenses", ZERO2))
        is_cash     = (getattr(header, "billcash", None) in (0, 2))

        supplier_acct = getattr(header, "account", None) or getattr(header, "accountid", None)

        first_purch_acct = None
        base_total = ZERO2  # total purchase base (without taxes/charges)

        last_purch_acct = None
        last_detail_id  = None

        # -----------------------------
        # 2) Reverse purchase base + reverse other-charges + Stock OUT
        # -----------------------------
        for d in details:
            prod = getattr(d, "product", None)

            line_amt      = q2(getattr(d, "amount", ZERO2))
            other_on_line  = q2(getattr(d, "othercharges", ZERO2))
            base           = q2(line_amt - other_on_line)

            # Cr Purchase/Expense (reverse purchase)
            if base > ZERO2 and prod:
                purch_acct = get_purchase_account_for_product(prod)
                if purch_acct is None:
                    raise ValueError(f"Purchase account not set for product {getattr(prod,'id',None)}")

                if first_purch_acct is None:
                    first_purch_acct = purch_acct
                last_purch_acct = purch_acct
                last_detail_id  = getattr(d, "id", None)

                jl.append(self._jl(
                    account=purch_acct,
                    accounthead=(
                        getattr(purch_acct, "creditaccounthead", None)
                        or getattr(purch_acct, "debitaccounthead", None)   # fallback safe
                        or getattr(purch_acct, "accounthead", None)
                    ),
                    cr=base,
                    desc=f"Purchase Return line #{getattr(d,'id',None)}",
                    detailid=getattr(d, "id", None)
                ))
                base_total = q2(base_total + base)

            # Reverse Other charges (Purchase debited these → PR credits them)
            charges = []
            rel = getattr(d, "otherchargesdetail", None)
            if rel is not None:
                try:
                    charges.extend(list(rel.all()))
                except Exception:
                    pass
            if extra_charges_map and getattr(d, "id", None) in extra_charges_map:
                charges.extend(extra_charges_map[d.id])

            for oc in charges:
                amt = q2(getattr(oc, "amount", ZERO2))
                if amt > ZERO2:
                    acct = getattr(oc, "account", None) or misc_exp_acct
                    jl.append(self._jl(
                        account=acct,
                        cr=amt,
                        desc=f"PR other charge reversal line #{getattr(d,'id',None)}",
                        detailid=getattr(d, "id", None)
                    ))

            # Inventory OUT
            qty = getattr(d, "orderqty", None)
            qty = getattr(d, "pieces", 0) if q4(qty) == ZERO4 else qty
            qty = q4(qty)

            if prod and qty != ZERO4:
                # For PR OUT, you can use purchase rate as unit_cost
                rate_val = getattr(d, "rate", None)
                if rate_val is None or q4(rate_val) == ZERO4:
                    # fallback: base/qty (base excludes othercharges)
                    unit_cost = q4((base / qty) if qty != ZERO4 else ZERO4)
                else:
                    unit_cost = q4(rate_val)

                mv = self._im(
                    product=prod,
                    qty=-qty,               # -ve for OUT
                    unit_cost=unit_cost,
                    move_type="OUT",
                    detailid=getattr(d, "id", None),
                )
                self._assign_move_detail_and_links(mv, header, d)
                self._ensure_move_costs(mv, qty=-qty, unit_cost=unit_cost)
                im.append(mv)

        # -----------------------------
        # 3) Taxes reversal (Cr input GST) ONLY if reversecharge=False
        #    ✅ UPDATE-PROOF fallback to detail sums if header tax fields are 0
        # -----------------------------
        if not getattr(header, "reversecharge", False):
            t = _derive_purchase_taxes(header, details)
            igst, cgst, sgst, cess = t["igst"], t["cgst"], t["sgst"], t["cess"]

            if igst > ZERO2 and tax_in.get("igst"):
                jl.append(self._jl(account=tax_in["igst"], cr=igst, desc="Input IGST (PR reversal)"))
            if cgst > ZERO2 and tax_in.get("cgst"):
                jl.append(self._jl(account=tax_in["cgst"], cr=cgst, desc="Input CGST (PR reversal)"))
            if sgst > ZERO2 and tax_in.get("sgst"):
                jl.append(self._jl(account=tax_in["sgst"], cr=sgst, desc="Input SGST (PR reversal)"))
            if cess > ZERO2 and tax_in.get("cess"):
                jl.append(self._jl(account=tax_in["cess"], cr=cess, desc="Input CESS (PR reversal)"))

        # Header expenses reversal (credit, because purchase posted it as debit)
        if expenses > ZERO2:
            jl.append(self._jl(account=misc_exp_acct, cr=expenses, desc="Expenses (PR header reversal)"))

        # Roundoff (keep same convention as your other methods)
        if roundoff != ZERO2:
            if roundoff > ZERO2:
                jl.append(self._jl(account=ro_expense, dr=roundoff, desc="Round-off (PR)"))
            else:
                jl.append(self._jl(account=ro_income,  cr=abs(roundoff), desc="Round-off (PR)"))

        final_total = apply_roundoff_to_total(gtotal_base, roundoff)
        header.gtotal = final_total

        # -----------------------------
        # 4) Supplier/Cash DEBIT (Debit Note / Refund receivable)
        # -----------------------------
        # Compute net debit to supplier = credits so far - debits so far
        dr_before = q2(sum(l.amount for l in jl if l and l.drcr))
        cr_before = q2(sum(l.amount for l in jl if l and not l.drcr))
        supplier_debit = q2(cr_before - dr_before)

        if supplier_debit <= ZERO2:
            raise ValueError("Purchase Return computed debit is not positive (check amounts/taxes).")

        if is_cash:
            jl.append(self._jl(account=cash_acct, dr=supplier_debit, desc="Cash refund receivable (PR)"))
        else:
            if supplier_acct is None:
                raise ValueError("Supplier account not set on purchase return header.")
            jl.append(self._jl(account=supplier_acct, dr=supplier_debit, desc="Supplier debit note (PR)"))

        # -----------------------------
        # 5) Final balancing guard (tiny residual)
        # -----------------------------
        dr_mem = q2(sum(l.amount for l in jl if l and l.drcr))
        cr_mem = q2(sum(l.amount for l in jl if l and not l.drcr))
        if dr_mem != cr_mem:
            missing = q2(dr_mem - cr_mem)
            # choose a sensible target
            target_acct = last_purch_acct or first_purch_acct or misc_exp_acct
            if missing > ZERO2:
                # Need extra CR
                jl.append(self._jl(account=target_acct, cr=missing, desc="PR adjustment", detailid=last_detail_id))
            else:
                # Need extra DR
                jl.append(self._jl(account=(cash_acct if is_cash else supplier_acct),
                                   dr=abs(missing), desc="PR adjustment"))

        # -----------------------------
        # 6) Final check + persist
        # -----------------------------
        dr_mem = q2(sum(l.amount for l in jl if l and l.drcr))
        cr_mem = q2(sum(l.amount for l in jl if l and not l.drcr))
        if dr_mem != cr_mem:
            detail = [("DR" if l.drcr else "CR",
                       getattr(getattr(l, "account", None), "accountname", str(getattr(l, "account", None))),
                       f"{l.amount:.2f}", l.desc) for l in jl if l]
            raise ValueError(f"Pre-save imbalance: DR {dr_mem:.2f} != CR {cr_mem:.2f}; lines={detail}")

        JournalLine.objects.bulk_create([l for l in jl if l is not None])
        if im:
            InventoryMove.objects.bulk_create(im)

        # PR should not create tdsmain; if any old rows exist, delete them
        tdsmain.objects.filter(entityid=self.entity, transactiontype=self.txntype, transactionno=self.txnid).delete()

        self._assert_balanced()


    @transaction.atomic
    def post_sales(self, header, details, extra_charges_map: Optional[dict] = None):
        self.header = header
        self.clear_existing()

        jl: List[JournalLine] = []
        im: List[InventoryMove] = []

        details = self._fresh_details(header, details)
        if not details:
            return

        cash_acct = get_cash_account(self.entity)
        tax_out   = get_tax_accounts(self.entity)
        ro_income, ro_expense = get_roundoff_accounts(self.entity)
        tcs_1h2, tcs_2 = get_tcs_accounts(self.entity)
        tds_recv, _ = get_tds_accounts(self.entity)

        gtotal_base = q2(getattr(header, "gtotal", ZERO2))
        roundoff    = q2(getattr(header, "roundOff", ZERO2))
        expenses    = q2(getattr(header, "expenses", ZERO2))
        tcs_a       = q2(getattr(header, "tcs206c1ch2", ZERO2))
        tcs_b       = q2(getattr(header, "tcs206C2", ZERO2))
        tds_amt     = q2(getattr(header, "tds194q1", ZERO2))
        is_cash     = (getattr(header, "billcash", None) in (0, 2))

        first_sale_acct = None
        rev_total = ZERO2

        for d in details:
            line_amt = q2(getattr(d, "amount", ZERO2))
            other_on_line = q2(getattr(d, "othercharges", ZERO2))
            rev = q2(line_amt - other_on_line)

            if rev > ZERO2 and getattr(d, "product", None):
                sale_acct = get_sales_account_for_product(d.product)
                if first_sale_acct is None:
                    first_sale_acct = sale_acct
                line = self._jl(
                    account=sale_acct,
                    accounthead=getattr(sale_acct, "creditaccounthead", None),
                    cr=rev, desc=f"Sales line #{d.id}", detailid=d.id
                )
                if line: jl.append(line)
                rev_total = q2(rev_total + rev)

            charges = []
            rel = getattr(d, "otherchargesdetail", None)
            if rel is not None:
                try:
                    charges.extend(list(rel.all()))
                except Exception:
                    pass
            if extra_charges_map and getattr(d, "id", None) in extra_charges_map:
                charges.extend(extra_charges_map[d.id])
            for oc in charges:
                amt = q2(getattr(oc, "amount", ZERO2))
                acct = getattr(oc, "account", None)
                if amt > ZERO2 and acct is not None:
                    line = self._jl(
                        account=acct,
                        accounthead=getattr(acct, "creditaccounthead", None),
                        cr=amt, desc=f"Other charge line #{d.id}", detailid=d.id
                    )
                    if line: jl.append(line)

            qty = getattr(d, "orderqty", None)
            qty = d.pieces if q4(qty) == ZERO4 else qty
            if qty and q4(qty) != ZERO4 and getattr(d, "product", None):
                unit_cost = self._issue_unit_cost(d)
                try:
                    mv = self._im(
                        product=d.product,
                        qty=-q4(qty),
                        unit_cost=unit_cost,
                        move_type="OUT",
                        detailid=d.id,
                    )
                except TypeError:
                    mv = self._im(product=d.product, qty=-q4(qty), move_type="OUT")

                self._assign_move_detail_and_links(mv, header, d)
                self._ensure_move_costs(mv, qty=-q4(qty), unit_cost=unit_cost)
                im.append(mv)

        # Subtotal alignment for tiny differences only (0 < |gap| <= 0.05)
        header_subtotal = q2(getattr(header, "subtotal", ZERO2) or ZERO2)
        gap = q2(header_subtotal - rev_total)
        if first_sale_acct is not None and ZERO2 < gap.copy_abs() <= Decimal("0.05"):
            if gap > ZERO2:
                line = self._jl(account=first_sale_acct,
                                accounthead=getattr(first_sale_acct, "creditaccounthead", None),
                                cr=gap, desc="Sales subtotal alignment")
            else:
                line = self._jl(account=first_sale_acct,
                                accounthead=getattr(first_sale_acct, "creditaccounthead", None),
                                dr=abs(gap), desc="Sales subtotal alignment (reverse)")
            if line: jl.append(line)

        # Taxes
        t = _derive_sales_taxes(header, details)
        igst, cgst, sgst, cess = t["igst"], t["cgst"], t["sgst"], t["cess"]
        if igst > ZERO2 and tax_out.get("igst"): jl.append(self._jl(account=tax_out["igst"], cr=q2(igst), desc="IGST"))
        if cgst > ZERO2 and tax_out.get("cgst"): jl.append(self._jl(account=tax_out["cgst"], cr=q2(cgst), desc="CGST"))
        if sgst > ZERO2 and tax_out.get("sgst"): jl.append(self._jl(account=tax_out["sgst"], cr=q2(sgst), desc="SGST"))
        if cess > ZERO2 and tax_out.get("cess"): jl.append(self._jl(account=tax_out["cess"], cr=q2(cess), desc="Cess"))

        # Header expense recovery -> Cr
        if expenses > ZERO2:
            exp_acct = get_expense_recovery_account(self.entity)
            jl.append(self._jl(account=exp_acct, cr=expenses, desc="Expense recovery"))

        # Round-off
        if roundoff != ZERO2:
            if roundoff > ZERO2:
                jl.append(self._jl(account=ro_expense, dr=roundoff, desc="Round-off (reduction)"))
            else:
                jl.append(self._jl(account=ro_income,  cr=q2(abs(roundoff)), desc="Round-off (increase)"))

        # Final gtotal
        final_total = apply_roundoff_to_total(gtotal_base, roundoff)
        header.gtotal = final_total

        # TCS liabilities
        if tcs_b > ZERO2: jl.append(self._jl(account=tcs_2,   cr=tcs_b, desc="TCS 206C(2)"))
        if tcs_a > ZERO2: jl.append(self._jl(account=tcs_1h2, cr=tcs_a, desc="TCS 206C(1H)(2)"))

        # Dr Customer/Cash
        ar_total = q2(final_total + tcs_a + tcs_b)
        if is_cash:
            cash_net = q2(ar_total - tds_amt) if tds_amt > ZERO2 else ar_total
            if cash_net > ZERO2:
                jl.append(self._jl(account=cash_acct, dr=cash_net,
                                   desc=f"Cash receipt Bill #{getattr(header, 'billno', None)}"))
        else:
            if ar_total > ZERO2:
                jl.append(self._jl(
                    account=header.accountid,
                    accounthead=getattr(header.accountid, "accounthead", None),
                    dr=ar_total, desc="Customer AR"
                ))

        # TDS
        if tds_amt > ZERO2:
            jl.append(self._jl(account=tds_recv, dr=tds_amt, desc="TDS 194Q receivable"))
            if not is_cash:
                jl.append(self._jl(
                    account=header.accountid, accounthead=getattr(header.accountid, "accounthead", None),
                    cr=tds_amt, desc="TDS 194Q setoff"
                ))
            const = stocktransconstant()
            tdsvbo    = const.gettdsvbono(self.entity)
            tdsreturn = const.gettdsreturnid()
            tdstype   = const.gettdstypeid()
            tdsmain.objects.create(
                voucherdate=self.entrydate,
                voucherno=tdsvbo,
                creditaccountid=header.accountid,
                debitaccountid=tds_recv,
                tdsaccountid=tds_recv,
                tdsreturnccountid=tdsreturn,
                tdstype=tdstype,
                debitamount=q2(getattr(header, "subtotal", ZERO2)),
                tdsrate=q2(getattr(header, "tds194q", ZERO2)),
                entityid=self.entity,
                transactiontype=self.txntype,
                transactionno=self.txnid,
                tdsvalue=tds_amt
            )

        # tiny residual guard
        dr_mem = q2(sum(l.amount for l in jl if l.drcr))
        cr_mem = q2(sum(l.amount for l in jl if not l.drcr))
        if dr_mem != cr_mem:
            missing = q2(dr_mem - cr_mem)
            if missing > ZERO2:
                is_inter = bool(getattr(header, "isigst", False))
                if is_inter and tax_out.get("igst"):
                    jl.append(self._jl(account=tax_out["igst"], cr=missing, desc="Auto-IGST (fallback)"))
                elif (not is_inter) and tax_out.get("cgst") and tax_out.get("sgst"):
                    half = q2(missing / Decimal("2"))
                    if half > ZERO2:
                        jl.append(self._jl(account=tax_out["cgst"], cr=half, desc="Auto-CGST (fallback)"))
                    rest = q2(missing - half)
                    if rest > ZERO2:
                        jl.append(self._jl(account=tax_out["sgst"], cr=rest, desc="Auto-SGST (fallback)"))
                else:
                    jl.append(self._jl(account=(first_sale_acct or header.accountid),
                                       cr=missing, desc="Auto-balance (fallback)"))
            else:
                amt = q2(abs(missing))
                if amt > ZERO2:
                    jl.append(self._jl(account=header.accountid, dr=amt, desc="Auto-debit (fallback)"))

        # final check
        dr_mem = q2(sum(l.amount for l in jl if l.drcr))
        cr_mem = q2(sum(l.amount for l in jl if not l.drcr))
        if dr_mem != cr_mem:
            detail = [("DR" if l.drcr else "CR",
                       getattr(getattr(l, "account", None), "accountname", str(getattr(l, "account", None))),
                       f"{l.amount:.2f}", l.desc) for l in jl]
            raise ValueError(f"Pre-save imbalance: DR {dr_mem:.2f} != CR {cr_mem:.2f}; lines={detail}")

        JournalLine.objects.bulk_create(jl)
        if im:
            InventoryMove.objects.bulk_create(im)
        self._assert_balanced()


    

    @transaction.atomic
    def post_sales_return(self, header, details, extra_charges_map: Optional[dict] = None):
        """
        Sales Return posting (SR) = reverse of Sales:
        - Dr Sales (reverse revenue)
        - Dr Output GST (reverse liability) ONLY if reversecharge=False
        ✅ UPDATE-PROOF: if header tax fields are 0, fallback to sum(detail taxes)
        - Dr other charges reversal (reverse of sales other-charge credits)
        - Cr Customer/Cash (credit note)
        - Inventory IN`
        """
        self.header = header
        self.clear_existing()

        jl: List[JournalLine] = []
        im: List[InventoryMove] = []

        # -----------------------------
        # 1) Ensure we have saved SR details
        # -----------------------------
        try:
            details = list(details or [])
            if (not details) or any(getattr(d, "pk", None) is None for d in details):
                raise ValueError("unsaved/empty")
        except Exception:
            details = list(
                getattr(header, "salereturndetails")
                .select_related("product", "product__sales_account", "product__purchase_account")
                .prefetch_related("otherchargesdetail")
                .all()
            )

        if not details:
            return

        cash_acct = get_cash_account(self.entity)
        tax_out   = get_tax_accounts(self.entity)  # {"igst":..,"cgst":..,"sgst":..,"cess":..}
        ro_income, ro_expense = get_roundoff_accounts(self.entity)

        # if other-charge line has no account, use misc expense
        misc_exp_acct = get_purchase_misc_expense_account(self.entity)

        gtotal_base = q2(getattr(header, "gtotal", ZERO2))
        roundoff    = q2(getattr(header, "roundOff", ZERO2))
        expenses    = q2(getattr(header, "expenses", ZERO2))
        is_cash     = (getattr(header, "billcash", None) in (0, 2))

        cust_acct = getattr(header, "account", None) or getattr(header, "accountid", None)

        first_sale_acct = None
        last_sale_acct  = None
        last_detail_id  = None

        # -----------------------------
        # 2) Reverse revenue + reverse other-charges + Stock IN
        # -----------------------------
        for d in details:
            prod = getattr(d, "product", None)

            line_amt      = q2(getattr(d, "amount", ZERO2))
            other_on_line  = q2(getattr(d, "othercharges", ZERO2))
            rev            = q2(line_amt - other_on_line)

            # Dr Sales (reverse revenue)
            if rev > ZERO2 and prod:
                sale_acct = get_sales_account_for_product(prod)
                if sale_acct is None:
                    raise ValueError(f"Sales account not set for product {getattr(prod,'id',None)}")

                if first_sale_acct is None:
                    first_sale_acct = sale_acct
                last_sale_acct = sale_acct
                last_detail_id = getattr(d, "id", None)

                jl.append(self._jl(
                    account=sale_acct,
                    accounthead=(
                    getattr(sale_acct, "debitaccounthead", None)
                    or getattr(sale_acct, "creditaccounthead", None)   # ✅ SR-safe fallback
                    or getattr(sale_acct, "accounthead", None)
                ),
                    dr=rev,
                    desc=f"Sales Return line #{getattr(d,'id',None)}",
                    detailid=getattr(d, "id", None)
                ))

            # Reverse Other charges (Sales credited these → SR debits them)
            charges = []
            rel = getattr(d, "otherchargesdetail", None)
            if rel is not None:
                try:
                    charges.extend(list(rel.all()))
                except Exception:
                    pass
            if extra_charges_map and getattr(d, "id", None) in extra_charges_map:
                charges.extend(extra_charges_map[d.id])

            for oc in charges:
                amt = q2(getattr(oc, "amount", ZERO2))
                if amt > ZERO2:
                    acct = getattr(oc, "account", None) or misc_exp_acct
                    jl.append(self._jl(
                        account=acct,
                        dr=amt,
                        desc=f"SR other charge line #{getattr(d,'id',None)}",
                        detailid=getattr(d, "id", None)
                    ))

            # Inventory IN
            qty = getattr(d, "orderqty", None)
            qty = getattr(d, "pieces", 0) if q4(qty) == ZERO4 else qty
            qty = q4(qty)

            if prod and qty != ZERO4:
                unit_cost = self._issue_unit_cost(d)
                mv = self._im(
                    product=prod,
                    qty=qty,                 # +ve for IN
                    unit_cost=unit_cost,
                    move_type="IN",
                    detailid=getattr(d, "id", None),
                )
                self._assign_move_detail_and_links(mv, header, d)
                self._ensure_move_costs(mv, qty=qty, unit_cost=unit_cost)
                im.append(mv)

        # -----------------------------
        # 3) Taxes reversal (Dr output GST) ONLY if reversecharge=False
        #    ✅ UPDATE-PROOF fallback to detail sums if header tax fields are 0
        # -----------------------------
        if not getattr(header, "reversecharge", False):
            igst = q2(getattr(header, "igst", ZERO2))
            cgst = q2(getattr(header, "cgst", ZERO2))
            sgst = q2(getattr(header, "sgst", ZERO2))
            cess = q2(getattr(header, "cess", ZERO2))

            if igst == ZERO2 and cgst == ZERO2 and sgst == ZERO2 and cess == ZERO2:
                sums = _sum_taxes_from_detail_objs(details)
                igst, cgst, sgst, cess = sums["igst"], sums["cgst"], sums["sgst"], sums["cess"]

            if igst > ZERO2 and tax_out.get("igst"):
                jl.append(self._jl(account=tax_out["igst"], dr=igst, desc="IGST (SR reversal)"))
            if cgst > ZERO2 and tax_out.get("cgst"):
                jl.append(self._jl(account=tax_out["cgst"], dr=cgst, desc="CGST (SR reversal)"))
            if sgst > ZERO2 and tax_out.get("sgst"):
                jl.append(self._jl(account=tax_out["sgst"], dr=sgst, desc="SGST (SR reversal)"))
            if cess > ZERO2 and tax_out.get("cess"):
                jl.append(self._jl(account=tax_out["cess"], dr=cess, desc="CESS (SR reversal)"))

        # Header expenses (if used)
        if expenses > ZERO2:
            jl.append(self._jl(account=misc_exp_acct, dr=expenses, desc="Expenses (SR header)"))

        # Roundoff
        if roundoff != ZERO2:
            if roundoff > ZERO2:
                jl.append(self._jl(account=ro_expense, dr=roundoff, desc="Round-off (SR)"))
            else:
                jl.append(self._jl(account=ro_income,  cr=abs(roundoff), desc="Round-off (SR)"))

        final_total = apply_roundoff_to_total(gtotal_base, roundoff)
        header.gtotal = final_total

        # -----------------------------
        # 4) Customer/Cash CREDIT (Credit Note)
        # -----------------------------
        dr_before = q2(sum(l.amount for l in jl if l and l.drcr))
        cr_before = q2(sum(l.amount for l in jl if l and not l.drcr))
        customer_credit = q2(dr_before - cr_before)

        if customer_credit <= ZERO2:
            raise ValueError("Sales Return computed credit is not positive (check amounts/taxes).")

        if is_cash:
            jl.append(self._jl(account=cash_acct, cr=customer_credit, desc="Cash refund (SR)"))
        else:
            if cust_acct is None:
                raise ValueError("Customer account not set on sales return header.")
            jl.append(self._jl(account=cust_acct, cr=customer_credit, desc="Customer credit note (SR)"))

        # -----------------------------
        # 5) Final balancing guard (tiny residual)
        # -----------------------------
        dr_mem = q2(sum(l.amount for l in jl if l and l.drcr))
        cr_mem = q2(sum(l.amount for l in jl if l and not l.drcr))
        if dr_mem != cr_mem:
            missing = q2(dr_mem - cr_mem)
            target_acct = last_sale_acct or first_sale_acct or misc_exp_acct
            if missing > ZERO2:
                jl.append(self._jl(account=target_acct, cr=missing, desc="SR adjustment", detailid=last_detail_id))
            else:
                jl.append(self._jl(account=(cash_acct if is_cash else cust_acct),
                                dr=abs(missing), desc="SR adjustment"))

        JournalLine.objects.bulk_create([l for l in jl if l is not None])
        if im:
            InventoryMove.objects.bulk_create(im)

        # SR should not create tdsmain; if any old rows exist, delete them
        tdsmain.objects.filter(entityid=self.entity, transactiontype=self.txntype, transactionno=self.txnid).delete()

        self._assert_balanced()


    # ======================================================
    # PURCHASE
    # ======================================================
    @transaction.atomic
    def post_purchase(
        self,
        hdr: Any,
        lines: List[Any],
        *,
        extra_charges_map: Optional[dict] = None
    ) -> None:
        self.clear_existing()

        jl: List[JournalLine] = []
        im: List[InventoryMove] = []

        first_purch_acct = None
        last_purch_acct  = None
        last_detail_id   = None

        cash_acct = get_cash_account(self.entity)
        in_tax    = get_input_tax_accounts(self.entity)
        ro_income, ro_expense = get_roundoff_accounts(self.entity)
        misc_exp_acct = get_purchase_misc_expense_account(self.entity)

        discount = q2(getattr(hdr, "discount", ZERO2))
        addless  = q2(getattr(hdr, "addless",  ZERO2))
        expenses = q2(getattr(hdr, "expenses", ZERO2))
        roundoff = q2(getattr(hdr, "roundOff", ZERO2))

        t = _derive_purchase_taxes(hdr, lines)
        igst, cgst, sgst, cess = t["igst"], t["cgst"], t["sgst"], t["cess"]

        for d in lines:
            line_amt = q2(getattr(d, "amount", ZERO2))
            prod     = getattr(d, "product", None)

            if line_amt > ZERO2 and prod:
                purch_acct = get_purchase_account_for_product(prod)
                if purch_acct:
                    if first_purch_acct is None:
                        first_purch_acct = purch_acct
                    last_purch_acct = purch_acct
                    last_detail_id  = getattr(d, 'id', None)

                    jl.append(self._jl(
                        account=purch_acct, dr=line_amt,
                        desc=f"Purchase line #{getattr(d, 'id', None)}",
                        detailid=getattr(d, 'id', None)
                    ))

            qty_raw = getattr(d, "orderqty", ZERO4)
            if q4(qty_raw) == ZERO4:
                qty_raw = getattr(d, "pieces", 0)
            qty = q4(qty_raw)

            if prod and qty != ZERO4:
                rate_val = getattr(d, "rate", None)
                if rate_val is None or q4(rate_val) == ZERO4:
                    amt = q2(getattr(d, "amount", ZERO2))
                    unit_cost = q4((amt / qty) if qty != ZERO4 else ZERO4)
                else:
                    unit_cost = q4(rate_val)

                im.append(self._im(
                    product=prod, qty=qty, unit_cost=unit_cost,
                    move_type="IN", detailid=getattr(d, 'id', None),
                ))

            charges = []
            rel = getattr(d, "otherchargesdetail", None)
            if rel is not None:
                try:
                    charges.extend(list(rel.all()))
                except Exception:
                    pass
            if extra_charges_map and getattr(d, "id", None) in extra_charges_map:
                charges.extend(extra_charges_map[getattr(d, "id")])

            for oc in charges:
                oc_amt = q2(getattr(oc, "amount", ZERO2))
                if oc_amt > ZERO2:
                    oc_acct = getattr(oc, "account", None) or misc_exp_acct
                    jl.append(self._jl(
                        account=oc_acct, dr=oc_amt,
                        desc=f"Other charge line #{getattr(d, 'id', None)}",
                        detailid=getattr(d, 'id', None)
                    ))

        if expenses > ZERO2:
            jl.append(self._jl(account=misc_exp_acct, dr=expenses, desc="Expenses (header)"))

        if discount > ZERO2:
            jl.append(self._jl(account=misc_exp_acct, cr=discount, desc="Purchase discount"))

        if addless != ZERO2:
            if addless > ZERO2:
                jl.append(self._jl(account=misc_exp_acct, dr=addless, desc="Add/Less (add)"))
            else:
                jl.append(self._jl(account=misc_exp_acct, cr=abs(addless), desc="Add/Less (less)"))

        if not getattr(hdr, "reversecharge", False):
            def pick(container, key):
                return container.get(key) if isinstance(container, dict) else getattr(container, key, None)

            igst_ac = pick(in_tax, "igst")
            cgst_ac = pick(in_tax, "cgst")
            sgst_ac = pick(in_tax, "sgst")
            cess_ac = pick(in_tax, "cess")

            if igst > ZERO2 and igst_ac is not None: jl.append(self._jl(account=igst_ac, dr=igst, desc="Input IGST"))
            if cgst > ZERO2 and cgst_ac is not None: jl.append(self._jl(account=cgst_ac, dr=cgst, desc="Input CGST"))
            if sgst > ZERO2 and sgst_ac is not None: jl.append(self._jl(account=sgst_ac, dr=sgst, desc="Input SGST"))
            if cess > ZERO2 and cess_ac is not None: jl.append(self._jl(account=cess_ac, dr=cess, desc="Input CESS"))

        if roundoff != ZERO2:
            if roundoff > ZERO2:
                jl.append(self._jl(account=ro_expense, dr=roundoff, desc="Round-off"))
            else:
                jl.append(self._jl(account=ro_income,  cr=abs(roundoff), desc="Round-off"))

        is_cash    = (getattr(hdr, "billcash", None) in (0, 2))
        payee_acct = cash_acct if is_cash else getattr(hdr, "account", None)
        if payee_acct is None:
            raise ValueError("Supplier/Cash account not set on purchase header.")

        dr_mem_before_supplier = sum(l.amount for l in jl if l.drcr)
        cr_mem_before_supplier = sum(l.amount for l in jl if not l.drcr)
        supplier_credit = q2(dr_mem_before_supplier - cr_mem_before_supplier)

        jl.append(self._jl(account=payee_acct, cr=supplier_credit,
                           desc=f"Supplier Bill {getattr(hdr, 'billno', None)}"))

        dr_mem = sum(l.amount for l in jl if l.drcr)
        cr_mem = sum(l.amount for l in jl if not l.drcr)
        missing = dr_mem - cr_mem
        if missing != ZERO2:
            target_acct   = last_purch_acct or first_purch_acct or misc_exp_acct
            target_detail = last_detail_id
            if missing < ZERO2:
                jl.append(self._jl(account=target_acct, dr=abs(missing),
                                   desc=f"Purchase line #{target_detail} (adjustment)",
                                   detailid=target_detail))
            else:
                jl.append(self._jl(account=payee_acct, cr=missing, desc="Supplier (adjustment)"))

        JournalLine.objects.bulk_create(jl)
        if im:
            InventoryMove.objects.bulk_create(im)
        self._assert_balanced()

    # ======================================================
    # JOURNAL
    # ======================================================
    def _resolve_bank_or_cash_acct_for_journal(self, header):
        """
        For Cash voucher: cash-in-hand account from stocktransconstant().
        For Bank voucher: header.mainaccountid (must be an account object or FK-resolved).
        For Journal: None (no automatic counter line).
        """
        from .stocktransconstant import stocktransconstant
        const = stocktransconstant()
        vt = getattr(header, "vouchertype", None)
        if vt in ("C", "Cash"):
            return const.getcashid(self.entity)
        if vt in ("B", "Bank"):
            # header.mainaccountid is usually a FK to account. If it's an id, fetch; if it's an object, return as-is.
            acct = getattr(header, "mainaccountid", None)
            if acct is None:
                return None
            # If it's an int, resolve to account object
            try:
                from invoice.models import account as AccountModel
                if isinstance(acct, int):
                    return AccountModel.objects.get(id=acct)
            except Exception:
                pass
            return acct
        return None  # Journal vouchers have no automatic CB counterpart

    def _fresh_journal_details(self, header, passed):
        """
        Ensure we have a complete, saved set of journaldetails for this header.
        """
        try:
            items = list(passed or [])
            if (not items) or any(getattr(d, "pk", None) is None for d in items):
                raise ValueError("unsaved/empty")
            return items
        except Exception:
            # Fallback: reload from DB
            return list(
                getattr(header, "journaldetails", None)
                .select_related("account")  # to avoid N+1 on account
                .all()
            )
        
    def _resolve_cb_account(entity, header):
        # For Cash → const cash; For Bank → header.mainaccountid; else None
        const = stocktransconstant()
        if header.vouchertype == VoucherType.CASH:
            return const.getcashid(entity)
        if header.vouchertype == VoucherType.BANK:
            return header.mainaccountid
        return None

    

    # ======================================================
    # JOURNAL VOUCHER (header + journaldetails)
    # ======================================================
    @transaction.atomic
    def post_journal_voucher(self, header, details=None):
        """
        CONFIGURABLE posting for Journal / Cash / Bank vouchers:
        • components ALWAYS posted (Discount, Bank Charges, TDS)
        • per-entity: pick which main line carries net (CB or Party)
        • per-entity: for each component choose offset target (CB, Party, or CARRIER to net)
        • presentation order: before / between / after
        """
        

        # 1) pick JournalLine.transactiontype label
        if header.vouchertype == VoucherType.CASH:
            self.txntype = TxnType.JOURNAL_CASH
        elif header.vouchertype == VoucherType.BANK:
            self.txntype = TxnType.JOURNAL_BANK
        else:
            self.txntype = TxnType.JOURNAL

        self.clear_existing()

        entity = header.entity
        cb_acct = self._resolve_bank_or_cash_acct_for_journal(header)
        cfg = EffectivePostingConfig(entity)

        # narration prefix
        narr = ("Cash V.No " if header.vouchertype == VoucherType.CASH
                else "Bank V.No " if header.vouchertype == VoucherType.BANK
                else "Journal V.No ")
        base_desc = f"{narr}{getattr(header, 'voucherno', '')}"

        # ensure we work with saved BASE rows
        base_rows = self._fresh_journal_details(header, details)

        const = stocktransconstant()
        jl = []

        for d in base_rows:
            debit  = q2(getattr(d, "debitamount", ZERO2))
            credit = q2(getattr(d, "creditamount", ZERO2))
            amt    = q2(debit + credit)
            if amt == ZERO2:
                continue

            desc = (d.desc or base_desc)
            party = getattr(d, "account", None)
            is_payment = bool(getattr(d, "drcr", False))  # Debit party => payment; Credit party => receipt

            # Pure Journal: just mirror as-is
            if header.vouchertype == VoucherType.JOURNAL or cb_acct is None:
                if is_payment:
                    jl.append(self._jl(account=party, dr=amt, desc=desc, detailid=getattr(d, "id", None)))
                else:
                    jl.append(self._jl(account=party, cr=amt, desc=desc, detailid=getattr(d, "id", None)))
                continue

            # Components (always posted)
            disc = q2(getattr(d, "discount", ZERO2))
            bc   = q2(getattr(d, "bankcharges", ZERO2))
            tds  = q2(getattr(d, "tds", ZERO2))

            disc_ac = cfg.discount_account(is_payment)
            bc_ac   = cfg.bank_charges_account()
            tds_recv= cfg.tds_receivable_account()
            tds_pay = cfg.tds_payable_account()

            carrier = cfg.carrier(is_payment)  # "CB" or "PARTY"
            order   = cfg.order(is_payment)
            targets = cfg.targets(is_payment)

            # Initialize gross bases
            if not is_payment:  # RECEIPT (party credit)
                cb_dr    = Decimal("0.00")
                party_cr = Decimal("0.00")
                if carrier == PostingConfig.CARRIER_CB:
                    cb_dr    = amt  # CB gross; will net if target=CARRIER
                else:
                    party_cr = amt  # Party gross; will net if target=CARRIER

                comp_lines = []

                def net_into_carrier(value):
                    nonlocal cb_dr, party_cr
                    if carrier == PostingConfig.CARRIER_CB:
                        cb_dr = q2(cb_dr - value)
                    else:
                        party_cr = q2(party_cr - value)

                def add_component(dr_account, amount, label, target_key):
                    if amount <= ZERO2:
                        return
                    comp_lines.append(self._jl(account=dr_account, dr=amount, desc=f"{desc} ({label})", detailid=getattr(d, "id", None)))
                    t = targets[target_key]
                    if t == PostingConfig.TARGET_CB:
                        comp_lines.append(self._jl(account=cb_acct, cr=amount, desc=f"{desc} ({label} offset)", detailid=getattr(d, "id", None)))
                    elif t == PostingConfig.TARGET_PARTY:
                        comp_lines.append(self._jl(account=party, cr=amount, desc=f"{desc} ({label} offset)", detailid=getattr(d, "id", None)))
                    else:  # net into carrier
                        net_into_carrier(amount)

                add_component(disc_ac, disc, "discount", "discount")
                add_component(bc_ac,   bc,   "bank charges", "bankcharges")
                add_component(tds_recv,tds,  "TDS receivable", "tds")

                # If carrier was PARTY, CB Dr still needs to appear (gross or net already computed)
                if carrier == PostingConfig.CARRIER_PARTY and cb_dr == ZERO2:
                    cb_dr = amt  # CB gross; net adjustments were taken from party_cr via net_into_carrier

                # Emit lines by order
                if order == PostingConfig.ORDER_BEFORE:
                    for ln in comp_lines: jl.append(ln)
                    if cb_dr  > ZERO2: jl.append(self._jl(account=cb_acct, dr=cb_dr, desc=desc, detailid=getattr(d, "id", None)))
                    pc = party_cr if party_cr > ZERO2 else (amt if carrier == PostingConfig.CARRIER_CB else party_cr)
                    jl.append(self._jl(account=party, cr=pc, desc=desc, detailid=getattr(d, "id", None)))

                elif order == PostingConfig.ORDER_AFTER:
                    if cb_dr  > ZERO2: jl.append(self._jl(account=cb_acct, dr=cb_dr, desc=desc, detailid=getattr(d, "id", None)))
                    pc = party_cr if party_cr > ZERO2 else (amt if carrier == PostingConfig.CARRIER_CB else party_cr)
                    jl.append(self._jl(account=party, cr=pc, desc=desc, detailid=getattr(d, "id", None)))
                    for ln in comp_lines: jl.append(ln)

                else:  # BETWEEN
                    if cb_dr  > ZERO2: jl.append(self._jl(account=cb_acct, dr=cb_dr, desc=desc, detailid=getattr(d, "id", None)))
                    for ln in comp_lines: jl.append(ln)
                    pc = party_cr if party_cr > ZERO2 else (amt if carrier == PostingConfig.CARRIER_CB else party_cr)
                    jl.append(self._jl(account=party, cr=pc, desc=desc, detailid=getattr(d, "id", None)))

            else:
                # PAYMENT (party debit)
                cb_cr    = Decimal("0.00")
                party_dr = Decimal("0.00")
                if carrier == PostingConfig.CARRIER_CB:
                    cb_cr    = amt
                else:
                    party_dr = amt

                comp_lines = []

                def net_into_carrier(value):
                    nonlocal cb_cr, party_dr
                    if carrier == PostingConfig.CARRIER_CB:
                        cb_cr = q2(cb_cr - value)  # components that reduce CB credit
                    else:
                        party_dr = q2(party_dr - value)

                def add_component_sign(cr_account, dr_account, amount, label, target_key):
                    if amount <= ZERO2:
                        return
                    # component posting lines
                    # discount: Cr discount; bank charges: Dr bank charges; tds: Cr tds payable
                    comp_lines.append(self._jl(
                        account=cr_account if cr_account else dr_account,
                        cr=amount if cr_account else None,
                        dr=amount if dr_account else None,
                        desc=f"{desc} ({label})",
                        detailid=getattr(d, "id", None),
                    ))
                    # offset
                    t = targets[target_key]
                    if t == PostingConfig.TARGET_CB:
                        comp_lines.append(self._jl(account=cb_acct,
                                                dr=amount if cr_account else None,
                                                cr=amount if dr_account else None,
                                                desc=f"{desc} ({label} offset)", detailid=getattr(d, "id", None)))
                    elif t == PostingConfig.TARGET_PARTY:
                        comp_lines.append(self._jl(account=party,
                                                dr=amount if cr_account else None,
                                                cr=amount if dr_account else None,
                                                desc=f"{desc} ({label} offset)", detailid=getattr(d, "id", None)))
                    else:
                        net_into_carrier(amount)

                # Discount (you receive) → Cr Discount
                add_component_sign(cr_account=cfg.discount_account(True), dr_account=None, amount=disc, label="discount", target_key="discount")
                # Bank charges → Dr Bank Charges
                add_component_sign(cr_account=None, dr_account=bc_ac, amount=bc, label="bank charges", target_key="bankcharges")
                # TDS payable → Cr TDS Payable
                add_component_sign(cr_account=tds_pay, dr_account=None, amount=tds, label="TDS payable", target_key="tds")

                if carrier == PostingConfig.CARRIER_PARTY and cb_cr == ZERO2:
                    cb_cr = amt

                if order == PostingConfig.ORDER_BEFORE:
                    for ln in comp_lines: jl.append(ln)
                    pd = party_dr if party_dr > ZERO2 else (amt if carrier == PostingConfig.CARRIER_CB else party_dr)
                    jl.append(self._jl(account=party, dr=pd, desc=desc, detailid=getattr(d, "id", None)))
                    if cb_cr > ZERO2: jl.append(self._jl(account=cb_acct, cr=cb_cr, desc=desc, detailid=getattr(d, "id", None)))

                elif order == PostingConfig.ORDER_AFTER:
                    pd = party_dr if party_dr > ZERO2 else (amt if carrier == PostingConfig.CARRIER_CB else party_dr)
                    jl.append(self._jl(account=party, dr=pd, desc=desc, detailid=getattr(d, "id", None)))
                    if cb_cr > ZERO2: jl.append(self._jl(account=cb_acct, cr=cb_cr, desc=desc, detailid=getattr(d, "id", None)))
                    for ln in comp_lines: jl.append(ln)

                else:  # BETWEEN
                    pd = party_dr if party_dr > ZERO2 else (amt if carrier == PostingConfig.CARRIER_CB else party_dr)
                    jl.append(self._jl(account=party, dr=pd, desc=desc, detailid=getattr(d, "id", None)))
                    for ln in comp_lines: jl.append(ln)
                    if cb_cr > ZERO2: jl.append(self._jl(account=cb_acct, cr=cb_cr, desc=desc, detailid=getattr(d, "id", None)))

        # Balance guard (in-memory)
        dr_mem = q2(sum(l.amount for l in jl if l and l.drcr))
        cr_mem = q2(sum(l.amount for l in jl if l and not l.drcr))
        if dr_mem != cr_mem:
            detail_dump = [("DR" if l.drcr else "CR",
                            getattr(getattr(l, "account", None), "accountname", str(getattr(l, "account", None))),
                            f"{l.amount:.2f}", l.desc) for l in jl if l]
            raise ValueError(f"Pre-save imbalance: DR {dr_mem:.2f} != CR {cr_mem:.2f}; lines={detail_dump}")

        JournalLine.objects.bulk_create([l for l in jl if l is not None])
        self._assert_balanced()


    @transaction.atomic
    def post_journal(self, lines: List[dict]):
        self.clear_existing()
        jl = []
        for ln in lines:
            acc = ln["account"]
            if "dr" in ln:
                jl.append(self._jl(account=acc, dr=q2(ln["dr"]), desc=ln.get("desc")))
            else:
                jl.append(self._jl(account=acc, cr=q2(ln["cr"]), desc=ln.get("desc")))

        dr_mem = sum(l.amount for l in jl if l.drcr)
        cr_mem = sum(l.amount for l in jl if not l.drcr)
        if dr_mem != cr_mem:
            detail = [("DR" if l.drcr else "CR",
                       getattr(getattr(l, "account", None), "accountname", str(getattr(l, "account", None))),
                       f"{l.amount:.2f}", l.desc) for l in jl]
            raise ValueError(f"Pre-save imbalance: DR {dr_mem:.2f} != CR {cr_mem:.2f}; lines={detail}")

        JournalLine.objects.bulk_create(jl)
        self._assert_balanced()

    # ---------- final balance check ----------
    def _assert_balanced(self):
        sums = (JournalLine.objects
                .filter(entity=self.entity, transactiontype=self.txntype, transactionid=self.txnid)
                .aggregate(
                    dr=Sum('amount', filter=models.Q(drcr=True)),
                    cr=Sum('amount', filter=models.Q(drcr=False))
                ))
        dr = sums['dr'] or ZERO2
        cr = sums['cr'] or ZERO2
        if dr != cr:
            raise ValueError(f"Unbalanced entry: Dr {dr} != Cr {cr}")


