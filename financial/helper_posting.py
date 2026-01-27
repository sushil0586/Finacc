from decimal import Decimal
from django.core.exceptions import ValidationError


from invoice.models import JournalLine,entry  # adjust import
from financial.models import staticacountsmapping  # adjust import

OPENING_TXN_TYPE = "OA"          # keep consistent everywhere
OPENING_STATIC_CODE = "8600"  # create staticacounts.code with this value


def get_opening_offset_accounthead_id(entity_id: int) -> int:
    """
    Uses static mapping:
      staticacounts.code = 'OPENING_OFFSET'  --> mapped account --> account.accounthead_id
    """
    m = (
        staticacountsmapping.objects
        .select_related("account", "staticaccount")
        .filter(entity_id=entity_id, staticaccount__code=OPENING_STATIC_CODE)
        .first()
    )
    if not m or not m.account_id or not m.account.accounthead_id:
        raise ValidationError(
            f"Opening offset is not configured. Map static account code '{OPENING_STATIC_CODE}' "
            f"to an Account that has accounthead."
        )
    return m.account.accounthead_id


def delete_opening_journal_lines(acc):
    """
    Delete existing opening posting for this account.
    (We delete ONLY lines where account = this account. Offset lines remain and will be recreated.)
    """
    JournalLine.objects.filter(
        entity_id=acc.entity_id,
        transactiontype=OPENING_TXN_TYPE,
        transactionid=acc.id,
        account_id=acc.id,
    ).delete()

    # Also delete offset lines for same txn locator (account is NULL)
    JournalLine.objects.filter(
        entity_id=acc.entity_id,
        transactiontype=OPENING_TXN_TYPE,
        transactionid=acc.id,
        account__isnull=True,
    ).delete()


def post_opening_balance_journal_lines(acc, entry_obj, entry_date):
    """
    Creates TWO JournalLine rows (balanced):
      1) Party line -> account=acc, accounthead=acc.accounthead, drcr True/False
      2) Offset line -> account=NULL, accounthead=OPENING_OFFSET head, opposite drcr
    """
    opening_dr = Decimal(acc.openingbdr or 0)
    opening_cr = Decimal(acc.openingbcr or 0)

    if opening_dr <= 0 and opening_cr <= 0:
        return

    if opening_dr > 0 and opening_cr > 0:
        raise ValidationError("Only one of openingbdr/openingbcr should be set.")

    offset_head_id = get_opening_offset_accounthead_id(acc.entity_id)

    if opening_dr > 0:
        amt = opening_dr
        party_drcr = True     # Debit
        offset_drcr = False   # Credit
        desc = "Opening Balance (Dr)"
    else:
        amt = opening_cr
        party_drcr = False    # Credit
        offset_drcr = True    # Debit
        desc = "Opening Balance (Cr)"

    vno = str(acc.accountcode) if acc.accountcode is not None else None

    # 1) Party line
    JournalLine.objects.create(
        entry=entry_obj,
        entity_id=acc.entity_id,
        transactiontype=OPENING_TXN_TYPE,
        transactionid=acc.id,
        detailid=None,
        voucherno=vno,
        accounthead_id=acc.accounthead_id,
        account_id=acc.id,
        drcr=party_drcr,
        amount=amt,
        desc=desc,
        entrydate=entry_date,
        entrydatetime=None,
        createdby_id=acc.createdby_id,
    )

    # 2) Offset line
    JournalLine.objects.create(
        entry=entry_obj,
        entity_id=acc.entity_id,
        transactiontype=OPENING_TXN_TYPE,
        transactionid=acc.id,
        detailid=None,
        voucherno=vno,
        accounthead_id=offset_head_id,
        account=None,
        drcr=offset_drcr,
        amount=amt,
        desc=f"{desc} - Offset",
        entrydate=entry_date,
        entrydatetime=None,
        createdby_id=acc.createdby_id,
    )


def repost_opening_balance(acc, fin_start_date):
    """
    One call to:
      - delete old OA lines
      - ensure entry exists
      - post OA lines again
    """
    delete_opening_journal_lines(acc)

    if not fin_start_date:
        return

    entry_obj, _ = entry.objects.get_or_create(entrydate1=fin_start_date, entity_id=acc.entity_id)
    post_opening_balance_journal_lines(acc, entry_obj, fin_start_date)