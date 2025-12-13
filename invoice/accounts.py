# ledger/accounts.py
from .stocktransconstant import stocktransconstant  # adjust import path to where you define this

def get_sales_account_for_product(product):
    return product.sales_account

def get_purchase_account_for_product(product):
    return product.purchase_account

def get_cash_account(entity):
    const = stocktransconstant()
    return const.getcashid(entity)

def get_roundoff_accounts(entity):
    const = stocktransconstant()
    return const.getroundoffincome(entity), const.getroundoffexpnses(entity)

def get_tax_accounts(entity):
    const = stocktransconstant()
    return {
        "igst": const.getigst(entity),
        "cgst": const.getcgst(entity),
        "sgst": const.getsgst(entity),
        "cess": const.getcessid(entity),
    }

def get_input_tax_accounts(entity):
    const = stocktransconstant()
    # if you have dedicated input tax getters, prefer them; fallback to output ledgers
    igst = getattr(const, "get_input_igst", None)
    cgst = getattr(const, "get_input_cgst", None)
    sgst = getattr(const, "get_input_sgst", None)
    cess = getattr(const, "get_input_cess", None)
    return {
        "igst": igst(entity) if igst else const.getigst(entity),
        "cgst": cgst(entity) if cgst else const.getcgst(entity),
        "sgst": sgst(entity) if sgst else const.getsgst(entity),
        "cess": cess(entity) if cess else const.getcessid(entity),
    }

def get_tcs_accounts(entity):
    const = stocktransconstant()
    return const.gettcs206c1ch2id(entity), const.gettcs206C2id(entity)  # (1H(2), 206C(2))

def get_tcs_receivable_accounts(entity):
    const = stocktransconstant()
    rec_1h2 = getattr(const, "gettcs206c1ch2_receivable", None)
    rec_c2  = getattr(const, "gettcs206C2_receivable", None)
    # fallback to the same id if receivable ledgers aren't separated yet
    return (
        rec_1h2(entity) if rec_1h2 else const.gettcs206c1ch2id(entity),
        rec_c2(entity)  if rec_c2  else const.gettcs206C2id(entity),
    )

def get_tds_accounts(entity):
    const = stocktransconstant()
    tds_recv = const.gettds194q1id(entity)  # receivable (sales)
    tds_pay_getter = getattr(const, "gettds194q1_payable", None)
    tds_pay = tds_pay_getter(entity) if tds_pay_getter else tds_recv
    return tds_recv, tds_pay

def get_expense_recovery_account(entity):
    const = stocktransconstant()
    return const.getexpensesid(entity)

def get_purchase_misc_expense_account(entity):
    const = stocktransconstant()
    getter = getattr(const, "get_purchase_misc_expense_id", None)
    return getter(entity) if getter else const.getexpensesid(entity)
