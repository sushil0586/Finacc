from rest_framework import permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from entity.models import Constitution, Entity, EntityFinancialYear, GstRegistrationType, SubEntity, UnitType
from entity.onboarding_serializers import (
    CityOptionSerializer,
    CountryOptionSerializer,
    DistrictOptionSerializer,
    EntityOnboardingCreateSerializer,
    EntityOnboardingDetailResponseSerializer,
    OnboardingMetaResponseSerializer,
    EntityOnboardingResponseSerializer,
    EntityOnboardingUpdateSerializer,
    RegisterAndOnboardResponseSerializer,
    RegisterAndOnboardSerializer,
    StateOptionSerializer,
)
from entity.onboarding_services import EntityOnboardingService
from geography.models import City, Country, District, State
from helpers.utils.gst_api import get_gst_details
from subscriptions.services import SubscriptionService


def _entity_primary_gst(entity):
    row = entity.gst_registrations.filter(isactive=True, is_primary=True).first()
    return row.gstin if row else None


class EntityOnboardingCreateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = EntityOnboardingCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = EntityOnboardingService.create_entity(actor=request.user, payload=serializer.validated_data)
        entity = result["entity"]
        response_payload = {
            "entity_id": entity.id,
            "entity_name": entity.entityname,
            "gstno": _entity_primary_gst(entity),
            "financial_year_ids": result["financial_year_ids"],
            "bank_account_ids": result["bank_account_ids"],
            "subentity_ids": result["subentity_ids"],
            "constitution_ids": result["constitution_ids"],
            "financial": result["financial"],
            "rbac": result["rbac"],
            "subscription": SubscriptionService.build_subscription_snapshot(entity=entity),
        }
        output = EntityOnboardingResponseSerializer(response_payload)
        return Response(output.data, status=status.HTTP_201_CREATED)


class EntityOnboardingDetailAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk, *args, **kwargs):
        entity = get_object_or_404(Entity, pk=pk)
        if not EntityOnboardingService.can_manage_entity(user=request.user, entity=entity):
            return Response({"detail": "You are not allowed to view this entity."}, status=status.HTTP_403_FORBIDDEN)

        payload = EntityOnboardingService.build_entity_payload(entity=entity)
        output = EntityOnboardingDetailResponseSerializer(payload)
        return Response(output.data, status=status.HTTP_200_OK)

    def put(self, request, pk, *args, **kwargs):
        return self._update(request, pk, partial=False)

    def patch(self, request, pk, *args, **kwargs):
        return self._update(request, pk, partial=True)

    def _update(self, request, pk, partial):
        entity = get_object_or_404(Entity, pk=pk)
        serializer = EntityOnboardingUpdateSerializer(data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        payload = EntityOnboardingService.update_entity(
            actor=request.user,
            entity=entity,
            payload=serializer.validated_data,
        )
        output = EntityOnboardingDetailResponseSerializer(payload)
        return Response(output.data, status=status.HTTP_200_OK)


class RegisterAndEntityOnboardingCreateAPIView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        serializer = RegisterAndOnboardSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = EntityOnboardingService.register_user_and_create_entity(
            payload=serializer.validated_data,
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
            ip_address=_client_ip(request),
        )
        entity = result["onboarding"]["entity"]
        onboarding_payload = {
            "entity_id": entity.id,
            "entity_name": entity.entityname,
            "gstno": _entity_primary_gst(entity),
            "financial_year_ids": result["onboarding"]["financial_year_ids"],
            "bank_account_ids": result["onboarding"]["bank_account_ids"],
            "subentity_ids": result["onboarding"]["subentity_ids"],
            "constitution_ids": result["onboarding"]["constitution_ids"],
            "financial": result["onboarding"]["financial"],
            "rbac": result["onboarding"]["rbac"],
            "subscription": result["subscription"],
        }
        response_payload = {
            "user": {
                "id": result["user"].id,
                "email": result["user"].email,
                "username": result["user"].username,
                "first_name": result["user"].first_name,
                "last_name": result["user"].last_name,
            },
            "intent": result.get("intent"),
            "onboarding": onboarding_payload,
            "verification": result["verification"],
            "subscription": result["subscription"],
        }
        output = RegisterAndOnboardResponseSerializer(response_payload)
        return Response(output.data, status=status.HTTP_201_CREATED)


class EntityOnboardingMetaAPIView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request, *args, **kwargs):
        payload = {
            "version": "v2",
            "defaults": {
                "seed_options": {
                    "template_code": "standard_trading",
                    "seed_financial": True,
                    "seed_rbac": True,
                    "seed_default_subentity": True,
                    "seed_default_roles": True,
                },
                "bank_account_types": [
                    {"value": "current", "label": "Current"},
                    {"value": "savings", "label": "Savings"},
                ],
            },
            "required_fields": {
                "entity": ["entityname", "address", "phoneoffice"],
                "financial_years": ["finstartyear", "finendyear"],
            },
            "payload_contract": {
                "root_keys": [
                    "entity",
                    "financial_years",
                    "bank_accounts",
                    "subentities",
                    "constitution_details",
                    "seed_options",
                ],
                "arrays_allow_empty": [
                    "bank_accounts",
                    "subentities",
                    "constitution_details",
                ],
                "arrays_required_non_empty": [
                    "financial_years",
                ],
            },
            "ui_hints": {
                "financial_years_min_items": 1,
                "seed_default_subentity_note": "If subentities is empty and seed_default_subentity=true, backend creates one default HO subentity.",
                "enum_source": "field_choices",
                "date_format": "Use ISO date/date-time strings.",
            },
            "dropdowns": {
                "unit_types": [
                    {
                        "id": row.id,
                        "label": row.UnitName,
                        "description": row.UnitDesc,
                    }
                    for row in UnitType.objects.all().order_by("UnitName")
                ],
                "gst_registration_types": [
                    {
                        "id": row.id,
                        "label": row.Name,
                        "description": row.Description,
                    }
                    for row in GstRegistrationType.objects.all().order_by("Name")
                ],
                "constitutions": [
                    {
                        "id": row.id,
                        "label": row.constitutionname,
                        "code": row.constcode,
                        "description": row.constitutiondesc,
                    }
                    for row in Constitution.objects.all().order_by("constitutionname")
                ],
                "countries": CountryOptionSerializer(Country.objects.all().order_by("countryname"), many=True).data,
            },
            "field_choices": {
                "organization_status": [{"value": value, "label": label} for value, label in Entity.OrganizationStatus.choices],
                "business_type": [{"value": value, "label": label} for value, label in Entity.BusinessType.choices],
                "gst_registration_status": [{"value": value, "label": label} for value, label in Entity.GstStatus.choices],
                "msme_category": [{"value": value, "label": label} for value, label in Entity.MsmeCategory.choices],
                "branch_type": [{"value": value, "label": label} for value, label in SubEntity.BranchType.choices],
                "financial_year_status": [{"value": value, "label": label} for value, label in EntityFinancialYear.PeriodStatus.choices],
            },
            "geography_filters": {
                "states_by_country": True,
                "districts_by_state": True,
                "cities_by_district": True,
            },
            "endpoints": {
                "create": "/api/entity/onboarding/create/",
                "detail": "/api/entity/onboarding/entity/<id>/",
                "update": "/api/entity/onboarding/entity/<id>/",
                "register_and_create": "/api/entity/onboarding/register/",
                "meta": "/api/entity/onboarding/meta/",
                "countries": "/api/entity/onboarding/options/countries/",
                "states": "/api/entity/onboarding/options/states/?country_id=<id>",
                "districts": "/api/entity/onboarding/options/districts/?state_id=<id>",
                "cities": "/api/entity/onboarding/options/cities/?district_id=<id>",
                "gst_lookup": "/api/entity/onboarding/gst-lookup/?gstno=<gstin>",
            },
            "deprecated_endpoints": [
                "/api/entity/entityDetails",
                "/api/entity/unittype",
                "/api/entity/constitution",
                "/api/entity/entityfy",
                "/api/entity/entityfylist",
                "/api/entity/subentity",
                "/api/entity/subentity/<id>",
                "/api/entity/subentitybyentity/",
                "/api/entity/getyearsbyentity",
                "/api/entity/bankaccounts/",
                "/api/entity/bankaccounts/<pk>/",
                "/api/entity/bankaccounts/entity/<entity_id>/",
                "/api/entity/entity/<id>/",
            ],
        }
        output = OnboardingMetaResponseSerializer(payload)
        return Response(output.data, status=status.HTTP_200_OK)


class OnboardingCountryOptionsAPIView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request, *args, **kwargs):
        rows = Country.objects.all().order_by("countryname")
        return Response(CountryOptionSerializer(rows, many=True).data, status=status.HTTP_200_OK)


class OnboardingStateOptionsAPIView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request, *args, **kwargs):
        country_id = request.query_params.get("country_id")
        rows = State.objects.all().order_by("statename")
        if country_id:
            rows = rows.filter(country_id=country_id)
        return Response(StateOptionSerializer(rows, many=True).data, status=status.HTTP_200_OK)


class OnboardingDistrictOptionsAPIView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request, *args, **kwargs):
        state_id = request.query_params.get("state_id")
        rows = District.objects.all().order_by("districtname")
        if state_id:
            rows = rows.filter(state_id=state_id)
        return Response(DistrictOptionSerializer(rows, many=True).data, status=status.HTTP_200_OK)


class OnboardingCityOptionsAPIView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request, *args, **kwargs):
        district_id = request.query_params.get("district_id")
        rows = City.objects.all().order_by("cityname")
        if district_id:
            rows = rows.filter(distt_id=district_id)
        return Response(CityOptionSerializer(rows, many=True).data, status=status.HTTP_200_OK)


class OnboardingGstLookupAPIView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request, *args, **kwargs):
        gstno = (request.query_params.get("gstno") or "").strip()
        if not gstno:
            raise ValidationError({"gstno": "gstno query parameter is required."})

        gst_data = get_gst_details(gstno)
        if not gst_data:
            raise ValidationError({"gstno": "GST details could not be fetched."})

        try:
            state = State.objects.filter(statecode=gst_data.get("StateCode")).first()
            city = City.objects.filter(pincode=gst_data.get("AddrPncd")).first()
            district = city.distt if city else None
            country = state.country if state else None
        except Exception:
            state = None
            city = None
            district = None
            country = None

        payload = {
            "gstno": gst_data.get("Gstin"),
            "entityname": gst_data.get("TradeName"),
            "legalname": gst_data.get("LegalName"),
            "address": gst_data.get("AddrBnm"),
            "address2": gst_data.get("AddrBno"),
            "addressfloorno": gst_data.get("AddrFlno"),
            "addressstreet": gst_data.get("AddrSt"),
            "stateid": state.id if state else None,
            "cityid": city.id if city else None,
            "countryid": country.id if country else None,
            "disttid": district.id if district else None,
            "pincode": gst_data.get("AddrPncd"),
            "gstintype": gst_data.get("TxpType"),
            "dateofreg": gst_data.get("DtReg"),
            "dateofdreg": gst_data.get("DtDReg"),
            "blockstatus": gst_data.get("BlkStatus"),
            "status": gst_data.get("Status"),
        }
        return Response(payload, status=status.HTTP_200_OK)


def _client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
