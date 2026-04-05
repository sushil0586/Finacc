from types import SimpleNamespace
from decimal import Decimal
from unittest.mock import patch
from datetime import date

from django.test import SimpleTestCase

from sales.models import SalesInvoiceHeader, SalesSettings
from sales.services.sales_invoice_service import SalesInvoiceService
from sales.services.sales_withholding_service import SalesWithholdingService
from sales.services.irp_payload_builder import IRPPayloadBuilder
from sales.services.compliance_error_catalog_service import ComplianceErrorCatalogService
from sales.services.eway_payload_builder import EWayInput, build_generate_eway_payload
from sales.services.sales_compliance_service import SalesComplianceService
from sales.services.providers.mastergst import _extract_error


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
