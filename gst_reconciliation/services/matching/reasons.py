from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from gst_reconciliation.models import GstMismatchReason


@dataclass(frozen=True)
class StructuredMismatch:
    code: str
    category: str
    severity: str
    message: str
    details_json: dict[str, Any]

    def to_summary(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "category": self.category,
            "severity": self.severity,
            "message": self.message,
            "details": self.details_json,
        }


def missing_in_books_reason(*, gstin: str, invoice_number: str) -> StructuredMismatch:
    return StructuredMismatch(
        code="MISSING_IN_BOOKS",
        category="matching",
        severity=GstMismatchReason.Severity.ERROR,
        message="Imported GST portal row was not found in purchase books.",
        details_json={"counterparty_gstin": gstin, "invoice_number": invoice_number},
    )


def multiple_candidates_reason(*, candidate_ids: list[int]) -> StructuredMismatch:
    return StructuredMismatch(
        code="MULTIPLE_CANDIDATES",
        category="matching",
        severity=GstMismatchReason.Severity.ERROR,
        message="Multiple purchase invoices matched with similar confidence.",
        details_json={"candidate_ids": candidate_ids},
    )


def field_mismatch_reason(
    *,
    code: str,
    message: str,
    expected: Any,
    actual: Any,
    severity: str = GstMismatchReason.Severity.WARNING,
) -> StructuredMismatch:
    return StructuredMismatch(
        code=code,
        category="field_mismatch",
        severity=severity,
        message=message,
        details_json={"expected": str(expected), "actual": str(actual)},
    )


def amount_mismatch_reason(
    *,
    code: str,
    message: str,
    expected: Decimal,
    actual: Decimal,
    tolerance: Decimal,
    severity: str = GstMismatchReason.Severity.WARNING,
) -> StructuredMismatch:
    return StructuredMismatch(
        code=code,
        category="amount_mismatch",
        severity=severity,
        message=message,
        details_json={
            "expected": str(expected),
            "actual": str(actual),
            "tolerance": str(tolerance),
            "difference": str((expected - actual).copy_abs().quantize(Decimal("0.01"))),
        },
    )
