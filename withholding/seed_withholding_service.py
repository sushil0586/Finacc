from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Dict

from django.db import transaction

from withholding.models import (
    WithholdingSection,
    WithholdingTaxType,
    WithholdingBaseRule,
)


class WithholdingSeedService:

    @staticmethod
    def _sections_data() -> List[Dict]:
        """
        Master seed definitions.
        Adjust rates/thresholds per FY if needed.
        """

        return [

            # ==========================
            # TDS SECTIONS
            # ==========================

            # 194C - Contractor
            dict(
                tax_type=WithholdingTaxType.TDS,
                section_code="194C",
                description="Payment to Contractor",
                base_rule=WithholdingBaseRule.INVOICE_VALUE_EXCL_GST,
                rate_default=Decimal("1.0000"),  # Individual/HUF (default)
                threshold_default=None,
                requires_pan=True,
                higher_rate_no_pan=Decimal("20.0000"),
                effective_from=date(2024, 4, 1),
            ),

            # 194J - Professional Fees
            dict(
                tax_type=WithholdingTaxType.TDS,
                section_code="194J",
                description="Professional / Technical Fees",
                base_rule=WithholdingBaseRule.INVOICE_VALUE_EXCL_GST,
                rate_default=Decimal("10.0000"),
                threshold_default=None,
                requires_pan=True,
                higher_rate_no_pan=Decimal("20.0000"),
                effective_from=date(2024, 4, 1),
            ),

            # 194H - Commission
            dict(
                tax_type=WithholdingTaxType.TDS,
                section_code="194H",
                description="Commission or Brokerage",
                base_rule=WithholdingBaseRule.INVOICE_VALUE_EXCL_GST,
                rate_default=Decimal("5.0000"),
                threshold_default=None,
                requires_pan=True,
                higher_rate_no_pan=Decimal("20.0000"),
                effective_from=date(2024, 4, 1),
            ),

            # 194I - Rent
            dict(
                tax_type=WithholdingTaxType.TDS,
                section_code="194I",
                description="Rent Payment",
                base_rule=WithholdingBaseRule.INVOICE_VALUE_EXCL_GST,
                rate_default=Decimal("10.0000"),
                threshold_default=None,
                requires_pan=True,
                higher_rate_no_pan=Decimal("20.0000"),
                effective_from=date(2024, 4, 1),
            ),

            # 194Q - Purchase of Goods
            dict(
                tax_type=WithholdingTaxType.TDS,
                section_code="194Q",
                description="TDS on Purchase of Goods",
                base_rule=WithholdingBaseRule.INVOICE_VALUE_EXCL_GST,
                rate_default=Decimal("0.1000"),
                threshold_default=Decimal("5000000.00"),  # 50L
                requires_pan=True,
                higher_rate_no_pan=Decimal("5.0000"),
                effective_from=date(2024, 4, 1),
            ),

            # ==========================
            # TCS SECTIONS
            # ==========================

            # 206C(1) - Scrap
            dict(
                tax_type=WithholdingTaxType.TCS,
                section_code="206C(1)",
                description="TCS on Scrap",
                base_rule=WithholdingBaseRule.INVOICE_VALUE_EXCL_GST,
                rate_default=Decimal("1.0000"),
                threshold_default=None,
                requires_pan=True,
                higher_rate_no_pan=Decimal("5.0000"),
                effective_from=date(2024, 4, 1),
            ),

            # 206C(1H) - Sale of Goods (Historical)
            dict(
                tax_type=WithholdingTaxType.TCS,
                section_code="206C(1H)",
                description="TCS on Sale of Goods (Valid till 31-Mar-2025)",
                base_rule=WithholdingBaseRule.INVOICE_VALUE_EXCL_GST,
                rate_default=Decimal("0.1000"),
                threshold_default=Decimal("5000000.00"),
                requires_pan=True,
                higher_rate_no_pan=Decimal("5.0000"),
                effective_from=date(2020, 10, 1),
                effective_to=date(2025, 3, 31),  # Important
            ),
        ]

    # -------------------------------------------------

    @classmethod
    @transaction.atomic
    def seed(cls, *, verbose: bool = True) -> None:
        """
        Idempotent seed.
        Updates existing, creates missing.
        """

        created = 0
        updated = 0

        for data in cls._sections_data():
            obj, is_created = WithholdingSection.objects.update_or_create(
                tax_type=data["tax_type"],
                section_code=data["section_code"],
                effective_from=data["effective_from"],
                defaults={
                    "description": data["description"],
                    "base_rule": data["base_rule"],
                    "rate_default": data["rate_default"],
                    "threshold_default": data.get("threshold_default"),
                    "requires_pan": data["requires_pan"],
                    "higher_rate_no_pan": data.get("higher_rate_no_pan"),
                    "effective_to": data.get("effective_to"),
                    "is_active": True,
                }
            )

            if is_created:
                created += 1
            else:
                updated += 1

        if verbose:
            print(f"[WithholdingSeedService] Created: {created}, Updated: {updated}")