from __future__ import annotations

from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from reports.api.report_permissions import assert_any_report_permission
from reports.services.payables_settings import get_payables_settings_response, save_payables_settings
from rbac.services import EffectivePermissionService


class PayablesSettingsAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    required_permissions = (
        "reports.payables.settings.view",
        "reports.payables.view",
    )

    def _resolve_entity(self, request, entity_id):
        entity = EffectivePermissionService.entity_for_user(request.user, entity_id)
        if not entity:
            raise PermissionDenied("You do not have access to this entity.")
        return entity

    def get(self, request):
        entity_id = request.query_params.get("entity")
        if not entity_id:
            raise PermissionDenied("Entity is required.")
        self._resolve_entity(request, entity_id)
        assert_any_report_permission(
            user=request.user,
            entity_id=int(entity_id),
            required_permissions=self.required_permissions,
            message="You do not have permission to view payables settings.",
        )
        return Response(get_payables_settings_response(user=request.user, entity_id=entity_id))

    def patch(self, request):
        entity_id = request.data.get("entity")
        if not entity_id:
            raise PermissionDenied("Entity is required.")
        entity = self._resolve_entity(request, entity_id)
        assert_any_report_permission(
            user=request.user,
            entity_id=int(entity_id),
            required_permissions=self.required_permissions,
            message="You do not have permission to update payables settings.",
        )
        payload = request.data.get("payload") or {}
        return Response(save_payables_settings(user=request.user, entity=entity, payload=payload))

    def put(self, request):
        return self.patch(request)
