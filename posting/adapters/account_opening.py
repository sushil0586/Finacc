from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from django.core.exceptions import ValidationError
from django.utils import timezone

from entity.models import EntityFinancialYear
from posting.common.static_accounts import StaticAccountCodes
from posting.services.posting_service import JLInput, q2
from posting.services.static_accounts import StaticAccountService

ZERO = Decimal("0.00")


@dataclass(frozen=True)
class AccountOpeningPostingPayload:
    entityfin_id: int
    posting_date: date
    voucher_date: date
    voucher_no: str
    narration: str
    jl_inputs: list[JLInput]


class AccountOpeningPostingAdapter:
    offset_static_account_code = StaticAccountCodes.OPENING_BALANCE_OFFSET

    def __init__(self, *, entity_id: int):
        self.entity_id = int(entity_id)

    @staticmethod
    def _as_date(value) -> Optional[date]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        try:
            return value.date()
        except Exception:
            return None

    @staticmethod
    def _opening_pair(account_obj) -> tuple[Decimal, Decimal]:
        ledger = getattr(account_obj, "ledger", None)
        opening_dr = q2(getattr(ledger, "openingbdr", None) or ZERO)
        opening_cr = q2(getattr(ledger, "openingbcr", None) or ZERO)
        return opening_dr, opening_cr

    def resolve_financial_year(self, account_obj, *, opening_date=None) -> EntityFinancialYear:
        opening_day = self._as_date(opening_date)
        base_qs = (
            EntityFinancialYear.objects.filter(entity_id=account_obj.entity_id)
            .only("id", "desc", "year_code", "finstartyear", "finendyear", "isactive")
        )
        if opening_day:
            row = (
                base_qs.filter(
                    finstartyear__date__lte=opening_day,
                    finendyear__date__gte=opening_day,
                )
                .order_by("-finstartyear", "-id")
                .first()
            )
            if row:
                return row

        row = base_qs.filter(isactive=True).order_by("-finstartyear", "-id").first()
        if row:
            return row

        today = timezone.localdate()
        row = (
            base_qs.filter(
                finstartyear__date__lte=today,
                finendyear__date__gte=today,
            )
            .order_by("-finstartyear", "-id")
            .first()
        )
        if row:
            return row

        row = base_qs.order_by("-finstartyear", "-id").first()
        if row:
            return row

        raise ValidationError(
            {
                "opening_balance": (
                    "No financial year is configured for this entity. "
                    "Create or activate the correct financial year before saving opening balances."
                )
            }
        )

    def validate_prerequisites(self, account_obj, *, opening_date=None) -> None:
        if not getattr(account_obj, "ledger_id", None):
            raise ValidationError({"opening_balance": "Opening balance posting requires the account to be linked to a ledger."})

        opening_dr, opening_cr = self._opening_pair(account_obj)
        if opening_dr and opening_cr:
            raise ValidationError({"opening_balance": "Only one of Opening DR or Opening CR can be non-zero."})

        if opening_dr < ZERO or opening_cr < ZERO:
            raise ValidationError({"opening_balance": "Opening balance values cannot be negative."})

        if opening_dr == ZERO and opening_cr == ZERO:
            return

        self.resolve_financial_year(account_obj, opening_date=opening_date)
        StaticAccountService.get_account_id(
            account_obj.entity_id,
            self.offset_static_account_code,
            required=True,
        )

    def build_post_payload(self, account_obj, *, opening_date=None) -> Optional[AccountOpeningPostingPayload]:
        self.validate_prerequisites(account_obj, opening_date=opening_date)

        opening_dr, opening_cr = self._opening_pair(account_obj)
        if opening_dr == ZERO and opening_cr == ZERO:
            return None

        financial_year = self.resolve_financial_year(account_obj, opening_date=opening_date)
        posting_date = self._as_date(opening_date) or self._as_date(financial_year.finstartyear)
        if posting_date is None:
            raise ValidationError({"opening_balance": "Unable to determine the opening balance posting date."})

        offset_account_id = StaticAccountService.get_account_id(
            account_obj.entity_id,
            self.offset_static_account_code,
            required=True,
        )
        offset_ledger_id = StaticAccountService.get_ledger_id(
            account_obj.entity_id,
            self.offset_static_account_code,
            required=False,
        )

        amount = opening_dr or opening_cr
        label = str(getattr(account_obj, "accountname", "") or f"Account {account_obj.pk}").strip()
        voucher_no = f"ACC-OPEN-{financial_year.id}-{account_obj.id}"
        narration = f"Opening balance for {label}"
        detail_id = int(getattr(account_obj, "ledger_id", 0) or account_obj.id)

        if opening_dr > ZERO:
            jl_inputs = [
                JLInput(
                    account_id=account_obj.id,
                    ledger_id=account_obj.ledger_id,
                    drcr=True,
                    amount=amount,
                    description=f"{narration} | Opening debit",
                    detail_id=detail_id,
                ),
                JLInput(
                    account_id=offset_account_id,
                    ledger_id=offset_ledger_id,
                    drcr=False,
                    amount=amount,
                    description=f"{narration} | Opening offset",
                    detail_id=detail_id,
                ),
            ]
        else:
            jl_inputs = [
                JLInput(
                    account_id=offset_account_id,
                    ledger_id=offset_ledger_id,
                    drcr=True,
                    amount=amount,
                    description=f"{narration} | Opening offset",
                    detail_id=detail_id,
                ),
                JLInput(
                    account_id=account_obj.id,
                    ledger_id=account_obj.ledger_id,
                    drcr=False,
                    amount=amount,
                    description=f"{narration} | Opening credit",
                    detail_id=detail_id,
                ),
            ]

        return AccountOpeningPostingPayload(
            entityfin_id=int(financial_year.id),
            posting_date=posting_date,
            voucher_date=posting_date,
            voucher_no=voucher_no,
            narration=narration,
            jl_inputs=jl_inputs,
        )
