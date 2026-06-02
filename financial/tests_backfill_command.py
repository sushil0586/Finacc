from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from Authentication.models import User
from entity.models import Entity
from financial.models import AccountAddress, AccountCommercialProfile, AccountComplianceProfile, Ledger, account, accountHead, accounttype
from financial.seeding import FinancialSeedService


class AccountProfilesBackfillCommandTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="fin-backfill@example.com",
            username="fin-backfill@example.com",
            password="secret123",
            email_verified=True,
        )
        self.entity = Entity.objects.create(entityname="Entity Backfill", createdby=self.user)

    def test_backfill_creates_missing_normalized_profiles(self):
        acc = account.objects.create(
            entity=self.entity,
            accountname="Legacy Vendor",
            createdby=self.user,
        )
        AccountComplianceProfile.objects.filter(account=acc).delete()
        AccountCommercialProfile.objects.filter(account=acc).delete()

        self.assertFalse(AccountComplianceProfile.objects.filter(account=acc).exists())
        self.assertFalse(AccountCommercialProfile.objects.filter(account=acc).exists())
        self.assertFalse(AccountAddress.objects.filter(account=acc, isprimary=True, isactive=True).exists())

        call_command("backfill_account_profiles", entity_id=self.entity.id)

        self.assertTrue(AccountComplianceProfile.objects.filter(account=acc).exists())
        self.assertTrue(AccountCommercialProfile.objects.filter(account=acc).exists())
        self.assertFalse(AccountAddress.objects.filter(account=acc, isprimary=True, isactive=True).exists())

    def test_backfill_dry_run_does_not_write(self):
        acc = account.objects.create(
            entity=self.entity,
            accountname="Legacy Customer",
            createdby=self.user,
        )
        AccountComplianceProfile.objects.filter(account=acc).delete()
        AccountCommercialProfile.objects.filter(account=acc).delete()

        out = StringIO()
        call_command("backfill_account_profiles", entity_id=self.entity.id, dry_run=True, stdout=out)

        self.assertFalse(AccountComplianceProfile.objects.filter(account=acc).exists())
        self.assertFalse(AccountCommercialProfile.objects.filter(account=acc).exists())
        self.assertFalse(AccountAddress.objects.filter(account=acc, isprimary=True, isactive=True).exists())
        self.assertIn("DRY RUN", out.getvalue())

    def test_backfill_reports_zero_missing_primary_address_after_cutover(self):
        acc = account.objects.create(
            entity=self.entity,
            accountname="Legacy Address Not Copied",
            createdby=self.user,
        )
        AccountComplianceProfile.objects.filter(account=acc).delete()
        AccountCommercialProfile.objects.filter(account=acc).delete()

        out = StringIO()
        call_command("backfill_account_profiles", entity_id=self.entity.id, dry_run=True, stdout=out)
        self.assertIn("Missing primary addresses: 0", out.getvalue())


class FinancialGovernanceRepairCommandTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="fin-governance-command@example.com",
            username="fin-governance-command@example.com",
            password="secret123",
            email_verified=True,
        )
        self.entity = Entity.objects.create(entityname="Governance Repair Entity", createdby=self.user)
        FinancialSeedService.seed_entity(entity=self.entity, actor=self.user, template_code="indian_accounting_final")
        self.party_type = accounttype.objects.get(entity=self.entity, accounttypename="Party")
        self.vendor_head = accountHead.objects.get(entity=self.entity, code=6100)
        self.creditor_head = accountHead.objects.get(entity=self.entity, code=7000)

    def test_governance_repair_dry_run_reports_without_writing(self):
        legacy = Ledger.objects.create(
            entity=self.entity,
            ledger_code=None,
            name="Dry Run Vendor",
            legal_name="Dry Run Vendor",
            accounthead=self.vendor_head,
            creditaccounthead=self.creditor_head,
            accounttype=self.party_type,
            is_party=False,
            is_system=False,
            createdby=self.user,
        )

        out = StringIO()
        call_command(
            "repair_financial_governance",
            entity_id=self.entity.id,
            dry_run=True,
            report_rows=True,
            stdout=out,
        )

        legacy.refresh_from_db()
        self.assertIsNone(legacy.ledger_code)
        self.assertFalse(hasattr(legacy, "account_profile"))
        self.assertIn("DRY RUN", out.getvalue())
        self.assertIn("row: ledger_id=", out.getvalue())

    def test_governance_repair_applies_code_and_account_link(self):
        legacy = Ledger.objects.create(
            entity=self.entity,
            ledger_code=None,
            name="Apply Vendor",
            legal_name="Apply Vendor",
            accounthead=self.vendor_head,
            creditaccounthead=self.creditor_head,
            accounttype=self.party_type,
            is_party=False,
            is_system=False,
            createdby=self.user,
        )

        out = StringIO()
        call_command(
            "repair_financial_governance",
            entity_id=self.entity.id,
            report_rows=True,
            stdout=out,
        )

        legacy.refresh_from_db()
        self.assertIsNotNone(legacy.ledger_code)
        self.assertTrue(legacy.is_party)
        self.assertEqual(legacy.account_profile.accountname, "Apply Vendor")
        self.assertIn("APPLIED", out.getvalue())
