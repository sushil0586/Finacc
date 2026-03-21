from rest_framework import serializers

from financial.models import ContactDetails, ShippingDetails


class ShippingDetailsSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = ShippingDetails
        fields = (
            "id",
            "account",
            "entity",
            "gstno",
            "address1",
            "address2",
            "country",
            "state",
            "district",
            "city",
            "pincode",
            "phoneno",
            "full_name",
            "emailid",
            "isprimary",
        )
        extra_kwargs = {
            "account": {"required": False, "allow_null": True},
            "entity": {"required": False, "allow_null": True},
        }

    def validate(self, attrs):
        isprimary = attrs.get("isprimary", None)
        account = attrs.get("account", getattr(self.instance, "account", None))
        entity = attrs.get("entity", getattr(self.instance, "entity", None))

        if isprimary is True and account:
            qs = ShippingDetails.objects.filter(account=account, isprimary=True)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({"isprimary": "Primary shipping address already exists for this account."})

        if entity is None and account and getattr(account, "entity_id", None):
            attrs["entity"] = account.entity

        return attrs


class ShippingDetailsListSerializer(serializers.ModelSerializer):
    countryName = serializers.CharField(source="country.countryname", read_only=True, allow_null=True)
    stateName = serializers.CharField(source="state.statename", read_only=True, allow_null=True)
    districtName = serializers.CharField(source="district.districtname", read_only=True, allow_null=True)
    cityName = serializers.CharField(source="city.cityname", read_only=True, allow_null=True)
    statecode = serializers.CharField(source="state.statecode", read_only=True)

    class Meta:
        model = ShippingDetails
        fields = (
            "id",
            "account",
            "entity",
            "gstno",
            "address1",
            "address2",
            "pincode",
            "phoneno",
            "full_name",
            "emailid",
            "isprimary",
            "country",
            "countryName",
            "state",
            "stateName",
            "district",
            "districtName",
            "city",
            "cityName",
            "statecode",
        )


class ContactDetailsSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = ContactDetails
        fields = (
            "id",
            "account",
            "entity",
            "address1",
            "address2",
            "country",
            "state",
            "district",
            "city",
            "pincode",
            "phoneno",
            "full_name",
            "emailid",
            "designation",
            "isprimary",
        )
        extra_kwargs = {
            "account": {"required": False, "allow_null": True},
            "entity": {"required": False, "allow_null": True},
        }

    def validate(self, attrs):
        isprimary = attrs.get("isprimary", None)
        account = attrs.get("account", getattr(self.instance, "account", None))

        if isprimary is True and account:
            qs = ContactDetails.objects.filter(account=account, isprimary=True)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({"isprimary": "Primary contact already exists for this account."})

        entity = attrs.get("entity", None)
        if entity is None and account and getattr(account, "entity_id", None):
            attrs["entity"] = account.entity

        return attrs


class ContactDetailsListSerializer(serializers.ModelSerializer):
    countryName = serializers.CharField(source="country.countryname", read_only=True, allow_null=True)
    stateName = serializers.CharField(source="state.statename", read_only=True, allow_null=True)
    districtName = serializers.CharField(source="district.districtname", read_only=True, allow_null=True)
    cityName = serializers.CharField(source="city.cityname", read_only=True, allow_null=True)

    class Meta:
        model = ContactDetails
        fields = (
            "id",
            "account",
            "entity",
            "address1",
            "address2",
            "pincode",
            "phoneno",
            "emailid",
            "full_name",
            "designation",
            "isprimary",
            "country",
            "countryName",
            "state",
            "stateName",
            "district",
            "districtName",
            "city",
            "cityName",
        )
