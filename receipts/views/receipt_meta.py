from __future__ import annotations

from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from entity.models import EntityFinancialYear, SubEntity
from financial.models import account
from receipts.models import ReceiptMode, ReceiptVoucherHeader
from receipts.serializers.receipt_voucher import ReceiptVoucherHeaderSerializer
from receipts.services.receipt_choice_service import ReceiptChoiceService
from receipts.services.receipt_settings_service import (
    DEFAULT_RECEIPT_POLICY_CONTROLS,
    ReceiptSettingsService,
)
from sales.models.sales_ar import CustomerAdvanceBalance, CustomerSettlement


class ReceiptMetaBaseAPIView(APIView):
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

    def _customers(self, entity_id: int):
        rows = list(
            account.objects.filter(entity_id=entity_id, isactive=True)
            .filter(Q(partytype__in=["Customer", "Both", "Bank"]) | Q(partytype__isnull=True) | Q(partytype=""))
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

    def _received_in_accounts(self, entity_id: int):
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

    def _receipt_modes(self):
        return list(
            ReceiptMode.objects.order_by("paymentmode", "id").values(
                "id",
                "paymentmode",
                "paymentmodecode",
                "iscash",
            )
        )

    def _voucher_queryset(self, entity_id: int, entityfinid_id: int, subentity_id: int | None):
        qs = ReceiptVoucherHeader.objects.filter(entity_id=entity_id, entityfinid_id=entityfinid_id).select_related(
            "entity",
            "entityfinid",
            "subentity",
            "received_in",
            "received_in__ledger",
            "received_from",
            "received_from__ledger",
            "receipt_mode",
            "ap_settlement",
        ).prefetch_related(
            "allocations__open_item",
            "advance_adjustments__advance_balance__receipt_voucher",
            "adjustments",
        )
        if subentity_id is None:
            return qs.filter(subentity__isnull=True)
        return qs.filter(Q(subentity_id=subentity_id) | Q(subentity__isnull=True))

    def _action_flags(self, header: ReceiptVoucherHeader):
        is_draft = int(header.status) == int(ReceiptVoucherHeader.Status.DRAFT)
        is_confirmed = int(header.status) == int(ReceiptVoucherHeader.Status.CONFIRMED)
        is_posted = int(header.status) == int(ReceiptVoucherHeader.Status.POSTED)
        is_cancelled = int(header.status) == int(ReceiptVoucherHeader.Status.CANCELLED)
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
        settings_obj = ReceiptSettingsService.get_settings(entity_id, subentity_id)
        return {
            "entity_id": entity_id,
            "entityfinid_id": entityfinid_id,
            "subentity_id": subentity_id,
            "choices": ReceiptChoiceService.compile_choices(),
            "financial_years": self._financial_years(entity_id),
            "subentities": self._subentities(entity_id),
            "received_in_accounts": self._received_in_accounts(entity_id),
            "customers": self._customers(entity_id),
            "receipt_modes": self._receipt_modes(),
            "settings": {
                "default_doc_code_receipt": settings_obj.default_doc_code_receipt,
                "default_workflow_action": settings_obj.default_workflow_action,
            },
        }


class ReceiptVoucherFormMetaAPIView(ReceiptMetaBaseAPIView):
    def get(self, request):
        entity_id, entityfinid_id, subentity_id = self._parse_scope(request, require_entityfinid=False)
        return Response(self._voucher_form_meta(entity_id, entityfinid_id, subentity_id))


class ReceiptVoucherDetailFormMetaAPIView(ReceiptMetaBaseAPIView):
    def get(self, request):
        entity_id, entityfinid_id, subentity_id = self._parse_scope(request, require_entityfinid=True)
        voucher_id = self._parse_int(request.query_params.get("voucher"), "voucher", required=True)
        header = self._voucher_queryset(entity_id, entityfinid_id, subentity_id).filter(pk=voucher_id).first()
        if not header:
            raise serializers.ValidationError({"voucher": "Receipt voucher not found in selected scope."})
        payload = self._voucher_form_meta(entity_id, entityfinid_id, subentity_id)
        payload.update(
            {
                "voucher_id": voucher_id,
                "voucher": ReceiptVoucherHeaderSerializer(
                    header,
                    context={"request": request, "skip_preview_numbers": True},
                ).data,
                "action_flags": self._action_flags(header),
                "received_in": self._account_block(header, "received_in"),
                "received_from": self._account_block(header, "received_from"),
            }
        )
        return Response(payload)


class ReceiptVoucherSearchMetaAPIView(ReceiptMetaBaseAPIView):
    def get(self, request):
        entity_id, entityfinid_id, subentity_id = self._parse_scope(request, require_entityfinid=True)
        return Response(
            {
                "entity_id": entity_id,
                "entityfinid_id": entityfinid_id,
                "subentity_id": subentity_id,
                "choices": ReceiptChoiceService.compile_choices(),
                "financial_years": self._financial_years(entity_id),
                "subentities": self._subentities(entity_id),
                "customers": self._customers(entity_id),
                "receipt_modes": self._receipt_modes(),
            }
        )


class ReceiptArMetaAPIView(ReceiptMetaBaseAPIView):
    def get(self, request):
        entity_id, entityfinid_id, subentity_id = self._parse_scope(request, require_entityfinid=True)
        return Response(
            {
                "entity_id": entity_id,
                "entityfinid_id": entityfinid_id,
                "subentity_id": subentity_id,
                "financial_years": self._financial_years(entity_id),
                "subentities": self._subentities(entity_id),
                "customers": self._customers(entity_id),
                "receipt_modes": self._receipt_modes(),
                "receipt_types": [
                    {"value": value, "label": label}
                    for value, label in ReceiptVoucherHeader.ReceiptType.choices
                ],
                "voucher_statuses": [
                    {"value": int(value), "label": label}
                    for value, label in ReceiptVoucherHeader.Status.choices
                ],
                "settlement_statuses": [
                    {"value": int(value), "label": label}
                    for value, label in CustomerSettlement.Status.choices
                ],
                "settlement_types": [
                    {"value": value, "label": label}
                    for value, label in CustomerSettlement.SettlementType.choices
                ],
                "advance_source_types": [
                    {"value": value, "label": label}
                    for value, label in CustomerAdvanceBalance.SourceType.choices
                ],
            }
        )


class ReceiptArSettlementFormMetaAPIView(ReceiptMetaBaseAPIView):
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
                "customers": self._customers(entity_id),
                "received_in_accounts": self._received_in_accounts(entity_id),
                "receipt_modes": self._receipt_modes(),
                "receipt_types": [
                    {"value": value, "label": label}
                    for value, label in ReceiptVoucherHeader.ReceiptType.choices
                ],
                "settlement_statuses": [
                    {"value": int(value), "label": label}
                    for value, label in CustomerSettlement.Status.choices
                ],
                "settlement_types": [
                    {"value": value, "label": label}
                    for value, label in CustomerSettlement.SettlementType.choices
                ],
            }
        )


class ReceiptSettingsMetaAPIView(ReceiptMetaBaseAPIView):
    def get(self, request):
        entity_id, entityfinid_id, subentity_id = self._parse_scope(request, require_entityfinid=True)
        settings_obj = ReceiptSettingsService.get_settings(entity_id, subentity_id)
        policy = ReceiptSettingsService.get_policy(entity_id, subentity_id)
        receipt_current = ReceiptSettingsService.get_current_doc_no(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            doc_key="RECEIPT_VOUCHER",
            doc_code=settings_obj.default_doc_code_receipt,
        )
        return Response(
            {
                "entity_id": entity_id,
                "entityfinid_id": entityfinid_id,
                "subentity_id": subentity_id,
                "financial_years": self._financial_years(entity_id),
                "subentities": self._subentities(entity_id),
                "settings": {
                    "default_doc_code_receipt": settings_obj.default_doc_code_receipt,
                    "default_workflow_action": settings_obj.default_workflow_action,
                    "policy_controls": policy.controls,
                },
                "defaults": {
                    "policy_controls": dict(DEFAULT_RECEIPT_POLICY_CONTROLS),
                    "default_workflow_actions": [
                        {"value": value, "label": label}
                        for value, label in settings_obj.DefaultWorkflowAction.choices
                    ],
                },
                "current_doc_numbers": {
                    "receipt_voucher": receipt_current,
                },
            }
        )
