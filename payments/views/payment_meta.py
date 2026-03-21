from __future__ import annotations

from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from entity.models import EntityFinancialYear, SubEntity
from financial.models import account
from payments.models import PaymentMode, PaymentVoucherHeader
from payments.serializers.payment_voucher import PaymentVoucherHeaderSerializer
from payments.services.payment_choice_service import PaymentChoiceService
from payments.services.payment_settings_service import (
    DEFAULT_PAYMENT_POLICY_CONTROLS,
    PaymentSettingsService,
)
from purchase.models.purchase_ap import VendorAdvanceBalance, VendorSettlement


class PaymentMetaBaseAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def _parse_int(self, raw_value, field_name: str, required: bool = False):
        if raw_value in (None, "", "null", "None"):
            if required:
                raise serializers.ValidationError({field_name: f"{field_name} query param is required"})
            return None
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            raise serializers.ValidationError({field_name: f"{field_name} must be an integer"})

    def _parse_scope(self, request, *, require_entityfinid: bool = False):
        entity_id = self._parse_int(request.query_params.get("entity"), "entity", required=True)
        entityfinid_id = self._parse_int(
            request.query_params.get("entityfinid"),
            "entityfinid",
            required=require_entityfinid,
        )
        subentity_id = self._parse_int(request.query_params.get("subentity"), "subentity", required=False)
        if subentity_id == 0:
            subentity_id = None
        return entity_id, entityfinid_id, subentity_id

    def _financial_years(self, entity_id: int):
        return list(
            EntityFinancialYear.objects.filter(entity_id=entity_id, isactive=True)
            .order_by("-isactive", "-finstartyear", "-id")
            .values("id", "finstartyear", "finendyear", "desc", "isactive")
        )

    def _subentities(self, entity_id: int):
        rows = list(
            SubEntity.objects.filter(entity_id=entity_id, isactive=True)
            .order_by("-is_head_office", "subentityname", "id")
            .values("id", "subentityname", "is_head_office")
        )
        for row in rows:
            # Backward-compatible key for older frontend consumers.
            row["ismainentity"] = row["is_head_office"]
        return rows

    def _account_payload(self, row: dict):
        return {
            "id": row["id"],
            "accountname": row["accountname"],
            "display_name": row["ledger__name"] or row["accountname"],
            "accountcode": row["ledger__ledger_code"],
            "gstno": row["gstno"],
            "pan": row["pan"],
            "partytype": row["partytype"],
            "state": row["state_id"],
            "statecode": row["state__statecode"],
            "statename": row["state__statename"],
            "city": row["city_id"],
            "cityname": row["city__cityname"],
            "ledger_id": row["ledger_id"],
        }

    def _vendors(self, entity_id: int):
        rows = list(
            account.objects.filter(entity_id=entity_id, isactive=True)
            .filter(Q(partytype__in=["Vendor", "Both", "Bank"]) | Q(partytype__isnull=True) | Q(partytype=""))
            .select_related("ledger", "state", "city")
            .order_by("accountname", "id")
            .values(
                "id",
                "accountname",
                "gstno",
                "pan",
                "partytype",
                "state_id",
                "state__statecode",
                "state__statename",
                "city_id",
                "city__cityname",
                "ledger_id",
                "ledger__ledger_code",
                "ledger__name",
            )
        )
        return [self._account_payload(row) for row in rows]

    def _paid_from_accounts(self, entity_id: int):
        rows = list(
            account.objects.filter(entity_id=entity_id, isactive=True, ledger__isnull=False)
            .exclude(Q(partytype__in=["Customer", "Vendor", "Both"]))
            .select_related("ledger", "state", "city")
            .order_by("accountname", "id")
            .values(
                "id",
                "accountname",
                "gstno",
                "pan",
                "partytype",
                "state_id",
                "state__statecode",
                "state__statename",
                "city_id",
                "city__cityname",
                "ledger_id",
                "ledger__ledger_code",
                "ledger__name",
            )
        )
        return [self._account_payload(row) for row in rows]

    def _payment_modes(self):
        return list(
            PaymentMode.objects.order_by("paymentmode", "id").values(
                "id",
                "paymentmode",
                "paymentmodecode",
                "iscash",
            )
        )

    def _voucher_queryset(self, entity_id: int, entityfinid_id: int, subentity_id: int | None):
        qs = PaymentVoucherHeader.objects.filter(entity_id=entity_id, entityfinid_id=entityfinid_id).select_related(
            "entity",
            "entityfinid",
            "subentity",
            "paid_from",
            "paid_from__ledger",
            "paid_to",
            "paid_to__ledger",
            "payment_mode",
            "ap_settlement",
        ).prefetch_related(
            "allocations__open_item",
            "advance_adjustments__advance_balance__payment_voucher",
            "adjustments",
        )
        if subentity_id is None:
            return qs.filter(subentity__isnull=True)
        return qs.filter(Q(subentity_id=subentity_id) | Q(subentity__isnull=True))

    def _action_flags(self, header: PaymentVoucherHeader):
        is_draft = int(header.status) == int(PaymentVoucherHeader.Status.DRAFT)
        is_confirmed = int(header.status) == int(PaymentVoucherHeader.Status.CONFIRMED)
        is_posted = int(header.status) == int(PaymentVoucherHeader.Status.POSTED)
        is_cancelled = int(header.status) == int(PaymentVoucherHeader.Status.CANCELLED)
        return {
            "can_edit": not is_posted and not is_cancelled,
            "can_confirm": is_draft,
            "can_post": is_confirmed,
            "can_cancel": is_draft or is_confirmed,
            "can_unpost": is_posted,
            "status": int(header.status),
            "status_name": header.get_status_display(),
        }

    def _account_block(self, obj, field_name: str):
        acct = getattr(obj, field_name, None)
        if not acct:
            return None
        stored_ledger_id = getattr(obj, f"{field_name}_ledger_id", None)
        return {
            "id": acct.id,
            "accountname": getattr(acct, "accountname", None),
            "display_name": getattr(acct, "effective_accounting_name", None),
            "accountcode": getattr(acct, "effective_accounting_code", None),
            "ledger_id": stored_ledger_id or getattr(acct, "ledger_id", None),
            "partytype": getattr(acct, "partytype", None),
            "gstno": getattr(acct, "gstno", None),
            "pan": getattr(acct, "pan", None),
        }

    def _voucher_form_meta(self, entity_id: int, entityfinid_id: int | None, subentity_id: int | None):
        settings_obj = PaymentSettingsService.get_settings(entity_id, subentity_id)
        payload = {
            "entity_id": entity_id,
            "entityfinid_id": entityfinid_id,
            "subentity_id": subentity_id,
            "choices": PaymentChoiceService.compile_choices(),
            "financial_years": self._financial_years(entity_id),
            "subentities": self._subentities(entity_id),
            "paid_from_accounts": self._paid_from_accounts(entity_id),
            "vendors": self._vendors(entity_id),
            "payment_modes": self._payment_modes(),
            "settings": {
                "default_doc_code_payment": settings_obj.default_doc_code_payment,
                "default_workflow_action": settings_obj.default_workflow_action,
            },
        }
        return payload


class PaymentVoucherFormMetaAPIView(PaymentMetaBaseAPIView):
    def get(self, request):
        entity_id, entityfinid_id, subentity_id = self._parse_scope(request, require_entityfinid=False)
        return Response(self._voucher_form_meta(entity_id, entityfinid_id, subentity_id))


class PaymentVoucherDetailFormMetaAPIView(PaymentMetaBaseAPIView):
    def get(self, request):
        entity_id, entityfinid_id, subentity_id = self._parse_scope(request, require_entityfinid=True)
        voucher_id = self._parse_int(request.query_params.get("voucher"), "voucher", required=True)
        header = self._voucher_queryset(entity_id, entityfinid_id, subentity_id).get(pk=voucher_id)
        payload = self._voucher_form_meta(entity_id, entityfinid_id, subentity_id)
        payload.update(
            {
                "voucher_id": voucher_id,
                "voucher": PaymentVoucherHeaderSerializer(
                    header,
                    context={"request": request, "skip_preview_numbers": True},
                ).data,
                "action_flags": self._action_flags(header),
                "paid_from": self._account_block(header, "paid_from"),
                "paid_to": self._account_block(header, "paid_to"),
            }
        )
        return Response(payload)


class PaymentVoucherSearchMetaAPIView(PaymentMetaBaseAPIView):
    def get(self, request):
        entity_id, entityfinid_id, subentity_id = self._parse_scope(request, require_entityfinid=True)
        return Response(
            {
                "entity_id": entity_id,
                "entityfinid_id": entityfinid_id,
                "subentity_id": subentity_id,
                "choices": PaymentChoiceService.compile_choices(),
                "financial_years": self._financial_years(entity_id),
                "subentities": self._subentities(entity_id),
                "vendors": self._vendors(entity_id),
                "payment_modes": self._payment_modes(),
            }
        )


class PaymentApMetaAPIView(PaymentMetaBaseAPIView):
    def get(self, request):
        entity_id, entityfinid_id, subentity_id = self._parse_scope(request, require_entityfinid=True)
        return Response(
            {
                "entity_id": entity_id,
                "entityfinid_id": entityfinid_id,
                "subentity_id": subentity_id,
                "financial_years": self._financial_years(entity_id),
                "subentities": self._subentities(entity_id),
                "vendors": self._vendors(entity_id),
                "payment_modes": self._payment_modes(),
                "payment_types": [
                    {"value": value, "label": label}
                    for value, label in PaymentVoucherHeader.PaymentType.choices
                ],
                "voucher_statuses": [
                    {"value": int(value), "label": label}
                    for value, label in PaymentVoucherHeader.Status.choices
                ],
                "settlement_statuses": [
                    {"value": int(value), "label": label}
                    for value, label in VendorSettlement.Status.choices
                ],
                "settlement_types": [
                    {"value": value, "label": label}
                    for value, label in VendorSettlement.SettlementType.choices
                ],
                "advance_source_types": [
                    {"value": value, "label": label}
                    for value, label in VendorAdvanceBalance.SourceType.choices
                ],
            }
        )


class PaymentApSettlementFormMetaAPIView(PaymentMetaBaseAPIView):
    def get(self, request):
        entity_id, entityfinid_id, subentity_id = self._parse_scope(request, require_entityfinid=True)
        return Response(
            {
                "entity_id": entity_id,
                "entityfinid_id": entityfinid_id,
                "subentity_id": subentity_id,
                "default_voucher_date": timezone.localdate(),
                "financial_years": self._financial_years(entity_id),
                "subentities": self._subentities(entity_id),
                "vendors": self._vendors(entity_id),
                "paid_from_accounts": self._paid_from_accounts(entity_id),
                "payment_modes": self._payment_modes(),
                "payment_types": [
                    {"value": value, "label": label}
                    for value, label in PaymentVoucherHeader.PaymentType.choices
                ],
                "settlement_statuses": [
                    {"value": int(value), "label": label}
                    for value, label in VendorSettlement.Status.choices
                ],
                "settlement_types": [
                    {"value": value, "label": label}
                    for value, label in VendorSettlement.SettlementType.choices
                ],
            }
        )


class PaymentSettingsMetaAPIView(PaymentMetaBaseAPIView):
    def get(self, request):
        entity_id, entityfinid_id, subentity_id = self._parse_scope(request, require_entityfinid=True)
        settings_obj = PaymentSettingsService.get_settings(entity_id, subentity_id)
        policy = PaymentSettingsService.get_policy(entity_id, subentity_id)
        payment_current = PaymentSettingsService.get_current_doc_no(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            doc_key="PAYMENT_VOUCHER",
            doc_code=settings_obj.default_doc_code_payment,
        )
        return Response(
            {
                "entity_id": entity_id,
                "entityfinid_id": entityfinid_id,
                "subentity_id": subentity_id,
                "financial_years": self._financial_years(entity_id),
                "subentities": self._subentities(entity_id),
                "settings": {
                    "default_doc_code_payment": settings_obj.default_doc_code_payment,
                    "default_workflow_action": settings_obj.default_workflow_action,
                    "policy_controls": policy.controls,
                },
                "defaults": {
                    "policy_controls": dict(DEFAULT_PAYMENT_POLICY_CONTROLS),
                    "default_workflow_actions": [
                        {"value": value, "label": label}
                        for value, label in settings_obj.DefaultWorkflowAction.choices
                    ],
                },
                "current_doc_numbers": {
                    "payment_voucher": payment_current,
                },
            }
        )
