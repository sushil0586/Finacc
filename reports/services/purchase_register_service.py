from __future__ import annotations

from decimal import Decimal

from django.db.models import (
    BooleanField,
    Case,
    CharField,
    Count,
    DecimalField,
    Exists,
    F,
    IntegerField,
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
from purchase.models.purchase_core import PurchaseInvoiceHeader, PurchaseInvoiceLine
from reports.filters.purchase_register_filter import PurchaseRegisterFilter

ZERO = Decimal("0.00")


class PurchaseRegisterService:
    """
    Purchase Register service.

    The register is intentionally header-wise and uses `PurchaseInvoiceHeader` as
    the source of truth because the header already persists statutory totals.
    This avoids duplicate rows and keeps reporting aligned with the posted
    commercial document rather than rebuilding totals from joined line items.
    """

    default_statuses = (
        PurchaseInvoiceHeader.Status.CONFIRMED,
        PurchaseInvoiceHeader.Status.POSTED,
    )

    def get_base_queryset(self):
        """Return the document-level base queryset with only safe `select_related` joins."""
        return PurchaseInvoiceHeader.objects.select_related(
            "vendor",
            "vendor_ledger",
            "place_of_supply_state",
            "entity",
            "entityfinid",
            "subentity",
        )

    def apply_filters(self, queryset, params):
        """Apply reusable django-filter rules and normalize validation errors."""
        filterset = PurchaseRegisterFilter(data=params, queryset=queryset)
        if not filterset.is_valid():
            raise ValidationError(filterset.errors)

        cleaned = filterset.form.cleaned_data
        self._validate_date_ranges(cleaned)
        entity_id = cleaned.get("entity")
        vendor_id = cleaned.get("vendor")
        if entity_id and vendor_id:
            self._validate_vendor_scope(entity_id=entity_id, vendor_id=vendor_id)

        queryset = filterset.qs
        queryset = self.apply_default_status_rules(queryset, cleaned_data=cleaned, raw_params=params)
        return queryset, cleaned

    def apply_default_status_rules(self, queryset, *, cleaned_data, raw_params):
        """
        Default to business-valid documents only.

        Draft and cancelled documents are excluded unless `status` is explicitly
        supplied. Cancelled documents can still be requested, but their monetary
        impact is zeroed later so they never affect totals.
        """
        if raw_params.get("status") not in (None, ""):
            return queryset
        return queryset.filter(status__in=self.default_statuses)

    def annotate_register_fields(self, queryset):
        """
        Add signed register columns without joining line tables into the rowset.

        Credit-note style documents are negative, debit-note style documents are
        positive, and cancelled documents are forced to zero so report totals
        remain mathematically consistent even if cancelled rows are included.
        """
        discount_totals = (
            PurchaseInvoiceLine.objects.filter(header_id=OuterRef("pk"))
            .values("header_id")
            .annotate(total=Coalesce(Sum("discount_amount"), ZERO))
            .values("total")[:1]
        )
        blocked_line_exists = PurchaseInvoiceLine.objects.filter(
            header_id=OuterRef("pk")
        ).filter(Q(is_itc_eligible=False) | (Q(itc_block_reason__isnull=False) & ~Q(itc_block_reason="")))

        sign_multiplier = Case(
            When(status=PurchaseInvoiceHeader.Status.CANCELLED, then=Value(Decimal("0"))),
            When(doc_type__in=self._negative_doc_type_values(), then=Value(Decimal("-1"))),
            default=Value(Decimal("1")),
            output_field=DecimalField(max_digits=4, decimal_places=0),
        )
        affects_totals = Case(
            When(status=PurchaseInvoiceHeader.Status.CANCELLED, then=Value(False)),
            default=Value(True),
            output_field=BooleanField(),
        )
        blocked_itc = Case(
            When(itc_claim_status=PurchaseInvoiceHeader.ItcClaimStatus.BLOCKED, then=Value(True)),
            When(Q(itc_block_reason__isnull=False) & ~Q(itc_block_reason=""), then=Value(True)),
            When(condition=Exists(blocked_line_exists), then=Value(True)),
            default=Value(False),
            output_field=BooleanField(),
        )

        return queryset.annotate(
            supplier_name=Coalesce(F("vendor_name"), F("vendor__accountname"), Value(""), output_field=CharField()),
            supplier_gstin=Coalesce(F("vendor_gstin"), F("vendor__gstno"), Value(""), output_field=CharField()),
            place_of_supply=Coalesce(F("place_of_supply_state__statename"), Value(""), output_field=CharField()),
            supply_type=F("supply_category"),
            supply_type_name=Case(
                *[
                    When(supply_category=choice.value, then=Value(str(choice.label)))
                    for choice in PurchaseInvoiceHeader.SupplyCategory
                ],
                default=Value(""),
                output_field=CharField(),
            ),
            doc_type_name=Case(
                *[
                    When(doc_type=choice.value, then=Value(str(choice.label)))
                    for choice in PurchaseInvoiceHeader.DocType
                ],
                default=Value(""),
                output_field=CharField(),
            ),
            status_name=Case(
                *[
                    When(status=choice.value, then=Value(str(choice.label)))
                    for choice in PurchaseInvoiceHeader.Status
                ],
                default=Value(""),
                output_field=CharField(),
            ),
            itc_claim_status_name=Case(
                *[
                    When(itc_claim_status=choice.value, then=Value(str(choice.label)))
                    for choice in PurchaseInvoiceHeader.ItcClaimStatus
                ],
                default=Value(""),
                output_field=CharField(),
            ),
            gstr2b_match_status_name=Case(
                *[
                    When(gstr2b_match_status=choice.value, then=Value(str(choice.label)))
                    for choice in PurchaseInvoiceHeader.Gstr2bMatchStatus
                ],
                default=Value(""),
                output_field=CharField(),
            ),
            discount_total=Coalesce(
                Subquery(discount_totals, output_field=DecimalField(max_digits=14, decimal_places=2)),
                ZERO,
            ),
            affects_totals=affects_totals,
            blocked_itc=blocked_itc,
            taxable_amount=F("total_taxable") * sign_multiplier,
            cgst_amount=F("total_cgst") * sign_multiplier,
            sgst_amount=F("total_sgst") * sign_multiplier,
            igst_amount=F("total_igst") * sign_multiplier,
            cess_amount=F("total_cess") * sign_multiplier,
            roundoff_amount=F("round_off") * sign_multiplier,
            signed_grand_total=F("grand_total") * sign_multiplier,
            discount_total_signed=F("discount_total") * sign_multiplier,
            itc_eligibility=F("is_itc_eligible"),
            reverse_charge=F("is_reverse_charge"),
        )

    def calculate_totals(self, queryset):
        """Aggregate totals from the full filtered dataset, not the paginated slice."""
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

    def get_grouped_summary(self, queryset, *, group_field="doc_type", label_field=None):
        """Optional grouped helper that can later power supplier/doc-type summary blocks."""
        label_field = label_field or f"{group_field}_name"
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
        """Return stable frontend identifiers for opening the purchase document detail."""
        return {
            "target": "purchase_document_detail",
            "id": row.id,
            "doc_type": row.doc_type,
            "purchase_number": row.purchase_number,
        }

    @staticmethod
    def _negative_doc_type_values():
        return [
            choice.value
            for choice in PurchaseInvoiceHeader.DocType
            if "CREDIT" in choice.name.upper()
            or "RETURN" in choice.name.upper()
            or "CREDIT" in str(choice.label).upper()
            or "RETURN" in str(choice.label).upper()
        ]

    @staticmethod
    def _validate_vendor_scope(*, entity_id: int, vendor_id: int):
        if not account.objects.filter(entity_id=entity_id, id=vendor_id).exists():
            raise ValidationError({"vendor": ["Vendor is not available in the selected entity scope."]})

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
