from rest_framework import generics, permissions, filters
from django_filters.rest_framework import DjangoFilterBackend
from purchase.services.purchase_invoice_nav_service import PurchaseInvoiceNavService


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
            .prefetch_related("lines", "tax_summaries")
        )
