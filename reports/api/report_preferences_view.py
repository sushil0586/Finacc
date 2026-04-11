from __future__ import annotations

from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from reports.serializers.report_preferences_serializer import ReportPreferenceSerializer
from reports.services.report_preferences import (
    get_user_report_preference,
    list_user_report_preferences,
    upsert_user_report_preference,
)
from rbac.services import EffectivePermissionService


class ReportPreferenceAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _resolve_entity(self, request, entity_id):
        entity = EffectivePermissionService.entity_for_user(request.user, entity_id)
        if not entity:
            raise PermissionDenied("You do not have access to this entity.")
        return entity

    def get(self, request):
        entity_id = request.query_params.get("entity")
        report_code = request.query_params.get("report_code")
        if not entity_id:
            raise PermissionDenied("Entity is required.")
        self._resolve_entity(request, entity_id)
        if report_code:
            preference = get_user_report_preference(user=request.user, entity_id=entity_id, report_code=report_code)
            if not preference:
                return Response({"entity": int(entity_id), "report_code": report_code, "payload": {}})
            return Response(
                {
                    "entity": int(entity_id),
                    "report_code": report_code,
                    "payload": preference.payload or {},
                    "updated_at": preference.updated_at,
                }
            )
        return Response(
            {
                "entity": int(entity_id),
                "results": list_user_report_preferences(user=request.user, entity_id=entity_id),
            }
        )

    def patch(self, request):
        serializer = ReportPreferenceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entity = self._resolve_entity(request, serializer.validated_data["entity"])
        preference = upsert_user_report_preference(
            user=request.user,
            entity=entity,
            report_code=serializer.validated_data["report_code"],
            payload=serializer.validated_data.get("payload") or {},
        )
        return Response(
            {
                "entity": entity.id,
                "report_code": preference.report_code,
                "payload": preference.payload or {},
                "updated_at": preference.updated_at,
            }
        )

    def put(self, request):
        return self.patch(request)
