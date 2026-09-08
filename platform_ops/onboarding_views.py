from rest_framework.response import Response

from .discovery_views import PlatformReadAPIView
from .models import PlatformAuditEvent
from .onboarding import PlatformOnboardingValidationSerializer, PlatformOnboardingValidationService
from .services import PlatformAuditService


class PlatformOnboardingValidationAPIView(PlatformReadAPIView):
    required_platform_permissions = ("platform.customer.create", "platform.entity.onboard")

    def post(self, request):
        serializer = PlatformOnboardingValidationSerializer(data=request.data)
        if not serializer.is_valid():
            PlatformAuditService.log(
                actor=request.user,
                event_type="platform.onboarding.validation",
                outcome=PlatformAuditEvent.Outcome.FAILED,
                request=request,
                permission_code="platform.entity.onboard",
                details={"validation_errors": serializer.errors},
            )
            return Response(
                {"valid": False, "code": "invalid_onboarding_payload", "errors": serializer.errors},
                status=400,
            )

        result = PlatformOnboardingValidationService.build_result(serializer.validated_data)
        PlatformAuditService.log(
            actor=request.user,
            event_type="platform.onboarding.validation",
            outcome=PlatformAuditEvent.Outcome.SUCCESS,
            request=request,
            permission_code="platform.entity.onboard",
            details={
                "valid": result["valid"],
                "blocking_codes": [row["code"] for row in result["blocking_errors"]],
                "warning_codes": [row["code"] for row in result["warnings"]],
            },
        )
        return Response(result)
