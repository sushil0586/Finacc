from __future__ import annotations

from rest_framework import generics, permissions

from receipts.models import ReceiptMode
from receipts.serializers.receipt_masters import ReceiptModeSerializer


class ReceiptModeListAPIView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ReceiptModeSerializer

    def get_queryset(self):
        return ReceiptMode.objects.all().order_by("paymentmode")
