from __future__ import annotations

import logging

from django.core.exceptions import ValidationError
from rest_framework import permissions, status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import APIView

from core.entitlements import ScopedEntitlementMixin
from reports.api.report_permissions import assert_any_report_permission
from reports.gst_portal.services import GstPortalService
from reports.gst_portal.whitebox import WhiteboxConfigurationError, WhiteboxRequestError
from subscriptions.services import SubscriptionLimitCodes, SubscriptionService


logger = logging.getLogger(__name__)


class GstPortalScopedAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL
    service_class = GstPortalService

    def _entity_id(self, payload):
        value = payload.get("entity")
        if value in (None, "", 0, "0"):
            raise ValueError("entity is required.")
        return int(value)

    def _entityfinid_id(self, payload):
        value = payload.get("entityfinid")
        if value in (None, "", 0, "0"):
            return None
        return int(value)

    def _subentity_id(self, payload):
        value = payload.get("subentity")
        if value in (None, "", 0, "0"):
            return None
        return int(value)

    def _enforce(self, request, *, payload, file_permission=False):
        entity_id = self._entity_id(payload)
        entityfinid_id = self._entityfinid_id(payload)
        subentity_id = self._subentity_id(payload)
        self.enforce_scope(request, entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id)
        permissions_required = ("reports.gst.file",) if file_permission else ("reports.gst.view", "reports.gstr1report.view", "reports.gstr3b.view")
        assert_any_report_permission(
            user=request.user,
            entity_id=entity_id,
            required_permissions=permissions_required,
            message="You do not have permission to use GST portal filing.",
        )
        return entity_id, entityfinid_id, subentity_id


class GstPortalFilingPrepareAPIView(GstPortalScopedAPIView):
    def post(self, request):
        payload = request.data or {}
        try:
            self._enforce(request, payload=payload)
            return_type = payload.get("return_type")
            result = self.service_class().prepare(return_type=return_type, params=payload, user=request.user)
        except ValidationError as exc:
            return Response(exc.message_dict if hasattr(exc, "message_dict") else {"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except LookupError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except APIException:
            raise
        except Exception as exc:
            return _unexpected_error_response(exc, action="prepare GST portal filing")
        return Response(result, status=status.HTTP_201_CREATED)


class GstPortalFilingStatusAPIView(GstPortalScopedAPIView):
    def get(self, request):
        try:
            entity_id, entityfinid_id, _ = self._enforce(request, payload=request.query_params)
            filing_id = _optional_int(request.query_params.get("filing_id"), "filing_id")
            limit = _optional_int(request.query_params.get("limit"), "limit") or 10
            result = self.service_class().status(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                return_type=request.query_params.get("return_type"),
                filing_id=filing_id,
                limit=limit,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except LookupError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except APIException:
            raise
        except Exception as exc:
            return _unexpected_error_response(exc, action="read GST portal filing status")
        return Response(result, status=status.HTTP_200_OK)


class GstPortalProfileAPIView(GstPortalScopedAPIView):
    def get(self, request):
        try:
            entity_id, _, subentity_id = self._enforce(request, payload=request.query_params)
            result = self.service_class().profile(entity_id=entity_id, subentity_id=subentity_id)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except LookupError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except APIException:
            raise
        except Exception as exc:
            return _unexpected_error_response(exc, action="read GST portal profile")
        return Response(result, status=status.HTTP_200_OK)

    def post(self, request):
        payload = request.data or {}
        try:
            entity_id, _, subentity_id = self._enforce(request, payload=payload, file_permission=True)
            result = self.service_class().save_profile(
                entity_id=entity_id,
                subentity_id=subentity_id,
                gst_username=str(payload.get("gst_username") or "").strip(),
                registered_mobile_masked=str(payload.get("registered_mobile_masked") or payload.get("phone") or "").strip(),
                registered_email_masked=str(payload.get("registered_email_masked") or "").strip(),
                notes=str(payload.get("notes") or "").strip(),
                user=request.user,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except LookupError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except APIException:
            raise
        except Exception as exc:
            return _unexpected_error_response(exc, action="save GST portal profile")
        return Response(result, status=status.HTTP_200_OK)

    def put(self, request):
        return self.post(request)


class GstPortalOtpRequestAPIView(GstPortalScopedAPIView):
    def post(self, request):
        payload = request.data or {}
        try:
            entity_id, _, subentity_id = self._enforce(request, payload=payload, file_permission=True)
            email = str(payload.get("email") or "").strip()
            gst_username = str(payload.get("gst_username") or "").strip()
            ip_address = str(payload.get("ip_address") or request.META.get("REMOTE_ADDR") or "").strip()
            result = self.service_class().request_otp(
                entity_id=entity_id,
                subentity_id=subentity_id,
                email=email,
                gst_username=gst_username,
                ip_address=ip_address,
                user=request.user,
            )
        except (ValueError, WhiteboxConfigurationError, WhiteboxRequestError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except LookupError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except APIException:
            raise
        except Exception as exc:
            return _unexpected_error_response(exc, action="request GST portal OTP")
        return Response(result, status=status.HTTP_201_CREATED)


class GstPortalOtpVerifyAPIView(GstPortalScopedAPIView):
    def post(self, request):
        payload = request.data or {}
        try:
            entity_id, _, _ = self._enforce(request, payload=payload, file_permission=True)
            session_id = _required_int(payload.get("session_id"), "session_id")
            otp = _required_string(payload.get("otp"), "otp")
            result = self.service_class().verify_otp(
                session_id=session_id,
                entity_id=entity_id,
                otp=otp,
                user=request.user,
            )
        except (ValueError, WhiteboxConfigurationError, WhiteboxRequestError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except LookupError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except APIException:
            raise
        except Exception as exc:
            return _unexpected_error_response(exc, action="verify GST portal OTP")
        return Response(result, status=status.HTTP_200_OK)


class GstPortalFilingSaveAPIView(GstPortalScopedAPIView):
    def post(self, request):
        payload = request.data or {}
        try:
            entity_id, _, _ = self._enforce(request, payload=payload, file_permission=True)
            filing_id = _required_int(payload.get("filing_id"), "filing_id")
            email = str(payload.get("email") or "").strip()
            gst_username = str(payload.get("gst_username") or "").strip()
            ip_address = str(payload.get("ip_address") or request.META.get("REMOTE_ADDR") or "").strip()
            result = self.service_class().save_to_portal(
                filing_id=filing_id,
                entity_id=entity_id,
                email=email,
                gst_username=gst_username,
                ip_address=ip_address,
                user=request.user,
            )
        except (ValueError, WhiteboxConfigurationError, WhiteboxRequestError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except LookupError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except APIException:
            raise
        except Exception as exc:
            return _unexpected_error_response(exc, action="save GST portal filing")
        return Response(result, status=status.HTTP_200_OK)


class GstPortalFilingPortalSummaryAPIView(GstPortalScopedAPIView):
    def post(self, request):
        payload = request.data or {}
        try:
            entity_id, _, _ = self._enforce(request, payload=payload, file_permission=True)
            filing_id = _required_int(payload.get("filing_id"), "filing_id")
            email = str(payload.get("email") or "").strip()
            gst_username = str(payload.get("gst_username") or "").strip()
            ip_address = str(payload.get("ip_address") or request.META.get("REMOTE_ADDR") or "").strip()
            result = self.service_class().fetch_portal_summary(
                filing_id=filing_id,
                entity_id=entity_id,
                email=email,
                gst_username=gst_username,
                ip_address=ip_address,
                summary_type=str(payload.get("summary_type") or "").strip(),
                user=request.user,
            )
        except (ValueError, WhiteboxConfigurationError, WhiteboxRequestError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except LookupError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except APIException:
            raise
        except Exception as exc:
            return _unexpected_error_response(exc, action="fetch GST portal summary")
        return Response(result, status=status.HTTP_200_OK)


class GstPortalFilingProceedAPIView(GstPortalScopedAPIView):
    def post(self, request):
        payload = request.data or {}
        try:
            entity_id, _, _ = self._enforce(request, payload=payload, file_permission=True)
            filing_id = _required_int(payload.get("filing_id"), "filing_id")
            email = str(payload.get("email") or "").strip()
            gst_username = str(payload.get("gst_username") or "").strip()
            ip_address = str(payload.get("ip_address") or request.META.get("REMOTE_ADDR") or "").strip()
            result = self.service_class().proceed_to_file(
                filing_id=filing_id,
                entity_id=entity_id,
                email=email,
                gst_username=gst_username,
                ip_address=ip_address,
                user=request.user,
            )
        except (ValueError, WhiteboxConfigurationError, WhiteboxRequestError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except LookupError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except APIException:
            raise
        except Exception as exc:
            return _unexpected_error_response(exc, action="proceed GST portal filing")
        return Response(result, status=status.HTTP_200_OK)


class GstPortalFilingRequestEvcAPIView(GstPortalScopedAPIView):
    def post(self, request):
        payload = request.data or {}
        try:
            entity_id, _, _ = self._enforce(request, payload=payload, file_permission=True)
            filing_id = _required_int(payload.get("filing_id"), "filing_id")
            email = str(payload.get("email") or "").strip()
            gst_username = str(payload.get("gst_username") or "").strip()
            pan = _required_string(payload.get("pan"), "pan").upper()
            ip_address = str(payload.get("ip_address") or request.META.get("REMOTE_ADDR") or "").strip()
            result = self.service_class().request_evc(
                filing_id=filing_id,
                entity_id=entity_id,
                email=email,
                gst_username=gst_username,
                ip_address=ip_address,
                pan=pan,
                form_type=str(payload.get("form_type") or "").strip(),
                user=request.user,
            )
        except (ValueError, WhiteboxConfigurationError, WhiteboxRequestError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except LookupError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except APIException:
            raise
        except Exception as exc:
            return _unexpected_error_response(exc, action="request GST portal EVC")
        return Response(result, status=status.HTTP_200_OK)


class GstPortalFilingEvcFileAPIView(GstPortalScopedAPIView):
    def post(self, request):
        payload = request.data or {}
        try:
            entity_id, _, _ = self._enforce(request, payload=payload, file_permission=True)
            filing_id = _required_int(payload.get("filing_id"), "filing_id")
            email = str(payload.get("email") or "").strip()
            gst_username = str(payload.get("gst_username") or "").strip()
            pan = _required_string(payload.get("pan"), "pan").upper()
            evc_otp = _required_string(payload.get("evc_otp") or payload.get("otp"), "evc_otp")
            ip_address = str(payload.get("ip_address") or request.META.get("REMOTE_ADDR") or "").strip()
            result = self.service_class().file_with_evc(
                filing_id=filing_id,
                entity_id=entity_id,
                email=email,
                gst_username=gst_username,
                ip_address=ip_address,
                pan=pan,
                evc_otp=evc_otp,
                user=request.user,
            )
        except (ValueError, WhiteboxConfigurationError, WhiteboxRequestError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except LookupError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except APIException:
            raise
        except Exception as exc:
            return _unexpected_error_response(exc, action="file GST portal filing with EVC")
        return Response(result, status=status.HTTP_200_OK)


class GstPortalFilingPollStatusAPIView(GstPortalScopedAPIView):
    def post(self, request):
        payload = request.data or {}
        try:
            entity_id, _, _ = self._enforce(request, payload=payload, file_permission=True)
            filing_id = _required_int(payload.get("filing_id"), "filing_id")
            email = str(payload.get("email") or "").strip()
            gst_username = str(payload.get("gst_username") or "").strip()
            ip_address = str(payload.get("ip_address") or request.META.get("REMOTE_ADDR") or "").strip()
            result = self.service_class().poll_return_status(
                filing_id=filing_id,
                entity_id=entity_id,
                email=email,
                gst_username=gst_username,
                ip_address=ip_address,
                ref_id=str(payload.get("ref_id") or "").strip(),
                user=request.user,
            )
        except (ValueError, WhiteboxConfigurationError, WhiteboxRequestError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except LookupError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except APIException:
            raise
        except Exception as exc:
            return _unexpected_error_response(exc, action="poll GST portal filing status")
        return Response(result, status=status.HTTP_200_OK)


def _required_string(value, field: str) -> str:
    value = str(value or "").strip()
    if not value:
        raise ValueError(f"{field} is required.")
    return value


def _required_int(value, field: str) -> int:
    parsed = _optional_int(value, field)
    if parsed is None:
        raise ValueError(f"{field} is required.")
    return parsed


def _optional_int(value, field: str) -> int | None:
    if value in (None, "", 0, "0"):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer.") from exc
    if parsed <= 0:
        raise ValueError(f"{field} must be a positive integer.")
    return parsed


def _unexpected_error_response(exc: Exception, *, action: str) -> Response:
    logger.exception("Unexpected error while attempting to %s.", action)
    return Response(
        {"detail": f"Unable to {action}. Please check backend logs for details."},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
