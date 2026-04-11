from __future__ import annotations

from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from .registry import DASHBOARD_PAGE_PERMISSION
from .serializers import DashboardHomeScopeSerializer
from .services import build_dashboard_home_contract


class DashboardHomeMetaAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = DashboardHomeScopeSerializer

    def get_scope(self, request):
        serializer = self.serializer_class(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def get(self, request):
        scope = self.get_scope(request)
        contract = build_dashboard_home_contract(request=request, scope=scope)
        if not contract:
            raise PermissionDenied("You do not have access to this entity.")
        if not contract["permissions"]["page"]["granted"]:
            raise PermissionDenied(f"You do not have permission to access {DASHBOARD_PAGE_PERMISSION}.")
        return Response(contract)

