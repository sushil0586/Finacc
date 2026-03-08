from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from receipts.services.receipt_choice_service import ReceiptChoiceService


class ReceiptCompiledChoicesAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(ReceiptChoiceService.compile_choices())
