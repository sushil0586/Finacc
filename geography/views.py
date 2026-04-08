from rest_framework.generics import ListAPIView
from geography.models import Country, State, District, City
from geography.serializers import CountrySerializer, StateListSerializer, DistrictListSerializer, CityListSerializer
from django_filters.rest_framework import DjangoFilterBackend


class CountryApiView(ListAPIView):
    serializer_class = CountrySerializer
    

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['id']

    def get_queryset(self):
        return Country.objects.filter(isactive=True).prefetch_related('state')


class StateApiView(ListAPIView):
    serializer_class = StateListSerializer
    

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['id', 'country']

    def get_queryset(self):
        return State.objects.filter(isactive=True, country__isactive=True).select_related('country').prefetch_related('districts')


class DistrictApiView(ListAPIView):
    serializer_class = DistrictListSerializer
    

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['id', 'state']

    def get_queryset(self):
        return District.objects.filter(isactive=True, state__isactive=True).select_related('state').prefetch_related('cities')


class CityApiView(ListAPIView):
    serializer_class = CityListSerializer
   

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['id']

    def get_queryset(self):
        queryset = City.objects.filter(isactive=True, distt__isactive=True).select_related('distt')
        district_id = self.request.query_params.get('district_id') or self.request.query_params.get('distt')
        if district_id:
            queryset = queryset.filter(distt_id=district_id)
        return queryset
