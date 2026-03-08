from __future__ import annotations

from django.conf import settings
from django.db import models

from .base import TrackingModel


class PaymentMode(TrackingModel):
    paymentmode = models.CharField(max_length=200, verbose_name="Payment Mode")
    paymentmodecode = models.CharField(max_length=20, verbose_name="Payment Mode Code")
    iscash = models.BooleanField(default=True, verbose_name="IsCash Transaction")
    createdby = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    class Meta:
        ordering = ("paymentmode", "id")
        constraints = [
            models.UniqueConstraint(fields=("paymentmodecode",), name="uq_pay_mode_code"),
        ]

    def __str__(self):
        return f"{self.paymentmode}"
