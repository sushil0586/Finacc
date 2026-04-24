from types import SimpleNamespace
from decimal import Decimal
from unittest.mock import patch
from datetime import date

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.exceptions import ValidationError

from sales.models import SalesInvoiceHeader, SalesSettings
from sales.services.sales_invoice_service import SalesInvoiceService
from sales.services.sales_stock_balance_service import SalesStockBalanceService
from sales.services.sales_withholding_service import SalesWithholdingService
from sales.services.irp_payload_builder import IRPPayloadBuilder
from sales.services.compliance_error_catalog_service import ComplianceErrorCatalogService
from sales.services.eway_payload_builder import EWayInput, build_generate_eway_payload
from sales.services.sales_compliance_service import SalesComplianceService
from sales.services.sales_nav_service import SalesInvoiceNavService
from sales.services.sales_settings_service import SalesSettingsService
from sales.services.providers.mastergst import _extract_error
from sales.views.sales_invoice_views import (
    SalesInvoiceCancelAPIView,
    SalesInvoiceConfirmAPIView,
    SalesInvoiceListCreateAPIView,
    SalesInvoicePostAPIView,
    SalesInvoiceReverseAPIView,
    SalesInvoiceRetrieveUpdateAPIView,
)
from sales.views.sales_ar_exports import CustomerStatementExcelAPIView


class SalesInvoiceServiceUnitTests(SimpleTestCase):
    @patch("sales.services.sales_withholding_service.WithholdingResolver.get_entity_config")
    def test_compute_tcs_skips_when_entity_config_disables_tcs(self, mocked_get_cfg):
        mocked_get_cfg.return_value = SimpleNamespace(enable_tcs=False, apply_tcs_206c1h=False)
        header = SimpleNamespace(
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            tcs_section=SimpleNamespace(section_code="206C(1)", rate_default=Decimal("0.1000")),
        )

        res = SalesWithholdingService.compute_tcs(
            header=header,
            customer_account_id=10,
            invoice_date=date(2026, 4, 1),
            taxable_total=Decimal("1000.00"),
            gross_total=Decimal("1180.00"),
        )
        self.assertFalse(res.enabled)
        self.assertEqual(res.amount, Decimal("0.00"))
        self.assertEqual(res.reason_code, "DISABLED")

    @patch("sales.services.sales_withholding_service.WithholdingResolver.get_entity_config")
    def test_compute_tcs_disables_206c1h_by_config(self, mocked_get_cfg):
        mocked_get_cfg.return_value = SimpleNamespace(enable_tcs=True, apply_tcs_206c1h=False)
        header = SimpleNamespace(
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            tcs_section=SimpleNamespace(section_code="206C(1H)", rate_default=Decimal("0.1000")),
        )

        res = SalesWithholdingService.compute_tcs(
            header=header,
            customer_account_id=10,
            invoice_date=date(2026, 4, 1),
            taxable_total=Decimal("1000.00"),
            gross_total=Decimal("1180.00"),
        )
        self.assertTrue(res.enabled)
        self.assertEqual(res.amount, Decimal("0.00"))
        self.assertEqual(res.reason_code, "DISABLED_206C_1H_BY_CONFIG")

    @patch("sales.services.sales_withholding_service.WithholdingResolver.get_entity_config")
    def test_compute_tcs_skips_payment_based_section_in_invoice_context(self, mocked_get_cfg):
        mocked_get_cfg.return_value = SimpleNamespace(enable_tcs=True, apply_tcs_206c1h=True)
        header = SimpleNamespace(
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            tcs_section=SimpleNamespace(section_code="194N", base_rule=4, rate_default=Decimal("2.0000")),
        )

        res = SalesWithholdingService.compute_tcs(
            header=header,
            customer_account_id=10,
            invoice_date=date(2026, 4, 1),
            taxable_total=Decimal("1000.00"),
            gross_total=Decimal("1180.00"),
        )

        self.assertTrue(res.enabled)
        self.assertEqual(res.amount, Decimal("0.00"))
        self.assertEqual(res.reason_code, "NOT_APPLICABLE_BASE_RULE_CONTEXT")

    def test_reverse_move_type(self):
        self.assertEqual(SalesInvoiceService._reverse_move_type("IN"), "OUT")
        self.assertEqual(SalesInvoiceService._reverse_move_type("OUT"), "IN")
        self.assertEqual(SalesInvoiceService._reverse_move_type("ADJ"), "REV")

    @patch("sales.services.sales_invoice_service.resolve_posting_location_id", return_value=5)
    @patch("sales.services.sales_invoice_service.SalesInvoiceService._build_stock_balance_maps")
    @patch("sales.services.sales_invoice_service.SalesInvoiceService._stock_policy")
    @patch("sales.services.sales_invoice_service.Product.objects")
    def test_validate_stock_policy_blocks_shortage_when_negative_stock_disabled(
        self,
        mocked_product_objects,
        mocked_stock_policy,
        mocked_build_maps,
        mocked_resolve_location,
    ):
        mocked_stock_policy.return_value = SimpleNamespace(
            mode="STRICT",
            allow_negative_stock=False,
            expiry_validation_required=False,
            fefo_required=False,
            allow_manual_batch_override=True,
        )
        mocked_build_maps.return_value = (
            {(1, "B1", 5): Decimal("1.0000")},
            {},
        )
        mocked_product_qs = mocked_product_objects.filter.return_value.only.return_value
        mocked_product_qs.__iter__.return_value = iter([
            SimpleNamespace(
                id=1,
                productname="A-B",
                is_service=False,
                is_batch_managed=True,
                is_expiry_tracked=False,
            )
        ])

        header = SimpleNamespace(
            entity_id=1,
            entityfinid_id=1,
            subentity_id=1,
            doc_type=int(SalesInvoiceHeader.DocType.TAX_INVOICE),
            bill_date=date(2026, 4, 13),
            location_id=5,
            godown_id=None,
        )
        lines = [
            SimpleNamespace(
                product_id=1,
                qty=Decimal("2.000"),
                free_qty=Decimal("0.000"),
                batch_number="B1",
                expiry_date=date(2026, 5, 1),
                line_no=1,
            )
        ]

        with self.assertRaisesMessage(ValidationError, "insufficient stock"):
            SalesInvoiceService._validate_stock_policy_on_post(header=header, lines=lines)

        self.assertTrue(mocked_resolve_location.called)

    @patch("sales.services.sales_invoice_service.resolve_posting_location_id", return_value=5)
    @patch("sales.services.sales_invoice_service.SalesInvoiceService._build_stock_balance_maps")
    @patch("sales.services.sales_invoice_service.SalesInvoiceService._stock_policy")
    @patch("sales.services.sales_invoice_service.Product.objects")
    def test_allocate_batches_auto_picks_earliest_available_batch(
        self,
        mocked_product_objects,
        mocked_stock_policy,
        mocked_build_maps,
        mocked_resolve_location,
    ):
        mocked_stock_policy.return_value = SimpleNamespace(
            mode="STRICT",
            allow_negative_stock=False,
            batch_required_for_sales=True,
            expiry_validation_required=True,
            fefo_required=True,
            allow_manual_batch_override=False,
        )
        mocked_build_maps.return_value = (
            {(1, "B-A", 5): Decimal("3.0000"), (1, "B-B", 5): Decimal("4.0000")},
            {
                (1, "B-B", 5, date(2026, 6, 1)): Decimal("4.0000"),
                (1, "B-A", 5, date(2026, 5, 1)): Decimal("3.0000"),
            },
        )
        mocked_product_qs = mocked_product_objects.filter.return_value.only.return_value
        mocked_product_qs.__iter__.return_value = iter([
            SimpleNamespace(
                id=1,
                productname="A-B",
                is_service=False,
                is_batch_managed=True,
                is_expiry_tracked=True,
            )
        ])

        saved = []

        class Line:
            product_id = 1
            qty = Decimal("1.000")
            free_qty = Decimal("0.000")
            batch_number = ""
            manufacture_date = None
            expiry_date = None
            line_no = 1

            def save(self, update_fields=None):
                saved.append(list(update_fields or []))

        header = SimpleNamespace(
            entity_id=1,
            entityfinid_id=1,
            subentity_id=1,
            doc_type=int(SalesInvoiceHeader.DocType.TAX_INVOICE),
            bill_date=date(2026, 4, 13),
            location_id=5,
            godown_id=None,
        )

        line = Line()
        SalesInvoiceService._allocate_batches_for_post(header=header, lines=[line])

        self.assertEqual(line.batch_number, "B-A")
        self.assertEqual(line.expiry_date, date(2026, 5, 1))
        self.assertTrue(saved)
        self.assertIn("batch_number", saved[0])

    def test_recompute_settlement_fields_open(self):
        header = SimpleNamespace(
            grand_total=Decimal("1000.00"),
            tcs_amount=Decimal("20.00"),
            settled_amount=Decimal("0.00"),
            settlement_status=None,
            outstanding_amount=None,
        )
        SalesInvoiceService.recompute_settlement_fields(header=header)
        self.assertEqual(header.outstanding_amount, Decimal("1020.00"))
        self.assertEqual(header.settlement_status, int(SalesInvoiceHeader.SettlementStatus.OPEN))

    def test_recompute_settlement_fields_partial(self):
        header = SimpleNamespace(
            grand_total=Decimal("1000.00"),
            tcs_amount=Decimal("20.00"),
            settled_amount=Decimal("500.00"),
            settlement_status=None,
            outstanding_amount=None,
        )
        SalesInvoiceService.recompute_settlement_fields(header=header)
        self.assertEqual(header.outstanding_amount, Decimal("520.00"))
        self.assertEqual(header.settlement_status, int(SalesInvoiceHeader.SettlementStatus.PARTIAL))

    def test_recompute_settlement_fields_settled_caps_to_gross(self):
        header = SimpleNamespace(
            grand_total=Decimal("1000.00"),
            tcs_amount=Decimal("20.00"),
            settled_amount=Decimal("2000.00"),
            settlement_status=None,
            outstanding_amount=None,
        )
        SalesInvoiceService.recompute_settlement_fields(header=header)
        self.assertEqual(header.settled_amount, Decimal("1020.00"))
        self.assertEqual(header.outstanding_amount, Decimal("0.00"))
        self.assertEqual(header.settlement_status, int(SalesInvoiceHeader.SettlementStatus.SETTLED))

    def test_validate_doc_linkage_cn_requires_original(self):
        with self.assertRaisesMessage(ValueError, "original_invoice is required"):
            SalesInvoiceService._validate_doc_linkage(
                doc_type=int(SalesInvoiceHeader.DocType.CREDIT_NOTE),
                original_invoice=None,
                entity_id=1,
                entityfinid_id=1,
                subentity_id=None,
                customer_id=10,
            )

    def test_align_note_tax_scope_from_original_invoice(self):
        header_data = {
            "seller_gstin": "22AAAAA0000A1Z5",
            "seller_state_code": "22",
            "place_of_supply_state_code": "22",
        }
        original = SimpleNamespace(
            seller_gstin="03BNDPG2450J1Z3",
            seller_state_code="03",
            place_of_supply_state_code="0",
        )

        SalesInvoiceService._align_note_tax_scope_from_original_invoice(
            header_data=header_data,
            original_invoice=original,
        )

        self.assertEqual(header_data["seller_gstin"], "03BNDPG2450J1Z3")
        self.assertEqual(header_data["seller_state_code"], "03")
        self.assertEqual(header_data["place_of_supply_state_code"], "0")

    def test_validate_doc_linkage_tax_invoice_disallows_original(self):
        original = SimpleNamespace(entity_id=1, entityfinid_id=1, subentity_id=None, customer_id=10)
        with self.assertRaisesMessage(ValueError, "allowed only for Credit Note / Debit Note"):
            SalesInvoiceService._validate_doc_linkage(
                doc_type=int(SalesInvoiceHeader.DocType.TAX_INVOICE),
                original_invoice=original,
                entity_id=1,
                entityfinid_id=1,
                subentity_id=None,
                customer_id=10,
            )

    def test_validate_b2b_gstin_requirements_blocks_missing_customer_gstin(self):
        header = SimpleNamespace(
            supply_category=int(SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B),
            seller_gstin="22AAAAA0000A1Z5",
            customer_gstin="",
        )
        with self.assertRaisesMessage(ValueError, "customer_gstin"):
            SalesInvoiceService._validate_b2b_gstin_requirements(header=header)

    def test_derive_compliance_flags_auto(self):
        header = SimpleNamespace(
            supply_category=int(SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B),
            seller_gstin="22AAAAA0000A1Z5",
            customer_gstin="27BBBBB1111B2Z6",
            grand_total=Decimal("75000.00"),
            einvoice_applicable_manual=None,
            eway_applicable_manual=None,
            compliance_override_reason="",
            compliance_override_at=None,
            compliance_override_by=None,
            is_einvoice_applicable=False,
            is_eway_applicable=False,
            gst_compliance_mode=int(SalesInvoiceHeader.GstComplianceMode.NONE),
        )
        settings_obj = SalesSettings(
            enable_einvoice=True,
            enable_eway=True,
            einvoice_entity_applicable=True,
            eway_value_threshold=Decimal("50000.00"),
            compliance_applicability_mode=SalesSettings.ComplianceApplicabilityMode.AUTO_ONLY,
        )
        SalesInvoiceService._derive_compliance_flags(header=header, settings_obj=settings_obj, user=None)
        self.assertTrue(header.is_einvoice_applicable)
        self.assertTrue(header.is_eway_applicable)
        self.assertEqual(header.gst_compliance_mode, int(SalesInvoiceHeader.GstComplianceMode.EINVOICE_AND_EWAY))

    def test_derive_compliance_flags_manual_requires_reason(self):
        header = SimpleNamespace(
            supply_category=int(SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B),
            seller_gstin="22AAAAA0000A1Z5",
            customer_gstin="27BBBBB1111B2Z6",
            grand_total=Decimal("1000.00"),
            einvoice_applicable_manual=True,
            eway_applicable_manual=None,
            compliance_override_reason="",
            compliance_override_at=None,
            compliance_override_by=None,
        )
        settings_obj = SalesSettings(
            enable_einvoice=True,
            enable_eway=True,
            einvoice_entity_applicable=False,
            eway_value_threshold=Decimal("50000.00"),
            compliance_applicability_mode=SalesSettings.ComplianceApplicabilityMode.AUTO_WITH_OVERRIDE,
        )
        with self.assertRaisesMessage(ValueError, "compliance_override_reason"):
            SalesInvoiceService._derive_compliance_flags(header=header, settings_obj=settings_obj, user=None)

    @patch("sales.services.sales_invoice_service.SalesInvoiceService.get_settings")
    def test_apply_tcs_credit_note_disallow_policy(self, mocked_get_settings):
        mocked_get_settings.return_value = SimpleNamespace(tcs_credit_note_policy="DISALLOW")
        section = SimpleNamespace(section_code="206C(1)", rate_default=Decimal("0.1000"))

        class Header:
            withholding_enabled = True
            doc_type = int(SalesInvoiceHeader.DocType.CREDIT_NOTE)
            tcs_section = section
            tcs_section_id = 1
            tcs_rate = Decimal("0.1000")
            tcs_base_amount = Decimal("100.00")
            tcs_amount = Decimal("10.00")
            tcs_reason = ""
            tcs_is_reversal = False
            entity_id = 1
            subentity_id = None
            customer_id = 1
            bill_date = None

            def save(self, **kwargs):
                return None

        h = Header()
        SalesInvoiceService._apply_tcs(header=h, user=None)
        self.assertEqual(h.tcs_amount, Decimal("0.00"))
        self.assertIn("disallowed", (h.tcs_reason or "").lower())

    @patch("sales.services.sales_invoice_service.SalesInvoiceHeader.objects")
    def test_validate_adjustment_caps_blocks_excess(self, mocked_hdr_objects):
        original = SimpleNamespace(
            id=100,
            total_taxable_value=Decimal("100.00"),
            total_cgst=Decimal("9.00"),
            total_sgst=Decimal("9.00"),
            total_igst=Decimal("0.00"),
            total_cess=Decimal("0.00"),
            grand_total=Decimal("118.00"),
        )
        header = SimpleNamespace(
            id=101,
            doc_type=int(SalesInvoiceHeader.DocType.CREDIT_NOTE),
            original_invoice_id=100,
            original_invoice=original,
            total_taxable_value=Decimal("40.00"),
            total_cgst=Decimal("3.60"),
            total_sgst=Decimal("3.60"),
            total_igst=Decimal("0.00"),
            total_cess=Decimal("0.00"),
            grand_total=Decimal("47.20"),
        )

        qs = mocked_hdr_objects.filter.return_value.exclude.return_value
        qs.exclude.return_value = qs
        qs.aggregate.return_value = {
            "taxable": Decimal("70.00"),
            "cgst": Decimal("6.30"),
            "sgst": Decimal("6.30"),
            "igst": Decimal("0.00"),
            "cess": Decimal("0.00"),
            "grand": Decimal("82.60"),
        }
        with self.assertRaisesMessage(ValueError, "cumulative"):
            SalesInvoiceService._validate_adjustment_caps(header=header)

    @patch("sales.services.sales_invoice_service.SalesInvoiceService.get_settings")
    @patch("sales.services.sales_invoice_service.ComplianceAuditService")
    @patch("sales.services.sales_invoice_service.SalesInvoiceService.reverse_posting")
    def test_cancel_blocked_when_statutory_not_cancelled(self, mocked_reverse, mocked_audit, mocked_get_settings):
        mocked_get_settings.return_value = SimpleNamespace(enforce_statutory_cancel_before_business_cancel=True)
        header = SimpleNamespace(
            status=int(SalesInvoiceHeader.Status.CONFIRMED),
            entity_id=1,
            subentity_id=None,
            einvoice_artifact=SimpleNamespace(status=2, irn="x"),
            eway_artifact=SimpleNamespace(status=2, ewb_no="y"),
        )
        with self.assertRaisesMessage(ValueError, "generated but not cancelled"):
            SalesInvoiceService.cancel.__func__.__wrapped__(SalesInvoiceService, header=header, user=None, reason="")
        mocked_reverse.assert_not_called()
        self.assertTrue(mocked_audit.log_action.called)
        self.assertTrue(mocked_audit.open_exception.called)


class SalesStockBalanceServiceUnitTests(SimpleTestCase):
    @patch("sales.services.sales_stock_balance_service.Godown.objects.filter")
    @patch("sales.services.sales_stock_balance_service.SalesStockBalanceService._build_balance_maps")
    @patch("sales.services.sales_stock_balance_service.resolve_posting_location_id", return_value=5)
    def test_relaxed_mode_skips_shortage_hint_when_no_other_stock_rules(
        self,
        mocked_resolve_location,
        mocked_build_maps,
        mocked_godown_filter,
    ):
        mocked_godown_filter.return_value.values_list.return_value.first.return_value = "Main Location"
        policy = SimpleNamespace(
            mode="RELAXED",
            allow_negative_stock=True,
            batch_required_for_sales=False,
            expiry_validation_required=False,
            fefo_required=False,
            allow_manual_batch_override=True,
        )
        product = SimpleNamespace(id=10, productname="P-1", is_service=False)

        hint = SalesStockBalanceService.build_hint(
            entity_id=1,
            entityfinid_id=1,
            subentity_id=1,
            bill_date=date(2026, 4, 16),
            product=product,
            requested_qty=Decimal("10.0000"),
            batch_number="",
            expiry_date=None,
            location_id=5,
            policy=policy,
        )

        self.assertEqual(hint["status"], "info")
        self.assertEqual(hint["message"], "")
        self.assertIsNone(hint["available_qty"])
        self.assertIsNone(hint["shortage_qty"])
        mocked_build_maps.assert_not_called()
        self.assertTrue(mocked_resolve_location.called)

    @patch("sales.services.sales_stock_balance_service.Godown.objects.filter")
    @patch("sales.services.sales_stock_balance_service.SalesStockBalanceService._best_batch", return_value=None)
    @patch(
        "sales.services.sales_stock_balance_service.SalesStockBalanceService._build_balance_maps",
        return_value=({}, {}, Decimal("3.0000")),
    )
    @patch("sales.services.sales_stock_balance_service.resolve_posting_location_id", return_value=5)
    def test_controlled_mode_returns_warning_for_location_shortage(
        self,
        mocked_resolve_location,
        mocked_build_maps,
        mocked_best_batch,
        mocked_godown_filter,
    ):
        mocked_godown_filter.return_value.values_list.return_value.first.return_value = "Main Location"
        policy = SimpleNamespace(
            mode="CONTROLLED",
            allow_negative_stock=True,
            batch_required_for_sales=False,
            expiry_validation_required=False,
            fefo_required=False,
            allow_manual_batch_override=True,
        )
        product = SimpleNamespace(id=10, productname="P-1", is_service=False)

        hint = SalesStockBalanceService.build_hint(
            entity_id=1,
            entityfinid_id=1,
            subentity_id=1,
            bill_date=date(2026, 4, 16),
            product=product,
            requested_qty=Decimal("5.0000"),
            batch_number="",
            expiry_date=None,
            location_id=5,
            policy=policy,
        )

        self.assertEqual(hint["status"], "warning")
        self.assertIn("Only 3.0000 available", hint["message"])
        mocked_build_maps.assert_called_once()
        mocked_best_batch.assert_called_once()
        self.assertTrue(mocked_resolve_location.called)


class SalesInvoiceViewUnitTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = SimpleNamespace(is_authenticated=True, id=7)
        self.header = SimpleNamespace(entity_id=1, doc_type=int(SalesInvoiceHeader.DocType.TAX_INVOICE))

    def _build_request(self, path: str, payload: dict | None = None):
        request = self.factory.post(path, payload or {}, format="json")
        force_authenticate(request, user=self.user)
        return request

    def _build_put_request(self, path: str, payload: dict | None = None):
        request = self.factory.put(path, payload or {}, format="json")
        force_authenticate(request, user=self.user)
        return request

    def _build_patch_request(self, path: str, payload: dict | None = None):
        request = self.factory.patch(path, payload or {}, format="json")
        force_authenticate(request, user=self.user)
        return request

    def _assert_serializer_context(self, mocked_serializer_cls, *, expected_line_mode: str):
        _, serializer_kwargs = mocked_serializer_cls.call_args
        serializer_request = serializer_kwargs["context"]["request"]
        self.assertEqual(serializer_request.method, "POST")
        self.assertEqual(serializer_request.query_params.get("line_mode"), expected_line_mode)
        self.assertEqual(serializer_kwargs["context"]["line_mode"], expected_line_mode)

    @patch("sales.views.sales_invoice_views.require_sales_request_permission")
    def test_list_queryset_uses_exists_for_line_mode_filter(self, mocked_require_permission):
        request = self.factory.get("/api/sales/invoices/?entity=1&line_mode=goods")
        force_authenticate(request, user=self.user)

        view = SalesInvoiceListCreateAPIView()
        view.request = view.initialize_request(request)

        queryset = view.get_queryset()
        sql = str(queryset.query).upper()

        self.assertIn("EXISTS(", sql)
        self.assertNotIn(" DISTINCT ", sql)

    @patch("sales.views.sales_invoice_views.require_sales_request_permission")
    def test_list_queryset_selects_customer_related_ledger(self, mocked_require_permission):
        request = self.factory.get("/api/sales/invoices/?entity=1")
        force_authenticate(request, user=self.user)

        view = SalesInvoiceListCreateAPIView()
        view.request = view.initialize_request(request)

        queryset = view.get_queryset()
        select_related = queryset.query.select_related

        self.assertIn("customer", select_related)
        self.assertIn("ledger", select_related["customer"])
        self.assertIn("subentity", select_related)

    def test_nav_scope_queryset_uses_exists_for_line_mode_filter(self):
        queryset = SalesInvoiceNavService._scope_qs(
            entity_id=1,
            entityfinid_id=1,
            subentity_id=None,
            doc_type=int(SalesInvoiceHeader.DocType.TAX_INVOICE),
            doc_code="SI",
            allowed_statuses=SalesInvoiceNavService.DEFAULT_ALLOWED_STATUSES,
            line_mode="goods",
        )
        sql = str(queryset.query).upper()
        self.assertIn("EXISTS(", sql)
        self.assertNotIn(" DISTINCT ", sql)

    def test_last_saved_doc_scope_queryset_uses_subentity_isnull(self):
        with patch("sales.services.sales_settings_service.SalesInvoiceHeader.objects.filter") as mocked_filter:
            mocked_filter.return_value.only.return_value.order_by.return_value.first.return_value = None

            SalesSettingsService._last_saved_doc_in_scope(
                entity_id=10,
                entityfinid_id=8,
                subentity_id=None,
                doc_type=int(SalesInvoiceHeader.DocType.TAX_INVOICE),
            )

        mocked_filter.assert_called_once_with(
            entity_id=10,
            entityfinid_id=8,
            doc_type=int(SalesInvoiceHeader.DocType.TAX_INVOICE),
            subentity_id__isnull=True,
        )

    @patch("sales.views.sales_invoice_views.require_sales_request_permission")
    @patch("sales.views.sales_invoice_views.SalesInvoiceService.confirm")
    @patch("sales.views.sales_invoice_views.SalesInvoiceHeaderSerializer")
    @patch.object(SalesInvoiceConfirmAPIView, "_get_scoped_header")
    def test_confirm_view_serializes_with_line_mode_context(
        self,
        mocked_get_header,
        mocked_serializer_cls,
        mocked_confirm,
        mocked_require_permission,
    ):
        mocked_get_header.return_value = self.header
        mocked_confirm.return_value = self.header
        mocked_serializer_cls.return_value.data = {"id": 10, "status_name": "Confirmed"}

        request = self._build_request("/api/sales/invoices/10/confirm/?line_mode=service")

        response = SalesInvoiceConfirmAPIView.as_view()(request, pk=10)

        self.assertEqual(response.status_code, 200)
        mocked_require_permission.assert_called_once()
        mocked_confirm.assert_called_once_with(header=self.header, user=self.user)
        self._assert_serializer_context(mocked_serializer_cls, expected_line_mode="service")

    @patch("sales.views.sales_invoice_views.require_sales_request_permission")
    @patch("sales.views.sales_invoice_views.SalesInvoiceService.confirm")
    @patch.object(SalesInvoiceConfirmAPIView, "_get_scoped_header")
    def test_confirm_view_returns_structured_validation_error_payload(
        self,
        mocked_get_header,
        mocked_confirm,
        mocked_require_permission,
    ):
        mocked_get_header.return_value = self.header
        mocked_confirm.side_effect = ValidationError({"customer": ["GSTIN is required."]})

        request = self._build_request("/api/sales/invoices/10/confirm/?line_mode=goods")

        response = SalesInvoiceConfirmAPIView.as_view()(request, pk=10)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"customer": ["GSTIN is required."]})
        mocked_require_permission.assert_called_once()

    @patch("sales.views.sales_invoice_views.require_sales_request_permission")
    @patch("sales.views.sales_invoice_views.SalesInvoiceService.post")
    @patch("sales.views.sales_invoice_views.SalesInvoiceHeaderSerializer")
    @patch.object(SalesInvoicePostAPIView, "_get_scoped_header")
    def test_post_view_serializes_with_line_mode_context(
        self,
        mocked_get_header,
        mocked_serializer_cls,
        mocked_post,
        mocked_require_permission,
    ):
        mocked_get_header.return_value = self.header
        mocked_post.return_value = self.header
        mocked_serializer_cls.return_value.data = {"id": 10, "status_name": "Posted"}

        request = self._build_request("/api/sales/invoices/10/post/?line_mode=goods")

        response = SalesInvoicePostAPIView.as_view()(request, pk=10)

        self.assertEqual(response.status_code, 200)
        mocked_require_permission.assert_called_once()
        mocked_post.assert_called_once_with(header=self.header, user=self.user)
        self._assert_serializer_context(mocked_serializer_cls, expected_line_mode="goods")

    @patch("sales.views.sales_invoice_views.require_sales_request_permission")
    @patch("sales.views.sales_invoice_views.SalesInvoiceService.cancel")
    @patch("sales.views.sales_invoice_views.SalesInvoiceHeaderSerializer")
    @patch.object(SalesInvoiceCancelAPIView, "_get_scoped_header")
    def test_cancel_view_passes_reason_and_serializes_with_line_mode_context(
        self,
        mocked_get_header,
        mocked_serializer_cls,
        mocked_cancel,
        mocked_require_permission,
    ):
        mocked_get_header.return_value = self.header
        mocked_cancel.return_value = self.header
        mocked_serializer_cls.return_value.data = {"id": 10, "status_name": "Cancelled"}

        request = self._build_request(
            "/api/sales/invoices/10/cancel/?line_mode=service",
            {"reason": "Customer requested cancellation."},
        )

        response = SalesInvoiceCancelAPIView.as_view()(request, pk=10)

        self.assertEqual(response.status_code, 200)
        mocked_require_permission.assert_called_once()
        mocked_cancel.assert_called_once_with(
            header=self.header,
            user=self.user,
            reason="Customer requested cancellation.",
        )
        self._assert_serializer_context(mocked_serializer_cls, expected_line_mode="service")

    @patch("sales.views.sales_invoice_views.require_sales_request_permission")
    @patch("sales.views.sales_invoice_views.SalesInvoiceService.reverse_posting")
    @patch("sales.views.sales_invoice_views.SalesInvoiceHeaderSerializer")
    @patch.object(SalesInvoiceReverseAPIView, "_get_scoped_header")
    def test_reverse_view_passes_reason_and_serializes_with_line_mode_context(
        self,
        mocked_get_header,
        mocked_serializer_cls,
        mocked_reverse,
        mocked_require_permission,
    ):
        mocked_get_header.return_value = self.header
        mocked_reverse.return_value = self.header
        mocked_serializer_cls.return_value.data = {"id": 10, "status_name": "Confirmed"}

        request = self._build_request(
            "/api/sales/invoices/10/reverse/?line_mode=goods",
            {"reason": "Posting reversed for correction."},
        )

        response = SalesInvoiceReverseAPIView.as_view()(request, pk=10)

        self.assertEqual(response.status_code, 200)
        mocked_require_permission.assert_called_once()
        mocked_reverse.assert_called_once_with(
            header=self.header,
            user=self.user,
            reason="Posting reversed for correction.",
        )
        self._assert_serializer_context(mocked_serializer_cls, expected_line_mode="goods")

    @patch("sales.views.sales_invoice_views.require_sales_request_permission")
    @patch("rest_framework.generics.ListCreateAPIView.create")
    def test_create_view_returns_structured_validation_error_payload(
        self,
        mocked_super_create,
        mocked_require_permission,
    ):
        mocked_super_create.side_effect = ValidationError({"lines": [{"gst_rate": ["This field is required."]}]})

        request = self._build_request(
            "/api/sales/invoices/?line_mode=goods",
            {"entity": 1, "doc_type": int(SalesInvoiceHeader.DocType.TAX_INVOICE)},
        )

        response = SalesInvoiceListCreateAPIView.as_view()(request)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"lines": [{"gst_rate": ["This field is required."]}]})
        mocked_require_permission.assert_called_once()

    @patch("sales.views.sales_invoice_views.SalesInvoiceListSerializer")
    @patch.object(SalesInvoiceListCreateAPIView, "filter_queryset")
    @patch.object(SalesInvoiceListCreateAPIView, "get_queryset")
    def test_list_view_uses_lightweight_serializer(
        self,
        mocked_get_queryset,
        mocked_filter_queryset,
        mocked_list_serializer,
    ):
        mocked_get_queryset.return_value = [self.header]
        mocked_filter_queryset.return_value = [self.header]
        mocked_list_serializer.return_value.data = [{"id": 10, "invoice_number": "INV-10"}]

        request = self.factory.get("/api/sales/invoices/?entity=1")
        force_authenticate(request, user=self.user)

        response = SalesInvoiceListCreateAPIView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        mocked_list_serializer.assert_called_once()
        self.assertEqual(response.data, [{"id": 10, "invoice_number": "INV-10"}])

    @patch("sales.views.sales_invoice_views.require_sales_request_permission")
    @patch("rest_framework.generics.RetrieveUpdateAPIView.update")
    @patch.object(SalesInvoiceRetrieveUpdateAPIView, "get_object")
    def test_update_view_returns_structured_validation_error_payload(
        self,
        mocked_get_object,
        mocked_super_update,
        mocked_require_permission,
    ):
        mocked_get_object.return_value = self.header
        mocked_super_update.side_effect = ValidationError({"customer": ["This field is required."]})

        request = self._build_put_request(
            "/api/sales/invoices/10/?line_mode=service",
            {"customer": None},
        )

        response = SalesInvoiceRetrieveUpdateAPIView.as_view()(request, pk=10)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"customer": ["This field is required."]})
        mocked_require_permission.assert_called_once()

    @patch("sales.views.sales_invoice_views.require_sales_request_permission")
    @patch("rest_framework.generics.RetrieveUpdateAPIView.partial_update")
    @patch.object(SalesInvoiceRetrieveUpdateAPIView, "get_object")
    def test_partial_update_view_returns_structured_validation_error_payload(
        self,
        mocked_get_object,
        mocked_super_partial_update,
        mocked_require_permission,
    ):
        mocked_get_object.return_value = self.header
        mocked_super_partial_update.side_effect = ValidationError({"bill_date": ["Enter a valid date."]})

        request = self._build_patch_request(
            "/api/sales/invoices/10/?line_mode=goods",
            {"bill_date": "bad-date"},
        )

        response = SalesInvoiceRetrieveUpdateAPIView.as_view()(request, pk=10)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"bill_date": ["Enter a valid date."]})
        mocked_require_permission.assert_called_once()


class IRPPayloadBuilderUnitTests(SimpleTestCase):
    @staticmethod
    def _make_line():
        product = SimpleNamespace(name="Widget", hsn_code="1001")
        uom = SimpleNamespace(code="NOS")
        return SimpleNamespace(
            line_no=1,
            product=product,
            uom=uom,
            hsn_sac_code="1001",
            is_service=False,
            qty=Decimal("1.000"),
            free_qty=Decimal("0.000"),
            rate=Decimal("100.0000"),
            discount_amount=Decimal("0.00"),
            taxable_value=Decimal("100.00"),
            cgst_amount=Decimal("9.00"),
            sgst_amount=Decimal("9.00"),
            igst_amount=Decimal("0.00"),
            cess_amount=Decimal("0.00"),
            gst_rate=Decimal("18.00"),
            line_total=Decimal("118.00"),
        )

    @classmethod
    def _make_invoice(cls, **overrides):
        line = cls._make_line()
        original = SimpleNamespace(doc_no=123, bill_date=date(2026, 1, 1), id=10)
        customer = SimpleNamespace(country=SimpleNamespace(countrycode="IN"), state=SimpleNamespace(statecode="27"))
        base = dict(
            id=1,
            doc_type=int(SalesInvoiceHeader.DocType.TAX_INVOICE),
            supply_category=int(SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B),
            is_reverse_charge=False,
            doc_no=101,
            invoice_number="SINV-101",
            bill_date=date(2026, 3, 1),
            total_discount=Decimal("0.00"),
            total_other_charges=Decimal("0.00"),
            round_off=Decimal("0.00"),
            grand_total=Decimal("118.00"),
            lines=SimpleNamespace(all=lambda: [line]),
            original_invoice=original,
            customer=customer,
        )
        base.update(overrides)
        return SimpleNamespace(**base)

    def test_build_blocks_b2c_invoice(self):
        inv = self._make_invoice(supply_category=int(SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2C))
        with self.assertRaisesMessage(ValueError, "B2C"):
            IRPPayloadBuilder(inv).build()

    def test_build_rejects_invalid_doc_no_pattern(self):
        inv = self._make_invoice(doc_no=None, invoice_number="/BADNO")
        with self.assertRaisesMessage(ValueError, "Document number"):
            IRPPayloadBuilder(inv).build()

    def test_build_prefers_invoice_number_over_doc_no(self):
        inv = self._make_invoice(doc_no=1020, invoice_number="SI-SINV-1020")
        payload = IRPPayloadBuilder(inv).build()
        self.assertEqual(payload["DocDtls"]["No"], "SI-SINV-1020")

    def test_build_includes_ref_dtls_for_credit_note(self):
        inv = self._make_invoice(doc_type=int(SalesInvoiceHeader.DocType.CREDIT_NOTE))
        payload = IRPPayloadBuilder(inv).build()
        self.assertIn("RefDtls", payload)
        self.assertEqual(payload["RefDtls"]["PrecDocDtls"][0]["InvNo"], "123")

    def test_build_export_requires_country_code(self):
        customer = SimpleNamespace(country=None, state=SimpleNamespace(statecode="27"))
        inv = self._make_invoice(
            supply_category=int(SalesInvoiceHeader.SupplyCategory.EXPORT_WITH_IGST),
            customer=customer,
        )
        with self.assertRaisesMessage(ValueError, "country code"):
            IRPPayloadBuilder(inv).build()

    def test_build_blocks_non_notified_gst_rate(self):
        line = self._make_line()
        line.gst_rate = Decimal("9.00")
        line.cgst_amount = Decimal("450.00")
        line.sgst_amount = Decimal("450.00")
        line.igst_amount = Decimal("0.00")
        inv = self._make_invoice(lines=SimpleNamespace(all=lambda: [line]))
        with self.assertRaisesMessage(ValueError, "notified GST slab"):
            IRPPayloadBuilder(inv).build()

    def test_build_includes_eway_and_dispatch_blocks_when_available(self):
        line = self._make_line()
        eway = SimpleNamespace(
            disp_dtls_json={
                "Nm": "ABC company pvt ltd",
                "Addr1": "7th block, kuvempu layout",
                "Loc": "Bangalore",
                "Pin": "518360",
                "Stcd": "37",
            },
            exp_ship_dtls_json={
                "Gstin": "29AWGPV7107B1Z1",
                "LglNm": "XYZ company pvt ltd",
                "TrdNm": "XYZ Industries",
                "Addr1": "7th block, kuvempu layout",
                "Loc": "Bangalore",
                "Pin": "560004",
                "Stcd": "29",
            },
            transport_mode=1,
            distance_km=100,
            transporter_id="12AWGPV7107B1Z1",
            transporter_name="XYZ EXPORTS",
            doc_no="DOC01",
            doc_date=date(2026, 3, 5),
            vehicle_no="KA12AB1234",
            vehicle_type="R",
        )
        inv = SimpleNamespace(
            id=1,
            doc_type=int(SalesInvoiceHeader.DocType.TAX_INVOICE),
            supply_category=int(SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B),
            is_reverse_charge=False,
            doc_no=101,
            invoice_number="SINV-101",
            bill_date=date(2026, 3, 1),
            total_discount=Decimal("0.00"),
            total_other_charges=Decimal("0.00"),
            round_off=Decimal("0.00"),
            grand_total=Decimal("118.00"),
            lines=SimpleNamespace(all=lambda: [line]),
            original_invoice=None,
            customer=SimpleNamespace(country=SimpleNamespace(countrycode="IN"), state=SimpleNamespace(statecode="27")),
            customer_gstin="29AWGPV7107B1Z1",
            eway_artifact=eway,
        )
        payload = IRPPayloadBuilder(inv).build()
        self.assertIn("DispDtls", payload)
        self.assertIn("ShipDtls", payload)
        self.assertIn("EwbDtls", payload)
        self.assertEqual(payload["EwbDtls"]["TransMode"], "1")


class ComplianceErrorCatalogServiceUnitTests(SimpleTestCase):
    @patch("sales.services.compliance_error_catalog_service.SalesComplianceErrorCode.objects")
    def test_resolve_returns_catalog_reason_resolution(self, mocked_objects):
        mocked_objects.filter.return_value.only.return_value.first.return_value = SimpleNamespace(
            code="2230",
            message="IRN cancel blocked due to active EWB.",
            reason="EWB exists.",
            resolution="Cancel EWB first.",
        )
        info = ComplianceErrorCatalogService.resolve(code="2230", message="fallback")
        self.assertEqual(info.code, "2230")
        self.assertIn("EWB", info.as_text())

    def test_resolve_without_code_uses_message(self):
        info = ComplianceErrorCatalogService.resolve(code=None, message="Some failure")
        self.assertEqual(info.as_text(), "Some failure")


class EWayPayloadBuilderUnitTests(SimpleTestCase):
    def test_rail_requires_trans_doc_fields(self):
        x = EWayInput(
            distance_km=10,
            trans_mode="2",
            transporter_id="",
            transporter_name="",
            trans_doc_no="",
            trans_doc_date=None,
            vehicle_no=None,
            vehicle_type=None,
        )
        with self.assertRaisesMessage(ValueError, "TransDocNo"):
            build_generate_eway_payload("IRN123", x)

    def test_road_allows_missing_trans_doc_and_supports_zero_distance(self):
        x = EWayInput(
            distance_km=0,
            trans_mode="1",
            transporter_id="05AAACG0904A1ZL",
            transporter_name="ABC",
            trans_doc_no="",
            trans_doc_date=None,
            vehicle_no="APR3214",
            vehicle_type="R",
        )
        payload = build_generate_eway_payload("IRN123", x)
        self.assertEqual(payload["Distance"], 0)
        self.assertEqual(payload["VehType"], "R")
        self.assertNotIn("TransDocDt", payload)


class SalesComplianceDateParseUnitTests(SimpleTestCase):
    def test_parse_mastergst_datetime_with_ampm(self):
        dt = SalesComplianceService._parse_dt("05/03/2026 10:22:00 PM")
        self.assertIsNotNone(dt)


class MasterGSTErrorExtractUnitTests(SimpleTestCase):
    @patch("sales.services.providers.mastergst.ComplianceErrorCatalogService.resolve")
    def test_extract_error_reads_status_desc_json(self, mocked_resolve):
        mocked_resolve.return_value = SimpleNamespace(code="2150", message="Duplicate IRN", reason=None, resolution=None)
        raw = {
            "status_cd": "0",
            "status_desc": '[{"ErrorCode":"2150","ErrorMessage":"Duplicate IRN"}]',
        }
        code, msg, reason, resolution = _extract_error(raw)
        self.assertEqual(code, "2150")
        self.assertEqual(msg, "Duplicate IRN")


class CustomerStatementExportViewTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = SimpleNamespace(id=11, is_authenticated=True)

    @patch("sales.views.sales_ar_exports._require_ar_view_permission")
    @patch("sales.views.sales_ar_exports.SalesArService.customer_statement")
    @patch("sales.views.sales_ar_exports.account.objects.filter")
    @patch("sales.views.sales_ar_exports.resolve_scope_names")
    def test_customer_statement_excel_export_returns_attachment(
        self,
        mocked_resolve_scope_names,
        mocked_account_filter,
        mocked_customer_statement,
        mocked_require_permission,
    ):
        mocked_require_permission.return_value = None
        mocked_resolve_scope_names.return_value = {
            "entity_name": "Arnika G",
            "entityfin_name": "FY 2026-27",
            "subentity_name": "Main Branch",
        }

        class _Query:
            def select_related(self, *args, **kwargs):
                return self

            def only(self, *args, **kwargs):
                return self

            def first(self):
                return SimpleNamespace(
                    id=501,
                    accountname="Customer A",
                    effective_accounting_name="Customer A",
                    effective_accounting_code=9004,
                    ledger_id=268,
                )

        mocked_account_filter.return_value = _Query()
        mocked_customer_statement.return_value = {
            "totals": {
                "outstanding_total": "100.00",
                "advance_outstanding_total": "25.00",
                "advance_consumed_total": "5.00",
                "net_ar_position": "75.00",
            },
            "open_items": [
                {
                    "bill_date": "2026-04-01",
                    "due_date": "2026-04-30",
                    "invoice_number": "INV-1",
                    "customer_reference_number": "REF-1",
                    "original_amount": "100.00",
                    "settled_amount": "0.00",
                    "outstanding_amount": "100.00",
                    "is_open": True,
                }
            ],
            "advances": [],
            "settlements": [],
        }

        request = self.factory.get(
            "/api/sales/ar/customer-statement/excel/",
            {"entity": "10", "entityfinid": "8", "customer": "501"},
        )
        force_authenticate(request, user=self.user)

        response = CustomerStatementExcelAPIView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertIn("attachment;", response["Content-Disposition"])
        self.assertIn("CustomerLedger_", response["Content-Disposition"])
