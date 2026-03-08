from __future__ import annotations

from rest_framework import generics, permissions

from payments.models import PaymentMode
from payments.serializers.payment_masters import PaymentModeSerializer


class PaymentModeListAPIView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PaymentModeSerializer

    def get_queryset(self):
        return PaymentMode.objects.all().order_by("paymentmode")
