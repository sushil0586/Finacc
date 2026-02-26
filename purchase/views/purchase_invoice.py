from rest_framework import generics, permissions, filters
from django_filters.rest_framework import DjangoFilterBackend
from purchase.services.purchase_invoice_nav_service import PurchaseInvoiceNavService
from django.db.models import Prefetch
from purchase.models.purchase_core import PurchaseInvoiceLine
from purchase.serializers.purchase_invoice import PurchaseInvoiceSearchSerializer
from purchase.filters import PurchaseInvoiceSearchFilter
from rest_framework.filters import OrderingFilter, SearchFilter



from purchase.models.purchase_core import PurchaseInvoiceHeader
from purchase.serializers.purchase_invoice import PurchaseInvoiceHeaderSerializer


class PurchaseInvoiceListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = PurchaseInvoiceHeaderSerializer
    permission_classes = [permissions.IsAuthenticated]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = [
        "entity", "entityfinid", "subentity",
        "doc_type", "status",
        "supply_category", "default_taxability",
        "tax_regime", "is_reverse_charge",
        "vendor",
    ]
    search_fields = ["purchase_number", "supplier_invoice_number", "vendor_name", "vendor_gstin"]
    ordering_fields = ["bill_date", "doc_no", "id"]
    ordering = ["-bill_date", "-id"]

    def get_queryset(self):
        return (
            PurchaseInvoiceHeader.objects.all()
            .select_related(
                "vendor", "vendor_state",
                "supplier_state", "place_of_supply_state",
                "entity", "entityfinid", "subentity",
                "ref_document",
            )
            .prefetch_related("lines", "tax_summaries")
        )

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class PurchaseInvoiceRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = PurchaseInvoiceHeaderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            PurchaseInvoiceHeader.objects.all()
            .select_related(
                "vendor", "vendor_state",
                "supplier_state", "place_of_supply_state",
                "entity", "entityfinid", "subentity",
                "ref_document",
            )
            .prefetch_related(
                Prefetch(
                    "lines",
                    queryset=PurchaseInvoiceLine.objects.select_related("product", "uom")
                ),
                "tax_summaries",
            )
        )
    

class PurchaseInvoiceSearchAPIView(generics.ListAPIView):
    """
    GET /api/purchase/purchase-invoices/search/

    Supports:
    - entity/entityfinid/subentity scoping
    - multiple filter scenarios via query params
    - q=<free text> + DRF search=<free text>
    - ordering
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PurchaseInvoiceSearchSerializer

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = PurchaseInvoiceSearchFilter

    # Optional DRF search (separate from q). Use either or both.
    search_fields = [
        "purchase_number",
        "supplier_invoice_number",
        "vendor_name",
        "vendor_gstin",
        "doc_code",
    ]

    # Safe ordering fields
    ordering_fields = [
        "id",
        "bill_date",
        "posting_date",
        "due_date",
        "doc_no",
        "grand_total",
        "created_at",
        "updated_at",
    ]
    ordering = ["-bill_date", "-id"]  # default order

    def get_queryset(self):
        qs = (
            PurchaseInvoiceHeader.objects
            .select_related(
                "entity",
                "entityfinid",
                "subentity",
                "vendor",
                "vendor_state",
               
            )
            .only(
                # keep DB payload smaller (tune as needed)
                "id", "entity_id", "entityfinid_id", "subentity_id",
                "doc_type", "status",
                "doc_code", "doc_no", "purchase_number",
                "bill_date", "posting_date", "credit_days", "due_date",
                "supplier_invoice_number", "supplier_invoice_date",
                "vendor_id", "vendor_name", "vendor_gstin", "vendor_state_id",
                "supply_category", "default_taxability", "tax_regime",
                "is_igst", "is_reverse_charge", "is_itc_eligible",
                "gstr2b_match_status", "itc_claim_status", "itc_claim_period", "itc_block_reason",
                "total_taxable", "total_gst", "round_off", "grand_total",
                "created_at", "updated_at",
            )
        )
        return qs
