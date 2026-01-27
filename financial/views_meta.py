# accounts/views_meta.py  (or put inside your existing views.py)

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

# import the choices from your models.py
from .models import (
    PARTY_TYPE_CHOICES,
    PAYMENT_TERMS_CHOICES,
    CURRENCY_CHOICES,
    GST_REG_TYPE_CHOICES,
    GSTIN_TYPE_CHOICES,
    BLOCK_STATUS_CHOICES,

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
