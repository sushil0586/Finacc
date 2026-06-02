# accounts/views_meta.py  (or put inside your existing views.py)

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import Q

from core.entitlements import ScopedEntitlementMixin
from subscriptions.services import SubscriptionLimitCodes, SubscriptionService
from .governance import PARTY_MANAGED, resolve_financial_master_rule

# import the choices from your models.py
from .models import (
    PARTY_TYPE_CHOICES,
    PAYMENT_TERMS_CHOICES,
    CURRENCY_CHOICES,
    GST_REG_TYPE_CHOICES,
    GSTIN_TYPE_CHOICES,
    BLOCK_STATUS_CHOICES,
    BALANCE_TYPE_CHOICES,
    accountHead,
    accounttype,
    Ledger,

)

def _choice_list(choices):
    # choices: [("Customer","Customer"), ...]
    return [{"value": v, "label": str(lbl)} for v, lbl in choices]


def _governance_payload(entity_id: int) -> dict:
    party_suggestions: dict[str, dict] = {}
    party_managed_account_type_ids: set[int] = set()
    party_managed_head_ids: set[int] = set()
    direct_edit_blocked_account_type_ids: set[int] = set()
    direct_edit_blocked_head_ids: set[int] = set()

    for party_value, _label in PARTY_TYPE_CHOICES:
        rule = resolve_financial_master_rule(entity=entity_id, partytype=party_value)
        if not rule:
            continue
        payload = {
            "management_mode": rule.management_mode,
            "auto_create_account": bool(rule.auto_create_account),
            "allow_direct_ledger_edit": bool(rule.allow_direct_ledger_edit),
            "account_type_id": getattr(rule.suggested_account_type, "id", None) or rule.account_type_id,
            "debit_head_id": getattr(rule.suggested_debit_head, "id", None) or rule.debit_head_id,
            "credit_head_id": getattr(rule.suggested_credit_head, "id", None) or rule.credit_head_id,
        }
        party_suggestions[party_value] = payload

        candidate_type_ids = [payload["account_type_id"], rule.account_type_id]
        candidate_head_ids = [
            payload["debit_head_id"],
            payload["credit_head_id"],
            rule.debit_head_id,
            rule.credit_head_id,
        ]
        if rule.management_mode == PARTY_MANAGED:
            party_managed_account_type_ids.update(int(item) for item in candidate_type_ids if item)
            party_managed_head_ids.update(int(item) for item in candidate_head_ids if item)
        if not rule.allow_direct_ledger_edit:
            direct_edit_blocked_account_type_ids.update(int(item) for item in candidate_type_ids if item)
            direct_edit_blocked_head_ids.update(int(item) for item in candidate_head_ids if item)

    return {
        "party_suggestions": party_suggestions,
        "party_managed_account_type_ids": sorted(party_managed_account_type_ids),
        "party_managed_head_ids": sorted(party_managed_head_ids),
        "direct_edit_blocked_account_type_ids": sorted(direct_edit_blocked_account_type_ids),
        "direct_edit_blocked_head_ids": sorted(direct_edit_blocked_head_ids),
    }


class AccountChoicesAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            "partytype": _choice_list(PARTY_TYPE_CHOICES),
            "paymentterms": _choice_list(PAYMENT_TERMS_CHOICES),
            "currency": _choice_list(CURRENCY_CHOICES),
            "gstregtype": _choice_list(GST_REG_TYPE_CHOICES),
            "gstintype": _choice_list(GSTIN_TYPE_CHOICES),
            "blockstatus": _choice_list(BLOCK_STATUS_CHOICES),
        })


class LedgerFormMetaAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [IsAuthenticated]
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_FINANCIAL
    subscription_access_mode = SubscriptionService.ACCESS_MODE_SETUP

    def get(self, request):
        entity_id = request.query_params.get("entity")
        if not entity_id:
            return Response({"error": "Entity is required"}, status=400)
        self.enforce_scope(request, entity_id=int(entity_id))

        account_types = list(
            accounttype.objects.filter(entity_id=entity_id, isactive=True)
            .order_by("accounttypename")
            .values("id", "accounttypename", "accounttypecode", "balanceType")
        )

        account_heads = list(
            accountHead.objects.filter(entity_id=entity_id, isactive=True)
            .select_related("accounttype", "accountheadsr")
            .order_by("code", "name")
            .values(
                "id",
                "name",
                "code",
                "balanceType",
                "drcreffect",
                "detailsingroup",
                "accounttype_id",
                "accounttype__accounttypename",
                "accountheadsr_id",
                "accountheadsr__name",
            )
        )

        ledgers = list(
            Ledger.objects.filter(entity_id=entity_id, isactive=True)
            .order_by("ledger_code", "name")
            .values("id", "ledger_code", "name", "accounthead_id")
        )

        return Response(
            {
                "entity_id": int(entity_id),
                "accounttypes": [
                    {
                        "id": row["id"],
                        "name": row["accounttypename"],
                        "code": row["accounttypecode"],
                        "balanceType": row["balanceType"],
                    }
                    for row in account_types
                ],
                "accountheads": [
                    {
                        "id": row["id"],
                        "name": row["name"],
                        "code": row["code"],
                        "balanceType": row["balanceType"],
                        "drcreffect": row["drcreffect"],
                        "detailsingroup": row["detailsingroup"],
                        "accounttype_id": row["accounttype_id"],
                        "accounttype_name": row["accounttype__accounttypename"],
                        "parent_id": row["accountheadsr_id"],
                        "parent_name": row["accountheadsr__name"],
                    }
                    for row in account_heads
                ],
                "contra_ledgers": [
                    {
                        "id": row["id"],
                        "ledger_code": row["ledger_code"],
                        "name": row["name"],
                        "accounthead_id": row["accounthead_id"],
                    }
                    for row in ledgers
                ],
                "governance": _governance_payload(int(entity_id)),
            }
        )


class AccountFormMetaAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [IsAuthenticated]
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_FINANCIAL
    subscription_access_mode = SubscriptionService.ACCESS_MODE_SETUP

    def get(self, request):
        entity_id = request.query_params.get("entity")
        if not entity_id:
            return Response({"error": "Entity is required"}, status=400)
        self.enforce_scope(request, entity_id=int(entity_id))

        account_types = list(
            accounttype.objects.filter(entity_id=entity_id, isactive=True)
            .order_by("accounttypename")
            .values("id", "accounttypename", "accounttypecode", "balanceType")
        )

        account_heads = list(
            accountHead.objects.filter(entity_id=entity_id, isactive=True)
            .select_related("accounttype", "accountheadsr")
            .order_by("code", "name")
            .values(
                "id",
                "name",
                "code",
                "balanceType",
                "drcreffect",
                "detailsingroup",
                "accounttype_id",
                "accounttype__accounttypename",
                "accountheadsr_id",
                "accountheadsr__name",
            )
        )

        contra_ledgers = list(
            Ledger.objects.filter(entity_id=entity_id, isactive=True)
            .order_by("ledger_code", "name")
            .values("id", "ledger_code", "name", "accounthead_id")
        )

        return Response(
            {
                "entity_id": int(entity_id),
                "choices": {
                    "partytype": _choice_list(PARTY_TYPE_CHOICES),
                    "paymentterms": _choice_list(PAYMENT_TERMS_CHOICES),
                    "currency": _choice_list(CURRENCY_CHOICES),
                    "gstregtype": _choice_list(GST_REG_TYPE_CHOICES),
                    "gstintype": _choice_list(GSTIN_TYPE_CHOICES),
                    "blockstatus": _choice_list(BLOCK_STATUS_CHOICES),
                },
                "accounttypes": [
                    {
                        "id": row["id"],
                        "name": row["accounttypename"],
                        "code": row["accounttypecode"],
                        "balanceType": row["balanceType"],
                    }
                    for row in account_types
                ],
                "accountheads": [
                    {
                        "id": row["id"],
                        "name": row["name"],
                        "code": row["code"],
                        "balanceType": row["balanceType"],
                        "drcreffect": row["drcreffect"],
                        "detailsingroup": row["detailsingroup"],
                        "accounttype_id": row["accounttype_id"],
                        "accounttype_name": row["accounttype__accounttypename"],
                        "parent_id": row["accountheadsr_id"],
                        "parent_name": row["accountheadsr__name"],
                    }
                    for row in account_heads
                ],
                "contra_ledgers": [
                    {
                        "id": row["id"],
                        "ledger_code": row["ledger_code"],
                        "name": row["name"],
                        "accounthead_id": row["accounthead_id"],
                    }
                    for row in contra_ledgers
                ],
                "ledger_mode": "auto_managed",
                "governance": _governance_payload(int(entity_id)),
            }
        )


class AccountingMastersMetaAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [IsAuthenticated]
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_FINANCIAL
    subscription_access_mode = SubscriptionService.ACCESS_MODE_SETUP

    def get(self, request):
        entity_id = request.query_params.get("entity")
        if not entity_id:
            return Response({"error": "Entity is required"}, status=400)
        self.enforce_scope(request, entity_id=int(entity_id))

        account_types = list(
            accounttype.objects.filter(entity_id=entity_id)
            .order_by("accounttypename")
            .values("id", "accounttypename", "accounttypecode", "balanceType", "isactive")
        )

        account_heads = list(
            accountHead.objects.filter(entity_id=entity_id)
            .select_related("accounttype", "accountheadsr")
            .order_by("code", "name")
            .values(
                "id",
                "name",
                "code",
                "detailsingroup",
                "balanceType",
                "drcreffect",
                "description",
                "accounttype_id",
                "accounttype__accounttypename",
                "accountheadsr_id",
                "accountheadsr__name",
                "canbedeleted",
                "isactive",
            )
        )

        return Response(
            {
                "entity_id": int(entity_id),
                "choices": {
                    "balanceType": _choice_list(BALANCE_TYPE_CHOICES),
                    "drcrEffect": _choice_list(BALANCE_TYPE_CHOICES),
                    "detailsInGroup": [
                        {"value": 1, "label": "Trading / Stock"},
                        {"value": 2, "label": "Profit & Loss Group"},
                        {"value": 3, "label": "Ledger Posting Group"},
                    ],
                },
                "accounttypes": [
                    {
                        "id": row["id"],
                        "accounttypename": row["accounttypename"],
                        "accounttypecode": row["accounttypecode"],
                        "balanceType": row["balanceType"],
                        "isactive": row["isactive"],
                    }
                    for row in account_types
                ],
                "accountheads": [
                    {
                        "id": row["id"],
                        "name": row["name"],
                        "code": row["code"],
                        "detailsingroup": row["detailsingroup"],
                        "balanceType": row["balanceType"],
                        "drcreffect": row["drcreffect"],
                        "description": row["description"],
                        "accounttype": row["accounttype_id"],
                        "accounttype_name": row["accounttype__accounttypename"],
                        "accountheadsr": row["accountheadsr_id"],
                        "parent_name": row["accountheadsr__name"],
                        "canbedeleted": row["canbedeleted"],
                        "isactive": row["isactive"],
                    }
                    for row in account_heads
                ],
            }
        )
