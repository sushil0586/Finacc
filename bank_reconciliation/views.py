from __future__ import annotations

import json

from django.db.models import Q
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from core.entitlements import ScopedEntitlementMixin
from entity.models import Entity, EntityBankAccountV2
from rbac.services import EffectivePermissionService
from subscriptions.services import SubscriptionLimitCodes, SubscriptionService
from posting.models import JournalLine

from .models import BankReconciliationSession, BankStatementImportProfile
from .serializers import (
    BankReconciliationAutoMatchResponseSerializer,
    BankReconciliationCandidateSerializer,
    BankReconciliationExceptionRequestSerializer,
    BankReconciliationMatchRequestSerializer,
    BankReconciliationScopeSerializer,
    BankReconciliationSessionCreateSerializer,
    BankReconciliationSessionLockSerializer,
    BankReconciliationUnmatchRequestSerializer,
    BankReconciliationExceptionResolveRequestSerializer,
    BankReconciliationSplitMatchRequestSerializer,
    BankStatementImportProfileQuerySerializer,
    BankStatementImportProfileSerializer,
    BankStatementImportSerializer,
    BankStatementPreviewSerializer,
    BankStatementUploadSerializer,
)
from .services import (
    auto_match_session,
    build_hub_payload,
    build_reconciliation_summary,
    build_session_payload,
    candidate_journal_lines,
    create_session,
    import_statement_rows,
    import_statement_file,
    list_import_profiles,
    preview_statement_file,
    recalculate_session_metrics,
    record_exception,
    lock_session,
    manual_match_line,
    resolve_exception_item,
    save_import_profile,
    serialize_import_profile,
    split_match_line,
    unmatch_statement_line,
)


VIEW_PERMISSION_CODES = ("reports.financial_hub.bank_reconciliation.view",)
WRITE_PERMISSION_CODES = (
    "reports.financial_hub.bank_reconciliation.create",
    "reports.financial_hub.bank_reconciliation.update",
)
IMPORT_PERMISSION_CODES = (
    "reports.financial_hub.bank_reconciliation.import",
    "reports.financial_hub.bank_reconciliation.update",
)


class BankReconciliationPermissionMixin:
    def require_permission(self, request, entity, permission_codes: tuple[str, ...]) -> None:
        current_codes = EffectivePermissionService.permission_codes_for_user(request.user, entity.id)
        if any(code in current_codes for code in permission_codes):
            return
        raise PermissionDenied({"detail": "You do not have permission to access bank reconciliation for this entity."})

    def ensure_not_locked(self, session: BankReconciliationSession) -> None:
        if session.status == BankReconciliationSession.Status.LOCKED:
            raise PermissionDenied({"detail": "This reconciliation session is locked."})


def _first_scalar(value, default=None):
    if value is None:
        return default
    if isinstance(value, (list, tuple)):
        return value[0] if value else default
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("[") and text.endswith("]"):
            try:
                parsed = json.loads(text.replace("'", '"'))
                if isinstance(parsed, list) and parsed:
                    return parsed[0]
            except Exception:
                return value
    return value


class BankReconciliationHubAPIView(ScopedEntitlementMixin, BankReconciliationPermissionMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BankReconciliationScopeSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_FINANCIAL
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def get(self, request):
        serializer = self.serializer_class(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        entity = self.enforce_scope(
            request,
            entity_id=scope["entity"],
            entityfinid_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
        )
        self.require_permission(request, entity, VIEW_PERMISSION_CODES)
        return Response(
            build_hub_payload(
                entity=entity,
                entityfin_id=scope.get("entityfinid"),
                subentity_id=scope.get("subentity"),
            )
        )


class BankReconciliationSessionListCreateAPIView(ScopedEntitlementMixin, BankReconciliationPermissionMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BankReconciliationSessionCreateSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_FINANCIAL
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def get(self, request):
        serializer = BankStatementImportProfileQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        entity = self.enforce_scope(
            request,
            entity_id=scope["entity"],
            entityfinid_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
        )
        self.require_permission(request, entity, VIEW_PERMISSION_CODES)

        sessions = (
            BankReconciliationSession.objects.filter(entity=entity)
            .select_related("bank_account", "entityfin", "subentity")
            .order_by("-created_at", "-id")
        )
        if scope.get("entityfinid"):
            sessions = sessions.filter(entityfin_id=scope["entityfinid"])
        if scope.get("subentity"):
            sessions = sessions.filter(subentity_id=scope["subentity"])

        total_count = sessions.count()
        payload = [build_session_payload(session) for session in sessions[:25]]
        return Response({"results": payload, "count": total_count})

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        entity = self.enforce_scope(
            request,
            entity_id=scope["entity"],
            entityfinid_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
        )
        self.require_permission(request, entity, WRITE_PERMISSION_CODES)

        session = create_session(entity=entity, payload=scope, created_by=request.user)
        return Response(build_session_payload(session), status=status.HTTP_201_CREATED)


class BankReconciliationSessionDetailAPIView(ScopedEntitlementMixin, BankReconciliationPermissionMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_FINANCIAL
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def get_object(self, *, request, session_id: int) -> BankReconciliationSession:
        return (
            BankReconciliationSession.objects.select_related("entity", "entityfin", "subentity", "bank_account")
            .prefetch_related("batches__lines", "matches__allocations", "exceptions", "audit_logs")
            .get(pk=session_id)
        )

    def get(self, request, session_id: int):
        session = self.get_object(request=request, session_id=session_id)
        self.enforce_scope(
            request,
            entity_id=session.entity_id,
            entityfinid_id=session.entityfin_id,
            subentity_id=session.subentity_id,
        )
        self.require_permission(request, session.entity, VIEW_PERMISSION_CODES)
        return Response(build_session_payload(session))

    def patch(self, request, session_id: int):
        session = self.get_object(request=request, session_id=session_id)
        self.enforce_scope(
            request,
            entity_id=session.entity_id,
            entityfinid_id=session.entityfin_id,
            subentity_id=session.subentity_id,
        )
        self.require_permission(request, session.entity, WRITE_PERMISSION_CODES)
        self.ensure_not_locked(session)
        notes = request.data.get("notes")
        if notes is not None:
            session.notes = str(notes).strip()
        status_value = request.data.get("status")
        if status_value:
            session.status = str(status_value).strip().lower()
        session.save(update_fields=["notes", "status", "updated_at"])
        recalculate_session_metrics(session)
        return Response(build_session_payload(session))

    def delete(self, request, session_id: int):
        session = self.get_object(request=request, session_id=session_id)
        self.enforce_scope(
            request,
            entity_id=session.entity_id,
            entityfinid_id=session.entityfin_id,
            subentity_id=session.subentity_id,
        )
        self.require_permission(request, session.entity, WRITE_PERMISSION_CODES)
        self.ensure_not_locked(session)
        session.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class BankReconciliationImportAPIView(ScopedEntitlementMixin, BankReconciliationPermissionMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BankStatementImportSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_FINANCIAL
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def post(self, request, session_id: int):
        session = BankReconciliationSession.objects.select_related("entity").get(pk=session_id)
        self.enforce_scope(
            request,
            entity_id=session.entity_id,
            entityfinid_id=session.entityfin_id,
            subentity_id=session.subentity_id,
        )
        self.require_permission(request, session.entity, IMPORT_PERMISSION_CODES)
        self.ensure_not_locked(session)

        serializer = self.serializer_class(data={**request.data, "entity": session.entity_id, "entityfinid": session.entityfin_id, "subentity": session.subentity_id, "bank_account": session.bank_account_id})
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        batch = import_statement_rows(
            session=session,
            rows=scope["rows"],
            created_by=request.user,
            source_name=scope.get("source_name") or "",
            source_format=scope.get("source_format") or "json",
        )

        if scope.get("statement_opening_balance") is not None:
            session.statement_opening_balance = scope["statement_opening_balance"]
        if scope.get("statement_closing_balance") is not None:
            session.statement_closing_balance = scope["statement_closing_balance"]
        if scope.get("book_opening_balance") is not None:
            session.book_opening_balance = scope["book_opening_balance"]
        if scope.get("book_closing_balance") is not None:
            session.book_closing_balance = scope["book_closing_balance"]
        session.notes = scope.get("notes") or session.notes
        session.metadata = {**(session.metadata or {}), **(scope.get("metadata") or {}), "last_import_batch_id": batch.id}
        session.save(update_fields=[
            "statement_opening_balance",
            "statement_closing_balance",
            "book_opening_balance",
            "book_closing_balance",
            "notes",
            "metadata",
            "updated_at",
        ])

        recalculate_session_metrics(session)
        return Response(build_session_payload(session), status=status.HTTP_201_CREATED)


class BankReconciliationUploadAPIView(ScopedEntitlementMixin, BankReconciliationPermissionMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BankStatementUploadSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_FINANCIAL
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def post(self, request, session_id: int):
        session = BankReconciliationSession.objects.select_related("entity").get(pk=session_id)
        self.enforce_scope(
            request,
            entity_id=session.entity_id,
            entityfinid_id=session.entityfin_id,
            subentity_id=session.subentity_id,
        )
        self.require_permission(request, session.entity, IMPORT_PERMISSION_CODES)
        self.ensure_not_locked(session)

        source_name = _first_scalar(request.data.get("source_name"))
        source_format = _first_scalar(request.data.get("source_format"))
        delimiter = _first_scalar(request.data.get("delimiter"))
        notes = _first_scalar(request.data.get("notes"))
        profile_id = _first_scalar(request.data.get("profile_id"))
        column_mapping_raw = _first_scalar(request.data.get("column_mapping"))
        statement_opening_balance = _first_scalar(request.data.get("statement_opening_balance"))
        statement_closing_balance = _first_scalar(request.data.get("statement_closing_balance"))
        book_opening_balance = _first_scalar(request.data.get("book_opening_balance"))
        book_closing_balance = _first_scalar(request.data.get("book_closing_balance"))
        metadata_raw = request.data.get("metadata")
        metadata = _first_scalar(metadata_raw, metadata_raw)

        serializer = self.serializer_class(
            data={
                "entity": session.entity_id,
                "entityfinid": session.entityfin_id,
                "subentity": session.subentity_id,
                "bank_account": session.bank_account_id,
                "source_name": source_name,
                "source_format": source_format,
                "delimiter": delimiter,
                "profile_id": profile_id,
                "file": request.FILES.get("file"),
                "column_mapping": (
                    json.loads(column_mapping_raw or "{}")
                    if isinstance(column_mapping_raw, str)
                    else column_mapping_raw or {}
                ),
                "statement_opening_balance": statement_opening_balance,
                "statement_closing_balance": statement_closing_balance,
                "book_opening_balance": book_opening_balance,
                "book_closing_balance": book_closing_balance,
                "notes": notes,
                "metadata": metadata or {},
            }
        )
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        upload_file = scope["file"]
        profile = None
        if scope.get("profile_id"):
            profile = BankStatementImportProfile.objects.filter(
                id=scope["profile_id"],
                entity=session.entity,
            ).first()
            if profile is None:
                return Response({"detail": "Import profile not found for this entity."}, status=status.HTTP_404_NOT_FOUND)
        raw_column_mapping = scope.get("column_mapping") or (profile.column_mapping if profile else {}) or {}
        if isinstance(raw_column_mapping, str):
            try:
                raw_column_mapping = json.loads(raw_column_mapping or "{}")
            except json.JSONDecodeError:
                raw_column_mapping = {}
        column_mapping = raw_column_mapping if isinstance(raw_column_mapping, dict) else {}
        delimiter = scope.get("delimiter") or (profile.delimiter if profile else ",") or ","
        source_format = scope.get("source_format") or (profile.source_format if profile else "csv")
        try:
            import_statement_file(
                session=session,
                file_data=upload_file.read(),
                source_format=source_format,
                created_by=request.user,
                source_name=scope.get("source_name") or upload_file.name,
                notes=scope.get("notes") or "",
                metadata={**(scope.get("metadata") or {}), "profile_id": profile.id if profile else None, "column_mapping": column_mapping, "delimiter": delimiter},
                column_mapping=column_mapping,
                delimiter=delimiter,
                statement_opening_balance=scope.get("statement_opening_balance"),
                statement_closing_balance=scope.get("statement_closing_balance"),
                book_opening_balance=scope.get("book_opening_balance"),
                book_closing_balance=scope.get("book_closing_balance"),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(build_session_payload(session), status=status.HTTP_201_CREATED)


class BankReconciliationPreviewAPIView(ScopedEntitlementMixin, BankReconciliationPermissionMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BankStatementPreviewSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_FINANCIAL
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def post(self, request, session_id: int):
        session = BankReconciliationSession.objects.select_related("entity").get(pk=session_id)
        self.enforce_scope(
            request,
            entity_id=session.entity_id,
            entityfinid_id=session.entityfin_id,
            subentity_id=session.subentity_id,
        )
        self.require_permission(request, session.entity, VIEW_PERMISSION_CODES)

        source_format = _first_scalar(request.data.get("source_format"))
        delimiter = _first_scalar(request.data.get("delimiter"))

        serializer = self.serializer_class(
            data={
                "entity": session.entity_id,
                "entityfinid": session.entityfin_id,
                "subentity": session.subentity_id,
                "bank_account": session.bank_account_id,
                "source_format": source_format,
                "delimiter": delimiter,
                "file": request.FILES.get("file"),
            }
        )
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        upload_file = scope["file"]
        preview = preview_statement_file(
            upload_file.read(),
            scope.get("source_format") or "csv",
            delimiter=scope.get("delimiter") or ",",
        )
        return Response(preview)


class BankStatementImportProfileAPIView(ScopedEntitlementMixin, BankReconciliationPermissionMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BankStatementImportProfileSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_FINANCIAL
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def get(self, request):
        serializer = BankStatementImportProfileQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        entity = self.enforce_scope(
            request,
            entity_id=scope["entity"],
            entityfinid_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
        )
        self.require_permission(request, entity, VIEW_PERMISSION_CODES)
        profiles = list_import_profiles(entity=entity, bank_account=scope.get("bank_account"), source_format=scope.get("source_format"))
        return Response({"results": [serialize_import_profile(profile) for profile in profiles]})

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        entity = self.enforce_scope(
            request,
            entity_id=scope["entity_id"],
            entityfinid_id=request.data.get("entityfinid"),
            subentity_id=request.data.get("subentity"),
        )
        self.require_permission(request, entity, WRITE_PERMISSION_CODES)
        profile = save_import_profile(entity=entity, payload=scope, created_by=request.user)
        return Response(serialize_import_profile(profile), status=status.HTTP_201_CREATED)


class BankReconciliationOptionsAPIView(ScopedEntitlementMixin, BankReconciliationPermissionMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BankReconciliationScopeSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_FINANCIAL
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def get(self, request):
        serializer = self.serializer_class(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        entity = self.enforce_scope(
            request,
            entity_id=scope["entity"],
            entityfinid_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
        )
        self.require_permission(request, entity, VIEW_PERMISSION_CODES)
        bank_accounts = EntityBankAccountV2.objects.filter(entity=entity, isactive=True).order_by("-is_primary", "bank_name", "id")
        return Response(
            {
                "entity_id": entity.id,
                "bank_accounts": [
                    {
                        "id": account.id,
                        "bank_name": account.bank_name,
                        "account_number": f"****{str(account.account_number)[-4:]}",
                        "ifsc_code": account.ifsc_code,
                        "account_type": account.account_type,
                        "is_primary": account.is_primary,
                    }
                    for account in bank_accounts
                ],
            }
        )


class BankReconciliationCandidatesAPIView(ScopedEntitlementMixin, BankReconciliationPermissionMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BankReconciliationScopeSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_FINANCIAL
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def get(self, request, session_id: int):
        session = BankReconciliationSession.objects.select_related("entity").get(pk=session_id)
        self.enforce_scope(
            request,
            entity_id=session.entity_id,
            entityfinid_id=session.entityfin_id,
            subentity_id=session.subentity_id,
        )
        self.require_permission(request, session.entity, VIEW_PERMISSION_CODES)

        statement_line_id = request.query_params.get("statement_line_id")
        if not statement_line_id:
            return Response({"detail": "statement_line_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        statement = (
            session.batches.select_related("session")
            .filter(lines__id=statement_line_id)
            .first()
        )
        if statement is None:
            return Response({"detail": "Statement line not found for this session."}, status=status.HTTP_404_NOT_FOUND)
        statement = statement.lines.filter(id=statement_line_id).first()
        if statement is None:
            return Response({"detail": "Statement line not found for this session."}, status=status.HTTP_404_NOT_FOUND)

        candidates = candidate_journal_lines(session, statement)
        serializer = BankReconciliationCandidateSerializer(candidates, many=True)
        return Response({"results": serializer.data, "count": len(serializer.data)})


class BankReconciliationSplitMatchAPIView(ScopedEntitlementMixin, BankReconciliationPermissionMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BankReconciliationSplitMatchRequestSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_FINANCIAL
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def post(self, request, session_id: int):
        session = BankReconciliationSession.objects.select_related("entity").get(pk=session_id)
        self.enforce_scope(
            request,
            entity_id=session.entity_id,
            entityfinid_id=session.entityfin_id,
            subentity_id=session.subentity_id,
        )
        self.require_permission(request, session.entity, WRITE_PERMISSION_CODES)
        self.ensure_not_locked(session)

        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data

        statement_line = session.batches.filter(lines__id=scope["statement_line_id"]).first()
        if statement_line is not None:
            statement_line = statement_line.lines.filter(id=scope["statement_line_id"]).first()
        if statement_line is None:
            return Response({"detail": "Statement line not found for this session."}, status=status.HTTP_404_NOT_FOUND)

        try:
            match = split_match_line(
                session=session,
                statement_line=statement_line,
                allocations=scope["allocations"],
                created_by=request.user,
                notes=scope.get("notes") or "",
                metadata=scope.get("metadata") or {},
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        recalculate_session_metrics(session)
        return Response(
            {
                "match": {
                    "id": match.id,
                    "statement_line_id": match.statement_line_id,
                    "match_kind": match.match_kind,
                    "matched_amount": f"{match.matched_amount:.2f}",
                    "difference_amount": f"{match.difference_amount:.2f}",
                    "confidence": f"{match.confidence:.2f}",
                    "notes": match.notes,
                },
                "session": build_session_payload(session),
            },
            status=status.HTTP_201_CREATED,
        )


class BankReconciliationUnmatchAPIView(ScopedEntitlementMixin, BankReconciliationPermissionMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BankReconciliationUnmatchRequestSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_FINANCIAL
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def post(self, request, session_id: int):
        session = BankReconciliationSession.objects.select_related("entity").get(pk=session_id)
        self.enforce_scope(
            request,
            entity_id=session.entity_id,
            entityfinid_id=session.entityfin_id,
            subentity_id=session.subentity_id,
        )
        self.require_permission(request, session.entity, WRITE_PERMISSION_CODES)
        self.ensure_not_locked(session)

        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data

        statement = session.batches.filter(lines__id=scope["statement_line_id"]).first()
        if statement is None:
            return Response({"detail": "Statement line not found for this session."}, status=status.HTTP_404_NOT_FOUND)
        statement_line = statement.lines.filter(id=scope["statement_line_id"]).first()
        if statement_line is None:
            return Response({"detail": "Statement line not found for this session."}, status=status.HTTP_404_NOT_FOUND)
        if not session.matches.filter(statement_line=statement_line).exists():
            return Response({"detail": "No match exists for the selected statement line."}, status=status.HTTP_400_BAD_REQUEST)

        unmatch_statement_line(session=session, statement_line=statement_line, created_by=request.user)
        recalculate_session_metrics(session)
        return Response(build_session_payload(session))


class BankReconciliationExceptionAPIView(ScopedEntitlementMixin, BankReconciliationPermissionMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BankReconciliationExceptionRequestSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_FINANCIAL
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def post(self, request, session_id: int):
        session = BankReconciliationSession.objects.select_related("entity").get(pk=session_id)
        self.enforce_scope(
            request,
            entity_id=session.entity_id,
            entityfinid_id=session.entityfin_id,
            subentity_id=session.subentity_id,
        )
        self.require_permission(request, session.entity, WRITE_PERMISSION_CODES)
        self.ensure_not_locked(session)

        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data

        statement_line = session.batches.filter(lines__id=scope["statement_line_id"]).first()
        if statement_line is not None:
            statement_line = statement_line.lines.filter(id=scope["statement_line_id"]).first()
        if statement_line is None:
            return Response({"detail": "Statement line not found for this session."}, status=status.HTTP_404_NOT_FOUND)

        try:
            exception_item = record_exception(
                session=session,
                statement_line=statement_line,
                exception_type=scope["exception_type"],
                amount=scope.get("amount"),
                created_by=request.user,
                notes=scope.get("notes") or "",
                metadata=scope.get("metadata") or {},
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        recalculate_session_metrics(session)
        return Response(
            {
                "exception": {
                    "id": exception_item.id,
                    "statement_line_id": exception_item.statement_line_id,
                    "exception_type": exception_item.exception_type,
                    "status": exception_item.status,
                    "amount": f"{exception_item.amount:.2f}",
                    "notes": exception_item.notes,
                },
                "session": build_session_payload(session),
            },
            status=status.HTTP_201_CREATED,
        )


class BankReconciliationExceptionResolveAPIView(ScopedEntitlementMixin, BankReconciliationPermissionMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BankReconciliationExceptionResolveRequestSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_FINANCIAL
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def post(self, request, session_id: int):
        session = BankReconciliationSession.objects.select_related("entity").get(pk=session_id)
        self.enforce_scope(
            request,
            entity_id=session.entity_id,
            entityfinid_id=session.entityfin_id,
            subentity_id=session.subentity_id,
        )
        self.require_permission(request, session.entity, WRITE_PERMISSION_CODES)
        self.ensure_not_locked(session)

        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data

        exception_item = session.exceptions.select_related("statement_line").filter(id=scope["exception_id"]).first()
        if exception_item is None:
            return Response({"detail": "Exception not found for this session."}, status=status.HTTP_404_NOT_FOUND)

        try:
            resolved_exception = resolve_exception_item(
                session=session,
                exception_item=exception_item,
                created_by=request.user,
                status=scope.get("status") or "resolved",
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        recalculate_session_metrics(session)
        return Response(
            {
                "exception": {
                    "id": resolved_exception.id,
                    "statement_line_id": resolved_exception.statement_line_id,
                    "exception_type": resolved_exception.exception_type,
                    "status": resolved_exception.status,
                    "amount": f"{resolved_exception.amount:.2f}",
                    "notes": resolved_exception.notes,
                },
                "session": build_session_payload(session),
            }
        )


class BankReconciliationSummaryAPIView(ScopedEntitlementMixin, BankReconciliationPermissionMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_FINANCIAL
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def get(self, request, session_id: int):
        session = BankReconciliationSession.objects.select_related("entity").get(pk=session_id)
        self.enforce_scope(
            request,
            entity_id=session.entity_id,
            entityfinid_id=session.entityfin_id,
            subentity_id=session.subentity_id,
        )
        self.require_permission(request, session.entity, VIEW_PERMISSION_CODES)
        return Response(build_reconciliation_summary(session))


class BankReconciliationLockAPIView(ScopedEntitlementMixin, BankReconciliationPermissionMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BankReconciliationSessionLockSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_FINANCIAL
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def post(self, request, session_id: int):
        session = BankReconciliationSession.objects.select_related("entity").get(pk=session_id)
        self.enforce_scope(
            request,
            entity_id=session.entity_id,
            entityfinid_id=session.entityfin_id,
            subentity_id=session.subentity_id,
        )
        self.require_permission(request, session.entity, WRITE_PERMISSION_CODES)
        self.ensure_not_locked(session)

        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        try:
            locked_session = lock_session(session=session, created_by=request.user, force=scope.get("force", False))
        except ValueError as exc:
            return Response({"detail": str(exc), "summary": build_reconciliation_summary(session)}, status=status.HTTP_400_BAD_REQUEST)
        recalculate_session_metrics(locked_session)
        return Response(build_session_payload(locked_session))


class BankReconciliationAutoMatchAPIView(ScopedEntitlementMixin, BankReconciliationPermissionMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_FINANCIAL
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def post(self, request, session_id: int):
        session = BankReconciliationSession.objects.select_related("entity").get(pk=session_id)
        self.enforce_scope(
            request,
            entity_id=session.entity_id,
            entityfinid_id=session.entityfin_id,
            subentity_id=session.subentity_id,
        )
        self.require_permission(request, session.entity, WRITE_PERMISSION_CODES)
        self.ensure_not_locked(session)
        payload = auto_match_session(session=session, created_by=request.user)
        serializer = BankReconciliationAutoMatchResponseSerializer(payload)
        return Response(serializer.data)


class BankReconciliationManualMatchAPIView(ScopedEntitlementMixin, BankReconciliationPermissionMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BankReconciliationMatchRequestSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_FINANCIAL
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def post(self, request, session_id: int):
        session = BankReconciliationSession.objects.select_related("entity").get(pk=session_id)
        self.enforce_scope(
            request,
            entity_id=session.entity_id,
            entityfinid_id=session.entityfin_id,
            subentity_id=session.subentity_id,
        )
        self.require_permission(request, session.entity, WRITE_PERMISSION_CODES)

        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data

        statement_line = None
        if scope.get("statement_line_id"):
            statement_line = session.batches.filter(lines__id=scope["statement_line_id"]).first()
            if statement_line is not None:
                statement_line = statement_line.lines.filter(id=scope["statement_line_id"]).first()
        if statement_line is None:
            return Response({"detail": "Statement line not found for this session."}, status=status.HTTP_404_NOT_FOUND)

        journal_line = JournalLine.objects.select_related("entry").filter(
            id=scope["journal_line_id"],
            entity=session.entity,
        ).first()
        if journal_line is None:
            return Response({"detail": "Journal line not found for this entity."}, status=status.HTTP_404_NOT_FOUND)

        match = manual_match_line(
            session=session,
            statement_line=statement_line,
            journal_line=journal_line,
            created_by=request.user,
            match_kind=scope.get("match_kind") or "manual",
            notes=scope.get("notes") or "",
            confidence=scope.get("confidence"),
            metadata=scope.get("metadata") or {},
        )
        recalculate_session_metrics(session)
        return Response(
            {
                "match": {
                    "id": match.id,
                    "statement_line_id": match.statement_line_id,
                    "journal_line_id": match.journal_line_id,
                    "match_kind": match.match_kind,
                    "matched_amount": f"{match.matched_amount:.2f}",
                    "difference_amount": f"{match.difference_amount:.2f}",
                    "confidence": f"{match.confidence:.2f}",
                    "notes": match.notes,
                },
                "session": build_session_payload(session),
            },
            status=status.HTTP_201_CREATED,
        )
