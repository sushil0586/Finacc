from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from Authentication.models import User
from entity.models import Entity
from financial.models import AccountAddress, AccountCommercialProfile, AccountComplianceProfile, account


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
