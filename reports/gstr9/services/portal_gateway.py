from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.utils import timezone


@dataclass(frozen=True)
class Gstr9PortalSubmitResult:
    status: str
    provider: str
    portal_reference: str
    payload: dict


class BaseGstr9PortalGateway:
    provider = "base"

    def submit(self, *, filing_run, submission_data: dict | None = None) -> Gstr9PortalSubmitResult:
        raise NotImplementedError


class SimulatedGstr9PortalGateway(BaseGstr9PortalGateway):
    provider = "simulated"

    def submit(self, *, filing_run, submission_data: dict | None = None) -> Gstr9PortalSubmitResult:
        portal_reference = f"GSTR9-SIM-{filing_run.id}"
        stamp = timezone.now().strftime("%Y%m%d%H%M%S")
        payload = {
            "mode": "simulated",
            "ack_no": f"ACK-{filing_run.id}-{stamp}",
            "arn_no": f"ARN-{filing_run.id}-{stamp}",
        }
        return Gstr9PortalSubmitResult(
            status="submitted",
            provider=self.provider,
            portal_reference=portal_reference,
            payload=payload,
        )


class ManualGstr9PortalGateway(BaseGstr9PortalGateway):
    provider = "manual"

    def submit(self, *, filing_run, submission_data: dict | None = None) -> Gstr9PortalSubmitResult:
        submission_data = submission_data or {}
        portal_reference = str(submission_data.get("portal_reference") or "").strip()
        if not portal_reference:
            raise ValueError("portal_reference is required for manual provider.")
        payload = {
            "mode": "manual",
            "ack_no": str(submission_data.get("ack_no") or "").strip(),
            "arn_no": str(submission_data.get("arn_no") or "").strip(),
            "note": str(submission_data.get("note") or "").strip(),
        }
        return Gstr9PortalSubmitResult(
            status="submitted",
            provider=self.provider,
            portal_reference=portal_reference,
            payload=payload,
        )


def build_gstr9_portal_gateway() -> BaseGstr9PortalGateway:
    provider = str(getattr(settings, "GSTR9_FILING_PROVIDER", "simulated") or "simulated").strip().lower()
    if provider == "simulated":
        return SimulatedGstr9PortalGateway()
    if provider == "manual":
        return ManualGstr9PortalGateway()
    raise ValueError("Unsupported GSTR9_FILING_PROVIDER. Supported values: simulated, manual.")
