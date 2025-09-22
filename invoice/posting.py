# ledger/posting.py
from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction, models
from django.db.models import Sum
from django.utils.timezone import now

# --- your app imports (adjust paths if needed) ---
from invoice.models import (
    JournalLine, InventoryMove, TxnType,
    salesOrderdetails, entry as EntryModel, tdsmain
)
from .stocktransconstant import stocktransconstant

from .accounts import (
    get_sales_account_for_product, get_purchase_account_for_product,
    get_tax_accounts, get_input_tax_accounts,
    get_roundoff_accounts, get_cash_account,
    get_tcs_accounts, get_tcs_receivable_accounts,
    get_tds_accounts, get_expense_recovery_account,
    get_purchase_misc_expense_account
)

# ---------- rounding helpers ----------
TWOPL = Decimal("0.01")
ZERO2 = Decimal("0.00")
ZERO4 = Decimal("0.0000")

def q2(x):
    if isinstance(x, Decimal):
        return x.quantize(TWOPL, rounding=ROUND_HALF_UP)
    return Decimal(str(x or "0")).quantize(TWOPL, rounding=ROUND_HALF_UP)

def q4(x):
    if isinstance(x, Decimal):
        return x.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return Decimal(str(x or "0")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

def apply_roundoff_to_total(gtotal, roundoff):
    """
    gtotal: base (pre-round) total
    roundoff > 0  => subtract from final total
    roundoff < 0  => add absolute(roundoff) to final total
    """
    if roundoff > ZERO2:
        return q2(gtotal - roundoff)
    elif roundoff < ZERO2:
        return q2(gtotal + abs(roundoff))
    return q2(gtotal)


class Poster:
    """
    Two-ledger poster (GL + Inventory).
    Handles Sales / Sales Return / Purchase / Purchase Return / Journal.
    - Cash detection: billcash in (0, 2) = Cash
    - Per-line otherchargesdetail handling
    - TCS/TDS handling incl. tdsmain
    - Subtotal alignment to handle late/unsaved detail rows
    """

    def __init__(self, entry, entity, user, transactiontype, transactionid, voucherno, entrydate, entrydt):
        self.entry = entry
        self.entity = entity
        self.user = user
        self.txntype = transactiontype
        self.txnid = transactionid
        self.voucherno = str(voucherno) if voucherno is not None else None
        self.entrydate = entrydate
        self.entrydt = entrydt or now()

    # ---------- builders ----------
    def _jl(self, *, account, accounthead=None, dr=None, cr=None, desc=None, detailid=None):
        assert (dr is None) ^ (cr is None), "Provide exactly one of dr or cr"
        amount = q2(dr if dr is not None else cr)
        return JournalLine(
            entry=self.entry, entity=self.entity,
            transactiontype=self.txntype, transactionid=self.txnid, detailid=detailid,
            voucherno=self.voucherno, account=account, accounthead=accounthead,
            drcr=(dr is not None), amount=amount, desc=desc,
            entrydate=self.entrydate, entrydatetime=self.entrydt, createdby=self.user
        )

    def _im(self, *, product, qty, unit_cost=ZERO4, move_type="OUT", detailid=None, location=None, uom=None):
        qty = q4(qty)
        return InventoryMove(
            entry=self.entry, entity=self.entity,
            transactiontype=self.txntype, transactionid=self.txnid, detailid=detailid,
            voucherno=self.voucherno, product=product, location=location, uom=uom,
            qty=qty, unit_cost=q4(unit_cost), ext_cost=q2(abs(qty) * q4(unit_cost)),
            move_type=move_type, entrydate=self.entrydate, entrydatetime=self.entrydt, createdby=self.user
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
                .select_related("product", "product__saleaccount", "product__purchaseaccount")
                .prefetch_related("otherchargesdetail")
            )

    # ---------- cleanup ----------
    @transaction.atomic
    def clear_existing(self):
        JournalLine.objects.filter(entity=self.entity, transactiontype=self.txntype, transactionid=self.txnid).delete()
        InventoryMove.objects.filter(entity=self.entity, transactiontype=self.txntype, transactionid=self.txnid).delete()
        tdsmain.objects.filter(entityid=self.entity, transactiontype=self.txntype, transactionno=self.txnid).delete()

    # ======================================================
    # SALES
    # ======================================================
    @transaction.atomic
    def post_sales(self, header, details, extra_charges_map=None):
        self.clear_existing()
        jl, im = [], []

        # Use a fresh, complete set of saved details
        details = self._fresh_details(header, details)

        cash_acct = get_cash_account(self.entity)
        tax_out = get_tax_accounts(self.entity)
        ro_income, ro_expense = get_roundoff_accounts(self.entity)
        tcs_1h2, tcs_2 = get_tcs_accounts(self.entity)           # liabilities
        tds_recv, _tds_pay = get_tds_accounts(self.entity)       # receivable

        gtotal_base = q2(header.gtotal)
        roundoff    = q2(header.roundOff)
        cgst = q2(header.cgst); sgst = q2(header.sgst); igst = q2(header.igst); cess = q2(header.cess)
        expenses = q2(header.expenses)
        tcs_a = q2(header.tcs206c1ch2); tcs_b = q2(header.tcs206C2)
        tds_amt = q2(header.tds194q1)
        is_cash = (getattr(header, "billcash", None) in (0, 2))

        # Per-line revenue / othercharges / inventory OUT
        first_sale_acct = None
        rev_total = ZERO2

        for d in details:
            rev = q2(d.amount) - q2(getattr(d, "othercharges", ZERO2))
            if rev > ZERO2 and d.product:
                sale_acct = get_sales_account_for_product(d.product)
                if first_sale_acct is None:
                    first_sale_acct = sale_acct
                jl.append(self._jl(account=sale_acct,
                                   accounthead=getattr(sale_acct, "creditaccounthead", None),
                                   cr=rev, desc=f"Sales line #{d.id}", detailid=d.id))
                rev_total += rev

            # per-line other charges -> Cr
            charges = []
            rel = getattr(d, "otherchargesdetail", None)
            if rel is not None:
                try:
                    charges.extend(list(rel.all()))
                except Exception:
                    pass
            if extra_charges_map and d.id in extra_charges_map:
                charges.extend(extra_charges_map[d.id])
            for oc in charges:
                amt = q2(getattr(oc, "amount", ZERO2))
                acct = getattr(oc, "account", None)
                if amt > ZERO2 and acct is not None:
                    jl.append(self._jl(
                        account=acct,
                        accounthead=getattr(acct, "creditaccounthead", None),
                        cr=amt, desc=f"Other charge line #{d.id}", detailid=d.id
                    ))

            # inventory OUT
            qty = d.pieces if q4(d.orderqty) == ZERO4 else d.orderqty
            if qty and q4(qty) != ZERO4 and d.product:
                im.append(self._im(product=d.product, qty=-q4(qty), unit_cost=ZERO4,
                                   move_type="OUT", detailid=d.id))

        # 🔧 Align credited revenue with header.subtotal (handles late rows)
        expected_subtotal = q2(getattr(header, "subtotal", ZERO2) or ZERO2)
        gap = expected_subtotal - rev_total
        if gap != ZERO2 and first_sale_acct is not None:
            if gap > ZERO2:
                jl.append(self._jl(account=first_sale_acct,
                                   accounthead=getattr(first_sale_acct, "creditaccounthead", None),
                                   cr=gap, desc="Sales subtotal alignment"))
            else:
                jl.append(self._jl(account=first_sale_acct,
                                   accounthead=getattr(first_sale_acct, "creditaccounthead", None),
                                   dr=abs(gap), desc="Sales subtotal alignment (reverse)"))

        # Header taxes -> Cr
        if igst > ZERO2: jl.append(self._jl(account=tax_out["igst"], cr=igst, desc="IGST"))
        if cgst > ZERO2: jl.append(self._jl(account=tax_out["cgst"], cr=cgst, desc="CGST"))
        if sgst > ZERO2: jl.append(self._jl(account=tax_out["sgst"], cr=sgst, desc="SGST"))
        if cess > ZERO2: jl.append(self._jl(account=tax_out["cess"], cr=cess, desc="Cess"))

        # Header expense recovery -> Cr
        if expenses > ZERO2:
            exp_acct = get_expense_recovery_account(self.entity)
            jl.append(self._jl(account=exp_acct, cr=expenses, desc="Expense recovery"))

        # Round-off (post ONCE, mapped to expense/income)
        if roundoff != ZERO2:
            if roundoff > ZERO2:
                jl.append(self._jl(account=ro_expense, dr=roundoff, desc="Round-off (reduction)"))
            else:
                jl.append(self._jl(account=ro_income,  cr=abs(roundoff), desc="Round-off (increase)"))

        # Final total after applying round-off to base gtotal
        final_total = apply_roundoff_to_total(gtotal_base, roundoff)
        header.gtotal = final_total  # reflect what we post

        # TCS liabilities -> Cr
        if tcs_b > ZERO2: jl.append(self._jl(account=tcs_2,   cr=tcs_b, desc="TCS 206C(2)"))
        if tcs_a > ZERO2: jl.append(self._jl(account=tcs_1h2, cr=tcs_a, desc="TCS 206C(1H)(2)"))

        # Dr Customer/Cash = final_total + TCS
        ar_total = final_total + tcs_a + tcs_b
        if is_cash:
            cash_net = ar_total - tds_amt if tds_amt > ZERO2 else ar_total
            if cash_net > ZERO2:
                jl.append(self._jl(account=cash_acct, dr=cash_net, desc=f"Cash receipt Bill #{header.billno}"))
        else:
            if ar_total > ZERO2:
                jl.append(self._jl(account=header.accountid, accounthead=header.accountid.accounthead,
                                   dr=ar_total, desc="Customer AR"))

        # TDS receivable (sales) + tdsmain
        if tds_amt > ZERO2:
            jl.append(self._jl(account=tds_recv, dr=tds_amt, desc="TDS 194Q receivable"))
            if not is_cash:
                jl.append(self._jl(account=header.accountid, accounthead=header.accountid.accounthead,
                                   cr=tds_amt, desc="TDS 194Q setoff"))
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
                debitamount=q2(header.subtotal),
                tdsrate=q2(header.tds194q),
                entityid=self.entity,
                transactiontype=self.txntype,
                transactionno=self.txnid,
                tdsvalue=tds_amt
            )

        JournalLine.objects.bulk_create(jl)
        InventoryMove.objects.bulk_create(im)
        self._assert_balanced()

    @transaction.atomic
    def post_sales_return(self, header, details):
        # Reverse sales; no tdsmain kept for returns
        self.clear_existing()
        self.post_sales(header, details)
        JournalLine.objects.filter(entity=self.entity, transactiontype=self.txntype, transactionid=self.txnid)\
            .update(drcr=~models.F('drcr'))
        InventoryMove.objects.filter(entity=self.entity, transactiontype=self.txntype, transactionid=self.txnid)\
            .update(qty=-models.F('qty'))
        tdsmain.objects.filter(entityid=self.entity, transactiontype=self.txntype, transactionno=self.txnid).delete()
        self._assert_balanced()

    # ======================================================
    # PURCHASE
    # ======================================================
    @transaction.atomic
    def post_purchase(self, header, details, extra_charges_map=None):
        self.clear_existing()
        jl, im = [], []

        details = self._fresh_details(header, details)

        cash_acct = get_cash_account(self.entity)
        tax_in = get_input_tax_accounts(self.entity)
        ro_income, ro_expense = get_roundoff_accounts(self.entity)
        tcs_rec_1h2, tcs_rec_2 = get_tcs_receivable_accounts(self.entity)  # assets
        _tds_recv, tds_pay = get_tds_accounts(self.entity)                  # liability
        misc_exp = get_purchase_misc_expense_account(self.entity)

        gtotal_base = q2(header.gtotal)
        roundoff    = q2(header.roundOff)
        cgst = q2(header.cgst); sgst = q2(header.sgst); igst = q2(header.igst); cess = q2(header.cess)
        expenses = q2(header.expenses)
        tcs_a = q2(header.tcs206c1ch2); tcs_b = q2(header.tcs206C2)
        tds_amt = q2(header.tds194q1)
        is_cash = (getattr(header, "billcash", None) in (0, 2))

        # Per-line cost / othercharges / inventory IN
        first_pur_acct = None
        cost_total = ZERO2

        for d in details:
            cost = q2(d.amount) - q2(getattr(d, "othercharges", ZERO2))
            if cost > ZERO2 and d.product:
                pur_acct = get_purchase_account_for_product(d.product)
                if first_pur_acct is None:
                    first_pur_acct = pur_acct
                jl.append(self._jl(account=pur_acct,
                                   accounthead=getattr(pur_acct, "accounthead", None),
                                   dr=cost, desc=f"Purchase line #{d.id}", detailid=d.id))
                cost_total += cost

            # per-line other charges -> Dr
            charges = []
            rel = getattr(d, "otherchargesdetail", None)
            if rel is not None:
                try:
                    charges.extend(list(rel.all()))
                except Exception:
                    pass
            if extra_charges_map and d.id in extra_charges_map:
                charges.extend(extra_charges_map[d.id])
            for oc in charges:
                amt = q2(getattr(oc, "amount", ZERO2))
                acct = getattr(oc, "account", None)
                if amt > ZERO2 and acct is not None:
                    jl.append(self._jl(
                        account=acct,
                        accounthead=getattr(acct, "accounthead", None),
                        dr=amt, desc=f"Other charge line #{d.id}", detailid=d.id
                    ))

            # inventory IN
            qty = d.pieces if q4(d.orderqty) == ZERO4 else d.orderqty
            if qty and q4(qty) != ZERO4 and d.product:
                ucost = (q4(cost) / q4(qty)) if (cost > ZERO2 and q4(qty) != ZERO4) else ZERO4
                im.append(self._im(product=d.product, qty=+q4(qty), unit_cost=ucost,
                                   move_type="IN", detailid=d.id))

        # 🔧 Align debited cost with header.subtotal
        expected_subtotal = q2(getattr(header, "subtotal", ZERO2) or ZERO2)
        gap = expected_subtotal - cost_total
        if gap != ZERO2 and first_pur_acct is not None:
            if gap > ZERO2:
                jl.append(self._jl(account=first_pur_acct,
                                   accounthead=getattr(first_pur_acct, "accounthead", None),
                                   dr=gap, desc="Purchase subtotal alignment"))
            else:
                jl.append(self._jl(account=first_pur_acct,
                                   accounthead=getattr(first_pur_acct, "accounthead", None),
                                   cr=abs(gap), desc="Purchase subtotal alignment (reverse)"))

        # Input taxes -> Dr
        if igst > ZERO2: jl.append(self._jl(account=tax_in["igst"], dr=igst, desc="IGST In"))
        if cgst > ZERO2: jl.append(self._jl(account=tax_in["cgst"], dr=cgst, desc="CGST In"))
        if sgst > ZERO2: jl.append(self._jl(account=tax_in["sgst"], dr=sgst, desc="SGST In"))
        if cess > ZERO2: jl.append(self._jl(account=tax_in["cess"], dr=cess, desc="Cess In"))

        # Header expenses -> Dr
        if expenses > ZERO2:
            jl.append(self._jl(account=misc_exp, dr=expenses, desc="Purchase expenses"))

        # Round-off once
        if roundoff != ZERO2:
            if roundoff > ZERO2:
                jl.append(self._jl(account=ro_expense, dr=roundoff, desc="Round-off (reduction)"))
            else:
                jl.append(self._jl(account=ro_income,  cr=abs(roundoff), desc="Round-off (increase)"))

        # Final total after applying round-off to base gtotal
        final_total = apply_roundoff_to_total(gtotal_base, roundoff)
        header.gtotal = final_total

        # TCS receivables -> Dr
        if tcs_b > ZERO2: jl.append(self._jl(account=tcs_rec_2,   dr=tcs_b, desc="TCS 206C(2) receivable"))
        if tcs_a > ZERO2: jl.append(self._jl(account=tcs_rec_1h2, dr=tcs_a, desc="TCS 206C(1H)(2) receivable"))

        # AP / Cash -> Cr
        ap_total = final_total + tcs_a + tcs_b
        net_payable = ap_total - tds_amt if tds_amt > ZERO2 else ap_total
        if is_cash:
            if net_payable > ZERO2:
                jl.append(self._jl(account=cash_acct, cr=net_payable, desc=f"Cash payment Bill #{header.billno}"))
        else:
            if net_payable > ZERO2:
                jl.append(self._jl(account=header.accountid, accounthead=header.accountid.accounthead,
                                   cr=net_payable, desc="Supplier AP"))

        # TDS payable -> Cr (+ tdsmain)
        if tds_amt > ZERO2:
            jl.append(self._jl(account=tds_pay, cr=tds_amt, desc="TDS 194Q payable"))
            const = stocktransconstant()
            tdsvbo    = getattr(const, "gettdsvbono", lambda e: None)(self.entity)
            tdsreturn = const.gettdsreturnid()
            tdstype   = const.gettdstypeid()
            tdsmain.objects.create(
                voucherdate=self.entrydate,
                voucherno=tdsvbo,
                creditaccountid=tds_pay,
                debitaccountid=header.accountid,
                tdsaccountid=tds_pay,
                tdsreturnccountid=tdsreturn,
                tdstype=tdstype,
                debitamount=q2(header.subtotal),
                tdsrate=q2(header.tds194q),
                entityid=self.entity,
                transactiontype=self.txntype,
                transactionno=self.txnid,
                tdsvalue=tds_amt
            )

        JournalLine.objects.bulk_create(jl)
        InventoryMove.objects.bulk_create(im)
        self._assert_balanced()

    @transaction.atomic
    def post_purchase_return(self, header, details):
        self.clear_existing()
        self.post_purchase(header, details)
        JournalLine.objects.filter(entity=self.entity, transactiontype=self.txntype, transactionid=self.txnid)\
            .update(drcr=~models.F('drcr'))
        InventoryMove.objects.filter(entity=self.entity, transactiontype=self.txntype, transactionid=self.txnid)\
            .update(qty=-models.F('qty'))
        tdsmain.objects.filter(entityid=self.entity, transactiontype=self.txntype, transactionno=self.txnid).delete()
        self._assert_balanced()

    # ======================================================
    # JOURNAL
    # ======================================================
    @transaction.atomic
    def post_journal(self, lines):
        """
        lines = [{account, dr} or {account, cr}, desc?]
        """
        self.clear_existing()
        jl = []
        for ln in lines:
            acc = ln["account"]
            if "dr" in ln:
                jl.append(self._jl(account=acc, dr=q2(ln["dr"]), desc=ln.get("desc")))
            else:
                jl.append(self._jl(account=acc, cr=q2(ln["cr"]), desc=ln.get("desc")))
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
