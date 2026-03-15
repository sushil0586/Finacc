from __future__ import annotations

from decimal import Decimal

from django.db.models import (
    BooleanField,
    Case,
    CharField,
    Count,
    DecimalField,
    F,
    OuterRef,
    Q,
    Subquery,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce
from rest_framework.exceptions import ValidationError

from financial.models import account
from geography.models import State
from reports.filters.sales_register_filter import SalesRegisterFilter
from sales.models import SalesEInvoice, SalesEWayBill, SalesInvoiceHeader, SalesInvoiceLine

ZERO = Decimal("0.00")


class SalesRegisterService:
    """
    Sales Register service.

    The register is header-wise and uses `SalesInvoiceHeader` as the source of
    truth because the sales header already stores statutory totals and customer
    snapshot data. That keeps the report safe from duplicate rows caused by
    line or tax-summary joins.
    """

    default_statuses = (
        SalesInvoiceHeader.Status.CONFIRMED,
        SalesInvoiceHeader.Status.POSTED,
    )

    def get_base_queryset(self):
        """Return the document-level queryset with only single-row joins."""
        return SalesInvoiceHeader.objects.select_related(
            "customer",
            "customer_ledger",
            "original_invoice",
            "einvoice_artifact",
            "eway_artifact",
            "entity",
            "entityfinid",
            "subentity",
        )

    def apply_filters(self, queryset, params):
        """Apply filterset validation and additional entity/customer checks."""
        filterset = SalesRegisterFilter(data=params, queryset=queryset)
        if not filterset.is_valid():
            raise ValidationError(filterset.errors)

        cleaned = filterset.form.cleaned_data
        self._validate_date_ranges(cleaned)

        entity_id = cleaned.get("entity")
        customer_id = cleaned.get("customer")
        if entity_id and customer_id:
            self._validate_customer_scope(entity_id=entity_id, customer_id=customer_id)

        queryset = filterset.qs
        queryset = self.apply_default_status_rules(queryset, raw_params=params)
        return queryset, cleaned

    def apply_default_status_rules(self, queryset, *, raw_params):
        """
        Default to business-valid sales documents only.

        Draft and cancelled invoices are excluded unless `status` is explicitly
        requested. Cancelled rows can still be listed, but later annotations
        force their monetary effect to zero so they never distort totals.
        """
        if raw_params.get("status") not in (None, ""):
            return queryset
        return queryset.filter(status__in=self.default_statuses)

    def annotate_register_fields(self, queryset):
        """
        Add signed reporting columns without joining lines into the rowset.

        Credit-note or return-style documents reduce totals, debit notes
        increase them, and cancelled documents are zeroed.
        """
        place_of_supply_name = (
            State.objects.filter(statecode=OuterRef("place_of_supply_state_code"))
            .values("statename")[:1]
        )
        line_discount_total = (
            SalesInvoiceLine.objects.filter(header_id=OuterRef("pk"))
            .values("header_id")
            .annotate(total=Coalesce(Sum("discount_amount"), ZERO))
            .values("total")[:1]
        )
        einvoice_irn = SalesEInvoice.objects.filter(invoice_id=OuterRef("pk")).values("irn")[:1]
        einvoice_ack_date = SalesEInvoice.objects.filter(invoice_id=OuterRef("pk")).values("ack_date")[:1]
        eway_no = SalesEWayBill.objects.filter(invoice_id=OuterRef("pk")).values("ewb_no")[:1]
        eway_date = SalesEWayBill.objects.filter(invoice_id=OuterRef("pk")).values("ewb_date")[:1]

        sign_multiplier = Case(
            When(status=SalesInvoiceHeader.Status.CANCELLED, then=Value(Decimal("0"))),
            When(doc_type__in=self._negative_doc_type_values(), then=Value(Decimal("-1"))),
            default=Value(Decimal("1")),
            output_field=DecimalField(max_digits=4, decimal_places=0),
        )
        affects_totals = Case(
            When(status=SalesInvoiceHeader.Status.CANCELLED, then=Value(False)),
            default=Value(True),
            output_field=BooleanField(),
        )

        return queryset.annotate(
            invoice_date=F("bill_date"),
            invoice_type=F("doc_type"),
            invoice_type_name=Case(
                *[
                    When(doc_type=choice.value, then=Value(str(choice.label)))
                    for choice in SalesInvoiceHeader.DocType
                ],
                default=Value(""),
                output_field=CharField(),
            ),
            doc_type_name=Case(
                *[
                    When(doc_type=choice.value, then=Value(str(choice.label)))
                    for choice in SalesInvoiceHeader.DocType
                ],
                default=Value(""),
                output_field=CharField(),
            ),
            sales_invoice_number=Coalesce(F("invoice_number"), Value(""), output_field=CharField()),
            place_of_supply=Coalesce(
                Subquery(place_of_supply_name, output_field=CharField()),
                F("place_of_supply_state_code"),
                Value(""),
                output_field=CharField(),
            ),
            supply_classification=F("supply_category"),
            supply_classification_name=Case(
                *[
                    When(supply_category=choice.value, then=Value(self._supply_classification_label(choice)))
                    for choice in SalesInvoiceHeader.SupplyCategory
                ],
                default=Value(""),
                output_field=CharField(),
            ),
            status_name=Case(
                *[
                    When(status=choice.value, then=Value(str(choice.label)))
                    for choice in SalesInvoiceHeader.Status
                ],
                default=Value(""),
                output_field=CharField(),
            ),
            discount_total=Case(
                When(total_discount__gt=ZERO, then=F("total_discount")),
                default=Coalesce(
                    Subquery(line_discount_total, output_field=DecimalField(max_digits=18, decimal_places=2)),
                    ZERO,
                ),
                output_field=DecimalField(max_digits=18, decimal_places=2),
            ),
            linked_credit_debit_note_reference=Coalesce(
                F("original_invoice__invoice_number"),
                F("original_invoice__doc_code"),
                Value(""),
                output_field=CharField(),
            ),
            e_invoice_no=Coalesce(Subquery(einvoice_irn, output_field=CharField()), Value(""), output_field=CharField()),
            e_invoice_date=Subquery(einvoice_ack_date),
            e_way_bill_no=Coalesce(Subquery(eway_no, output_field=CharField()), Value(""), output_field=CharField()),
            e_way_bill_date=Subquery(eway_date),
            affects_totals=affects_totals,
            taxable_amount=F("total_taxable_value") * sign_multiplier,
            cgst_amount=F("total_cgst") * sign_multiplier,
            sgst_amount=F("total_sgst") * sign_multiplier,
            igst_amount=F("total_igst") * sign_multiplier,
            cess_amount=F("total_cess") * sign_multiplier,
            discount_total_signed=F("discount_total") * sign_multiplier,
            roundoff_amount=F("round_off") * sign_multiplier,
            signed_grand_total=F("grand_total") * sign_multiplier,
        )

    def calculate_totals(self, queryset):
        """Aggregate totals from the full filtered dataset, not the paginated page."""
        raw_totals = queryset.aggregate(
            document_count=Count("id"),
            taxable_amount_total=Coalesce(Sum("taxable_amount"), ZERO),
            cgst_amount_total=Coalesce(Sum("cgst_amount"), ZERO),
            sgst_amount_total=Coalesce(Sum("sgst_amount"), ZERO),
            igst_amount_total=Coalesce(Sum("igst_amount"), ZERO),
            cess_amount_total=Coalesce(Sum("cess_amount"), ZERO),
            discount_total_total=Coalesce(Sum("discount_total_signed"), ZERO),
            roundoff_amount_total=Coalesce(Sum("roundoff_amount"), ZERO),
            grand_total_total=Coalesce(Sum("signed_grand_total"), ZERO),
        )
        return {
            "document_count": raw_totals["document_count"],
            "taxable_amount": raw_totals["taxable_amount_total"],
            "cgst_amount": raw_totals["cgst_amount_total"],
            "sgst_amount": raw_totals["sgst_amount_total"],
            "igst_amount": raw_totals["igst_amount_total"],
            "cess_amount": raw_totals["cess_amount_total"],
            "discount_total": raw_totals["discount_total_total"],
            "roundoff_amount": raw_totals["roundoff_amount_total"],
            "grand_total": raw_totals["grand_total_total"],
        }

    def get_grouped_summary(self, queryset, *, group_field="supply_classification", label_field="supply_classification_name"):
        """Optional grouped summary helper for future exports/dashboards."""
        return list(
            queryset.values(group_field, label_field)
            .annotate(
                document_count=Count("id"),
                taxable_amount=Coalesce(Sum("taxable_amount"), ZERO),
                grand_total=Coalesce(Sum("signed_grand_total"), ZERO),
            )
            .order_by(group_field)
        )

    def build_drilldown(self, row):
        """Return stable frontend identifiers for opening the sales document detail."""
        return {
            "target": "sales_invoice_detail",
            "id": row.id,
            "doc_type": row.doc_type,
            "invoice_number": row.invoice_number,
        }

    @staticmethod
    def _negative_doc_type_values():
        return [
            choice.value
            for choice in SalesInvoiceHeader.DocType
            if "CREDIT" in choice.name.upper()
            or "RETURN" in choice.name.upper()
            or "CREDIT" in str(choice.label).upper()
            or "RETURN" in str(choice.label).upper()
        ]

    @staticmethod
    def _supply_classification_label(choice):
        name = choice.name.upper()
        if "B2B" in name:
            return "B2B"
        if "B2C" in name:
            return "B2C"
        if "SEZ" in name:
            return "SEZ"
        if "DEEMED_EXPORT" in name:
            return "DEEMED_EXPORT"
        if "EXPORT" in name:
            return "EXPORT"
        return str(choice.label)

    @staticmethod
    def _validate_customer_scope(*, entity_id: int, customer_id: int):
        if not account.objects.filter(entity_id=entity_id, id=customer_id).exists():
            raise ValidationError({"customer": ["Customer is not available in the selected entity scope."]})

    @staticmethod
    def _validate_date_ranges(cleaned_data):
        from_date = cleaned_data.get("from_date")
        to_date = cleaned_data.get("to_date")
        posting_from_date = cleaned_data.get("posting_from_date")
        posting_to_date = cleaned_data.get("posting_to_date")
        if from_date and to_date and from_date > to_date:
            raise ValidationError({"from_date": ["from_date cannot be after to_date."]})
        if posting_from_date and posting_to_date and posting_from_date > posting_to_date:
            raise ValidationError({"posting_from_date": ["posting_from_date cannot be after posting_to_date."]})
