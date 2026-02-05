from rest_framework import serializers

class StockAgingRequestSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    as_on_date = serializers.DateField()

    # filters (optional)
    location = serializers.IntegerField(required=False)
    locations = serializers.ListField(child=serializers.IntegerField(), required=False)
    product = serializers.IntegerField(required=False)
    products = serializers.ListField(child=serializers.IntegerField(), required=False)
    category = serializers.IntegerField(required=False)
    brand = serializers.IntegerField(required=False)
    hsn = serializers.IntegerField(required=False)

    include_txn_types = serializers.ListField(child=serializers.CharField(), required=False)
    exclude_txn_types = serializers.ListField(child=serializers.CharField(), required=False)
    search = serializers.CharField(required=False, allow_blank=True)

    group_by_location = serializers.BooleanField(required=False, default=True)
    include_zero = serializers.BooleanField(required=False, default=False)

    # buckets as list of end days: [30,60,90,180] -> creates: 0-30,31-60,61-90,91-180,181+
    bucket_ends = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        default=[30, 60, 90, 180]
    )

    ordering = serializers.ChoiceField(
        choices=["product", "-product", "qty", "-qty"],
        required=False,
        default="product"
    )

    # pagination for JSON only
    page = serializers.IntegerField(required=False, default=1)
    page_size = serializers.IntegerField(required=False, default=50)

    def validate_bucket_ends(self, value):
        value = sorted(set(value))
        if not value:
            raise serializers.ValidationError("bucket_ends cannot be empty")
        return value
