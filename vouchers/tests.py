from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from entity.models import Entity, EntityFinancialYear, SubEntity
from numbering.models import DocumentNumberSeries, DocumentType
from numbering.seeding import NumberingSeedService
from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from vouchers.models import VoucherHeader, VoucherLine
from vouchers.serializers.voucher import VoucherWriteSerializer
from vouchers.services.voucher_settings_service import VoucherSettingsService
from vouchers.services.voucher_service import VoucherResult, VoucherService
from vouchers.views.voucher import (
    VoucherListCreateAPIView,
    VoucherApprovalAPIView,
    VoucherCancelAPIView,
    VoucherConfirmAPIView,
    VoucherPostAPIView,
    VoucherUnpostAPIView,
    _duplicate_reference_warnings,
)


class VoucherServiceUnitTests(SimpleTestCase):
    def test_validate_journal_lines_returns_balanced_totals(self):
        total_dr, total_cr = VoucherService._validate_journal_lines(
            lines=[
                {"account": 11, "dr_amount": Decimal("100.00"), "cr_amount": Decimal("0.00")},
                {"account": 12, "dr_amount": Decimal("0.00"), "cr_amount": Decimal("100.00")},
            ]
        )

        self.assertEqual(total_dr, Decimal("100.00"))
        self.assertEqual(total_cr, Decimal("100.00"))

    def test_validate_journal_lines_rejects_unbalanced_totals(self):
        with self.assertRaisesMessage(ValueError, "Journal voucher total debit and credit must be equal."):
            VoucherService._validate_journal_lines(
                lines=[
                    {"account": 11, "dr_amount": Decimal("100.00"), "cr_amount": Decimal("0.00")},
                    {"account": 12, "dr_amount": Decimal("0.00"), "cr_amount": Decimal("90.00")},
                ]
            )

    def test_validate_cash_bank_lines_rejects_same_cash_bank_account(self):
        header = SimpleNamespace(
            voucher_type=VoucherHeader.VoucherType.CASH,
            cash_bank_account_id=21,
        )

        with self.assertRaisesMessage(ValueError, "Line 1: account cannot be same as cash/bank account."):
            VoucherService._validate_cash_bank_lines(
                header=header,
                lines=[{"account": 21, "entry_type": "DR", "amount": Decimal("10.00")}],
                policy_controls={},
            )

    def test_validate_cash_bank_lines_blocks_mixed_entries_when_policy_is_hard(self):
        header = SimpleNamespace(
            voucher_type=VoucherHeader.VoucherType.BANK,
            cash_bank_account_id=99,
        )

        with self.assertRaisesMessage(ValueError, "mixed DR and CR lines are not allowed in BANK voucher"):
            VoucherService._validate_cash_bank_lines(
                header=header,
                lines=[
                    {"account": 11, "entry_type": "DR", "amount": Decimal("10.00")},
                    {"account": 12, "entry_type": "CR", "amount": Decimal("10.00")},
                ],
                policy_controls={"cash_bank_mixed_entry_rule": "hard"},
            )

    @patch.object(VoucherService, "_account_ledger_id", return_value=501)
    def test_build_cash_bank_rows_creates_offset_pairs(self, mocked_ledger_id):
        header = VoucherHeader(
            voucher_type=VoucherHeader.VoucherType.CASH,
            cash_bank_account_id=55,
            cash_bank_ledger_id=77,
            narration="Main cash voucher",
        )

        rows = VoucherService._build_cash_bank_rows(
            header=header,
            lines=[
                {"account": 11, "entry_type": "DR", "amount": Decimal("25.00"), "narration": "Line A"},
                {"account": 12, "entry_type": "DR", "amount": Decimal("30.00"), "narration": ""},
            ],
        )

        self.assertEqual(len(rows), 4)
        self.assertFalse(rows[0].is_system_generated)
        self.assertTrue(rows[1].is_system_generated)
        self.assertEqual(rows[1].account_id, 55)
        self.assertEqual(rows[1].ledger_id, 77)
        self.assertEqual(rows[1].system_line_role, VoucherLine.SystemLineRole.CASH_OFFSET)
        self.assertEqual(rows[1].cr_amount, Decimal("25.00"))
        self.assertEqual(rows[1].narration, "Against Line A")
        self.assertEqual(rows[3].narration, "Against Main cash voucher")
        self.assertEqual(rows[0].ledger_id, 501)
        self.assertEqual(mocked_ledger_id.call_count, 2)


class VoucherNumberingRecoveryTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="voucher-numbering-user",
            email="voucher-numbering@example.com",
            password="pass@12345",
        )
        self.entity = Entity.objects.create(entityname="Voucher Numbering Entity", createdby=self.user)
        self.entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2026-27",
            finstartyear=timezone.now(),
            finendyear=timezone.now(),
            createdby=self.user,
        )
        self.subentity = SubEntity.objects.create(entity=self.entity, subentityname="Branch A", is_head_office=True)

    def test_current_doc_no_auto_seeds_missing_branch_series_from_voucher_scope(self):
        NumberingSeedService.seed_document(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=None,
            module="vouchers",
            doc_key="BANK_VOUCHER",
            name="Bank Voucher",
            default_code="BV",
            prefix="BV",
            start=4,
            padding=4,
        )

        payload = VoucherSettingsService.current_doc_no_for_type(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            voucher_type=VoucherHeader.VoucherType.BANK,
        )

        self.assertTrue(payload["enabled"])
        self.assertEqual(payload["current_number"], 1)
        bank_doc_type = DocumentType.objects.get(module="vouchers", doc_key="BANK_VOUCHER")
        self.assertTrue(
            DocumentNumberSeries.objects.filter(
                entity=self.entity,
                entityfinid=self.entityfin,
                subentity=self.subentity,
                doc_type=bank_doc_type,
                doc_code="BV",
            ).exists()
        )

    def test_confirm_voucher_auto_seeds_missing_branch_series_before_allocating_number(self):
        NumberingSeedService.seed_document(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=None,
            module="vouchers",
            doc_key="JOURNAL_VOUCHER",
            name="Journal Voucher",
            default_code="JV",
            prefix="JV",
            start=8,
            padding=4,
        )
        header = VoucherHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            voucher_type=VoucherHeader.VoucherType.JOURNAL,
            doc_code="JV",
            status=VoucherHeader.Status.DRAFT,
            total_debit_amount=Decimal("100.00"),
            total_credit_amount=Decimal("100.00"),
            created_by=self.user,
            voucher_date=timezone.localdate(),
        )

        result = VoucherService.confirm_voucher(header.id, confirmed_by_id=self.user.id)

        self.assertEqual(result.header.status, VoucherHeader.Status.CONFIRMED)
        self.assertEqual(result.header.doc_no, 1)
        self.assertTrue(str(result.header.voucher_code).startswith("JV-"))
        journal_doc_type = DocumentType.objects.get(module="vouchers", doc_key="JOURNAL_VOUCHER")
        self.assertTrue(
            DocumentNumberSeries.objects.filter(
                entity=self.entity,
                entityfinid=self.entityfin,
                subentity=self.subentity,
                doc_type=journal_doc_type,
                doc_code="JV",
            ).exists()
        )


class VoucherNumberingSeedCommandTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="voucher-seed-user",
            email="voucher-seed@example.com",
            password="pass@12345",
        )
        self.entity = Entity.objects.create(entityname="Voucher Seed Entity", createdby=self.user)
        self.entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2026-27",
            finstartyear=timezone.now(),
            finendyear=timezone.now(),
            createdby=self.user,
        )
        self.subentity = SubEntity.objects.create(entity=self.entity, subentityname="Branch A", is_head_office=True)

    def test_seed_voucher_numbering_without_subentity_seeds_root_and_branch_scopes(self):
        call_command(
            "seed_voucher_numbering",
            entity=self.entity.id,
            entityfinid=self.entityfin.id,
        )

        cash_doc_type = DocumentType.objects.get(module="vouchers", doc_key="CASH_VOUCHER")
        bank_doc_type = DocumentType.objects.get(module="vouchers", doc_key="BANK_VOUCHER")
        journal_doc_type = DocumentType.objects.get(module="vouchers", doc_key="JOURNAL_VOUCHER")

        self.assertTrue(
            DocumentNumberSeries.objects.filter(
                entity=self.entity,
                entityfinid=self.entityfin,
                subentity=None,
                doc_type=cash_doc_type,
                doc_code="CV",
            ).exists()
        )
        self.assertTrue(
            DocumentNumberSeries.objects.filter(
                entity=self.entity,
                entityfinid=self.entityfin,
                subentity=self.subentity,
                doc_type=cash_doc_type,
                doc_code="CV",
            ).exists()
        )
        self.assertTrue(
            DocumentNumberSeries.objects.filter(
                entity=self.entity,
                entityfinid=self.entityfin,
                subentity=None,
                doc_type=bank_doc_type,
                doc_code="BV",
            ).exists()
        )
        self.assertTrue(
            DocumentNumberSeries.objects.filter(
                entity=self.entity,
                entityfinid=self.entityfin,
                subentity=self.subentity,
                doc_type=bank_doc_type,
                doc_code="BV",
            ).exists()
        )
        self.assertTrue(
            DocumentNumberSeries.objects.filter(
                entity=self.entity,
                entityfinid=self.entityfin,
                subentity=None,
                doc_type=journal_doc_type,
                doc_code="JV",
            ).exists()
        )


class VoucherWorkflowPolicyTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="voucher-policy-user",
            email="voucher-policy@example.com",
            password="pass@12345",
        )
        self.approver = get_user_model().objects.create_user(
            username="voucher-policy-approver",
            email="voucher-policy-approver@example.com",
            password="pass@12345",
        )
        self.entity = Entity.objects.create(entityname="Voucher Policy Entity", createdby=self.user)
        self.entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2026-27",
            finstartyear=timezone.now(),
            finendyear=timezone.now(),
            createdby=self.user,
        )
        self.subentity = SubEntity.objects.create(entity=self.entity, subentityname="Head Office", is_head_office=True)

    def _header(self, *, status=VoucherHeader.Status.DRAFT, workflow_payload=None):
        return VoucherHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            voucher_type=VoucherHeader.VoucherType.JOURNAL,
            doc_code="JV",
            status=status,
            workflow_payload=workflow_payload or {},
            total_debit_amount=Decimal("100.00"),
            total_credit_amount=Decimal("100.00"),
            created_by=self.user,
            voucher_date=timezone.localdate(),
        )

    @patch("vouchers.services.voucher_service.VoucherSettingsService.get_policy")
    def test_update_voucher_blocks_submitted_edit_when_policy_locks_it(self, mocked_get_policy):
        header = self._header(
            workflow_payload={
                "_approval_state": {
                    "status": "SUBMITTED",
                    "submitted_by": self.user.id,
                }
            }
        )
        mocked_get_policy.return_value = SimpleNamespace(controls={"allow_edit_after_submit": "off"})

        with self.assertRaisesMessage(ValueError, "Submitted voucher is locked for edit by policy."):
            VoucherService.update_voucher(
                instance=header,
                data={
                    "narration": "Edited after submit",
                    "lines": [],
                },
            )

    @patch("vouchers.services.voucher_service.VoucherSettingsService.get_policy")
    def test_approve_voucher_blocks_same_submitter_when_policy_disallows_it(self, mocked_get_policy):
        header = self._header(
            workflow_payload={
                "_approval_state": {
                    "status": "SUBMITTED",
                    "submitted_by": self.user.id,
                }
            }
        )
        mocked_get_policy.return_value = SimpleNamespace(
            controls={
                "require_submit_before_approve": "on",
                "same_user_submit_approve": "off",
            }
        )

        with self.assertRaisesMessage(ValueError, "Approver must be different from submitter."):
            VoucherService.approve_voucher(header.id, approved_by_id=self.user.id, remarks="Self approval")

    @patch("vouchers.services.voucher_service.VoucherPostingAdapter.post_voucher")
    @patch("vouchers.services.voucher_service.VoucherSettingsService.get_policy")
    def test_post_voucher_requires_approved_state_when_maker_checker_is_hard(
        self,
        mocked_get_policy,
        mocked_post_voucher,
    ):
        header = self._header(
            status=VoucherHeader.Status.CONFIRMED,
            workflow_payload={
                "_approval_state": {
                    "status": "SUBMITTED",
                    "submitted_by": self.user.id,
                }
            },
        )
        mocked_get_policy.return_value = SimpleNamespace(
            controls={
                "require_confirm_before_post": "on",
                "voucher_maker_checker": "hard",
            }
        )

        with self.assertRaisesMessage(ValueError, "Voucher must be approved before posting by policy."):
            VoucherService.post_voucher(header.id, posted_by_id=self.user.id)

        mocked_post_voucher.assert_not_called()

    @patch("vouchers.services.voucher_service.VoucherPostingAdapter.post_voucher")
    @patch("vouchers.services.voucher_service.VoucherSettingsService.get_policy")
    def test_post_voucher_succeeds_after_approval_when_maker_checker_is_hard(
        self,
        mocked_get_policy,
        mocked_post_voucher,
    ):
        header = self._header(
            status=VoucherHeader.Status.CONFIRMED,
            workflow_payload={
                "_approval_state": {
                    "status": "APPROVED",
                    "submitted_by": self.user.id,
                    "approved_by": self.approver.id,
                }
            },
        )
        mocked_get_policy.return_value = SimpleNamespace(
            controls={
                "require_confirm_before_post": "on",
                "voucher_maker_checker": "hard",
            }
        )

        result = VoucherService.post_voucher(header.id, posted_by_id=self.approver.id)

        header.refresh_from_db()
        self.assertEqual(result.header.status, VoucherHeader.Status.POSTED)
        self.assertEqual(header.status, VoucherHeader.Status.POSTED)
        mocked_post_voucher.assert_called_once()

    @patch("vouchers.services.voucher_service.VoucherPostingAdapter.unpost_voucher")
    @patch("vouchers.services.voucher_service.VoucherSettingsService.get_policy")
    def test_unpost_voucher_returns_to_draft_when_policy_requests_draft(
        self,
        mocked_get_policy,
        mocked_unpost_voucher,
    ):
        header = self._header(status=VoucherHeader.Status.POSTED)
        mocked_get_policy.return_value = SimpleNamespace(controls={"unpost_target_status": "draft"})

        result = VoucherService.unpost_voucher(header.id, unposted_by_id=self.user.id)

        header.refresh_from_db()
        self.assertEqual(result.header.status, VoucherHeader.Status.DRAFT)
        self.assertEqual(header.status, VoucherHeader.Status.DRAFT)
        self.assertEqual(header.workflow_payload["_audit_log"][-1]["action"], "UNPOSTED")
        mocked_unpost_voucher.assert_called_once()


class VoucherWriteSerializerValidationTests(SimpleTestCase):
    def test_journal_voucher_rejects_cash_bank_account(self):
        serializer = VoucherWriteSerializer()

        with self.assertRaisesMessage(Exception, "cash_bank_account must be blank for journal vouchers."):
            serializer.validate(
                {
                    "voucher_type": VoucherHeader.VoucherType.JOURNAL,
                    "cash_bank_account": 10,
                    "lines": [],
                }
            )

    def test_cash_voucher_rejects_journal_amount_shape(self):
        serializer = VoucherWriteSerializer()

        with self.assertRaisesMessage(Exception, "Line 1: use entry_type/amount for cash/bank vouchers."):
            serializer.validate(
                {
                    "voucher_type": VoucherHeader.VoucherType.CASH,
                    "cash_bank_account": 10,
                    "lines": [{"dr_amount": Decimal("10.00")}],
                }
            )


class VoucherViewUnitTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = SimpleNamespace(is_authenticated=True, id=7)
        self.header = SimpleNamespace(
            id=12,
            entity_id=1,
            voucher_type=VoucherHeader.VoucherType.JOURNAL,
        )

    def _build_request(self, path: str, payload: dict | None = None):
        request = self.factory.post(path, payload or {}, format="json")
        force_authenticate(request, user=self.user)
        return request

    @patch("errorlogger.drf_exception_handler.ErrorLog.objects.create")
    @patch("vouchers.views.voucher.VoucherService.confirm_voucher")
    @patch.object(VoucherConfirmAPIView, "_require")
    @patch.object(VoucherConfirmAPIView, "_get_header")
    def test_confirm_view_returns_structured_validation_error_payload(
        self,
        mocked_get_header,
        mocked_require,
        mocked_confirm,
        mocked_error_log,
    ):
        mocked_get_header.return_value = self.header
        mocked_confirm.side_effect = ValueError({"lines": ["At least one valid line is required."]})

        request = self._build_request("/api/vouchers/vouchers/12/confirm/?entity=1&entityfinid=1")

        response = VoucherConfirmAPIView.as_view()(request, pk=12)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"lines": ["At least one valid line is required."]})
        mocked_require.assert_called_once_with(self.header, "confirm")
        mocked_error_log.assert_called_once()

    @patch("vouchers.views.voucher.VoucherDetailSerializer")
    @patch("vouchers.views.voucher.VoucherService.post_voucher")
    @patch.object(VoucherPostAPIView, "_require")
    @patch.object(VoucherPostAPIView, "_get_header")
    def test_post_view_returns_serialized_data(
        self,
        mocked_get_header,
        mocked_require,
        mocked_post,
        mocked_serializer_cls,
    ):
        mocked_get_header.return_value = self.header
        mocked_post.return_value = VoucherResult(header=self.header, message="Voucher posted.")
        mocked_serializer_cls.return_value.data = {"id": 12, "status_name": "Posted"}

        request = self._build_request("/api/vouchers/vouchers/12/post/?entity=1&entityfinid=1")

        response = VoucherPostAPIView.as_view()(request, pk=12)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["message"], "Voucher posted.")
        self.assertEqual(response.data["notice"], "Voucher posted.")
        self.assertEqual(response.data["warnings"], [])
        self.assertEqual(response.data["data"], {"id": 12, "status_name": "Posted"})
        mocked_require.assert_called_once_with(self.header, "post")
        mocked_post.assert_called_once_with(12, posted_by_id=7)

    @patch("vouchers.views.voucher.VoucherDetailSerializer")
    @patch("vouchers.views.voucher.VoucherService.submit_voucher")
    @patch.object(VoucherApprovalAPIView, "_require")
    @patch.object(VoucherApprovalAPIView, "_get_header")
    def test_approval_submit_view_passes_remarks_and_returns_approval_status(
        self,
        mocked_get_header,
        mocked_require,
        mocked_submit,
        mocked_serializer_cls,
    ):
        mocked_get_header.return_value = self.header
        mocked_submit.return_value = VoucherResult(header=self.header, message="Voucher submitted.")
        mocked_serializer_cls.return_value.data = {
            "id": 12,
            "approval_status": "SUBMITTED",
            "approval_status_name": "Submitted",
        }

        request = self._build_request(
            "/api/vouchers/vouchers/12/approval/?entity=1&entityfinid=1",
            {"action": "submit", "remarks": "Ready for approval"},
        )

        response = VoucherApprovalAPIView.as_view()(request, pk=12)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["approval_status"], "SUBMITTED")
        self.assertEqual(response.data["approval_status_name"], "Submitted")
        mocked_require.assert_called_once_with(self.header, "submit")
        mocked_submit.assert_called_once_with(12, submitted_by_id=7, remarks="Ready for approval")

    @patch("vouchers.views.voucher.VoucherDetailSerializer")
    @patch("vouchers.views.voucher.VoucherService.cancel_voucher")
    @patch.object(VoucherCancelAPIView, "_require")
    @patch.object(VoucherCancelAPIView, "_get_header")
    def test_cancel_view_passes_reason(
        self,
        mocked_get_header,
        mocked_require,
        mocked_cancel,
        mocked_serializer_cls,
    ):
        mocked_get_header.return_value = self.header
        mocked_cancel.return_value = VoucherResult(header=self.header, message="Voucher cancelled.")
        mocked_serializer_cls.return_value.data = {"id": 12, "status_name": "Cancelled"}

        request = self._build_request(
            "/api/vouchers/vouchers/12/cancel/?entity=1&entityfinid=1",
            {"reason": "Created in error"},
        )

        response = VoucherCancelAPIView.as_view()(request, pk=12)

        self.assertEqual(response.status_code, 200)
        mocked_require.assert_called_once_with(self.header, "cancel")
        mocked_cancel.assert_called_once_with(12, cancelled_by_id=7, reason="Created in error")

    @patch("errorlogger.drf_exception_handler.ErrorLog.objects.create")
    @patch("vouchers.views.voucher.VoucherService.unpost_voucher")
    @patch.object(VoucherUnpostAPIView, "_require")
    @patch.object(VoucherUnpostAPIView, "_get_header")
    def test_unpost_view_wraps_string_validation_error_as_non_field_errors(
        self,
        mocked_get_header,
        mocked_require,
        mocked_unpost,
        mocked_error_log,
    ):
        mocked_get_header.return_value = self.header
        mocked_unpost.side_effect = ValueError("Only posted vouchers can be unposted.")

        request = self._build_request("/api/vouchers/vouchers/12/unpost/?entity=1&entityfinid=1")

        response = VoucherUnpostAPIView.as_view()(request, pk=12)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"non_field_errors": ["Only posted vouchers can be unposted."]})
        mocked_require.assert_called_once_with(self.header, "unpost")
        mocked_error_log.assert_called_once()

    @patch("errorlogger.drf_exception_handler.ErrorLog.objects.create")
    def test_list_view_reports_missing_scope_as_field_errors(self, mocked_error_log):
        request = self._build_request("/api/vouchers/vouchers/")

        response = VoucherListCreateAPIView.as_view()(request)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(str(response.data["entity"][0]), "This field is required.")
        self.assertEqual(str(response.data["entityfinid"][0]), "This field is required.")
        mocked_error_log.assert_called_once()

    @patch("errorlogger.drf_exception_handler.ErrorLog.objects.create")
    @patch.object(VoucherApprovalAPIView, "_require")
    @patch.object(VoucherApprovalAPIView, "_get_header")
    def test_approval_view_reports_invalid_action_on_action_field(
        self,
        mocked_get_header,
        mocked_require,
        mocked_error_log,
    ):
        mocked_get_header.return_value = self.header
        request = self._build_request(
            "/api/vouchers/vouchers/12/approval/?entity=1&entityfinid=1",
            {"action": "ship"},
        )

        response = VoucherApprovalAPIView.as_view()(request, pk=12)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(str(response.data["action"]), "Use submit, approve, or reject.")
        mocked_require.assert_not_called()
        mocked_error_log.assert_called_once()

    @patch("vouchers.views.voucher.VoucherHeader.objects.filter")
    def test_duplicate_reference_warnings_returns_warning_message(self, mocked_filter):
        mocked_values = mocked_filter.return_value.filter.return_value.exclude.return_value.order_by.return_value.values.return_value
        mocked_values.first.return_value = {"voucher_code": "BV-88", "doc_no": 88, "id": 88}

        warnings = _duplicate_reference_warnings(
            instance_id=12,
            entity_id=1,
            entityfinid_id=1,
            subentity_id=5,
            voucher_type="BANK",
            reference_number="UTR-1",
        )

        self.assertEqual(warnings, ["Reference number already exists on voucher BV-88."])

    @patch("vouchers.views.voucher.VoucherHeader.objects.filter")
    def test_duplicate_reference_warnings_returns_empty_for_blank_reference(self, mocked_filter):
        warnings = _duplicate_reference_warnings(
            instance_id=None,
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            voucher_type="BANK",
            reference_number="  ",
        )

        self.assertEqual(warnings, [])
        mocked_filter.assert_not_called()
