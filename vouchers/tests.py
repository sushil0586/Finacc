from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from vouchers.models import VoucherHeader, VoucherLine
from vouchers.serializers.voucher import VoucherWriteSerializer
from vouchers.services.voucher_service import VoucherResult, VoucherService
from vouchers.views.voucher import (
    VoucherListCreateAPIView,
    VoucherApprovalAPIView,
    VoucherCancelAPIView,
    VoucherConfirmAPIView,
    VoucherPostAPIView,
    VoucherUnpostAPIView,
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
