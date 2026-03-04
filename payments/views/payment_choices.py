from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from payments.services.payment_choice_service import PaymentChoiceService


class PaymentCompiledChoicesAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(PaymentChoiceService.compile_choices())
