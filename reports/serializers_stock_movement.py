from rest_framework import serializers

class StockMovementRequestSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    from_date = serializers.DateField()
    to_date = serializers.DateField()

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

    # switches
    include_details = serializers.BooleanField(required=False, default=False)
    include_zero = serializers.BooleanField(required=False, default=False)
    group_by_location = serializers.BooleanField(required=False, default=True)

    # sorting
    ordering = serializers.ChoiceField(
        choices=["product", "-product", "qty", "-qty", "value", "-value"],
        required=False,
        default="product"
    )

    # paging for JSON only
    page = serializers.IntegerField(required=False, default=1)
    page_size = serializers.IntegerField(required=False, default=50)

    def validate(self, data):
        if data["from_date"] > data["to_date"]:
            raise serializers.ValidationError("from_date cannot be after to_date")
        return data
