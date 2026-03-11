from rest_framework import generics, permissions, filters
from django_filters.rest_framework import DjangoFilterBackend
from purchase.services.purchase_invoice_nav_service import PurchaseInvoiceNavService
from django.db.models import Prefetch
from rest_framework.exceptions import ValidationError
from purchase.models.purchase_core import PurchaseInvoiceLine
from purchase.serializers.purchase_invoice import PurchaseInvoiceSearchSerializer
from purchase.filters import PurchaseInvoiceSearchFilter
from rest_framework.filters import OrderingFilter, SearchFilter



from purchase.models.purchase_core import PurchaseInvoiceHeader
from purchase.serializers.purchase_invoice import (
    PurchaseInvoiceHeaderSerializer,
    PurchaseInvoiceListSerializer,
)
from purchase.services.purchase_settings_service import PurchaseSettingsService


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

    def _scope_ids(self, *, required: bool):
        if self.request.method.upper() == "POST":
            return None, None, None

        entity = self.request.query_params.get("entity")
        entityfinid = self.request.query_params.get("entityfinid")
        subentity = self.request.query_params.get("subentity")

        if required and (not entity or not entityfinid):
            raise ValidationError({"detail": "entity and entityfinid query params are required."})
        if not entity or not entityfinid:
            return None, None, None

        try:
            entity_id = int(entity)
            entityfinid_id = int(entityfinid)
            subentity_id = int(subentity) if subentity not in (None, "", "null") else None
        except (TypeError, ValueError):
            raise ValidationError({"detail": "entity/entityfinid/subentity must be integers."})
        return entity_id, entityfinid_id, subentity_id

    def get_serializer_class(self):
        if self.request.method.upper() == "GET":
            return PurchaseInvoiceListSerializer
        return PurchaseInvoiceHeaderSerializer

    def get_queryset(self):
        entity_id, entityfinid_id, subentity_id = self._scope_ids(required=True)
        base_qs = PurchaseInvoiceHeader.objects.all().select_related(
            "vendor", "vendor_ledger", "vendor_state",
            "supplier_state", "place_of_supply_state",
            "entity", "entityfinid", "subentity",
            "ref_document",
        )
        if entity_id is not None and entityfinid_id is not None:
            base_qs = base_qs.filter(entity_id=entity_id, entityfinid_id=entityfinid_id)
            if subentity_id is None:
                base_qs = base_qs.filter(subentity__isnull=True)
            else:
                base_qs = base_qs.filter(subentity_id=subentity_id)

        if self.request.method.upper() == "GET":
            return base_qs

        return base_qs.prefetch_related(
            Prefetch(
                "lines",
                queryset=PurchaseInvoiceLine.objects.select_related("product", "uom")
            ),
            "tax_summaries",
            "charges",
        )

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if self.request.method.upper() == "GET":
            # List response should avoid expensive per-row preview/navigation queries.
            ctx["skip_preview_numbers"] = True
            ctx["skip_navigation"] = True
        return ctx

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class PurchaseInvoiceRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = PurchaseInvoiceHeaderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def _scope_ids(self):
        entity = self.request.query_params.get("entity")
        entityfinid = self.request.query_params.get("entityfinid")
        subentity = self.request.query_params.get("subentity")

        if not entity or not entityfinid:
            raise ValidationError({"detail": "entity and entityfinid query params are required."})
        try:
            entity_id = int(entity)
            entityfinid_id = int(entityfinid)
            subentity_id = int(subentity) if subentity not in (None, "", "null") else None
        except (TypeError, ValueError):
            raise ValidationError({"detail": "entity/entityfinid/subentity must be integers."})
        return entity_id, entityfinid_id, subentity_id

    def get_queryset(self):
        entity_id, entityfinid_id, subentity_id = self._scope_ids()
        qs = (
            PurchaseInvoiceHeader.objects.all()
            .filter(entity_id=entity_id, entityfinid_id=entityfinid_id)
            .select_related(
                "vendor", "vendor_ledger", "vendor_state",
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
                "charges",
            )
        )
        if subentity_id is None:
            return qs.filter(subentity__isnull=True)
        return qs.filter(subentity_id=subentity_id)

    def perform_destroy(self, instance):
        policy = PurchaseSettingsService.get_policy(instance.entity_id, instance.subentity_id)
        if policy.delete_policy == "never":
            raise ValidationError({"detail": "Delete is disabled by purchase policy."})
        if policy.delete_policy == "draft_only" and int(instance.status) != int(PurchaseInvoiceHeader.Status.DRAFT):
            raise ValidationError({"detail": "Only draft purchase invoices can be deleted. Use cancel/credit-note flow."})
        if policy.delete_policy == "non_posted" and int(instance.status) == int(PurchaseInvoiceHeader.Status.POSTED):
            raise ValidationError({"detail": "Posted purchase invoices cannot be deleted."})
        super().perform_destroy(instance)

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

    def _scope_ids(self):
        entity = self.request.query_params.get("entity")
        entityfinid = self.request.query_params.get("entityfinid")
        subentity = self.request.query_params.get("subentity")
        if not entity or not entityfinid:
            raise ValidationError({"detail": "entity and entityfinid query params are required."})
        try:
            entity_id = int(entity)
            entityfinid_id = int(entityfinid)
            subentity_id = int(subentity) if subentity not in (None, "", "null") else None
        except (TypeError, ValueError):
            raise ValidationError({"detail": "entity/entityfinid/subentity must be integers."})
        return entity_id, entityfinid_id, subentity_id

    def get_queryset(self):
        entity_id, entityfinid_id, subentity_id = self._scope_ids()
        qs = (
            PurchaseInvoiceHeader.objects
            .filter(entity_id=entity_id, entityfinid_id=entityfinid_id)
            .select_related(
                "entity",
                "entityfinid",
                "subentity",
                "vendor",
                "vendor_ledger",
                "vendor_state",
               
            )
            .only(
                # keep DB payload smaller (tune as needed)
                "id", "entity_id", "entityfinid_id", "subentity_id",
                "doc_type", "status",
                "doc_code", "doc_no", "purchase_number",
                "bill_date", "posting_date", "credit_days", "due_date",
                "supplier_invoice_number", "supplier_invoice_date", "po_reference_no", "grn_reference_no",
                "vendor_id", "vendor_name", "vendor_gstin", "vendor_state_id",
                "vendor__partytype", "vendor_ledger_id", "vendor_ledger__ledger_code", "vendor_ledger__name",
                "supply_category", "default_taxability", "tax_regime",
                "is_igst", "is_reverse_charge", "is_itc_eligible",
                "gstr2b_match_status", "itc_claim_status", "itc_claim_period", "itc_block_reason",
                "total_taxable", "total_gst", "round_off", "grand_total",
                "created_at", "updated_at",
            )
        )
        if subentity_id is None:
            return qs.filter(subentity__isnull=True)
        return qs.filter(subentity_id=subentity_id)
