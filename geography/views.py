from django_filters.rest_framework import DjangoFilterBackend
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework.generics import ListAPIView

from geography.models import City, Country, District, State
from geography.serializers import CityListSerializer, CountrySerializer, DistrictListSerializer, StateListSerializer


COUNTRY_CACHE_SECONDS = 24 * 60 * 60
STATE_CACHE_SECONDS = 6 * 60 * 60
DISTRICT_CACHE_SECONDS = 2 * 60 * 60
CITY_CACHE_SECONDS = 2 * 60 * 60


def _search_term(request):
    for key in ("search", "q", "term"):
        value = (request.query_params.get(key) or "").strip()
        if value:
            return value
    return ""


def _apply_search(queryset, request, fields):
    term = _search_term(request)
    if not term:
        return queryset

    search_query = None
    for field in fields:
        lookup = {f"{field}__icontains": term}
        filtered = queryset.filter(**lookup)
        search_query = filtered if search_query is None else search_query | filtered
    return search_query.distinct() if search_query is not None else queryset


@method_decorator(cache_page(COUNTRY_CACHE_SECONDS), name="dispatch")
class CountryApiView(ListAPIView):
    serializer_class = CountrySerializer

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['id']

    def get_queryset(self):
        queryset = Country.objects.filter(isactive=True).prefetch_related('state')
        return _apply_search(queryset, self.request, ["countryname", "countrycode"])


@method_decorator(cache_page(STATE_CACHE_SECONDS), name="dispatch")
class StateApiView(ListAPIView):
    serializer_class = StateListSerializer

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['id', 'country']

    def get_queryset(self):
        queryset = State.objects.filter(isactive=True, country__isactive=True).select_related('country').prefetch_related('districts')
        country_id = self.request.query_params.get('country') or self.request.query_params.get('country_id')
        if country_id:
            queryset = queryset.filter(country_id=country_id)
        return _apply_search(queryset, self.request, ["statename", "statecode"])


@method_decorator(cache_page(DISTRICT_CACHE_SECONDS), name="dispatch")
class DistrictApiView(ListAPIView):
    serializer_class = DistrictListSerializer

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['id', 'state']

    def get_queryset(self):
        queryset = District.objects.filter(isactive=True, state__isactive=True).select_related('state').prefetch_related('cities')
        state_id = self.request.query_params.get('state') or self.request.query_params.get('state_id')
        if state_id:
            queryset = queryset.filter(state_id=state_id)
        return _apply_search(queryset, self.request, ["districtname", "districtcode"])


@method_decorator(cache_page(CITY_CACHE_SECONDS), name="dispatch")
class CityApiView(ListAPIView):
    serializer_class = CityListSerializer

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['id']

    def get_queryset(self):
        queryset = City.objects.filter(isactive=True, distt__isactive=True).select_related('distt')
        district_id = self.request.query_params.get('district_id') or self.request.query_params.get('distt')
        if district_id:
            queryset = queryset.filter(distt_id=district_id)
        return _apply_search(queryset, self.request, ["cityname", "citycode", "pincode"])
