from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import Mock, patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from Authentication.models import User
from entity.models import Entity, EntityFinancialYear, EntityGstRegistration, GstRegistrationType, SubEntity, SubEntityGstRegistration
from geography.models import Country, State
from reports.gst_portal.payloads import Gstr1WhiteboxPayloadBuilder, Gstr3bWhiteboxPayloadBuilder, build_gstr1_retfile_payload, ret_period_from_date, ret_period_from_scope
from reports.gst_portal.scope import resolve_gst_portal_registration_scope
from reports.gst_portal.whitebox import WhiteboxConfigurationError, WhiteboxContext, WhiteboxGstClient, WhiteboxRequestError, WhiteboxResponse, redacted_whitebox_snapshot
from reports.models import GstPortalFilingRun, GstPortalProfile, GstPortalSession
from sales.models import SalesInvoiceHeader


class GstPortalPayloadBuilderTests(TestCase):
    def test_ret_period_helpers_use_gst_month_year_format(self):
        scope = Mock(from_date=date(2026, 8, 1))

        self.assertEqual(ret_period_from_scope(scope), "082026")
        self.assertEqual(ret_period_from_date(datetime(2026, 8, 20, 9, 30)), "082026")
        self.assertEqual(ret_period_from_date("2026-08-31"), "082026")

    def test_gstr1_builder_maps_core_filing_prep_tables_to_whitebox_payload(self):
        filing_prep = {
            "ret_period": "082026",
            "tables": {
                "1_2_3": [{"gstin": "27AAAAA1111A1Z1", "previous_financial_year_aggregate_turnover": "1000.00"}],
                "4": [
                    {
                        "invoice_id": 1,
                        "invoice_number": "S-1",
                        "invoice_date": "2026-08-03",
                        "customer_gstin": "27ABCDE1234F1Z5",
                        "place_of_supply_state_code": "27",
                        "taxable_amount": "100.00",
                        "gst_rate": "18.00",
                        "cgst_amount": "9.00",
                        "sgst_amount": "9.00",
                        "grand_total": "118.00",
                    },
                    {
                        "invoice_id": 1,
                        "invoice_number": "S-1",
                        "invoice_date": "2026-08-03",
                        "customer_gstin": "27ABCDE1234F1Z5",
                        "place_of_supply_state_code": "27",
                        "taxable_amount": "50.00",
                        "gst_rate": "5.00",
                        "cgst_amount": "1.25",
                        "sgst_amount": "1.25",
                        "grand_total": "118.00",
                    },
                ],
                "7": [
                    {
                        "place_of_supply_state_code": "29",
                        "gst_rate": "18.00",
                        "taxable_value": "200.00",
                        "igst_amount": "36.00",
                    }
                ],
                "12": [
                    {
                        "hsn_sac_code": "9983",
                        "is_service": True,
                        "gst_rate": "18.00",
                        "total_qty": "1.00",
                        "taxable_value": "100.00",
                        "igst_amount": "18.00",
                    }
                ],
                "13": [
                    {
                        "doc_type": 1,
                        "doc_code": "SINV",
                        "document_count": 2,
                        "cancelled_count": 1,
                        "min_doc_no": 1,
                        "max_doc_no": 2,
                    }
                ],
            },
        }

        prepared = Gstr1WhiteboxPayloadBuilder().build(filing_prep_payload=filing_prep)

        self.assertEqual(prepared.return_type, "gstr1")
        self.assertEqual(prepared.gstin, "27AAAAA1111A1Z1")
        self.assertEqual(prepared.ret_period, "082026")
        self.assertEqual(prepared.payload["fp"], "082026")
        self.assertEqual(prepared.payload["b2b"][0]["ctin"], "27ABCDE1234F1Z5")
        invoice = prepared.payload["b2b"][0]["inv"][0]
        self.assertEqual(invoice["inum"], "S-1")
        self.assertEqual(invoice["idt"], "03-08-2026")
        self.assertEqual(len(invoice["itms"]), 2)
        self.assertEqual(prepared.payload["b2cs"][0]["pos"], "29")
        self.assertEqual(prepared.payload["hsnsum"]["data"][0]["hsn_sc"], "9983")
        self.assertEqual(prepared.payload["doc_issue"]["doc_det"][0]["docs"][0]["net_issue"], 1)

    def test_gstr1_retfile_payload_derives_checksum_section_summaries_and_negative_notes(self):
        save_payload = {
            "gstin": "27AAAAA1111A1Z1",
            "fp": "082026",
            "b2b": [
                {
                    "ctin": "27ABCDE1234F1Z5",
                    "inv": [
                        {
                            "inum": "S-1",
                            "val": 118.0,
                            "itms": [
                                {
                                    "num": 1,
                                    "itm_det": {
                                        "txval": 100.0,
                                        "rt": 18.0,
                                        "camt": 9.0,
                                        "samt": 9.0,
                                    },
                                }
                            ],
                        }
                    ],
                }
            ],
            "cdnr": [
                {
                    "ctin": "27ABCDE1234F1Z5",
                    "nt": [
                        {
                            "ntty": "C",
                            "nt_num": "CN-1",
                            "val": 59.0,
                            "itms": [
                                {
                                    "num": 1,
                                    "itm_det": {
                                        "txval": 50.0,
                                        "rt": 18.0,
                                        "camt": 4.5,
                                        "samt": 4.5,
                                    },
                                }
                            ],
                        }
                    ],
                }
            ],
        }

        payload = build_gstr1_retfile_payload(save_payload=save_payload)
        payload_again = build_gstr1_retfile_payload(save_payload=save_payload)

        self.assertEqual(payload["gstin"], "27AAAAA1111A1Z1")
        self.assertEqual(payload["ret_period"], "082026")
        self.assertTrue(payload["newSumFlag"])
        self.assertRegex(payload["chksum"], r"^[0-9a-f]{64}$")
        self.assertEqual(payload["chksum"], payload_again["chksum"])
        sections = {section["sec_nm"]: section for section in payload["sec_sum"]}
        self.assertEqual(sections["B2B"]["ttl_rec"], 1)
        self.assertEqual(sections["B2B"]["ttl_val"], 100.0)
        self.assertEqual(sections["B2B"]["ttl_tax"], 18.0)
        self.assertEqual(sections["CDNR"]["ttl_val"], -50.0)
        self.assertEqual(sections["CDNR"]["ttl_tax"], -9.0)
        self.assertRegex(sections["CDNR"]["chksum"], r"^[0-9a-f]{64}$")

    def test_gstr3b_builder_maps_summary_to_whitebox_payload_and_warns_for_missing_pos_breakup(self):
        summary = {
            "section_3_1": {
                "outward_taxable_supplies": {"taxable_value": "100.00", "cgst": "9.00", "sgst": "9.00", "igst": "0.00", "cess": "0.00"},
                "outward_zero_rated_supplies": {"taxable_value": "20.00", "igst": "0.00", "cess": "0.00"},
                "outward_nil_exempt_non_gst": {"taxable_value": "5.00"},
                "inward_supplies_reverse_charge": {"taxable_value": "50.00", "cgst": "2.50", "sgst": "2.50", "igst": "0.00", "cess": "0.00"},
                "non_gst_outward_supplies": {"taxable_value": "3.00"},
            },
            "section_3_2": {
                "interstate_supplies_to_unregistered": {"taxable_value": "10.00", "igst": "1.80"},
            },
            "section_4": {
                "itc_available": {"cgst": "4.00", "sgst": "4.00", "igst": "2.00", "cess": "0.00"},
                "itc_reversed": {"cgst": "1.00", "sgst": "1.00", "igst": "0.00", "cess": "0.00"},
                "net_itc": {"cgst": "3.00", "sgst": "3.00", "igst": "2.00", "cess": "0.00"},
            },
            "section_5_1": {
                "inward_exempt_nil_non_gst": {"taxable_value": "6.00"},
            },
        }

        prepared = Gstr3bWhiteboxPayloadBuilder().build(
            summary=summary,
            gstin="27AAAAA1111A1Z1",
            ret_period="082026",
        )

        self.assertEqual(prepared.payload["sup_details"]["osup_det"]["txval"], 100.0)
        self.assertEqual(prepared.payload["sup_details"]["isup_rev"]["camt"], 2.5)
        self.assertEqual(prepared.payload["itc_elg"]["itc_net"]["samt"], 3.0)
        self.assertEqual(prepared.payload["inward_sup"]["isup_details"][0]["inter"], 6.0)
        self.assertEqual(prepared.warnings[0]["code"], "WHITEBOX_GSTR3B_POS_BREAKUP_PENDING")


class GstPortalScopeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="gst-scope", email="gst-scope@example.com", password="pass123")
        self.country = Country.objects.create(countryname="India", countrycode="IN")
        self.state = State.objects.create(statename="Maharashtra", statecode="27", country=self.country)
        self.gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="Scope Entity",
            legalname="Scope Entity Pvt Ltd",
            GstRegitrationType=self.gst_type,
            createdby=self.user,
        )

    def test_scope_for_shared_branch_gstin_requires_gstin_level_aggregation(self):
        branch_a = SubEntity.objects.create(entity=self.entity, subentityname="Mumbai HO")
        branch_b = SubEntity.objects.create(entity=self.entity, subentityname="Mumbai Depot")
        SubEntityGstRegistration.objects.create(subentity=branch_a, gstin="27AAAAA1111A1Z1", state=self.state, is_primary=True)
        SubEntityGstRegistration.objects.create(subentity=branch_b, gstin="27AAAAA1111A1Z1", state=self.state, is_primary=True)

        scope = resolve_gst_portal_registration_scope(entity_id=self.entity.id, subentity_id=branch_a.id)

        self.assertEqual(scope.gstin, "27AAAAA1111A1Z1")
        self.assertIsNone(scope.filing_subentity_id)
        self.assertEqual(scope.shared_subentity_ids, (branch_a.id, branch_b.id))
        self.assertEqual(scope.warnings[0]["code"], "GST_PORTAL_SHARED_GSTIN_SCOPE")

    def test_scope_uses_entity_registration_when_branch_registration_is_missing(self):
        branch = SubEntity.objects.create(entity=self.entity, subentityname="No GST Branch")
        EntityGstRegistration.objects.create(entity=self.entity, gstin="27AAAAA1111A1Z1", state=self.state, is_primary=True)

        scope = resolve_gst_portal_registration_scope(entity_id=self.entity.id, subentity_id=branch.id)

        self.assertEqual(scope.registration_source, "entity")
        self.assertEqual(scope.gstin, "27AAAAA1111A1Z1")
        self.assertEqual(scope.state_cd, "27")
        self.assertEqual(scope.filing_subentity_id, branch.id)
        self.assertEqual(scope.shared_subentity_ids, ())


@override_settings(
    WHITEBOX_GST_BASE_URL="https://whitebox.example.test",
    WHITEBOX_GST_CLIENT_ID="client",
    WHITEBOX_GST_CLIENT_SECRET="secret",
)
class WhiteboxGstClientTests(TestCase):
    def test_save_gstr1_sends_required_headers_and_redacts_sensitive_snapshot(self):
        response = Mock(status_code=200)
        response.headers = {"txn": "WB-TXN-1"}
        response.json.return_value = {"status_cd": "1"}
        session = Mock()
        session.request.return_value = response
        client = WhiteboxGstClient(session=session)
        context = WhiteboxContext(
            email="gst@example.com",
            gstin="27AAAAA1111A1Z1",
            gst_username="GSTUSER",
            state_cd="27",
            ip_address="203.0.113.1",
            txn="TXN-1",
        )

        result = client.save_gstr1(context=context, ret_period="082026", payload={"gstin": "27AAAAA1111A1Z1"})

        self.assertEqual(result.payload["status_cd"], "1")
        self.assertEqual(result.payload["header"]["txn"], "WB-TXN-1")
        self.assertEqual(result.txn, "WB-TXN-1")
        _, _, kwargs = session.request.mock_calls[0]
        self.assertEqual(kwargs["headers"]["accept"], "*/*")
        self.assertEqual(kwargs["headers"]["gstin"], "27AAAAA1111A1Z1")
        self.assertEqual(kwargs["headers"]["ret_period"], "082026")
        self.assertEqual(kwargs["headers"]["client_id"], "client")
        snapshot = redacted_whitebox_snapshot({"client_secret": "secret", "otp": "123456", "safe": {"gstin": "27"}})
        self.assertEqual(snapshot["client_secret"], "***redacted***")
        self.assertEqual(snapshot["safe"]["gstin"], "27")

    def test_client_raises_clean_error_for_non_json_provider_response(self):
        response = Mock(status_code=500)
        response.headers = {}
        response.text = "<!doctype html><html><title>Server Error (500)</title></html>"
        response.json.side_effect = ValueError("not json")
        session = Mock()
        session.request.return_value = response
        client = WhiteboxGstClient(session=session)

        with self.assertRaises(WhiteboxRequestError) as ctx:
            client.request_otp(context=WhiteboxContext(email="gst@example.com"))

        self.assertIn("non-JSON response", str(ctx.exception))
        self.assertEqual(ctx.exception.response_payload["status_cd"], "0")
        self.assertIn("Server Error", ctx.exception.response_payload["response_preview"])

    def test_client_raises_clean_error_for_provider_status_failure(self):
        response = Mock(status_code=200)
        response.headers = {}
        response.json.return_value = {"status_cd": "0", "error": {"error_cd": "AUTH403", "message": "Session limit reached"}}
        session = Mock()
        session.request.return_value = response
        client = WhiteboxGstClient(session=session)

        with self.assertRaises(WhiteboxRequestError) as ctx:
            client.request_otp(context=WhiteboxContext(email="gst@example.com"))

        self.assertIn("AUTH403: Session limit reached", str(ctx.exception))

    def test_proceed_to_file_falls_back_to_legacy_endpoint_when_new_endpoint_is_unavailable(self):
        not_found = Mock(status_code=404)
        not_found.headers = {}
        not_found.json.return_value = {"message": "Not found"}
        ok = Mock(status_code=200)
        ok.headers = {"txn": "LEGACY-TXN"}
        ok.json.return_value = {"status_cd": "1", "ref_id": "LEGACY-PROCEED"}
        session = Mock()
        session.request.side_effect = [not_found, ok]
        client = WhiteboxGstClient(session=session)
        context = WhiteboxContext(
            email="gst@example.com",
            gstin="27AAAAA1111A1Z1",
            gst_username="GSTUSER",
            state_cd="27",
            ip_address="203.0.113.1",
            txn="TXN-1",
        )

        result = client.proceed_to_file(context=context, ret_period="082026", return_type="gstr1", is_nil=True)

        self.assertEqual(result.payload["ref_id"], "LEGACY-PROCEED")
        first_call = session.request.mock_calls[0].kwargs
        second_call = session.request.mock_calls[1].kwargs
        self.assertIn("/all/newproceedfile", session.request.mock_calls[0].args[1])
        self.assertIn("/all/proceedfile", session.request.mock_calls[1].args[1])
        self.assertEqual(first_call["params"]["isNil"], "Y")
        self.assertNotIn("isNil", second_call["params"])

    def test_return_status_falls_back_to_legacy_endpoint_when_new_endpoint_is_unavailable(self):
        not_found = Mock(status_code=404)
        not_found.headers = {}
        not_found.json.return_value = {"message": "Not found"}
        ok = Mock(status_code=200)
        ok.headers = {"txn": "STATUS-TXN"}
        ok.json.return_value = {"status_cd": "1", "status": "FILED"}
        session = Mock()
        session.request.side_effect = [not_found, ok]
        client = WhiteboxGstClient(session=session)
        context = WhiteboxContext(
            email="gst@example.com",
            gstin="27AAAAA1111A1Z1",
            gst_username="GSTUSER",
            state_cd="27",
            ip_address="203.0.113.1",
            txn="TXN-1",
        )

        result = client.return_status(context=context, ret_period="082026", ref_id="REF-1", return_type="GSTR1")

        self.assertEqual(result.payload["status"], "FILED")
        first_call = session.request.mock_calls[0].kwargs
        second_call = session.request.mock_calls[1].kwargs
        self.assertIn("/all/newretstatus", session.request.mock_calls[0].args[1])
        self.assertIn("/gstr/retstatus", session.request.mock_calls[1].args[1])
        self.assertEqual(first_call["params"]["rettype"], "GSTR1")
        self.assertNotIn("rettype", second_call["params"])

    def test_evc_file_gstr1_sends_evc_otp_as_query_param_without_body(self):
        response = Mock(status_code=200)
        response.headers = {"txn": "EVC-FILE-TXN"}
        response.json.return_value = {"status_cd": "1", "ack_no": "ACK-1"}
        session = Mock()
        session.request.return_value = response
        client = WhiteboxGstClient(session=session)
        context = WhiteboxContext(
            email="gst@example.com",
            gstin="27AAAAA1111A1Z1",
            gst_username="GSTUSER",
            state_cd="27",
            ip_address="203.0.113.1",
            txn="TXN-1",
        )

        result = client.evc_file_gstr1(context=context, ret_period="082026", pan="AAAAA1111A", evc_otp="575757")

        self.assertEqual(result.payload["ack_no"], "ACK-1")
        call = session.request.mock_calls[0]
        self.assertIn("/gstr1/retevcfile", call.args[1])
        self.assertEqual(call.kwargs["params"]["evcotp"], "575757")
        self.assertIsNone(call.kwargs["json"])

    @override_settings(
        WHITEBOOKS_BASE_URL="",
        WHITEBOOKS_API_KEY="",
        WHITEBOOKS_API_SECRET="",
        WHITEBOX_GST_BASE_URL="",
        WHITEBOX_GST_CLIENT_ID="",
        WHITEBOX_GST_CLIENT_SECRET="",
    )
    def test_client_blocks_when_not_configured(self):
        client = WhiteboxGstClient()

        with self.assertRaises(WhiteboxConfigurationError):
            client.request_otp(context=WhiteboxContext(email="gst@example.com"))


@override_settings(ROOT_URLCONF="FA.urls", AUTH_PASSWORD_VALIDATORS=[])
class GstPortalPreviewExportAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="gst-preview", email="gst-preview@example.com", password="pass123")
        self.client.force_authenticate(user=self.user)
        self.permission_patch = patch(
            "reports.api.report_permissions.EffectivePermissionService.permission_codes_for_user",
            return_value=["reports.gst.view", "reports.gstr1report.view", "reports.gstr3b.view", "reports.gst.file"],
        )
        self.permission_patch.start()
        self.addCleanup(self.permission_patch.stop)
        self.country = Country.objects.create(countryname="India", countrycode="IN")
        self.state = State.objects.create(statename="Maharashtra", statecode="27", country=self.country)
        self.gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="Preview Entity",
            legalname="Preview Entity Pvt Ltd",
            GstRegitrationType=self.gst_type,
            createdby=self.user,
        )
        self.branch = SubEntity.objects.create(entity=self.entity, subentityname="Mumbai Branch")
        self.entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2026-27",
            finstartyear=timezone.make_aware(datetime(2026, 4, 1)),
            finendyear=timezone.make_aware(datetime(2027, 3, 31)),
            createdby=self.user,
        )
        EntityGstRegistration.objects.create(
            entity=self.entity,
            gstin="27AAAAA1111A1Z1",
            state=self.state,
            is_primary=True,
            createdby=self.user,
        )
        self.params = {
            "entity": self.entity.id,
            "entityfinid": self.entityfin.id,
            "subentity": self.branch.id,
            "from_date": "2026-08-01",
            "to_date": "2026-08-31",
            "format": "whitebox_json",
        }

    def test_gstr1_whitebox_preview_export_is_available_without_live_whitebox_credentials(self):
        response = self.client.get(reverse("reports_api:gstr1-export"), self.params)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["return_type"], "gstr1")
        self.assertEqual(response.data["gstin"], "27AAAAA1111A1Z1")
        self.assertEqual(response.data["ret_period"], "082026")
        self.assertEqual(response.data["payload"]["gstin"], "27AAAAA1111A1Z1")
        self.assertEqual(response.data["scope"]["requested_subentity"], self.branch.id)

    def test_gstr3b_whitebox_preview_export_is_available_without_live_whitebox_credentials(self):
        response = self.client.get(reverse("reports_api:gstr3b-export"), self.params)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["return_type"], "gstr3b")
        self.assertEqual(response.data["gstin"], "27AAAAA1111A1Z1")
        self.assertEqual(response.data["ret_period"], "082026")
        self.assertIn("sup_details", response.data["payload"])

    def test_gstr3b_whitebox_preview_includes_pos_wise_interstate_breakup(self):
        SalesInvoiceHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.branch,
            doc_type=SalesInvoiceHeader.DocType.TAX_INVOICE,
            status=SalesInvoiceHeader.Status.POSTED,
            bill_date="2026-08-12",
            posting_date="2026-08-12",
            doc_code="SINV",
            doc_no=1,
            invoice_number="SINV-1",
            customer_name="Retail Customer",
            customer_gstin="",
            seller_gstin="27AAAAA1111A1Z1",
            seller_state_code="27",
            place_of_supply_state_code="29",
            taxability=SalesInvoiceHeader.Taxability.TAXABLE,
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2C,
            tax_regime=SalesInvoiceHeader.TaxRegime.INTER_STATE,
            is_igst=True,
            total_taxable_value=Decimal("1000.00"),
            total_cgst=Decimal("0.00"),
            total_sgst=Decimal("0.00"),
            total_igst=Decimal("180.00"),
            total_cess=Decimal("0.00"),
            grand_total=Decimal("1180.00"),
        )

        response = self.client.get(reverse("reports_api:gstr3b-export"), self.params)

        self.assertEqual(response.status_code, 200)
        unregistered = response.data["payload"]["inter_sup"]["unreg_details"]
        self.assertEqual(unregistered[0]["pos"], "29")
        self.assertEqual(unregistered[0]["txval"], 1000.0)
        self.assertEqual(unregistered[0]["iamt"], 180.0)
        self.assertFalse(response.data["warnings"])

    def test_gstr3b_meta_advertises_whitebox_preview_export(self):
        response = self.client.get(reverse("reports_api:gstr3b-meta"), {"entity": self.entity.id})

        self.assertEqual(response.status_code, 200)
        self.assertIn("whitebox_json", response.data["supported_exports"])

    def test_gst_portal_prepare_persists_gstr1_filing_run(self):
        payload = {**self.params, "return_type": "gstr1"}
        response = self.client.post(reverse("reports_api:gst-portal-filing-prepare"), payload, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["return_type"], "gstr1")
        self.assertEqual(response.data["status"], GstPortalFilingRun.Status.PREPARED)
        self.assertEqual(response.data["gstin"], "27AAAAA1111A1Z1")
        self.assertEqual(response.data["portal_profile"]["source"], "missing")
        self.assertEqual(GstPortalFilingRun.objects.count(), 1)

    def test_gst_portal_profile_can_be_saved_for_gstin_scope(self):
        response = self.client.post(
            reverse("reports_api:gst-portal-profile"),
            {
                "entity": self.entity.id,
                "subentity": self.branch.id,
                "gst_username": "GSTUSER27",
                "registered_mobile_masked": "******1234",
                "registered_email_masked": "owner@example.com",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["exists"])
        self.assertEqual(response.data["gstin"], "27AAAAA1111A1Z1")
        self.assertEqual(response.data["gst_username"], "GSTUSER27")
        self.assertEqual(response.data["source"], "profile")
        self.assertEqual(GstPortalProfile.objects.count(), 1)

        fetched = self.client.get(
            reverse("reports_api:gst-portal-profile"),
            {"entity": self.entity.id, "subentity": self.branch.id},
        )
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.data["gst_username"], "GSTUSER27")

    def test_gst_portal_prepare_includes_saved_profile_metadata(self):
        GstPortalProfile.objects.create(
            provider="whitebox",
            entity=self.entity,
            gstin="27AAAAA1111A1Z1",
            state_cd="27",
            gst_username="GSTUSER27",
        )

        response = self.client.post(
            reverse("reports_api:gst-portal-filing-prepare"),
            {**self.params, "return_type": "gstr1"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["portal_profile"]["gst_username"], "GSTUSER27")
        self.assertEqual(response.data["portal_profile"]["source"], "profile")

    def test_gst_portal_status_lists_prepared_runs(self):
        prepared = self.client.post(
            reverse("reports_api:gst-portal-filing-prepare"),
            {**self.params, "return_type": "gstr3b"},
            format="json",
        )
        self.assertEqual(prepared.status_code, 201)

        response = self.client.get(
            reverse("reports_api:gst-portal-filing-status"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "return_type": "gstr3b",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], prepared.data["id"])

    def test_gst_portal_request_otp_is_blocked_until_whitebox_is_configured(self):
        response = self.client.post(
            reverse("reports_api:gst-portal-auth-request-otp"),
            {
                "entity": self.entity.id,
                "subentity": self.branch.id,
                "email": "gst@example.com",
                "gst_username": "GSTUSER",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Whitebox GST is not configured", response.data["detail"])
        session = GstPortalSession.objects.get()
        self.assertEqual(session.status, GstPortalSession.Status.FAILED)

    def test_gst_portal_save_is_blocked_until_whitebox_is_configured_and_marks_run_failed(self):
        prepared = self.client.post(
            reverse("reports_api:gst-portal-filing-prepare"),
            {**self.params, "return_type": "gstr1"},
            format="json",
        )
        self.assertEqual(prepared.status_code, 201)

        response = self.client.post(
            reverse("reports_api:gst-portal-filing-save"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "filing_id": prepared.data["id"],
                "email": "gst@example.com",
                "gst_username": "GSTUSER",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Whitebox GST is not configured", response.data["detail"])
        run = GstPortalFilingRun.objects.get(id=prepared.data["id"])
        self.assertEqual(run.status, GstPortalFilingRun.Status.FAILED)

    @override_settings(
        WHITEBOOKS_BASE_URL="https://whitebox.example.test",
        WHITEBOOKS_API_KEY="client",
        WHITEBOOKS_API_SECRET="secret",
        WHITEBOOKS_CONTACT_EMAIL="ops@example.com",
        WHITEBOOKS_ENABLE_GSTR1_SAVE_LIVE=False,
    )
    def test_gst_portal_save_is_blocked_until_live_flag_is_enabled(self):
        prepared = self.client.post(
            reverse("reports_api:gst-portal-filing-prepare"),
            {**self.params, "return_type": "gstr1"},
            format="json",
        )
        self.assertEqual(prepared.status_code, 201)

        response = self.client.post(
            reverse("reports_api:gst-portal-filing-save"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "filing_id": prepared.data["id"],
                "gst_username": "GSTUSER",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("WHITEBOOKS_ENABLE_GSTR1_SAVE_LIVE", response.data["detail"])
        run = GstPortalFilingRun.objects.get(id=prepared.data["id"])
        self.assertEqual(run.status, GstPortalFilingRun.Status.PREPARED)

    @override_settings(WHITEBOOKS_CONTACT_EMAIL="ops@example.com", WHITEBOOKS_GST_USERNAME="GSTUSER")
    @patch("reports.gst_portal.services.WhiteboxGstClient")
    def test_gst_portal_otp_verify_lifecycle_with_fake_whitebox_client(self, client_class):
        fake_client = Mock()
        fake_client.request_otp.return_value = WhiteboxResponse(status_code=200, payload={"status_cd": "1"}, txn="OTP-TXN")
        fake_client.auth_token.return_value = WhiteboxResponse(status_code=200, payload={"auth_token": "SECRET", "status_cd": "1"}, txn="AUTH-TXN")
        client_class.return_value = fake_client

        requested = self.client.post(
            reverse("reports_api:gst-portal-auth-request-otp"),
            {
                "entity": self.entity.id,
                "subentity": self.branch.id,
            },
            format="json",
        )
        self.assertEqual(requested.status_code, 201)
        self.assertEqual(requested.data["email"], "ops@example.com")
        self.assertEqual(requested.data["gst_username"], "GSTUSER")

        verified = self.client.post(
            reverse("reports_api:gst-portal-auth-verify-otp"),
            {
                "entity": self.entity.id,
                "session_id": requested.data["id"],
                "otp": "123456",
            },
            format="json",
        )

        self.assertEqual(verified.status_code, 200)
        self.assertEqual(verified.data["status"], GstPortalSession.Status.AUTHENTICATED)
        self.assertEqual(verified.data["last_response"]["auth_token"], "***redacted***")
        fake_client.auth_token.assert_called_once()

    @override_settings(WHITEBOOKS_CONTACT_EMAIL="ops@example.com", WHITEBOOKS_GST_USERNAME="")
    @patch("reports.gst_portal.services.WhiteboxGstClient")
    def test_gst_portal_otp_request_uses_saved_profile_username(self, client_class):
        GstPortalProfile.objects.create(
            provider="whitebox",
            entity=self.entity,
            gstin="27AAAAA1111A1Z1",
            state_cd="27",
            gst_username="GSTUSER27",
        )
        fake_client = Mock()
        fake_client.request_otp.return_value = WhiteboxResponse(status_code=200, payload={"status_cd": "1"}, txn="OTP-TXN")
        client_class.return_value = fake_client

        requested = self.client.post(
            reverse("reports_api:gst-portal-auth-request-otp"),
            {
                "entity": self.entity.id,
                "subentity": self.branch.id,
            },
            format="json",
        )

        self.assertEqual(requested.status_code, 201)
        self.assertEqual(requested.data["gst_username"], "GSTUSER27")
        context = fake_client.request_otp.call_args.kwargs["context"]
        self.assertEqual(context.gst_username, "GSTUSER27")

    @override_settings(
        WHITEBOOKS_CONTACT_EMAIL="ops@example.com",
        WHITEBOOKS_ENABLE_GSTR1_SAVE_LIVE=True,
        WHITEBOOKS_ENABLE_GSTR1_FILE_LIVE=True,
    )
    @patch("reports.gst_portal.services.WhiteboxGstClient")
    def test_gst_portal_filing_lifecycle_with_fake_whitebox_client(self, client_class):
        fake_client = Mock()
        fake_client.save_gstr1.return_value = WhiteboxResponse(status_code=200, payload={"status_cd": "1", "ref_id": "SAVE-REF"}, txn="SAVE-TXN")
        fake_client.gstr1_summary.return_value = WhiteboxResponse(status_code=200, payload={"chksum": "CHK-1"}, txn="SUMMARY-TXN")
        fake_client.proceed_to_file.return_value = WhiteboxResponse(status_code=200, payload={"status_cd": "1", "ref_id": "PROCEED-REF"}, txn="PROCEED-TXN")
        fake_client.request_evc_otp.return_value = WhiteboxResponse(status_code=200, payload={"status_cd": "1"}, txn="EVC-TXN")
        fake_client.evc_file_gstr1.return_value = WhiteboxResponse(status_code=200, payload={"ack_no": "ACK-1"}, txn="FILE-TXN")
        fake_client.return_status.return_value = WhiteboxResponse(status_code=200, payload={"status": "FILED"}, txn="POLL-TXN")
        client_class.return_value = fake_client

        prepared = self.client.post(
            reverse("reports_api:gst-portal-filing-prepare"),
            {**self.params, "return_type": "gstr1"},
            format="json",
        )
        self.assertEqual(prepared.status_code, 201)

        base_payload = {
            "entity": self.entity.id,
            "entityfinid": self.entityfin.id,
            "filing_id": prepared.data["id"],
            "gst_username": "GSTUSER",
        }
        saved = self.client.post(reverse("reports_api:gst-portal-filing-save"), base_payload, format="json")
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.data["status"], GstPortalFilingRun.Status.SAVED)
        self.assertEqual(saved.data["txn"], "SAVE-TXN")

        summary = self.client.post(reverse("reports_api:gst-portal-filing-portal-summary"), base_payload, format="json")
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.data["status"], GstPortalFilingRun.Status.SUMMARY_FETCHED)
        self.assertEqual(summary.data["portal_response"]["summary"]["chksum"], "CHK-1")

        proceeded = self.client.post(reverse("reports_api:gst-portal-filing-proceed"), base_payload, format="json")
        self.assertEqual(proceeded.status_code, 200)
        self.assertEqual(proceeded.data["status"], GstPortalFilingRun.Status.PROCEEDED)
        self.assertEqual(proceeded.data["stage"], "proceeded_to_file")
        self.assertEqual(proceeded.data["portal_response"]["proceed_to_file"]["ref_id"], "PROCEED-REF")

        evc = self.client.post(
            reverse("reports_api:gst-portal-filing-request-evc"),
            {**base_payload, "pan": "AAAAA1111A"},
            format="json",
        )
        self.assertEqual(evc.status_code, 200)
        self.assertEqual(evc.data["status"], GstPortalFilingRun.Status.EVC_REQUESTED)

        filed = self.client.post(
            reverse("reports_api:gst-portal-filing-file-evc"),
            {**base_payload, "pan": "AAAAA1111A", "evc_otp": "654321"},
            format="json",
        )
        self.assertEqual(filed.status_code, 200)
        self.assertEqual(filed.data["status"], GstPortalFilingRun.Status.FILED)
        self.assertEqual(filed.data["portal_reference"], "ACK-1")

        polled = self.client.post(reverse("reports_api:gst-portal-filing-poll-status"), base_payload, format="json")
        self.assertEqual(polled.status_code, 200)
        self.assertEqual(polled.data["stage"], "status_polled")
        self.assertEqual(polled.data["portal_response"]["status_poll"]["status"], "FILED")
        fake_client.return_status.assert_called_once()
