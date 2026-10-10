from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from importlib import import_module
from threading import Barrier
from types import SimpleNamespace

from django.db import close_old_connections
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITransactionTestCase

from errorlogger.models import ErrorLog
from financial.models import Ledger
from financial.seeding import FinancialSeedService
from posting.models import EntityStaticAccountMap, Entry, JournalLine, StaticAccount
from posting.services.static_accounts import StaticAccountService
from payments.models import PaymentVoucherHeader
from purchase.models.purchase_ap import VendorBillOpenItem, VendorSettlement
from purchase.models.purchase_core import PurchaseInvoiceHeader
from purchase.services.purchase_settings_service import PurchaseSettingsService
from sales.models import SalesInvoiceHeader
from sales.services.sales_settings_service import SalesSettingsService
from subscriptions.models import UserEntityAccess
from subscriptions.services import SubscriptionService
from vouchers.models import VoucherHeader
from vouchers.services.voucher_settings_service import VoucherSettingsService

_sales_e2e = import_module("sales.tests_e2e_api")
_purchase_e2e = import_module("purchase.tests_e2e_api")


class _ConcurrentApiMixin:
    worker_counts = (2, 5, 10)

    def _client_for_worker(self) -> APIClient:
        client = APIClient()
        client.force_authenticate(user=self.user)
        return client

    def _run_concurrently(self, count: int, callback):
        barrier = Barrier(count)

        def worker(index: int):
            close_old_connections()
            try:
                barrier.wait(timeout=15)
                return callback(index)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=count) as executor:
            return list(executor.map(worker, range(count)))

    def _seed_posting_mappings(self):
        FinancialSeedService.seed_entity(entity=self.entity, actor=self.user, template_code="indian_accounting_final")
        StaticAccountService.seed_static_account_master()
        StaticAccountService.seed_required_entity_mappings(entity=self.entity, actor=self.user)
        static_ledger_codes = {
            "PURCHASE_DEFAULT": 1001,
            "PURCHASE_MISC_EXPENSE": 8351,
            "ROUND_OFF_INCOME": 7081,
            "ROUND_OFF_EXPENSE": 8403,
            "INPUT_CGST": 6501,
            "INPUT_SGST": 6502,
            "INPUT_IGST": 6503,
            "INPUT_CESS": 6504,
            "OUTPUT_CGST": 6601,
            "OUTPUT_SGST": 6602,
            "OUTPUT_IGST": 6603,
            "OUTPUT_CESS": 6604,
            "SALES_DEFAULT": 3001,
            "SALES_REVENUE": 3002,
        }
        for static_code, ledger_code in static_ledger_codes.items():
            static_account = StaticAccount.objects.get(code=static_code)
            ledger = Ledger.objects.get(entity=self.entity, ledger_code=ledger_code)
            EntityStaticAccountMap.objects.update_or_create(
                entity=self.entity,
                sub_entity=None,
                static_account=static_account,
                defaults={"account": ledger.account_profile, "ledger": ledger, "createdby": self.user},
            )
        StaticAccountService.invalidate(self.entity.id)

    def _assert_balanced_entries_for(self, *, voucher_no: str):
        entries = Entry.objects.filter(voucher_no=voucher_no)
        self.assertTrue(entries.exists(), f"No posting entry found for voucher {voucher_no}")
        for entry in entries:
            lines = JournalLine.objects.filter(entry=entry)
            debit = sum(line.amount for line in lines if line.drcr)
            credit = sum(line.amount for line in lines if not line.drcr)
            self.assertEqual(debit, credit, f"Unbalanced entry {entry.id} for voucher {voucher_no}")

    def _prepare_subscription_access_for_tenant(self, *, tenant: dict) -> None:
        customer_account = SubscriptionService.ensure_customer_account(user=self.user)
        SubscriptionService.ensure_active_subscription(customer_account=customer_account)
        SubscriptionService.ensure_account_membership(
            customer_account=customer_account,
            user=self.user,
            role=UserEntityAccess.Role.OWNER,
            granted_by=self.user,
        )
        entity = tenant["entity"]
        if getattr(entity, "customer_account_id", None) != customer_account.id:
            entity.customer_account = customer_account
            entity.save(update_fields=["customer_account", "updated_at"])


class SalesInvoicePhase2AConcurrencyTests(_ConcurrentApiMixin, APITransactionTestCase):
    databases = {"default"}

    _scope_qs = _sales_e2e.SalesApiEndToEndTests._scope_qs
    _goods_line_payload = _sales_e2e.SalesApiEndToEndTests._goods_line_payload
    _service_line_payload = _sales_e2e.SalesApiEndToEndTests._service_line_payload
    _invoice_payload = _sales_e2e.SalesApiEndToEndTests._invoice_payload
    _create_invoice = _sales_e2e.SalesApiEndToEndTests._create_invoice

    def setUp(self):
        _sales_e2e.SalesApiEndToEndTests.setUp(self)
        self._seed_posting_mappings()

    def test_sales_invoice_concurrent_confirm_allocates_unique_vouchers_at_2_5_10_workers(self):
        next_doc_no = 1001
        for worker_count in self.worker_counts:
            invoices = [
                self._create_invoice(
                    reference=f"PH2A-SALES-CONFIRM-{worker_count}-{index}",
                    lines=[self._service_line_payload()],
                    endpoint="/api/sales/service-invoices/",
                )
                for index in range(worker_count)
            ]

            def confirm(index: int):
                client = self._client_for_worker()
                return client.post(
                    f"/api/sales/service-invoices/{invoices[index]['id']}/confirm/{self._scope_qs()}",
                    {},
                    format="json",
                )

            responses = self._run_concurrently(worker_count, confirm)
            for response in responses:
                self.assertEqual(response.status_code, status.HTTP_200_OK, response.json())

            rows = list(
                SalesInvoiceHeader.objects.filter(id__in=[row["id"] for row in invoices])
                .order_by("doc_no")
                .values_list("doc_no", "invoice_number", "status")
            )
            doc_nos = [row[0] for row in rows]
            self.assertEqual(doc_nos, list(range(next_doc_no, next_doc_no + worker_count)))
            self.assertEqual(len(set(row[1] for row in rows)), worker_count)
            self.assertEqual({row[2] for row in rows}, {SalesInvoiceHeader.Status.CONFIRMED})
            next_doc_no += worker_count

    def test_sales_invoice_concurrent_post_is_idempotent_for_same_invoice(self):
        created = self._create_invoice(
            reference="PH2A-SALES-SAME-POST",
            lines=[self._service_line_payload()],
            endpoint="/api/sales/service-invoices/",
        )
        confirm_resp = self.client.post(
            f"/api/sales/service-invoices/{created['id']}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        def post(_index: int):
            client = self._client_for_worker()
            return client.post(
                f"/api/sales/service-invoices/{created['id']}/post/{self._scope_qs()}",
                {},
                format="json",
            )

        responses = self._run_concurrently(2, post)
        for response in responses:
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.json())

        header = SalesInvoiceHeader.objects.get(pk=created["id"])
        self.assertEqual(header.status, SalesInvoiceHeader.Status.POSTED)
        self._assert_balanced_entries_for(voucher_no=header.invoice_number)
        self.assertEqual(
            SalesInvoiceHeader.objects.filter(
                entity=self.entity,
                entityfinid=self.entityfin,
                subentity=self.subentity,
                doc_code=header.doc_code,
                doc_no=header.doc_no,
            ).count(),
            1,
        )


class PurchaseInvoicePhase2AConcurrencyTests(_ConcurrentApiMixin, APITransactionTestCase):
    databases = {"default"}

    _scope_qs = _purchase_e2e.PurchaseApiEndToEndTests._scope_qs
    _goods_line_payload = _purchase_e2e.PurchaseApiEndToEndTests._goods_line_payload
    _service_line_payload = _purchase_e2e.PurchaseApiEndToEndTests._service_line_payload
    _invoice_payload = _purchase_e2e.PurchaseApiEndToEndTests._invoice_payload
    _create_invoice = _purchase_e2e.PurchaseApiEndToEndTests._create_invoice

    def setUp(self):
        _purchase_e2e.PurchaseApiEndToEndTests.setUp(self)
        self._sales_entity_scope_patch = _purchase_e2e.patch(
            "sales.views.sales_invoice_views.EffectivePermissionService.entity_for_user",
            side_effect=lambda _user, entity_id: SimpleNamespace(id=int(entity_id)),
        )
        self._sales_codes_patch = _purchase_e2e.patch(
            "sales.views.sales_invoice_views.EffectivePermissionService.permission_codes_for_user",
            return_value={
                "sales.invoice.view",
                "sales.invoice.read",
                "sales.invoice.list",
                "sales.invoice.create",
                "sales.invoice.update",
                "sales.invoice.edit",
                "sales.invoice.confirm",
                "sales.invoice.post",
                "sales.invoice.cancel",
            },
        )
        self._sales_entity_scope_patch.start()
        self._sales_codes_patch.start()
        self.addCleanup(self._sales_entity_scope_patch.stop)
        self.addCleanup(self._sales_codes_patch.stop)
        self._voucher_codes_patch = _purchase_e2e.patch(
            "vouchers.views.voucher.EffectivePermissionService.permission_codes_for_user",
            return_value={
                "sales.invoice.view",
                "sales.invoice.read",
                "sales.invoice.list",
                "sales.invoice.create",
                "sales.invoice.update",
                "sales.invoice.edit",
                "sales.invoice.confirm",
                "sales.invoice.post",
                "sales.invoice.cancel",
                "voucher.journal.view",
                "voucher.journal.create",
                "voucher.journal.update",
                "voucher.journal.confirm",
                "voucher.journal.post",
                "voucher.journal.unpost",
                "voucher.journal.cancel",
                "voucher.journal.submit",
                "voucher.journal.approve",
                "voucher.journal.reject",
            },
        )
        self._voucher_codes_patch.start()
        self.addCleanup(self._voucher_codes_patch.stop)
        tenant_a = {
            "entity": self.entity,
            "subentity": self.subentity,
            "entityfin": self.entityfin,
            "state_home": self.state_home,
            "state_other": self.state_other,
            "debit_head": self.debit_head,
            "credit_head": self.credit_head,
            "customer_gstin": "27VWXYZ1234F1Z5",
        }
        self._create_sales_customer_and_account(prefix="TENANTA", tenant=tenant_a)
        self.customer = tenant_a["customer"]
        self.sales_account = tenant_a["sales_account"]
        self._prepare_subscription_access_for_tenant(tenant=tenant_a)
        sales_doc_type, _ = _purchase_e2e.DocumentType.objects.get_or_create(
            module="sales",
            doc_key="sales_invoice",
            defaults={"name": "Sales Tax Invoice", "default_code": "SINV", "is_active": True},
        )
        _purchase_e2e.DocumentNumberSeries.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            doc_type=sales_doc_type,
            doc_code="SINV",
            prefix="TASI",
            starting_number=1001,
            current_number=1001,
            is_active=True,
            created_by=self.user,
        )
        SalesSettingsService.get_settings(
            self.entity.id,
            self.subentity.id,
            entityfinid_id=self.entityfin.id,
        )
        self._seed_posting_mappings()
        PurchaseSettingsService.upsert_settings(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            updates={"policy_controls": {"settlement_mode": "basic", "allocation_policy": "manual"}},
        )
        VoucherSettingsService.upsert_settings(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            updates={"default_doc_code_journal": "JV", "default_workflow_action": "draft"},
        )
        VoucherSettingsService.ensure_numbering_scope_for_type(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            voucher_type=VoucherHeader.VoucherType.JOURNAL,
            doc_code="JV",
        )

    def _create_manual_open_item(
        self,
        *,
        supplier_invoice_number: str,
        amount: str = "1180.00",
        lines: list[dict] | None = None,
    ) -> VendorBillOpenItem:
        created = self._create_invoice(
            supplier_invoice_number=supplier_invoice_number,
            lines=lines,
        )
        header = PurchaseInvoiceHeader.objects.get(pk=created["id"])
        return VendorBillOpenItem.objects.create(
            header=header,
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            vendor=self.vendor,
            vendor_ledger_id=self.vendor.ledger_id,
            doc_type=int(header.doc_type),
            bill_date=header.bill_date,
            due_date=header.bill_date,
            purchase_number=header.purchase_number,
            supplier_invoice_number=header.supplier_invoice_number,
            original_amount=amount,
            gross_amount=amount,
            tds_deducted="0.00",
            gst_tds_deducted="0.00",
            net_payable_amount=amount,
            settled_amount="0.00",
            outstanding_amount=amount,
            is_open=True,
        )

    def _create_payment_voucher(self, *, open_item: VendorBillOpenItem, amount: str, reference: str) -> int:
        response = self.client.post(
            "/api/payments/payment-vouchers/",
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "voucher_date": "2026-04-10",
                "payment_type": PaymentVoucherHeader.PaymentType.AGAINST_BILL,
                "supply_type": PaymentVoucherHeader.SupplyType.GOODS,
                "paid_from": self.cash_account.id,
                "paid_to": self.vendor.id,
                "payment_mode": self.cash_payment_mode.id,
                "cash_paid_amount": amount,
                "reference_number": reference,
                "narration": f"Phase 2A.2 payment {reference}",
                "allocations": [
                    {
                        "open_item": open_item.id,
                        "settled_amount": amount,
                        "is_full_settlement": Decimal(amount) == Decimal(open_item.outstanding_amount),
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.json())
        return int(response.json()["id"])

    def _create_sales_customer_and_account(self, *, prefix: str, tenant: dict):
        customer_ledger = _purchase_e2e.Ledger.objects.create(
            entity=tenant["entity"],
            ledger_code=9101,
            name=f"{prefix} Customer",
            accounthead=tenant["debit_head"],
            createdby=self.user,
        )
        customer = _purchase_e2e.create_account_with_synced_ledger(
            account_data={
                "entity": tenant["entity"],
                "ledger": customer_ledger,
                "accountname": f"{prefix} Customer",
                "createdby": self.user,
            },
            ledger_overrides={"ledger_code": 9101, "accounthead": tenant["debit_head"], "is_party": True},
        )
        _purchase_e2e.AccountCommercialProfile.objects.update_or_create(
            account=customer,
            defaults={"entity": tenant["entity"], "partytype": "Customer", "createdby": self.user},
        )
        _purchase_e2e.AccountComplianceProfile.objects.update_or_create(
            account=customer,
            defaults={"entity": tenant["entity"], "gstno": tenant["customer_gstin"], "createdby": self.user},
        )
        sales_ledger = _purchase_e2e.Ledger.objects.create(
            entity=tenant["entity"],
            ledger_code=9502,
            name=f"{prefix} Sales Revenue",
            accounthead=tenant["credit_head"],
            createdby=self.user,
        )
        sales_account = _purchase_e2e.create_account_with_synced_ledger(
            account_data={
                "entity": tenant["entity"],
                "ledger": sales_ledger,
                "accountname": f"{prefix} Sales Revenue",
                "createdby": self.user,
            },
            ledger_overrides={"ledger_code": 9502, "accounthead": tenant["credit_head"], "is_party": False},
        )
        tenant["customer"] = customer
        tenant["sales_account"] = sales_account

    def _create_independent_tenant(self, *, prefix: str, home_state_code: str, other_state_code: str, gstin: str) -> dict:
        country = _purchase_e2e.Country.objects.create(countryname=f"{prefix} India", countrycode=f"I{prefix[-1]}")
        state_home = _purchase_e2e.State.objects.create(statename=f"{prefix} Home", statecode=home_state_code, country=country)
        state_other = _purchase_e2e.State.objects.create(statename=f"{prefix} Other", statecode=other_state_code, country=country)
        district = _purchase_e2e.District.objects.create(districtname=f"{prefix} District", districtcode=f"{prefix[:6]}D", state=state_home)
        city = _purchase_e2e.City.objects.create(cityname=f"{prefix} City", citycode=f"{prefix[:6]}C", pincode="400001", distt=district)
        gst_type = _purchase_e2e.GstRegistrationType.objects.create(Name=f"{prefix} Regular", Description="Regular")
        entity = _purchase_e2e.Entity.objects.create(
            entityname=f"{prefix} Entity",
            legalname=f"{prefix} Entity Pvt Ltd",
            business_type=_purchase_e2e.Entity.BusinessType.MIXED,
            GstRegitrationType=gst_type,
            createdby=self.user,
        )
        subentity = _purchase_e2e.SubEntity.objects.create(entity=entity, subentityname=f"{prefix} Head Office")
        entityfin = _purchase_e2e.EntityFinancialYear.objects.create(
            entity=entity,
            desc=f"{prefix} FY 2026-27",
            finstartyear=timezone.make_aware(_purchase_e2e.datetime(2026, 4, 1)),
            finendyear=timezone.make_aware(_purchase_e2e.datetime(2027, 3, 31)),
            createdby=self.user,
        )
        _purchase_e2e.EntityAddress.objects.create(
            entity=entity,
            address_type=_purchase_e2e.EntityAddress.AddressType.REGISTERED,
            line1=f"{prefix} Address",
            country=country,
            state=state_home,
            district=district,
            city=city,
            pincode="400001",
            is_primary=True,
            createdby=self.user,
        )
        _purchase_e2e.EntityGstRegistration.objects.create(
            entity=entity,
            gstin=gstin,
            registration_type=gst_type,
            state=state_home,
            is_primary=True,
            createdby=self.user,
        )
        acc_type = _purchase_e2e.accounttype.objects.create(
            entity=entity,
            accounttypename=f"{prefix} Current",
            accounttypecode=f"{prefix[:4]}CL",
            createdby=self.user,
        )
        credit_head = _purchase_e2e.accountHead.objects.create(
            entity=entity,
            name=f"{prefix} Creditors",
            code=7000,
            balanceType="Credit",
            drcreffect="Credit",
            accounttype=acc_type,
            createdby=self.user,
        )
        debit_head = _purchase_e2e.accountHead.objects.create(
            entity=entity,
            name=f"{prefix} Purchase",
            code=1000,
            balanceType="Debit",
            drcreffect="Debit",
            accounttype=acc_type,
            createdby=self.user,
        )
        vendor_ledger = _purchase_e2e.Ledger.objects.create(
            entity=entity,
            ledger_code=9001,
            name=f"{prefix} Vendor",
            accounthead=credit_head,
            createdby=self.user,
        )
        vendor = _purchase_e2e.create_account_with_synced_ledger(
            account_data={"entity": entity, "ledger": vendor_ledger, "accountname": f"{prefix} Vendor", "createdby": self.user},
            ledger_overrides={"ledger_code": 9001, "accounthead": credit_head, "is_party": True},
        )
        _purchase_e2e.AccountCommercialProfile.objects.update_or_create(
            account=vendor,
            defaults={"entity": entity, "partytype": "Vendor", "createdby": self.user},
        )
        _purchase_e2e.AccountComplianceProfile.objects.update_or_create(
            account=vendor,
            defaults={"entity": entity, "gstno": f"{home_state_code}ABCDE1234F1Z5", "pan": "ABCDE1234F", "createdby": self.user},
        )
        service_ledger = _purchase_e2e.Ledger.objects.create(
            entity=entity,
            ledger_code=5001,
            name=f"{prefix} Service Expense",
            accounthead=debit_head,
            createdby=self.user,
        )
        service_purchase_account = _purchase_e2e.create_account_with_synced_ledger(
            account_data={"entity": entity, "ledger": service_ledger, "accountname": f"{prefix} Service Expense", "createdby": self.user},
            ledger_overrides={"ledger_code": 5001, "accounthead": debit_head, "is_party": False},
        )
        cash_ledger = _purchase_e2e.Ledger.objects.create(
            entity=entity,
            ledger_code=1002,
            name=f"{prefix} Cash",
            accounthead=debit_head,
            createdby=self.user,
        )
        cash_account = _purchase_e2e.create_account_with_synced_ledger(
            account_data={"entity": entity, "ledger": cash_ledger, "accountname": f"{prefix} Cash", "createdby": self.user},
            ledger_overrides={"ledger_code": 1002, "accounthead": debit_head, "is_party": False},
        )
        payment_mode = _purchase_e2e.PaymentMode.objects.create(
            paymentmode=f"{prefix} Cash",
            paymentmodecode=f"{prefix[:8]}CASH",
            iscash=True,
            createdby=self.user,
        )
        uom = _purchase_e2e.UnitOfMeasure.objects.create(entity=entity, code=f"{prefix[:4]}KG", description="Kilograms")
        product_category = _purchase_e2e.ProductCategory.objects.create(entity=entity, pcategoryname=f"{prefix} Goods")
        goods_product = _purchase_e2e.Product.objects.create(
            entity=entity,
            productname=f"{prefix} Product",
            sku=f"{prefix}-SKU",
            productdesc=f"{prefix} Product",
            productcategory=product_category,
            base_uom=uom,
            is_service=False,
            purchase_behavior=_purchase_e2e.ProductPurchaseBehavior.EXPENSE,
            purchase_account=service_purchase_account,
        )
        purchase_doc_type = _purchase_e2e.DocumentType.objects.create(module="purchase", name=f"{prefix} Purchase Invoice", doc_key=f"{prefix}_PURCHASE_TAX_INVOICE", default_code="PINV", is_active=True)
        payment_doc_type = _purchase_e2e.DocumentType.objects.create(module="payments", name=f"{prefix} Payment Voucher", doc_key=f"{prefix}_PAYMENT_VOUCHER", default_code="PPV", is_active=True)
        sales_doc_type, _ = _purchase_e2e.DocumentType.objects.get_or_create(
            module="sales",
            doc_key="sales_invoice",
            defaults={"name": "Sales Tax Invoice", "default_code": "SINV", "is_active": True},
        )
        for doc_type, code, prefix_code in (
            (purchase_doc_type, "PINV", f"{prefix[:3]}PI"),
            (payment_doc_type, "PPV", f"{prefix[:3]}PV"),
            (sales_doc_type, "SINV", f"{prefix[:3]}SI"),
        ):
            _purchase_e2e.DocumentNumberSeries.objects.create(
                entity=entity,
                entityfinid=entityfin,
                subentity=subentity,
                doc_type=doc_type,
                doc_code=code,
                prefix=prefix_code,
                starting_number=1001,
                current_number=1001,
                is_active=True,
                created_by=self.user,
            )
        tenant = {
            "entity": entity,
            "subentity": subentity,
            "entityfin": entityfin,
            "country": country,
            "state_home": state_home,
            "state_other": state_other,
            "gst_type": gst_type,
            "credit_head": credit_head,
            "debit_head": debit_head,
            "vendor": vendor,
            "service_purchase_account": service_purchase_account,
            "cash_account": cash_account,
            "cash_payment_mode": payment_mode,
            "uom": uom,
            "goods_product": goods_product,
            "seller_gstin": gstin,
            "vendor_gstin": f"{home_state_code}ABCDE1234F1Z5",
            "customer_gstin": f"{home_state_code}VWXYZ1234F1Z5",
        }
        self._create_sales_customer_and_account(prefix=prefix, tenant=tenant)
        self._prepare_subscription_access_for_tenant(tenant=tenant)
        current = self._capture_tenant_attrs()
        self._apply_tenant_attrs(tenant)
        self._seed_posting_mappings()
        SalesSettingsService.get_settings(entity.id, subentity.id, entityfinid_id=entityfin.id)
        PurchaseSettingsService.upsert_settings(
            entity_id=entity.id,
            subentity_id=subentity.id,
            updates={"policy_controls": {"settlement_mode": "basic", "allocation_policy": "manual"}},
        )
        VoucherSettingsService.upsert_settings(
            entity_id=entity.id,
            subentity_id=subentity.id,
            updates={"default_doc_code_journal": "JV", "default_workflow_action": "draft"},
        )
        VoucherSettingsService.ensure_numbering_scope_for_type(
            entity_id=entity.id,
            entityfinid_id=entityfin.id,
            subentity_id=subentity.id,
            voucher_type=VoucherHeader.VoucherType.JOURNAL,
            doc_code="JV",
        )
        self._apply_tenant_attrs(current)
        return tenant

    def _capture_tenant_attrs(self) -> dict:
        keys = (
            "entity", "subentity", "entityfin", "country", "state_home", "state_other", "gst_type",
            "vendor", "service_purchase_account", "cash_account", "cash_payment_mode", "uom",
            "goods_product", "customer", "sales_account", "debit_head", "credit_head",
        )
        return {key: getattr(self, key, None) for key in keys}

    def _apply_tenant_attrs(self, tenant: dict) -> None:
        self.entity = tenant["entity"]
        self.subentity = tenant["subentity"]
        self.entityfin = tenant["entityfin"]
        self.country = tenant.get("country", getattr(self, "country", None))
        self.state_home = tenant["state_home"]
        self.state_other = tenant["state_other"]
        self.gst_type = tenant.get("gst_type", getattr(self, "gst_type", None))
        self.vendor = tenant["vendor"]
        self.service_purchase_account = tenant["service_purchase_account"]
        self.cash_account = tenant["cash_account"]
        self.cash_payment_mode = tenant["cash_payment_mode"]
        self.uom = tenant["uom"]
        self.goods_product = tenant["goods_product"]
        self.customer = tenant.get("customer", getattr(self, "customer", None))
        self.sales_account = tenant.get("sales_account", getattr(self, "sales_account", None))
        self.debit_head = tenant.get("debit_head", getattr(self, "debit_head", None))
        self.credit_head = tenant.get("credit_head", getattr(self, "credit_head", None))

    def _primary_tenant(self) -> dict:
        return {
            "entity": self.entity,
            "subentity": self.subentity,
            "entityfin": self.entityfin,
            "state_home": self.state_home,
            "state_other": self.state_other,
            "vendor": self.vendor,
            "service_purchase_account": self.service_purchase_account,
            "cash_account": self.cash_account,
            "cash_payment_mode": self.cash_payment_mode,
            "uom": self.uom,
            "goods_product": self.goods_product,
            "customer": self.customer,
            "sales_account": self.sales_account,
            "seller_gstin": "27AAAAA1234A1Z5",
            "vendor_gstin": "27ABCDE1234F1Z5",
            "customer_gstin": "27VWXYZ1234F1Z5",
        }

    def _tenant_scope_qs(self, tenant: dict) -> str:
        return f"?entity={tenant['entity'].id}&entityfinid={tenant['entityfin'].id}&subentity={tenant['subentity'].id}"

    def _sales_scope_qs_for(self, tenant: dict) -> str:
        return f"?entity_id={tenant['entity'].id}&entityfinid={tenant['entityfin'].id}&subentity_id={tenant['subentity'].id}"

    def _sales_service_line_for(self, tenant: dict) -> dict:
        return {
            "id": None,
            "line_no": 1,
            "product": None,
            "sales_account": tenant["sales_account"].id,
            "uom": None,
            "hsn_sac_code": "998311",
            "qty": "1.000",
            "free_qty": "0.000",
            "rate": "500.0000",
            "productDesc": "Phase 2A.3 service",
            "is_service": True,
            "discount_type": 0,
            "discount_percent": "0.0000",
            "discount_amount": "0.00",
            "gst_rate": "18.00",
            "cess_percent": "0.00",
            "cess_amount": "0.00",
        }

    def _create_sales_invoice_for_tenant(self, *, client: APIClient, tenant: dict, reference: str) -> int:
        payload = {
            "doc_type": int(SalesInvoiceHeader.DocType.TAX_INVOICE),
            "bill_date": "2026-04-10",
            "credit_days": 5,
            "doc_code": "SINV",
            "customer": tenant["customer"].id,
            "customer_name": tenant["customer"].accountname,
            "customer_gstin": tenant["customer_gstin"],
            "customer_state_code": tenant["state_home"].statecode,
            "seller_gstin": tenant["seller_gstin"],
            "seller_state_code": tenant["state_home"].statecode,
            "place_of_supply_state_code": tenant["state_other"].statecode,
            "supply_category": int(SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B),
            "taxability": int(SalesInvoiceHeader.Taxability.TAXABLE),
            "reference": reference,
            "entity": tenant["entity"].id,
            "entityfinid": tenant["entityfin"].id,
            "subentity": tenant["subentity"].id,
            "lines": [self._sales_service_line_for(tenant)],
            "charges": [],
            "custom_fields": {},
            "withholding_enabled": False,
        }
        response = client.post("/api/sales/service-invoices/", payload, format="json")
        existing_sales_rows = list(
            SalesInvoiceHeader.objects.filter(entity=tenant["entity"])
            .order_by("id")
            .values("id", "entity_id", "entityfinid_id", "subentity_id", "doc_type", "doc_code", "doc_no", "invoice_number", "reference", "seller_gstin", "status")
        )
        recent_errors = list(
            ErrorLog.objects.filter(path="/api/sales/service-invoices/")
            .order_by("-id")
            .values_list("message", "stacktrace")[:3]
        )
        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            {
                "response": response.json(),
                "reference": reference,
                "entity_id": tenant["entity"].id,
                "entityfinid_id": tenant["entityfin"].id,
                "subentity_id": tenant["subentity"].id,
                "customer_id": tenant["customer"].id,
                "seller_gstin": tenant["seller_gstin"],
                "existing_sales_rows": existing_sales_rows,
                "recent_errors": [(message, stacktrace[-800:]) for message, stacktrace in recent_errors],
            },
        )
        return int(response.json()["id"])

    def _purchase_service_line_for(self, tenant: dict, *, product_desc: str) -> dict:
        return {
            "id": None,
            "line_no": 1,
            "product": None,
            "purchase_account": tenant["service_purchase_account"].id,
            "uom": None,
            "qty": "1.0000",
            "free_qty": "0.0000",
            "rate": "500.00",
            "product_desc": product_desc,
            "is_service": True,
            "hsn_sac": "998311",
            "taxability": int(PurchaseInvoiceHeader.Taxability.TAXABLE),
            "gst_rate": "18.00",
            "cgst_percent": "0.00",
            "sgst_percent": "0.00",
            "igst_percent": "18.00",
            "taxable_value": "500.00",
            "cgst_amount": "0.00",
            "sgst_amount": "0.00",
            "igst_amount": "90.00",
            "cess_percent": "0.00",
            "cess_amount": "0.00",
            "line_total": "590.00",
            "is_itc_eligible": True,
        }

    def _create_purchase_invoice_for_tenant(self, *, client: APIClient, tenant: dict, supplier_invoice_number: str) -> int:
        payload = {
            "doc_type": int(PurchaseInvoiceHeader.DocType.TAX_INVOICE),
            "bill_date": "2026-04-10",
            "posting_date": "2026-04-10",
            "supplier_invoice_number": supplier_invoice_number,
            "supplier_invoice_date": "2026-04-10",
            "vendor": tenant["vendor"].id,
            "vendor_name": tenant["vendor"].accountname,
            "vendor_gstin": tenant["vendor_gstin"],
            "vendor_state": tenant["state_home"].id,
            "supplier_state": tenant["state_home"].id,
            "place_of_supply_state": tenant["state_other"].id,
            "supply_category": int(PurchaseInvoiceHeader.SupplyCategory.DOMESTIC),
            "default_taxability": int(PurchaseInvoiceHeader.Taxability.TAXABLE),
            "tax_regime": int(PurchaseInvoiceHeader.TaxRegime.INTER),
            "is_igst": True,
            "is_reverse_charge": False,
            "is_itc_eligible": True,
            "itc_claim_status": int(PurchaseInvoiceHeader.ItcClaimStatus.PENDING),
            "status": int(PurchaseInvoiceHeader.Status.DRAFT),
            "entity": tenant["entity"].id,
            "entityfinid": tenant["entityfin"].id,
            "subentity": tenant["subentity"].id,
            "lines": [self._purchase_service_line_for(tenant, product_desc=supplier_invoice_number)],
            "charges": [],
            "custom_fields": {},
            "withholding_enabled": False,
            "gst_tds_enabled": False,
            "vendor_gst_tds_declared": False,
            "vendor_tds_declared": False,
        }
        response = client.post("/api/purchase/purchase-invoices/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.json())
        return int(response.json()["id"])

    def _create_open_item_for_tenant(self, *, tenant: dict, header_id: int, amount: str) -> VendorBillOpenItem:
        header = PurchaseInvoiceHeader.objects.get(pk=header_id)
        return VendorBillOpenItem.objects.create(
            header=header,
            entity=tenant["entity"],
            entityfinid=tenant["entityfin"],
            subentity=tenant["subentity"],
            vendor=tenant["vendor"],
            vendor_ledger_id=tenant["vendor"].ledger_id,
            doc_type=int(header.doc_type),
            bill_date=header.bill_date,
            due_date=header.bill_date,
            purchase_number=header.purchase_number,
            supplier_invoice_number=header.supplier_invoice_number,
            original_amount=amount,
            gross_amount=amount,
            tds_deducted="0.00",
            gst_tds_deducted="0.00",
            net_payable_amount=amount,
            settled_amount="0.00",
            outstanding_amount=amount,
            is_open=True,
        )

    def _create_payment_voucher_for_tenant(self, *, client: APIClient, tenant: dict, open_item: VendorBillOpenItem, amount: str, reference: str) -> int:
        response = client.post(
            "/api/payments/payment-vouchers/",
            {
                "entity": tenant["entity"].id,
                "entityfinid": tenant["entityfin"].id,
                "subentity": tenant["subentity"].id,
                "voucher_date": "2026-04-10",
                "payment_type": PaymentVoucherHeader.PaymentType.AGAINST_BILL,
                "supply_type": PaymentVoucherHeader.SupplyType.GOODS,
                "paid_from": tenant["cash_account"].id,
                "paid_to": tenant["vendor"].id,
                "payment_mode": tenant["cash_payment_mode"].id,
                "cash_paid_amount": amount,
                "reference_number": reference,
                "narration": f"Phase 2A.3 payment {reference}",
                "allocations": [{"open_item": open_item.id, "settled_amount": amount, "is_full_settlement": True}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.json())
        return int(response.json()["id"])

    def _create_journal_voucher_for_tenant(self, *, client: APIClient, tenant: dict, reference: str, amount: str = "100.00") -> int:
        response = client.post(
            f"/api/vouchers/vouchers/{self._tenant_scope_qs(tenant)}",
            {
                "entity": tenant["entity"].id,
                "entityfinid": tenant["entityfin"].id,
                "subentity": tenant["subentity"].id,
                "voucher_date": "2026-04-10",
                "doc_code": "JV",
                "voucher_type": VoucherHeader.VoucherType.JOURNAL,
                "reference_number": reference,
                "narration": f"Phase 2B.1 journal {reference}",
                "lines": [
                    {
                        "line_no": 1,
                        "ledger_account": tenant["service_purchase_account"].id,
                        "narration": "Journal debit",
                        "dr_amount": amount,
                        "cr_amount": "0.00",
                    },
                    {
                        "line_no": 2,
                        "ledger_account": tenant["cash_account"].id,
                        "narration": "Journal credit",
                        "dr_amount": "0.00",
                        "cr_amount": amount,
                    },
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.json())
        return int(response.json()["id"])

    def test_purchase_invoice_concurrent_confirm_allocates_unique_vouchers_at_2_5_10_workers(self):
        next_doc_no = 1001
        for worker_count in self.worker_counts:
            invoices = [
                self._create_invoice(
                    supplier_invoice_number=f"PH2A-PUR-CONFIRM-{worker_count}-{index}",
                    lines=[self._service_line_payload(product_desc=f"PH2A service {worker_count}-{index}")],
                )
                for index in range(worker_count)
            ]

            def confirm(index: int):
                client = self._client_for_worker()
                return client.post(
                    f"/api/purchase/purchase-invoices/{invoices[index]['id']}/confirm/{self._scope_qs()}",
                    {},
                    format="json",
                )

            responses = self._run_concurrently(worker_count, confirm)
            for response in responses:
                self.assertEqual(response.status_code, status.HTTP_200_OK, response.json())

            rows = list(
                PurchaseInvoiceHeader.objects.filter(id__in=[row["id"] for row in invoices])
                .order_by("doc_no")
                .values_list("doc_no", "purchase_number", "status")
            )
            doc_nos = [row[0] for row in rows]
            self.assertEqual(doc_nos, list(range(next_doc_no, next_doc_no + worker_count)))
            self.assertEqual(len(set(row[1] for row in rows)), worker_count)
            self.assertEqual({row[2] for row in rows}, {PurchaseInvoiceHeader.Status.CONFIRMED})
            next_doc_no += worker_count

    def test_purchase_invoice_concurrent_post_is_idempotent_for_same_invoice(self):
        created = self._create_invoice(
            supplier_invoice_number="PH2A-PUR-SAME-POST",
            lines=[self._service_line_payload(product_desc="PH2A post service")],
        )
        confirm_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{created['id']}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        def post(_index: int):
            client = self._client_for_worker()
            return client.post(
                f"/api/purchase/purchase-invoices/{created['id']}/post/{self._scope_qs()}",
                {},
                format="json",
            )

        responses = self._run_concurrently(2, post)
        for response in responses:
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.json())

        header = PurchaseInvoiceHeader.objects.get(pk=created["id"])
        self.assertEqual(header.status, PurchaseInvoiceHeader.Status.POSTED)
        self._assert_balanced_entries_for(voucher_no=header.purchase_number)
        self.assertEqual(
            PurchaseInvoiceHeader.objects.filter(
                entity=self.entity,
                entityfinid=self.entityfin,
                subentity=self.subentity,
                doc_code=header.doc_code,
                doc_no=header.doc_no,
            ).count(),
            1,
        )

    def test_ap_settlement_concurrent_allocations_same_invoice_at_2_5_10_workers(self):
        for worker_count in self.worker_counts:
            amount = Decimal("1200.00")
            per_worker = (amount / Decimal(worker_count)).quantize(Decimal("0.01"))
            open_item = self._create_manual_open_item(
                supplier_invoice_number=f"PH2A2-AP-SAME-{worker_count}",
                amount=str(amount),
            )
            settlement_ids = []
            for index in range(worker_count):
                create_resp = self.client.post(
                    "/api/purchase/ap/settlements/",
                    {
                        "entity": self.entity.id,
                        "entityfinid": self.entityfin.id,
                        "subentity": self.subentity.id,
                        "vendor": self.vendor.id,
                        "settlement_type": "payment",
                        "settlement_date": "2026-04-12",
                        "reference_no": f"PH2A2-AP-SAME-{worker_count}-{index}",
                        "lines": [{"open_item_id": open_item.id, "amount": str(per_worker)}],
                    },
                    format="json",
                )
                self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED, create_resp.json())
                settlement_ids.append(int(create_resp.json()["data"]["id"]))

            def post_settlement(index: int):
                client = self._client_for_worker()
                return client.post(f"/api/purchase/ap/settlements/{settlement_ids[index]}/post/", {}, format="json")

            responses = self._run_concurrently(worker_count, post_settlement)
            for response in responses:
                self.assertEqual(response.status_code, status.HTTP_200_OK, response.json())

            open_item.refresh_from_db()
            self.assertEqual(open_item.settled_amount, amount)
            self.assertEqual(open_item.outstanding_amount, Decimal("0.00"))
            self.assertFalse(open_item.is_open)
            self.assertEqual(
                VendorSettlement.objects.filter(pk__in=settlement_ids, status=VendorSettlement.Status.POSTED).count(),
                worker_count,
            )

    def test_ap_settlement_concurrent_payments_different_invoices_same_vendor_at_2_5_10_workers(self):
        for worker_count in self.worker_counts:
            open_items = [
                self._create_manual_open_item(
                    supplier_invoice_number=f"PH2A2-AP-DIFF-{worker_count}-{index}",
                    amount="100.00",
                    lines=[self._service_line_payload(product_desc=f"AP diff {worker_count}-{index}")],
                )
                for index in range(worker_count)
            ]
            settlement_ids = []
            for index, open_item in enumerate(open_items):
                create_resp = self.client.post(
                    "/api/purchase/ap/settlements/",
                    {
                        "entity": self.entity.id,
                        "entityfinid": self.entityfin.id,
                        "subentity": self.subentity.id,
                        "vendor": self.vendor.id,
                        "settlement_type": "payment",
                        "settlement_date": "2026-04-13",
                        "reference_no": f"PH2A2-AP-DIFF-{worker_count}-{index}",
                        "lines": [{"open_item_id": open_item.id, "amount": "100.00"}],
                    },
                    format="json",
                )
                self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED, create_resp.json())
                settlement_ids.append(int(create_resp.json()["data"]["id"]))

            def post_settlement(index: int):
                client = self._client_for_worker()
                return client.post(f"/api/purchase/ap/settlements/{settlement_ids[index]}/post/", {}, format="json")

            responses = self._run_concurrently(worker_count, post_settlement)
            for response in responses:
                self.assertEqual(response.status_code, status.HTTP_200_OK, response.json())

            for open_item in open_items:
                open_item.refresh_from_db()
                self.assertEqual(open_item.settled_amount, Decimal("100.00"))
                self.assertEqual(open_item.outstanding_amount, Decimal("0.00"))
                self.assertFalse(open_item.is_open)

    def test_payment_voucher_concurrent_confirm_allocates_unique_numbers_at_2_5_10_workers(self):
        next_doc_no = 1001
        for worker_count in self.worker_counts:
            voucher_ids = []
            for index in range(worker_count):
                open_item = self._create_manual_open_item(
                    supplier_invoice_number=f"PH2A2-PV-NUM-{worker_count}-{index}",
                    amount="100.00",
                    lines=[self._service_line_payload(product_desc=f"PV num {worker_count}-{index}")],
                )
                voucher_ids.append(
                    self._create_payment_voucher(
                        open_item=open_item,
                        amount="100.00",
                        reference=f"PH2A2-PV-NUM-{worker_count}-{index}",
                    )
                )

            def confirm(index: int):
                client = self._client_for_worker()
                return client.post(
                    f"/api/payments/payment-vouchers/{voucher_ids[index]}/confirm/{self._scope_qs()}",
                    {},
                    format="json",
                )

            responses = self._run_concurrently(worker_count, confirm)
            for response in responses:
                self.assertEqual(response.status_code, status.HTTP_200_OK, response.json())

            rows = list(
                PaymentVoucherHeader.objects.filter(pk__in=voucher_ids)
                .order_by("doc_no")
                .values_list("doc_no", "voucher_code", "status")
            )
            doc_nos = [row[0] for row in rows]
            self.assertEqual(doc_nos, list(range(next_doc_no, next_doc_no + worker_count)))
            self.assertEqual(len(set(row[1] for row in rows)), worker_count)
            self.assertEqual({row[2] for row in rows}, {PaymentVoucherHeader.Status.CONFIRMED})
            next_doc_no += worker_count

    def test_payment_voucher_concurrent_confirm_and_post_closes_different_invoices_at_2_5_10_workers(self):
        next_doc_no = 1001
        for worker_count in self.worker_counts:
            open_items = []
            voucher_ids = []
            for index in range(worker_count):
                open_item = self._create_manual_open_item(
                    supplier_invoice_number=f"PH2A2-PV-POST-{worker_count}-{index}",
                    amount="100.00",
                    lines=[self._service_line_payload(product_desc=f"PV post {worker_count}-{index}")],
                )
                open_items.append(open_item)
                voucher_ids.append(
                    self._create_payment_voucher(
                        open_item=open_item,
                        amount="100.00",
                        reference=f"PH2A2-PV-POST-{worker_count}-{index}",
                    )
                )

            def confirm_and_post(index: int):
                client = self._client_for_worker()
                confirm_response = client.post(
                    f"/api/payments/payment-vouchers/{voucher_ids[index]}/confirm/{self._scope_qs()}",
                    {},
                    format="json",
                )
                if confirm_response.status_code != status.HTTP_200_OK:
                    return confirm_response
                return client.post(
                    f"/api/payments/payment-vouchers/{voucher_ids[index]}/post/{self._scope_qs()}",
                    {},
                    format="json",
                )

            responses = self._run_concurrently(worker_count, confirm_and_post)
            for response in responses:
                self.assertEqual(response.status_code, status.HTTP_200_OK, response.json())

            vouchers = list(
                PaymentVoucherHeader.objects.filter(pk__in=voucher_ids)
                .order_by("doc_no")
                .values_list("doc_no", "voucher_code", "status", "ap_settlement_id")
            )
            doc_nos = [row[0] for row in vouchers]
            self.assertEqual(doc_nos, list(range(next_doc_no, next_doc_no + worker_count)))
            self.assertEqual(len(set(row[1] for row in vouchers)), worker_count)
            self.assertEqual({row[2] for row in vouchers}, {PaymentVoucherHeader.Status.POSTED})
            self.assertTrue(all(row[3] for row in vouchers))
            next_doc_no += worker_count

            for open_item in open_items:
                open_item.refresh_from_db()
                self.assertEqual(open_item.settled_amount, Decimal("100.00"))
                self.assertEqual(open_item.outstanding_amount, Decimal("0.00"))
                self.assertFalse(open_item.is_open)

    def test_journal_voucher_concurrent_confirm_and_post_at_2_5_10_workers(self):
        next_doc_no = 1
        tenant = self._primary_tenant()
        for worker_count in self.worker_counts:
            voucher_ids = [
                self._create_journal_voucher_for_tenant(
                    client=self.client,
                    tenant=tenant,
                    reference=f"PH2B1-JV-{worker_count}-{index}",
                    amount="100.00",
                )
                for index in range(worker_count)
            ]

            def confirm_and_post(index: int):
                client = self._client_for_worker()
                confirm_response = client.post(
                    f"/api/vouchers/vouchers/{voucher_ids[index]}/confirm/{self._tenant_scope_qs(tenant)}",
                    {},
                    format="json",
                )
                if confirm_response.status_code != status.HTTP_200_OK:
                    return confirm_response
                return client.post(
                    f"/api/vouchers/vouchers/{voucher_ids[index]}/post/{self._tenant_scope_qs(tenant)}",
                    {},
                    format="json",
                )

            responses = self._run_concurrently(worker_count, confirm_and_post)
            for response in responses:
                self.assertEqual(response.status_code, status.HTTP_200_OK, response.json())

            rows = list(
                VoucherHeader.objects.filter(pk__in=voucher_ids)
                .order_by("doc_no")
                .values_list("doc_no", "voucher_code", "status", "total_debit_amount", "total_credit_amount")
            )
            doc_nos = [row[0] for row in rows]
            self.assertEqual(doc_nos, list(range(next_doc_no, next_doc_no + worker_count)))
            self.assertEqual(len(set(row[1] for row in rows)), worker_count)
            self.assertEqual({row[2] for row in rows}, {VoucherHeader.Status.POSTED})
            for _doc_no, voucher_code, _status_value, debit, credit in rows:
                self.assertEqual(debit, Decimal("100.00"))
                self.assertEqual(credit, Decimal("100.00"))
                self._assert_balanced_entries_for(voucher_no=voucher_code)
            next_doc_no += worker_count

    def test_cross_tenant_sales_purchase_payment_writes_are_isolated_at_2_5_10_workers(self):
        tenant_a = self._primary_tenant()
        tenant_b = self._create_independent_tenant(
            prefix="TENANTB",
            home_state_code="33",
            other_state_code="36",
            gstin="33BBBBB1234B1Z5",
        )
        tenants = [tenant_a, tenant_b]
        results: list[dict] = []

        for worker_count in self.worker_counts:
            def write_financial_flow(index: int):
                tenant = tenants[index % 2]
                tenant_label = "A" if tenant["entity"].id == tenant_a["entity"].id else "B"
                client = self._client_for_worker()

                sales_id = self._create_sales_invoice_for_tenant(
                    client=client,
                    tenant=tenant,
                    reference=f"PH2A3-SALES-{worker_count}-{index}-{tenant_label}",
                )
                sales_confirm = client.post(
                    f"/api/sales/service-invoices/{sales_id}/confirm/{self._sales_scope_qs_for(tenant)}",
                    {},
                    format="json",
                )
                self.assertEqual(sales_confirm.status_code, status.HTTP_200_OK, sales_confirm.json())

                purchase_id = self._create_purchase_invoice_for_tenant(
                    client=client,
                    tenant=tenant,
                    supplier_invoice_number=f"PH2A3-PUR-{worker_count}-{index}-{tenant_label}",
                )
                purchase_confirm = client.post(
                    f"/api/purchase/purchase-invoices/{purchase_id}/confirm/{self._tenant_scope_qs(tenant)}",
                    {},
                    format="json",
                )
                self.assertEqual(purchase_confirm.status_code, status.HTTP_200_OK, purchase_confirm.json())

                open_item = self._create_open_item_for_tenant(
                    tenant=tenant,
                    header_id=purchase_id,
                    amount="100.00",
                )
                voucher_id = self._create_payment_voucher_for_tenant(
                    client=client,
                    tenant=tenant,
                    open_item=open_item,
                    amount="100.00",
                    reference=f"PH2A3-PAY-{worker_count}-{index}-{tenant_label}",
                )
                payment_confirm = client.post(
                    f"/api/payments/payment-vouchers/{voucher_id}/confirm/{self._tenant_scope_qs(tenant)}",
                    {},
                    format="json",
                )
                self.assertEqual(payment_confirm.status_code, status.HTTP_200_OK, payment_confirm.json())
                payment_post = client.post(
                    f"/api/payments/payment-vouchers/{voucher_id}/post/{self._tenant_scope_qs(tenant)}",
                    {},
                    format="json",
                )
                self.assertEqual(payment_post.status_code, status.HTTP_200_OK, payment_post.json())

                return {
                    "tenant": tenant_label,
                    "entity_id": tenant["entity"].id,
                    "sales_id": sales_id,
                    "purchase_id": purchase_id,
                    "open_item_id": open_item.id,
                    "voucher_id": voucher_id,
                }

            batch_results = self._run_concurrently(worker_count, write_financial_flow)
            results.extend(batch_results)

        for tenant, label in ((tenant_a, "A"), (tenant_b, "B")):
            tenant_results = [row for row in results if row["tenant"] == label]
            sales_ids = [row["sales_id"] for row in tenant_results]
            purchase_ids = [row["purchase_id"] for row in tenant_results]
            voucher_ids = [row["voucher_id"] for row in tenant_results]
            open_item_ids = [row["open_item_id"] for row in tenant_results]

            self.assertTrue(sales_ids)
            self.assertEqual(
                SalesInvoiceHeader.objects.filter(pk__in=sales_ids, entity=tenant["entity"], entityfinid=tenant["entityfin"]).count(),
                len(sales_ids),
            )
            self.assertEqual(
                PurchaseInvoiceHeader.objects.filter(pk__in=purchase_ids, entity=tenant["entity"], entityfinid=tenant["entityfin"]).count(),
                len(purchase_ids),
            )
            self.assertEqual(
                PaymentVoucherHeader.objects.filter(pk__in=voucher_ids, entity=tenant["entity"], entityfinid=tenant["entityfin"]).count(),
                len(voucher_ids),
            )
            self.assertFalse(SalesInvoiceHeader.objects.filter(pk__in=sales_ids).exclude(entity=tenant["entity"]).exists())
            self.assertFalse(PurchaseInvoiceHeader.objects.filter(pk__in=purchase_ids).exclude(entity=tenant["entity"]).exists())
            self.assertFalse(PaymentVoucherHeader.objects.filter(pk__in=voucher_ids).exclude(entity=tenant["entity"]).exists())
            self.assertFalse(Entry.objects.filter(txn_id__in=sales_ids, txn_type__in=["S"]).exclude(entity=tenant["entity"]).exists())
            self.assertFalse(Entry.objects.filter(txn_id__in=purchase_ids, txn_type__in=["P"]).exclude(entity=tenant["entity"]).exists())

            sales_doc_nos = list(
                SalesInvoiceHeader.objects.filter(pk__in=sales_ids).order_by("doc_no").values_list("doc_no", flat=True)
            )
            purchase_doc_nos = list(
                PurchaseInvoiceHeader.objects.filter(pk__in=purchase_ids).order_by("doc_no").values_list("doc_no", flat=True)
            )
            payment_doc_nos = list(
                PaymentVoucherHeader.objects.filter(pk__in=voucher_ids).order_by("doc_no").values_list("doc_no", flat=True)
            )
            expected = list(range(1001, 1001 + len(tenant_results)))
            self.assertEqual(sales_doc_nos, expected)
            self.assertEqual(purchase_doc_nos, expected)
            self.assertEqual(payment_doc_nos, expected)

            for open_item in VendorBillOpenItem.objects.filter(pk__in=open_item_ids):
                self.assertEqual(open_item.entity_id, tenant["entity"].id)
                self.assertEqual(open_item.settled_amount, Decimal("100.00"))
                self.assertEqual(open_item.outstanding_amount, Decimal("0.00"))
                self.assertFalse(open_item.is_open)

        tenant_b_voucher_id = next(row["voucher_id"] for row in results if row["tenant"] == "B")
        before_status = PaymentVoucherHeader.objects.get(pk=tenant_b_voucher_id).status
        misuse = self.client.post(
            f"/api/payments/payment-vouchers/{tenant_b_voucher_id}/confirm/{self._tenant_scope_qs(tenant_a)}",
            {},
            format="json",
        )
        self.assertIn(misuse.status_code, {status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND})
        self.assertEqual(PaymentVoucherHeader.objects.get(pk=tenant_b_voucher_id).status, before_status)
