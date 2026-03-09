from decimal import Decimal
from django.core.exceptions import ValidationError


from invoice.models import JournalLine, StockTransactions, entry  # adjust import
from financial.models import FinancialSettings, staticacountsmapping  # adjust import

OPENING_TXN_TYPE = "OA"          # keep consistent everywhere
OPENING_STATIC_CODE = "8600"  # create staticacounts.code with this value

OPENING_EDIT_ALWAYS = "always"
OPENING_EDIT_BEFORE_POSTING = "before_posting"
OPENING_EDIT_LOCKED = "locked"


def get_opening_balance_edit_mode(entity_id: int) -> str:
    settings_obj = (
        FinancialSettings.objects.filter(entity_id=entity_id)
        .only("opening_balance_edit_mode")
        .first()
    )
    if not settings_obj:
        return OPENING_EDIT_BEFORE_POSTING
    return settings_obj.opening_balance_edit_mode or OPENING_EDIT_BEFORE_POSTING


def has_non_opening_activity(acc) -> bool:
    has_journal_activity = JournalLine.objects.filter(
        entity_id=acc.entity_id,
        account_id=acc.id,
    ).exclude(transactiontype=OPENING_TXN_TYPE).exists()

    if has_journal_activity:
        return True

    return StockTransactions.objects.filter(
        entity_id=acc.entity_id,
        account_id=acc.id,
    ).exclude(transactiontype=OPENING_TXN_TYPE).exists()


def validate_opening_balance_edit(acc, old_opening_dr, old_opening_cr, new_opening_dr, new_opening_cr):
    old_dr = Decimal(old_opening_dr or 0)
    old_cr = Decimal(old_opening_cr or 0)
    new_dr = Decimal(new_opening_dr or 0)
    new_cr = Decimal(new_opening_cr or 0)

    if old_dr == new_dr and old_cr == new_cr:
        return

    mode = get_opening_balance_edit_mode(acc.entity_id)

    if mode == OPENING_EDIT_ALWAYS:
        return

    if mode == OPENING_EDIT_LOCKED:
        raise ValidationError("Opening balance is locked by financial settings for this entity.")

    if mode == OPENING_EDIT_BEFORE_POSTING and has_non_opening_activity(acc):
        raise ValidationError(
            "Opening balance cannot be changed after posting activity has started for this account."
        )


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
