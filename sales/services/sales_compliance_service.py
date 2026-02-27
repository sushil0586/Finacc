from __future__ import annotations

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from sales.models.sales_compliance import (
    SalesEInvoice, SalesEWayBill,
    SalesEInvoiceStatus, SalesEWayStatus,
)
from sales.services.providers.registry import ProviderRegistry
from sales.services.party_resolvers import seller_from_entity, buyer_from_account
from sales.services.irp_payload_builder import IRPPayloadBuilder
from financial.models import account as AccountModel


class SalesComplianceService:
    def __init__(self, *, invoice, user=None):
        self.invoice = invoice
        self.user = user

    def _buyer_account(self) -> AccountModel:
        inv = self.invoice
        # common FK names; update if yours differs
        for attr in ("customer", "buyer", "party", "account"):
            if hasattr(inv, attr) and getattr(inv, f"{attr}_id", None):
                return getattr(inv, attr)
        for id_attr in ("customer_id", "buyer_id", "party_id", "account_id"):
            if hasattr(inv, id_attr) and getattr(inv, id_attr):
                return AccountModel.objects.get(pk=getattr(inv, id_attr))
        raise ValidationError("Buyer account FK not found on SalesInvoiceHeader.")

    def _ensure_einvoice_row(self) -> SalesEInvoice:
        obj, _ = SalesEInvoice.objects.get_or_create(
            invoice=self.invoice,
            defaults={"created_by": self.user, "updated_by": self.user, "status": SalesEInvoiceStatus.PENDING},
        )
        return obj

    def _ensure_eway_row(self) -> SalesEWayBill:
        obj, _ = SalesEWayBill.objects.get_or_create(
            invoice=self.invoice,
            defaults={"created_by": self.user, "updated_by": self.user, "status": SalesEWayStatus.PENDING},
        )
        return obj

    def _assert_confirmed(self):
        if self.invoice.status != self.invoice.Status.CONFIRMED:
            raise ValidationError("Invoice must be CONFIRMED before generating IRN/EWB.")

    @transaction.atomic
    def ensure_rows(self) -> dict:
        # For now: create rows always; later we add rules engine
        einv = self._ensure_einvoice_row()
        ewb = self._ensure_eway_row()
        return {"einvoice_id": einv.id, "eway_id": ewb.id}

    @transaction.atomic
    def generate_irn(self) -> SalesEInvoice:
        self._assert_confirmed()

        einv = self._ensure_einvoice_row()
        if einv.status == SalesEInvoiceStatus.GENERATED and einv.irn:
            return einv  # idempotent

        payload = IRPPayloadBuilder(self.invoice).build()

        # inject Seller/Buyer from your required sources:
        payload["SellerDtls"] = seller_from_entity(self.invoice.entity)
        buyer = self._buyer_account()
        payload["BuyerDtls"] = buyer_from_account(buyer, pos_state=getattr(self.invoice, "pos_state", None))

        einv.last_request_json = payload
        einv.attempt_count = (einv.attempt_count or 0) + 1
        einv.last_attempt_at = timezone.now()
        einv.status = SalesEInvoiceStatus.PENDING
        einv.updated_by = self.user
        einv.save()

        provider_name = getattr(settings, "EINVOICE_PROVIDER", "mastergst")
        provider = ProviderRegistry.get_einvoice(provider_name)

        try:
            result = provider.generate_irn(invoice=self.invoice, payload=payload)
        except Exception as ex:
            einv.status = SalesEInvoiceStatus.FAILED
            einv.last_error_code = "PROVIDER_EXCEPTION"
            einv.last_error_message = str(ex)
            einv.save(update_fields=["status", "last_error_code", "last_error_message", "updated_at"])
            raise

        einv.last_response_json = result.raw
        if not result.ok or not result.irn:
            einv.status = SalesEInvoiceStatus.FAILED
            einv.last_error_code = result.error_code or "IRN_FAILED"
            einv.last_error_message = result.error_message or "IRN generation failed."
            einv.save()
            raise ValidationError({
                "message": einv.last_error_message,
                "code": einv.last_error_code,
                "raw": einv.last_response_json,   # ✅ so you see MasterGST exact reason
            })

        einv.irn = result.irn
        einv.ack_no = result.ack_no
        einv.ack_date = result.ack_date
        einv.signed_invoice = result.signed_invoice
        einv.signed_qr_code = result.signed_qr_code

        einv.ewb_no = result.ewb_no
        einv.ewb_date = result.ewb_date
        einv.ewb_valid_upto = result.ewb_valid_upto

        einv.status = SalesEInvoiceStatus.GENERATED
        einv.last_success_at = timezone.now()
        einv.last_error_code = None
        einv.last_error_message = None
        einv.updated_by = self.user
        einv.save()

        return einv