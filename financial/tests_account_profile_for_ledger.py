from django.contrib.auth import get_user_model
from django.test import TestCase

from entity.models import Entity, GstRegistrationType
from financial.models import Ledger, account
from financial.seeding import FinancialSeedService
from financial.services import ensure_account_profile_for_ledger


class EnsureAccountProfileForLedgerTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="ledger-profile",
            email="ledger-profile@example.com",
            password="testpass123",
        )
        self.gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="Ledger Profile Entity",
            legalname="Ledger Profile Entity Pvt Ltd",
            GstRegitrationType=self.gst_type,
            createdby=self.user,
        )

    def test_long_ledger_name_is_trimmed_for_account_profile(self):
        long_name = "L" * 240
        legal_name = "Legal " + ("N" * 220)
        ledger = Ledger.objects.create(
            entity=self.entity,
            ledger_code=9101,
            name=long_name,
            legal_name=legal_name,
            is_party=True,
            createdby=self.user,
        )

        profile = ensure_account_profile_for_ledger(ledger=ledger, createdby=self.user)

        profile.refresh_from_db()
        self.assertEqual(profile.ledger_id, ledger.id)
        self.assertEqual(len(profile.accountname), account._meta.get_field("accountname").max_length)
        self.assertEqual(profile.accountname, long_name[:200])
        self.assertEqual(profile.legalname, legal_name)

    def test_reconcile_entity_trims_long_ledger_name_when_syncing_profile(self):
        long_name = "R" * 240
        ledger = Ledger.objects.create(
            entity=self.entity,
            ledger_code=9102,
            name=long_name,
            legal_name="Reconcilable Long Ledger",
            is_party=True,
            createdby=self.user,
        )

        FinancialSeedService.reconcile_entity(entity=self.entity, actor=self.user)

        profile = account.objects.get(ledger=ledger)
        self.assertEqual(profile.accountname, long_name[:200])
