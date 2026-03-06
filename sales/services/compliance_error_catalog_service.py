from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sales.models.sales_compliance import SalesComplianceErrorCode


@dataclass(frozen=True)
class ComplianceErrorInfo:
    code: Optional[str]
    message: Optional[str]
    reason: Optional[str] = None
    resolution: Optional[str] = None

    def as_text(self) -> str:
        msg = (self.message or "").strip()
        reason = (self.reason or "").strip()
        resolution = (self.resolution or "").strip()
        if reason:
            msg = f"{msg} | Reason: {reason}" if msg else f"Reason: {reason}"
        if resolution:
            msg = f"{msg} | Resolution: {resolution}" if msg else f"Resolution: {resolution}"
        return msg or "Unknown compliance error."


class ComplianceErrorCatalogService:
    @staticmethod
    def resolve(*, code: Optional[str], message: Optional[str]) -> ComplianceErrorInfo:
        c = (str(code).strip() if code is not None else "") or None
        m = (str(message).strip() if message is not None else "") or None
        if not c:
            return ComplianceErrorInfo(code=c, message=m)

        row = (
            SalesComplianceErrorCode.objects
            .filter(code=c, is_active=True)
            .only("code", "message", "reason", "resolution")
            .first()
        )
        if not row:
            return ComplianceErrorInfo(code=c, message=m)

        return ComplianceErrorInfo(
            code=c,
            message=row.message or m,
            reason=row.reason or None,
            resolution=row.resolution or None,
        )
