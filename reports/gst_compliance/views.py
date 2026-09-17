from __future__ import annotations

from django.core.exceptions import ValidationError
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from core.entitlements import ScopedEntitlementMixin
from reports.api.report_permissions import assert_any_report_permission
from reports.gst_compliance.contracts import parse_gst_compliance_scope
from reports.gst_compliance.services import GstComplianceSnapshotService
from subscriptions.services import SubscriptionLimitCodes, SubscriptionService


GST_COMPLIANCE_CENTER_VIEW_PERMISSIONS = (
    "reports.gst.view",
    "reports.gstr1report.view",
    "reports.gstr3b.view",
    "reports.gstr9.view",
    "reports.gstr1_gstr3b_reconciliation.view",
    "reports.gst_exception_dashboard.view",
    "gst.reconciliation.view",
    "reports.financial_hub.gst_tds_compliance_center.view",
    "reports.financial_hub.tcs_compliance_center.view",
)


class GstComplianceSnapshotAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL
    service_class = GstComplianceSnapshotService

    def get(self, request):
        try:
            scope = parse_gst_compliance_scope(request.query_params)
        except ValidationError as exc:
            return Response(exc.message_dict, status=400)

        self.enforce_scope(
            request,
            entity_id=scope.entity_id,
            entityfinid_id=scope.entityfinid_id,
            subentity_id=scope.subentity_id,
        )
        permission_codes = assert_any_report_permission(
            user=request.user,
            entity_id=scope.entity_id,
            required_permissions=GST_COMPLIANCE_CENTER_VIEW_PERMISSIONS,
            message="You do not have permission to access the GST Compliance Center.",
        )
        return Response(self.service_class().build(scope=scope, permission_codes=permission_codes))
