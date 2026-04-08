from __future__ import annotations

from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.entitlements import ScopedEntitlementMixin
from entity.models import EntityFinancialYear, SubEntity
from financial.models import AccountAddress, account
from financial.profile_access import account_gstno, account_pan, account_partytype
from vouchers.models import VoucherHeader, VoucherLine
from vouchers.serializers.voucher import VoucherDetailSerializer
from vouchers.services.voucher_settings_service import VoucherSettingsService
from subscriptions.services import SubscriptionLimitCodes, SubscriptionService


class VoucherMetaBaseAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [IsAuthenticated]
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_FINANCIAL
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

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
        self.enforce_scope(request, entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id)
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

    def _account_payload(self, row):
        prefetched_primary = getattr(row, "prefetched_primary_addresses", None)
        primary = prefetched_primary[0] if prefetched_primary else None
        state = getattr(primary, "state", None)
        city = getattr(primary, "city", None)
        return {
            "id": row.id,
            "accountname": row.accountname,
            "display_name": getattr(row.ledger, "name", None) or row.accountname,
            "accountcode": getattr(row.ledger, "ledger_code", None),
            "gstno": getattr(getattr(row, "compliance_profile", None), "gstno", None),
            "pan": getattr(getattr(row, "compliance_profile", None), "pan", None),
            "partytype": getattr(getattr(row, "commercial_profile", None), "partytype", None),
            "state": getattr(primary, "state_id", None),
            "statecode": getattr(state, "statecode", None),
            "statename": getattr(state, "statename", None),
            "city": getattr(primary, "city_id", None),
            "cityname": getattr(city, "cityname", None),
            "ledger_id": row.ledger_id,
        }

    def _cash_bank_accounts(self, entity_id: int):
        primary_address_qs = AccountAddress.objects.filter(isprimary=True, isactive=True).select_related("state", "city")
        rows = list(
            account.objects.filter(entity_id=entity_id, isactive=True, ledger__isnull=False)
            .exclude(commercial_profile__partytype__in=["Customer", "Vendor", "Both"])
            .select_related("ledger", "compliance_profile", "commercial_profile")
            .prefetch_related(
                Prefetch(
                    "addresses",
                    queryset=primary_address_qs,
                    to_attr="prefetched_primary_addresses",
                )
            )
            .order_by("accountname", "id")
        )
        return [self._account_payload(row) for row in rows]

    def _line_accounts(self, entity_id: int):
        primary_address_qs = AccountAddress.objects.filter(isprimary=True, isactive=True).select_related("state", "city")
        rows = list(
            account.objects.filter(entity_id=entity_id, isactive=True, ledger__isnull=False)
            .select_related("ledger", "compliance_profile", "commercial_profile")
            .prefetch_related(
                Prefetch(
                    "addresses",
                    queryset=primary_address_qs,
                    to_attr="prefetched_primary_addresses",
                )
            )
            .order_by("accountname", "id")
        )
        return [self._account_payload(row) for row in rows]

    def _voucher_queryset(
        self,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: int | None,
        *,
        allow_any_subentity: bool = False,
    ):
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
            if allow_any_subentity:
                return qs
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
            "partytype": account_partytype(acct),
            "gstno": account_gstno(acct),
            "pan": account_pan(acct),
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
        header = get_object_or_404(
            self._voucher_queryset(
                entity_id,
                entityfinid_id,
                subentity_id,
                allow_any_subentity=subentity_id is None,
            ),
            pk=voucher_id,
        )
        effective_subentity_id = header.subentity_id if subentity_id is None else subentity_id
        payload = self._voucher_form_meta(entity_id, entityfinid_id, effective_subentity_id)
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

