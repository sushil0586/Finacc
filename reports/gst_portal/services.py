from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from reports.gstr1.exporters.gstn_json_export import Gstr1GstnJsonExportService
from reports.gstr1.selectors.queries import apply_smart_filters
from reports.gstr1.services.report import Gstr1ReportService
from reports.gstr3b.services import Gstr3bSummaryService
from reports.gst_portal.payloads import Gstr1WhiteboxPayloadBuilder, Gstr3bWhiteboxPayloadBuilder, PreparedWhiteboxPayload, ret_period_from_scope
from reports.gst_portal.scope import GstPortalRegistrationScope, resolve_gst_portal_registration_scope
from reports.gst_portal.whitebox import WhiteboxConfigurationError, WhiteboxContext, WhiteboxGstClient, WhiteboxRequestError, redacted_whitebox_snapshot
from reports.models import GstPortalFilingRun, GstPortalProfile, GstPortalSession


class GstPortalService:
    provider = "whitebox"

    def __init__(self, *, client: WhiteboxGstClient | None = None):
        self.client = client or WhiteboxGstClient()

    def preview(self, *, return_type: str, params) -> dict:
        return_type = self._normalize_return_type(return_type)
        if return_type == GstPortalFilingRun.ReturnType.GSTR1:
            scope, registration_scope, prepared = self._prepare_gstr1(params)
        elif return_type == GstPortalFilingRun.ReturnType.GSTR3B:
            scope, registration_scope, prepared = self._prepare_gstr3b(params)
        else:
            raise ValueError(f"Unsupported GST portal return type: {return_type}")
        return self._prepared_payload(
            prepared=prepared,
            scope=scope,
            registration_scope=registration_scope,
        )

    def prepare(self, *, return_type: str, params, user=None) -> dict:
        return_type = self._normalize_return_type(return_type)
        if return_type == GstPortalFilingRun.ReturnType.GSTR1:
            scope, registration_scope, prepared = self._prepare_gstr1(params)
        elif return_type == GstPortalFilingRun.ReturnType.GSTR3B:
            scope, registration_scope, prepared = self._prepare_gstr3b(params)
        else:
            raise ValueError(f"Unsupported GST portal return type: {return_type}")

        run = GstPortalFilingRun.objects.create(
            provider=self.provider,
            return_type=return_type,
            entity_id=scope.entity_id,
            entityfinid_id=scope.entityfinid_id,
            subentity_id=registration_scope.filing_subentity_id,
            gstin=prepared.gstin,
            state_cd=registration_scope.state_cd,
            ret_period=prepared.ret_period,
            status=GstPortalFilingRun.Status.PREPARED,
            stage="prepared",
            scope_payload=self._scope_payload(scope=scope, registration_scope=registration_scope),
            payload=prepared.payload,
            warnings=[*registration_scope.warnings, *prepared.warnings],
            prepared_by=user if getattr(user, "is_authenticated", False) else None,
            prepared_at=timezone.now(),
        )
        return self.serialize_filing_run(run)

    def status(self, *, entity_id: int, entityfinid_id: int | None = None, return_type: str | None = None, filing_id: int | None = None, limit: int = 10) -> dict:
        qs = GstPortalFilingRun.objects.filter(entity_id=entity_id)
        if entityfinid_id:
            qs = qs.filter(entityfinid_id=entityfinid_id)
        if return_type:
            qs = qs.filter(return_type=self._normalize_return_type(return_type))
        if filing_id:
            run = qs.filter(id=filing_id).first()
            if not run:
                raise LookupError(f"GST portal filing run not found for filing_id={filing_id}.")
            return self.serialize_filing_run(run)
        results = [self.serialize_filing_run(row) for row in qs.order_by("-id")[:limit]]
        return {"count": len(results), "results": results}

    def profile(self, *, entity_id: int, subentity_id: int | None = None) -> dict:
        registration_scope = resolve_gst_portal_registration_scope(entity_id=entity_id, subentity_id=subentity_id)
        profile = self._get_profile(entity_id=entity_id, gstin=registration_scope.gstin)
        return self._profile_payload(registration_scope=registration_scope, profile=profile, entity_id=entity_id)

    def save_profile(
        self,
        *,
        entity_id: int,
        subentity_id: int | None = None,
        gst_username: str = "",
        registered_mobile_masked: str = "",
        registered_email_masked: str = "",
        notes: str = "",
        user=None,
    ) -> dict:
        registration_scope = resolve_gst_portal_registration_scope(entity_id=entity_id, subentity_id=subentity_id)
        gst_username = str(gst_username or "").strip()
        if not gst_username:
            raise ValueError("GST portal username is required.")
        profile, _ = GstPortalProfile.objects.update_or_create(
            provider=self.provider,
            entity_id=entity_id,
            gstin=registration_scope.gstin,
            defaults={
                "state_cd": registration_scope.state_cd,
                "gst_username": gst_username,
                "registered_mobile_masked": str(registered_mobile_masked or "").strip(),
                "registered_email_masked": str(registered_email_masked or "").strip().lower(),
                "notes": str(notes or "").strip(),
                "updated_by": user if getattr(user, "is_authenticated", False) else None,
                "isactive": True,
            },
        )
        return self._profile_payload(registration_scope=registration_scope, profile=profile, entity_id=entity_id)

    def request_otp(self, *, entity_id: int, subentity_id: int | None, email: str = "", gst_username: str = "", ip_address: str = "", user=None) -> dict:
        registration_scope = resolve_gst_portal_registration_scope(entity_id=entity_id, subentity_id=subentity_id)
        email, gst_username, ip_address = self._resolve_context_inputs(
            email=email,
            gst_username=gst_username,
            ip_address=ip_address,
            entity_id=entity_id,
            gstin=registration_scope.gstin,
        )
        context = WhiteboxContext(
            email=email,
            gstin=registration_scope.gstin,
            gst_username=gst_username,
            state_cd=registration_scope.state_cd,
            ip_address=ip_address,
        )
        session = GstPortalSession.objects.create(
            provider=self.provider,
            entity_id=entity_id,
            subentity_id=registration_scope.filing_subentity_id,
            gstin=registration_scope.gstin,
            state_cd=registration_scope.state_cd,
            gst_username=gst_username,
            email=email,
            ip_address=ip_address,
            status=GstPortalSession.Status.OTP_REQUESTED,
            requested_by=user if getattr(user, "is_authenticated", False) else None,
            otp_requested_at=timezone.now(),
        )
        try:
            response = self.client.request_otp(context=context)
        except (WhiteboxConfigurationError, WhiteboxRequestError) as exc:
            session.status = GstPortalSession.Status.FAILED
            session.last_error = str(exc)
            if isinstance(exc, WhiteboxRequestError):
                session.last_response = redacted_whitebox_snapshot(exc.response_payload)
            session.save(update_fields=["status", "last_error", "last_response", "updated_at"])
            raise
        session.txn = response.txn
        session.last_response = redacted_whitebox_snapshot(response.payload)
        session.save(update_fields=["txn", "last_response", "updated_at"])
        self._touch_profile_last_used(entity_id=entity_id, gstin=registration_scope.gstin)
        return self.serialize_session(session)

    def verify_otp(self, *, session_id: int, entity_id: int, otp: str, user=None) -> dict:
        session = GstPortalSession.objects.filter(id=session_id, entity_id=entity_id).first()
        if not session:
            raise LookupError(f"GST portal session not found for session_id={session_id}.")
        context = WhiteboxContext(
            email=session.email,
            gstin=session.gstin,
            gst_username=session.gst_username,
            state_cd=session.state_cd,
            ip_address=session.ip_address,
            txn=session.txn,
        )
        try:
            response = self.client.auth_token(context=context, otp=otp)
        except (WhiteboxConfigurationError, WhiteboxRequestError) as exc:
            session.status = GstPortalSession.Status.FAILED
            session.last_error = str(exc)
            if isinstance(exc, WhiteboxRequestError):
                session.last_response = redacted_whitebox_snapshot(exc.response_payload)
            session.save(update_fields=["status", "last_error", "last_response", "updated_at"])
            raise
        session.status = GstPortalSession.Status.AUTHENTICATED
        session.txn = response.txn
        session.last_response = redacted_whitebox_snapshot(response.payload)
        session.authenticated_by = user if getattr(user, "is_authenticated", False) else None
        session.authenticated_at = timezone.now()
        session.save(update_fields=["status", "txn", "last_response", "authenticated_by", "authenticated_at", "updated_at"])
        return self.serialize_session(session)

    def save_to_portal(self, *, filing_id: int, entity_id: int, email: str = "", gst_username: str = "", ip_address: str = "", user=None) -> dict:
        run = GstPortalFilingRun.objects.filter(id=filing_id, entity_id=entity_id).first()
        if not run:
            raise LookupError(f"GST portal filing run not found for filing_id={filing_id}.")
        if run.status != GstPortalFilingRun.Status.PREPARED:
            raise ValueError("Only prepared GST portal filing runs can be saved to GSTN.")
        context = self._context_for_run(run, email=email, gst_username=gst_username, ip_address=ip_address)
        try:
            self.client.ensure_configured()
            self._assert_live_write_enabled(run.return_type, "save")
            if run.return_type == GstPortalFilingRun.ReturnType.GSTR1:
                response = self.client.save_gstr1(context=context, ret_period=run.ret_period, payload=run.payload)
            elif run.return_type == GstPortalFilingRun.ReturnType.GSTR3B:
                response = self.client.save_gstr3b(context=context, ret_period=run.ret_period, payload=run.payload)
            else:
                raise ValueError(f"Unsupported GST portal return type: {run.return_type}")
        except (WhiteboxConfigurationError, WhiteboxRequestError) as exc:
            self._mark_failed(run, exc)
            raise
        run.status = GstPortalFilingRun.Status.SAVED
        run.stage = "saved"
        run.txn = response.txn
        run.portal_response = redacted_whitebox_snapshot(response.payload)
        run.submitted_by = user if getattr(user, "is_authenticated", False) else None
        run.save(update_fields=["status", "stage", "txn", "portal_response", "submitted_by", "updated_at"])
        return self.serialize_filing_run(run)

    def fetch_portal_summary(self, *, filing_id: int, entity_id: int, email: str = "", gst_username: str = "", ip_address: str = "", summary_type: str = "", user=None) -> dict:
        run = self._get_filing_run(filing_id=filing_id, entity_id=entity_id)
        context = self._context_for_run(run, email=email, gst_username=gst_username, ip_address=ip_address)
        try:
            if run.return_type == GstPortalFilingRun.ReturnType.GSTR1:
                response = self.client.gstr1_summary(context=context, ret_period=run.ret_period, summary_type=summary_type)
            elif run.return_type == GstPortalFilingRun.ReturnType.GSTR3B:
                response = self.client.gstr3b_summary(context=context, ret_period=run.ret_period)
            else:
                raise ValueError(f"Unsupported GST portal return type: {run.return_type}")
        except (WhiteboxConfigurationError, WhiteboxRequestError) as exc:
            self._mark_failed(run, exc)
            raise
        portal_response = dict(run.portal_response or {})
        portal_response["summary"] = redacted_whitebox_snapshot(response.payload)
        self._update_run_after_portal_call(
            run,
            status=GstPortalFilingRun.Status.SUMMARY_FETCHED,
            stage="summary_fetched",
            txn=response.txn,
            portal_response=portal_response,
            user=user,
        )
        return self.serialize_filing_run(run)

    def proceed_to_file(self, *, filing_id: int, entity_id: int, email: str = "", gst_username: str = "", ip_address: str = "", user=None) -> dict:
        run = self._get_filing_run(filing_id=filing_id, entity_id=entity_id)
        if run.status not in {
            GstPortalFilingRun.Status.SAVED,
            GstPortalFilingRun.Status.SUMMARY_FETCHED,
        }:
            raise ValueError("GST portal filing run must be saved before proceed-to-file.")
        context = self._context_for_run(run, email=email, gst_username=gst_username, ip_address=ip_address)
        try:
            response = self.client.proceed_to_file(
                context=context,
                ret_period=run.ret_period,
                return_type=run.return_type,
                is_nil=_is_nil_filing_payload(run.payload),
            )
        except (WhiteboxConfigurationError, WhiteboxRequestError) as exc:
            self._mark_failed(run, exc)
            raise
        portal_response = dict(run.portal_response or {})
        portal_response["proceed_to_file"] = redacted_whitebox_snapshot(response.payload)
        self._update_run_after_portal_call(
            run,
            status=GstPortalFilingRun.Status.PROCEEDED,
            stage="proceeded_to_file",
            txn=response.txn,
            portal_response=portal_response,
            user=user,
        )
        return self.serialize_filing_run(run)

    def request_evc(self, *, filing_id: int, entity_id: int, email: str = "", gst_username: str = "", ip_address: str = "", pan: str = "", form_type: str = "", user=None) -> dict:
        run = self._get_filing_run(filing_id=filing_id, entity_id=entity_id)
        if run.return_type == GstPortalFilingRun.ReturnType.GSTR1 and run.status != GstPortalFilingRun.Status.PROCEEDED:
            raise ValueError("GSTR-1 must be proceeded to file before requesting EVC.")
        context = self._context_for_run(run, email=email, gst_username=gst_username, ip_address=ip_address)
        try:
            response = self.client.request_evc_otp(
                context=context,
                pan=pan,
                form_type=form_type or self._default_form_type(run.return_type),
            )
        except (WhiteboxConfigurationError, WhiteboxRequestError) as exc:
            self._mark_failed(run, exc)
            raise
        portal_response = dict(run.portal_response or {})
        portal_response["evc_request"] = redacted_whitebox_snapshot(response.payload)
        self._update_run_after_portal_call(
            run,
            status=GstPortalFilingRun.Status.EVC_REQUESTED,
            stage="evc_requested",
            txn=response.txn,
            portal_response=portal_response,
            user=user,
        )
        return self.serialize_filing_run(run)

    def file_with_evc(self, *, filing_id: int, entity_id: int, email: str = "", gst_username: str = "", ip_address: str = "", pan: str = "", evc_otp: str = "", user=None) -> dict:
        run = self._get_filing_run(filing_id=filing_id, entity_id=entity_id)
        if run.status not in {
            GstPortalFilingRun.Status.SAVED,
            GstPortalFilingRun.Status.SUMMARY_FETCHED,
            GstPortalFilingRun.Status.PROCEEDED,
            GstPortalFilingRun.Status.EVC_REQUESTED,
            GstPortalFilingRun.Status.OFFSET,
        }:
            raise ValueError("GST portal filing run must be saved or EVC-ready before filing.")
        context = self._context_for_run(run, email=email, gst_username=gst_username, ip_address=ip_address)
        try:
            self.client.ensure_configured()
            self._assert_live_write_enabled(run.return_type, "file")
            if run.return_type == GstPortalFilingRun.ReturnType.GSTR1:
                response = self.client.evc_file_gstr1(context=context, ret_period=run.ret_period, pan=pan, evc_otp=evc_otp)
            elif run.return_type == GstPortalFilingRun.ReturnType.GSTR3B:
                response = self.client.evc_file_gstr3b(context=context, ret_period=run.ret_period, pan=pan, evc_otp=evc_otp)
            else:
                raise ValueError(f"Unsupported GST portal return type: {run.return_type}")
        except (WhiteboxConfigurationError, WhiteboxRequestError) as exc:
            self._mark_failed(run, exc)
            raise
        portal_response = dict(run.portal_response or {})
        portal_response["file"] = redacted_whitebox_snapshot(response.payload)
        run.portal_reference = _extract_portal_reference(response.payload)
        self._update_run_after_portal_call(
            run,
            status=GstPortalFilingRun.Status.FILED,
            stage="filed",
            txn=response.txn,
            portal_response=portal_response,
            user=user,
            submitted=True,
            update_fields_extra=["portal_reference"],
        )
        return self.serialize_filing_run(run)

    def poll_return_status(self, *, filing_id: int, entity_id: int, email: str = "", gst_username: str = "", ip_address: str = "", ref_id: str = "", user=None) -> dict:
        run = self._get_filing_run(filing_id=filing_id, entity_id=entity_id)
        reference = (ref_id or run.portal_reference or _extract_portal_reference(run.portal_response)).strip()
        if not reference:
            raise ValueError("ref_id is required until the portal filing reference is available.")
        context = self._context_for_run(run, email=email, gst_username=gst_username, ip_address=ip_address)
        try:
            response = self.client.return_status(
                context=context,
                ret_period=run.ret_period,
                ref_id=reference,
                return_type=run.return_type.upper(),
            )
        except (WhiteboxConfigurationError, WhiteboxRequestError) as exc:
            self._mark_failed(run, exc)
            raise
        portal_response = dict(run.portal_response or {})
        portal_response["status_poll"] = redacted_whitebox_snapshot(response.payload)
        run.portal_reference = reference
        self._update_run_after_portal_call(
            run,
            status=run.status,
            stage="status_polled",
            txn=response.txn,
            portal_response=portal_response,
            user=user,
            update_fields_extra=["portal_reference"],
        )
        return self.serialize_filing_run(run)

    def _prepare_gstr1(self, params) -> tuple[Any, GstPortalRegistrationScope, PreparedWhiteboxPayload]:
        service = Gstr1ReportService()
        scope = service.build_scope(params)
        if not scope.entityfinid_id:
            raise ValidationError({"entityfinid": ["entityfinid is required for GST portal filing."]})
        registration_scope = resolve_gst_portal_registration_scope(entity_id=scope.entity_id, subentity_id=scope.subentity_id)
        smart_filters = service.build_smart_filters(params)
        filtered_qs = self._gstr1_portal_queryset(service=service, scope=scope, smart_filters=smart_filters, registration_scope=registration_scope)
        filing_prep_payload = Gstr1GstnJsonExportService().build(scope=replace(scope, subentity_id=registration_scope.filing_subentity_id), base_queryset=filtered_qs)
        prepared = Gstr1WhiteboxPayloadBuilder().build(filing_prep_payload=filing_prep_payload, gstin=registration_scope.gstin)
        return scope, registration_scope, prepared

    def _prepare_gstr3b(self, params) -> tuple[Any, GstPortalRegistrationScope, PreparedWhiteboxPayload]:
        service = Gstr3bSummaryService()
        scope = service.build_scope(params)
        if not scope.entityfinid_id:
            raise ValidationError({"entityfinid": ["entityfinid is required for GST portal filing."]})
        registration_scope = resolve_gst_portal_registration_scope(entity_id=scope.entity_id, subentity_id=scope.subentity_id)
        filing_summary = self._gstr3b_portal_summary(service=service, scope=scope, registration_scope=registration_scope)
        interstate_breakups = self._gstr3b_portal_interstate_breakups(
            service=service,
            scope=scope,
            registration_scope=registration_scope,
        )
        prepared = Gstr3bWhiteboxPayloadBuilder().build(
            summary=filing_summary,
            gstin=registration_scope.gstin,
            ret_period=ret_period_from_scope(scope),
            interstate_breakups=interstate_breakups,
        )
        return scope, registration_scope, prepared

    def _gstr1_portal_queryset(self, *, service: Gstr1ReportService, scope, smart_filters, registration_scope: GstPortalRegistrationScope):
        filing_scope = replace(scope, subentity_id=registration_scope.filing_subentity_id)
        if registration_scope.filing_subentity_id is None and registration_scope.shared_subentity_ids:
            filing_scope = replace(scope, subentity_id=None)
        qs = service.scoped_queryset(filing_scope)
        if registration_scope.shared_subentity_ids:
            qs = qs.filter(subentity_id__in=registration_scope.shared_subentity_ids)
        if registration_scope.gstin:
            qs = qs.filter(seller_gstin__iexact=registration_scope.gstin)
        return apply_smart_filters(qs, smart_filters)

    def _gstr3b_portal_summary(self, *, service: Gstr3bSummaryService, scope, registration_scope: GstPortalRegistrationScope) -> dict:
        if registration_scope.filing_subentity_id is not None:
            return service.build(replace(scope, subentity_id=registration_scope.filing_subentity_id))
        if registration_scope.shared_subentity_ids:
            summaries = [service.build(replace(scope, subentity_id=branch_id)) for branch_id in registration_scope.shared_subentity_ids]
            return _combine_gstr3b_summaries(summaries)
        return service.build(replace(scope, subentity_id=None))

    def _gstr3b_portal_interstate_breakups(self, *, service: Gstr3bSummaryService, scope, registration_scope: GstPortalRegistrationScope) -> dict[str, list[dict]]:
        if registration_scope.filing_subentity_id is not None:
            return service.interstate_breakups(replace(scope, subentity_id=registration_scope.filing_subentity_id))
        if registration_scope.shared_subentity_ids:
            breakups = [service.interstate_breakups(replace(scope, subentity_id=branch_id)) for branch_id in registration_scope.shared_subentity_ids]
            return _combine_gstr3b_breakups(breakups)
        return service.interstate_breakups(replace(scope, subentity_id=None))

    def _mark_failed(self, run: GstPortalFilingRun, exc: Exception):
        run.status = GstPortalFilingRun.Status.FAILED
        run.stage = "failed"
        run.last_error = str(exc)
        if isinstance(exc, WhiteboxRequestError):
            run.portal_response = redacted_whitebox_snapshot(exc.response_payload)
        run.save(update_fields=["status", "stage", "last_error", "portal_response", "updated_at"])

    def _get_filing_run(self, *, filing_id: int, entity_id: int) -> GstPortalFilingRun:
        run = GstPortalFilingRun.objects.filter(id=filing_id, entity_id=entity_id).first()
        if not run:
            raise LookupError(f"GST portal filing run not found for filing_id={filing_id}.")
        return run

    def _context_for_run(self, run: GstPortalFilingRun, *, email: str = "", gst_username: str = "", ip_address: str = "") -> WhiteboxContext:
        email, gst_username, ip_address = self._resolve_context_inputs(
            email=email,
            gst_username=gst_username,
            ip_address=ip_address,
            entity_id=run.entity_id,
            gstin=run.gstin,
        )
        self._touch_profile_last_used(entity_id=run.entity_id, gstin=run.gstin)
        return WhiteboxContext(
            email=email,
            gstin=run.gstin,
            gst_username=gst_username,
            state_cd=run.state_cd,
            ip_address=ip_address,
            txn=run.txn,
        )

    def _resolve_context_inputs(
        self,
        *,
        email: str = "",
        gst_username: str = "",
        ip_address: str = "",
        entity_id: int | None = None,
        gstin: str = "",
    ) -> tuple[str, str, str]:
        profile_username = ""
        if entity_id and gstin:
            profile = self._get_profile(entity_id=entity_id, gstin=gstin)
            profile_username = profile.gst_username if profile else ""
        resolved_email = str(email or getattr(settings, "WHITEBOOKS_CONTACT_EMAIL", "") or getattr(settings, "WHITEBOX_GST_CONTACT_EMAIL", "") or "").strip()
        resolved_gst_username = str(
            gst_username
            or profile_username
            or getattr(settings, "WHITEBOOKS_GST_USERNAME", "")
            or getattr(settings, "WHITEBOX_GST_USERNAME", "")
            or ""
        ).strip()
        resolved_ip_address = str(
            ip_address
            or getattr(settings, "WHITEBOOKS_IP_ADDRESS", "")
            or getattr(settings, "WHITEBOX_GST_IP_ADDRESS", "")
            or getattr(settings, "MASTERGST_IP_ADDRESS", "")
            or ""
        ).strip()
        if not resolved_email:
            raise ValueError("WhiteBooks contact email is not configured in backend settings.")
        if not resolved_gst_username:
            raise ValueError("GST portal username is required for WhiteBooks portal actions.")
        return resolved_email, resolved_gst_username, resolved_ip_address

    def _get_profile(self, *, entity_id: int, gstin: str) -> GstPortalProfile | None:
        return (
            GstPortalProfile.objects.filter(
                provider=self.provider,
                entity_id=entity_id,
                gstin__iexact=str(gstin or "").strip(),
                isactive=True,
            )
            .order_by("-updated_at", "-id")
            .first()
        )

    def _touch_profile_last_used(self, *, entity_id: int, gstin: str):
        profile = self._get_profile(entity_id=entity_id, gstin=gstin)
        if profile:
            profile.last_used_at = timezone.now()
            profile.save(update_fields=["last_used_at", "updated_at"])

    def _update_run_after_portal_call(
        self,
        run: GstPortalFilingRun,
        *,
        status: str,
        stage: str,
        txn: str,
        portal_response: dict,
        user=None,
        submitted: bool = False,
        update_fields_extra: list[str] | None = None,
    ):
        run.status = status
        run.stage = stage
        run.txn = txn
        run.portal_response = portal_response
        run.submitted_by = user if getattr(user, "is_authenticated", False) else run.submitted_by
        update_fields = ["status", "stage", "txn", "portal_response", "submitted_by", "updated_at"]
        if submitted:
            run.submitted_at = timezone.now()
            update_fields.append("submitted_at")
        update_fields.extend(update_fields_extra or [])
        run.save(update_fields=update_fields)

    def _default_form_type(self, return_type: str) -> str:
        if return_type == GstPortalFilingRun.ReturnType.GSTR1:
            return "GSTR1"
        if return_type == GstPortalFilingRun.ReturnType.GSTR3B:
            return "GSTR3B"
        return return_type.upper()

    def _assert_live_write_enabled(self, return_type: str, action: str):
        setting_name = ""
        if return_type == GstPortalFilingRun.ReturnType.GSTR1 and action == "save":
            setting_name = "WHITEBOOKS_ENABLE_GSTR1_SAVE_LIVE"
        elif return_type == GstPortalFilingRun.ReturnType.GSTR1 and action == "file":
            setting_name = "WHITEBOOKS_ENABLE_GSTR1_FILE_LIVE"
        elif return_type == GstPortalFilingRun.ReturnType.GSTR3B and action == "save":
            setting_name = "WHITEBOOKS_ENABLE_GSTR3B_SAVE_LIVE"
        elif return_type == GstPortalFilingRun.ReturnType.GSTR3B and action == "file":
            setting_name = "WHITEBOOKS_ENABLE_GSTR3B_FILE_LIVE"
        if setting_name and not bool(getattr(settings, setting_name, False)):
            raise ValueError(f"WhiteBooks live {action} is disabled. Enable {setting_name} after approval.")

    def serialize_filing_run(self, run: GstPortalFilingRun) -> dict:
        profile = self._get_profile(entity_id=run.entity_id, gstin=run.gstin)
        return {
            "id": run.id,
            "provider": run.provider,
            "return_type": run.return_type,
            "entity": run.entity_id,
            "entityfinid": run.entityfinid_id,
            "subentity": run.subentity_id,
            "gstin": run.gstin,
            "state_cd": run.state_cd,
            "ret_period": run.ret_period,
            "status": run.status,
            "stage": run.stage,
            "txn": run.txn,
            "portal_reference": run.portal_reference,
            "scope": run.scope_payload or {},
            "payload": run.payload or {},
            "warnings": run.warnings or [],
            "portal_response": run.portal_response or {},
            "last_error": run.last_error,
            "portal_profile": self._profile_payload_from_values(
                entity_id=run.entity_id,
                gstin=run.gstin,
                state_cd=run.state_cd,
                profile=profile,
                scope=run.scope_payload or {},
            ),
            "prepared_at": run.prepared_at.isoformat() if run.prepared_at else None,
            "submitted_at": run.submitted_at.isoformat() if run.submitted_at else None,
        }

    def serialize_session(self, session: GstPortalSession) -> dict:
        return {
            "id": session.id,
            "provider": session.provider,
            "entity": session.entity_id,
            "subentity": session.subentity_id,
            "gstin": session.gstin,
            "state_cd": session.state_cd,
            "gst_username": session.gst_username,
            "email": session.email,
            "ip_address": session.ip_address,
            "txn": session.txn,
            "status": session.status,
            "last_response": session.last_response or {},
            "last_error": session.last_error,
            "otp_requested_at": session.otp_requested_at.isoformat() if session.otp_requested_at else None,
            "authenticated_at": session.authenticated_at.isoformat() if session.authenticated_at else None,
        }

    def _prepared_payload(self, *, prepared: PreparedWhiteboxPayload, scope, registration_scope: GstPortalRegistrationScope) -> dict:
        profile = self._get_profile(entity_id=scope.entity_id, gstin=registration_scope.gstin)
        return {
            "return_type": prepared.return_type,
            "gstin": prepared.gstin,
            "ret_period": prepared.ret_period,
            "payload": prepared.payload,
            "warnings": [*registration_scope.warnings, *prepared.warnings],
            "scope": self._scope_payload(scope=scope, registration_scope=registration_scope),
            "portal_profile": self._profile_payload(registration_scope=registration_scope, profile=profile, entity_id=scope.entity_id),
        }

    def _scope_payload(self, *, scope, registration_scope: GstPortalRegistrationScope) -> dict:
        return {
            "requested_subentity": registration_scope.requested_subentity_id,
            "filing_subentity": registration_scope.filing_subentity_id,
            "shared_subentities": list(registration_scope.shared_subentity_ids),
            "registration_source": registration_scope.registration_source,
            "from_date": scope.from_date.isoformat() if scope.from_date else None,
            "to_date": scope.to_date.isoformat() if scope.to_date else None,
        }

    def _profile_payload(
        self,
        *,
        registration_scope: GstPortalRegistrationScope,
        profile: GstPortalProfile | None,
        entity_id: int,
    ) -> dict:
        return self._profile_payload_from_values(
            entity_id=entity_id,
            gstin=registration_scope.gstin,
            state_cd=registration_scope.state_cd,
            profile=profile,
            scope={
                "requested_subentity": registration_scope.requested_subentity_id,
                "filing_subentity": registration_scope.filing_subentity_id,
                "shared_subentities": list(registration_scope.shared_subentity_ids),
                "registration_source": registration_scope.registration_source,
                "warnings": list(registration_scope.warnings),
            },
        )

    def _profile_payload_from_values(
        self,
        *,
        entity_id: int,
        gstin: str,
        state_cd: str,
        profile: GstPortalProfile | None,
        scope: dict,
    ) -> dict:
        backend_username = str(getattr(settings, "WHITEBOOKS_GST_USERNAME", "") or getattr(settings, "WHITEBOX_GST_USERNAME", "") or "").strip()
        gst_username = (profile.gst_username if profile else "") or backend_username
        source = "profile" if profile and profile.gst_username else "backend_default" if backend_username else "missing"
        return {
            "exists": bool(profile),
            "profile_id": profile.id if profile else None,
            "provider": self.provider,
            "entity": entity_id,
            "gstin": str(gstin or "").strip().upper(),
            "state_cd": str(state_cd or "").strip().zfill(2)[:2],
            "gst_username": gst_username,
            "registered_mobile_masked": profile.registered_mobile_masked if profile else "",
            "registered_email_masked": profile.registered_email_masked if profile else "",
            "is_verified": bool(profile.is_verified) if profile else False,
            "last_verified_at": profile.last_verified_at.isoformat() if profile and profile.last_verified_at else None,
            "last_used_at": profile.last_used_at.isoformat() if profile and profile.last_used_at else None,
            "needs_setup": not bool(gst_username),
            "source": source,
            "scope": scope,
        }

    def _normalize_return_type(self, return_type: str) -> str:
        value = str(return_type or "").strip().lower().replace("-", "")
        if value == "gstr1":
            return GstPortalFilingRun.ReturnType.GSTR1
        if value == "gstr3b":
            return GstPortalFilingRun.ReturnType.GSTR3B
        if value == "gstr2b":
            return GstPortalFilingRun.ReturnType.GSTR2B
        raise ValueError("return_type must be one of: gstr1, gstr3b, gstr2b.")


def _combine_gstr3b_summaries(summaries: list[dict]) -> dict:
    if not summaries:
        return {}
    return {
        "section_3_1": {
            "outward_taxable_supplies": _sum_buckets(summaries, ("section_3_1", "outward_taxable_supplies")),
            "outward_zero_rated_supplies": _sum_buckets(summaries, ("section_3_1", "outward_zero_rated_supplies")),
            "outward_nil_exempt_non_gst": _sum_taxable_only(summaries, ("section_3_1", "outward_nil_exempt_non_gst")),
            "inward_supplies_reverse_charge": _sum_buckets(summaries, ("section_3_1", "inward_supplies_reverse_charge")),
            "non_gst_outward_supplies": _sum_taxable_only(summaries, ("section_3_1", "non_gst_outward_supplies")),
            "rows": [],
        },
        "section_3_2": {
            "interstate_supplies_to_unregistered": _sum_buckets(summaries, ("section_3_2", "interstate_supplies_to_unregistered")),
            "interstate_supplies_to_composition": _sum_buckets(summaries, ("section_3_2", "interstate_supplies_to_composition")),
            "interstate_supplies_to_uin_holders": _sum_buckets(summaries, ("section_3_2", "interstate_supplies_to_uin_holders")),
            "rows": [],
        },
        "section_4": {
            "itc_available": _sum_buckets(summaries, ("section_4", "itc_available")),
            "itc_reversed": _sum_buckets(summaries, ("section_4", "itc_reversed")),
            "net_itc": _sum_buckets(summaries, ("section_4", "net_itc")),
            "rows": [],
        },
        "section_5_1": {
            "inward_exempt_nil_non_gst": _sum_taxable_only(summaries, ("section_5_1", "inward_exempt_nil_non_gst")),
            "rows": [],
        },
        "section_6_1": {
            "tax_payable": _sum_buckets(summaries, ("section_6_1", "tax_payable")),
            "tax_paid_cash": _sum_buckets(summaries, ("section_6_1", "tax_paid_cash")),
            "tax_paid_itc": _sum_buckets(summaries, ("section_6_1", "tax_paid_itc")),
            "balance_payable": _sum_buckets(summaries, ("section_6_1", "balance_payable")),
            "rows": [],
        },
        "totals": {
            "tax_payable": _sum_buckets(summaries, ("totals", "tax_payable")),
            "net_itc": _sum_buckets(summaries, ("totals", "net_itc")),
            "net_cash_tax_payable": _sum_buckets(summaries, ("totals", "net_cash_tax_payable")),
        },
    }


def _sum_buckets(summaries: list[dict], path: tuple[str, str]) -> dict:
    keys = ("taxable_value", "cgst", "sgst", "igst", "cess", "total_tax")
    return {key: sum((_decimal(_get_path(summary, path).get(key)) for summary in summaries), Decimal("0.00")) for key in keys}


def _sum_taxable_only(summaries: list[dict], path: tuple[str, str]) -> dict:
    return {"taxable_value": sum((_decimal(_get_path(summary, path).get("taxable_value")) for summary in summaries), Decimal("0.00"))}


def _get_path(summary: dict, path: tuple[str, str]) -> dict:
    current = summary
    for key in path:
        current = current.get(key) or {}
    return current


def _combine_gstr3b_breakups(breakups: list[dict[str, list[dict]]]) -> dict[str, list[dict]]:
    return {
        "unregistered": _sum_breakup_rows(breakups, "unregistered"),
        "composition": _sum_breakup_rows(breakups, "composition"),
        "uin": _sum_breakup_rows(breakups, "uin"),
    }


def _sum_breakup_rows(breakups: list[dict[str, list[dict]]], key: str) -> list[dict]:
    by_pos: dict[str, dict] = {}
    for breakup in breakups:
        for row in breakup.get(key, []):
            pos = str(row.get("place_of_supply_state_code") or row.get("pos") or "").strip()
            target = by_pos.setdefault(pos, {"place_of_supply_state_code": pos, "taxable_value": Decimal("0.00"), "igst": Decimal("0.00")})
            target["taxable_value"] += _decimal(row.get("taxable_value") or row.get("txval"))
            target["igst"] += _decimal(row.get("igst") or row.get("igst_amount") or row.get("iamt"))
    return [by_pos[pos] for pos in sorted(by_pos)]


def _extract_portal_reference(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("ref_id", "refid", "reference_id", "ack_num", "ack_no", "arn", "arn_no"):
            value = payload.get(key)
            if value not in (None, ""):
                return str(value).strip()
        for value in payload.values():
            nested = _extract_portal_reference(value)
            if nested:
                return nested
    if isinstance(payload, list):
        for item in payload:
            nested = _extract_portal_reference(item)
            if nested:
                return nested
    return ""


def _is_nil_filing_payload(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    non_nil_sections = (
        "b2b",
        "b2cl",
        "b2cs",
        "exp",
        "cdnr",
        "cdnur",
        "hsnsum",
        "doc_issue",
        "sup_details",
        "inter_sup",
        "itc_elg",
        "inward_sup",
    )
    return all(not payload.get(section) for section in non_nil_sections)


def _decimal(value: Any) -> Decimal:
    if value in (None, ""):
        return Decimal("0.00")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))
