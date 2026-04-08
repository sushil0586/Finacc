from rest_framework import serializers
from geography.models import Country, State, District, City

# Optimized City Serializer for listing (lightweight)
class CityListSerializer(serializers.ModelSerializer):
    district_id = serializers.IntegerField(source="distt_id", read_only=True)
    distt = serializers.IntegerField(source="distt_id", read_only=True)

    class Meta:
        model = City
        fields = ['id', 'cityname', 'citycode', 'pincode', 'district_id', 'distt']


# Optimized District Serializer (with minimal nested data)
class DistrictListSerializer(serializers.ModelSerializer):
    class Meta:
        model = District
        fields = ['id', 'districtname', 'districtcode', 'state']


# Optimized District Serializer with Cities (for when you need full district data)
class DistrictSerializer(serializers.ModelSerializer):
    cities = CityListSerializer(many=True, read_only=True)

    class Meta:
        model = District
        fields = '__all__'


# Optimized State Serializer with Districts (for when you need full state data)
class StateSerializer(serializers.ModelSerializer):
    districts = DistrictListSerializer(many=True, read_only=True)

    class Meta:
        model = State
        fields = ['id', 'statename', 'districts']


# Optimized State List Serializer (lightweight for state lists)
class StateListSerializer(serializers.ModelSerializer):
    class Meta:
        model = State
        fields = ['id', 'statename', 'statecode', 'country']


# Optimized Country Serializer (lightweight, only country name)
class CountrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = ['id', 'countryname']


# View optimizations (use select_related or prefetch_related in your queries to reduce database hits)
# Example for getting all countries with associated states and districts:
# Example of how to optimize queryset in your view to reduce database hits:
"""
country_queryset = country.objects.prefetch_related(
    'state_set__district_set__city_set'
).all()
"""
