from __future__ import annotations

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.entitlements import ScopedEntitlementMixin
from subscriptions.services import SubscriptionLimitCodes, SubscriptionService

from entity.models import Entity, EntityBankAccountV2
from financial.models import AccountBankDetails
from subscriptions.models import UserEntityAccess

from .models import BankReconciliationMatch, BankReconciliationRun, BankStatementImport
from .serializers import (
    AutoMatchResponseSerializer,
    AuditTrailRowSerializer,
    BankRecoRunReportScopeSerializer,
    BankRecoScopeSerializer,
    BankStatementImportArchiveSerializer,
    BankStatementImportCreateSerializer,
    BankStatementImportDetailSerializer,
    BankStatementImportUpdateSerializer,
    BankStatementImportPreviewResponseSerializer,
    BankStatementImportPreviewSerializer,
    BankStatementImportListSerializer,
    BankStatementImportValidationResponseSerializer,
    BankStatementLineListSerializer,
    BrsReportSerializer,
    ExceptionActionRequestSerializer,
    GroupMatchRequestSerializer,
    MatchCandidateResponseSerializer,
    MatchRequestSerializer,
    RunActionRequestSerializer,
    UnmatchRequestSerializer,
    VoucherCreationRequestSerializer,
    WorkspaceBankLineSerializer,
    WorkspaceBookLineSerializer,
    resolve_scope_models,
)
from .services.imports import (
    archive_statement_import,
    build_workspace_summary,
    import_statement_upload,
    preview_statement_file,
    revise_statement_import,
    validate_statement_import,
)
from .services.matching import (
    auto_match_import,
    build_workspace_payload,
    confirm_manual_match,
    get_run_bank_lines,
    unmatch,
)
from .services.voucher_creation import create_voucher_from_bank_line
from .services.exceptions import apply_exception_action
from .services.run_controls import apply_run_action, ensure_run_mutable
from .services.reports import (
    build_audit_trail_report,
    build_brs_report,
    build_unmatched_bank_report,
    build_unmatched_books_report,
)
from posting.models import JournalLine


class BankRecoBaseAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_FINANCIAL
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def build_audit_context(self, request):
        return {
            "ip_address": request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR", ""),
            "user_agent": request.META.get("HTTP_USER_AGENT", ""),
            "request_path": request.path,
            "request_method": request.method,
        }

    def validate_scope_models(self, *, entity, entityfin=None, subentity=None, bank_account=None):
        if entityfin is not None and getattr(entityfin, "entity_id", None) not in {None, entity.id}:
            raise PermissionError("Entity financial year does not belong to the selected entity.")
        if subentity is not None and getattr(subentity, "entity_id", None) not in {None, entity.id}:
            raise PermissionError("Subentity does not belong to the selected entity.")
        if bank_account is not None and getattr(bank_account, "entity_id", None) != entity.id:
            raise PermissionError("Bank account is not valid for the selected entity.")

    def get_scoped_import(self, request, import_id: int) -> BankStatementImport:
        statement_import = BankStatementImport.objects.select_related("entity", "entityfin", "subentity", "bank_account").get(pk=import_id)
        self.enforce_scope(
            request,
            entity_id=statement_import.entity_id,
            entityfinid_id=statement_import.entityfin_id,
            subentity_id=statement_import.subentity_id,
        )
        self.validate_scope_models(
            entity=statement_import.entity,
            entityfin=statement_import.entityfin,
            subentity=statement_import.subentity,
            bank_account=statement_import.bank_account,
        )
        return statement_import

    def get_scoped_run(self, request, run_id: int) -> BankReconciliationRun:
        run = BankReconciliationRun.objects.select_related("entity", "entityfin", "subentity", "bank_account", "statement_import").get(pk=run_id)
        self.enforce_scope(
            request,
            entity_id=run.entity_id,
            entityfinid_id=run.entityfin_id,
            subentity_id=run.subentity_id,
        )
        self.validate_scope_models(
            entity=run.entity,
            entityfin=run.entityfin,
            subentity=run.subentity,
            bank_account=run.bank_account,
        )
        return run

    def ensure_run_mutable(self, run: BankReconciliationRun):
        ensure_run_mutable(run=run)

    def serialize_run_bank_account(self, run: BankReconciliationRun):
        bank_account = getattr(run, "bank_account", None)
        if bank_account is None:
            return None
        return {
            "id": bank_account.id,
            "bank_name": bank_account.bank_name,
            "account_number_masked": f"***{bank_account.account_number[-4:]}",
        }


class BankRecoHealthAPIView(BankRecoBaseAPIView):
    def get(self, request):
        return Response(
            {
                "module": "bank_reco",
                "status": "active",
                "message": "New bank reconciliation domain is ready for import, validation, and workspace operations.",
            }
        )


class BankRecoMetaAPIView(BankRecoBaseAPIView):
    def get(self, request):
        memberships = UserEntityAccess.objects.filter(user=request.user, is_active=True).values_list("customer_account_id", flat=True)
        entities = list(
            Entity.objects.filter(customer_account_id__in=memberships, isactive=True)
            .order_by("entityname", "id")
        )
        requested_entity_id = request.query_params.get("entity")
        selected_entity = None
        if requested_entity_id:
            selected_entity = self.enforce_scope(request, entity_id=int(requested_entity_id))
        elif entities:
            selected_entity = entities[0]

        bank_accounts = EntityBankAccountV2.objects.none()
        if selected_entity is not None:
            bank_accounts = (
                EntityBankAccountV2.objects.filter(entity=selected_entity, isactive=True)
                .select_related("book_ledger", "book_ledger__account_profile")
                .order_by("-is_primary", "bank_name", "id")
            )

        account_bindings = {
            detail.banKAcno: detail
            for detail in AccountBankDetails.objects.filter(
                entity=selected_entity,
                isactive=True,
            ).select_related("account__ledger")
        } if selected_entity is not None else {}
        return Response(
            {
                "entities": [
                    {
                        "id": entity.id,
                        "name": entity.entityname,
                        "entity_code": entity.entity_code or str(entity.id),
                    }
                    for entity in entities
                ],
                "bank_accounts": [
                    {
                        "id": item.id,
                        "entity": item.entity_id,
                        "bank_name": item.bank_name,
                        "account_number_masked": f"***{item.account_number[-4:]}",
                        "ifsc": item.ifsc_code,
                        "ledger_id": (
                            getattr(item.book_ledger, "id", None)
                            or getattr(getattr(account_bindings.get(item.account_number), "account", None), "ledger_id", None)
                        ),
                        "ledger_name": (
                            getattr(item.book_ledger, "name", None)
                            or getattr(getattr(getattr(account_bindings.get(item.account_number), "account", None), "ledger", None), "name", None)
                        ),
                        "is_primary": bool(item.is_primary),
                        "is_active": bool(item.isactive),
                    }
                    for item in bank_accounts
                ],
                "voucher_types": list(VoucherCreationRequestSerializer().fields["voucher_kind"].choices.keys()),
                "exception_actions": list(ExceptionActionRequestSerializer().fields["action"].choices.keys()),
                "statuses": [choice[0] for choice in BankStatementImport.Status.choices] + [choice[0] for choice in BankReconciliationMatch.Status.choices],
            }
        )


class BankRecoImportCreateAPIView(BankRecoBaseAPIView):
    def post(self, request):
        serializer = BankStatementImportCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        entity = self.enforce_scope(
            request,
            entity_id=payload["entity"],
            entityfinid_id=payload.get("entityfinid"),
            subentity_id=payload.get("subentity"),
        )
        entityfin, subentity, bank_account = resolve_scope_models(payload)
        try:
            self.validate_scope_models(entity=entity, entityfin=entityfin, subentity=subentity, bank_account=bank_account)
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        statement_import = import_statement_upload(
            entity=entity,
            entityfin=entityfin,
            subentity=subentity,
            bank_account=bank_account,
            uploaded_file=payload["file"],
            file_type=payload["source_file_type"],
            uploaded_by=request.user,
            parser_key=payload.get("parser_key") or "",
            delimiter=payload.get("delimiter") or ",",
            statement_from=payload.get("statement_from"),
            statement_to=payload.get("statement_to"),
            opening_balance=payload.get("opening_balance"),
            closing_balance=payload.get("closing_balance"),
            metadata={
                **(payload.get("metadata") or {}),
                "request_context": self.build_audit_context(request),
            },
            column_map=payload.get("column_map") or {},
        )
        return Response(BankStatementImportListSerializer(statement_import).data, status=status.HTTP_201_CREATED)


class BankRecoImportPreviewAPIView(BankRecoBaseAPIView):
    def post(self, request):
        serializer = BankStatementImportPreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        entity = self.enforce_scope(
            request,
            entity_id=payload["entity"],
            entityfinid_id=payload.get("entityfinid"),
            subentity_id=payload.get("subentity"),
        )
        entityfin, subentity, bank_account = resolve_scope_models(payload)
        try:
            self.validate_scope_models(entity=entity, entityfin=entityfin, subentity=subentity, bank_account=bank_account)
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        uploaded_file = payload["file"]
        preview = preview_statement_file(
            data=uploaded_file.read(),
            file_type=payload["source_file_type"],
            delimiter=payload.get("delimiter") or ",",
            column_map=payload.get("column_map") or {},
        )
        return Response(BankStatementImportPreviewResponseSerializer(preview).data)


class BankRecoImportListAPIView(BankRecoBaseAPIView):
    def get(self, request):
        serializer = BankRecoScopeSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        entity = self.enforce_scope(
            request,
            entity_id=payload["entity"],
            entityfinid_id=payload.get("entityfinid"),
            subentity_id=payload.get("subentity"),
        )
        entityfin, subentity, bank_account = resolve_scope_models(payload)
        try:
            self.validate_scope_models(entity=entity, entityfin=entityfin, subentity=subentity, bank_account=bank_account)
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        queryset = BankStatementImport.objects.filter(entity=entity).select_related("bank_account")
        if entityfin is not None:
            queryset = queryset.filter(entityfin=entityfin)
        if subentity is not None:
            queryset = queryset.filter(subentity=subentity)
        if bank_account is not None:
            queryset = queryset.filter(bank_account=bank_account)
        return Response(
            {
                "count": queryset.count(),
                "results": BankStatementImportListSerializer(queryset.order_by("-created_at", "-id"), many=True).data,
            }
        )


class BankRecoImportLineListAPIView(BankRecoBaseAPIView):
    def get(self, request, import_id: int):
        statement_import = self.get_scoped_import(request, import_id)
        queryset = statement_import.lines.order_by("line_no", "id")
        status_filter = request.query_params.get("validation_status")
        if status_filter:
            queryset = queryset.filter(validation_status=status_filter)
        return Response(
            {
                "import": BankStatementImportListSerializer(statement_import).data,
                "count": queryset.count(),
                "results": BankStatementLineListSerializer(queryset, many=True).data,
            }
        )


class BankRecoImportDetailAPIView(BankRecoBaseAPIView):
    def get(self, request, import_id: int):
        statement_import = self.get_scoped_import(request, import_id)
        return Response(BankStatementImportDetailSerializer(statement_import).data)

    def patch(self, request, import_id: int):
        statement_import = self.get_scoped_import(request, import_id)
        serializer = BankStatementImportUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        statement_import = revise_statement_import(
            statement_import=statement_import,
            actor=request.user,
            audit_context=self.build_audit_context(request),
            **serializer.validated_data,
        )
        return Response(BankStatementImportDetailSerializer(statement_import).data)


class BankRecoImportArchiveAPIView(BankRecoBaseAPIView):
    def post(self, request, import_id: int):
        statement_import = self.get_scoped_import(request, import_id)
        serializer = BankStatementImportArchiveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        statement_import = archive_statement_import(
            statement_import=statement_import,
            actor=request.user,
            audit_context=self.build_audit_context(request),
            reason=serializer.validated_data.get("reason") or "",
        )
        return Response(BankStatementImportDetailSerializer(statement_import).data)


class BankRecoImportValidateAPIView(BankRecoBaseAPIView):
    def post(self, request, import_id: int):
        statement_import = self.get_scoped_import(request, import_id)
        statement_import = validate_statement_import(
            statement_import=statement_import,
            actor=request.user,
            audit_context=self.build_audit_context(request),
        )
        return Response(BankStatementImportValidationResponseSerializer(statement_import).data)


class BankRecoImportAutoMatchAPIView(BankRecoBaseAPIView):
    def post(self, request, import_id: int):
        statement_import = self.get_scoped_import(request, import_id)
        run, matches = auto_match_import(
            statement_import=statement_import,
            actor=request.user,
            audit_context=self.build_audit_context(request),
        )
        return Response(
            AutoMatchResponseSerializer(
                {"run_id": run.id, "run_code": run.run_code, "matches": matches}
            ).data
        )


class BankRecoMatchAPIView(BankRecoBaseAPIView):
    def post(self, request):
        serializer = MatchRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        run = self.get_scoped_run(request, payload["run_id"])
        self.ensure_run_mutable(run)
        bank_line = get_run_bank_lines(run=run, bank_line_ids=[payload["bank_line_id"]])[0]
        journal_line = JournalLine.objects.select_related("entry").get(pk=payload["journal_line_id"])
        match = confirm_manual_match(
            run=run,
            bank_lines=[bank_line],
            journal_lines=[journal_line],
            actor=request.user,
            notes=payload.get("notes") or "",
            audit_context=self.build_audit_context(request),
        )
        return Response(
            MatchCandidateResponseSerializer(
                {
                    "match_id": match.id,
                    "status": match.status,
                    "match_type": match.match_type,
                    "match_kind": match.match_kind,
                    "confidence_score": str(match.confidence_score),
                    "matched_amount": str(match.matched_amount),
                    "difference_amount": str(match.difference_amount),
                    "reason_codes": match.reason_codes,
                    "bank_line_ids": [rel.statement_line_id for rel in match.bank_lines.all()],
                    "journal_line_ids": [rel.journal_line_id for rel in match.book_lines.all()],
                }
            ).data,
            status=status.HTTP_201_CREATED,
        )


class BankRecoGroupMatchAPIView(BankRecoBaseAPIView):
    def post(self, request):
        serializer = GroupMatchRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        run = self.get_scoped_run(request, payload["run_id"])
        self.ensure_run_mutable(run)
        bank_lines = get_run_bank_lines(run=run, bank_line_ids=payload["bank_line_ids"])
        journal_lines = list(JournalLine.objects.select_related("entry").filter(id__in=payload["journal_line_ids"]).order_by("posting_date", "id"))
        if len(journal_lines) != len(set(payload["journal_line_ids"])):
            return Response({"journal_line_ids": "One or more selected journal lines could not be found."}, status=status.HTTP_400_BAD_REQUEST)
        match = confirm_manual_match(
            run=run,
            bank_lines=bank_lines,
            journal_lines=journal_lines,
            actor=request.user,
            notes=payload.get("notes") or "",
            audit_context=self.build_audit_context(request),
        )
        return Response(
            MatchCandidateResponseSerializer(
                {
                    "match_id": match.id,
                    "status": match.status,
                    "match_type": match.match_type,
                    "match_kind": match.match_kind,
                    "confidence_score": str(match.confidence_score),
                    "matched_amount": str(match.matched_amount),
                    "difference_amount": str(match.difference_amount),
                    "reason_codes": match.reason_codes,
                    "bank_line_ids": [rel.statement_line_id for rel in match.bank_lines.all()],
                    "journal_line_ids": [rel.journal_line_id for rel in match.book_lines.all()],
                }
            ).data,
            status=status.HTTP_201_CREATED,
        )


class BankRecoUnmatchAPIView(BankRecoBaseAPIView):
    def post(self, request):
        serializer = UnmatchRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        match = BankReconciliationMatch.objects.select_related("run__entity", "run__entityfin", "run__subentity", "run__statement_import").get(pk=payload["match_id"])
        run = self.get_scoped_run(request, match.run_id)
        self.ensure_run_mutable(run)
        match = unmatch(
            match=match,
            actor=request.user,
            notes=payload.get("notes") or "",
            audit_context=self.build_audit_context(request),
        )
        return Response(
            MatchCandidateResponseSerializer(
                {
                    "match_id": match.id,
                    "status": match.status,
                    "match_type": match.match_type,
                    "match_kind": match.match_kind,
                    "confidence_score": str(match.confidence_score),
                    "matched_amount": str(match.matched_amount),
                    "difference_amount": str(match.difference_amount),
                    "reason_codes": match.reason_codes,
                    "bank_line_ids": [rel.statement_line_id for rel in match.bank_lines.all()],
                    "journal_line_ids": [rel.journal_line_id for rel in match.book_lines.all()],
                }
            ).data
        )


class BankRecoWorkspaceAPIView(BankRecoBaseAPIView):
    def get(self, request):
        serializer = BankRecoScopeSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        entity = self.enforce_scope(
            request,
            entity_id=payload["entity"],
            entityfinid_id=payload.get("entityfinid"),
            subentity_id=payload.get("subentity"),
        )
        entityfin, subentity, bank_account = resolve_scope_models(payload)
        try:
            self.validate_scope_models(entity=entity, entityfin=entityfin, subentity=subentity, bank_account=bank_account)
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if payload.get("run_id"):
            run = self.get_scoped_run(request, payload["run_id"])
            statement_import = run.statement_import
        elif payload.get("import_id"):
            statement_import = self.get_scoped_import(request, payload["import_id"])
            run = BankReconciliationRun.objects.filter(statement_import=statement_import).order_by("-created_at", "-id").first()
        else:
            summary = build_workspace_summary(
                entity=entity,
                entityfin=entityfin,
                subentity=subentity,
                bank_account=bank_account,
            )
            return Response(summary)
        return Response(
            build_workspace_payload(
                statement_import=statement_import,
                run=run,
                filters={
                    "date_from": payload.get("date_from"),
                    "date_to": payload.get("date_to"),
                    "amount": payload.get("amount"),
                    "status": payload.get("status"),
                    "reference": payload.get("reference"),
                    "narration": payload.get("narration"),
                },
                summary_only=bool(payload.get("summary_only")),
                include_queues=bool(payload.get("include_queues", True)),
                include_matches=bool(payload.get("include_matches", True)),
            )
        )


class BankRecoCreateVoucherFromBankLineAPIView(BankRecoBaseAPIView):
    def post(self, request):
        serializer = VoucherCreationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        run = self.get_scoped_run(request, payload["run_id"])
        self.ensure_run_mutable(run)
        result = create_voucher_from_bank_line(
            run=run,
            bank_line_id=payload["bank_line_id"],
            voucher_kind=payload["voucher_kind"],
            counterpart_account_id=payload["counterpart_account_id"],
            allocations=payload.get("allocations") or None,
            actor=request.user,
            voucher_date=payload.get("voucher_date"),
            reference_number=payload.get("reference_number") or "",
            narration=payload.get("narration") or "",
            instrument_no=payload.get("instrument_no") or "",
            instrument_date=payload.get("instrument_date"),
            audit_context=self.build_audit_context(request),
        )
        return Response(result, status=status.HTTP_201_CREATED)


class BankRecoExceptionActionAPIView(BankRecoBaseAPIView):
    def post(self, request):
        serializer = ExceptionActionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        run = self.get_scoped_run(request, payload["run_id"])
        self.ensure_run_mutable(run)
        bank_line = apply_exception_action(
            run=run,
            bank_line_id=payload["bank_line_id"],
            action=payload["action"],
            reason=payload.get("reason") or "",
            actor=request.user,
            audit_context=self.build_audit_context(request),
        )
        return Response(
            WorkspaceBankLineSerializer(
                {
                    "id": bank_line.id,
                    "line_no": bank_line.line_no,
                    "txn_date": bank_line.txn_date,
                    "value_date": bank_line.value_date,
                    "narration": bank_line.narration,
                    "reference_no": bank_line.reference_no,
                    "cheque_no": bank_line.cheque_no,
                    "debit_amount": bank_line.debit_amount,
                    "credit_amount": bank_line.credit_amount,
                    "balance": bank_line.balance,
                    "status": bank_line.reconciliation_status,
                    "exception_status": bank_line.exception_status,
                    "exception_reason": bank_line.exception_reason,
                    "statement_import_id": bank_line.statement_import_id,
                    "statement_import_code": bank_line.statement_import.import_code,
                    "is_opening_item": bool(
                        run.statement_import.statement_from
                        and bank_line.statement_import.statement_to
                        and bank_line.statement_import.statement_to < run.statement_import.statement_from
                    ),
                    "created_voucher_id": bank_line.created_voucher_id,
                }
            ).data
        )


class BankRecoRunActionAPIView(BankRecoBaseAPIView):
    def post(self, request, run_id: int):
        serializer = RunActionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        run = self.get_scoped_run(request, run_id)
        if payload["action"] != "unlock_run":
            self.ensure_run_mutable(run)
        run = apply_run_action(
            run=run,
            action=payload["action"],
            actor=request.user,
            notes=payload.get("notes") or "",
            audit_context=self.build_audit_context(request),
        )
        return Response(
            {
                "run_id": run.id,
                "run_code": run.run_code,
                "status": run.status,
                "locked_by": getattr(run.locked_by, "id", None),
                "locked_at": run.locked_at,
                "notes": run.notes,
            }
        )


class BankRecoUnmatchedBankReportAPIView(BankRecoBaseAPIView):
    def get(self, request):
        serializer = BankRecoRunReportScopeSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        run = self.get_scoped_run(request, payload["run_id"])
        report = build_unmatched_bank_report(
            run=run,
            limit=payload.get("limit") or 400,
            offset=payload.get("offset") or 0,
            filters={
                "date_from": payload.get("date_from"),
                "date_to": payload.get("date_to"),
                "amount": payload.get("amount"),
                "status": payload.get("status"),
                "reference": payload.get("reference"),
                "narration": payload.get("narration"),
            },
        )
        return Response(
            {
                "count": report["count"],
                "results": WorkspaceBankLineSerializer(report["rows"], many=True).data,
                "totals": report["totals"],
                "export_rows": report["export_rows"],
                "bank_account": self.serialize_run_bank_account(run),
            }
        )


class BankRecoUnmatchedBooksReportAPIView(BankRecoBaseAPIView):
    def get(self, request):
        serializer = BankRecoRunReportScopeSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        run = self.get_scoped_run(request, payload["run_id"])
        report = build_unmatched_books_report(
            run=run,
            limit=payload.get("limit") or 400,
            offset=payload.get("offset") or 0,
            filters={
                "date_from": payload.get("date_from"),
                "date_to": payload.get("date_to"),
                "amount": payload.get("amount"),
                "status": payload.get("status"),
                "reference": payload.get("reference"),
                "narration": payload.get("narration"),
            },
        )
        return Response(
            {
                "count": report["count"],
                "results": WorkspaceBookLineSerializer(report["rows"], many=True).data,
                "totals": report["totals"],
                "export_rows": report["export_rows"],
                "bank_account": self.serialize_run_bank_account(run),
            }
        )


class BankRecoAuditTrailReportAPIView(BankRecoBaseAPIView):
    def get(self, request):
        serializer = BankRecoRunReportScopeSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        run = self.get_scoped_run(request, payload["run_id"])
        report = build_audit_trail_report(run=run, action=payload.get("action"))
        return Response({
            "count": len(report["rows"]),
            "results": AuditTrailRowSerializer(report["rows"], many=True).data,
            "export_rows": report["export_rows"],
            "bank_account": self.serialize_run_bank_account(run),
        })


class BankRecoBrsReportAPIView(BankRecoBaseAPIView):
    def get(self, request):
        serializer = BankRecoRunReportScopeSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        run = self.get_scoped_run(request, payload["run_id"])
        data = BrsReportSerializer(build_brs_report(run=run)).data
        data["bank_account"] = self.serialize_run_bank_account(run)
        return Response(data)
