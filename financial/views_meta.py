# accounts/views_meta.py  (or put inside your existing views.py)

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import Q

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


class LedgerFormMetaAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        entity_id = request.query_params.get("entity")
        if not entity_id:
            return Response({"error": "Entity is required"}, status=400)

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
            }
        )


class AccountFormMetaAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        entity_id = request.query_params.get("entity")
        if not entity_id:
            return Response({"error": "Entity is required"}, status=400)

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
            }
        )


class AccountingMastersMetaAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        entity_id = request.query_params.get("entity")
        if not entity_id:
            return Response({"error": "Entity is required"}, status=400)

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
