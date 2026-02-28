from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from django.db.models import Q, Sum


ZERO2 = Decimal("0.00")


def q2(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"))


@dataclass(frozen=True)
class ThresholdResult:
    threshold: Decimal
    previous_total: Decimal
    current_amount: Decimal
    base_applicable: Decimal          # amount above threshold within this txn
    cumulative_after: Decimal

    def to_dict(self) -> dict:
        return {
            "threshold": str(self.threshold),
            "previous_total": str(self.previous_total),
            "current_amount": str(self.current_amount),
            "base_applicable": str(self.base_applicable),
            "cumulative_after": str(self.cumulative_after),
        }


class FyPartyThresholdService:
    """
    Generic FY+party threshold calculator.

    Typical use:
      - 194Q: per vendor per FY threshold 50L, apply on amount exceeding threshold.
      - (Later) 206C(1H) historical: per customer per FY threshold 50L, apply above threshold.

    This service only computes the *base amount* on which withholding applies.
    """

    @staticmethod
    def _sum_previous(
        *,
        model,                 # PurchaseInvoiceHeader (or SalesInvoiceHeader for TCS)
        amount_field: str,      # e.g. "total_taxable"
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        party_field: str,       # "vendor_id" or "customer_id"
        party_id: int,
        txn_date: date,         # bill_date
        current_id: Optional[int],
        allowed_statuses: tuple,
        date_field: str = "bill_date",
    ) -> Decimal:
        """
        Sum amounts for all documents in the same FY/party earlier than this document.

        Ordering rule for backdated docs:
          earlier = (date < txn_date) OR (date == txn_date AND id < current_id)
        For create (no id yet), it uses (date < txn_date) only, which is good enough.
        """

        qs = model.objects.filter(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            **({ "subentity_id": subentity_id } if subentity_id is not None else {"subentity_id__isnull": True}),
            **{party_field: party_id},
            status__in=allowed_statuses,
        )

        # exclude self if update
        if current_id:
            qs = qs.exclude(id=current_id)

        # earlier filter
        if current_id:
            earlier_q = Q(**{f"{date_field}__lt": txn_date}) | (Q(**{date_field: txn_date}) & Q(id__lt=current_id))
        else:
            earlier_q = Q(**{f"{date_field}__lt": txn_date})

        qs = qs.filter(earlier_q)

        agg = qs.aggregate(total=Sum(amount_field))
        return q2((agg["total"] or ZERO2))

    @classmethod
    def compute_base_above_threshold(
        cls,
        *,
        model,
        amount_field: str,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: Optional[int],
        party_field: str,
        party_id: int,
        txn_date: date,
        current_amount: Decimal,
        threshold: Decimal,
        current_id: Optional[int],
        allowed_statuses: tuple,
        date_field: str = "bill_date",
    ) -> ThresholdResult:
        """
        Returns the part of current_amount that is above the FY threshold.
        """
        threshold = q2(threshold)
        current_amount = q2(current_amount)

        if current_amount <= ZERO2 or threshold <= ZERO2:
            return ThresholdResult(threshold, ZERO2, current_amount, ZERO2, current_amount)

        prev_total = cls._sum_previous(
            model=model,
            amount_field=amount_field,
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            party_field=party_field,
            party_id=party_id,
            txn_date=txn_date,
            current_id=current_id,
            allowed_statuses=allowed_statuses,
            date_field=date_field,
        )

        cumulative_after = q2(prev_total + current_amount)

        # 3 cases:
        # A) still below threshold => 0
        if cumulative_after <= threshold:
            base = ZERO2
        # B) already exceeded before => full current
        elif prev_total >= threshold:
            base = current_amount
        # C) crossing in this txn => only excess part
        else:
            base = q2(cumulative_after - threshold)

        return ThresholdResult(
            threshold=threshold,
            previous_total=prev_total,
            current_amount=current_amount,
            base_applicable=base,
            cumulative_after=cumulative_after,
        )