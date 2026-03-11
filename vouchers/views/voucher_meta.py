from __future__ import annotations

from django.db.models import Q
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from entity.models import EntityFinancialYear, SubEntity
from financial.models import account
from vouchers.models import VoucherHeader, VoucherLine
from vouchers.serializers.voucher import VoucherDetailSerializer
from vouchers.services.voucher_settings_service import VoucherSettingsService


class VoucherMetaBaseAPIView(APIView):
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
        return list(
            SubEntity.objects.filter(entity_id=entity_id, isactive=True)
            .order_by("-ismainentity", "subentityname", "id")
            .values("id", "subentityname", "ismainentity")
        )

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

    def _cash_bank_accounts(self, entity_id: int):
        rows = list(
            account.objects.filter(entity_id=entity_id, isactive=True, ledger__isnull=False)
            .exclude(partytype__in=["Customer", "Vendor", "Both"])
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

    def _line_accounts(self, entity_id: int):
        rows = list(
            account.objects.filter(entity_id=entity_id, isactive=True, ledger__isnull=False)
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

    def _voucher_queryset(self, entity_id: int, entityfinid_id: int, subentity_id: int | None):
        qs = (
            VoucherHeader.objects.filter(entity_id=entity_id, entityfinid_id=entityfinid_id)
            .select_related(
                "entity",
                "entityfinid",
                "subentity",
                "cash_bank_account",
                "cash_bank_account__ledger",
                "created_by",
                "approved_by",
                "cancelled_by",
            )
            .prefetch_related("lines__account", "lines__account__ledger", "lines__generated_from_line")
        )
        if subentity_id is None:
            return qs.filter(subentity__isnull=True)
        return qs.filter(Q(subentity_id=subentity_id) | Q(subentity__isnull=True))

    def _action_flags(self, header: VoucherHeader):
        is_draft = int(header.status) == int(VoucherHeader.Status.DRAFT)
        is_confirmed = int(header.status) == int(VoucherHeader.Status.CONFIRMED)
        is_posted = int(header.status) == int(VoucherHeader.Status.POSTED)
        is_cancelled = int(header.status) == int(VoucherHeader.Status.CANCELLED)
        return {
            "can_edit": not is_posted and not is_cancelled,
            "can_confirm": is_draft,
            "can_post": is_confirmed,
            "can_cancel": is_draft or is_confirmed,
            "can_unpost": is_posted,
            "status": int(header.status),
            "status_name": header.get_status_display(),
        }

    def _account_block(self, obj, field_name: str, ledger_field_name: str):
        acct = getattr(obj, field_name, None)
        if not acct:
            return None
        stored_ledger_id = getattr(obj, ledger_field_name, None)
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
        settings_obj = VoucherSettingsService.get_settings(entity_id, subentity_id)
        return {
            "entity_id": entity_id,
            "entityfinid_id": entityfinid_id,
            "subentity_id": subentity_id,
            "choices": {
                "voucher_types": [{"value": value, "label": label} for value, label in VoucherHeader.VoucherType.choices],
                "statuses": [{"value": int(value), "label": label} for value, label in VoucherHeader.Status.choices],
            },
            "financial_years": self._financial_years(entity_id),
            "subentities": self._subentities(entity_id),
            "cash_bank_accounts": self._cash_bank_accounts(entity_id),
            "line_accounts": self._line_accounts(entity_id),
            "settings": {
                "default_doc_code_cash": settings_obj.default_doc_code_cash,
                "default_doc_code_bank": settings_obj.default_doc_code_bank,
                "default_doc_code_journal": settings_obj.default_doc_code_journal,
                "default_workflow_action": settings_obj.default_workflow_action,
            },
        }


class VoucherFormMetaAPIView(VoucherMetaBaseAPIView):
    def get(self, request):
        entity_id, entityfinid_id, subentity_id = self._parse_scope(request, require_entityfinid=False)
        return Response(self._voucher_form_meta(entity_id, entityfinid_id, subentity_id))


class VoucherDetailFormMetaAPIView(VoucherMetaBaseAPIView):
    def get(self, request):
        entity_id, entityfinid_id, subentity_id = self._parse_scope(request, require_entityfinid=True)
        voucher_id = self._parse_int(request.query_params.get("voucher"), "voucher", required=True)
        header = self._voucher_queryset(entity_id, entityfinid_id, subentity_id).get(pk=voucher_id)
        payload = self._voucher_form_meta(entity_id, entityfinid_id, subentity_id)
        payload.update(
            {
                "voucher_id": voucher_id,
                "voucher": VoucherDetailSerializer(
                    header,
                    context={"request": request, "skip_preview_numbers": True},
                ).data,
                "action_flags": self._action_flags(header),
                "cash_bank_account": self._account_block(header, "cash_bank_account", "cash_bank_ledger_id"),
            }
        )
        return Response(payload)


class VoucherSearchMetaAPIView(VoucherMetaBaseAPIView):
    def get(self, request):
        entity_id, entityfinid_id, subentity_id = self._parse_scope(request, require_entityfinid=True)
        return Response(
            {
                "entity_id": entity_id,
                "entityfinid_id": entityfinid_id,
                "subentity_id": subentity_id,
                "choices": {
                    "voucher_types": [{"value": value, "label": label} for value, label in VoucherHeader.VoucherType.choices],
                    "statuses": [{"value": int(value), "label": label} for value, label in VoucherHeader.Status.choices],
                },
                "financial_years": self._financial_years(entity_id),
                "subentities": self._subentities(entity_id),
                "cash_bank_accounts": self._cash_bank_accounts(entity_id),
            }
        )


class VoucherSettingsMetaAPIView(VoucherMetaBaseAPIView):
    def get(self, request):
        entity_id, entityfinid_id, subentity_id = self._parse_scope(request, require_entityfinid=True)
        settings_obj = VoucherSettingsService.get_settings(entity_id, subentity_id)
        policy = VoucherSettingsService.get_policy(entity_id, subentity_id)
        current_doc_numbers = {}
        doc_pairs = [
            ("cash_voucher", VoucherHeader.VoucherType.CASH, settings_obj.default_doc_code_cash),
            ("bank_voucher", VoucherHeader.VoucherType.BANK, settings_obj.default_doc_code_bank),
            ("journal_voucher", VoucherHeader.VoucherType.JOURNAL, settings_obj.default_doc_code_journal),
        ]
        for key, voucher_type, doc_code in doc_pairs:
            current_doc_numbers[key] = VoucherSettingsService.current_doc_no_for_type(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=subentity_id,
                voucher_type=voucher_type,
            )
        return Response(
            {
                "entity_id": entity_id,
                "entityfinid_id": entityfinid_id,
                "subentity_id": subentity_id,
                "financial_years": self._financial_years(entity_id),
                "subentities": self._subentities(entity_id),
                "settings": {
                    "default_doc_code_cash": settings_obj.default_doc_code_cash,
                    "default_doc_code_bank": settings_obj.default_doc_code_bank,
                    "default_doc_code_journal": settings_obj.default_doc_code_journal,
                    "default_workflow_action": settings_obj.default_workflow_action,
                    "policy_controls": policy.controls,
                },
                "current_doc_numbers": current_doc_numbers,
            }
        )
