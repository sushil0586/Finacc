from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from entity.onboarding_serializers import (
    EntityOnboardingCreateSerializer,
    EntityOnboardingResponseSerializer,
    RegisterAndOnboardResponseSerializer,
    RegisterAndOnboardSerializer,
)
from entity.onboarding_services import EntityOnboardingService


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
            "gstno": entity.gstno,
            "financial_year_ids": result["financial_year_ids"],
            "bank_account_ids": result["bank_account_ids"],
            "subentity_ids": result["subentity_ids"],
            "constitution_ids": result["constitution_ids"],
            "financial": result["financial"],
            "rbac": result["rbac"],
        }
        output = EntityOnboardingResponseSerializer(response_payload)
        return Response(output.data, status=status.HTTP_201_CREATED)


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
            "gstno": entity.gstno,
            "financial_year_ids": result["onboarding"]["financial_year_ids"],
            "bank_account_ids": result["onboarding"]["bank_account_ids"],
            "subentity_ids": result["onboarding"]["subentity_ids"],
            "constitution_ids": result["onboarding"]["constitution_ids"],
            "financial": result["onboarding"]["financial"],
            "rbac": result["onboarding"]["rbac"],
        }
        response_payload = {
            "user": {
                "id": result["user"].id,
                "email": result["user"].email,
                "username": result["user"].username,
                "first_name": result["user"].first_name,
                "last_name": result["user"].last_name,
            },
            "onboarding": onboarding_payload,
            "verification": result["verification"],
        }
        output = RegisterAndOnboardResponseSerializer(response_payload)
        return Response(output.data, status=status.HTTP_201_CREATED)


def _client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
