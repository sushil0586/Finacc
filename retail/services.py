from __future__ import annotations

from decimal import Decimal
from django.utils import timezone

from rest_framework.exceptions import ValidationError

from .models import RetailCloseBatch, RetailCloseBatchTicket, RetailConfig, RetailSession, RetailTicket


ZERO = Decimal("0.0000")


def quantize(value: Decimal | int | float | None) -> Decimal:
    return Decimal(str(value if value is not None else 0)).quantize(Decimal("0.0001"))


class RetailTicketTotalsService:
    @staticmethod
    def refresh(ticket: RetailTicket) -> RetailTicket:
        lines = list(ticket.lines.all())
        ticket.line_count = len(lines)
        ticket.total_qty = sum((quantize(line.qty) for line in lines), ZERO)
        ticket.total_free_qty = sum((quantize(line.free_qty) for line in lines), ZERO)
        ticket.total_issue_qty = sum((quantize(line.stock_issue_qty) for line in lines), ZERO)
        ticket.gross_value = sum((quantize(line.gross_value) for line in lines), ZERO)
        ticket.discount_value = sum((quantize(line.discount_amount) for line in lines), ZERO)
        ticket.taxable_value = sum((quantize(line.taxable_value) for line in lines), ZERO)
        ticket.save(
            update_fields=[
                "line_count",
                "total_qty",
                "total_free_qty",
                "total_issue_qty",
                "gross_value",
                "discount_value",
                "taxable_value",
                "updated_at",
            ]
        )
        return ticket


class RetailConfigResolutionService:
    @staticmethod
    def get_effective_config(*, entity_id: int, subentity_id: int | None) -> RetailConfig | None:
        queryset = RetailConfig.objects.filter(entity_id=entity_id)
        if subentity_id:
            return queryset.filter(subentity_id=subentity_id).first() or queryset.filter(subentity__isnull=True).first()
        return queryset.filter(subentity__isnull=True).first()


class RetailSessionService:
    @staticmethod
    def get_open_session(*, entity_id: int, subentity_id: int | None, location_id: int | None) -> RetailSession | None:
        queryset = RetailSession.objects.filter(entity_id=entity_id, status=RetailSession.Status.OPEN)
        if subentity_id:
            queryset = queryset.filter(subentity_id=subentity_id)
        else:
            queryset = queryset.filter(subentity__isnull=True)
        if location_id:
            queryset = queryset.filter(location_id=location_id)
        else:
            queryset = queryset.filter(location__isnull=True)
        return queryset.order_by("-opened_at", "-id").first()

    @staticmethod
    def open_session(
        *,
        entity_id: int,
        entityfin_id: int | None,
        subentity_id: int | None,
        location_id: int | None,
        session_date,
        opening_note: str = "",
        user=None,
    ) -> RetailSession:
        existing = RetailSessionService.get_open_session(entity_id=entity_id, subentity_id=subentity_id, location_id=location_id)
        if existing:
            return existing
        return RetailSession.objects.create(
            entity_id=entity_id,
            entityfin_id=entityfin_id,
            subentity_id=subentity_id,
            location_id=location_id,
            session_date=session_date,
            opening_note=opening_note or "",
            opened_by=user,
        )

    @staticmethod
    def summarize(session: RetailSession) -> dict:
        tickets = list(session.tickets.all())
        completed = [ticket for ticket in tickets if ticket.status == RetailTicket.Status.COMPLETED]
        draft_or_held = [ticket for ticket in tickets if ticket.status in (RetailTicket.Status.DRAFT, RetailTicket.Status.HELD)]
        return {
            "ticket_count": len(tickets),
            "completed_count": len(completed),
            "draft_or_held_count": len(draft_or_held),
            "gross_value": float(sum((quantize(ticket.gross_value) for ticket in tickets), ZERO)),
            "taxable_value": float(sum((quantize(ticket.taxable_value) for ticket in tickets), ZERO)),
        }

    @staticmethod
    def close_session(session: RetailSession, *, closing_note: str = "", user=None) -> RetailSession:
        if session.status == RetailSession.Status.CLOSED:
            raise ValidationError({"detail": "Retail session is already closed."})
        summary = RetailSessionService.summarize(session)
        if summary["draft_or_held_count"] > 0:
            raise ValidationError({"detail": "Close blocked. Complete or clear all draft/held tickets in this session first."})
        session.status = RetailSession.Status.CLOSED
        session.closing_note = closing_note or session.closing_note
        session.closed_at = timezone.now()
        session.closed_by = user
        session.save(update_fields=["status", "closing_note", "closed_at", "closed_by"])
        RetailCloseBatchService.build_for_session(session, user=user)
        return session


class RetailCloseBatchService:
    CLOSE_TRIGGER_BILLING_MODES = {
        RetailConfig.BillingMode.DAILY_SUMMARY,
    }
    CLOSE_TRIGGER_POSTING_MODES = {
        RetailConfig.PostingMode.ON_CLOSE,
    }

    @staticmethod
    def build_for_session(session: RetailSession, *, user=None) -> RetailCloseBatch:
        existing = getattr(session, "close_batch", None)
        if existing:
            return existing

        completed_tickets = list(
            session.tickets.filter(status=RetailTicket.Status.COMPLETED).order_by("id")
        )
        billing_ready_count = 0
        billing_pending_count = 0
        posting_ready_count = 0
        posting_pending_count = 0

        batch = RetailCloseBatch.objects.create(
            session=session,
            entity_id=session.entity_id,
            entityfin_id=session.entityfin_id,
            subentity_id=session.subentity_id,
            location_id=session.location_id,
            session_date=session.session_date,
            completed_ticket_count=len(completed_tickets),
            gross_value=sum((quantize(ticket.gross_value) for ticket in completed_tickets), ZERO),
            taxable_value=sum((quantize(ticket.taxable_value) for ticket in completed_tickets), ZERO),
            created_by=user,
        )

        ticket_links = []
        for ticket in completed_tickets:
            billing_status = ticket.billing_execution_status
            posting_status = ticket.posting_execution_status

            if (
                ticket.billing_mode_snapshot in RetailCloseBatchService.CLOSE_TRIGGER_BILLING_MODES
                and billing_status == RetailTicket.ExecutionStatus.PENDING
            ):
                billing_status = RetailTicket.ExecutionStatus.READY
            if (
                ticket.posting_mode_snapshot in RetailCloseBatchService.CLOSE_TRIGGER_POSTING_MODES
                and posting_status == RetailTicket.ExecutionStatus.PENDING
            ):
                posting_status = RetailTicket.ExecutionStatus.READY

            if billing_status == RetailTicket.ExecutionStatus.READY:
                billing_ready_count += 1
            else:
                billing_pending_count += 1

            if posting_status == RetailTicket.ExecutionStatus.READY:
                posting_ready_count += 1
            else:
                posting_pending_count += 1

            updates = []
            if ticket.billing_execution_status != billing_status:
                ticket.billing_execution_status = billing_status
                updates.append("billing_execution_status")
            if ticket.posting_execution_status != posting_status:
                ticket.posting_execution_status = posting_status
                updates.append("posting_execution_status")
            if updates:
                updates.extend(["updated_at"])
                ticket.save(update_fields=updates)

            ticket_links.append(
                RetailCloseBatchTicket(
                    batch=batch,
                    ticket=ticket,
                    billing_status_snapshot=billing_status,
                    posting_status_snapshot=posting_status,
                )
            )

        if ticket_links:
            RetailCloseBatchTicket.objects.bulk_create(ticket_links)

        batch.billing_ready_count = billing_ready_count
        batch.billing_pending_count = billing_pending_count
        batch.posting_ready_count = posting_ready_count
        batch.posting_pending_count = posting_pending_count
        batch.save(
            update_fields=[
                "billing_ready_count",
                "billing_pending_count",
                "posting_ready_count",
                "posting_pending_count",
            ]
        )
        return batch


class RetailPolicySnapshotService:
    @staticmethod
    def apply(ticket: RetailTicket) -> RetailTicket:
        config = RetailConfigResolutionService.get_effective_config(entity_id=ticket.entity_id, subentity_id=ticket.subentity_id)
        ticket.billing_mode_snapshot = getattr(config, "billing_mode", RetailConfig.BillingMode.INVOICE_PER_TICKET)
        ticket.posting_mode_snapshot = getattr(config, "posting_mode", RetailConfig.PostingMode.REAL_TIME)

        if ticket.status == RetailTicket.Status.COMPLETED:
            ticket.billing_execution_status = (
                RetailTicket.ExecutionStatus.READY
                if ticket.billing_mode_snapshot == RetailConfig.BillingMode.INVOICE_PER_TICKET
                else RetailTicket.ExecutionStatus.PENDING
            )
            ticket.posting_execution_status = (
                RetailTicket.ExecutionStatus.READY
                if ticket.posting_mode_snapshot == RetailConfig.PostingMode.REAL_TIME
                else RetailTicket.ExecutionStatus.PENDING
            )
        else:
            ticket.billing_execution_status = RetailTicket.ExecutionStatus.PENDING
            ticket.posting_execution_status = RetailTicket.ExecutionStatus.PENDING
        return ticket


class RetailTicketSessionAssignmentService:
    @staticmethod
    def assign(ticket: RetailTicket) -> RetailTicket:
        open_session = RetailSessionService.get_open_session(
            entity_id=ticket.entity_id,
            subentity_id=ticket.subentity_id,
            location_id=ticket.location_id,
        )
        ticket.session = open_session
        return ticket


class RetailTicketCompletionService:
    @staticmethod
    def validate(ticket: RetailTicket) -> None:
        RetailTicketTotalsService.refresh(ticket)
        if ticket.status == RetailTicket.Status.COMPLETED:
            raise ValidationError({"detail": "Retail ticket is already completed."})
        if ticket.status == RetailTicket.Status.CANCELLED:
            raise ValidationError({"detail": "Cancelled retail ticket cannot be completed."})
        if not ticket.location_id:
            raise ValidationError({"detail": "Stock location is required before completing the retail ticket."})
        if ticket.line_count <= 0:
            raise ValidationError({"detail": "Add at least one line before completing the retail ticket."})
        invalid_lines = []
        for line in ticket.lines.all():
            if quantize(line.qty) <= ZERO:
                invalid_lines.append(line.line_no)
        if invalid_lines:
            raise ValidationError({"detail": f"Line quantity must be greater than zero for lines: {', '.join(map(str, invalid_lines))}."})

    @staticmethod
    def complete(ticket: RetailTicket, *, user=None) -> RetailTicket:
        RetailTicketCompletionService.validate(ticket)
        ticket.status = RetailTicket.Status.COMPLETED
        ticket.completed_at = ticket.completed_at or ticket.updated_at
        ticket.completed_by = user
        ticket.updated_by = user
        RetailPolicySnapshotService.apply(ticket)
        ticket.save(
            update_fields=[
                "status",
                "completed_at",
                "completed_by",
                "updated_by",
                "updated_at",
                "billing_mode_snapshot",
                "posting_mode_snapshot",
                "billing_execution_status",
                "posting_execution_status",
            ]
        )
        return RetailTicketTotalsService.refresh(ticket)
