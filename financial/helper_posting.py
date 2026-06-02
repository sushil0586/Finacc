from decimal import Decimal
from django.core.exceptions import ValidationError

from posting.models import JournalLine
from posting.models import TxnType
from financial.models import FinancialSettings

OPENING_TXN_TYPE = TxnType.OPENING_BALANCE

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
    ).exclude(txn_type=OPENING_TXN_TYPE).exists()

    return has_journal_activity


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


def delete_opening_journal_lines(acc):
    from financial.services_opening_balance import clear_account_opening_posting

    return clear_account_opening_posting(acc)


def post_opening_balance_journal_lines(acc, entry_obj, entry_date):
    from financial.services_opening_balance import sync_account_opening_posting

    actor = None
    if entry_obj is not None:
        actor = getattr(entry_obj, "posted_by", None) or getattr(entry_obj, "created_by", None)
    return sync_account_opening_posting(acc, opening_date=entry_date, actor=actor)


def repost_opening_balance(acc, fin_start_date):
    from financial.services_opening_balance import sync_account_opening_posting

    return sync_account_opening_posting(acc, opening_date=fin_start_date)
