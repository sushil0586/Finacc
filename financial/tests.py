from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient, APIRequestFactory

from Authentication.models import User
from entity.models import Entity, SubEntity
from financial.bulk_accounts import commit_payload as commit_accounts_bulk_payload
from financial.bulk_accounts import export_payload as export_accounts_bulk_payload
from financial.bulk_accounts import template_payload as accounts_bulk_template_payload
from financial.models import AccountAddress, AccountBankDetails, AccountCommercialProfile, AccountComplianceProfile, ContactDetails, Ledger, ShippingDetails, account, accountHead, accounttype
from geography.models import City, Country, District, State
from financial.seeding import FinancialSeedService
from financial.serializers_ledger import AccountProfileV2ReadSerializer, AccountProfileV2WriteSerializer
from financial.services import (
    apply_normalized_profile_payload,
    create_account_with_synced_ledger,
    sync_account_profiles_for_account,
    sync_ledger_for_account,
)
from withholding.models import EntityPartyTaxProfile


class FinancialLedgerSyncTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(
            email="fin-tests@example.com",
            username="fin-tests@example.com",
            password="secret123",
            email_verified=True,
        )
        self.entity_a = Entity.objects.create(entityname="Entity A", createdby=self.user)
        self.entity_b = Entity.objects.create(entityname="Entity B", createdby=self.user)
        self.subentity = SubEntity.objects.create(entity=self.entity_a, subentityname="Head Office")

    def test_create_account_with_synced_ledger_allocates_codes_and_links(self):
        a1 = create_account_with_synced_ledger(
            account_data={
                "entity": self.entity_a,
                "accountname": "Cash Account",
                "createdby": self.user,
            }
        )
        a2 = create_account_with_synced_ledger(
            account_data={
                "entity": self.entity_a,
                "accountname": "Bank Account",
                "createdby": self.user,
            }
        )

        self.assertIsNotNone(a1.ledger_id)
        self.assertIsNotNone(a2.ledger_id)
        self.assertEqual(a1.entity_id, a1.ledger.entity_id)
        self.assertEqual(a2.entity_id, a2.ledger.entity_id)
        self.assertIsNotNone(a1.ledger.ledger_code)
        self.assertIsNotNone(a2.ledger.ledger_code)
        self.assertGreater(a2.ledger.ledger_code, a1.ledger.ledger_code)

    def test_create_account_with_cross_entity_ledger_rolls_back(self):
        foreign_ledger = Ledger.objects.create(
            entity=self.entity_b,
            ledger_code=1200,
            name="Foreign Ledger",
            createdby=self.user,
        )

        with self.assertRaises(ValidationError):
            create_account_with_synced_ledger(
                account_data={
                    "entity": self.entity_a,
                    "ledger": foreign_ledger,
                    "accountname": "Invalid Link",
                    "createdby": self.user,
                }
            )

        self.assertFalse(account.objects.filter(accountname="Invalid Link").exists())

    def test_sync_ledger_for_account_rejects_cross_entity_existing_link(self):
        foreign_ledger = Ledger.objects.create(
            entity=self.entity_b,
            ledger_code=1300,
            name="Cross Linked",
            createdby=self.user,
        )
        acc = account.objects.create(
            entity=self.entity_a,
            ledger=foreign_ledger,
            accountname="Bad Existing Link",
            createdby=self.user,
        )

        with self.assertRaises(ValidationError):
            sync_ledger_for_account(acc)

    def test_create_account_also_creates_normalized_profiles(self):
        acc = create_account_with_synced_ledger(
            account_data={
                "entity": self.entity_a,
                "accountname": "Vendor One",
                "createdby": self.user,
            }
        )
        apply_normalized_profile_payload(
            acc,
            compliance_data={"gstno": "29ABCDE1234F1Z5", "pan": "ABCDE1234F"},
            commercial_data={"partytype": "Vendor", "creditdays": 30},
            createdby=self.user,
        )
        comp = AccountComplianceProfile.objects.get(account=acc)
        comm = AccountCommercialProfile.objects.get(account=acc)
        self.assertEqual(comp.gstno, "29ABCDE1234F1Z5")
        self.assertEqual(comp.pan, "ABCDE1234F")
        self.assertEqual(comm.partytype, "Vendor")
        self.assertEqual(comm.creditdays, 30)

    def test_create_account_initializes_blank_normalized_profiles_without_legacy_copy(self):
        acc = create_account_with_synced_ledger(
            account_data={
                "entity": self.entity_a,
                "accountname": "Normalized Blank Init",
                "createdby": self.user,
            }
        )
        comp = AccountComplianceProfile.objects.get(account=acc)
        comm = AccountCommercialProfile.objects.get(account=acc)
        self.assertIsNone(comp.gstno)
        self.assertIsNone(comp.pan)
        self.assertIsNone(comm.partytype)
        self.assertIsNone(comm.creditdays)

    def test_profile_sync_does_not_copy_legacy_fields_after_cutover(self):
        acc = create_account_with_synced_ledger(
            account_data={
                "entity": self.entity_a,
                "accountname": "Customer One",
                "createdby": self.user,
            }
        )
        apply_normalized_profile_payload(
            acc,
            compliance_data={"gstno": "29ABCDE1234F1Z5", "pan": "ABCDE1234F"},
            commercial_data={"partytype": "Customer", "creditdays": 30},
            createdby=self.user,
        )
        sync_account_profiles_for_account(acc)

        comp = AccountComplianceProfile.objects.get(account=acc)
        comm = AccountCommercialProfile.objects.get(account=acc)
        self.assertEqual(comp.gstno, "29ABCDE1234F1Z5")
        self.assertEqual(comp.pan, "ABCDE1234F")
        self.assertEqual(comm.partytype, "Customer")
        self.assertEqual(comm.creditdays, 30)

    def test_account_read_serializer_uses_normalized_profiles_only(self):
        acc = create_account_with_synced_ledger(
            account_data={
                "entity": self.entity_a,
                "accountname": "Serializer Check",
                "createdby": self.user,
            }
        )
        apply_normalized_profile_payload(
            acc,
            compliance_data={"gstno": "29ABCDE1234F1Z5", "pan": "ABCDE1234F"},
            commercial_data={"partytype": "Vendor", "creditdays": 30},
            primary_address_data={"line1": "Profile Address 1"},
            createdby=self.user,
        )

        data = AccountProfileV2ReadSerializer(acc).data
        self.assertEqual(data["gstno"], "29ABCDE1234F1Z5")
        self.assertEqual(data["pan"], "ABCDE1234F")
        self.assertEqual(data["partytype"], "Vendor")
        self.assertEqual(data["creditdays"], 30)
        self.assertEqual(data["address1"], "Profile Address 1")

    def test_account_read_serializer_prefers_primary_contact_and_bank_details(self):
        acc = create_account_with_synced_ledger(
            account_data={
                "entity": self.entity_a,
                "accountname": "Contact Bank Check",
                "createdby": self.user,
            }
        )
        ContactDetails.objects.create(
            account=acc,
            entity=self.entity_a,
            createdby=self.user,
            full_name="Primary Person",
            phoneno="9999999999",
            emailid="primary@example.com",
            isprimary=True,
        )
        AccountBankDetails.objects.create(
            account=acc,
            entity=self.entity_a,
            createdby=self.user,
            bankname="Primary Bank",
            banKAcno="PRIMARY001",
            isprimary=True,
            isactive=True,
        )

        data = AccountProfileV2ReadSerializer(acc).data
        self.assertEqual(data["emailid"], "primary@example.com")
        self.assertEqual(data["contactno"], "9999999999")
        self.assertEqual(data["contactperson"], "Primary Person")
        self.assertEqual(data["bankname"], "Primary Bank")
        self.assertEqual(data["banKAcno"], "PRIMARY001")

    def test_account_write_serializer_persists_profile_data_without_legacy_columns(self):
        head = accountHead.objects.create(
            entity=self.entity_a,
            name="Sundry Creditors",
            code=2001,
            drcreffect="Credit",
            createdby=self.user,
        )
        serializer = AccountProfileV2WriteSerializer(
            data={
                "entity": self.entity_a.id,
                "accountname": "Normalized Writer",
                "accounthead": head.id,
                "compliance_profile": {
                    "gstno": "29ABCDE1234F1Z5",
                    "pan": "ABCDE1234F",
                },
                "commercial_profile": {
                    "partytype": "Vendor",
                    "creditdays": 45,
                },
                "primary_address": {
                    "line1": "Profile Address",
                    "pincode": "560001",
                },
            },
            context={"request": None},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        acc = serializer.save()

        acc.refresh_from_db()
        self.assertEqual(acc.accountname, "Normalized Writer")

        comp = AccountComplianceProfile.objects.get(account=acc)
        comm = AccountCommercialProfile.objects.get(account=acc)
        address = acc.addresses.filter(isprimary=True, isactive=True).first()
        self.assertEqual(comp.gstno, "29ABCDE1234F1Z5")
        self.assertEqual(comp.pan, "ABCDE1234F")
        self.assertEqual(comm.partytype, "Vendor")
        self.assertEqual(comm.creditdays, 45)
        self.assertIsNotNone(address)
        self.assertEqual(address.line1, "Profile Address")
        self.assertEqual(address.pincode, "560001")

    def test_account_write_serializer_persists_structured_msme_fields(self):
        head = accountHead.objects.create(
            entity=self.entity_a,
            name="MSME Vendors",
            code=2002,
            drcreffect="Credit",
            createdby=self.user,
        )
        serializer = AccountProfileV2WriteSerializer(
            data={
                "entity": self.entity_a.id,
                "accountname": "MSME Vendor",
                "accounthead": head.id,
                "compliance_profile": {
                    "msme": "legacy-msme-ref",
                    "msme_status": "micro",
                    "udyam_no": " udyam-ab-123 ",
                    "has_written_payment_terms": True,
                    "msme_credit_days": 45,
                },
                "commercial_profile": {
                    "partytype": "Vendor",
                    "creditdays": 30,
                },
            },
            context={"request": None},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        acc = serializer.save()

        compliance = AccountComplianceProfile.objects.get(account=acc)
        self.assertEqual(compliance.msme, "legacy-msme-ref")
        self.assertEqual(compliance.msme_status, "micro")
        self.assertEqual(compliance.udyam_no, "UDYAM-AB-123")
        self.assertTrue(compliance.has_written_payment_terms)
        self.assertEqual(compliance.msme_credit_days, 45)

    def test_account_write_serializer_rejects_invalid_msme_credit_days(self):
        head = accountHead.objects.create(
            entity=self.entity_a,
            name="MSME Validation",
            code=2003,
            drcreffect="Credit",
            createdby=self.user,
        )
        serializer = AccountProfileV2WriteSerializer(
            data={
                "entity": self.entity_a.id,
                "accountname": "Bad MSME Vendor",
                "accounthead": head.id,
                "compliance_profile": {
                    "msme_status": "small",
                    "msme_credit_days": 60,
                },
            },
            context={"request": None},
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("MSME credit days must be between 0 and 45.", str(serializer.errors))

    def test_account_read_serializer_exposes_structured_msme_fields(self):
        acc = create_account_with_synced_ledger(
            account_data={
                "entity": self.entity_a,
                "accountname": "MSME Serializer Check",
                "createdby": self.user,
            }
        )
        apply_normalized_profile_payload(
            acc,
            compliance_data={
                "msme": "legacy-flag",
                "msme_status": "small",
                "udyam_no": "UDYAM-PB-7788",
                "has_written_payment_terms": True,
                "msme_credit_days": 45,
            },
            commercial_data={"partytype": "Vendor", "creditdays": 30},
            createdby=self.user,
        )

        data = AccountProfileV2ReadSerializer(acc).data
        self.assertEqual(data["msme"], "legacy-flag")
        self.assertEqual(data["msme_status"], "small")
        self.assertEqual(data["udyam_no"], "UDYAM-PB-7788")
        self.assertTrue(data["has_written_payment_terms"])
        self.assertEqual(data["msme_credit_days"], 45)

    def test_account_read_serializer_includes_scoped_withholding_profile(self):
        acc = create_account_with_synced_ledger(
            account_data={
                "entity": self.entity_a,
                "accountname": "Scoped Withholding Read",
                "createdby": self.user,
            }
        )
        apply_normalized_profile_payload(
            acc,
            compliance_data={"pan": "ABCDE1234F"},
            createdby=self.user,
        )
        EntityPartyTaxProfile.objects.create(
            entity=self.entity_a,
            subentity=self.subentity,
            party_account=acc,
            residency_status="non_resident",
            tax_identifier="TIN-001",
            declaration_reference="DECL-9",
            is_exempt_withholding=True,
            is_active=True,
        )

        request = self.factory.get("/api/financial/accounts-v2/1?subentity_id=%s" % self.subentity.id)
        data = AccountProfileV2ReadSerializer(acc, context={"request": request}).data

        self.assertEqual(data["withholding_profile"]["subentity"], self.subentity.id)
        self.assertEqual(data["withholding_profile"]["pan"], "ABCDE1234F")
        self.assertEqual(data["withholding_profile"]["residency_status"], "non_resident")
        self.assertEqual(data["withholding_profile"]["tax_identifier"], "TIN-001")
        self.assertTrue(data["withholding_profile"]["is_exempt_withholding"])

    def test_account_write_serializer_persists_withholding_profile(self):
        head = accountHead.objects.create(
            entity=self.entity_a,
            name="Scoped Withholding Writer",
            code=2004,
            drcreffect="Credit",
            createdby=self.user,
        )
        serializer = AccountProfileV2WriteSerializer(
            data={
                "entity": self.entity_a.id,
                "accountname": "Withholding Writer",
                "accounthead": head.id,
                "compliance_profile": {"pan": "ABCDE1234F"},
                "withholding_profile": {
                    "subentity": self.subentity.id,
                    "residency_status": "non_resident",
                    "tax_identifier": "TIN-909",
                    "declaration_reference": "DECL-22",
                    "is_exempt_withholding": True,
                },
            },
            context={"request": None},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        acc = serializer.save()

        scoped = EntityPartyTaxProfile.objects.get(entity=self.entity_a, subentity=self.subentity, party_account=acc)
        self.assertEqual(scoped.residency_status, "non_resident")
        self.assertEqual(scoped.tax_identifier, "TIN-909")
        self.assertEqual(scoped.declaration_reference, "DECL-22")
        self.assertTrue(scoped.is_exempt_withholding)


class FinancialSeedTemplateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="fin-seed@example.com",
            username="fin-seed@example.com",
            password="secret123",
            email_verified=True,
        )
        self.entity = Entity.objects.create(entityname="Seed Entity", createdby=self.user)

    def test_indian_accounting_final_seed_creates_correct_advance_classification(self):
        FinancialSeedService.seed_entity(entity=self.entity, actor=self.user, template_code="indian_accounting_final")

        advance_payable_head = accountHead.objects.get(entity=self.entity, code=6000)
        advance_receivable_head = accountHead.objects.get(entity=self.entity, code=6100)
        advance_payable_ledger = Ledger.objects.get(entity=self.entity, ledger_code=6000)
        party_type = accounttype.objects.get(entity=self.entity, accounttypename="Party")

        self.assertEqual(advance_payable_head.accounttype.accounttypename, "Current Liabilities")
        self.assertEqual(advance_receivable_head.accounttype.accounttypename, "Current Assets")
        self.assertEqual(advance_payable_ledger.accounthead_id, advance_payable_head.id)
        self.assertEqual(advance_payable_ledger.creditaccounthead_id, advance_payable_head.id)
        self.assertTrue(party_type.isactive)

    def test_indian_accounting_final_seed_creates_static_ready_ledgers(self):
        FinancialSeedService.seed_entity(entity=self.entity, actor=self.user, template_code="indian_accounting_final")

        self.assertTrue(Ledger.objects.filter(entity=self.entity, ledger_code=5304, name="GST TDS Payable").exists())
        self.assertTrue(Ledger.objects.filter(entity=self.entity, ledger_code=7081, name="Round Off Income").exists())
        self.assertTrue(Ledger.objects.filter(entity=self.entity, ledger_code=8403, name="Round Off Expense").exists())

    def test_reconcile_entity_sets_party_heads_from_party_type(self):
        acc = create_account_with_synced_ledger(
            account_data={
                "entity": self.entity,
                "accountname": "Customer X",
                "createdby": self.user,
            }
        )
        apply_normalized_profile_payload(
            acc,
            commercial_data={"partytype": "Customer"},
            createdby=self.user,
        )
        acc.ledger.accounthead = None
        acc.ledger.accounttype = None
        acc.ledger.ledger_code = 99001
        acc.ledger.save(update_fields=["accounthead", "accounttype", "ledger_code"])

        FinancialSeedService.reconcile_entity(entity=self.entity, actor=self.user, template_code="indian_accounting_final")

        acc.refresh_from_db()
        self.assertEqual(acc.ledger.accounthead.code, 8000)
        self.assertEqual(acc.ledger.accounttype.accounttypename, "Current Assets")

    def test_seed_marks_both_party_type_control_accounts_as_party_ledgers(self):
        FinancialSeedService.seed_entity(entity=self.entity, actor=self.user, template_code="indian_accounting_final")

        creditors_control = Ledger.objects.get(entity=self.entity, ledger_code=7000)
        debtors_control = Ledger.objects.get(entity=self.entity, ledger_code=8000)

        self.assertTrue(creditors_control.is_party)
        self.assertTrue(debtors_control.is_party)

    def test_account_write_serializer_persists_primary_contact_and_bank_details(self):
        head = accountHead.objects.create(
            entity=self.entity,
            name="Sundry Creditors Contact",
            code=2003,
            drcreffect="Credit",
            createdby=self.user,
        )
        serializer = AccountProfileV2WriteSerializer(
            data={
                "entity": self.entity.id,
                "accountname": "Contact Writer",
                "accounthead": head.id,
                "emailid": "contact@example.com",
                "contactno": "8888888888",
                "contactperson": "Write Person",
                "bankname": "Writer Bank",
                "banKAcno": "WRITER001",
            },
            context={"request": None},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        acc = serializer.save()

        primary_contact = ContactDetails.objects.get(account=acc, isprimary=True)
        primary_bank = AccountBankDetails.objects.get(account=acc, isprimary=True, isactive=True)
        self.assertEqual(primary_contact.emailid, "contact@example.com")
        self.assertEqual(primary_contact.phoneno, "8888888888")
        self.assertEqual(primary_contact.full_name, "Write Person")
        self.assertEqual(primary_bank.bankname, "Writer Bank")
        self.assertEqual(primary_bank.banKAcno, "WRITER001")

    def test_account_write_serializer_rejects_legacy_profile_input_fields(self):
        head = accountHead.objects.create(
            entity=self.entity,
            name="Sundry Debtors",
            code=2002,
            drcreffect="Debit",
            createdby=self.user,
        )
        serializer = AccountProfileV2WriteSerializer(
            data={
                "entity": self.entity.id,
                "accountname": "Legacy Payload Rejected",
                "accounthead": head.id,
                "gstno": "29ABCDE1234F1Z5",
                "partytype": "Customer",
                "address1": "Old Flat Address",
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("gstno", serializer.errors)
        self.assertIn("partytype", serializer.errors)
        self.assertIn("address1", serializer.errors)

    def test_account_model_allows_create_without_legacy_profile_columns(self):
        acc = account.objects.create(
            entity=self.entity,
            accountname="Account Create",
            createdby=self.user,
        )
        self.assertEqual(acc.accountname, "Account Create")


class FinancialGeographyHierarchyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="geo-fin@example.com",
            username="geo-fin@example.com",
            password="secret123",
            email_verified=True,
        )
        self.entity = Entity.objects.create(entityname="Geo Entity", createdby=self.user)
        self.account = create_account_with_synced_ledger(
            account_data={
                "entity": self.entity,
                "accountname": "Geo Account",
                "createdby": self.user,
            }
        )
        self.country = Country.objects.create(countryname="India", countrycode="IN")
        self.state = State.objects.create(statename="Punjab", statecode="03", country=self.country)
        self.other_state = State.objects.create(statename="Haryana", statecode="06", country=self.country)
        self.district = District.objects.create(districtname="Fatehgarh Sahib", districtcode="FGS", state=self.state)
        self.city = City.objects.create(cityname="Sirhind", citycode="SRH", pincode="140406", distt=self.district)

    def test_account_address_rejects_city_from_other_state(self):
        with self.assertRaises(ValidationError):
            AccountAddress.objects.create(
                account=self.account,
                entity=self.entity,
                createdby=self.user,
                line1="Address 1",
                country=self.country,
                state=self.other_state,
                district=self.district,
                city=self.city,
                pincode="140406",
                isactive=True,
            )

    def test_contact_details_rejects_mismatched_district_and_state(self):
        with self.assertRaises(ValidationError):
            ContactDetails.objects.create(
                account=self.account,
                entity=self.entity,
                createdby=self.user,
                full_name="Geo Contact",
                country=self.country,
                state=self.other_state,
                district=self.district,
                city=self.city,
                pincode="140406",
                isprimary=True,
            )

    def test_shipping_details_accepts_consistent_hierarchy(self):
        row = ShippingDetails.objects.create(
            account=self.account,
            entity=self.entity,
            createdby=self.user,
            full_name="Geo Shipping",
            country=self.country,
            state=self.state,
            district=self.district,
            city=self.city,
            pincode="140406",
            isprimary=True,
        )
        self.assertIsNotNone(row.id)


class FinancialEndpointAliasTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="fin-alias@example.com",
            username="fin-alias@example.com",
            password="secret123",
            email_verified=True,
        )
        self.entity = Entity.objects.create(entityname="Alias Entity", createdby=self.user)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_legacy_base_account_list_alias_sets_deprecation_headers(self):
        response = self.client.get(f"/api/financial/baseaccountlistv2/?entity={self.entity.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("X-API-Deprecated"), "true")
        self.assertEqual(response.headers.get("X-API-Replacement"), "/api/financial/base-account-list-v2")

    def test_legacy_simple_accounts_alias_sets_deprecation_headers(self):
        response = self.client.get(f"/api/financial/accounts/simplev2?entity={self.entity.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("X-API-Deprecated"), "true")
        self.assertEqual(response.headers.get("X-API-Replacement"), "/api/financial/accounts/simple-v2")

    def test_legacy_account_list_post_alias_sets_deprecation_headers_even_on_error(self):
        response = self.client.post("/api/financial/accountListPostV2", data={}, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.headers.get("X-API-Deprecated"), "true")
        self.assertEqual(response.headers.get("X-API-Replacement"), "/api/financial/account-list-post-v2")

    def test_canonical_endpoint_has_no_deprecation_header(self):
        response = self.client.get(f"/api/financial/base-account-list-v2/?entity={self.entity.id}")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.headers.get("X-API-Deprecated"))

    def test_pure_ledger_create_does_not_auto_create_account_profile(self):
        head = accountHead.objects.create(
            entity=self.entity,
            name="Indirect Expense",
            code=3001,
            drcreffect="Debit",
            createdby=self.user,
        )
        response = self.client.post(
            "/api/financial/ledgers",
            data={
                "entity": self.entity.id,
                "ledger_code": 3001,
                "name": "Bank Charges",
                "accounthead": head.id,
                "is_party": False,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        ledger = Ledger.objects.get(id=response.data["id"])
        self.assertFalse(hasattr(ledger, "account_profile"))

    def test_party_ledger_create_auto_creates_account_profile(self):
        head = accountHead.objects.create(
            entity=self.entity,
            name="Sundry Creditors",
            code=3002,
            drcreffect="Credit",
            createdby=self.user,
        )
        response = self.client.post(
            "/api/financial/ledgers",
            data={
                "entity": self.entity.id,
                "ledger_code": 3002,
                "name": "Vendor A",
                "accounthead": head.id,
                "is_party": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        ledger = Ledger.objects.select_related("account_profile").get(id=response.data["id"])
        self.assertEqual(ledger.account_profile.accountname, "Vendor A")


class FinancialAccountsBulkCoverageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="fin-bulk@example.com",
            username="fin-bulk@example.com",
            password="secret123",
            email_verified=True,
        )
        self.entity = Entity.objects.create(entityname="Bulk Accounts Entity", createdby=self.user)
        self.head = accountHead.objects.create(
            entity=self.entity,
            name="Sundry Debtors",
            code=4100,
            drcreffect="Debit",
            createdby=self.user,
        )
        self.credit_head = accountHead.objects.create(
            entity=self.entity,
            name="Sundry Creditors",
            code=4200,
            drcreffect="Credit",
            createdby=self.user,
        )

    def test_template_and_export_include_extended_profile_fields(self):
        template_row = accounts_bulk_template_payload()["accounts"][0]
        for field in (
            "contactperson",
            "website",
            "contra_ledger",
            "gstintype",
            "gstregtype",
            "cin",
            "msme",
            "gsttdsno",
            "tdsno",
            "tdsrate",
            "tdssection",
            "tds_threshold",
            "istcsapplicable",
            "tcscode",
            "blockstatus",
            "blockedreason",
            "approved",
            "agent",
            "reminders",
            "bankname",
            "banKAcno",
        ):
            self.assertIn(field, template_row)

        acc = create_account_with_synced_ledger(
            account_data={
                "entity": self.entity,
                "accountname": "ABC Traders",
                "legalname": "ABC Traders Pvt Ltd",
                "website": "https://example.com",
                "createdby": self.user,
            },
            ledger_overrides={
                "ledger_code": 5100,
                "name": "ABC Traders",
                "legal_name": "ABC Traders Pvt Ltd",
                "accounthead_id": self.head.id,
                "creditaccounthead_id": self.credit_head.id,
                "is_party": True,
                "isactive": True,
            },
        )
        apply_normalized_profile_payload(
            acc,
            compliance_data={
                "gstno": "29ABCDE1234F1Z5",
                "pan": "ABCDE1234F",
                "gstintype": "Regular",
                "gstregtype": "Regular",
                "is_sez": True,
                "cin": "L12345KA2024PLC000001",
                "msme": "MSME123",
                "gsttdsno": "GSTTDS001",
                "tdsno": "TDS001",
                "tdsrate": "1.00",
                "tdssection": "194C",
                "tds_threshold": "50000.00",
                "istcsapplicable": True,
                "tcscode": "TCS206C",
            },
            commercial_data={
                "partytype": "Customer",
                "creditlimit": "1000.00",
                "creditdays": 15,
                "paymentterms": "Net15",
                "currency": "INR",
                "blockstatus": "Blocked",
                "blockedreason": "KYC pending",
                "approved": True,
                "agent": "Raj",
                "reminders": 3,
            },
            primary_contact_data={
                "emailid": "abc@example.com",
                "phoneno": "9876543210",
                "full_name": "Amit Sharma",
            },
            primary_bank_data={
                "bankname": "State Bank",
                "banKAcno": "1234567890",
            },
            createdby=self.user,
        )

        export_row = export_accounts_bulk_payload(self.entity)["accounts"][0]
        self.assertEqual(export_row["contactperson"], "Amit Sharma")
        self.assertEqual(export_row["website"], "https://example.com")
        self.assertEqual(export_row["gstintype"], "Regular")
        self.assertEqual(export_row["blockstatus"], "Blocked")
        self.assertEqual(export_row["bankname"], "State Bank")

    def test_commit_payload_persists_extended_profile_fields(self):
        payload = {
            "accounts": [
                {
                    "id": "",
                    "ledger_code": "7001",
                    "accountname": "XYZ Supplies",
                    "legalname": "XYZ Supplies LLP",
                    "emailid": "xyz@example.com",
                    "contactno": "9999999999",
                    "contactperson": "Priya",
                    "isactive": True,
                    "website": "https://xyz.example.com",
                    "accounthead": str(self.head.id),
                    "creditaccounthead": str(self.credit_head.id),
                    "contra_ledger": "",
                    "accounttype": "",
                    "openingbdr": "100.00",
                    "openingbcr": "0.00",
                    "canbedeleted": True,
                    "partytype": "Customer",
                    "gstno": "29ABCDE1234F1Z5",
                    "pan": "ABCDE1234F",
                    "gstintype": "Regular",
                    "gstregtype": "Regular",
                    "is_sez": True,
                    "cin": "L12345KA2024PLC000002",
                    "msme": "MSME456",
                    "gsttdsno": "GSTTDS002",
                    "tdsno": "TDS002",
                    "tdsrate": "2.00",
                    "tdssection": "194J",
                    "tds_threshold": "75000.00",
                    "istcsapplicable": True,
                    "tcscode": "TCS206C",
                    "creditlimit": "5000.00",
                    "creditdays": "30",
                    "paymentterms": "Net30",
                    "currency": "INR",
                    "blockstatus": "Active",
                    "blockedreason": "",
                    "approved": True,
                    "agent": "Neha",
                    "reminders": "2",
                    "bankname": "HDFC",
                    "banKAcno": "9988776655",
                    "line1": "Address 1",
                    "line2": "Address 2",
                    "floor_no": "3",
                    "street": "MG Road",
                    "country": "",
                    "state": "",
                    "district": "",
                    "city": "",
                    "pincode": "560001",
                }
            ]
        }

        result = commit_accounts_bulk_payload(payload, self.entity)

        self.assertEqual(result.errors, [])
        acc = account.objects.get(entity=self.entity, accountname="XYZ Supplies")
        self.assertEqual(acc.website, "https://xyz.example.com")
        self.assertEqual(acc.compliance_profile.gstintype, "Regular")
        self.assertEqual(acc.compliance_profile.tdssection, "194J")
        self.assertEqual(acc.commercial_profile.agent, "Neha")
        self.assertEqual(acc.commercial_profile.reminders, 2)
        self.assertEqual(acc.bank_details.get(isprimary=True).bankname, "HDFC")
        self.assertEqual(acc.contact_details.get(isprimary=True).full_name, "Priya")
