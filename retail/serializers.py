from __future__ import annotations

from django.db import transaction
from rest_framework import serializers

from catalog.models import Product, ProductBarcode, UnitOfMeasure
from entity.models import Godown, SubEntity
from financial.models import account

from .models import RetailCloseBatch, RetailCloseBatchTicket, RetailConfig, RetailSession, RetailTicket, RetailTicketLine
from .services import RetailPolicySnapshotService, RetailTicketSessionAssignmentService, RetailTicketTotalsService


class RetailTicketLineWriteSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)
    line_source = serializers.ChoiceField(choices=RetailTicketLine.LineSource.choices, required=False, default=RetailTicketLine.LineSource.SCAN)
    product = serializers.IntegerField()
    barcode = serializers.IntegerField(required=False, allow_null=True)
    scanned_barcode = serializers.CharField(required=False, allow_blank=True, max_length=50)
    uom = serializers.IntegerField(required=False, allow_null=True)
    uom_code_snapshot = serializers.CharField(required=False, allow_blank=True, max_length=20)
    pack_size_snapshot = serializers.DecimalField(required=False, max_digits=18, decimal_places=4)
    qty = serializers.DecimalField(max_digits=18, decimal_places=4)
    free_qty = serializers.DecimalField(required=False, max_digits=18, decimal_places=4, default=0)
    stock_issue_qty = serializers.DecimalField(required=False, max_digits=18, decimal_places=4, default=0)
    rate = serializers.DecimalField(required=False, max_digits=18, decimal_places=4, default=0)
    gross_value = serializers.DecimalField(required=False, max_digits=18, decimal_places=4, default=0)
    discount_percent = serializers.DecimalField(required=False, max_digits=9, decimal_places=4, default=0)
    discount_amount = serializers.DecimalField(required=False, max_digits=18, decimal_places=4, default=0)
    taxable_value = serializers.DecimalField(required=False, max_digits=18, decimal_places=4, default=0)
    promotion_id_snapshot = serializers.IntegerField(required=False, allow_null=True)
    promotion_code_snapshot = serializers.CharField(required=False, allow_blank=True, max_length=50)
    gst_snapshot = serializers.JSONField(required=False)
    note = serializers.CharField(required=False, allow_blank=True, max_length=200)


class RetailTicketLineReadSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.productname", read_only=True)
    sku = serializers.CharField(source="product.productcode", read_only=True)

    class Meta:
        model = RetailTicketLine
        fields = [
            "id",
            "line_no",
            "line_source",
            "product",
            "product_name",
            "sku",
            "barcode",
            "scanned_barcode",
            "uom",
            "uom_code_snapshot",
            "pack_size_snapshot",
            "qty",
            "free_qty",
            "stock_issue_qty",
            "rate",
            "gross_value",
            "discount_percent",
            "discount_amount",
            "taxable_value",
            "promotion_id_snapshot",
            "promotion_code_snapshot",
            "gst_snapshot",
            "note",
        ]


class RetailTicketReadSerializer(serializers.ModelSerializer):
    lines = RetailTicketLineReadSerializer(many=True, read_only=True)
    location_name = serializers.CharField(source="location.display_name", read_only=True)
    customer_label = serializers.SerializerMethodField()
    session_code = serializers.CharField(source="session.session_code", read_only=True)

    class Meta:
        model = RetailTicket
        fields = [
            "id",
            "ticket_no",
            "bill_date",
            "status",
            "entity",
            "entityfin",
            "subentity",
            "location",
            "location_name",
            "session",
            "session_code",
            "customer",
            "customer_label",
            "customer_name",
            "customer_phone",
            "customer_email",
            "customer_gstin",
            "address1",
            "address2",
            "city",
            "state_code",
            "pincode",
            "narration",
            "line_count",
            "total_qty",
            "total_free_qty",
            "total_issue_qty",
            "gross_value",
            "discount_value",
            "taxable_value",
            "billing_mode_snapshot",
            "posting_mode_snapshot",
            "billing_execution_status",
            "posting_execution_status",
            "billing_reference",
            "posting_reference",
            "created_at",
            "completed_at",
            "updated_at",
            "lines",
        ]

    def get_customer_label(self, obj: RetailTicket) -> str:
        if obj.customer_id and getattr(obj.customer, "accountname", None):
            return str(obj.customer.accountname)
        return obj.customer_name or ""


class RetailTicketWriteSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)
    bill_date = serializers.DateField()
    status = serializers.ChoiceField(choices=RetailTicket.Status.choices, required=False, default=RetailTicket.Status.DRAFT)
    location = serializers.IntegerField(required=False, allow_null=True)
    customer = serializers.IntegerField(required=False, allow_null=True)
    customer_name = serializers.CharField(required=False, allow_blank=True, max_length=200)
    customer_phone = serializers.CharField(required=False, allow_blank=True, max_length=30)
    customer_email = serializers.CharField(required=False, allow_blank=True, max_length=120)
    customer_gstin = serializers.CharField(required=False, allow_blank=True, max_length=30)
    address1 = serializers.CharField(required=False, allow_blank=True, max_length=255)
    address2 = serializers.CharField(required=False, allow_blank=True, max_length=255)
    city = serializers.CharField(required=False, allow_blank=True, max_length=100)
    state_code = serializers.CharField(required=False, allow_blank=True, max_length=20)
    pincode = serializers.CharField(required=False, allow_blank=True, max_length=12)
    narration = serializers.CharField(required=False, allow_blank=True, max_length=500)
    lines = RetailTicketLineWriteSerializer(many=True, required=False)

    def validate(self, attrs):
        entity_id = attrs["entity"]
        subentity_id = attrs.get("subentity")
        location_id = attrs.get("location")
        customer_id = attrs.get("customer")

        if subentity_id and not SubEntity.objects.filter(id=subentity_id, entity_id=entity_id).exists():
            raise serializers.ValidationError({"subentity": "Selected subentity does not belong to the entity."})
        if location_id and not Godown.objects.filter(id=location_id, entity_id=entity_id).exists():
            raise serializers.ValidationError({"location": "Selected location does not belong to the entity."})
        if customer_id and not account.objects.filter(id=customer_id, entity_id=entity_id).exists():
            raise serializers.ValidationError({"customer": "Selected customer does not belong to the entity."})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        lines_data = validated_data.pop("lines", [])
        request = self.context.get("request")
        ticket = RetailTicket.objects.create(
            entity_id=validated_data["entity"],
            entityfin_id=validated_data.get("entityfinid"),
            subentity_id=validated_data.get("subentity"),
            bill_date=validated_data["bill_date"],
            status=validated_data.get("status", RetailTicket.Status.DRAFT),
            location_id=validated_data.get("location"),
            customer_id=validated_data.get("customer"),
            customer_name=validated_data.get("customer_name", ""),
            customer_phone=validated_data.get("customer_phone", ""),
            customer_email=validated_data.get("customer_email", ""),
            customer_gstin=validated_data.get("customer_gstin", ""),
            address1=validated_data.get("address1", ""),
            address2=validated_data.get("address2", ""),
            city=validated_data.get("city", ""),
            state_code=validated_data.get("state_code", ""),
            pincode=validated_data.get("pincode", ""),
            narration=validated_data.get("narration", ""),
            created_by=getattr(request, "user", None),
            updated_by=getattr(request, "user", None),
        )
        RetailPolicySnapshotService.apply(ticket)
        RetailTicketSessionAssignmentService.assign(ticket)
        ticket.save(
            update_fields=[
                "billing_mode_snapshot",
                "posting_mode_snapshot",
                "billing_execution_status",
                "posting_execution_status",
                "session",
            ]
        )
        self._replace_lines(ticket, lines_data)
        return RetailTicket.objects.prefetch_related("lines").select_related("location", "customer", "session").get(pk=ticket.pk)

    @transaction.atomic
    def update(self, instance: RetailTicket, validated_data):
        if instance.status == RetailTicket.Status.COMPLETED:
            raise serializers.ValidationError({"detail": "Completed retail ticket cannot be edited."})
        if instance.status == RetailTicket.Status.CANCELLED:
            raise serializers.ValidationError({"detail": "Cancelled retail ticket cannot be edited."})
        lines_data = validated_data.pop("lines", None)
        request = self.context.get("request")
        instance.entityfin_id = validated_data.get("entityfinid")
        instance.subentity_id = validated_data.get("subentity")
        instance.bill_date = validated_data["bill_date"]
        instance.status = validated_data.get("status", instance.status)
        instance.location_id = validated_data.get("location")
        instance.customer_id = validated_data.get("customer")
        instance.customer_name = validated_data.get("customer_name", "")
        instance.customer_phone = validated_data.get("customer_phone", "")
        instance.customer_email = validated_data.get("customer_email", "")
        instance.customer_gstin = validated_data.get("customer_gstin", "")
        instance.address1 = validated_data.get("address1", "")
        instance.address2 = validated_data.get("address2", "")
        instance.city = validated_data.get("city", "")
        instance.state_code = validated_data.get("state_code", "")
        instance.pincode = validated_data.get("pincode", "")
        instance.narration = validated_data.get("narration", "")
        instance.updated_by = getattr(request, "user", None)
        RetailPolicySnapshotService.apply(instance)
        RetailTicketSessionAssignmentService.assign(instance)
        instance.save()
        if lines_data is not None:
            self._replace_lines(instance, lines_data)
        RetailTicketTotalsService.refresh(instance)
        return RetailTicket.objects.prefetch_related("lines").select_related("location", "customer", "session").get(pk=instance.pk)

    def _replace_lines(self, ticket: RetailTicket, lines_data):
        ticket.lines.all().delete()
        rows = []
        for idx, row in enumerate(lines_data, start=1):
            product = Product.objects.get(pk=row["product"])
            barcode_id = row.get("barcode")
            if barcode_id:
                ProductBarcode.objects.get(pk=barcode_id, product_id=product.id)
            uom_id = row.get("uom")
            if uom_id:
                UnitOfMeasure.objects.get(pk=uom_id)
            rows.append(
                RetailTicketLine(
                    ticket=ticket,
                    line_no=idx,
                    line_source=row.get("line_source", RetailTicketLine.LineSource.SCAN),
                    product=product,
                    barcode_id=barcode_id,
                    scanned_barcode=row.get("scanned_barcode", ""),
                    uom_id=uom_id,
                    uom_code_snapshot=row.get("uom_code_snapshot", ""),
                    pack_size_snapshot=row.get("pack_size_snapshot", 0),
                    qty=row.get("qty", 0),
                    free_qty=row.get("free_qty", 0),
                    stock_issue_qty=row.get("stock_issue_qty", 0),
                    rate=row.get("rate", 0),
                    gross_value=row.get("gross_value", 0),
                    discount_percent=row.get("discount_percent", 0),
                    discount_amount=row.get("discount_amount", 0),
                    taxable_value=row.get("taxable_value", 0),
                    promotion_id_snapshot=row.get("promotion_id_snapshot"),
                    promotion_code_snapshot=row.get("promotion_code_snapshot", ""),
                    gst_snapshot=row.get("gst_snapshot", {}) or {},
                    note=row.get("note", ""),
                )
            )
        if rows:
            RetailTicketLine.objects.bulk_create(rows)
        RetailTicketTotalsService.refresh(ticket)


class RetailConfigReadSerializer(serializers.ModelSerializer):
    default_walk_in_customer_label = serializers.CharField(source="default_walk_in_customer.accountname", read_only=True)
    default_location_name = serializers.CharField(source="default_location.display_name", read_only=True)

    class Meta:
        model = RetailConfig
        fields = [
            "id",
            "billing_mode",
            "posting_mode",
            "customer_mode",
            "walk_in_capture_mode",
            "auto_create_customer_mode",
            "default_walk_in_customer",
            "default_walk_in_customer_label",
            "default_location",
            "default_location_name",
            "allow_negative_stock",
            "allow_hold_resume",
        ]


class RetailSessionReadSerializer(serializers.ModelSerializer):
    location_name = serializers.CharField(source="location.display_name", read_only=True)
    summary = serializers.SerializerMethodField()
    close_batch = serializers.SerializerMethodField()

    class Meta:
        model = RetailSession
        fields = [
            "id",
            "session_code",
            "session_date",
            "status",
            "location",
            "location_name",
            "opening_note",
            "closing_note",
            "opened_at",
            "closed_at",
            "summary",
            "close_batch",
        ]

    def get_summary(self, obj: RetailSession) -> dict:
        from .services import RetailSessionService
        return RetailSessionService.summarize(obj)

    def get_close_batch(self, obj: RetailSession) -> dict | None:
        batch = getattr(obj, "close_batch", None)
        if not batch:
            return None
        return RetailCloseBatchReadSerializer(batch).data


class RetailCloseBatchReadSerializer(serializers.ModelSerializer):
    session_code = serializers.CharField(source="session.session_code", read_only=True)
    location_name = serializers.CharField(source="location.display_name", read_only=True)

    class Meta:
        model = RetailCloseBatch
        fields = [
            "id",
            "batch_code",
            "trigger_mode",
            "session",
            "session_code",
            "session_date",
            "location",
            "location_name",
            "completed_ticket_count",
            "billing_ready_count",
            "billing_pending_count",
            "posting_ready_count",
            "posting_pending_count",
            "gross_value",
            "taxable_value",
            "created_at",
        ]


class RetailCloseBatchTicketReadSerializer(serializers.ModelSerializer):
    ticket_no = serializers.CharField(source="ticket.ticket_no", read_only=True)
    bill_date = serializers.DateField(source="ticket.bill_date", read_only=True)
    ticket_status = serializers.CharField(source="ticket.status", read_only=True)
    customer_label = serializers.SerializerMethodField()
    gross_value = serializers.DecimalField(source="ticket.gross_value", max_digits=18, decimal_places=4, read_only=True)
    taxable_value = serializers.DecimalField(source="ticket.taxable_value", max_digits=18, decimal_places=4, read_only=True)
    billing_mode_snapshot = serializers.CharField(source="ticket.billing_mode_snapshot", read_only=True)
    posting_mode_snapshot = serializers.CharField(source="ticket.posting_mode_snapshot", read_only=True)

    class Meta:
        model = RetailCloseBatchTicket
        fields = [
            "id",
            "ticket",
            "ticket_no",
            "bill_date",
            "ticket_status",
            "customer_label",
            "gross_value",
            "taxable_value",
            "billing_mode_snapshot",
            "posting_mode_snapshot",
            "billing_status_snapshot",
            "posting_status_snapshot",
            "created_at",
        ]

    def get_customer_label(self, obj: RetailCloseBatchTicket) -> str:
        ticket = obj.ticket
        if ticket.customer_id and getattr(ticket.customer, "accountname", None):
            return str(ticket.customer.accountname)
        return ticket.customer_name or ""


class RetailCloseBatchDetailSerializer(RetailCloseBatchReadSerializer):
    ticket_rows = RetailCloseBatchTicketReadSerializer(source="ticket_links", many=True, read_only=True)

    class Meta(RetailCloseBatchReadSerializer.Meta):
        fields = RetailCloseBatchReadSerializer.Meta.fields + [
            "ticket_rows",
        ]
