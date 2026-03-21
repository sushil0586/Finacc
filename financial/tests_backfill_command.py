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
        account.objects.filter(pk=acc.pk).update(
            gstno="29ABCDE1234F1Z5",
            pan="ABCDE1234F",
            partytype="Vendor",
            creditdays=30,
            address1="Addr 1",
            pincode="560001",
        )
        acc.refresh_from_db()

        self.assertFalse(AccountComplianceProfile.objects.filter(account=acc).exists())
        self.assertFalse(AccountCommercialProfile.objects.filter(account=acc).exists())
        self.assertFalse(AccountAddress.objects.filter(account=acc, isprimary=True, isactive=True).exists())

        call_command("backfill_account_profiles", entity_id=self.entity.id)

        self.assertTrue(AccountComplianceProfile.objects.filter(account=acc).exists())
        self.assertTrue(AccountCommercialProfile.objects.filter(account=acc).exists())
        self.assertTrue(AccountAddress.objects.filter(account=acc, isprimary=True, isactive=True).exists())

    def test_backfill_dry_run_does_not_write(self):
        acc = account.objects.create(
            entity=self.entity,
            accountname="Legacy Customer",
            createdby=self.user,
        )
        account.objects.filter(pk=acc.pk).update(
            gstno="27ABCDE1234F1Z5",
            pan="ABCDE1234F",
            address1="Addr X",
        )
        acc.refresh_from_db()

        out = StringIO()
        call_command("backfill_account_profiles", entity_id=self.entity.id, dry_run=True, stdout=out)

        self.assertFalse(AccountComplianceProfile.objects.filter(account=acc).exists())
        self.assertFalse(AccountCommercialProfile.objects.filter(account=acc).exists())
        self.assertFalse(AccountAddress.objects.filter(account=acc, isprimary=True, isactive=True).exists())
        self.assertIn("DRY RUN", out.getvalue())
