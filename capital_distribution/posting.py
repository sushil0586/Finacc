from __future__ import annotations

from django.db import transaction

from posting.common.static_accounts import StaticAccountCodes
from posting.models import EntityStaticAccountMap, Entry, EntryStatus, TxnType
from posting.services.posting_service import JLInput, PostingService

from .models import CapitalDistributionAccountMapping, CapitalDistributionLine, CapitalDistributionRun


class CapitalDistributionPostingAdapter:
    @staticmethod
    def _journal_lines(*, run: CapitalDistributionRun, reverse: bool = False) -> list[JLInput]:
        appropriation_mapping = EntityStaticAccountMap.objects.filter(
            entity_id=run.entity_id,
            sub_entity__isnull=True,
            static_account__code=StaticAccountCodes.PROFIT_LOSS_APPROPRIATION,
            static_account__is_active=True,
            is_active=True,
            account__isactive=True,
            account__ledger__isactive=True,
            ledger__isactive=True,
        ).select_related("account__ledger", "ledger").first()
        if not appropriation_mapping or not appropriation_mapping.account_id or not appropriation_mapping.ledger_id:
            raise ValueError("Profit and Loss Appropriation needs an entity-level account and ledger mapping in Posting Setup.")
        appropriation_account_id = appropriation_mapping.account_id
        appropriation_ledger_id = appropriation_mapping.ledger_id
        mappings = {
            row.ownership_id: row
            for row in CapitalDistributionAccountMapping.objects.filter(
                entity_id=run.entity_id,
                ownership_id__in=run.lines.values_list("stakeholder__ownership_id", flat=True),
                isactive=True,
            ).select_related(
                "capital_account__ledger",
                "current_account__ledger",
                "drawings_account__ledger",
            )
        }
        result: list[JLInput] = []
        for line in run.lines.select_related("stakeholder__ownership").order_by("segment_id", "id"):
            mapping = mappings.get(line.stakeholder.ownership_id)
            if not mapping:
                raise ValueError(f"No active posting account mapping exists for {line.stakeholder.target_name}.")
            destination = mapping.destination_account(line.stakeholder.destination_account_preference)
            if not destination or not destination.ledger_id:
                raise ValueError(f"A valid destination ledger is required for {line.stakeholder.target_name}.")
            stakeholder_is_debit = line.side == CapitalDistributionLine.Side.DEBIT
            if reverse:
                stakeholder_is_debit = not stakeholder_is_debit
            description = f"{line.stakeholder.target_name} | {line.get_component_type_display()}"
            result.extend((
                JLInput(
                    account_id=destination.id,
                    ledger_id=destination.ledger_id,
                    drcr=stakeholder_is_debit,
                    amount=line.amount,
                    description=("Reversal | " if reverse else "") + description,
                    detail_id=line.id,
                ),
                JLInput(
                    account_id=appropriation_account_id,
                    ledger_id=appropriation_ledger_id,
                    drcr=not stakeholder_is_debit,
                    amount=line.amount,
                    description=("Reversal | " if reverse else "") + description,
                    detail_id=line.id,
                ),
            ))
        if not result:
            raise ValueError("The distribution run has no non-zero calculation lines to post.")
        return result

    @staticmethod
    def _service(run: CapitalDistributionRun, user_id: int | None) -> PostingService:
        return PostingService(
            entity_id=run.entity_id,
            entityfin_id=run.entityfin_id,
            subentity_id=run.subentity_id,
            user_id=user_id,
        )

    @classmethod
    @transaction.atomic
    def post(cls, *, run: CapitalDistributionRun, user_id: int | None) -> Entry:
        return cls._service(run, user_id).post(
            txn_type=TxnType.CAPITAL_DISTRIBUTION,
            txn_id=run.id,
            voucher_no=f"CAPDIST-{run.entityfin.year_code or run.entityfin_id}-{run.id}",
            voucher_date=run.period_to,
            posting_date=run.period_to,
            narration=f"Capital distribution run {run.id}: {run.period_from} to {run.period_to}",
            jl_inputs=cls._journal_lines(run=run),
            im_inputs=(),
            use_advisory_lock=True,
            mark_posted=True,
        )

    @classmethod
    @transaction.atomic
    def reverse(cls, *, run: CapitalDistributionRun, user_id: int | None) -> Entry:
        entry = cls._service(run, user_id).post(
            txn_type=TxnType.CAPITAL_DISTRIBUTION,
            txn_id=run.id,
            voucher_no=f"CAPDIST-{run.entityfin.year_code or run.entityfin_id}-{run.id}",
            voucher_date=run.period_to,
            posting_date=run.period_to,
            narration=f"Reversal of capital distribution run {run.id}",
            jl_inputs=cls._journal_lines(run=run, reverse=True),
            im_inputs=(),
            use_advisory_lock=True,
            mark_posted=True,
        )
        Entry.objects.filter(pk=entry.pk).update(
            status=EntryStatus.REVERSED,
            narration=f"Reversed capital distribution run {run.id}",
        )
        entry.refresh_from_db()
        return entry
