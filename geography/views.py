from rest_framework.generics import ListAPIView
from rest_framework import permissions
from geography.models import Country, State, District, City
from geography.serializers import CountrySerializer, StateListSerializer, DistrictListSerializer, CityListSerializer,CountrySerializer
from django_filters.rest_framework import DjangoFilterBackend


class CountryApiView(ListAPIView):
    serializer_class = CountrySerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['id']

    def get_queryset(self):
        # Prefetch related states for each country
        return Country.objects.prefetch_related('state').all()


class StateApiView(ListAPIView):
    serializer_class = StateListSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['id', 'country']

    def get_queryset(self):
        # Prefetch related districts for each state (using related_name='districts')
        return State.objects.prefetch_related('districts').all()


class DistrictApiView(ListAPIView):
    serializer_class = DistrictListSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['id', 'state']

    def get_queryset(self):
        # Prefetch related cities for each district (using related_name='cities')
        return District.objects.prefetch_related('cities').all()


class CityApiView(ListAPIView):
    serializer_class = CityListSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['id', 'distt']

    def get_queryset(self):
        # Just return all cities
        return City.objects.all().order_by('-id')[:10]
