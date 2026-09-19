from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from entity.models import Entity, EntityFinancialYear, SubEntity
from purchase.models import PurchaseInvoiceHeader, PurchaseInvoiceLine, PurchaseTaxSummary
from reports.gstr1.conf import export_pos_code
from sales.models import SalesInvoiceHeader, SalesInvoiceLine, SalesTaxSummary


SOURCE_SYSTEM = "gst_certification_matrix"


class Command(BaseCommand):
    help = (
        "Seed controlled GST certification documents for strict browser gates. "
        "Creates only explicit certification sales/purchase documents for the selected scope."
    )

    def add_arguments(self, parser):
        parser.add_argument("--entity-id", type=int, required=True)
        parser.add_argument("--entityfin-id", type=int, required=True)
        parser.add_argument("--subentity-id", type=int, default=None)
        parser.add_argument("--gstin", type=str, required=True)
        parser.add_argument("--return-period", type=str, required=True, help="YYYY-MM")
        parser.add_argument("--prefix", type=str, default="GSTCERT")
        parser.add_argument("--user-email", type=str, default=None)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--confirm-seed",
            action="store_true",
            help="Required to mutate data. Omit with --dry-run to preview the target scope.",
        )

    def handle(self, *args, **options):
        if not options["dry_run"] and not options["confirm_seed"]:
            raise CommandError("Refusing to mutate data without --confirm-seed. Use --dry-run to preview.")

        entity = self._get_entity(options["entity_id"])
        entityfin = self._get_entityfin(options["entityfin_id"], entity_id=entity.id)
        subentity = self._get_subentity(options.get("subentity_id"), entity_id=entity.id)
        period_start, period_end = self._period_window(options["return_period"])
        bill_date = period_start
        user = self._resolve_user(options.get("user_email"))
        gstin = (options["gstin"] or "").strip().upper()
        prefix = (options["prefix"] or "GSTCERT").strip().upper()

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run only. No documents were created."))
            self._write_scope(entity, entityfin, subentity, gstin, period_start, period_end)
            return

        with transaction.atomic():
            original = self._upsert_sales_document(
                code="domestic-original",
                doc_type=SalesInvoiceHeader.DocType.TAX_INVOICE,
                entity=entity,
                entityfin=entityfin,
                subentity=subentity,
                gstin=gstin,
                prefix=prefix,
                bill_date=bill_date,
                doc_no_base=970001,
                invoice_number=f"{prefix}-{options['return_period']}-SI",
                customer_name="GST Certification Registered Customer",
                customer_gstin="29ABCDE1234F2Z6",
                place_of_supply_state_code=self._state_code(gstin),
                supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
                tax_regime=SalesInvoiceHeader.TaxRegime.INTRA_STATE,
                is_igst=False,
                taxable=Decimal("1000.00"),
                cgst=Decimal("90.00"),
                sgst=Decimal("90.00"),
                igst=Decimal("0.00"),
                user=user,
            )
            self._upsert_sales_document(
                code="registered-credit-note",
                doc_type=SalesInvoiceHeader.DocType.CREDIT_NOTE,
                entity=entity,
                entityfin=entityfin,
                subentity=subentity,
                gstin=gstin,
                prefix=prefix,
                bill_date=bill_date,
                doc_no_base=970101,
                invoice_number=f"{prefix}-{options['return_period']}-SCN",
                customer_name="GST Certification Registered Customer",
                customer_gstin="29ABCDE1234F2Z6",
                place_of_supply_state_code=self._state_code(gstin),
                supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
                tax_regime=SalesInvoiceHeader.TaxRegime.INTRA_STATE,
                is_igst=False,
                taxable=Decimal("100.00"),
                cgst=Decimal("9.00"),
                sgst=Decimal("9.00"),
                igst=Decimal("0.00"),
                user=user,
                original_invoice=original,
            )
            self._upsert_sales_document(
                code="registered-debit-note",
                doc_type=SalesInvoiceHeader.DocType.DEBIT_NOTE,
                entity=entity,
                entityfin=entityfin,
                subentity=subentity,
                gstin=gstin,
                prefix=prefix,
                bill_date=bill_date,
                doc_no_base=970201,
                invoice_number=f"{prefix}-{options['return_period']}-SDN",
                customer_name="GST Certification Registered Customer",
                customer_gstin="29ABCDE1234F2Z6",
                place_of_supply_state_code=self._state_code(gstin),
                supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
                tax_regime=SalesInvoiceHeader.TaxRegime.INTRA_STATE,
                is_igst=False,
                taxable=Decimal("150.00"),
                cgst=Decimal("13.50"),
                sgst=Decimal("13.50"),
                igst=Decimal("0.00"),
                user=user,
                original_invoice=original,
            )
            self._upsert_sales_document(
                code="export-zero-rated",
                doc_type=SalesInvoiceHeader.DocType.TAX_INVOICE,
                entity=entity,
                entityfin=entityfin,
                subentity=subentity,
                gstin=gstin,
                prefix=prefix,
                bill_date=bill_date,
                doc_no_base=970301,
                invoice_number=f"{prefix}-{options['return_period']}-EXP",
                customer_name="GST Certification Export Customer",
                customer_gstin="",
                place_of_supply_state_code=export_pos_code(),
                supply_category=SalesInvoiceHeader.SupplyCategory.EXPORT_WITHOUT_IGST,
                tax_regime=SalesInvoiceHeader.TaxRegime.INTER_STATE,
                is_igst=True,
                taxable=Decimal("500.00"),
                cgst=Decimal("0.00"),
                sgst=Decimal("0.00"),
                igst=Decimal("0.00"),
                user=user,
            )
            self._upsert_purchase_rcm_document(
                entity=entity,
                entityfin=entityfin,
                subentity=subentity,
                gstin=gstin,
                prefix=prefix,
                bill_date=bill_date,
                return_period=options["return_period"],
                user=user,
            )

        self.stdout.write(self.style.SUCCESS("GST certification matrix seed completed."))
        self._write_scope(entity, entityfin, subentity, gstin, period_start, period_end)

    def _upsert_sales_document(
        self,
        *,
        code,
        doc_type,
        entity,
        entityfin,
        subentity,
        gstin,
        prefix,
        bill_date,
        doc_no_base,
        invoice_number,
        customer_name,
        customer_gstin,
        place_of_supply_state_code,
        supply_category,
        tax_regime,
        is_igst,
        taxable,
        cgst,
        sgst,
        igst,
        user,
        original_invoice=None,
    ):
        key = f"{prefix}:{entity.id}:{entityfin.id}:{subentity.id if subentity else 'root'}:{code}:{bill_date:%Y%m}"
        header = SalesInvoiceHeader.objects.filter(entity=entity, legacy_source_system=SOURCE_SYSTEM, legacy_source_key=key).first()
        if header is None:
            header = SalesInvoiceHeader(
                entity=entity,
                entityfinid=entityfin,
                subentity=subentity,
                doc_type=doc_type,
                doc_code="GSTCERT",
                doc_no=self._next_sales_doc_no(
                    entity=entity,
                    entityfin=entityfin,
                    subentity=subentity,
                    doc_type=doc_type,
                    base=doc_no_base,
                ),
                invoice_number=invoice_number,
                legacy_source_system=SOURCE_SYSTEM,
                legacy_source_key=key,
                created_by=user,
            )

        now = timezone.now()
        total_tax = cgst + sgst + igst
        header.status = SalesInvoiceHeader.Status.POSTED
        header.bill_date = bill_date
        header.posting_date = bill_date
        header.original_invoice = original_invoice
        header.note_reason = (
            SalesInvoiceHeader.NoteReason.QUANTITY_RETURN
            if doc_type == SalesInvoiceHeader.DocType.CREDIT_NOTE
            else None
        )
        header.customer_name = customer_name
        header.customer_gstin = customer_gstin
        header.customer_state_code = place_of_supply_state_code if customer_gstin else ""
        header.seller_gstin = gstin
        header.seller_state_code = self._state_code(gstin)
        header.place_of_supply_state_code = place_of_supply_state_code
        header.supply_category = supply_category
        header.taxability = SalesInvoiceHeader.Taxability.TAXABLE
        header.tax_regime = tax_regime
        header.is_igst = is_igst
        header.total_taxable_value = taxable
        header.total_cgst = cgst
        header.total_sgst = sgst
        header.total_igst = igst
        header.total_cess = Decimal("0.00")
        header.grand_total = taxable + total_tax
        header.outstanding_amount = header.grand_total
        header.confirmed_at = now
        header.posted_at = now
        header.confirmed_by = user
        header.posted_by = user
        header.updated_by = user
        header.save()

        SalesInvoiceLine.objects.update_or_create(
            header=header,
            line_no=1,
            defaults={
                "entity": entity,
                "entityfinid": entityfin,
                "subentity": subentity,
                "productDesc": f"GST certification {code}",
                "hsn_sac_code": "998399",
                "is_service": True,
                "qty": Decimal("1.000"),
                "rate": taxable,
                "taxability": SalesInvoiceHeader.Taxability.TAXABLE,
                "gst_rate": Decimal("18.00") if total_tax else Decimal("0.00"),
                "taxable_value": taxable,
                "cgst_amount": cgst,
                "sgst_amount": sgst,
                "igst_amount": igst,
                "cess_amount": Decimal("0.00"),
                "line_total": taxable + total_tax,
                "created_by": user,
                "updated_by": user,
            },
        )
        SalesTaxSummary.objects.update_or_create(
            header=header,
            taxability=SalesInvoiceHeader.Taxability.TAXABLE,
            hsn_sac_code="998399",
            is_service=True,
            gst_rate=Decimal("18.00") if total_tax else Decimal("0.00"),
            is_reverse_charge=False,
            defaults={
                "entity": entity,
                "entityfinid": entityfin,
                "subentity": subentity,
                "taxable_value": taxable,
                "cgst_amount": cgst,
                "sgst_amount": sgst,
                "igst_amount": igst,
                "cess_amount": Decimal("0.00"),
                "created_by": user,
                "updated_by": user,
            },
        )
        self.stdout.write(f"sales:{code}: {header.invoice_number}")
        return header

    def _upsert_purchase_rcm_document(self, *, entity, entityfin, subentity, gstin, prefix, bill_date, return_period, user):
        key = f"{prefix}:{entity.id}:{entityfin.id}:{subentity.id if subentity else 'root'}:purchase-rcm:{bill_date:%Y%m}"
        header = PurchaseInvoiceHeader.objects.filter(entity=entity, legacy_source_system=SOURCE_SYSTEM, legacy_source_key=key).first()
        if header is None:
            header = PurchaseInvoiceHeader(
                entity=entity,
                entityfinid=entityfin,
                subentity=subentity,
                doc_type=PurchaseInvoiceHeader.DocType.TAX_INVOICE,
                doc_code="GSTCERT",
                doc_no=self._next_purchase_doc_no(
                    entity=entity,
                    entityfin=entityfin,
                    subentity=subentity,
                    doc_type=PurchaseInvoiceHeader.DocType.TAX_INVOICE,
                    base=970401,
                ),
                purchase_number=f"{prefix}-{return_period}-PRCM",
                legacy_source_system=SOURCE_SYSTEM,
                legacy_source_key=key,
                created_by=user,
            )

        now = timezone.now()
        taxable = Decimal("1000.00")
        igst = Decimal("180.00")
        header.status = PurchaseInvoiceHeader.Status.POSTED
        header.bill_date = bill_date
        header.posting_date = bill_date
        header.supplier_invoice_number = f"{prefix}-{return_period}-VRCM"
        header.supplier_invoice_date = bill_date
        header.vendor_name = "GST Certification RCM Vendor"
        header.vendor_gstin = "27ABCDE1234F1Z7"
        header.supply_category = PurchaseInvoiceHeader.SupplyCategory.DOMESTIC
        header.default_taxability = PurchaseInvoiceHeader.Taxability.TAXABLE
        header.tax_regime = PurchaseInvoiceHeader.TaxRegime.INTER
        header.is_igst = True
        header.is_reverse_charge = True
        header.is_itc_eligible = True
        header.itc_claim_status = PurchaseInvoiceHeader.ItcClaimStatus.PENDING
        header.itc_claim_period = return_period
        header.total_taxable = taxable
        header.total_cgst = Decimal("0.00")
        header.total_sgst = Decimal("0.00")
        header.total_igst = igst
        header.total_cess = Decimal("0.00")
        header.total_gst = igst
        header.grand_total = taxable + igst
        header.grand_total_base_currency = header.grand_total
        header.confirmed_at = now
        header.posted_at = now
        header.confirmed_by = user
        header.posted_by = user
        header.save()

        PurchaseInvoiceLine.objects.update_or_create(
            header=header,
            line_no=1,
            defaults={
                "product_desc": "GST certification reverse charge service",
                "is_service": True,
                "purchase_behavior": "expense",
                "hsn_sac": "998399",
                "qty": Decimal("1.0000"),
                "rate": taxable,
                "taxability": PurchaseInvoiceHeader.Taxability.TAXABLE,
                "taxable_value": taxable,
                "gst_rate": Decimal("18.00"),
                "igst_percent": Decimal("18.00"),
                "igst_amount": igst,
                "line_total": taxable + igst,
                "is_itc_eligible": True,
            },
        )
        PurchaseTaxSummary.objects.update_or_create(
            header=header,
            taxability=PurchaseInvoiceHeader.Taxability.TAXABLE,
            hsn_sac="998399",
            is_service=True,
            gst_rate=Decimal("18.00"),
            is_reverse_charge=True,
            defaults={
                "taxable_value": taxable,
                "cgst_amount": Decimal("0.00"),
                "sgst_amount": Decimal("0.00"),
                "igst_amount": igst,
                "cess_amount": Decimal("0.00"),
                "total_value": taxable + igst,
                "itc_eligible_tax": igst,
                "itc_ineligible_tax": Decimal("0.00"),
            },
        )
        self.stdout.write(f"purchase:reverse-charge: {header.purchase_number}")
        return header

    def _next_sales_doc_no(self, *, entity, entityfin, subentity, doc_type, base):
        doc_no = base
        while SalesInvoiceHeader.objects.filter(
            entity=entity,
            entityfinid=entityfin,
            subentity=subentity,
            doc_type=doc_type,
            doc_code="GSTCERT",
            doc_no=doc_no,
        ).exists():
            doc_no += 1
        return doc_no

    def _next_purchase_doc_no(self, *, entity, entityfin, subentity, doc_type, base):
        doc_no = base
        while PurchaseInvoiceHeader.objects.filter(
            entity=entity,
            entityfinid=entityfin,
            subentity=subentity,
            doc_type=doc_type,
            doc_code="GSTCERT",
            doc_no=doc_no,
        ).exists():
            doc_no += 1
        return doc_no

    def _get_entity(self, entity_id):
        try:
            return Entity.objects.get(id=entity_id)
        except Entity.DoesNotExist as exc:
            raise CommandError(f"Entity {entity_id} does not exist.") from exc

    def _get_entityfin(self, entityfin_id, *, entity_id):
        try:
            return EntityFinancialYear.objects.get(id=entityfin_id, entity_id=entity_id)
        except EntityFinancialYear.DoesNotExist as exc:
            raise CommandError(f"Financial year {entityfin_id} is not valid for entity {entity_id}.") from exc

    def _get_subentity(self, subentity_id, *, entity_id):
        if not subentity_id:
            return None
        try:
            return SubEntity.objects.get(id=subentity_id, entity_id=entity_id)
        except SubEntity.DoesNotExist as exc:
            raise CommandError(f"Subentity {subentity_id} is not valid for entity {entity_id}.") from exc

    def _resolve_user(self, email):
        User = get_user_model()
        if email:
            user = User.objects.filter(email__iexact=email).first()
            if not user:
                raise CommandError(f"User with email {email} does not exist.")
            return user
        return User.objects.filter(is_active=True).order_by("-is_superuser", "id").first()

    def _period_window(self, period):
        try:
            year_raw, month_raw = str(period).split("-", 1)
            year = int(year_raw)
            month = int(month_raw)
            return date(year, month, 1), date(year, month, monthrange(year, month)[1])
        except (TypeError, ValueError) as exc:
            raise CommandError("--return-period must be in YYYY-MM format.") from exc

    def _state_code(self, gstin):
        return gstin[:2] if len(gstin) >= 2 and gstin[:2].isdigit() else "29"

    def _write_scope(self, entity, entityfin, subentity, gstin, period_start, period_end):
        self.stdout.write(f"Entity: {entity.id} | FY: {entityfin.id} | Subentity: {subentity.id if subentity else '-'}")
        self.stdout.write(f"GSTIN: {gstin} | Period: {period_start} -> {period_end}")
