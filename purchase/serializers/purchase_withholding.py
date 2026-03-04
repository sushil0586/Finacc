from __future__ import annotations

from rest_framework import serializers

from withholding.models import WithholdingSection


class PurchaseTdsSectionSerializer(serializers.ModelSerializer):
    default_rate = serializers.DecimalField(source="rate_default", max_digits=7, decimal_places=4, read_only=True)

    class Meta:
        model = WithholdingSection
        fields = [
            "id",
            "section_code",
            "description",
            "default_rate",
            "base_rule",
            "threshold_default",
            "is_active",
        ]
