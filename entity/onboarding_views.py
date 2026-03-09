from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from entity.onboarding_serializers import EntityOnboardingCreateSerializer, EntityOnboardingResponseSerializer
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
